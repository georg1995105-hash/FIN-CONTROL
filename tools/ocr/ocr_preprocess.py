"""Controlled preprocessing and OCR diagnostics; no user data."""
import math
import re
import numpy as np
from PIL import Image, ImageOps, ImageDraw

MONEY = re.compile(r'(?:[0-9]{1,7}|[0-9]{1,3}(?: [0-9]{3}){1,2})[,.][0-9]{2}')

def normalize(text):
    if not isinstance(text, str): return None
    text = text.strip().replace('\u00a0', ' ').replace('\u202f', ' ')
    if not MONEY.fullmatch(text): return None
    return text.replace(' ', '').replace('.', ',')

def trim(im):
    """Remove blank margins, preserving detected foreground, never using target text."""
    gray = im.convert('L')
    a = np.asarray(gray, dtype=np.int16)
    if min(a.shape) < 3: return gray
    bg = float(np.median(np.concatenate((a[0], a[-1], a[:,0], a[:,-1]))))
    if bg < 128:
        gray = ImageOps.invert(gray)
        a = 255 - a
        bg = 255 - bg
    threshold = max(15, min(45, (bg - float(np.percentile(a,2))) * .22))
    ys, xs = np.nonzero(a < bg - threshold)
    if not len(xs): return gray
    x0, x1, y0, y1 = int(xs.min()), int(xs.max())+1, int(ys.min()), int(ys.max())+1
    if y1-y0 < 3 or x1-x0 < 3: return gray
    pad = max(2, math.ceil((y1-y0)*.12))
    cropped = gray.crop((max(0,x0-pad),max(0,y0-pad),min(gray.width,x1+pad),min(gray.height,y1+pad)))
    return ImageOps.expand(cropped,border=max(2,pad//2),fill=255)

def self_test():
    assert normalize('1 234,56') == '1234,56'
    assert normalize('1\u202f234.56') == '1234,56'
    for bad in ('12 34,56','1234','1234,5','1234,567','1,234.56','ИТОГО 1234,56','-1234,56','1O99,10'):
        assert normalize(bad) is None
    im=Image.new('L',(400,100),255)
    ImageDraw.Draw(im).rectangle((30,20,160,65),fill=0)
    out=trim(im)
    assert out.width<250 and out.height<100
    assert np.count_nonzero(np.asarray(out)==0)==131*46
    assert trim(Image.new('L',(100,50),255)).size==(100,50)
    print('PASS: amount syntax and margin crop tests')
if __name__=='__main__': self_test()
