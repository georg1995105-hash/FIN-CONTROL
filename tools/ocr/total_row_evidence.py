"""Row-level evidence for Russian receipt totals.
Never infer digits, substitute a model-generated amount, or use reference labels
at inference. Experimental candidate evidence, not a financial conclusion.
"""
from dataclasses import dataclass
import math
import re
from collections import Counter
from total_candidate import Line,cleaned
from document_structure import LABEL_CHARS,OTHER,valid_box,rows
from semantic_ranker import spans,choose
from semantic_ranker_v2 import evidence,role,protected
from ocr_preprocess import normalize

LABEL=r'(?:ИТОГО К ОПЛАТЕ|ВСЕГО К ОПЛАТЕ|СУММА К ОПЛАТЕ|ИТОГОВАЯ СУММА|ОБЩАЯ СУММА|К ОПЛАТЕ|ИТОГО|ИТОГ|ВСЕГО)'
MONEY=r'(?:[0-9]{1,3}(?: [0-9]{3}){1,2}|[0-9]{1,7})[,.][0-9]{2}'
FINAL=re.compile(r'^('+LABEL+r')\s*(?::\s*)?(?:[=*]\s*)?('+MONEY+r')\s*(?:₽|РУБ\.?|Р\.)?$')
START=re.compile(r'^'+LABEL+r'(?=$|[\s:=*0-9])')
NONFINAL=re.compile(r'^(?:НДС|НАЛОГ|СКИДКА|СДАЧА|ВОЗВРАТ|ОПЛАТА|НАЛИЧНЫМИ|БЕЗНАЛИЧНЫМИ|ПОДЫТОГ|ПРЕДОПЛАТА|ПОЛУЧЕНО|ЦЕНА|КОЛИЧЕСТВО)(?:$|[\s:=*0-9])')
LABEL_WORDS=set('ИТОГО ИТОГ ВСЕГО СУММА ИТОГОВАЯ ОБЩАЯ К ОПЛАТЕ РУБ Р'.split())

def norm_text(s):
    return cleaned(s).translate(LABEL_CHARS)

def parse(s):
    t=norm_text(s)
    if OTHER.match(t) or NONFINAL.match(t):return None
    m=FINAL.fullmatch(t)
    if not m:return None
    amount=normalize(m.group(2))
    return (m.group(1),amount) if amount is not None else None

def high(s):
    return math.isfinite(s) and .85<=s<=1.

@dataclass(frozen=True)
class Row:
    indices:tuple
    text:str
    box:tuple
    safe:bool

def group_rows(lines):
    lines=[l for l in lines if valid_box(l) and l.text.strip()]
    idx={id(l):i for i,l in enumerate(lines)}
    out=[]
    for group in rows(lines):
        safe=True
        for a,b in zip(group,group[1:]):
            if b.box[0]<a.box[2]-.15*min(a.box[3]-a.box[1],b.box[3]-b.box[1]):
                safe=False
        out.append(Row(tuple(idx[id(l)] for l in group),' '.join(cleaned(l.text) for l in group),
                       (min(l.box[0] for l in group),min(l.box[1] for l in group),
                        max(l.box[2] for l in group),max(l.box[3] for l in group)),safe))
    return lines,out

def observed_amount(lines,row):
    """Exactly one amount span, existing in an original OCR fragment."""
    found=[(i,a) for i in row.indices for _,_,a in spans(lines[i].text)]
    if len(found)!=1:return None
    i,a=found[0]
    return (a,i) if high(lines[i].score) else None

def direct(lines,row):
    if not row.safe:return None
    p=parse(row.text)
    a=observed_amount(lines,row)
    if p is None or a is None or p[1]!=a[0]:return None
    # Label fragments may be uncertain: record their original confidence.
    # Money itself must be high-confidence and unmodified.
    return p[1],a[1]

def reread(lines,row,paddle,tess):
    """Require two distinct OCR families to agree on the entire explicit row.
    The original observed amount remains the source of the value.
    """
    if not row.safe:return None
    a=observed_amount(lines,row)
    if a is None:return None
    p,q=parse(paddle[0]),parse(tess[0])
    if not high(paddle[1]) or not high(tess[1]) or p is None or p!=q or p[1]!=a[0]:return None
    if OTHER.match(norm_text(row.text)) or NONFINAL.match(norm_text(row.text)):return None
    for i in row.indices:
        l=lines[i]
        if role(l)=='other':return None
        # Never overwrite a confidently read unrelated word or role.
        if high(l.score):
            words=re.findall(r'[А-ЯA-Z]+',norm_text(l.text))
            if any(w not in LABEL_WORDS for w in words):return None
    return a

def proposals(lines,groups,reads=None):
    reads=reads or {}
    _,labels,old_links,old_unresolved=evidence(lines)
    old_label_ids={i for i,_ in labels}
    links={};unresolved=set();reasons=Counter()
    for k,row in enumerate(groups):
        t=norm_text(row.text)
        # Excluded total-tax rows are not unparsed final-total labels.
        excluded=bool(OTHER.match(t) or NONFINAL.match(t))
        has_label=bool(START.match(t)) and not excluded
        old_ids=old_label_ids.intersection(row.indices)
        a=direct(lines,row)
        if a is None and k in reads:a=reread(lines,row,*reads[k])
        if a is not None:
            links[k]=a
            reasons['direct_row' if direct(lines,row) is not None else 'consensus_row']+=1
        elif (has_label or old_ids) and not excluded:
            unresolved.add(k)
            reasons['unresolved_total_row']+=1
        elif old_ids and excluded:
            # Contradictory old interpretation is not silently discarded.
            unresolved.add(k)
            reasons['conflicting_role']+=1
    # V2 successfully associated a value despite stricter grouping: retain
    # that evidence only if the old label is explicitly resolved and its
    # amount is still linked to the same original line.
    for i,(value,j) in old_links.items():
        owner=next((k for k,r in enumerate(groups) if i in r.indices),None)
        if owner is None:continue
        row=groups[owner]
        if j in row.indices and direct(lines,row)==(value,j):continue
        # Do not silently drop old evidence of a conflicting value.
        if owner in links and links[owner][0]!=value:
            unresolved.add(owner);reasons['old_new_conflict']+=1
        elif owner not in links:
            unresolved.add(owner);reasons['unresolved_old_link']+=1
    return links,unresolved,reasons

def select(lines,groups,obs,scores,reads=None):
    links,bad,reasons=proposals(lines,groups,reads)
    if not links:return None,'no_link',reasons
    if bad:return None,'unresolved_label',reasons
    if len({a for a,i in links.values()})!=1:return None,'conflicting_totals',reasons
    value=choose(obs,scores,threshold=.85,margin=.15,require_ocr=True)
    if value is None:return None,'rank_or_ocr_gate',reasons
    if value!=next(iter(links.values()))[0]:return None,'rank_disagrees',reasons
    ids={i for a,i in links.values() if a==value}
    if not any(c.amount==value and c.line in ids and high(c.score) and high(float(s)) for c,s in zip(obs,scores)):
        return None,'linked_rank_gate',reasons
    return value,'accepted',reasons

def candidates_for_reread(lines,groups,obs,scores,limit=8):
    by_index={}
    for c,s in zip(obs,scores):
        if math.isfinite(float(s)):by_index[c.line]=max(by_index.get(c.line,0),float(s))
    result=[]
    for k,row in enumerate(groups):
        if direct(lines,row) is not None or not row.safe or observed_amount(lines,row) is None:continue
        t=norm_text(row.text)
        if OTHER.match(t) or NONFINAL.match(t):continue
        score=max((by_index.get(i,0) for i in row.indices),default=0)
        if START.match(t) or score>=.5:result.append((bool(START.match(t)),score,k))
    return [k for _,_,k in sorted(result,reverse=True)[:limit]]

def self_test():
    def l(t,x=0,y=0,w=100,c=.98):return Line(t,c,(x,y,x+w,y+20))
    for t in ['ИТОГО 123,45','ИТОГ: =123.45','ИТОГО *123,45','СУММА К ОПЛАТЕ 123,45 РУБ.']:
        assert parse(t)[1]=='123,45',t
    for t in ['ИТОГО НДС 123,45','ОПЛАТА КАРТОЙ 123,45','ИТОГО -123,45','ИТОГО 123,4','ИТОГО 123,45 678,90','ИТОГО 12O,45','ВСЕГО ТОВАРОВ 123,45']:
        assert parse(t) is None,t
    ls,g=group_rows([l('СУММА'),l('К',105,w=15),l('ОПЛАТЕ',125,w=80),l('123,45',250)])
    assert len(g)==1 and direct(ls,g[0])==('123,45',3)
    ls,g=group_rows([l('ИТОГО'),l('123,45',250,c=.84)])
    assert direct(ls,g[0]) is None
    ls,g=group_rows([l('ИТОГО'),l('123,45',250),l('678,90',400)])
    assert direct(ls,g[0]) is None
    ls,g=group_rows([l('ИТОГО'),l('123,45',250,40)])
    assert not any(direct(ls,r) for r in g)
    ls,g=group_rows([l('ИТОГ0',c=.6),l('123,45',250)])
    assert reread(ls,g[0],('ИТОГО 123,45',.96),('ИТОГО 123.45',.95))==('123,45',1)
    assert reread(ls,g[0],('ИТОГО 123,45',.96),('ИТОГО 123.46',.95)) is None
    assert reread(ls,g[0],('ИТОГО 123,45',.96),('ИТОГО 123.45',.84)) is None
    assert reread(ls,g[0],('ИТОГО 123,46',.96),('ИТОГО 123.46',.95)) is None
    ls,g=group_rows([l('МОЛОКО'),l('123,45',250)])
    assert reread(ls,g[0],('ИТОГО 123,45',.96),('ИТОГО 123.45',.95)) is None
    ls,g=group_rows([l('НДС',c=.7),l('123,45',250)])
    assert reread(ls,g[0],('ИТОГО 123,45',.96),('ИТОГО 123.45',.95)) is None
    ls,g=group_rows([l('ИТОГО 123,45'),l('ИТОГО 678,90',y=40)])
    links,bad,_=proposals(ls,g);assert len({a for a,i in links.values()})==2
    from semantic_ranker_v2 import enriched
    ls,g=group_rows([l('ИТОГО'),l('123,45',250),l('НДС 20,00',y=50)])
    obs=enriched(ls);assert select(ls,g,obs,[.96,.1])[0]=='123,45'
    assert select(ls,g,obs,[.96,.9])[0] is None
    ls,g=group_rows([l('ИТОГО'),l('123,45',250),l('ИТОГО',y=50)])
    assert select(ls,g,enriched(ls),[.96])[0] is None
    print('PASS: row grammar, split labels, independent reread, amount preservation and conflict rejection')
if __name__=='__main__':self_test()
