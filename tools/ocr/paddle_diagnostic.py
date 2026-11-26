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

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np
from ocr_preprocess import trim, normalize, self_test
from huggingface_hub import HfApi, hf_hub_download, snapshot_download
import pyarrow.parquet as pq
from paddleocr import TextRecognition
from number_probe import VALUES, VARIANTS, fixture, read, MONEY

MODELS = ('cyrillic_PP-OCRv3_mobile_rec', 'eslav_PP-OCRv5_mobile_rec')
DATASET = 'cdek-ocr/receipt-ocr-ru'
REVISIONS = {'cyrillic_PP-OCRv3_mobile_rec':'e5b3249015e50836e3a7a54301a314b9d7fc7059','eslav_PP-OCRv5_mobile_rec':'7553801264d3379d8d2e854971989e5e26c22e03'}
DATA_REV = 'b322f00a2a028cf2156d4b4f89f9230d46b90eb7'

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
        # CDEK annotations can use normalized coordinates, not pixels.
        if 0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1:
            x1, x2, y1, y2 = x1*width, x2*width, y1*height, y2*height
        if not (0<=x1<x2<=width and 0<=y1<y2<=height and x2-x1>=10 and y2-y1>=8): return None
        return math.floor(x1),math.floor(y1),math.ceil(x2),math.ceil(y2)
    except (TypeError,ValueError,KeyError,IndexError,OverflowError): return None

def paddle_read(model, im, path):
    # Strip incompatible ICC metadata; preserve pixels.
    Image.fromarray(np.asarray(im.convert('RGB')).copy()).save(path)
    result = list(model.predict(input=str(path),batch_size=1))
    if len(result)!=1: return '',0.0
    entry=result[0].json['res']
    return str(entry['rec_text']), float(entry['rec_score'])

def tally(stats, expected, reads):
    for key,(raw,score) in reads.items():
        row=stats.setdefault(key,dict(n=0,accepted=0,wrong=0,raw_exact=0,normalized_exact=0,empty=0,format_rejected=0,confidence_rejected=0))
        row['n']+=1
        value=normalize(raw)
        row['raw_exact']+=int(normal(raw)==expected)
        row['normalized_exact']+=int(value==expected)
        if not raw.strip(): row['empty']+=1
        elif value is None: row['format_rejected']+=1
        elif not math.isfinite(score) or score<0.85: row['confidence_rejected']+=1
        else:
            row['accepted']+=1
            row['wrong']+=int(value!=expected)

def main():
    self_test()
    api=HfApi()
    models={}; manifests={}
    for name in MODELS:
        repo='PaddlePaddle/'+name
        revision=REVISIONS[name]
        path=Path(snapshot_download(repo,revision=revision,allow_patterns=['inference*','README.md','LICENSE*']))
        files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in path.iterdir() if p.is_file()}
        manifests[name]={'revision':revision,'files':files}
        models[name]=TextRecognition(model_name=name,model_dir=str(path),device='cpu',enable_mkldnn=False,cpu_threads=2)
    result={'packages':{p:version(p) for p in ('paddleocr','paddlepaddle','huggingface-hub','pyarrow','Pillow')},'models':manifests,'synthetic':{},'new_synthetic':{},'real_annotated_total_crops':{},'dataset_skips':0,'dataset_rows':0}
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)/'crop.png'
        def predict(im):
            reads={}
            for mode,inp in [('original',im),('trimmed',trim(im))]:
                value=read(inp,path,'rus')
                reads['tesseract_rus/'+mode]=(value or '',1.0 if value else 0.0)
                for name,model in models.items():
                    reads[name+'/'+mode]=paddle_read(model,inp,path)
            return reads
        for variant in VARIANTS:
            result['synthetic'][variant]={}
            for expected in VALUES: tally(result['synthetic'][variant],expected,predict(fixture(expected,variant)))
        font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',34)
        for variant in VARIANTS:
            stats={}
            for expected in ('1010,11','1009,19','8008,08','681,93','5000,00','9,99','23764,12','6611,16','402,07','10,01','9999,90','1700,73'):
                im=Image.new('L',(380,100),255)
                ImageDraw.Draw(im).text((30,25),expected,fill=0,font=font)
                if variant=='small': im=im.resize((190,50),Image.Resampling.LANCZOS)
                if variant=='blur': im=im.filter(ImageFilter.GaussianBlur(1.7))
                if variant=='tilt': im=im.rotate(-5,expand=True,fillcolor=255)
                tally(stats,expected,predict(im))
            result['new_synthetic'][variant]=stats
        # Write synthetic results separately even if dataset retrieval fails.
        Path('paddle_diagnostic_synthetic_results.json').write_text(json.dumps(result,indent=2)+'\n')
        revision=DATA_REV
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
        if result['dataset_rows']!=151 or not result['real_annotated_total_crops']:
            raise RuntimeError('No evaluable annotated crops; dataset check incomplete')
    Path('paddle_diagnostic_results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
