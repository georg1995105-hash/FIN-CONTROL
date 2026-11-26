"""Synthetic monetary crop comparison; no document parsing or user data."""
import csv, hashlib, io, json, os, re, statistics, subprocess, tempfile, time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

MODELS = ('rus', 'Cyrillic', 'eng')
DATA = Path('/usr/share/tesseract-ocr/5/tessdata')
FONT = '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf'
MONEY = re.compile(r'[0-9]{1,7}[,.][0-9]{2}')
VALUES = ('1099,10','1999,10','1000,01','1088,80','8888,88','0,01','90,09','123456,78','17,70','2020,02','3068,89','741,15')
VARIANTS = ('clean','small','blur','tilt')

def fixture(value, variant):
    im = Image.new('L',(480,100),255)
    ImageDraw.Draw(im).text((20,20),value,fill=0,font=ImageFont.truetype(FONT,48))
    if variant=='small': im=im.resize((240,50),Image.Resampling.LANCZOS)
    if variant=='blur': im=im.resize((240,50)).filter(ImageFilter.GaussianBlur(1.5))
    if variant=='tilt': im=im.rotate(6,expand=True,fillcolor=255)
    return im.resize((im.width*2,im.height*2),Image.Resampling.LANCZOS)

def read(im,path,lang):
    im.save(path)
    out=subprocess.run(['tesseract',str(path),'stdout','-l',lang,'--oem','1','--psm','7','-c','tessedit_char_whitelist=0123456789,.','tsv'],env=dict(os.environ,OMP_THREAD_LIMIT='1'),capture_output=True,text=True,check=True,timeout=15).stdout
    words=[r for r in csv.DictReader(io.StringIO(out),delimiter='\t') if r['level']=='5' and r['text'].strip()]
    if len(words)!=1:return None
    s=words[0]['text']; conf=float(words[0]['conf'])
    return s.replace('.',',') if MONEY.fullmatch(s) and conf>=85 else None

def main():
    methods=MODELS+('rus_eng_agreement','all_agreement'); summary={m:{v:{'n':0,'accepted':0,'wrong':0} for v in VARIANTS} for m in methods}; times={m:[] for m in MODELS}
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'crop.png'
        for variant in VARIANTS:
            for expected in VALUES:
                im=fixture(expected,variant); reads={}
                for m in MODELS:
                    start=time.perf_counter(); reads[m]=read(im,path,m); times[m].append(time.perf_counter()-start)
                reads['rus_eng_agreement']=reads['rus'] if reads['rus']==reads['eng'] else None
                reads['all_agreement']=reads['rus'] if reads['rus']==reads['eng']==reads['Cyrillic'] else None
                for m,result in reads.items():
                    r=summary[m][variant];r['n']+=1;r['accepted']+=int(result is not None);r['wrong']+=int(result is not None and result!=expected)
    print(json.dumps({'engine':subprocess.check_output(['tesseract','--version'],text=True).splitlines()[0],'models':{m:{'sha256':hashlib.sha256((DATA/(m+'.traineddata')).read_bytes()).hexdigest(),'bytes':(DATA/(m+'.traineddata')).stat().st_size} for m in MODELS},'font_sha256':hashlib.sha256(Path(FONT).read_bytes()).hexdigest(),'results':summary,'median_seconds':{m:round(statistics.median(times[m]),3) for m in MODELS}},indent=2))

if __name__=='__main__':main()
