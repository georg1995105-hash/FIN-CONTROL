"""Multi-model evidence for explicit totals. Research only.
No arithmetic correction; digits and decimal separator must be observed.
Confidence is not calibrated probability. Low confidence text is retained
as ambiguity rather than silently removed.
"""
import math
import re
from collections import Counter
from total_candidate import Line, cleaned, good
from document_structure import LABEL, MONEY, LABEL_CHARS, OTHER, valid_box
from layout_diagnostics import anchor_candidate, geometry
from ocr_preprocess import normalize

LABEL_RE=re.compile(r'^('+LABEL+r')\s*[:=]?$')
TOTAL_RE=re.compile(r'^('+LABEL+r')\s*[:=]?\s*('+MONEY+r')\s*(?:₽|РУБ\.?|Р\.)?$')
AMOUNT_RE=re.compile(r'^=?\s*('+MONEY+r')\s*(?:₽|РУБ\.?|Р\.)?$')

def key(text):
    text=cleaned(text).translate(LABEL_CHARS)
    if OTHER.match(text):return None
    m=TOTAL_RE.fullmatch(text)
    if m:return ('total',m.group(1),normalize(m.group(2)))
    m=LABEL_RE.fullmatch(text)
    if m:return ('label',m.group(1))
    m=AMOUNT_RE.fullmatch(text)
    if m:return ('amount',normalize(m.group(1)))
    return None

def text_for(k):
    if k[0]=='total':return k[1]+' '+k[2]
    return k[1]

def confidence(score):
    return math.isfinite(score) and .85<=score<=1.

def resolve(primary, reread, secondary, tesseract, require_tesseract=False):
    """v5 original and reread count as one model; v3 and Tesseract are distinct.
    All supporting votes must independently meet their unchanged threshold.
    A conflicting high-confidence semantic reading vetoes confirmation.
    """
    inputs={'v5':[primary,reread],'v3':[secondary],'tess':[tesseract]}
    votes={}
    for engine,readings in inputs.items():
        qualified=[(key(t),s) for t,s in readings if confidence(s) and key(t) is not None]
        keys={k for k,s in qualified}
        if len(keys)>1:return None
        if qualified:votes[engine]=max(qualified,key=lambda x:x[1])
    counts=Counter(k for k,s in votes.values())
    if len(counts)!=1:return None
    k,n=counts.most_common(1)[0]
    if n<2 or (require_tesseract and 'tess' not in votes):return None
    # Don't turn a confidently read unrelated word into a financial label.
    if confidence(primary[1]) and key(primary[0])!=k:return None
    return text_for(k),min(s for _,s in votes.values())

def selected_indices(lines):
    # Candidate selection only, never confirmation. Read explicit total labels
    # first, then a bounded number of short uncertain textual fragments.
    anchors=[]; weak=[]
    for i,l in enumerate(lines):
        if not valid_box(l):continue
        k=key(l.text)
        if k and k[0] in ('total','label'):anchors.append(i);continue
        t=cleaned(l.text)
        if not good(l) and 2<=len(t)<=32 and sum(c.isalpha() for c in t)>=2 and not OTHER.match(t):
            weak.append(i)
    labels=anchors+sorted(weak,key=lambda i:(len(lines[i].text),i))[:8]
    # No unverified amount is promoted merely because it is numerically plausible.
    money=[]
    for j,l in enumerate(lines):
        k=key(l.text)
        if not k or k[0]!='amount' or not valid_box(l):continue
        if any(geometry(lines[i],l)[0]>=-.15 and abs(geometry(lines[i],l)[1])<=.70 for i in labels):
            money.append(j)
    return sorted(set(labels+money))

def refined_lines(lines,reads,require_tesseract=False):
    result=[]
    for i,line in enumerate(lines):
        original=(line.text,line.score)
        if i in reads:
            vote=resolve(original,*reads[i],require_tesseract=require_tesseract)
            if vote:
                result.append(Line(vote[0],vote[1],line.box));continue
        # Keep conflicting labels/numbers visible to the parser, but do not
        # permit uncorroborated semantic evidence to be selected.
        result.append(Line(line.text,0.0 if key(line.text) is not None else line.score,line.box))
    return result

def self_test():
    low=('ИТОГО',.6); hi=('ИТОГО',.96); no=('',0.)
    assert resolve(low,hi,hi,no)==('ИТОГО',.96)
    assert resolve(low,hi,hi,no,True) is None
    assert resolve(low,hi,no,hi,True)==('ИТОГО',.96)
    assert resolve(hi,hi,no,no) is None
    assert resolve(hi,hi,('К ОПЛАТЕ',.96),hi) is None
    assert resolve(('ТЕЛЕФОН',.96),hi,hi,hi) is None
    assert resolve(('ТЕЛЕФОН',.5),hi,hi,hi)==('ИТОГО',.96)
    assert resolve(('120,50',.96),('120,50',.96),('120,51',.97),('120,50',.96)) is None
    assert resolve(('120,50',.7),('120.50',.96),('120,50',.95),no)==('120,50',.95)
    assert resolve(low,('ИТОГО',.84),hi,no) is None
    assert key('ИТОГО НДС 120,50') is None
    assert key('ИТОГО 1O0,00') is None
    assert key('ИТОГО 123,4') is None
    assert key('123,456') is None
    assert key('ИТОГО 1 234,56 ₽')==('total','ИТОГО','1234,56')
    assert key('=123,45')==('amount','123,45')
    lines=[Line('ИТОГО',.60,(0,0,100,20)),Line('120,50',.96,(200,0,290,20))]
    assert selected_indices(lines)==[0,1]
    assert anchor_candidate(refined_lines(lines,{})) is None
    reads={0:(hi,hi,hi),1:(('120,50',.96),('120,50',.96),('120,50',.96))}
    assert anchor_candidate(refined_lines(lines,reads,True))=='120,50'
    conflict=lines+[Line('ИТОГО 999,99',.65,(0,50,180,70))]
    assert anchor_candidate(refined_lines(conflict,reads,True)) is None
    print('PASS: 20 multi-reader evidence assertions')
if __name__=='__main__':self_test()
