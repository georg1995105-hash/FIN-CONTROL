"""Paired OCR geometry benchmark. Only aggregate outputs; no document text,
images, predictions, source IDs, per-document coordinates or weights exported.
"""
import io
import json
import math
import tempfile
import time
from pathlib import Path
from collections import Counter
import cv2
import numpy as np
from PIL import Image,ImageOps
from huggingface_hub import HfApi
from paddleocr import TextDetection,TextRecognition
from sklearn.feature_extraction import FeatureHasher
import semantic_ranker_run as prior
from semantic_ranker_v2_run import fit_v2
from semantic_ranker_v2 import enriched,protected,evidence,synthetic_docs
from semantic_ranker import choose
from geometry_research_run import process_polygons
from document_geometry import estimate,correct
from receipt_structure import fetch,DET,REC,REC_REV,fixture
from total_candidate import Line
from perspective_geometry import detect,transform,self_test

# geometry_research_run sets prior.LIMITS at import; override afterwards.
# Use all 137 eligible val records, only the last 17 are previously untouched.
prior.LIMITS={'test':32,'val':137,'train':160}
N_FEATURES=1024

def corrected_lines(raw,polys,matrix):
    result=[]
    for line,poly in zip(raw,polys):
        p=transform(poly,matrix)
        x,y=p.min(axis=0);X,Y=p.max(axis=0)
        if X<=x or Y<=y:raise ValueError('degenerate corrected line')
        result.append(Line(line.text,line.score,(float(x),float(y),float(X),float(Y))))
    return result

def prepare(im,det,rec,folder):
    raw,polys=process_polygons(im,det,rec,folder)
    axis=estimate(polys)
    rect=correct(raw,polys,axis)
    page=detect(np.asarray(im.convert('RGB')),polys)
    projected=corrected_lines(raw,polys,page.matrix) if page.matrix is not None else rect
    return rect,projected,page.reason

def diagnose(lines,obs,scores):
    """Exclusive first blocker in protected inference, plus evidence flags.
    A low-confidence label is not a verified transcription.
    """
    _,labels,links,unresolved=evidence(lines)
    flags=[]
    if not labels:flags.append('no_explicit_label')
    if unresolved:flags.append('unresolved_label')
    values={v for v,_ in links.values()}
    if len(values)>1:flags.append('conflicting_total_values')
    if len(values)==1:flags.append('one_linked_value')
    if labels and any(not math.isfinite(l.score) or l.score<.85 for _,l in labels):
        flags.append('label_low_ocr_confidence')
    if not obs:return 'no_money_spans',flags
    if not labels:return 'no_explicit_label',flags
    if unresolved:return 'unresolved_label',flags
    if len(values)!=1:return 'missing_or_conflicting_link',flags
    top=choose(obs,scores,threshold=0,margin=1e-9,require_ocr=False)
    score_gate=choose(obs,scores,threshold=.85,margin=.15,require_ocr=False)
    if score_gate is None:return 'rank_threshold_or_margin',flags
    value=choose(obs,scores,threshold=.85,margin=.15,require_ocr=True)
    if value is None:return 'amount_ocr_confidence',flags
    if top not in values:return 'rank_disagrees_with_link',flags
    if protected(lines,obs,scores) is None:return 'linked_candidate_not_supported',flags
    return 'accepted',flags

def evaluate(cases,models,hasher,det,rec,folder):
    out={'n':0,'positive':0,'negative':0,'outline_reasons':Counter(),'methods':{},'first_blocker':{},'evidence_flags':{},'elapsed_ms':[]}
    for im,expected in cases:
        t=time.perf_counter()
        rect,proj,reason=prepare(im,det,rec,folder)
        out['n']+=1;out['positive']+=int(expected is not None);out['negative']+=int(expected is None)
        out['outline_reasons'][reason]+=1
        for geo,lines in [('rotation',rect),('perspective',proj)]:
            obs=enriched(lines)
            for name,model in models.items():
                tag=geo+'_'+name
                scores=model.predict_proba(hasher.transform([c.features for c in obs]))[:,list(model.classes_).index(1)] if obs else []
                top=choose(obs,scores,threshold=0,margin=1e-9,require_ocr=False)
                value=protected(lines,obs,scores)
                cause,flags=diagnose(lines,obs,scores)
                out['first_blocker'].setdefault(tag,Counter())[cause]+=1
                out['evidence_flags'].setdefault(tag,Counter()).update(flags)
                for kind,v in [('top1',top),('protected',value)]:
                    row=out['methods'].setdefault(tag+'_'+kind,dict(correct=0,wrong=0,accepted=0,positive_rejected=0,negative_rejected=0))
                    row['correct']+=int(v is not None and v==expected)
                    row['wrong']+=int(v is not None and v!=expected)
                    row['accepted']+=int(v is not None)
                    row['positive_rejected']+=int(v is None and expected is not None)
                    row['negative_rejected']+=int(v is None and expected is None)
        out['elapsed_ms'].append((time.perf_counter()-t)*1000)
    out['median_ms']=round(float(np.median(out.pop('elapsed_ms'))),2)
    return out

# Known synthetic transformations, applied to document pixels before OCR.
# True outlines are not provided to the detector.
QUADS=[
    [[70,60],[820,105],[920,690],[40,650]],
    [[140,100],[900,45],[840,660],[35,720]],
    [[70,70],[910,130],[825,690],[150,610]],
    [[110,40],[880,95],[940,685],[55,720]],
]
def distorted(kind,index,quad):
    im,expected=fixture(index,kind)
    # Blank margin keeps text inside the complete page.
    im=ImageOps.expand(im,border=28,fill='white')
    arr=np.asarray(im.convert('RGB'))
    h,w=arr.shape[:2]
    src=np.array([[0,0],[w-1,0],[w-1,h-1],[0,h-1]],np.float32)
    M=cv2.getPerspectiveTransform(src,np.asarray(quad,np.float32))
    warped=cv2.warpPerspective(arr,M,(1000,790),borderValue=(40,40,40))
    return Image.fromarray(warped),expected

def save(result,name):
    Path(name).write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result,indent=2,sort_keys=True))

def main():
    self_test()
    api=HfApi();samples,meta=prior.sample(prior.preflight(api))
    result={'dataset_revision':prior.DATA_REV,'sampling':meta,'training':{},'evaluations':{},'synthetic':{},'models':{}}
    save(result,'perspective_preflight_results.json')
    dp,dm=fetch(DET,prior.DET_REV);rp,rm=fetch(REC,REC_REV)
    result['models']={DET:dm,REC:rm}
    det=TextDetection(model_name=DET,model_dir=str(dp),device='cpu',enable_mkldnn=False,cpu_threads=2)
    rec=TextRecognition(model_name=REC,model_dir=str(rp),device='cpu',enable_mkldnn=False,cpu_threads=2)
    hasher=FeatureHasher(n_features=N_FEATURES,input_type='dict',alternate_sign=False)
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp)
        def load(rows):
            for _,data,expected in rows:
                with Image.open(io.BytesIO(data)) as im:
                    yield im.convert('RGB'),expected
        train=[]
        for im,expected in load(samples['train']):
            rect,_,_=prepare(im,det,rec,folder)
            train.append((rect,expected))
        models,result['training']=fit_v2(train,list(synthetic_docs(183,240)),hasher)
        del train
        save(result,'perspective_training_results.json')
        # 40 previously unused perspective images; 16 negative cases.
        for kind in ('split','combined','blur','duplicate','missing'):
            result['synthetic'][kind]=evaluate((distorted(kind,12+i,q) for i in range(2) for q in QUADS),models,hasher,det,rec,folder)
        # Regression on the previous 24 images, including rotation-only cases.
        for kind in ('split','combined','tilt','blur','duplicate','missing'):
            result['synthetic']['regression_'+kind]=evaluate((fixture(i,kind) for i in range(4)),models,hasher,det,rec,folder)
        save(result,'perspective_synthetic_results.json')
        for name,selected in [('reused_val',samples['val'][:40]),('fresh_val',samples['val'][120:]),('test',samples['test'])]:
            result['evaluations'][name]=evaluate(load(selected),models,hasher,det,rec,folder)
            save(result,'perspective_'+name+'_results.json')
    save(result,'perspective_final_results.json')
if __name__=='__main__':main()
