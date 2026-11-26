"""Pinned OCR, aggregate-only diagnostics on the reused test split and a
previously unused validation subset. Exact duplicate image bytes excluded
from validation; near duplicates and annotation errors remain possible.
"""
import hashlib
import io
import json
import tempfile
import time
from collections import Counter
from pathlib import Path
from PIL import Image
from huggingface_hub import HfApi,hf_hub_download
import pyarrow.parquet as pq
from paddleocr import TextDetection,TextRecognition
from receipt_structure import process,fetch,DET,REC,REC_REV,fixture
from paddle_diagnostic import DATASET,DATA_REV
from document_structure import analyze
from layout_diagnostics import diagnose,anchor_candidate,self_test
from ocr_preprocess import normalize

DET_REV='0d63e78e2b680928f6b1747d76a08db6e645efb7'
VALIDATION_LIMIT=40

def stats():
    return {'n':0,'old':{'accepted':0,'correct':0,'wrong':0},'anchor':{'accepted':0,'correct':0,'wrong':0},
            'causes':Counter(),'facts':Counter(),'unresolved_facts':Counter()}

def tally(st,lines,expected):
    st['n']+=1
    old=analyze(lines); new=anchor_candidate(lines)
    for key,value in [('old',old.amount),('anchor',new)]:
        row=st[key]
        row['accepted']+=int(value is not None)
        row['correct']+=int(value is not None and value==expected)
        row['wrong']+=int(value is not None and value!=expected)
    cause,facts=diagnose(lines,expected)
    st['causes'][cause]+=1
    st['facts'].update(facts)
    if old.reason=='unresolved_total':st['unresolved_facts'].update(facts)

def rows_for(api,split):
    files=api.list_repo_files(DATASET,repo_type='dataset',revision=DATA_REV)
    files=sorted(f for f in files if f.endswith('.parquet') and ('/'+split+'/' in '/'+f or Path(f).name.startswith(split+'-')))
    if not files:raise RuntimeError('Missing requested dataset split: '+split)
    for file in files:
        path=hf_hub_download(DATASET,file,repo_type='dataset',revision=DATA_REV)
        for batch in pq.ParquetFile(path).iter_batches(batch_size=4,columns=['image','total_text']):
            yield from batch.to_pylist()

def save(result,name):
    Path(name).write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')

def main():
    self_test()
    api=HfApi()
    dp,dm=fetch(DET,DET_REV);rp,rm=fetch(REC,REC_REV)
    det=TextDetection(model_name=DET,model_dir=str(dp),device='cpu',enable_mkldnn=False,cpu_threads=2)
    rec=TextRecognition(model_name=REC,model_dir=str(rp),device='cpu',enable_mkldnn=False,cpu_threads=2)
    result={'models':{DET:dm,REC:rm},'dataset_revision':DATA_REV,
            'synthetic':{},'repeated_test':stats(),'validation_subset':stats(),
            'test_rows':0,'test_invalid':0,'validation_rows':0,'validation_invalid':0,
            'validation_exact_duplicates':0,'validation_eligible':0}
    seen=set()
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp)
        for kind in ('split','combined','tilt','blur','duplicate','missing'):
            st=stats()
            for i in range(6):
                im,expected=fixture(i,kind)
                tally(st,process(im,det,rec,folder),expected)
            result['synthetic'][kind]=st
        for row in rows_for(api,'test'):
            result['test_rows']+=1
            data=(row.get('image') or {}).get('bytes')
            expected=normalize(row['total_text'])
            if data:seen.add(hashlib.sha256(data).digest())
            if not data or expected is None:
                result['test_invalid']+=1;continue
            with Image.open(io.BytesIO(data)) as im:
                lines=process(im,det,rec,folder)
            tally(result['repeated_test'],lines,expected)
        if result['test_rows']!=151 or result['repeated_test']['n']!=140:raise RuntimeError('Unexpected test size')
        save(result,'layout_diagnostic_test_results.json')
        # Deterministic sample by hash order, not annotation value or model output.
        # Retain only up to VALIDATION_LIMIT image byte arrays in memory.
        selected=[]
        for row in rows_for(api,'validation'):
            result['validation_rows']+=1
            data=(row.get('image') or {}).get('bytes')
            expected=normalize(row['total_text'])
            if not data or expected is None:
                result['validation_invalid']+=1;continue
            digest=hashlib.sha256(data).digest()
            if digest in seen:
                result['validation_exact_duplicates']+=1;continue
            seen.add(digest)
            result['validation_eligible']+=1
            selected.append((digest,data,expected))
            selected.sort(key=lambda x:x[0])
            if len(selected)>VALIDATION_LIMIT:selected.pop()
        if len(selected)!=VALIDATION_LIMIT:raise RuntimeError('Insufficient unique validation images')
        for _,data,expected in selected:
            with Image.open(io.BytesIO(data)) as im:
                lines=process(im,det,rec,folder)
            tally(result['validation_subset'],lines,expected)
    save(result,'layout_diagnostic_results.json')
    print(json.dumps(result,indent=2,sort_keys=True))
if __name__=='__main__':main()
