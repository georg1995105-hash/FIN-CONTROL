"""Paired total-row research, no raw receipt data or per-document output."""
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
from semantic_ranker_v2 import enriched,protected,synthetic_docs
from semantic_ranker import choose
from geometry_research_run import process_polygons
from document_geometry import estimate,correct
from perspective_geometry import detect
from perspective_research_run import corrected_lines,distorted,QUADS
from receipt_structure import fetch,DET,REC,REC_REV,fixture
from reread_run import tess_read,batch_read
from total_row_evidence import group_rows,select,candidates_for_reread,self_test

# Imports above may mutate prior.LIMITS; restore frozen selection.
prior.LIMITS={'test':32,'val':137,'train':160}
N_FEATURES=1024

def prepare(im,det,rec,folder):
    raw,polys=process_polygons(im,det,rec,folder)
    axis=estimate(polys)
    rect=correct(raw,polys,axis)
    page=detect(np.asarray(im.convert('RGB')),polys)
    if page.matrix is not None:
        return rect,corrected_lines(raw,polys,page.matrix),page.matrix
    t=math.radians(axis.angle if axis.reliable else 0.)
    c=math.cos(t);s=math.sin(t)
    return rect,rect,np.array([[c,s,0],[-s,c,0],[0,0,1]],dtype=float)

def crop_row(im,groups,k,matrix):
    row=groups[k];x,y,X,Y=row.box;h=Y-y
    if h<3:return None
    # Extend to document text width to recover undetected label glyphs.
    lo=min(r.box[0] for r in groups);hi=max(r.box[2] for r in groups)
    left=min(lo,x)-.15*h;right=max(hi,X)+.15*h
    top=y-.12*h;bottom=Y+.12*h
    # Reject overlapping neighboring rows, rather than read mixed evidence.
    for j,r in enumerate(groups):
        if j==k:continue
        a,b,A,B=r.box
        if min(bottom,B)-max(top,b)>.1*min(h,B-b):return None
    width=max(1,round(right-left));height=max(1,round(bottom-top))
    if width>8000 or height>1000 or width/height>60:return None
    src=np.array([[[left,top],[right,top],[right,bottom],[left,bottom]]],np.float64)
    try:src=cv2.perspectiveTransform(src,np.linalg.inv(matrix))[0].astype(np.float32)
    except (np.linalg.LinAlgError,cv2.error):return None
    if not np.isfinite(src).all():return None
    dest=np.array([[0,0],[width-1,0],[width-1,height-1],[0,height-1]],np.float32)
    patch=cv2.warpPerspective(np.asarray(im.convert('RGB')),cv2.getPerspectiveTransform(src,dest),(width,height),borderValue=(255,255,255))
    image=Image.fromarray(patch).convert('L')
    if image.height<64:
        image=image.resize((max(1,round(image.width*64/image.height)),64),Image.Resampling.LANCZOS)
    return ImageOps.expand(ImageOps.autocontrast(image),border=4,fill=255).convert('RGB')

def reread_rows(im,groups,indices,matrix,rec,folder):
    paths=[];used=[]
    for k in indices:
        img=crop_row(im,groups,k,matrix)
        if img is None:continue
        path=folder/f'row-reread-{k}.png';img.save(path)
        paths.append(path);used.append(k)
    read=batch_read(rec,paths)
    result={k:(p,tess_read(path)) for k,p,path in zip(used,read,paths)}
    for path in paths:path.unlink()
    return result

def tally(row,value,expected):
    row['n']+=1
    row['correct']+=int(value is not None and value==expected)
    row['wrong']+=int(value is not None and value!=expected)
    row['refused']+=int(value is None and expected is not None)
    row['negative_rejected']+=int(value is None and expected is None)

def evaluate(cases,models,hasher,det,rec,folder):
    out={'n':0,'positive':0,'negative':0,'methods':{},'blockers':{},'evidence':{},'reread_rows':0,'median_ms':None}
    lat=[]
    for im,expected in cases:
        t=time.perf_counter()
        _,projected,matrix=prepare(im,det,rec,folder)
        lines,groups=group_rows(projected)
        obs=enriched(lines)
        scores={name:m.predict_proba(hasher.transform([c.features for c in obs]))[:,list(m.classes_).index(1)] if obs else [] for name,m in models.items()}
        prior_values={name:protected(lines,obs,sc) for name,sc in scores.items()}
        initial={name:select(lines,groups,obs,sc) for name,sc in scores.items()}
        # One bounded re-read set shared by both models. No known answer.
        todo=set()
        for name,sc in scores.items():
            if prior_values[name] is None and initial[name][0] is None:
                todo.update(candidates_for_reread(lines,groups,obs,sc))
        reads=reread_rows(im,groups,sorted(todo)[:12],matrix,rec,folder) if todo else {}
        out['reread_rows']+=len(reads)
        for name,sc in scores.items():
            original=prior_values[name]
            direct,_,_=initial[name]
            recovered,cause,reasons=select(lines,groups,obs,sc,reads)
            # Separate strict replacement from a union with prior candidates.
            # Union never overwrites an accepted prior result; disagreement rejects.
            union=original if recovered is None else recovered if original in (None,recovered) else None
            if original is not None and recovered is not None and original!=recovered:union=None
            for tag,value in [('prior',original),('row_only',direct),('row_reread',recovered),('union_diagnostic',union)]:
                tally(out['methods'].setdefault(name+'_'+tag,dict(n=0,correct=0,wrong=0,refused=0,negative_rejected=0)),value,expected)
            out['blockers'].setdefault(name,Counter())[cause]+=1
            out['evidence'].setdefault(name,Counter()).update(reasons)
        out['n']+=1;out['positive']+=int(expected is not None);out['negative']+=int(expected is None)
        lat.append((time.perf_counter()-t)*1000)
    out['median_ms']=round(float(np.median(lat)),2) if lat else None
    return out

def save(result,name):
    Path(name).write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result,indent=2,sort_keys=True))

def main():
    self_test()
    samples,meta=prior.sample(prior.preflight(HfApi()))
    result={'dataset_revision':prior.DATA_REV,'sampling':meta,'training':{},'evaluations':{},'synthetic':{},'models':{}}
    save(result,'row_evidence_preflight_results.json')
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
        save(result,'row_evidence_training_results.json')
        for kind in ('split','combined','tilt','blur','duplicate','missing'):
            result['synthetic'][kind]=evaluate((fixture(i,kind) for i in range(4)),models,hasher,det,rec,folder)
        for kind in ('split','combined','duplicate','missing'):
            result['synthetic']['perspective_'+kind]=evaluate((distorted(kind,12,q) for q in QUADS),models,hasher,det,rec,folder)
        save(result,'row_evidence_synthetic_results.json')
        for name,selected in [('reused_val',samples['val'][:40]),('last_val',samples['val'][120:]),('test',samples['test'])]:
            result['evaluations'][name]=evaluate(load(selected),models,hasher,det,rec,folder)
            save(result,'row_evidence_'+name+'_results.json')
    save(result,'row_evidence_final_results.json')
if __name__=='__main__':main()
