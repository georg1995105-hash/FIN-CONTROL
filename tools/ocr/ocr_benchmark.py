"""Synthetic Russian receipt OCR benchmark, no network and no user data."""
import csv, hashlib, io, json, os, re, resource, statistics, subprocess, tempfile, time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np

FONT = os.getenv('FIN_OCR_FONT', '/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf')
TESSDATA = Path(os.getenv('TESSDATA_PREFIX', '/usr/share/tesseract-ocr/5/tessdata'))
LABELS = ('ТОВАР', 'СКИДКА', 'ИТОГО')
VARIANTS = ('clean', 'small', 'blur', 'tilt', 'cropped')
MONEY = re.compile(r'\d{1,7}[,.]\d{2}')

def fixture(i, variant, holdout=False):
    cents = (12743 + i * 1739, 199 + i * 137)
    values = [cents[0], cents[1], cents[0] - cents[1]]
    expected = dict(zip(LABELS, (f'{x//100},{x%100:02}' for x in values)))
    image = Image.new('L', (760, 340), 255)
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(FONT, 32 if holdout else 36)
    draw.text((38, 22), 'КАССОВЫЙ ЧЕК', font=font, fill=0)
    for j, (label, value) in enumerate(expected.items()):
        draw.text((38, 90 + j*65), f'{label}   {value}', font=font, fill=0)
    if variant == 'small':
        image = image.resize((380, 170))
    elif variant == 'blur':
        image = image.resize((430, 192)).filter(ImageFilter.GaussianBlur(1.9 if holdout else 1.4))
    elif variant == 'tilt':
        image = image.rotate((-7 if i % 2 else 11) if holdout else 9, expand=True, fillcolor=255)
    elif variant == 'cropped':
        image = image.crop((0, 0, 760, 210))
    return image, expected

def prepare(image):
    # Projection-profile deskew; never use reference labels or known values.
    thumb = image.copy()
    thumb.thumbnail((400, 400))
    def score(angle):
        rotated = thumb.rotate(angle, resample=Image.Resampling.BILINEAR, expand=True, fillcolor=255)
        profile = (np.asarray(rotated) < 160).sum(axis=1).astype(float)
        return float(np.square(np.diff(profile)).sum())
    angle = max(range(-12, 13), key=lambda a: (score(a), -abs(a)))
    image = image.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)
    if image.width < 700:
        image = image.resize((image.width*2, image.height*2), Image.Resampling.LANCZOS)
    return image

def recognize(path):
    env = dict(os.environ, OMP_THREAD_LIMIT='1')
    start = time.perf_counter()
    result = subprocess.run(['tesseract', str(path), 'stdout', '-l', 'rus', '--oem', '1', '--psm', '6', 'tsv'], env=env, capture_output=True, text=True, timeout=15, check=True)
    groups = {}
    for word in csv.DictReader(io.StringIO(result.stdout), delimiter='\t'):
        if word['level'] == '5' and word['text'].strip():
            key = tuple(word[k] for k in ('page_num','block_num','par_num','line_num'))
            groups.setdefault(key, []).append((word['text'].strip(), float(word['conf'])))
    found = {}
    for words in groups.values():
        if len(words) != 2: continue
        (label, c1), (number, c2) = words
        if label in LABELS and MONEY.fullmatch(number):
            found.setdefault(label, []).append((number.replace('.', ','), min(c1, c2)))
    raw = {k: v[0][0] for k,v in found.items() if len(v) == 1}
    candidate = len(raw) == len(LABELS) and all(len(v)==1 and v[0][1]>=85 for v in found.values())
    return raw, candidate, round(time.perf_counter()-start, 3)

def benchmark(prepared=False, holdout=False):
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)/'sample.png'
        for variant in VARIANTS:
            for i in range(5):
                image, expected = fixture(i + (10 if holdout else 0), variant, holdout)
                start = time.perf_counter()
                if prepared: image = prepare(image)
                image.save(path)
                raw, candidate, _ = recognize(path)
                elapsed = time.perf_counter()-start
                exact = sum(raw.get(k)==v for k,v in expected.items())
                rows.append(dict(variant=variant, exact_fields=exact, candidate=candidate, unsafe_candidate=candidate and (variant=='cropped' or exact!=3), elapsed=elapsed))
    return {'samples':len(rows), 'exact_fields':sum(r['exact_fields'] for r in rows), 'total_fields':3*len(rows), 'candidates':sum(r['candidate'] for r in rows), 'unsafe_candidates':sum(r['unsafe_candidate'] for r in rows), 'median_seconds':round(statistics.median(r['elapsed'] for r in rows),3), 'variants':{v:{'exact_fields':sum(r['exact_fields'] for r in rows if r['variant']==v), 'candidates':sum(r['candidate'] for r in rows if r['variant']==v), 'unsafe_candidates':sum(r['unsafe_candidate'] for r in rows if r['variant']==v)} for v in VARIANTS}}

def main():
    result = {'version': subprocess.check_output(['tesseract','--version'], text=True).splitlines()[0], 'model_sha256': hashlib.sha256((TESSDATA/'rus.traineddata').read_bytes()).hexdigest(), 'model_bytes': (TESSDATA/'rus.traineddata').stat().st_size, 'font_sha256': hashlib.sha256(Path(FONT).read_bytes()).hexdigest(), 'baseline':benchmark(), 'prepared':benchmark(prepared=True), 'holdout_prepared':benchmark(prepared=True, holdout=True)}
    result['peak_child_rss_kib'] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    result['peak_python_rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__': main()
