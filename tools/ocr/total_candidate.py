"""Strict candidate extraction, not a financial conclusion.
Coordinates are pixels of the same rectified document. Confidence is uncalibrated.
"""
from dataclasses import dataclass
import math
import re
from ocr_preprocess import normalize

LABEL = r'(?:ИТОГО К ОПЛАТЕ|ВСЕГО К ОПЛАТЕ|ИТОГО|К ОПЛАТЕ|ВСЕГО)'
AMOUNT = r'(?:[0-9]{1,7}|[0-9]{1,3}(?: [0-9]{3}){1,2})[,.][0-9]{2}'
COMBINED = re.compile(r'^'+LABEL+r'\s*[:=]?\s*('+AMOUNT+r')(?:\s*(?:₽|РУБ\.?))?$')
LABEL_ONLY = re.compile(r'^'+LABEL+r'\s*[:=]?$')
THRESHOLD = .85

@dataclass(frozen=True)
class Line:
    text: str
    score: float
    box: tuple

def cleaned(s):
    return ' '.join(s.upper().replace('Ё','Е').split())

def good(line):
    return math.isfinite(line.score) and line.score >= THRESHOLD

def aligned(a,b):
    x,y,X,Y=a.box; u,v,U,V=b.box
    h=Y-y; k=V-v
    if min(h,k)<=0 or u<X-0.2*max(h,k):return False
    return min(Y,V)-max(y,v)>=.65*min(h,k) and abs((y+Y)-(v+V))/2<=.55*max(h,k)

def extract(lines):
    """Require exactly one unambiguous total label/amount association.
    Other monetary fields, taxes, discounts and completeness remain unverified.
    """
    candidates=[]; labels=0; uncertain=0
    for a in lines:
        text=cleaned(a.text)
        m=COMBINED.fullmatch(text)
        if m:
            labels+=1
            if good(a): candidates.append(normalize(m.group(1)))
            else: uncertain+=1
        elif LABEL_ONLY.fullmatch(text):
            labels+=1
            matching=[b for b in lines if a is not b and aligned(a,b) and normalize(cleaned(b.text)) is not None]
            if len(matching)==1 and good(a) and good(matching[0]):candidates.append(normalize(cleaned(matching[0].text)))
            else:uncertain+=1
    if labels==1 and len(candidates)==1 and not uncertain:return candidates[0]
    return None

def self_test():
    def line(s,x=0,y=0,w=100,h=20,c=.99): return Line(s,c,(x,y,x+w,y+h))
    cases=[
        ([line('ИТОГО 120,50')],'120,50'),
        ([line('Итого: 1 234,56 ₽')],'1234,56'),
        ([line('Всего к оплате'),line('123,45',150)],'123,45'),
        ([line('ИТОГО'),line('123,45',150,40)],None),
        ([line('ИТОГО'),line('123,45',150),line('234,56',280)],None),
        ([line('ИТОГО 123,45'),line('ИТОГО 123,45',0,40)],None),
        ([line('ИТОГО 123,45',c=.84)],None),
        ([line('ИТОГО'),line('123,45',150,c=.84)],None),
        ([line('ИТОГО'),line('123,45',150),line('ИТОГО',0,40)],None),
        ([line('НДС 20,00'),line('НАЛИЧНЫМИ 500,00')],None),
        ([line('ИТОГО 123,4')],None),
        ([line('ИТОГО 12O,50')],None),
        ([line('ИТОГО 123,45'),line('СКИДКА 5,00',0,30)],'123,45'),
    ]
    for lines,expected in cases:assert extract(lines)==expected
    print('PASS: 13 total candidate association cases')
if __name__=='__main__':self_test()
