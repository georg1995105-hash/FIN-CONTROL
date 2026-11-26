"""Ink-based separation of overlapping OCR boxes.

A second crop is allowed only if the original image contains a distinct
horizontal ink band supported by each target polygon and not by a competing
neighbor polygon. No pixels inside the selected band are erased or synthesized.
The original recognition and semantic acceptance thresholds remain unchanged.
"""
import math
from collections import Counter
import cv2
import numpy as np
from PIL import Image,ImageOps

def bands(mask,gap):
    active=np.flatnonzero(np.any(mask,axis=1))
    if not len(active):return []
    out=[];start=last=int(active[0])
    for yy in active[1:]:
        y=int(yy)
        if y-last>gap+1:
            out.append((start,last+1));start=y
        last=y
    out.append((start,last+1))
    return out

def polygon_mask(shape,poly):
    p=np.asarray(poly,dtype=np.float64)
    if p.shape!=(4,2) or not np.isfinite(p).all():return None
    if np.max(np.abs(p))>1e6:return None
    rounded=np.rint(p).astype(np.int32)
    hull=cv2.convexHull(rounded)
    if len(hull)!=4 or cv2.contourArea(hull)<3:return None
    mask=np.zeros(shape,np.uint8)
    cv2.fillConvexPoly(mask,hull,1)
    return mask.astype(bool)

def select_band(gray,targets,neighbors,nominal_height):
    """Return original-pixel crop bounds or explicit rejection reason.
    The two threshold masks must independently identify the same ink band.
    """
    g=np.asarray(gray,dtype=np.uint8)
    if g.ndim!=2 or min(g.shape)<3 or not targets:return None,'invalid_patch'
    h,w=g.shape
    bg=float(np.percentile(g,85));dark=float(np.percentile(g,5))
    if bg<125 or bg-dark<22:return None,'insufficient_contrast'
    otsu,_=cv2.threshold(g,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    level=int(min(bg-12,max(float(otsu),bg-72)))
    levels=sorted(set([level,min(int(bg-8),level+12)]))
    tm=[polygon_mask(g.shape,p) for p in targets]
    nm=[polygon_mask(g.shape,p) for p in neighbors]
    if any(m is None for m in tm+nm):return None,'invalid_polygon'
    results=[]
    for threshold in levels:
        fg=g<=threshold
        if np.mean(fg)>.55:return None,'dense_foreground'
        # Small vertical gaps can separate a dot from its glyph; never
        # remove foreground or close across a substantial interline gap.
        intervals=bands(fg,max(1,round(.06*nominal_height)))
        if not intervals:return None,'no_ink'
        def support(mask):
            a=fg&mask
            counts=[int(np.count_nonzero(a[y:Y])) for y,Y in intervals]
            order=sorted(range(len(counts)),key=lambda i:counts[i],reverse=True)
            return counts,order
        target_ids=[]
        for p,m in zip(targets,tm):
            counts,order=support(m)
            best=order[0]
            total=sum(counts)
            if total<5 or counts[best]<.62*total:return None,'ambiguous_target_ink'
            if len(order)>1 and counts[order[1]]>.42*counts[best]:return None,'ambiguous_target_ink'
            y,Y=intervals[best];cy=float(np.mean(np.asarray(p)[:,1]))
            ph=float(np.ptp(np.asarray(p)[:,1]))
            if max(y-cy,cy-Y,0)>.22*max(3.,ph):return None,'target_center_mismatch'
            target_ids.append(best)
        if len(set(target_ids))!=1:return None,'target_spans_multiple_bands'
        selected=target_ids[0];y,Y=intervals[selected]
        if Y-y>1.3*nominal_height:return None,'band_too_tall'
        if y<=0 or Y>=h:return None,'band_at_patch_boundary'
        # The same target band cannot be the dominant ink of another
        # recognized line. A neighbor with only shared/ambiguous ink
        # cannot establish independent separation either.
        for p,m in zip(neighbors,nm):
            counts,order=support(m)
            total=sum(counts)
            if not total:continue
            if counts[selected]==0:continue
            cy=float(np.mean(np.asarray(p)[:,1]))
            if order[0]==selected or counts[selected]>.38*total or y<=cy<=Y:
                return None,'neighbor_owns_target_ink'
        # No foreground on the separator rows. Crop original grayscale,
        # not a binarized or masked image.
        if np.any(fg[y-1]) or np.any(fg[Y]):return None,'no_clear_separator'
        results.append((y,Y))
    if len(results)>1 and max(abs(results[0][j]-results[-1][j]) for j in (0,1))>max(2,.12*nominal_height):
        return None,'unstable_threshold'
    y=min(r[0] for r in results);Y=max(r[1] for r in results)
    return (0,y-1,w,Y+1),'ink_ready'

def rectify_crop(im,lines,groups,k,matrix,polygons):
    if len(lines)!=len(polygons):raise ValueError('polygon/line mismatch')
    row=groups[k];x,y,X,Y=row.box;h=Y-y
    if not row.safe or not all(math.isfinite(v) for v in row.box) or h<3:return None,'invalid_target'
    # Search a local strip, with a modest margin around the actual row.
    # A missing label may be on the left; use nearby line starts only.
    if len(row.indices)==1:
        near=[r.box[0] for j,r in enumerate(groups) if j!=k and abs((r.box[1]+r.box[3]-y-Y)/2)<=8*h and r.box[0]<x]
        if near:x=min(x,min(near))
    left=math.floor(x-.18*h);right=math.ceil(X+.18*h)
    top=math.floor(y-1.0*h);bottom=math.ceil(Y+1.0*h)
    width=right-left;height=bottom-top
    if width<3 or height<3 or width>8000 or height>1000:return None,'oversize'
    local=np.array([[1.,0.,-left],[0.,1.,-top],[0.,0.,1.]])
    m=local@np.asarray(matrix,dtype=np.float64)
    if not np.isfinite(m).all():return None,'invalid_transform'
    try:
        g=cv2.warpPerspective(np.asarray(im.convert('L')),m,(width,height),borderValue=255)
        # Input polygons are already in the rectified coordinates.
        shift=np.array([left,top],dtype=float)
        pp=[np.asarray(p,dtype=float)-shift for p in polygons]
    except (ValueError,cv2.error):return None,'invalid_transform'
    members=set(row.indices)
    if not members or any(i>=len(pp) for i in members):return None,'invalid_target'
    targets=[pp[i] for i in sorted(members)]
    neighbors=[]
    for i,p in enumerate(pp):
        if i in members:continue
        a,b=p.min(axis=0);A,B=p.max(axis=0)
        if A<=0 or B<=0 or a>=width or b>=height:continue
        neighbors.append(p)
    bounds,reason=select_band(g,targets,neighbors,h)
    if bounds is None:return None,reason
    a,b,A,B=bounds
    image=Image.fromarray(g[b:B,a:A])
    if image.height<64:
        image=image.resize((max(1,round(image.width*64/image.height)),64),Image.Resampling.LANCZOS)
    # Whitespace only, no erasing individual symbols or choosing a value.
    return ImageOps.expand(ImageOps.autocontrast(image),border=4,fill=255).convert('RGB'),'ink_ready'

def self_test():
    def poly(x,y,X,Y):return np.array([[x,y],[X,y],[X,Y],[x,Y]],dtype=float)
    g=np.full((100,320),255,np.uint8)
    # Actual glyphs in distinct rows, padded OCR boxes overlap.
    for x in (20,48,76,220,248,276):
        cv2.rectangle(g,(x,32),(x+12,44),20,-1)
        cv2.rectangle(g,(x,53),(x+12,65),20,-1)
    target=[poly(14,26,95,51),poly(214,26,295,51)]
    neighbors=[poly(14,43,95,72),poly(214,43,295,72)]
    bounds,reason=select_band(g,target,neighbors,25)
    assert reason=='ink_ready',(bounds,reason)
    assert bounds[1]<=32 and bounds[3]>44 and bounds[3]<=53
    # Pixel touching: not possible to separate without cutting ink.
    joined=g.copy()
    cv2.rectangle(joined,(20,44),(32,53),20,-1)
    assert select_band(joined,target,neighbors,25)[0] is None
    # A second detector identifying the same row is ambiguous.
    assert select_band(g,target,[poly(14,26,95,51)],25)[0] is None
    # Members on different rows cannot be combined as a total.
    assert select_band(g,[target[0],neighbors[1]],[],25)[0] is None
    # Dark/blank background is not sufficient evidence.
    assert select_band(np.full_like(g,255),target,neighbors,25)[0] is None
    assert select_band(np.full_like(g,20),target,neighbors,25)[0] is None
    from total_candidate import Line
    from total_row_evidence import group_rows
    lines,groups=group_rows([Line('ИТОГ0',.6,(14,26,95,51)),Line('123,45',.98,(214,26,295,51)),
                            Line('ТОВАР',.95,(14,43,95,72)),Line('23,45',.98,(214,43,295,72))])
    boxes=[poly(*l.box) for l in lines]
    k=next(i for i,r in enumerate(groups) if 'ИТОГ0' in r.text)
    im,reason=rectify_crop(Image.fromarray(g),lines,groups,k,np.eye(3),boxes)
    assert im is not None,reason
    print('PASS: ink-separated padded boxes, touching and competing rows, full target strip')

if __name__=='__main__':self_test()
