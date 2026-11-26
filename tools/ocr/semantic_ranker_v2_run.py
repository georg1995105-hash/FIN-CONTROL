"""Train on separated real weak labels and synthetic negative documents.
Compare both generations on the same held-out OCR. Never persist receipt
text, images, hashes, per-document outputs or weights.
"""
import io
import json
import tempfile
import time
import warnings
from pathlib import Path
from importlib.metadata import version
import numpy as np
from PIL import Image
from huggingface_hub import HfApi
from paddleocr import TextDetection,TextRecognition
from sklearn.feature_extraction import FeatureHasher
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.exceptions import ConvergenceWarning
import semantic_ranker_run as prior
from receipt_structure import process,fetch,DET,REC,REC_REV,fixture
from semantic_ranker import candidates,choose
from semantic_ranker_v2 import enriched,protected,synthetic_docs,self_test
from document_structure import analyze
from layout_diagnostics import anchor_candidate

# Identical deterministic order. Prior val first 40; next 40 never processed
# in prior ranker experiments. Test is previously reused diagnostics.
prior.LIMITS={'test':32,'val':80,'train':160}
N_FEATURES=1024

def save(result,name):
    Path(name).write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result,indent=2,sort_keys=True))

def fit_v2(real,synthetic,hasher):
    f=[];y=[];w=[];meta={'real_documents':0,'synthetic_documents':0,'negative_synthetic':0,'weak_real_missing_reference':0,'ambiguous_matches_skipped':0}
    for source,docs in [('real',real),('synthetic',synthetic)]:
        for lines,expected in docs:
            obs=enriched(lines)
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
    meta.update(candidates=len(y),positives=int(y.sum()),features=N_FEATURES,models={})
    models={'v2_logistic':LogisticRegression(C=1.,max_iter=600,random_state=42),
            'v2_mlp':MLPClassifier(hidden_layer_sizes=(48,),activation='relu',solver='adam',alpha=.01,max_iter=350,tol=1e-4,random_state=42)}
    for name,m in models.items():
        t=time.perf_counter()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always',ConvergenceWarning)
            m.fit(x,y,sample_weight=w)
        arrays=[m.coef_,m.intercept_] if name.endswith('logistic') else list(m.coefs_)+list(m.intercepts_)
        meta['models'][name]={'parameters':sum(a.size for a in arrays),'float32_bytes':4*sum(a.size for a in arrays),'fit_ms':round(1000*(time.perf_counter()-t),2),'convergence_warning':any(issubclass(a.category,ConvergenceWarning) for a in caught)}
    return models,meta

def evaluate(docs,base,bh,new,nh):
    out={'n':0,'positive_docs':0,'negative_docs':0,'reference_present':0,'methods':{}}
    for lines,expected in docs:
        obs=candidates(lines);v2=enriched(lines)
        out['n']+=1
        out['positive_docs']+=int(expected is not None)
        out['negative_docs']+=int(expected is None)
        out['reference_present']+=int(expected is not None and any(c.amount==expected for c in obs))
        values={'old_anchor':anchor_candidate(lines),'old_structure':analyze(lines).amount}
        for models,hasher,observations,isnew in [(base,bh,obs,False),(new,nh,v2,True)]:
            for name,m in models.items():
                if observations:
                    scores=m.predict_proba(hasher.transform([c.features for c in observations]))[:,list(m.classes_).index(1)]
                    values[name+'_top1']=choose(observations,scores,threshold=0,margin=1e-9,require_ocr=False)
                    values[name+'_gated']=choose(observations,scores,threshold=.85,margin=.15,require_ocr=True)
                    if isnew:values[name+'_protected']=protected(lines,observations,scores)
                else:
                    values[name+'_top1']=None;values[name+'_gated']=None
                    if isnew:values[name+'_protected']=None
        for name,value in values.items():
            row=out['methods'].setdefault(name,dict(n=0,accepted=0,correct=0,wrong=0,negative_rejected=0,negative_accepted=0,positive_rejected=0))
            prior.count(row,value,expected)
            row['negative_rejected']+=int(expected is None and value is None)
            row['negative_accepted']+=int(expected is None and value is not None)
            row['positive_rejected']+=int(expected is not None and value is None)
    return out

def main():
    self_test()
    api=HfApi();samples,meta=prior.sample(prior.preflight(api))
    result={'dataset_revision':prior.DATA_REV,'sampling':meta,'packages':{n:version(n) for n in ('paddleocr','paddlepaddle','scikit-learn','numpy')},'training':{},'evaluations':{},'synthetic':{},'models':{}}
    save(result,'semantic_v2_preflight_results.json')
    dp,dm=fetch(DET,prior.DET_REV);rp,rm=fetch(REC,REC_REV)
    result['models']={DET:dm,REC:rm}
    det=TextDetection(model_name=DET,model_dir=str(dp),device='cpu',enable_mkldnn=False,cpu_threads=2)
    rec=TextRecognition(model_name=REC,model_dir=str(rp),device='cpu',enable_mkldnn=False,cpu_threads=2)
    bh=FeatureHasher(n_features=prior.N_FEATURES,input_type='dict',alternate_sign=False)
    nh=FeatureHasher(n_features=N_FEATURES,input_type='dict',alternate_sign=False)
    with tempfile.TemporaryDirectory() as temp:
        folder=Path(temp)
        def load(selected):
            for _,data,expected in selected:
                with Image.open(io.BytesIO(data)) as im:
                    yield process(im,det,rec,folder),expected
        train=list(load(samples['train']))
        base,result['training']['baseline']=prior.fit([(candidates(lines),expected) for lines,expected in train[:100]],bh)
        new,result['training']['v2']=fit_v2(train,list(synthetic_docs(183,240)),nh)
        del train
        save(result,'semantic_v2_training_results.json')
        # No tuning after these evaluations. The novel val subset is separate
        # from prior used val by deterministic order and exact-byte dedup.
        for name,selected in [('prior_val',samples['val'][:40]),('new_val',samples['val'][40:]),('test',samples['test'])]:
            result['evaluations'][name]=evaluate(load(selected),base,bh,new,nh)
            save(result,'semantic_v2_'+name+'_results.json')
        for kind in ('split','combined','tilt','blur','duplicate','missing'):
            def cases():
                for i in range(4):
                    im,expected=fixture(i,kind)
                    yield process(im,det,rec,folder),expected
            result['synthetic'][kind]=evaluate(cases(),base,bh,new,nh)
        result['synthetic']['new_structured']=evaluate(synthetic_docs(917,120),base,bh,new,nh)
    save(result,'semantic_v2_final_results.json')
if __name__=='__main__':main()
