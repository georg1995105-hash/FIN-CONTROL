"""Experimental document structure parsing. Outputs candidates, never an audit.
Do not infer or correct a digit from the arithmetic or ground truth.
"""
from collections import Counter
from dataclasses import dataclass
import math
import re
from total_candidate import Line, good, cleaned
from ocr_preprocess import normalize

# Explicit final-total labels, not generic 'sum', tax subtotal or payment amount.
LABEL = r'(?:ИТОГО(?: К ОПЛАТЕ)?|ИТОГ|ИТОГОВАЯ СУММА|ВСЕГО(?: К ОПЛАТЕ)?|К ОПЛАТЕ|СУММА К ОПЛАТЕ|ОБЩАЯ СУММА)'
MONEY = r'(?:[0-9]{1,7}|[0-9]{1,3}(?: [0-9]{3}){1,2})[,.][0-9]{2}'
FINAL = re.compile(r'^('+LABEL+r')\s*[:=]?\s*('+MONEY+r')\s*(?:₽|РУБ\.?|Р\.)?$')
LABEL_PREFIX = re.compile(r'^'+LABEL+r'(?=\s|[:=]|[0-9]|$)')
# Explicitly exclude total-tax, total-items, and payment-specific rows.
OTHER = re.compile(r'^(?:(?:ИТОГО|ВСЕГО|ИТОГ)\s+(?:НДС|НАЛОГ|ПОЗИЦИЙ|ТОВАРОВ|СКИДОК|СКИДКА|БЕЗ|С НДС|НАЛИЧНЫМИ|БЕЗНАЛИЧНЫМИ)|(?:НДС|НАЛОГ|СКИДКА|СДАЧА|НАЛИЧНЫМИ|БЕЗНАЛИЧНЫМИ|ОПЛАТА|ПОЛУЧЕНО|ПОДЫТОГ|ПРЕДОПЛАТА)(?:\b|:))')
# Normalize visual Latin lookalikes in labels ONLY, never amounts.
LABEL_CHARS = str.maketrans('ABCEHKMOPTXY','АВСЕНКМОРТХУ')

@dataclass(frozen=True)
class Candidate:
    amount: str | None
    reason: str
    label_count: int
    explicit_labels: int

def valid_box(l):
    try:
        x,y,X,Y=l.box
        return all(math.isfinite(t) for t in l.box) and X>x and Y>y
    except (ValueError,TypeError):return False

def same_row(a,b):
    x,y,X,Y=a.box;u,v,U,V=b.box
    h=Y-y;k=V-v
    return (min(Y,V)-max(y,v)>=.60*min(h,k) and
            abs((Y+y)-(V+v))/2<=.48*max(h,k))

def rows(lines):
    # Group by anchor and all members, rather than chaining adjacent rows.
    groups=[]
    for l in sorted((l for l in lines if valid_box(l) and l.text.strip()),key=lambda l:((l.box[1]+l.box[3])/2,l.box[0])):
        matches=[g for g in groups if all(same_row(l,m) for m in g)]
        if len(matches)==1:matches[0].append(l)
        else:groups.append([l])
    return [sorted(g,key=lambda l:l.box[0]) for g in groups]

def row_text(group):
    if any(b.box[0]<a.box[2]-.2*min(a.box[3]-a.box[1],b.box[3]-b.box[1]) for a,b in zip(group,group[1:])):return None
    chunks=[cleaned(l.text) for l in group]
    # Only join close numeric fragments for explicit thousands grouping.
    # A wide gap between two independent numbers is not a thousands separator.
    for a,b,left,right in zip(group,group[1:],chunks,chunks[1:]):
        if re.search(r'\d$',left) and re.match(r'\d',right):
            gap=b.box[0]-a.box[2]
            if gap>.75*min(a.box[3]-a.box[1],b.box[3]-b.box[1]):
                return None
    return ' '.join(chunks).translate(LABEL_CHARS)

def analyze(lines):
    if not lines:return Candidate(None,'no_text',0,0)
    found=[]; n=0; explicit=0; bad=0
    for group in rows(lines):
        text=row_text(group)
        # Keep ambiguous label evidence even when a row cannot be joined.
        raw=' '.join(cleaned(l.text) for l in group).translate(LABEL_CHARS)
        if OTHER.match(raw):continue
        if not LABEL_PREFIX.match(raw):continue
        n+=1
        m=FINAL.fullmatch(text or '')
        if not m:
            bad+=1;continue
        explicit+=1
        amount=normalize(m.group(2))
        if amount is None or not all(good(l) for l in group):
            bad+=1;continue
        found.append(amount)
    if n==0:return Candidate(None,'no_total_label',n,explicit)
    if n!=1:return Candidate(None,'multiple_total_labels',n,explicit)
    if bad or len(found)!=1:return Candidate(None,'unresolved_total',n,explicit)
    return Candidate(found[0],'candidate',n,explicit)

def self_test():
    def l(s,x=0,y=0,w=100,h=20,c=.99):return Line(s,c,(x,y,x+w,y+h))
    cases=[
        ([l('ИТОГО 120,50')],'120,50'),
        ([l('Итог: =120.50')],None),
        ([l('ИТОГО=120.50')],'120,50'),
        ([l('ИТОГОВАЯ СУММА'),l('120,50',300)],'120,50'),
        ([l('ВСЕГО'),l('К ОПЛАТЕ',120),l('123,45',300)],'123,45'),
        ([l('СУММА'),l('К'),l('ОПЛАТЕ',210),l('123,45',400)],None),
        ([l('СУММА'),l('К',110),l('ОПЛАТЕ',145),l('123,45',400)],'123,45'),
        ([l('ИТОГО'),l('123,45',300,40)],None),
        ([l('ИТОГО'),l('123,45',150),l('234,56',300)],None),
        ([l('ИТОГО 123,45'),l('ИТОГО 123,45',0,40)],None),
        ([l('ИТОГО 123,45'),l('ИТОГО',0,40)],None),
        ([l('ИТОГО 123,45'),l('ВСЕГО НДС 22,00',0,40)],'123,45'),
        ([l('ИТОГО НДС 123,45')],None),
        ([l('ИТОГО'),l('123,45',300,c=.84)],None),
        ([l('ИТОГО',c=.84),l('123,45',300)],None),
        ([l('ОПЛАТА КАРТОЙ 123,45')],None),
        ([l('ИТОГО 1O9,10')],None),
        ([l('ИТОГО 1 234,56 ₽')],'1234,56'),
        ([l('ИТОГО'),l('1',150,w=12),l('234,56',400)],None),
        ([l('ИТОГО'),l('1',150,w=12),l('234,56',166)],'1234,56'),
        ([l('ИТОГО 120,50'),l('СКИДКА 1,00',0,40)],'120,50'),
        ([l('ИТОГО 120,5')],None),
        ([l('ИТОГО 120,50',c=float('nan'))],None),
        ([l('ИТОГО 120,50'),l('ИТОГО 999,99',0,40,c=.1)],None),
        ([l('ИTOГO 120,50')],'120,50'),
        ([l('ИТОГО -120,50')],None),
    ]
    for i,(lines,expected) in enumerate(cases):
        actual=analyze(lines).amount
        assert actual==expected,f'case {i+1}: {actual!r} != {expected!r}'
    print(f'PASS: {len(cases)} structure cases')

if __name__=='__main__':self_test()
