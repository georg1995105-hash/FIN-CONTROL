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
from total_row_evidence import group_rows,select,self_test as evidence_self_test,parse,reread
from row_reread_scheduler import plan,make_crop,self_test
from row_ink_segmentation import rectify_crop,self_test as ink_self_test
from document_structure import valid_box

# Imports above may mutate prior.LIMITS; restore frozen selection.
prior.LIMITS={'test':32,'val':137,'train':160}
N_FEATURES=1024

def prepare(im,det,rec,folder):
    raw,polys=process_polygons(im,det,rec,folder)
    axis=estimate(polys)
    rect=correct(raw,polys,axis)
    page=detect(np.asarray(im.convert('RGB')),polys)
    if page.matrix is not None:
        return rect,corrected_lines(raw,polys,page.matrix),page.matrix,polys
    t=math.radians(axis.angle if axis.reliable else 0.)
    c=math.cos(t);s=math.sin(t)
    return rect,rect,np.array([[c,s,0],[-s,c,0],[0,0,1]],dtype=float),polys

def reread_rows(im,lines,groups,indices,matrix,rec,folder,polygons=None):
    paths=[];used=[];stats=Counter();ink_used=set()
    for k in indices:
        img,reason=make_crop(im,lines,groups,k,matrix)
        stats['crop_'+reason]+=1
        if img is None and reason=='neighbor_intersects_target' and polygons is not None:
            stats['ink_attempts']+=1
            img,ink_reason=rectify_crop(im,lines,groups,k,matrix,polygons)
            stats['ink_'+ink_reason]+=1
            if img is not None:ink_used.add(k)
        if img is None:continue
        path=folder/f'row-reread-{k}.png';img.save(path)
        paths.append(path);used.append(k)
    read=batch_read(rec,paths)
    stats['paddle_calls']=len(read)
    result={k:(p,tess_read(path)) for k,p,path in zip(used,read,paths)}
    stats['tesseract_calls']=len(result)
    stats['consensus_rows']=sum(reread(lines,groups[k],*pair) is not None for k,pair in result.items())
    stats['ink_calls']=len(ink_used)
    stats['ink_consensus']=sum(k in ink_used and reread(lines,groups[k],*pair) is not None for k,pair in result.items())
    stats['both_nonempty']=sum(bool(p[0].strip()) and bool(q[0].strip()) for p,q in result.values())
    for path in paths:path.unlink()
    return result,stats

def activation_probe(rec,folder):
    """Fault-injected first OCR observation on rendered image, actual second
    OCR engines. Verifies invocation, not natural first-pass failure rate."""
    from PIL import ImageDraw,ImageFont
    from total_candidate import Line
    im=Image.new('RGB',(800,240),'white')
    d=ImageDraw.Draw(im);f=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',40)
    d.text((25,75),'ИТОГО',font=f,fill='black')
    d.text((380,75),'123,45',font=f,fill='black')
    a=d.textbbox((25,75),'ИТОГО',font=f)
    b=d.textbbox((380,75),'123,45',font=f)
    lines,groups=group_rows([Line('ИТОГ0',.6,a),Line('123,45',.98,b)])
    obs=enriched(lines)
    indices,schedule=plan(lines,groups,obs,[.1]*len(obs))
    reads,stats=reread_rows(im,lines,groups,indices,np.eye(3),rec,folder)
    if not indices or stats['paddle_calls']<1 or stats['tesseract_calls']<1 or not reads:
        raise RuntimeError('Activation probe failed to invoke both real OCR engines')
    print('PASS: real Paddle and Tesseract invoked on fault-injected row image')
    return {'schedule':dict(schedule),'reads':dict(stats),'fault_injected':True,
            'known_amount_recovered':any((reread(lines,groups[k],*pair) or (None,None))[0]=='123,45' for k,pair in reads.items())}


def tally(row,value,expected):
    row['n']+=1
    row['correct']+=int(value is not None and value==expected)
    row['wrong']+=int(value is not None and value!=expected)
    row['refused']+=int(value is None and expected is not None)
    row['negative_rejected']+=int(value is None and expected is None)

def evaluate(cases,models,hasher,det,rec,folder):
    out={'n':0,'positive':0,'negative':0,'methods':{},'blockers':{},'evidence':{},'reread_rows':0,'schedule':Counter(),'read_stats':Counter(),'median_ms':None}
    lat=[]
    for im,expected in cases:
        t=time.perf_counter()
        _,projected,matrix,raw_polys=prepare(im,det,rec,folder)
        valid=[(l,p) for l,p in zip(projected,raw_polys) if valid_box(l) and l.text.strip()]
        if len(projected)!=len(raw_polys):raise RuntimeError('OCR polygon alignment lost')
        lines,groups=group_rows([l for l,p in valid])
        polygons=[cv2.perspectiveTransform(np.asarray(p,dtype=np.float64).reshape(1,-1,2),matrix)[0] for l,p in valid]
        obs=enriched(lines)
        scores={name:m.predict_proba(hasher.transform([c.features for c in obs]))[:,list(m.classes_).index(1)] if obs else [] for name,m in models.items()}
        prior_values={name:protected(lines,obs,sc) for name,sc in scores.items()}
        initial={name:select(lines,groups,obs,sc) for name,sc in scores.items()}
        # One bounded re-read set shared by both models. No known answer.
        reads={}
        if any(prior_values[name] is None or initial[name][0] is None for name in scores):
            # One shared prioritized queue, not a row-index-sorted union.
            merged=[max(float(sc[j]) for sc in scores.values()) for j in range(len(obs))]
            todo,schedule=plan(lines,groups,obs,merged)
            out['schedule'].update(schedule)
            if todo:
                reads,stats=reread_rows(im,lines,groups,todo,matrix,rec,folder,polygons)
                out['read_stats'].update(stats)
        else:
            out['schedule']['documents_already_accepted']+=1
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
    evidence_self_test()
    ink_self_test()
    samples,meta=prior.sample(prior.preflight(HfApi()))
    result={'dataset_revision':prior.DATA_REV,'sampling':meta,'training':{},'evaluations':{},'synthetic':{},'models':{}}
    save(result,'row_ink_preflight_results.json')
    dp,dm=fetch(DET,prior.DET_REV);rp,rm=fetch(REC,REC_REV)
    result['models']={DET:dm,REC:rm}
    det=TextDetection(model_name=DET,model_dir=str(dp),device='cpu',enable_mkldnn=False,cpu_threads=2)
    rec=TextRecognition(model_name=REC,model_dir=str(rp),device='cpu',enable_mkldnn=False,cpu_threads=2)
    hasher=FeatureHasher(n_features=N_FEATURES,input_type='dict',alternate_sign=False)
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp)
        result['activation_probe']=activation_probe(rec,folder)
        save(result,'row_ink_probe_results.json')
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
        save(result,'row_ink_training_results.json')
        for kind in ('split','combined','tilt','blur','duplicate','missing'):
            result['synthetic'][kind]=evaluate((fixture(i,kind) for i in range(4)),models,hasher,det,rec,folder)
        for kind in ('split','combined','duplicate','missing'):
            result['synthetic']['perspective_'+kind]=evaluate((distorted(kind,12,q) for q in QUADS),models,hasher,det,rec,folder)
        save(result,'row_ink_synthetic_results.json')
        for name,selected in [('reused_val',samples['val'][:40]),('last_val',samples['val'][120:]),('test',samples['test'])]:
            result['evaluations'][name]=evaluate(load(selected),models,hasher,det,rec,folder)
            save(result,'row_ink_'+name+'_results.json')
    save(result,'row_ink_final_results.json')
    if sum(x['read_stats'].get('ink_calls',0) for x in result['evaluations'].values())==0:
        raise RuntimeError('No real-document ink-separated rereads executed; inspect preserved separation counters')
if __name__=='__main__':main()
