"""Targeted OCR re-reading with a real additional train-subset probe.
Data and OCR text stay ephemeral; only aggregates are saved.
"""
import csv
import hashlib
import io
import json
import os
import subprocess
import tempfile
import time
import statistics
from pathlib import Path

import numpy as np
from PIL import Image,ImageOps,ImageFilter
from huggingface_hub import HfApi,hf_hub_download
import pyarrow.parquet as pq
from paddleocr import TextDetection,TextRecognition
from receipt_structure import fetch,warp,DET,REC,REC_REV,fixture
from paddle_diagnostic import DATASET,DATA_REV
from total_candidate import Line
from document_structure import analyze
from layout_diagnostics import anchor_candidate
from reread_evidence import key,selected_indices,refined_lines,self_test
from ocr_preprocess import normalize,trim

DET_REV='0d63e78e2b680928f6b1747d76a08db6e645efb7'
ALT='cyrillic_PP-OCRv3_mobile_rec'
ALT_REV='e5b3249015e50836e3a7a54301a314b9d7fc7059'
LIMITS={'test':32,'train':40}

def preflight(api):
    files=api.list_repo_files(DATASET,repo_type='dataset',revision=DATA_REV)
    out={}
    for split in LIMITS:
        paths=sorted(f for f in files if f.endswith('.parquet') and ('/'+split+'/' in '/'+f or Path(f).name.startswith(split+'-')))
        if not paths:raise RuntimeError('Required parquet split absent: '+split)
        out[split]=paths
    print('Preflight: both test and train parquet splits present')
    return out

def records(files,split):
    # First train shard is sufficient for a fixed previously-unused exploratory
    # subset, not representative of all stores. Read all test shards for dedup.
    for file in files[split] if split=='test' else files[split][:1]:
        path=hf_hub_download(DATASET,file,repo_type='dataset',revision=DATA_REV)
        for batch in pq.ParquetFile(path).iter_batches(batch_size=4,columns=['image','total_text']):
            yield from batch.to_pylist()

def sample(files):
    seen=set();selected={};meta={}
    for split,limit in LIMITS.items():
        keep=[];counts=dict(rows=0,invalid=0,exact_duplicates=0,eligible=0,selected=0,shards=len(files[split]) if split=='test' else 1)
        for row in records(files,split):
            counts['rows']+=1
            data=(row.get('image') or {}).get('bytes')
            expected=normalize(row.get('total_text'))
            if not data:counts['invalid']+=1;continue
            digest=hashlib.sha256(data).digest()
            if digest in seen:counts['exact_duplicates']+=1;continue
            seen.add(digest)
            if expected is None:counts['invalid']+=1;continue
            counts['eligible']+=1
            keep.append((digest,data,expected))
            keep.sort(key=lambda x:x[0])
            if len(keep)>limit:keep.pop()
        if len(keep)!=limit:raise RuntimeError('Insufficient unique eligible images: '+split)
        counts['selected']=len(keep);selected[split]=keep;meta[split]=counts
    if meta['test']['rows']!=151:raise RuntimeError('Unexpected test dataset size')
    return selected,meta

def batch_read(model,paths):
    if not paths:return []
    results=list(model.predict(input=[str(p) for p in paths],batch_size=8))
    by_path={str(Path(r.json['res']['input_path']).resolve()):r.json['res'] for r in results}
    if len(by_path)!=len(paths):raise RuntimeError('Unexpected recognition batch')
    return [(str(by_path[str(p.resolve())]['rec_text']),float(by_path[str(p.resolve())]['rec_score'])) for p in paths]

def tess_read(path):
    output=subprocess.run(['tesseract',str(path),'stdout','-l','rus','--oem','1','--psm','7','tsv'],capture_output=True,text=True,check=True,timeout=15,env=dict(os.environ,OMP_THREAD_LIMIT='1')).stdout
    words=[r for r in csv.DictReader(io.StringIO(output),delimiter='\t') if r['level']=='5' and r['text'].strip()]
    if not words:return '',0.
    return ' '.join(r['text'] for r in words),min(float(r['conf']) for r in words)/100.

def process_dual(im,det,rec,alt,folder):
    image=np.asarray(im.convert('RGB')).copy()
    source=folder/'document.png';Image.fromarray(image).save(source)
    result=list(det.predict(input=str(source),batch_size=1))
    if len(result)!=1:raise RuntimeError('Unexpected detection batch')
    boxes=[];raw=[];paths=[]
    for polygon in result[0].json['res']['dt_polys']:
        crop=warp(image,polygon)
        if crop is None:continue
        p=np.asarray(polygon,dtype=float)
        x,y=p.min(axis=0);X,Y=p.max(axis=0)
        if X<=x or Y<=y:continue
        boxes.append((float(x),float(y),float(X),float(Y)))
        imcrop=Image.fromarray(crop).convert('L');raw.append(imcrop)
        path=folder/f'primary-{len(paths)}.png'
        trim(imcrop).convert('RGB').save(path);paths.append(path)
    lines=[Line(t,s,b) for (t,s),b in zip(batch_read(rec,paths),boxes)]
    idx=selected_indices(lines)
    alternate=[]
    for i in idx:
        # Alternate crop: preserve all original ink; enlarge small glyphs and
        # add a modest margin. No expected value is used to select pixels.
        g=raw[i]
        if g.height<64:g=g.resize((max(1,round(g.width*64/g.height)),64),Image.Resampling.LANCZOS)
        g=ImageOps.autocontrast(g,cutoff=0)
        g=ImageOps.expand(g,border=4,fill=255)
        path=folder/f'alternate-{i}.png'
        g.convert('RGB').save(path);alternate.append(path)
    second=batch_read(rec,alternate);third=batch_read(alt,alternate)
    reads={i:(a,b,tess_read(p)) for i,a,b,p in zip(idx,second,third,alternate)}
    models=refined_lines(lines,reads)
    independent=refined_lines(lines,reads,True)
    evidence={'lines':len(lines),'reread_lines':len(idx),
              'old_weak_labels':sum(key(l.text) is not None and key(l.text)[0] in ('label','total') and l.score<.85 for l in lines),
              'model_confirmed_labels':sum(key(l.text) is not None and key(l.text)[0] in ('label','total') and l.score>=.85 for l in models),
              'independent_confirmed_labels':sum(key(l.text) is not None and key(l.text)[0] in ('label','total') and l.score>=.85 for l in independent)}
    values={'old_structure':analyze(lines).amount,'old_anchor':anchor_candidate(lines),'model_consensus':anchor_candidate(models),'independent_consensus':anchor_candidate(independent)}
    for p in paths+alternate:p.unlink()
    source.unlink()
    return values,evidence

def run_cases(cases,det,rec,alt,folder):
    out={'n':0,'methods':{},'evidence':{},'latency_ms':[]}
    for im,expected in cases:
        start=time.perf_counter()
        values,evidence=process_dual(im,det,rec,alt,folder)
        out['latency_ms'].append((time.perf_counter()-start)*1000)
        out['n']+=1
        for name,value in values.items():
            row=out['methods'].setdefault(name,{'accepted':0,'correct':0,'wrong':0})
            row['accepted']+=int(value is not None)
            row['correct']+=int(value is not None and value==expected)
            row['wrong']+=int(value is not None and value!=expected)
        for k,v in evidence.items():out['evidence'][k]=out['evidence'].get(k,0)+v
    out['median_ms']=round(statistics.median(out.pop('latency_ms')),2)
    return out

def save(result,name):
    Path(name).write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result,indent=2,sort_keys=True))

def main():
    self_test()
    api=HfApi()
    files=preflight(api)
    samples,meta=sample(files)
    # Both requested subsets are materialized BEFORE heavy inference.
    result={'dataset_revision':DATA_REV,'sampling':meta,'models':{},'synthetic':{},'real':{}}
    save(result,'reread_preflight_results.json')
    dp,dm=fetch(DET,DET_REV);rp,rm=fetch(REC,REC_REV);ap,am=fetch(ALT,ALT_REV)
    result['models']={DET:dm,REC:rm,ALT:am}
    det=TextDetection(model_name=DET,model_dir=str(dp),device='cpu',enable_mkldnn=False,cpu_threads=2)
    rec=TextRecognition(model_name=REC,model_dir=str(rp),device='cpu',enable_mkldnn=False,cpu_threads=2)
    alt=TextRecognition(model_name=ALT,model_dir=str(ap),device='cpu',enable_mkldnn=False,cpu_threads=2)
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp)
        for kind in ('split','combined','tilt','blur','duplicate','missing'):
            result['synthetic'][kind]=run_cases((fixture(i,kind) for i in range(4)),det,rec,alt,folder)
        save(result,'reread_synthetic_results.json')
        for split,selected in samples.items():
            def cases():
                for _,data,expected in selected:
                    with Image.open(io.BytesIO(data)) as src:im=src.convert('RGB')
                    yield im,expected
            result['real'][split]=run_cases(cases(),det,rec,alt,folder)
            save(result,f'reread_{split}_results.json')
    save(result,'reread_final_results.json')
if __name__=='__main__':main()
