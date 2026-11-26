"""Paired semantic graph benchmark, only aggregates exported."""
import io,json,time,tempfile,warnings
from collections import Counter
from pathlib import Path
import numpy as np
from PIL import Image
from huggingface_hub import HfApi
from paddleocr import TextDetection,TextRecognition
from sklearn.feature_extraction import FeatureHasher
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.exceptions import ConvergenceWarning
import semantic_ranker_run as prior
from semantic_ranker_v2_run import fit_v2
from semantic_ranker_v2 import enriched,protected,synthetic_docs
from semantic_ranker import choose
from total_row_evidence import group_rows,select
from row_ink_run import prepare,tally
from perspective_research_run import distorted,QUADS
from receipt_structure import fetch,DET,REC,REC_REV,fixture
from document_graph import graph_observations,diagnose,self_test

prior.LIMITS={'test':32,'val':137,'train':160}

def fit_graph(real,synthetic,hasher):
    f=[];y=[];w=[];meta={'real_documents':0,'synthetic_documents':0,'negative_synthetic':0,'weak_real_missing_reference':0,'ambiguous_matches_skipped':0}
    for source,docs in [('real',real),('synthetic',synthetic)]:
        for lines,expected in docs:
            obs=graph_observations(lines)
            if not obs:continue
            labels=[int(expected is not None and c.amount==expected) for c in obs]
            if source=='real':
                if not any(labels):
                    # Annotation may be wrong or OCR missing; do not use as a
                    # ground-truth absence example.
                    meta['weak_real_missing_reference']+=1;continue
                # Prefer explicit total-associated observations as positive
                # weak labels. Equal-value payment or item fields aren't
                # known total locations, so skip ambiguous matches.
                supported=any(z and c.features['v2:explicit_link'] for c,z in zip(obs,labels))
                for j,c in enumerate(obs):
                    if labels[j] and supported and not c.features['v2:explicit_link']:
                        labels[j]=-1;meta['ambiguous_matches_skipped']+=1
                meta['real_documents']+=1
            else:
                meta['synthetic_documents']+=1
                meta['negative_synthetic']+=int(expected is None)
                if expected is not None:
                    for j,c in enumerate(obs):
                        if labels[j] and not c.features['v2:explicit_link']:
                            labels[j]=0
            pos=labels.count(1);neg=labels.count(0)
            if not neg and not pos:continue
            # Weight by document, not its length. Synthetic data supplement
            # rather than overwhelm real examples.
            scale=1. if source=='real' else .35
            for c,z in zip(obs,labels):
                if z<0:continue
                f.append(c.features);y.append(z)
                w.append(scale*(.5 if pos and neg else 1.)/(pos if z else neg))
    if meta['real_documents']<40 or meta['negative_synthetic']<40:raise RuntimeError('Insufficient training coverage')
    x=hasher.transform(f);y=np.asarray(y);w=np.asarray(w);w*=len(w)/w.sum()
    meta.update(candidates=len(y),positives=int(y.sum()),features=2048,models={})
    models={'graph_logistic':LogisticRegression(C=1.,max_iter=600,random_state=42),
            'graph_mlp':MLPClassifier(hidden_layer_sizes=(48,),activation='relu',solver='adam',alpha=.01,max_iter=350,tol=1e-4,random_state=42)}
    for name,m in models.items():
        t=time.perf_counter()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always',ConvergenceWarning)
            m.fit(x,y,sample_weight=w)
        arrays=[m.coef_,m.intercept_] if name.endswith('logistic') else list(m.coefs_)+list(m.intercepts_)
        meta['models'][name]={'parameters':sum(a.size for a in arrays),'float32_bytes':4*sum(a.size for a in arrays),'fit_ms':round(1000*(time.perf_counter()-t),2),'convergence_warning':any(issubclass(a.category,ConvergenceWarning) for a in caught)}
    return models,meta


def evaluate(cases,models,hashers):
    out={'n':0,'positive':0,'negative':0,'methods':{},'diagnostics':Counter(),'gates':{},'median_rank_ms':None}
    lat=[]
    for lines,expected in cases:
        t=time.perf_counter()
        lines,groups=group_rows(lines)
        v2=enriched(lines);graph=graph_observations(lines)
        if [(c.amount,c.line,c.score) for c in v2]!=[(c.amount,c.line,c.score) for c in graph]:
            raise RuntimeError('Graph changed observed values or provenance')
        if expected is not None:out['diagnostics'].update(diagnose(lines,graph,expected))
        for name,model in models.items():
            obs=graph if name.startswith('graph_') else v2
            h=hashers['graph' if name.startswith('graph_') else 'v2']
            scores=model.predict_proba(h.transform([c.features for c in obs]))[:,list(model.classes_).index(1)] if obs else []
            row,reason,_=select(lines,groups,obs,scores)
            out['gates'].setdefault(name,Counter())[reason]+=1
            values={'top1_diagnostic':choose(obs,scores,threshold=0,margin=1e-9,require_ocr=False),
                    'rank_only_diagnostic':choose(obs,scores,threshold=.85,margin=.15,require_ocr=True),
                    'protected':protected(lines,obs,scores),'row_only':row}
            for tag,value in values.items():
                tally(out['methods'].setdefault(name+'_'+tag,dict(n=0,correct=0,wrong=0,refused=0,negative_rejected=0)),value,expected)
        out['n']+=1;out['positive']+=int(expected is not None);out['negative']+=int(expected is None)
        lat.append((time.perf_counter()-t)*1000)
    out['median_rank_ms']=round(float(np.median(lat)),3) if lat else None
    return out

def save(result,name):
    Path(name).write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result,indent=2,sort_keys=True))

def main():
    self_test()
    samples,meta=prior.sample(prior.preflight(HfApi()))
    result={'dataset_revision':prior.DATA_REV,'sampling':meta,'training':{},'evaluations':{},'synthetic':{},'models':{}}
    save(result,'graph_preflight_results.json')
    dp,dm=fetch(DET,prior.DET_REV);rp,rm=fetch(REC,REC_REV)
    result['models']={DET:dm,REC:rm}
    det=TextDetection(model_name=DET,model_dir=str(dp),device='cpu',enable_mkldnn=False,cpu_threads=2)
    rec=TextRecognition(model_name=REC,model_dir=str(rp),device='cpu',enable_mkldnn=False,cpu_threads=2)
    hashers={'v2':FeatureHasher(n_features=1024,input_type='dict',alternate_sign=False),
             'graph':FeatureHasher(n_features=2048,input_type='dict',alternate_sign=False)}
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp)
        def ocr(im):return prepare(im,det,rec,folder)[1]
        def load(rows):
            for _,data,expected in rows:
                with Image.open(io.BytesIO(data)) as im:yield ocr(im.convert('RGB')),expected
        train=list(load(samples['train']))
        synth=list(synthetic_docs(183,240))
        models,result['training']['v2']=fit_v2(train,synth,hashers['v2'])
        graph_models,result['training']['graph']=fit_graph(train,synth,hashers['graph'])
        models.update(graph_models)
        del train
        save(result,'graph_training_results.json')
        for name,selected in [('reused_val',samples['val'][:40]),('last_val',samples['val'][120:]),('test',samples['test'])]:
            result['evaluations'][name]=evaluate(load(selected),models,hashers)
            save(result,'graph_'+name+'_results.json')
        for kind in ('split','combined','tilt','blur','duplicate','missing'):
            result['synthetic'][kind]=evaluate(((ocr(im),e) for im,e in (fixture(i,kind) for i in range(4))),models,hashers)
        for kind in ('split','combined','duplicate','missing'):
            result['synthetic']['perspective_'+kind]=evaluate(((ocr(im),e) for im,e in (distorted(kind,12,q) for q in QUADS)),models,hashers)
        result['synthetic']['structured_new']=evaluate(synthetic_docs(917,120),models,hashers)
    save(result,'graph_final_results.json')
if __name__=='__main__':main()
