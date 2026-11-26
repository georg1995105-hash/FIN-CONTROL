"""Semantic ranking v2: explicit evidence, synthetic missing/conflicting totals.
No target values or arithmetic at inference. Output remains an OCR candidate.
"""
from dataclasses import replace
from collections import Counter
import math
import random
import re
from total_candidate import Line,cleaned
from document_structure import LABEL,LABEL_CHARS,OTHER,valid_box
from semantic_ranker import candidates,spans,choose
from ocr_preprocess import normalize

# Recognize explicit labels independently from OCR confidence: uncertain labels
# may guide suggestions but cannot be treated as verified transcription.
PREFIX=re.compile(r'^('+LABEL+r')(?=$|[\s:=0-9])')
NONFINAL=re.compile(r'^(?:НАЛИЧНЫМИ|БЕЗНАЛИЧНЫМИ|ОПЛАТА|СДАЧА|СКИДКА|НДС|НАЛОГ|ПОДЫТОГ|ПРЕДОПЛАТА|ПОЛУЧЕНО|ЦЕНА|КОЛИЧЕСТВО)(?:$|[\s:=0-9])')
LABEL_ONLY=re.compile(r'^'+LABEL+r'\s*[:=]?$')
MONEY=r'(?:[0-9]{1,3}(?: [0-9]{3}){1,2}|[0-9]{1,7})[,.][0-9]{2}'
SINGLE=re.compile(r'^(?:=\s*)?('+MONEY+r')\s*(?:₽|РУБ\.?|Р\.)?$')
COMBINED=re.compile(r'^'+LABEL+r'\s*[:=]?\s*('+MONEY+r')\s*(?:₽|РУБ\.?|Р\.)?$')

def text(l):return cleaned(l.text).translate(LABEL_CHARS)
def clean_lines(lines):return [l for l in lines if valid_box(l) and l.text.strip()]
def role(l):
    t=text(l)
    if OTHER.match(t) or NONFINAL.match(t):return 'other'
    if PREFIX.match(t):return 'total'
    return 'unknown'
def near(a,b):
    x,y,X,Y=a.box;u,v,U,V=b.box
    h=max(Y-y,V-v)
    return u>=X-.15*h and abs((v+V-y-Y)/(2*h))<=.65
def exact(l,pattern):
    m=pattern.fullmatch(text(l))
    return normalize(m.group(1)) if m else None

def evidence(lines):
    """Candidate-linked observed explicit labels. No inference from the value.
    Multiple conflicting explicit values, unparsed labels or ambiguous same-row
    amounts veto the protected candidate, even if a classifier ranks it first.
    """
    lines=clean_lines(lines)
    labels=[(i,l) for i,l in enumerate(lines) if role(l)=='total']
    links={}; unresolved=0
    for i,l in labels:
        value=exact(l,COMBINED)
        if value is not None:
            competing=[m for j,m in enumerate(lines) if j!=i and near(l,m) and spans(m.text)]
            if competing:unresolved+=1;continue
            links[i]=(value,i);continue
        if not LABEL_ONLY.fullmatch(text(l)):
            unresolved+=1;continue
        right=[(j,m) for j,m in enumerate(lines) if j!=i and near(l,m)]
        money=[(j,m,exact(m,SINGLE)) for j,m in right if spans(m.text)]
        if len(money)!=1 or money[0][2] is None:
            unresolved+=1;continue
        j,m,value=money[0]
        if any(k!=j and q.box[0]<m.box[2] and q.box[2]>l.box[2] for k,q in right):
            unresolved+=1;continue
        links[i]=(value,j)
    return lines,labels,links,unresolved

def enriched(lines):
    lines,labels,links,unresolved=evidence(lines)
    observed=candidates(lines)
    linked={(value,index) for value,index in links.values()}
    result=[]
    for c in observed:
        f=dict(c.features)
        f['v2:direct_total']=float(role(lines[c.line])=='total')
        f['v2:direct_nonfinal']=float(role(lines[c.line])=='other')
        f['v2:explicit_link']=float((c.amount,c.line) in linked)
        f['v2:label_count']=min(len(labels),4)/4
        f['v2:unresolved_labels']=min(unresolved,4)/4
        f['v2:distinct_linked_values']=min(len({v for v,_ in links.values()}),4)/4
        f['v2:money_lines']=min(40,len({a.line for a in observed}))/40
        result.append(replace(c,features=f))
    return result

def protected(lines,observed,scores):
    # Preserve the original candidate thresholds. This is a stricter research
    # candidate, NOT a confirmed financial result; label OCR may be uncertain.
    value=choose(observed,scores,threshold=.85,margin=.15,require_ocr=True)
    if value is None:return None
    _,labels,links,unresolved=evidence(lines)
    if not labels or unresolved or len({v for v,_ in links.values()})!=1:return None
    if value!=next(iter(links.values()))[0]:return None
    indices={i for v,i in links.values() if v==value}
    if not any(c.amount==value and c.line in indices and math.isfinite(c.score) and .85<=c.score<=1
               and math.isfinite(float(s)) and .85<=float(s)<=1 for c,s in zip(observed,scores)):return None
    return value

def synthetic_docs(seed,count):
    """Distinct training documents at structured OCR level; no receipt pixels.
    Balanced ordinary, missing, conflicting and payment-only examples.
    Evaluation uses separate image fixtures and a different synthetic seed.
    """
    rng=random.Random(seed)
    names=['ХЛЕБ','МОЛОКО','КОФЕ','СЫР','ТОМАТЫ','ЧАЙ','ВОДА','КРУПА','ЯБЛОКИ','СОК']
    labels=['ИТОГО','ВСЕГО К ОПЛАТЕ','СУММА К ОПЛАТЕ','ИТОГОВАЯ СУММА','К ОПЛАТЕ']
    def amount():return '%d,%02d'%(rng.randrange(10,9500),rng.randrange(100))
    for i in range(count):
        kind=i%6
        expected=amount()
        wrong=amount()
        while wrong==expected:wrong=amount()
        width=rng.randrange(350,800)
        height=rng.randrange(15,30)
        y=0;lines=[]
        def put(label,value=None,combined=False,confidence=None):
            nonlocal y
            conf=confidence if confidence is not None else rng.uniform(.7,1.)
            if combined and value is not None:
                lines.append(Line(label+' '+value,conf,(10,y,width-10,y+height)))
            else:
                lines.append(Line(label,conf,(10,y,min(width*.53,10+max(20,len(label)*height*.48)),y+height)))
                if value is not None:
                    lines.append(Line(value,rng.uniform(.84,1.),(width*.68,y+rng.uniform(-.12,.12)*height,width-10,y+height)))
            y+=height*rng.uniform(1.4,2.4)
        put('КАССОВЫЙ ЧЕК')
        for j in range(rng.randrange(2,8)):
            put(rng.choice(names),expected if j==0 and i%4==0 else amount(),i%7==0)
        if i%3==0:put('СКИДКА',amount())
        if kind in (0,1,2,4):
            put(rng.choice(labels),expected,kind==1)
        if kind==4:put(rng.choice(labels),wrong)
        if kind==5:put('ИТОГО НДС',wrong,True)
        put(rng.choice(['ОПЛАТА КАРТОЙ','НАЛИЧНЫМИ','БЕЗНАЛИЧНЫМИ']),expected)
        if i%4==0:put('СДАЧА',wrong)
        if i%2==0:put('НДС',amount())
        # 0,1,2 valid; 3 missing; 4 conflicting; 5 tax/payment only.
        yield lines,expected if kind in (0,1,2) else None

def self_test():
    def l(s,x=0,y=0,w=100,c=.98):return Line(s,c,(x,y,x+w,y+20))
    lines=[l('ИТОГО',c=.65),l('123,45',200),l('НДС 20,00',0,50)]
    a=enriched(lines)
    assert len(a)==2 and a[0].features['v2:explicit_link']==1
    assert protected(lines,a,[.96,.1])=='123,45'
    assert protected(lines,a,[.96,.88]) is None
    missing=[l('ОПЛАТА КАРТОЙ 123,45')]
    assert protected(missing,enriched(missing),[.99]) is None
    conflict=[l('ИТОГО 123,45'),l('ИТОГО 456,78',0,40)]
    assert protected(conflict,enriched(conflict),[.99,.1]) is None
    ambiguous=[l('ИТОГО'),l('123,45',200),l('456,78',400)]
    assert protected(ambiguous,enriched(ambiguous),[.99,.1]) is None
    weak=[l('ИТОГО 123,45',c=.84)]
    assert protected(weak,enriched(weak),[.99]) is None
    tax=[l('ИТОГО НДС 123,45')]
    assert protected(tax,enriched(tax),[.99]) is None
    repeated=[l('ИТОГО 123,45',c=.98),l('ОПЛАТА 123,45',0,40)]
    assert protected(repeated,enriched(repeated),[.1,.99]) is None
    assert protected(repeated,enriched(repeated),[.99,.98])=='123,45'
    docs=list(synthetic_docs(11,60))
    assert len(docs)==60 and sum(e is None for _,e in docs)==30
    assert all(enriched(lines) for lines,_ in docs)
    print('PASS: 12 v2 evidence and negative-document checks')
if __name__=='__main__':self_test()
