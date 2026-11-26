"""Paired whole-page OCR experiment; no raw document data exported."""
import csv
import io
import json
import math
import os
import subprocess
import tempfile
import time
from pathlib import Path
from collections import Counter
import cv2
import numpy as np
from PIL import Image
from huggingface_hub import HfApi
from paddleocr import TextDetection,TextRecognition
from sklearn.feature_extraction import FeatureHasher
import semantic_ranker_run as prior
from semantic_ranker_v2_run import fit_v2
from semantic_ranker_v2 import enriched,protected,synthetic_docs
from total_row_evidence import group_rows,select
from total_candidate import Line
from row_ink_run import prepare,tally
from perspective_research_run import distorted,QUADS
from receipt_structure import fetch,DET,REC,REC_REV,fixture
from page_layout_evidence import page_totals,corroborate,cross_validate,self_test

prior.LIMITS={'test':32,'val':137,'train':160}

def page_image(im,matrix,lines):
    w,h=im.size
    points=np.array([[[0.,0.],[w,0.],[w,h],[0.,h]]],np.float64)
    q=cv2.perspectiveTransform(points,matrix)[0]
    if not np.isfinite(q).all():return None,None
    lo=q.min(axis=0);hi=q.max(axis=0);wh=hi-lo
    if min(wh)<3 or max(wh)>20000:return None,None
    heights=[l.box[3]-l.box[1] for l in lines if l.box[3]>l.box[1]]
    median=float(np.median(heights)) if heights else 20.
    scale=min(2.,max(1.,32/max(median,1.)),4000/max(wh),math.sqrt(8e6/(wh[0]*wh[1])))
    outw,outh=(np.ceil(wh*scale).astype(int)+24)
    if min(outw,outh)<40:return None,None
    mapping=np.array([[scale,0.,12-scale*lo[0]],[0.,scale,12-scale*lo[1]],[0.,0.,1.]])
    page=cv2.warpPerspective(np.asarray(im.convert('L')),mapping@matrix,(int(outw),int(outh)),borderValue=255)
    return Image.fromarray(page),mapping

def words_from_tsv(tsv,mapping):
    scale=mapping[0,0];dx=mapping[0,2];dy=mapping[1,2]
    result=[]
    for row in csv.DictReader(io.StringIO(tsv),delimiter='\t'):
        if row.get('level')!='5' or not (row.get('text') or '').strip():continue
        try:
            x,y,w,h=(float(row[k]) for k in ('left','top','width','height'))
            score=float(row['conf'])/100
        except (ValueError,TypeError,KeyError):continue
        if w<=0 or h<=0 or not math.isfinite(score):continue
        result.append(Line(row['text'],score,((x-dx)/scale,(y-dy)/scale,(x+w-dx)/scale,(y+h-dy)/scale)))
    return result

def read_page(path,mapping,mode):
    try:
        proc=subprocess.run(['tesseract',str(path),'stdout','-l','rus','--oem','1','--psm',str(mode),'tsv'],
                            capture_output=True,text=True,timeout=35,env=dict(os.environ,OMP_THREAD_LIMIT='1'))
    except subprocess.TimeoutExpired:return [],'timeout'
    if proc.returncode!=0:return [],'engine_error'
    words=words_from_tsv(proc.stdout,mapping)
    return words,'read' if words else 'empty'

def evaluate(cases,models,hasher,det,rec,folder):
    out={'n':0,'positive':0,'negative':0,'methods':{},'page_stats':Counter(),'gates':{},'elapsed_ms':[]}
    for im,expected in cases:
        start=time.perf_counter()
        _,projected,matrix,_=prepare(im,det,rec,folder)
        lines,groups=group_rows(projected)
        obs=enriched(lines)
        page,mapping=page_image(im,matrix,lines)
        totals={}
        for mode in (4,6):
            if page is None:
                totals[mode]=[];out['page_stats']['invalid_canvas']+=1;continue
            path=folder/'whole-page.png';page.save(path)
            words,status=read_page(path,mapping,mode)
            out['page_stats'][f'psm{mode}_{status}']+=1
            out['page_stats'][f'psm{mode}_words']+=len(words)
            totals[mode],reason,stats=page_totals(words)
            out['page_stats'][f'psm{mode}_{reason}']+=1
            for key,v in stats.items():out['page_stats'][f'psm{mode}_{key}']+=v
            path.unlink()
        joined=corroborate(totals[4],totals[6])
        out['page_stats']['both_modes_spatial_agreement']+=int(bool(joined))
        for name,m in models.items():
            scores=m.predict_proba(hasher.transform([c.features for c in obs]))[:,list(m.classes_).index(1)] if obs else []
            old=protected(lines,obs,scores)
            strict,_,_=select(lines,groups,obs,scores)
            values={'prior':old,'row_only':strict}
            for tag,ts in [('psm4',totals[4]),('psm6',totals[6]),('both',joined)]:
                candidate,reason=cross_validate(lines,obs,scores,ts)
                values[tag+'_cross']=candidate
                out['gates'].setdefault(name+'_'+tag,Counter())[reason]+=1
                # A separate exploratory combined result. Never overwrite
                # a disagreement; no deployment choice made by this run.
                values[tag+'_combined_diagnostic']=strict if candidate is None else candidate if strict in (None,candidate) else None
            for tag,value in values.items():
                tally(out['methods'].setdefault(name+'_'+tag,dict(n=0,correct=0,wrong=0,refused=0,negative_rejected=0)),value,expected)
        out['n']+=1;out['positive']+=int(expected is not None);out['negative']+=int(expected is None)
        out['elapsed_ms'].append((time.perf_counter()-start)*1000)
    out['median_ms']=round(float(np.median(out.pop('elapsed_ms'))),2)
    return out

def save(result,name):
    Path(name).write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result,indent=2,sort_keys=True))

def main():
    self_test()
    # TSV coordinates must map back to the exact original rectified frame.
    t='level\tleft\ttop\twidth\theight\tconf\ttext\n5\t22\t42\t60\t20\t97.0\t123,45\n'
    words=words_from_tsv(t,np.array([[2.,0.,2.],[0.,2.,2.],[0.,0.,1.]]))
    assert len(words)==1 and words[0].box==(10.,20.,40.,30.)
    samples,meta=prior.sample(prior.preflight(HfApi()))
    result={'dataset_revision':prior.DATA_REV,'sampling':meta,'training':{},'evaluations':{},'synthetic':{},'models':{}}
    save(result,'page_layout_preflight_results.json')
    dp,dm=fetch(DET,prior.DET_REV);rp,rm=fetch(REC,REC_REV)
    result['models']={DET:dm,REC:rm}
    det=TextDetection(model_name=DET,model_dir=str(dp),device='cpu',enable_mkldnn=False,cpu_threads=2)
    rec=TextRecognition(model_name=REC,model_dir=str(rp),device='cpu',enable_mkldnn=False,cpu_threads=2)
    hasher=FeatureHasher(n_features=1024,input_type='dict',alternate_sign=False)
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp)
        def load(rows):
            for _,data,expected in rows:
                with Image.open(io.BytesIO(data)) as im:
                    yield im.convert('RGB'),expected
        train=[]
        for im,expected in load(samples['train']):
            rect,_,_,_=prepare(im,det,rec,folder)
            train.append((rect,expected))
        models,result['training']=fit_v2(train,list(synthetic_docs(183,240)),hasher)
        del train
        save(result,'page_layout_training_results.json')
        for kind in ('split','combined','tilt','blur','duplicate','missing'):
            result['synthetic'][kind]=evaluate((fixture(i,kind) for i in range(4)),models,hasher,det,rec,folder)
        for kind in ('split','combined','duplicate','missing'):
            result['synthetic']['perspective_'+kind]=evaluate((distorted(kind,12,q) for q in QUADS),models,hasher,det,rec,folder)
        save(result,'page_layout_synthetic_results.json')
        for name,selected in [('reused_val',samples['val'][:40]),('last_val',samples['val'][120:]),('test',samples['test'])]:
            result['evaluations'][name]=evaluate(load(selected),models,hasher,det,rec,folder)
            save(result,'page_layout_'+name+'_results.json')
    save(result,'page_layout_final_results.json')
    if not all(sum(x['page_stats'].get(f'psm{mode}_read',0) for x in result['evaluations'].values())>0 for mode in (4,6)):
        raise RuntimeError('Whole-page OCR mode never executed successfully on real images')
if __name__=='__main__':main()
