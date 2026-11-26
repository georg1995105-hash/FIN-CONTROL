"""Experimental extraction of labeled monetary fields, never a confirmed audit."""
import csv
import io
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from ocr_benchmark import prepare

ALIASES = {'ТОВАР': 'subtotal', 'РАБОТА': 'subtotal', 'МАТЕРИАЛЫ': 'subtotal',
           'СКИДКА': 'discount', 'ИТОГО': 'total', 'ВСЕГО К ОПЛАТЕ': 'total',
           'ИТОГО С УЧЕТОМ СКИДКИ': 'total'}
AMOUNT = re.compile(r'\d{1,7}[,.]\d{2}')


def words(image, path, psm):
    image.save(path)
    output = subprocess.run(['tesseract', str(path), 'stdout', '-l', 'rus', '--oem', '1',
                             '--psm', str(psm), 'tsv'], env=dict(os.environ, OMP_THREAD_LIMIT='1'),
                            capture_output=True, text=True, check=True, timeout=15).stdout
    result = []
    for row in csv.DictReader(io.StringIO(output), delimiter='\t'):
        if row['level'] != '5' or not row['text'].strip(): continue
        x, y, w, h = (int(row[k]) for k in ('left', 'top', 'width', 'height'))
        result.append((row['text'], float(row['conf']), x, y, w, h))
    return result


def rows_by_y(tokens):
    groups = []
    for token in sorted(tokens, key=lambda t: t[3]+t[5]/2):
        center = token[3]+token[5]/2
        if groups and abs(center-groups[-1][0]) <= max(3, min(token[5],groups[-1][1][0][5])*0.55):
            groups[-1][1].append(token)
        else:
            groups.append((center,[token]))
    return [sorted(g[1],key=lambda t:t[2]) for g in groups]


def parse(row):
    if len(row)<2 or not AMOUNT.fullmatch(row[-1][0]): return None
    label = ' '.join(t[0] for t in row[:-1]).upper().replace('Ё','Е')
    key = ALIASES.get(label)
    if not key: return None
    return key, row[-1][0].replace('.',','), min(t[1] for t in row)


def extract(image,path):
    detected = {}
    for row in rows_by_y(words(image,path,6)):
        item = parse(row)
        if item is None: continue
        key, amount, confidence = item
        # Require corroboration for every field, not only low-confidence ones.
        x0=max(0,min(t[2] for t in row)-12); y0=max(0,min(t[3] for t in row)-12)
        x1=min(image.width,max(t[2]+t[4] for t in row)+12); y1=min(image.height,max(t[3]+t[5] for t in row)+12)
        cropped=image.crop((x0,y0,x1,y1))
        cropped=cropped.resize((cropped.width*2,cropped.height*2),Image.Resampling.LANCZOS)
        retry=parse(sorted(words(cropped,path,7),key=lambda t:t[2]))
        if retry and retry[:2]==(key,amount) and retry[2]>=85: confidence=retry[2]
        else: confidence=-1
        detected.setdefault(key,[]).append((amount,confidence))
    # Multiple readings of a field are ambiguous even if the values agree.
    fields={k:v[0][0] for k,v in detected.items() if len(v)==1 and v[0][1]>=85}
    candidate=set(fields)=={'subtotal','discount','total'} and all(len(v)==1 for v in detected.values())
    return fields,candidate


def main():
    variants=('receipt','invoice','estimate','duplicate_total','missing_discount')
    result={}
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'sample.png'
        for batch in ('development','new_layouts'):
            summary={v:{'samples':0,'candidates':0,'wrong_candidates':0} for v in variants}
            for variant in variants:
                for i in range(4):
                    expected={'subtotal':f'{300+i*71},50','discount':'20,00','total':f'{280+i*71},50'}
                    if batch=='new_layouts': expected={'subtotal':f'{1000+i*129},17','discount':'30,07','total':f'{970+i*129},10'}
                    labels=('ТОВАР','СКИДКА','ИТОГО') if variant in ('receipt','duplicate_total','missing_discount') else ('Работа','Скидка','Всего к оплате') if variant=='invoice' else ('Материалы','Скидка','Итого с учетом скидки')
                    lines=[('КАССОВЫЙ ЧЕК' if variant=='receipt' else 'ДОКУМЕНТ',''),('Пример позиции 2 шт.','100,00')]+list(zip(labels,expected.values()))
                    if variant=='duplicate_total': lines.append(('ИТОГО','999,99'))
                    if variant=='missing_discount': lines.pop(3)
                    if batch=='new_layouts': lines.insert(1,('Номер документа 12345',''))
                    im=Image.new('L',(900,560),255);d=ImageDraw.Draw(im)
                    f=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf' if batch=='development' else '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',27+i*2)
                    for j,(label,value) in enumerate(lines):
                        y=30+j*64; d.text((35,y),label,fill=0,font=f)
                        if value:d.text((815 if batch=='development' else 850,y),value,fill=0,font=f,anchor='ra')
                    if batch=='new_layouts': im=im.rotate(-4 if i%2 else 5,expand=True,fillcolor=255)
                    fields,candidate=extract(prepare(im),path)
                    row=summary[variant];row['samples']+=1;row['candidates']+=int(candidate)
                    row['wrong_candidates']+=int(candidate and (fields!=expected or variant in ('duplicate_total','missing_discount')))
            result[batch]=summary
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
