"""Independent whole-page OCR evidence. No guessed digits or target annotations.
Both layout modes are one OCR family; independent Paddle evidence is required.
Only experimental total candidates are returned, never a financial verdict.
"""
from dataclasses import dataclass
import math
from collections import Counter
from total_candidate import Line
from total_row_evidence import group_rows,parse,START,OTHER,NONFINAL,norm_text,high,observed_amount
from semantic_ranker import choose
from semantic_ranker_v2 import evidence

@dataclass(frozen=True)
class PageTotal:
    value:str
    label:str
    row_box:tuple
    money_box:tuple
    score:float

def overlap_fraction(a,b):
    x,y,X,Y=a;u,v,U,V=b
    area=max(0.,min(X,U)-max(x,u))*max(0.,min(Y,V)-max(y,v))
    small=min((X-x)*(Y-y),(U-u)*(V-v))
    return area/small if small>0 else 0.

def same_field(a,b):
    # Amount location, not equal amounts elsewhere on the page.
    x,y,X,Y=a;u,v,U,V=b
    h=Y-y;k=V-v
    return (min(h,k)>0 and overlap_fraction(a,b)>=.65
            and abs((y+Y-v-V)/2)<=.45*max(h,k))

def page_totals(words):
    lines,groups=group_rows(words)
    found=[];bad=0;stats=Counter()
    for row in groups:
        t=norm_text(row.text)
        if OTHER.match(t) or NONFINAL.match(t):continue
        parsed=parse(t)
        if not parsed:
            if START.match(t):
                bad+=1;stats['unparsed_explicit']+=1
            continue
        stats['parsed_explicit']+=1
        a=observed_amount(lines,row)
        if (not row.safe or a is None or a[0]!=parsed[1] or
            not all(high(lines[i].score) for i in row.indices)):
            bad+=1;stats['weak_or_ambiguous']+=1;continue
        found.append(PageTotal(a[0],parsed[0],row.box,lines[a[1]].box,
                               min(lines[i].score for i in row.indices)))
    if bad:return [],'unresolved_page_label',stats
    if not found:return [],'no_page_total',stats
    if len({p.value for p in found})!=1:return [],'conflicting_page_totals',stats
    return found,'page_candidate',stats

def corroborate(a,b):
    if not a or not b:return []
    if {p.value for p in a}!={p.value for p in b}:return []
    # Every explicit total must be located in both modes, not just one
    # matching duplicate elsewhere. Exact label text is also required.
    def match(p,q):return p.value==q.value and p.label==q.label and same_field(p.money_box,q.money_box)
    if any(not any(match(p,q) for q in b) for p in a):return []
    if any(not any(match(p,q) for p in a) for q in b):return []
    return a

def cross_validate(lines,obs,scores,totals):
    if not totals:return None,'no_page_evidence'
    values={p.value for p in totals}
    if len(values)!=1:return None,'conflicting_page_values'
    value=next(iter(values))
    ranked=choose(obs,scores,threshold=.85,margin=.15,require_ocr=True)
    if ranked!=value:return None,'unchanged_rank_gate'
    original,labels,links,_=evidence(lines)
    if len(original)!=len(lines):return None,'line_index_mismatch'
    # Existing explicit evidence is a veto, not silently replaced.
    if any(v!=value for v,j in links.values()):return None,'original_conflict'
    for i,l in labels:
        if i in links:continue
        # Resolve uncertain explicit label only by independently read
        # complete row at its own position.
        if not any(same_field(l.box,p.row_box) for p in totals):
            return None,'unresolved_original_label'
    for p in totals:
        matching=[c for c,s in zip(obs,scores)
                  if c.amount==value and high(c.score) and high(float(s))
                  and same_field(lines[c.line].box,p.money_box)]
        if len({c.line for c in matching})!=1:return None,'no_unique_spatial_amount'
    return value,'candidate'

def self_test():
    from semantic_ranker_v2 import enriched
    def l(t,x=0,y=0,w=100,c=.98):return Line(t,c,(x,y,x+w,y+20))
    words=[l('ИТОГО'),l('123,45',220),l('ОПЛАТА',0,50),l('123,45',220,50)]
    a,reason,_=page_totals(words)
    assert reason=='page_candidate' and len(a)==1 and a[0].value=='123,45'
    assert corroborate(a,a)==a
    shifted=[PageTotal('123,45','ИТОГО',(0,50,320,70),(220,50,320,70),.98)]
    assert not corroborate(a,shifted)
    assert not page_totals([l('ИТОГО'),l('123,45',220,c=.84)])[0]
    assert not page_totals([l('ИТОГО'),l('123,45',220),l('ИТОГО',0,50),l('456,78',220,50)])[0]
    assert not page_totals([l('НДС'),l('123,45',220)])[0]
    assert not page_totals([l('ИТОГО'),l('123,45',220),l('456,78',400)])[0]
    original=[l('ИТОГ0',c=.6),l('123,45',220)]
    obs=enriched(original)
    assert cross_validate(original,obs,[.96],a)[0]=='123,45'
    assert cross_validate(original,obs,[.84],a)[0] is None
    original=[l('ОПЛАТА 123,45',0,50,w=320)]
    obs=enriched(original)
    assert cross_validate(original,obs,[.98],a)[0] is None
    original=[l('ИТОГО 456,78',0,50,w=320),l('123,45',220)]
    obs=enriched(original)
    scores=[.1 if c.amount=='456,78' else .98 for c in obs]
    assert cross_validate(original,obs,scores,a)[0] is None
    print('PASS: whole-page explicit labels, spatial corroboration, confidence and conflicting values')
if __name__=='__main__':self_test()
