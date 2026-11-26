"""Bounded review-evidence benchmark; no raw data or predictions saved.

Identical OCR, real training and held-out selection to previous semantic graph
benchmark. User-review suggestions are counted separately from supported
candidates; wrong suggestions are NOT automatic financial errors.
"""
import io,json,time,tempfile
from collections import Counter
from pathlib import Path
import numpy as np
from PIL import Image
from huggingface_hub import HfApi
from paddleocr import TextDetection,TextRecognition
from sklearn.feature_extraction import FeatureHasher
import semantic_ranker_run as prior
from semantic_ranker_v2_run import fit_v2
from semantic_ranker_v2 import enriched,synthetic_docs
from document_graph import graph_observations,diagnose
from document_graph_run import fit_graph
from document_evidence_triage import triage,near_miss_labels,self_test
from row_ink_run import prepare,tally
from total_row_evidence import group_rows,select
from perspective_research_run import distorted,QUADS
from receipt_structure import fetch,DET,REC,REC_REV,fixture

prior.LIMITS={'test':32,'val':137,'train':160}


def blank():return dict(n=0,supported_correct=0,supported_wrong=0,
    supported_negative=0,suggestion_correct=0,suggestion_wrong=0,
    suggestion_negative=0,suggested_total=0,ambiguous=0,needs_recapture=0,
    user_review_options_contains_reference=0,reference_observed=0,
    reference_high_ocr=0,reference_explicit_link=0,near_miss_labels=0,
    negative_rejected=0,review_without_auto=0,strict_reason={},state={})


def evaluate(cases,models,hashers):
    out={'n':0,'positive':0,'negative':0,'methods':{},'median_rank_ms':None}
    lat=[]
    for lines,expected in cases:
        t=time.perf_counter()
        lines,groups=group_rows(lines)
        v2=enriched(lines);graph=graph_observations(lines)
        if [(c.amount,c.line,c.score) for c in v2]!=[(c.amount,c.line,c.score) for c in graph]:
            raise RuntimeError('graph provenance differs from v2')
        diag=diagnose(lines,graph,expected) if expected is not None else {}
        fuzzy=near_miss_labels(lines)
        for name,model in models.items():
            obs=graph if name.startswith('graph_') else v2
            hasher=hashers['graph' if name.startswith('graph_') else 'v2']
            scores=model.predict_proba(hasher.transform([c.features for c in obs]))[:,list(model.classes_).index(1)] if obs else []
            result=triage(lines,obs,scores)
            direct,reason,_=select(lines,groups,obs,scores)
            if (result.state=='supported_candidate')!=(direct is not None):
                raise RuntimeError('evidence triage changed strict gate decision')
            if direct is not None and direct!=result.candidate.value:
                raise RuntimeError('evidence triage changed strict value')
            row=out['methods'].setdefault(name,blank())
            row['n']+=1
            row['state'][result.state]=row['state'].get(result.state,0)+1
            row['strict_reason'][reason]=row['strict_reason'].get(reason,0)+1
            row['reference_observed']+=diag.get('reference_observed',0)
            row['reference_high_ocr']+=diag.get('reference_high_ocr',0)
            row['reference_explicit_link']+=diag.get('reference_explicit_link',0)
            row['near_miss_labels']+=int(fuzzy>0)
            if result.state=='supported_candidate':
                row['supported_correct']+=int(expected is not None and result.candidate.value==expected)
                row['supported_wrong']+=int(expected is not None and result.candidate.value!=expected)
                row['supported_negative']+=int(expected is None)
            else:
                row['negative_rejected']+=int(expected is None)
                row['review_without_auto']+=int(expected is not None)
                row['user_review_options_contains_reference']+=int(
                    expected is not None and any(x.value==expected for x in result.alternatives))
                if result.state=='review_suggestion':
                    row['suggested_total']+=1
                    row['suggestion_correct']+=int(expected is not None and result.candidate.value==expected)
                    row['suggestion_wrong']+=int(expected is not None and result.candidate.value!=expected)
                    row['suggestion_negative']+=int(expected is None)
                elif result.state=='ambiguous_review':
                    row['ambiguous']+=1
                else:
                    row['needs_recapture']+=1
        out['n']+=1
        out['positive']+=int(expected is not None)
        out['negative']+=int(expected is None)
        lat.append((time.perf_counter()-t)*1000)
    out['median_rank_ms']=round(float(np.median(lat)),3) if lat else None
    return out


def save(result,name):
    Path(name).write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result,indent=2,sort_keys=True))


def main():
    self_test()
    samples,meta=prior.sample(prior.preflight(HfApi()))
    report={'sampling':meta,'dataset_revision':prior.DATA_REV,'models':{},'training':{},'evaluations':{},'synthetic':{}}
    save(report,'triage_preflight_results.json')
    dp,dm=fetch(DET,prior.DET_REV);rp,rm=fetch(REC,REC_REV)
    report['models']={DET:dm,REC:rm}
    det=TextDetection(model_name=DET,model_dir=str(dp),device='cpu',enable_mkldnn=False,cpu_threads=2)
    rec=TextRecognition(model_name=REC,model_dir=str(rp),device='cpu',enable_mkldnn=False,cpu_threads=2)
    hashers={'v2':FeatureHasher(n_features=1024,input_type='dict',alternate_sign=False),
             'graph':FeatureHasher(n_features=2048,input_type='dict',alternate_sign=False)}
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp)
        def ocr(im):return prepare(im,det,rec,folder)[1]
        def load(rows):
            for _,data,expected in rows:
                with Image.open(io.BytesIO(data)) as im:
                    yield ocr(im.convert('RGB')),expected
        train=list(load(samples['train']))
        training=list(synthetic_docs(183,240))
        models,report['training']['v2']=fit_v2(train,training,hashers['v2'])
        graph_models,report['training']['graph']=fit_graph(train,training,hashers['graph'])
        models.update(graph_models)
        del train
        save(report,'triage_training_results.json')
        # Real test values only evaluate existing OCR fields; never fit models.
        for name,selected in [('reused_val',samples['val'][:40]),('last_val',samples['val'][120:]),('test',samples['test'])]:
            report['evaluations'][name]=evaluate(load(selected),models,hashers)
            save(report,'triage_'+name+'_results.json')
        for kind in ('split','combined','tilt','blur','duplicate','missing'):
            report['synthetic'][kind]=evaluate(((ocr(im),e) for im,e in (fixture(i,kind) for i in range(4))),models,hashers)
        for kind in ('split','combined','duplicate','missing'):
            report['synthetic']['perspective_'+kind]=evaluate(((ocr(im),e) for im,e in (distorted(kind,12,q) for q in QUADS)),models,hashers)
        report['synthetic']['structured_new']=evaluate(synthetic_docs(917,120),models,hashers)
    save(report,'triage_final_results.json')
    if sum(v['n'] for v in report['evaluations'].values())!=89:
        raise RuntimeError('Unexpected real-document sample count')
if __name__=='__main__':main()
