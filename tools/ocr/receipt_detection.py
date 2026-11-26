"""Whole-receipt detection + recognition experiment; no raw receipt data logged."""
import hashlib
import io
import json
import math
import statistics
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from huggingface_hub import HfApi, hf_hub_download, snapshot_download
import pyarrow.parquet as pq
from paddleocr import TextDetection, TextRecognition
from ocr_preprocess import trim, normalize
from paddle_diagnostic import DATASET, DATA_REV, crop_box
from total_candidate import Line, extract, self_test, good

REC='eslav_PP-OCRv5_mobile_rec'
REC_REV='7553801264d3379d8d2e854971989e5e26c22e03'
DET='PP-OCRv5_mobile_det'

def fetch(name,rev):
    folder=Path(snapshot_download('PaddlePaddle/'+name,revision=rev,allow_patterns=['inference*','README.md','LICENSE*']))
    return folder,{'revision':rev,'files':{p.name:{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in folder.iterdir() if p.is_file()}}

def warp(image,polygon):
    p=np.asarray(polygon,dtype=np.float32)
    if p.shape!=(4,2) or not np.isfinite(p).all():return None
    # Preserve cyclic polygon order; choose first corner and clockwise direction.
    center=p.mean(axis=0)
    p=p[np.argsort(np.arctan2(p[:,1]-center[1],p[:,0]-center[0]))]
    p=np.roll(p,-int(np.argmin(p.sum(axis=1))),axis=0)
    width=round(max(np.linalg.norm(p[1]-p[0]),np.linalg.norm(p[2]-p[3])))
    height=round(max(np.linalg.norm(p[3]-p[0]),np.linalg.norm(p[2]-p[1])))
    if min(width,height)<3 or max(width,height)>8000:return None
    dest=np.array([[0,0],[width-1,0],[width-1,height-1],[0,height-1]],np.float32)
    crop=cv2.warpPerspective(image,cv2.getPerspectiveTransform(p,dest),(width,height),borderMode=cv2.BORDER_REPLICATE)
    if height>width*1.5:crop=cv2.rotate(crop,cv2.ROTATE_90_COUNTERCLOCKWISE)
    return crop

def process(im,detector,recognizer,folder):
    image=np.asarray(im.convert('RGB')).copy()
    # Paths avoid ambiguity of RGB/BGR input conventions.
    path=folder/'document.png';Image.fromarray(image).save(path)
    detected=list(detector.predict(input=str(path),batch_size=1))
    if len(detected)!=1:raise RuntimeError('Unexpected detection batch')
    data=detected[0].json['res']
    polygons=data['dt_polys']
    crops=[];boxes=[]
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
    if not crops:return []
    result=list(recognizer.predict(input=crops,batch_size=8))
    if len(result)!=len(crops):raise RuntimeError('Recognition count differs from detection')
    by_path={str(Path(r.json['res']['input_path']).resolve()):r.json['res'] for r in result}
    lines=[]
    for file,box in zip(crops,boxes):
        entry=by_path[str(Path(file).resolve())]
        lines.append(Line(str(entry['rec_text']),float(entry['rec_score']),box))
    for path in crops:Path(path).unlink()
    return lines

def summary():
    return dict(n=0,accepted=0,wrong=0,correct=0,oracle_exact=0,oracle_exact_high_confidence=0,detected_lines=0,annotated_box_valid=0,annotation_overlap=0,latency_ms=[])

def tally(row,lines,expected,elapsed,annotation=None):
    row['n']+=1;row['detected_lines']+=len(lines);row['latency_ms'].append(elapsed*1000)
    # Oracle only diagnoses whether the known amount is visible somewhere in OCR.
    # It never feeds the candidate selection.
    if expected is not None:
        import re
        pattern=re.compile(r'(?<![0-9])(?:[0-9]{1,7}|[0-9]{1,3}(?: [0-9]{3}){1,2})[,.][0-9]{2}(?![0-9])')
        hits=[l for l in lines if any(normalize(m.group())==expected for m in pattern.finditer(' '.join(l.text.split())))]
        row['oracle_exact']+=int(bool(hits))
        row['oracle_exact_high_confidence']+=int(any(good(l) for l in hits))
    candidate=extract(lines)
    row['accepted']+=int(candidate is not None)
    row['wrong']+=int(candidate is not None and candidate!=expected)
    row['correct']+=int(candidate is not None and candidate==expected)
    if annotation is not None:
        row['annotated_box_valid']+=1
        a,b,c,d=annotation; area=(c-a)*(d-b)
        for line in lines:
            x,y,X,Y=line.box
            overlap=max(0,min(c,X)-max(a,x))*max(0,min(d,Y)-max(b,y))
            if area>0 and overlap/area>=.5:
                row['annotation_overlap']+=1;break

def finish(row):
    lat=row.pop('latency_ms')
    row['median_ms']=round(statistics.median(lat),2) if lat else None
    row['p95_ms']=round(sorted(lat)[max(0,math.ceil(len(lat)*.95)-1)],2) if lat else None

def fixture(i,kind):
    im=Image.new('RGB',(800,580),'white')
    draw=ImageDraw.Draw(im)
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',30+i%3*2)
    cents=15937+i*2317; amount=f'{cents//100},{cents%100:02}'
    rows=[('КАССОВЫЙ ЧЕК',''),('МОЛОКО 2 ШТ','95,00'),('ХЛЕБ','64,37'),('СКИДКА','10,00'),('ИТОГО' if i%2 else 'ВСЕГО К ОПЛАТЕ',amount),('ОПЛАТА КАРТОЙ',amount)]
    if kind=='duplicate':rows.insert(5,('ИТОГО','999,99'))
    if kind=='missing':rows.pop(4)
    if kind=='combined':
        rows[4]=(rows[4][0]+' '+amount,'')
    for j,(label,value) in enumerate(rows):
        y=25+j*70;draw.text((25,y),label,fill='black',font=font)
        if value:draw.text((765,y),value,fill='black',font=font,anchor='ra')
    if kind=='tilt':im=im.rotate(-6 if i%2 else 7,expand=True,fillcolor='white')
    if kind=='blur':im=im.resize((480,348)).filter(ImageFilter.GaussianBlur(1.0))
    return im,None if kind in ('duplicate','missing') else amount

def main():
    self_test()
    api=HfApi()
    det_rev=api.model_info('PaddlePaddle/'+DET).sha
    det_path,dm=fetch(DET,det_rev);rec_path,rm=fetch(REC,REC_REV)
    det=TextDetection(model_name=DET,model_dir=str(det_path),device='cpu',enable_mkldnn=False,cpu_threads=2)
    rec=TextRecognition(model_name=REC,model_dir=str(rec_path),device='cpu',enable_mkldnn=False,cpu_threads=2)
    result={'models':{DET:dm,REC:rm},'dataset_revision':DATA_REV,'synthetic':{},'annotated_real':summary(),'dataset_rows':0,'invalid_reference':0,'missing_image':0}
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp)
        for kind in ('split','combined','tilt','blur','duplicate','missing'):
            stats=summary()
            for i in range(6):
                im,expected=fixture(i,kind)
                start=time.perf_counter();lines=process(im,det,rec,folder);elapsed=time.perf_counter()-start
                tally(stats,lines,expected,elapsed)
            finish(stats);result['synthetic'][kind]=stats
        Path('receipt_detection_synthetic_results.json').write_text(json.dumps(result,indent=2)+'\n')
        files=api.list_repo_files(DATASET,repo_type='dataset',revision=DATA_REV)
        files=sorted(f for f in files if f.endswith('.parquet') and ('/test/' in '/'+f or Path(f).name.startswith('test-')))
        if not files:raise RuntimeError('Missing test split')
        for file in files:
            path=hf_hub_download(DATASET,file,repo_type='dataset',revision=DATA_REV)
            for batch in pq.ParquetFile(path).iter_batches(batch_size=4,columns=['image','total_text','total_bbox']):
                for row in batch.to_pylist():
                    result['dataset_rows']+=1
                    expected=normalize(row['total_text'])
                    if expected is None:result['invalid_reference']+=1;continue
                    if not row['image'] or not row['image'].get('bytes'):result['missing_image']+=1;continue
                    with Image.open(io.BytesIO(row['image']['bytes'])) as src:im=src.convert('RGB')
                    box=crop_box(row['total_bbox'],im.width,im.height)
                    start=time.perf_counter();lines=process(im,det,rec,folder);elapsed=time.perf_counter()-start
                    tally(result['annotated_real'],lines,expected,elapsed,box)
        if result['dataset_rows']!=151:raise RuntimeError('Incomplete dataset evaluation')
        finish(result['annotated_real'])
    Path('receipt_detection_results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
