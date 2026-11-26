"""Paired raw/rectified geometry research; OCR crops and recognized text identical.
All previously evaluated datasets remain diagnostic; the final val slice is new.
No image, text, annotation, per-document output or trained weights is exported.
"""
import io
import json
import math
import tempfile
import time
from collections import Counter
from pathlib import Path
from PIL import Image
import numpy as np
from huggingface_hub import HfApi
from paddleocr import TextDetection,TextRecognition
from sklearn.feature_extraction import FeatureHasher
import semantic_ranker_run as prior
from semantic_ranker_v2_run import fit_v2
from semantic_ranker_v2 import enriched,protected,synthetic_docs,evidence
from semantic_ranker import choose
from receipt_structure import fetch,warp,DET,REC,REC_REV,fixture
from total_candidate import Line
from ocr_preprocess import trim
from document_geometry import estimate,correct,self_test

# Same deterministic ordering, reserve val/test before train.
prior.LIMITS={'test':32,'val':120,'train':160}
N_FEATURES=1024

def process_polygons(im,detector,recognizer,folder):
    image=np.asarray(im.convert('RGB')).copy()
    # Paths avoid ambiguity of RGB/BGR input conventions.
    path=folder/'document.png';Image.fromarray(image).save(path)
    detected=list(detector.predict(input=str(path),batch_size=1))
    if len(detected)!=1:raise RuntimeError('Unexpected detection batch')
    data=detected[0].json['res']
    polygons=data['dt_polys']
    crops=[];boxes=[];polys=[]
    for poly in polygons:
        crop=warp(image,poly)
        if crop is None:continue
        p=np.asarray(poly,dtype=float)
        x,y=p.min(axis=0);X,Y=p.max(axis=0)
        if X<=x or Y<=y:continue
        cropped=trim(Image.fromarray(crop))
        file=folder/f'line-{len(crops)}.png'
        cropped.convert('RGB').save(file)
        crops.append(str(file));boxes.append((float(x),float(y),float(X),float(Y)))
        polys.append(tuple(tuple(float(v) for v in q) for q in p))
    if not crops:return [],[]
    result=list(recognizer.predict(input=crops,batch_size=8))
    if len(result)!=len(crops):raise RuntimeError('Recognition count differs from detection')
    by_path={str(Path(r.json['res']['input_path']).resolve()):r.json['res'] for r in result}
    lines=[]
    for file,box in zip(crops,boxes):
        entry=by_path[str(Path(file).resolve())]
        lines.append(Line(str(entry['rec_text']),float(entry['rec_score']),box))
    for path in crops:Path(path).unlink()
    return lines,polys

def prepare(im,det,rec,folder):
    raw,poly=process_polygons(im,det,rec,folder)
    axis=estimate(poly)
    corrected=correct(raw,poly,axis)
    return raw,poly,axis,corrected

def predict(lines,model,hasher):
    obs=enriched(lines)
    if not obs:return None,None
    scores=model.predict_proba(hasher.transform([c.features for c in obs]))[:,list(model.classes_).index(1)]
    return choose(obs,scores,threshold=0,margin=1e-9,require_ocr=False),protected(lines,obs,scores)

def stable(raw,poly,axis,value):
    """Verify the same observed linked total under small angle perturbations.
    Does not change OCR/model thresholds or supply an amount.
    """
    if value is None:return None
    if not axis.reliable:return value # separately measured fallback, not a geometry pass
    delta=max(.5,min(1.5,axis.spread+.5))
    for offset in (-delta,delta):
        _,labels,links,unresolved=evidence(correct(raw,poly,axis,offset))
        if not labels or unresolved or {a for a,i in links.values()}!={value}:return None
    return value

def evaluate(cases,models,hasher,det,rec,folder):
    out={'n':0,'positive_docs':0,'negative_docs':0,'axis':Counter(),'methods':{},'elapsed_ms':[]}
    for im,expected in cases:
        start=time.perf_counter()
        raw,poly,axis,rect=prepare(im,det,rec,folder)
        out['n']+=1
        out['positive_docs']+=int(expected is not None)
        out['negative_docs']+=int(expected is None)
        out['axis']['reliable' if axis.reliable else 'fallback']+=1
        if axis.reliable and abs(axis.angle)>=2:out['axis']['abs_angle_ge_2']+=1
        values={}
        for name,model in models['raw'].items():
            top,protected_value=predict(raw,model,hasher)
            values['raw_'+name+'_top1']=top
            values['raw_'+name+'_protected']=protected_value
            top,pv=predict(rect,model,hasher)
            values['rect_same_model_'+name+'_top1']=top
            values['rect_same_model_'+name+'_protected']=pv
        for name,model in models['rect'].items():
            top,pv=predict(rect,model,hasher)
            values['rect_refit_'+name+'_top1']=top
            values['rect_refit_'+name+'_protected']=pv
            values['rect_refit_'+name+'_stable']=stable(raw,poly,axis,pv)
        for name,value in values.items():
            row=out['methods'].setdefault(name,dict(n=0,accepted=0,correct=0,wrong=0,negative_rejected=0,negative_accepted=0,positive_rejected=0))
            row['n']+=1;row['accepted']+=int(value is not None)
            row['correct']+=int(value is not None and value==expected)
            row['wrong']+=int(value is not None and value!=expected)
            row['negative_rejected']+=int(expected is None and value is None)
            row['negative_accepted']+=int(expected is None and value is not None)
            row['positive_rejected']+=int(expected is not None and value is None)
        out['elapsed_ms'].append((time.perf_counter()-start)*1000)
    out['median_ms']=round(float(np.median(out.pop('elapsed_ms'))),2) if out['n'] else None
    return out

def save(result,name):
    Path(name).write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result,indent=2,sort_keys=True))

def main():
    self_test()
    api=HfApi();samples,meta=prior.sample(prior.preflight(api))
    result={'dataset_revision':prior.DATA_REV,'sampling':meta,'training':{},'evaluations':{},'synthetic':{},'models':{}}
    save(result,'geometry_preflight_results.json')
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
        raw_train=[];rect_train=[];axis_counts=Counter()
        for im,expected in load(samples['train']):
            raw,poly,axis,rect=prepare(im,det,rec,folder)
            raw_train.append((raw,expected));rect_train.append((rect,expected))
            axis_counts['reliable' if axis.reliable else 'fallback']+=1
        syn=list(synthetic_docs(183,240))
        models={}
        for name,train in [('raw',raw_train),('rect',rect_train)]:
            models[name],result['training'][name]=fit_v2(train,syn,hasher)
        result['training']['axis']=axis_counts
        del raw_train,rect_train,syn
        save(result,'geometry_training_results.json')
        # First verify the previous failure and stronger signed inclinations.
        for kind in ('split','combined','tilt','blur','duplicate','missing'):
            result['synthetic'][kind]=evaluate((fixture(i,kind) for i in range(4)),models,hasher,det,rec,folder)
        for angle in (-12,-8,-4,4,8,12):
            def rotated():
                for kind in ('split','duplicate','missing'):
                    for i in range(2):
                        im,expected=fixture(i+10,kind)
                        yield im.rotate(angle,expand=True,fillcolor='white'),expected
            result['synthetic']['angle_'+str(angle)]=evaluate(rotated(),models,hasher,det,rec,folder)
        save(result,'geometry_synthetic_results.json')
        for name,selected in [('prior_val',samples['val'][:40]),('previous_new_val',samples['val'][40:80]),('fresh_val',samples['val'][80:]),('test',samples['test'])]:
            result['evaluations'][name]=evaluate(load(selected),models,hasher,det,rec,folder)
            save(result,'geometry_'+name+'_results.json')
    save(result,'geometry_final_results.json')
if __name__=='__main__':main()
