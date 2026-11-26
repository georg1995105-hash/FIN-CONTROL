"""Document-level structural context for observed monetary spans.
Research: no arithmetic, target values, amount magnitude or guessed digits.
The existing protected/row gate remains mandatory.
"""
from collections import Counter
from dataclasses import replace
import math
import re
from statistics import median
from total_candidate import Line
from document_structure import valid_box
from semantic_ranker import spans
from semantic_ranker_v2 import enriched,role,evidence,text
from total_row_evidence import group_rows,START,OTHER,NONFINAL,parse
from semantic_ranker import ROLE_PATTERNS

FOOTER=re.compile(r'\b(?:ФН|ФД|ФП|ФПД|ККТ|РНМ|РЕГИСТРАЦИОННЫЙ|СМЕНА|ИНН|КАССИР|ПРОВЕРКА ЧЕКА)\b')
ITEM=re.compile(r'\b(?:ШТ|КГ|ЦЕНА|КОЛИЧЕСТВО|ТОВАР|ПОЗИЦИЯ)\b')
CURRENCY=re.compile(r'(?:₽|\bРУБ\.?\b)')
def roles(t):
    out={name for name,pattern in ROLE_PATTERNS.items() if pattern.search(t)}
    if FOOTER.search(t):out.add('footer')
    if ITEM.search(t):out.add('item')
    if CURRENCY.search(t):out.add('currency')
    return out

def graph_observations(lines):
    lines,groups=group_rows(lines)
    old=enriched(lines)
    if not old:return []
    centers=[(r.box[1]+r.box[3])/2 for r in groups]
    order=sorted(range(len(groups)),key=lambda k:(centers[k],groups[k].box[0]))
    position={k:i for i,k in enumerate(order)}
    owners={i:k for k,r in enumerate(groups) for i in r.indices}
    heights=[l.box[3]-l.box[1] for l in lines]
    typical=max(1.,median(heights))
    x0=min(l.box[0] for l in lines);width=max(1.,max(l.box[2] for l in lines)-x0)
    by_row=Counter(owners[c.line] for c in old)
    row_roles={k:roles(text(Line(r.text,1.,r.box))) for k,r in enumerate(groups)}
    money_rows=sorted(by_row,key=lambda k:position[k])
    money_pos={k:i for i,k in enumerate(money_rows)}
    result=[]
    for c in old:
        k=owners[c.line];r=groups[k];p=position[k];l=lines[c.line]
        f=dict(c.features)
        f['graph:row_position']=p/max(1,len(groups)-1)
        f['graph:money_row_position']=money_pos[k]/max(1,len(money_rows)-1)
        f['graph:row_money_count']=min(8,by_row[k])/8
        f['graph:row_safe']=float(r.safe)
        f['graph:relative_height']=min(4.,(l.box[3]-l.box[1])/typical)/4
        f['graph:row_width']=min(1.,(r.box[2]-r.box[0])/width)
        same_col=[a for a in old if a.line!=c.line and
                  abs(lines[a.line].box[2]-l.box[2])<=max(.04*width,.5*typical)]
        f['graph:column_above']=min(20,sum(position[owners[a.line]]<p for a in same_col))/20
        f['graph:column_below']=min(20,sum(position[owners[a.line]]>p for a in same_col))/20
        for role_name in row_roles[k]:f['graph:own_role:'+role_name]=1.
        for offset in (-3,-2,-1,1,2,3):
            q=p+offset
            if not 0<=q<len(order):continue
            j=order[q];tag='graph:row'+str(offset)+':'
            f[tag+'gap']=min(12.,abs(centers[j]-centers[k])/typical)/12
            f[tag+'money']=min(8,by_row[j])/8
            for role_name in row_roles[j]:f[tag+'role:'+role_name]=1.
        for role_name in sorted({s for rs in row_roles.values() for s in rs}):
            distances=[position[j]-p for j,rs in row_roles.items() if role_name in rs]
            if any(d<0 for d in distances):
                f['graph:nearest_above:'+role_name]=1./(1.+min(-d for d in distances if d<0))
            if any(d>0 for d in distances):
                f['graph:nearest_below:'+role_name]=1./(1.+min(d for d in distances if d>0))
        result.append(replace(c,features=f))
    return result

def diagnose(lines,obs,expected):
    """Reference is used only in evaluation, never inference."""
    ls,labels,links,unresolved=evidence(lines)
    matched=[c for c in obs if c.amount==expected and expected is not None]
    high=[c for c in matched if math.isfinite(c.score) and .85<=c.score<=1.]
    return {'reference_observed':int(bool(matched)),
            'reference_high_ocr':int(bool(high)),
            'reference_unique_location':int(len({c.line for c in matched})==1),
            'reference_multiple_locations':int(len({c.line for c in matched})>1),
            'explicit_label_present':int(bool(labels)),
            'unresolved_explicit_label':int(bool(unresolved)),
            'reference_explicit_link':int(any(v==expected for v,j in links.values())),
            'reference_in_nonfinal':int(any(role(ls[c.line])=='other' for c in matched)),
            'explicit_link_conflict':int(len({v for v,j in links.values()})>1)}

def self_test():
    def l(t,x=0,y=0,w=100,c=.98):return Line(t,c,(x,y,x+w,y+20))
    doc=[l('ТОВАР',y=0),l('20,00',220),l('ИТОГО',y=40),l('123,45',220,40),
         l('ОПЛАТА',y=80),l('123,45',220,80),l('ФН',y=120)]
    a=graph_observations(doc)
    assert len(a)==3
    assert a[1].features['graph:own_role:total']==1
    assert a[1].features['graph:row1:role:payment']==1
    assert a[2].features['graph:nearest_above:total']==.5
    assert a[1].features['graph:column_above']>0
    assert a[1].features['graph:column_below']>0
    changed=[replace(x,text=x.text.replace('123,45','987,65').replace('20,00','30,00')) for x in doc]
    assert [c.features for c in a]==[c.features for c in graph_observations(changed)]
    shifted=[replace(x,box=tuple(v*2+100 for v in x.box)) for x in doc]
    assert all(abs(c.features[k]-d.features[k])<1e-8 for c,d in zip(a,graph_observations(shifted)) for k in c.features if k.startswith('graph:'))
    assert diagnose(doc,a,'123,45')['reference_multiple_locations']==1
    assert diagnose(doc,a,'123,45')['reference_explicit_link']==1
    assert diagnose(doc,a,'999,99')['reference_observed']==0
    assert graph_observations([])==[]
    print('PASS: document graph roles, geometry, value invariance and reference diagnostics')
if __name__=='__main__':self_test()
