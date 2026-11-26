"""Train a compact semantic classifier on weak labels; evaluate held-out val
and reused test without fitting on them. No source text/images, labels,
vocabulary, predictions or model weights exported. Only aggregate reports.
"""
import hashlib
import io
import json
import math
import tempfile
import time
import warnings
from pathlib import Path
from collections import Counter
from importlib.metadata import version

import numpy as np
from PIL import Image
from huggingface_hub import HfApi,hf_hub_download
import pyarrow.parquet as pq
from paddleocr import TextDetection,TextRecognition
from sklearn.feature_extraction import FeatureHasher
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.exceptions import ConvergenceWarning
from receipt_structure import process,fetch,DET,REC,REC_REV,fixture
from paddle_diagnostic import DATASET,DATA_REV
from document_structure import analyze
from layout_diagnostics import anchor_candidate
from ocr_preprocess import normalize
from semantic_ranker import candidates,choose,self_test

DET_REV='0d63e78e2b680928f6b1747d76a08db6e645efb7'
LIMITS={'test':32,'val':40,'train':100}
N_FEATURES=512

def preflight(api):
    files=api.list_repo_files(DATASET,repo_type='dataset',revision=DATA_REV)
    out={}
    for split in LIMITS:
        names=(split,'validation') if split=='val' else (split,)
        paths=sorted(f for f in files if f.endswith('.parquet') and any('/'+n+'/' in '/'+f or Path(f).name.startswith(n+'-') for n in names))
        if not paths:raise RuntimeError('Missing parquet split: '+split)
        out[split]=paths
    print('PASS: train, val, test parquet splits located')
    return out

def sample(files):
    seen=set();samples={};meta={}
    # All test and validation rows reserved before choosing training images.
    # Train uses first shard only for CPU feasibility; not full population.
    for split,limit in LIMITS.items():
        keep=[];paths=files[split] if split!='train' else files[split][:1]
        counts=dict(rows=0,invalid=0,exact_duplicates=0,eligible=0,selected=0,shards=len(paths))
        for name in paths:
            path=hf_hub_download(DATASET,name,repo_type='dataset',revision=DATA_REV)
            for batch in pq.ParquetFile(path).iter_batches(batch_size=4,columns=['image','total_text']):
                for row in batch.to_pylist():
                    counts['rows']+=1
                    data=(row.get('image') or {}).get('bytes')
                    if not data:counts['invalid']+=1;continue
                    digest=hashlib.sha256(data).digest()
                    if digest in seen:counts['exact_duplicates']+=1;continue
                    seen.add(digest)
                    expected=normalize(row.get('total_text'))
                    if expected is None:counts['invalid']+=1;continue
                    counts['eligible']+=1
                    keep.append((digest,data,expected));keep.sort(key=lambda x:x[0])
                    if len(keep)>limit:keep.pop()
        if len(keep)!=limit:raise RuntimeError('Insufficient unique eligible rows: '+split)
        counts['selected']=len(keep);samples[split]=keep;meta[split]=counts
    return samples,meta

def save(data,name):
    Path(name).write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
    print(json.dumps(data,indent=2,sort_keys=True))

def fit(docs,hasher):
    features=[];labels=[];weights=[];positive_docs=0;negative_only=0
    for observed,expected in docs:
        y=[int(c.amount==expected) for c in observed]
        npos=sum(y);nneg=len(y)-npos
        if not npos or not nneg:negative_only+=1;continue
        positive_docs+=1
        for c,label in zip(observed,y):
            features.append(c.features);labels.append(label)
            weights.append(.5/(npos if label else nneg))
    if positive_docs<20:raise RuntimeError('Too few train documents with positive and negative candidate spans')
    x=hasher.transform(features);y=np.asarray(labels);w=np.asarray(weights);w*=len(w)/w.sum()
    # Fixed hyperparameters. No validation/test feedback into fitting.
    models={'logistic':LogisticRegression(C=1.,max_iter=500,random_state=42),
            'compact_mlp':MLPClassifier(hidden_layer_sizes=(32,),activation='relu',solver='adam',alpha=.01,max_iter=120,random_state=42)}
    result={'documents_used':positive_docs,'documents_without_both_classes':negative_only,
            'training_candidates':len(y),'positive_candidates':int(y.sum()),'features':N_FEATURES,'models':{}}
    for name,model in models.items():
        start=time.perf_counter()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always',ConvergenceWarning)
            model.fit(x,y,sample_weight=w)
        arrays=([model.coef_,model.intercept_] if name=='logistic' else list(model.coefs_)+list(model.intercepts_))
        result['models'][name]={'parameter_count':sum(a.size for a in arrays),'float32_parameter_bytes':sum(a.size for a in arrays)*4,
                                'fit_ms':round((time.perf_counter()-start)*1000,2),
                                'convergence_warning':any(issubclass(a.category,ConvergenceWarning) for a in caught)}
    return models,result

def metrics():return dict(n=0,accepted=0,correct=0,wrong=0)

def count(row,value,expected):
    row['n']+=1;row['accepted']+=int(value is not None)
    row['correct']+=int(value is not None and value==expected)
    row['wrong']+=int(value is not None and value!=expected)

def evaluate(docs,models,hasher):
    out={'n':0,'reference_present_in_spans':0,'methods':{}}
    for lines,expected in docs:
        obs=candidates(lines)
        out['n']+=1
        out['reference_present_in_spans']+=int(expected is not None and any(c.amount==expected for c in obs))
        values={'old_structure':analyze(lines).amount,'old_anchor':anchor_candidate(lines)}
        if obs:
            x=hasher.transform([c.features for c in obs])
            for name,model in models.items():
                scores=model.predict_proba(x)[:,list(model.classes_).index(1)]
                values[name+'_top1']=choose(obs,scores,threshold=0,margin=1e-9,require_ocr=False)
                values[name+'_gated']=choose(obs,scores,threshold=.85,margin=.15,require_ocr=True)
        else:
            for name in models:
                values[name+'_top1']=None;values[name+'_gated']=None
        for name,value in values.items():count(out['methods'].setdefault(name,metrics()),value,expected)
    return out

def main():
    self_test()
    api=HfApi();samples,meta=sample(preflight(api))
    result={'dataset_revision':DATA_REV,'sampling':meta,'packages':{n:version(n) for n in ('paddleocr','paddlepaddle','scikit-learn','numpy')},
            'training':{},'evaluations':{},'synthetic':{},'models':{}}
    save(result,'semantic_ranker_preflight_results.json')
    dp,dm=fetch(DET,DET_REV);rp,rm=fetch(REC,REC_REV)
    result['models']={DET:dm,REC:rm}
    det=TextDetection(model_name=DET,model_dir=str(dp),device='cpu',enable_mkldnn=False,cpu_threads=2)
    rec=TextRecognition(model_name=REC,model_dir=str(rp),device='cpu',enable_mkldnn=False,cpu_threads=2)
    hasher=FeatureHasher(n_features=N_FEATURES,input_type='dict',alternate_sign=False)
    with tempfile.TemporaryDirectory() as temp:
        folder=Path(temp)
        def load(split):
            for _,data,expected in samples[split]:
                with Image.open(io.BytesIO(data)) as im:
                    yield process(im,det,rec,folder),expected
        train_docs=[(candidates(lines),expected) for lines,expected in load('train')]
        models,result['training']=fit(train_docs,hasher)
        del train_docs
        save(result,'semantic_ranker_training_results.json')
        # All fitting completed before held-out documents are evaluated.
        for split in ('val','test'):
            result['evaluations'][split]=evaluate(load(split),models,hasher)
            save(result,'semantic_ranker_'+split+'_results.json')
        for kind in ('split','combined','tilt','blur','duplicate','missing'):
            def cases():
                for i in range(4):
                    im,expected=fixture(i,kind)
                    yield process(im,det,rec,folder),expected
            result['synthetic'][kind]=evaluate(cases(),models,hasher)
    save(result,'semantic_ranker_final_results.json')
if __name__=='__main__':main()
