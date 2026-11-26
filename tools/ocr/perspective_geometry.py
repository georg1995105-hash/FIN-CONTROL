"""Conservative page quadrilateral projection. Never changes OCR text or money."""
from dataclasses import dataclass
import math
import cv2
import numpy as np

@dataclass(frozen=True)
class Page:
    matrix: object
    quad: object
    reason: str


def order_quad(points):
    p=np.asarray(points,dtype=np.float32).reshape(-1,2)
    if len(p)!=4 or not np.isfinite(p).all():return None
    center=p.mean(axis=0)
    p=p[np.argsort(np.arctan2(p[:,1]-center[1],p[:,0]-center[0]))]
    p=np.roll(p,-int(np.argmin(p.sum(axis=1))),axis=0)
    if not cv2.isContourConvex(p):return None
    edges=np.roll(p,-1,axis=0)-p
    lengths=np.linalg.norm(edges,axis=1)
    if min(lengths)<20:return None
    if max(lengths[0],lengths[2])/min(lengths[0],lengths[2])>2.5:return None
    if max(lengths[1],lengths[3])/min(lengths[1],lengths[3])>2.5:return None
    for a,b in zip(edges,np.roll(edges,-1,axis=0)):
        if abs(float(np.dot(a,b)/(np.linalg.norm(a)*np.linalg.norm(b))))>.75:return None
    # This pilot supports upright portrait/landscape pages, not 90-degree orientation.
    if edges[0,0]<=0 or edges[1,1]<=0 or edges[2,0]>=0 or edges[3,1]>=0:return None
    return p


def transform(points,matrix):
    p=np.asarray(points,dtype=np.float64).reshape(-1,2)
    q=cv2.perspectiveTransform(p.reshape(1,-1,2),matrix)[0]
    if not np.isfinite(q).all():raise ValueError('Nonfinite projection')
    return q


def matrix_for(quad):
    p=order_quad(quad)
    if p is None:return None
    lengths=np.linalg.norm(np.roll(p,-1,axis=0)-p,axis=1)
    w=float((lengths[0]+lengths[2])/2);h=float((lengths[1]+lengths[3])/2)
    dst=np.array([[0,0],[w,0],[w,h],[0,h]],np.float32)
    m=cv2.getPerspectiveTransform(p,dst)
    if not np.isfinite(m).all() or abs(np.linalg.det(m))<1e-10:return None
    return m


def text_angles(polygons):
    angles=[]
    for points in polygons:
        p=np.asarray(points,dtype=np.float64).reshape(-1,2)
        if len(p)!=4 or not np.isfinite(p).all():continue
        c=p.mean(axis=0);p=p[np.argsort(np.arctan2(p[:,1]-c[1],p[:,0]-c[0]))]
        e=np.roll(p,-1,axis=0)-p;length=np.linalg.norm(e,axis=1)
        if min(length)<3:continue
        a=(length[0]+length[2])/2;b=(length[1]+length[3])/2
        if max(a,b)/min(a,b)<1.8:continue
        k=0 if a>b else 1
        angles.extend((math.degrees(math.atan2(e[j,1],e[j,0]))+90)%180-90 for j in (k,k+2))
    return np.asarray(angles,dtype=float)


def detect(image,polygons):
    rgb=np.asarray(image)
    if rgb.ndim!=3 or rgb.shape[2]!=3:return Page(None,None,'unsupported_image')
    h,w=rgb.shape[:2]
    if min(h,w)<80 or len(polygons)<4:return Page(None,None,'insufficient_geometry')
    centers=np.asarray([np.mean(p,axis=0) for p in polygons],dtype=float)
    if centers.shape!=(len(polygons),2) or not np.isfinite(centers).all():return Page(None,None,'invalid_polygons')
    factor=min(1.,1200/max(h,w));small=cv2.resize(rgb,(max(1,round(w*factor)),max(1,round(h*factor)))) if factor<1 else rgb
    sy,sx=small.shape[:2];gray=cv2.cvtColor(small,cv2.COLOR_RGB2GRAY)
    blur=cv2.GaussianBlur(gray,(5,5),0);otsu,_=cv2.threshold(blur,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    quads=[]
    for threshold in sorted(set([max(110,int(otsu)),175,205])):
        mask=cv2.threshold(blur,threshold,255,cv2.THRESH_BINARY)[1]
        mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((7,7),np.uint8))
        contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        for contour in sorted(contours,key=cv2.contourArea,reverse=True)[:5]:
            area=cv2.contourArea(contour)/(sx*sy)
            if not .18<=area<=.94:continue
            approx=cv2.approxPolyDP(contour,.025*cv2.arcLength(contour,True),True)
            if len(approx)!=4:continue
            p=order_quad(approx.reshape(4,2)/np.array([sx/w,sy/h],dtype=np.float32))
            if p is None:continue
            if np.any(p[:,0]<3) or np.any(p[:,1]<3) or np.any(p[:,0]>w-4) or np.any(p[:,1]>h-4):continue
            inside=sum(cv2.pointPolygonTest(p,tuple(map(float,q)),False)>=0 for q in centers)
            if inside/len(centers)<.98:continue
            # A crop that excludes any part of an OCR fragment is not trustworthy.
            if any(cv2.pointPolygonTest(p,tuple(map(float,q)),True)<-2 for poly in polygons for q in poly):continue
            quads.append(p)
    if not quads:return Page(None,None,'no_complete_outline')
    ref=quads[0];scale=math.hypot(w,h)
    if any(float(np.max(np.linalg.norm(q-ref,axis=1)))>.025*scale for q in quads[1:]):return Page(None,None,'ambiguous_outline')
    m=matrix_for(ref)
    if m is None:return Page(None,None,'invalid_projection')
    try:projected=[transform(p,m) for p in polygons]
    except (ValueError,cv2.error):return Page(None,None,'invalid_projection')
    angles=text_angles(projected)
    if len(angles)<6 or np.mean(np.abs(angles)<=4)<.75:return Page(None,None,'inconsistent_text_geometry')
    original=text_angles(polygons)
    if len(original)>=6:
        before=float(np.median(np.abs(original-np.median(original))))
        after=float(np.median(np.abs(angles-np.median(angles))))
        if after>max(1.5,before+.7):return Page(None,None,'geometry_worsened')
    return Page(m,ref,'complete_outline')


def self_test():
    page=np.full((640,440,3),245,np.uint8)
    polys=[]
    for y in (70,155,240,325,410,495):
        for x in (45,275):
            p=np.array([[x,y],[x+110,y],[x+110,y+22],[x,y+22]],np.float32)
            polys.append(p);cv2.rectangle(page,(x,y),(x+110,y+22),(25,25,25),-1)
    src=np.array([[0,0],[439,0],[439,639],[0,639]],np.float32)
    cases=[[[70,50],[440,95],[480,690],[35,650]],[[120,100],[500,40],[450,650],[45,700]],[[45,70],[470,120],[430,680],[100,620]]]
    for target in cases:
        H=cv2.getPerspectiveTransform(src,np.asarray(target,np.float32))
        warped=cv2.warpPerspective(page,H,(560,760),borderValue=(30,30,30))
        ps=[transform(p,H) for p in polys]
        found=detect(warped,ps)
        assert found.matrix is not None,found.reason
        proj=[transform(p,found.matrix) for p in ps]
        for j in range(0,len(proj),2):
            assert abs(float(proj[j][:,1].mean()-proj[j+1][:,1].mean()))<4
        assert np.median(np.abs(text_angles(proj)))<1
        assert detect(warped,ps[:2]).matrix is None
    assert detect(page,polys).matrix is None # paper fills image: incomplete outline
    assert detect(np.full_like(page,30),polys).matrix is None
    assert matrix_for([[0,0],[1,1],[2,2],[3,3]]) is None
    print('PASS: 3 perspective transformations, row alignment, incomplete outline and degenerate geometry rejection')

if __name__=='__main__':self_test()
