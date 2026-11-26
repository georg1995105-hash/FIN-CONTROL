"""Controlled synthetic ring counting; not a general object detector."""
import json, statistics, time
import cv2
import numpy as np

VARIANTS = ('clean', 'lighting', 'small', 'overlap', 'cropped', 'foreign')

def fixture(seed, variant):
    rng = np.random.default_rng(seed)
    n = int(rng.integers(4, 11))
    img = np.full((480, 640), 230, np.uint8)
    centers = [(80 + 155*(i%4), 75 + 155*(i//4)) for i in range(n)]
    if variant == 'overlap': centers[1] = (centers[0][0] + 33, centers[0][1])
    if variant == 'cropped': centers[0] = (4, centers[0][1])
    for x,y in centers:
        r = int(rng.integers(22, 31))
        cv2.circle(img, (x,y), r, 40, -1, cv2.LINE_AA)
        cv2.circle(img, (x,y), r//2, 230, -1, cv2.LINE_AA)
    if variant == 'foreign': cv2.rectangle(img, (570, 410), (610, 450), 40, -1)
    if variant == 'lighting':
        lighting = np.linspace(0.68,1.0,img.shape[1])[None,:]
        img = np.clip(img.astype(float)*lighting + rng.normal(0, 4, img.shape), 0, 255).astype(np.uint8)
    if variant == 'small': img = cv2.resize(img, (320,240), interpolation=cv2.INTER_AREA)
    return img, n

def count_rings(image):
    # A constrained scene: dark, separated, roughly circular rings on a light surface.
    if image.ndim != 2 or min(image.shape) < 200: return None
    smooth = cv2.GaussianBlur(image, (3,3), 0)
    _, mask = cv2.threshold(smooth,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
    contours, hierarchy = cv2.findContours(mask,cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None: return None
    hierarchy = hierarchy[0]
    count = 0
    for i,c in enumerate(contours):
        if hierarchy[i][3] != -1: continue
        area = cv2.contourArea(c)
        if area < 12: continue  # tiny noise only
        x,y,w,h = cv2.boundingRect(c)
        if x<=1 or y<=1 or x+w>=image.shape[1]-1 or y+h>=image.shape[0]-1: return None
        if area < 100 or not 0.85 <= w/h <= 1.18: return None
        perimeter = cv2.arcLength(c,True)
        if perimeter <= 0 or 4*np.pi*area/perimeter**2 < 0.78: return None
        child = hierarchy[i][2]
        if child < 0 or hierarchy[child][0] != -1: return None
        hole = cv2.contourArea(contours[child])
        if not 0.14 <= hole/area <= 0.40: return None
        count += 1
    return count if count else None

def main():
    rows=[]
    for variant in VARIANTS:
        for seed in range(10,20):
            img, expected=fixture(seed,variant)
            start=time.perf_counter()
            count=count_rings(img)
            ms=(time.perf_counter()-start)*1000
            unsupported=variant in ('overlap','cropped','foreign')
            rows.append(dict(variant=variant, accepted=count is not None, wrong=count is not None and (unsupported or count!=expected), exact=count==expected and not unsupported, ms=ms))
    result={'opencv':cv2.__version__,'numpy':np.__version__,'samples':len(rows),'accepted':sum(r['accepted'] for r in rows),'wrong_accepts':sum(r['wrong'] for r in rows),'median_ms':round(statistics.median(r['ms'] for r in rows),2),'variants':{v:{'samples':10,'accepted':sum(r['accepted'] for r in rows if r['variant']==v),'wrong_accepts':sum(r['wrong'] for r in rows if r['variant']==v),'exact':sum(r['exact'] for r in rows if r['variant']==v)} for v in VARIANTS}}
    print(json.dumps(result,indent=2))

if __name__ == '__main__': main()
