"""Compact learned semantic ranking of observed monetary spans.

No amount magnitude, arithmetic, annotated box, expected answer or receipt ID
enters inference. OCR confidence and model ranking score are separate signals.
A suggested value is never a confirmed financial result.
"""
from dataclasses import dataclass
import math
import re
from collections import Counter
from ocr_preprocess import normalize
from total_candidate import Line,cleaned,good
from document_structure import valid_box,LABEL_CHARS

MONEY=r'(?:[0-9]{1,3}(?: [0-9]{3}){1,2}|[0-9]{1,7})[,.][0-9]{2}'
SPAN=re.compile(r'(?<![\w,.+\-])('+MONEY+r')(?![\w,.])')
# Explicit semantic signals supplement hashed context, not selection rules.
ROLES={
    'total':r'\b(?:ИТОГО|ИТОГ|ИТОГОВАЯ|ВСЕГО|К ОПЛАТЕ|ОБЩАЯ СУММА)\b',
    'payment':r'\b(?:ОПЛАТА|КАРТОЙ|НАЛИЧНЫМИ|БЕЗНАЛИЧНЫМИ|ПОЛУЧЕНО)\b',
    'change':r'\b(?:СДАЧА|ВОЗВРАТ)\b',
    'tax':r'\b(?:НДС|НАЛОГ)\b',
    'discount':r'\b(?:СКИДКА|СКИДОК|БОНУСЫ)\b',
    'subtotal':r'\b(?:ПОДЫТОГ|ПРОМЕЖУТОЧНЫЙ|ПРЕДОПЛАТА)\b',
    'quantity':r'\b(?:КОЛИЧЕСТВО|КОЛ-ВО|ШТ|КГ|ПОЗИЦИЙ)\b',
    'price':r'\b(?:ЦЕНА|СТОИМОСТЬ)\b',
}
ROLE_PATTERNS={k:re.compile(v) for k,v in ROLES.items()}
@dataclass(frozen=True)
class Observed:
    amount:str
    line:int
    score:float
    features:dict

def spans(text):
    text=cleaned(text)
    return [(m.start(1),m.end(1),normalize(m.group(1))) for m in SPAN.finditer(text) if normalize(m.group(1)) is not None]

def sanitized(text):
    # No numeric value or identifying token is explicitly provided as a feature.
    # FeatureHasher emits only numeric vectors; no text/vocabulary is saved.
    return re.sub(r'\d+','#',cleaned(text).translate(LABEL_CHARS))[:128]

def add_context(features,prefix,text):
    t=sanitized(text)
    for role,p in ROLE_PATTERNS.items():
        if p.search(t):features[prefix+'role:'+role]=1.
    for n in (2,3):
        for j in range(max(0,len(t)-n+1)):
            part=t[j:j+n]
            if any(c.isalpha() for c in part):features[prefix+'gram:'+part]=1.

def candidates(lines):
    lines=[l for l in lines if valid_box(l) and l.text.strip()]
    if not lines:return []
    x0=min(l.box[0] for l in lines);y0=min(l.box[1] for l in lines)
    width=max(1.,max(l.box[2] for l in lines)-x0)
    height=max(1.,max(l.box[3] for l in lines)-y0)
    occurrences=Counter(a for l in lines for _,_,a in spans(l.text))
    result=[]
    for i,l in enumerate(lines):
        text=cleaned(l.text)
        money=spans(text)
        if not money:continue
        x,y,X,Y=l.box
        cx=(x+X)/2;cy=(y+Y)/2;h=Y-y
        right=[];left=[];above=[];below=[]
        for j,m in enumerate(lines):
            if j==i:continue
            u,v,U,V=m.box
            delta=((v+V)/2-cy)/max(h,V-v)
            if abs(delta)<=.8:
                if U<=x+.15*h:left.append((max(0.,x-U),j,m))
                if u>=X-.15*h:right.append((max(0.,u-X),j,m))
            if -.8>delta>=-5:above.append((abs(delta)+.2*abs((u+U)/2-cx)/width,j,m))
            if .8<delta<=5:below.append((abs(delta)+.2*abs((u+U)/2-cx)/width,j,m))
        for index,(a,b,amount) in enumerate(money):
            f={'geom:x':(x-x0)/width,'geom:y':(cy-y0)/height,
               'geom:right':(X-x0)/width,'geom:width':(X-x)/width,
               'geom:height':h/height,'geom:ocr':float(l.score) if math.isfinite(l.score) else 0.,
               'geom:spanpos':a/max(1,len(text)),'geom:spanend':b/max(1,len(text)),
               'geom:numspans':min(8,len(money))/8,
               'geom:spanindex':index/max(1,len(money)-1),
               'geom:repeats':min(8,occurrences[amount])/8}
            add_context(f,'own:',text[:a]+' @ '+text[b:])
            add_context(f,'prefix:',text[:a])
            add_context(f,'suffix:',text[b:])
            for direction,neighbors in [('left',left),('right',right),('above',above),('below',below)]:
                for k,(dist,_,neighbor) in enumerate(sorted(neighbors,key=lambda n:(n[0],n[1]))[:2]):
                    tag=direction+str(k)+':'
                    add_context(f,tag,neighbor.text)
                    f[tag+'distance']=min(10.,dist/max(1.,width) if direction in ('left','right') else dist)/10.
                    f[tag+'confidence']=float(neighbor.score) if math.isfinite(neighbor.score) else 0.
            result.append(Observed(amount,i,l.score,f))
    return result

def choose(observed,scores,threshold=.85,margin=.15,require_ocr=True):
    """Rank distinct observed values. Ties/low score -> unresolved.
    Ranker score is not calibrated probability; thresholds are experimental.
    """
    if len(observed)!=len(scores):raise ValueError('score count mismatch')
    by_amount={}
    for c,s in zip(observed,scores):
        s=float(s)
        if not math.isfinite(s) or not 0<=s<=1:continue
        previous=by_amount.get(c.amount)
        if previous is None or s>previous[0] or (s==previous[0] and c.score>previous[1].score):
            by_amount[c.amount]=(s,c)
    ranked=sorted(by_amount.values(),key=lambda p:p[0],reverse=True)
    if not ranked:return None
    score,c=ranked[0]
    if score<threshold:return None
    if len(ranked)>1 and score-ranked[1][0]<margin:return None
    if require_ocr and (not math.isfinite(c.score) or not .85<=c.score<=1):return None
    return c.amount

def self_test():
    def l(s,x=0,y=0,w=100,h=20,c=.98):return Line(s,c,(x,y,x+w,y+h))
    assert [a for _,_,a in spans('ИТОГО 1 234,56 ₽')]==['1234,56']
    assert [a for _,_,a in spans('1234,567')]==[]
    assert spans('ABC123,45')==[]
    assert spans('-123,45')==[]
    assert spans('12.03.2025')==[]
    assert spans('ИТОГО 123,45 / 456,78')[-1][2]=='456,78'
    a=candidates([l('ИТОГО'),l('123,45',200),l('НДС 20,00',0,40)])
    assert len(a)==2
    assert 'left0:role:total' in a[0].features
    assert choose(a,[.96,.12])=='123,45'
    assert choose(a,[.96,.90]) is None
    assert choose(a,[.84,.1]) is None
    assert choose(a,[.96,float('nan')])=='123,45'
    assert choose(a,[.96,.12],require_ocr=True)=='123,45'
    weak=candidates([l('ИТОГО 123,45',c=.84)])
    assert choose(weak,[.99]) is None
    repeat=candidates([l('ИТОГО 123,45'),l('ОПЛАТА 123,45',0,40)])
    assert choose(repeat,[.95,.94])=='123,45'
    changed=candidates([l('ИТОГО 321,54')])
    original=candidates([l('ИТОГО 123,45')])
    assert changed[0].features==original[0].features
    assert candidates([])==[]
    print('PASS: observed span extraction, geometry, amount-blind features, abstention and conflicts')
if __name__=='__main__':self_test()
