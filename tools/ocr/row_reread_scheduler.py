"""Separate a bounded OCR work scheduler from the strict financial evidence gate.

Selection may inspect low-confidence/partial observations; this NEVER relaxes
the acceptance rules in total_row_evidence.select/reread. All results are
diagnostic candidates, not verified financial findings.
"""
import math
import re
from collections import Counter
import numpy as np
from PIL import Image,ImageOps
from total_candidate import Line
from total_row_evidence import (group_rows,direct,observed_amount,high,norm_text,
    START,NONFINAL,OTHER)
from semantic_ranker import spans

def plan(lines,groups,obs,scores,limit=12):
    by_index={}
    for c,s in zip(obs,scores):
        if math.isfinite(float(s)):by_index[c.line]=max(by_index.get(c.line,0.),float(s))
    stats=Counter();ranked=[]
    for k,row in enumerate(groups):
        stats['rows_seen']+=1
        t=norm_text(row.text)
        if direct(lines,row) is not None:
            stats['already_direct']+=1;continue
        if OTHER.match(t) or NONFINAL.match(t):
            stats['explicit_nonfinal']+=1;continue
        if not row.safe:
            stats['overlapping_fragments']+=1;continue
        found=[(i,a) for i in row.indices for _,_,a in spans(lines[i].text)]
        explicit=bool(START.match(t))
        if not found and not explicit:
            stats['no_money_or_label']+=1;continue
        if len(found)>1:
            stats['multiple_spans']+=1;continue
        # A low OCR or rank score must not prevent a diagnostic read.
        # Missing/weak money cannot pass the unchanged evidence gate.
        score=max((by_index.get(i,0.) for i in row.indices),default=0.)
        strong=observed_amount(lines,row) is not None
        stats['eligible']+=1
        stats['eligible_strong_amount' if strong else 'eligible_partial_or_weak']+=1
        ranked.append((int(explicit),int(strong),score,k))
    chosen=[k for _,_,_,k in sorted(ranked,key=lambda p:(-p[0],-p[1],-p[2],p[3]))[:limit]]
    stats['scheduled']=len(chosen)
    stats['budget_excluded']=len(ranked)-len(chosen)
    return chosen,stats

def crop_bounds(lines,groups,k):
    row=groups[k];x,y,X,Y=row.box;h=Y-y
    if not row.safe or not all(math.isfinite(v) for v in row.box) or h<3 or X<=x:
        return None,'invalid_target'
    # Keep a local row, not the width of unrelated footer/header text.
    # If the row has no observed label, extend toward nearby left edges.
    t=norm_text(row.text)
    has_letters=bool(re.search(r'[А-ЯA-Z]',t))
    if not has_letters:
        nearby=sorted((r for j,r in enumerate(groups) if j!=k and r.safe),
                      key=lambda r:abs((r.box[1]+r.box[3]-y-Y)/2))[:6]
        lefts=[r.box[0] for r in nearby if r.box[0]<x and abs((r.box[1]+r.box[3]-y-Y)/2)<=12*h]
        if lefts:x=min(x,min(lefts))
    left=x-.15*h;right=X+.15*h
    top=y-.20*h;bottom=Y+.20*h
    member=set(row.indices)
    # Clamp padding against actual neighboring OCR fragments, not their
    # row-wide unions. Do not remove any portion of the target bounds.
    for j,l in enumerate(lines):
        if j in member:continue
        a,b,A,B=l.box
        if min(right,A)<=max(left,a):continue
        if B<=y:top=max(top,B)
        elif b>=Y:bottom=min(bottom,b)
        else:
            # Positive area of a different text line inside target strip.
            # A real overlap remains ambiguous; don't mix two rows.
            if min(Y,B)-max(y,b)>.1*min(h,B-b):
                return None,'neighbor_intersects_target'
    if bottom-top<3 or right-left<3:return None,'empty_crop'
    if right-left>8000 or bottom-top>1000:return None,'oversize'
    if (right-left)/(bottom-top)>100:return None,'extreme_aspect'
    return (left,top,right,bottom),'ready'

def make_crop(im,lines,groups,k,matrix):
    import cv2
    bounds,reason=crop_bounds(lines,groups,k)
    if bounds is None:return None,reason
    left,top,right,bottom=bounds
    width=max(3,round(right-left));height=max(3,round(bottom-top))
    src=np.array([[[left,top],[right,top],[right,bottom],[left,bottom]]],np.float64)
    try:src=cv2.perspectiveTransform(src,np.linalg.inv(matrix))[0].astype(np.float32)
    except (np.linalg.LinAlgError,cv2.error):return None,'invalid_transform'
    if not np.isfinite(src).all():return None,'invalid_transform'
    dst=np.array([[0,0],[width-1,0],[width-1,height-1],[0,height-1]],np.float32)
    patch=cv2.warpPerspective(np.asarray(im.convert('RGB')),cv2.getPerspectiveTransform(src,dst),(width,height),borderValue=(255,255,255))
    image=Image.fromarray(patch).convert('L')
    if image.height<64:
        image=image.resize((max(1,round(image.width*64/image.height)),64),Image.Resampling.LANCZOS)
    return ImageOps.expand(ImageOps.autocontrast(image),border=4,fill=255).convert('RGB'),'ready'

def self_test():
    from semantic_ranker_v2 import enriched
    def l(t,x=0,y=0,w=100,c=.98):return Line(t,c,(x,y,x+w,y+20))
    lines,groups=group_rows([l('ИТОГ0',c=.6),l('123,45',250)])
    obs=enriched(lines)
    chosen,stats=plan(lines,groups,obs,[.1]*len(obs))
    assert chosen==[0] and stats['eligible_strong_amount']==1
    lines,groups=group_rows([l('ИТОГО'),l('123,45',250,c=.7)])
    obs=enriched(lines)
    chosen,stats=plan(lines,groups,obs,[.05]*len(obs))
    assert chosen==[0] and stats['eligible_partial_or_weak']==1
    lines,groups=group_rows([l('ИТОГО')])
    assert plan(lines,groups,[],[])[0]==[0]
    lines,groups=group_rows([l('НДС'),l('123,45',250)])
    assert plan(lines,groups,enriched(lines),[.99])[0]==[]
    lines,groups=group_rows([l('ИТОГ0',c=.6),l('123,45',250),l('МОЛОКО',y=22,w=300),l('ДЛИННЫЙ ЗАГОЛОВОК',y=70,w=2000)])
    bounds,reason=crop_bounds(lines,groups,0)
    assert reason=='ready' and bounds[3]<=22 and bounds[2]<400
    lines,groups=group_rows([l('ИТОГ0',c=.6),l('123,45',250),l('ПОДЫТОГ',x=0,y=14,w=300)])
    assert crop_bounds(lines,groups,0)[0] is None
    lines,groups=group_rows([l('123,45',250,y=35),l('ТОВАР',0,0,100)])
    k=next(i for i,r in enumerate(groups) if '123,45' in r.text)
    bounds,reason=crop_bounds(lines,groups,k)
    assert reason=='ready' and bounds[0]<5
    lines,groups=group_rows([l('123,45',250,y=i*35) for i in range(20)])
    obs=enriched(lines);chosen,stats=plan(lines,groups,obs,[0.]*len(obs),limit=5)
    assert len(chosen)==5 and stats['budget_excluded']==15
    print('PASS: weak and partial rows scheduled, local crop, neighbor clipping, conflict and read budget')

if __name__=='__main__':self_test()
