"""Research-only comparison of official PaddleOCR models and Tesseract.
Synthetic number crops and CDEK test-set annotated total crops; no raw images,
receipt values or predictions are printed or retained. Annotation is not ground truth.
"""
import hashlib
import io
import json
import math
import re
import tempfile
import time
from pathlib import Path
from importlib.metadata import version

from PIL import Image
from huggingface_hub import HfApi, hf_hub_download, snapshot_download
import pyarrow.parquet as pq
from paddleocr import TextRecognition
from number_probe import VALUES, VARIANTS, fixture, read, MONEY

MODELS = ('cyrillic_PP-OCRv3_mobile_rec', 'cyrillic_PP-OCRv5_mobile_rec')
DATASET = 'cdek-ocr/receipt-ocr-ru'

def normal(value):
    if not isinstance(value, str): return None
    value = value.strip().replace('.', ',')
    return value if MONEY.fullmatch(value) else None

def crop_box(raw, width, height):
    try:
        box = json.loads(raw) if isinstance(raw, str) else raw
        if len(box) == 4 and all(isinstance(x, (int,float)) for x in box):
            x1,y1,x2,y2=box
        elif len(box) == 4 and all(isinstance(p,list) and len(p)==2 for p in box):
            x1,y1=min(p[0] for p in box),min(p[1] for p in box)
            x2,y2=max(p[0] for p in box),max(p[1] for p in box)
        else: return None
        if not all(math.isfinite(x) for x in (x1,y1,x2,y2)): return None
        if not (0<=x1<x2<=width and 0<=y1<y2<=height and x2-x1>=10 and y2-y1>=8): return None
        return math.floor(x1),math.floor(y1),math.ceil(x2),math.ceil(y2)
    except (TypeError,ValueError,KeyError,IndexError,OverflowError): return None

def paddle_read(model, im, path):
    im.convert('RGB').save(path)
    result = model.predict(input=str(path),batch_size=1)
    if len(result)!=1: return None
    entry=result[0].json['res']
    return normal(entry['rec_text']) if float(entry['rec_score'])>=0.85 else None

def tally(stats, expected, reads):
    for key,value in reads.items():
        row=stats.setdefault(key,dict(n=0,accepted=0,wrong=0))
        row['n']+=1
        row['accepted']+=int(value is not None)
        row['wrong']+=int(value is not None and value!=expected)

def main():
    api=HfApi()
    models={}; manifests={}
    for name in MODELS:
        repo='PaddlePaddle/'+name
        revision=api.model_info(repo).sha
        path=Path(snapshot_download(repo,revision=revision,allow_patterns=['inference*','README.md','LICENSE*']))
        files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in path.iterdir() if p.is_file()}
        manifests[name]={'revision':revision,'files':files}
        models[name]=TextRecognition(model_name=name,model_dir=str(path),device='cpu',enable_mkldnn=False,cpu_threads=2)
    result={'packages':{p:version(p) for p in ('paddleocr','paddlepaddle','huggingface-hub','pyarrow','Pillow')},'models':manifests,'synthetic':{},'real_annotated_total_crops':{},'dataset_skips':0,'dataset_rows':0}
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)/'crop.png'
        def predict(im):
            reads={'tesseract_rus':read(im,path,'rus')}
            for name,model in models.items(): reads[name]=paddle_read(model,im,path)
            for name in MODELS:
                reads[name+'_and_tesseract']=reads[name] if reads[name]==reads['tesseract_rus'] else None
            return reads
        for variant in VARIANTS:
            result['synthetic'][variant]={}
            for expected in VALUES: tally(result['synthetic'][variant],expected,predict(fixture(expected,variant)))
        # Write synthetic results separately even if dataset retrieval fails.
        Path('paddle_synthetic_results.json').write_text(json.dumps(result,indent=2)+'\n')
        revision=api.dataset_info(DATASET,revision='refs/convert/parquet').sha
        files=api.list_repo_files(DATASET,repo_type='dataset',revision=revision)
        files=sorted(f for f in files if f.endswith('.parquet') and ('/test/' in '/'+f or Path(f).name.startswith('test-')))
        if not files: raise RuntimeError('No test parquet files found; no dataset results')
        result['dataset_revision']=revision
        for name in files:
            local=hf_hub_download(DATASET,name,repo_type='dataset',revision=revision)
            for batch in pq.ParquetFile(local).iter_batches(batch_size=4,columns=['image','total_text','total_bbox']):
                for row in batch.to_pylist():
                    result['dataset_rows']+=1
                    expected=normal(row['total_text'])
                    if expected is None or not row['image'] or not row['image'].get('bytes'):
                        result['dataset_skips']+=1; continue
                    with Image.open(io.BytesIO(row['image']['bytes'])) as src:
                        box=crop_box(row['total_bbox'],src.width,src.height)
                        if box is None: result['dataset_skips']+=1; continue
                        im=src.crop(box).convert('L')
                    tally(result['real_annotated_total_crops'],expected,predict(im))
        if not result['real_annotated_total_crops']:
            raise RuntimeError('No evaluable annotated crops; dataset check incomplete')
    Path('paddle_comparison_results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
