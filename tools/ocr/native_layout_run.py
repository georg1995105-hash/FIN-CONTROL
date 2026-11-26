"""Paired native-vs-geometric OCR experiment, aggregate outputs only."""
import io
import os
import subprocess
import tempfile
import time
from collections import Counter
from pathlib import Path
import numpy as np
from PIL import Image
from huggingface_hub import HfApi
from paddleocr import TextDetection,TextRecognition
from sklearn.feature_extraction import FeatureHasher
import semantic_ranker_run as prior
from semantic_ranker_v2_run import fit_v2
from semantic_ranker_v2 import enriched,protected,synthetic_docs
from total_row_evidence import group_rows,select
from row_ink_run import prepare,tally
from perspective_research_run import distorted,QUADS
from receipt_structure import fetch,DET,REC,REC_REV,fixture
from page_layout_evidence import page_totals,corroborate,cross_validate,self_test
from page_layout_run import page_image,words_from_tsv
from native_layout_evidence import native_groups,native_totals,self_test as native_self_test
import json

prior.LIMITS={'test':32,'val':137,'train':160}


def read_page(path,mapping,mode):
    try:
        proc=subprocess.run(['tesseract',str(path),'stdout','-l','rus','--oem','1','--psm',str(mode),'tsv'],
                            capture_output=True,text=True,timeout=35,env=dict(os.environ,OMP_THREAD_LIMIT='1'))
    except subprocess.TimeoutExpired:return [],[],'timeout','not_run'
    if proc.returncode!=0:return [],[],'engine_error','not_run'
    words=words_from_tsv(proc.stdout,mapping)
    try:hierarchy=native_groups(proc.stdout,mapping)
    except ValueError:return words,[],'read' if words else 'empty','invalid_native_tsv'
    return words,hierarchy,'read' if words else 'empty','read' if hierarchy else 'empty'


def evaluate(cases,models,hasher,det,rec,folder):
    out={'n':0,'positive':0,'negative':0,'methods':{},'page_stats':Counter(),'page_methods':{},'gates':{},'elapsed_ms':[]}
    for im,expected in cases:
        start=time.perf_counter()
        _,projected,matrix,_=prepare(im,det,rec,folder)
        lines,groups=group_rows(projected)
        obs=enriched(lines)
        page,mapping=page_image(im,matrix,lines)
        totals={};native={}
        for mode in (3,4,6):
            totals[mode]=[];native[mode]=[]
            if page is None:
                out['page_stats']['invalid_canvas']+=1;continue
            path=folder/'whole-page.png'
            page.save(path)
            try:words,hierarchy,status,native_status=read_page(path,mapping,mode)
            finally:path.unlink(missing_ok=True)
            out['page_stats'][f'psm{mode}_{status}']+=1
            out['page_stats'][f'psm{mode}_words']+=len(words)
            totals[mode],reason,stats=page_totals(words)
            out['page_stats'][f'psm{mode}_{reason}']+=1
            for key,v in stats.items():out['page_stats'][f'psm{mode}_{key}']+=v
            native[mode],reason,stats=native_totals(hierarchy)
            out['page_stats'][f'native{mode}_tsv_{native_status}']+=1
            out['page_stats'][f'native{mode}_{reason}']+=1
            out['page_stats'][f'native{mode}_lines']+=len(hierarchy)
            for key,v in stats.items():out['page_stats'][f'native{mode}_{key}']+=v
        joined=corroborate(totals[4],totals[6])
        native_joined=corroborate(native[4],native[6])
        out['page_stats']['both_modes_spatial_agreement']+=int(bool(joined))
        out['page_stats']['native_both_spatial_agreement']+=int(bool(native_joined))
        # Label-only diagnostics separate layout/recognition from the existing
        # Paddle ranking gate. Ground truth is used only by tally.
        for tag,ts in [('psm4',totals[4]),('psm6',totals[6]),('both',joined),
                       ('native3',native[3]),('native4',native[4]),('native6',native[6]),('native_both',native_joined)]:
            value=ts[0].value if ts else None
            tally(out['page_methods'].setdefault(tag+'_label_only_diagnostic',dict(n=0,correct=0,wrong=0,refused=0,negative_rejected=0)),value,expected)
        for name,m in models.items():
            scores=m.predict_proba(hasher.transform([c.features for c in obs]))[:,list(m.classes_).index(1)] if obs else []
            old=protected(lines,obs,scores)
            strict,_,_=select(lines,groups,obs,scores)
            values={'prior':old,'row_only':strict}
            methods=[('psm4',totals[4]),('psm6',totals[6]),('both',joined),
                     ('native3',native[3]),('native4',native[4]),('native6',native[6]),('native_both',native_joined)]
            for tag,ts in methods:
                candidate,reason=cross_validate(lines,obs,scores,ts)
                values[tag+'_cross']=candidate
                out['gates'].setdefault(name+'_'+tag,Counter())[reason]+=1
                values[tag+'_combined_diagnostic']=strict if candidate is None else candidate if strict in (None,candidate) else None
            for tag,value in values.items():
                tally(out['methods'].setdefault(name+'_'+tag,dict(n=0,correct=0,wrong=0,refused=0,negative_rejected=0)),value,expected)
        out['n']+=1;out['positive']+=int(expected is not None);out['negative']+=int(expected is None)
        out['elapsed_ms'].append((time.perf_counter()-start)*1000)
    out['median_ms']=round(float(np.median(out.pop('elapsed_ms'))),2)
    return out


def save(result,name):
    Path(name).write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result,indent=2,sort_keys=True))


def main():
    self_test();native_self_test()
    samples,meta=prior.sample(prior.preflight(HfApi()))
    result={'dataset_revision':prior.DATA_REV,'sampling':meta,'training':{},'evaluations':{},'synthetic':{},'models':{}}
    save(result,'native_layout_preflight_results.json')
    dp,dm=fetch(DET,prior.DET_REV);rp,rm=fetch(REC,REC_REV)
    result['models']={DET:dm,REC:rm}
    det=TextDetection(model_name=DET,model_dir=str(dp),device='cpu',enable_mkldnn=False,cpu_threads=2)
    rec=TextRecognition(model_name=REC,model_dir=str(rp),device='cpu',enable_mkldnn=False,cpu_threads=2)
    hasher=FeatureHasher(n_features=1024,input_type='dict',alternate_sign=False)
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp)
        def load(rows):
            for _,data,expected in rows:
                with Image.open(io.BytesIO(data)) as im:yield im.convert('RGB'),expected
        train=[]
        for im,expected in load(samples['train']):
            rect,_,_,_=prepare(im,det,rec,folder)
            train.append((rect,expected))
        models,result['training']=fit_v2(train,list(synthetic_docs(183,240)),hasher)
        del train
        save(result,'native_layout_training_results.json')
        for kind in ('split','combined','tilt','blur','duplicate','missing'):
            result['synthetic'][kind]=evaluate((fixture(i,kind) for i in range(4)),models,hasher,det,rec,folder)
        for kind in ('split','combined','duplicate','missing'):
            result['synthetic']['perspective_'+kind]=evaluate((distorted(kind,12,q) for q in QUADS),models,hasher,det,rec,folder)
        save(result,'native_layout_synthetic_results.json')
        for name,selected in [('reused_val',samples['val'][:40]),('last_val',samples['val'][120:]),('test',samples['test'])]:
            result['evaluations'][name]=evaluate(load(selected),models,hasher,det,rec,folder)
            save(result,'native_layout_'+name+'_results.json')
    save(result,'native_layout_final_results.json')
    for mode in (3,4,6):
        if not any(x['page_stats'].get(f'native{mode}_tsv_read',0)>0 for x in result['evaluations'].values()):
            raise RuntimeError(f'Native PSM{mode} never read a real image')

if __name__=='__main__':main()
