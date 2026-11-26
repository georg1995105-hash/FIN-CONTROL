"""Conservative document-wide geometry correction using OCR quadrilaterals.
No pixel alteration, OCR substitution, target value or annotated box is used.
A single dominant horizontal axis is supported, not arbitrary perspective.
"""
from dataclasses import dataclass
import math
import statistics
from total_candidate import Line

@dataclass(frozen=True)
class Axis:
    angle: float
    spread: float
    support: int
    inliers: int
    reliable: bool

def edge_angle(a,b):
    return (math.degrees(math.atan2(b[1]-a[1],b[0]-a[0]))+90.)%180.-90.

def polygon_angle(poly):
    try:
        p=[(float(x),float(y)) for x,y in poly]
    except (TypeError,ValueError,OverflowError):
        return None
    if len(p)!=4 or not all(math.isfinite(v) for q in p for v in q):return None
    cx=sum(q[0] for q in p)/4;cy=sum(q[1] for q in p)/4
    p.sort(key=lambda q:math.atan2(q[1]-cy,q[0]-cx))
    lengths=[math.dist(p[i],p[(i+1)%4]) for i in range(4)]
    if min(lengths)<3:return None
    a=(lengths[0]+lengths[2])/2;b=(lengths[1]+lengths[3])/2
    if max(a,b)/min(a,b)<1.8:return None
    i=0 if a>b else 1
    angles=[edge_angle(p[j],p[(j+1)%4]) for j in (i,i+2)]
    if any(abs(t)>20 for t in angles) or abs(angles[0]-angles[1])>4:return None
    return sum(angles)/2

def estimate(polygons):
    angles=[a for p in polygons if (a:=polygon_angle(p)) is not None]
    n=len(angles)
    if n<3:return Axis(0.,0.,n,0,False)
    center=statistics.median(angles)
    inliers=[a for a in angles if abs(a-center)<=2.5]
    if len(inliers)<3 or len(inliers)/n<.75 or abs(center)>15:
        return Axis(0.,0.,n,len(inliers),False)
    angle=statistics.median(inliers)
    spread=statistics.median(abs(a-angle) for a in inliers)
    if spread>1.25:return Axis(0.,spread,n,len(inliers),False)
    return Axis(angle,spread,n,len(inliers),True)

def project(poly,angle):
    t=math.radians(angle);c=math.cos(t);s=math.sin(t)
    q=[(c*x+s*y,-s*x+c*y) for x,y in poly]
    return (min(x for x,y in q),min(y for x,y in q),max(x for x,y in q),max(y for x,y in q))

def correct(lines,polygons,axis,offset=0.):
    if len(lines)!=len(polygons):raise ValueError('polygon/line mismatch')
    if not axis.reliable:return list(lines)
    return [Line(l.text,l.score,project(p,axis.angle+offset)) for l,p in zip(lines,polygons)]

def self_test():
    def rotate(p,t):
        r=math.radians(t);c=math.cos(r);s=math.sin(r)
        return [(c*x-s*y,s*x+c*y) for x,y in p]
    boxes=[[(0.,0.),(100.,0.),(100.,20.),(0.,20.)],
           [(200.,0.),(280.,0.),(280.,20.),(200.,20.)],
           [(0.,50.),(140.,50.),(140.,70.),(0.,70.)],
           [(200.,50.),(280.,50.),(280.,70.),(200.,70.)]]
    for angle in (-12.,-7.,-3.,0.,3.,7.,12.):
        pp=[rotate(p,angle) for p in boxes]
        ax=estimate(pp)
        assert ax.reliable and abs(ax.angle-angle)<1e-8
        for expected,actual in zip(boxes,[project(p,ax.angle) for p in pp]):
            target=project(expected,0)
            assert max(abs(x-y) for x,y in zip(target,actual))<1e-7
        shuffled=[list(reversed(p)) for p in pp]
        assert abs(estimate(shuffled).angle-angle)<1e-8
    assert not estimate([]).reliable
    assert not estimate(boxes[:2]).reliable
    assert not estimate([rotate(p,30) for p in boxes]).reliable
    assert not estimate([rotate(p,90) for p in boxes]).reliable
    assert not estimate([rotate(p,t) for p,t in zip(boxes,[-8,-8,8,8])]).reliable
    ax=estimate([rotate(p,7) for p in boxes]+[rotate(boxes[0],-12)])
    assert ax.reliable and abs(ax.angle-7)<1e-8
    assert polygon_angle([(0,0),(20,0),(20,20),(0,20)]) is None
    assert polygon_angle([(0,0),(0,0),(0,0),(0,0)]) is None
    assert polygon_angle([(0,0),(100,0),(100,float('nan')),(0,20)]) is None
    pp=[rotate(p,7) for p in boxes];ls=[Line(str(i),.96,project(p,0)) for i,p in enumerate(pp)]
    cc=correct(ls,pp,estimate(pp))
    assert all(a.text==b.text and a.score==b.score for a,b in zip(ls,cc))
    assert abs(cc[0].box[1]-cc[1].box[1])<1e-7
    assert correct(ls,pp,Axis(0,0,0,0,False))==ls
    print('PASS: seven signed angles, shuffled vertices, outlier/ambiguity guards and text preservation')
if __name__=='__main__':self_test()
