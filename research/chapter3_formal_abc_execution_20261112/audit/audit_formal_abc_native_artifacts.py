"""Post-run source and vector identity only; no scientific evidence is added after cutoff."""
from pathlib import Path
import json,sys,time
import numpy as np
from scipy.io import loadmat
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'work/formal_abc_v1'))
from guard import read,save,sha
from representation import load_science,digest
_,cg=load_science(ROOT)
start=time.monotonic();checks=[];records={}
def check(name,value):checks.append(dict(name=name,passed=bool(value)))
def payload(path,native=False):
    d=loadmat(path,variable_names=list(cg.KEYS))
    p={k:d[k].tocsc() if k in ('A','Aeq') else d[k].reshape(-1) for k in cg.KEYS}
    if native:p['intcon']=p['intcon'].astype(np.int64)-1
    return p
for arm in 'ABC':
    folder=ROOT/'work/formal_abc_execution_v1'/arm
    cert=read(folder/'representation_certificate.json')
    original=payload(folder/'original_zero_based.mat')
    submitted=payload(folder/'matlab/request_000001.mat',True)
    check(arm+'.original_arrays_bound_to_exact_certificate',cg.array_digest(original)==cert['source_array_sha256'])
    check(arm+'.native_arrays_bound_to_exact_certificate',cg.array_digest(submitted)==cert['derived_array_sha256'])
    check(arm+'.all_exact_projection_flags',all(cert['checks'].values()))
    receipt=read(folder/'receipt.json');native=receipt['native']
    raw=loadmat(folder/'matlab/request_000001.native.mat',variable_names=['x','fval','exitflag','output'],simplify_cells=True)
    vector=np.asarray(raw['x'],dtype=float).reshape(-1)
    check(arm+'.raw_MAT_vector_equals_native_JSON',np.array_equal(vector,np.asarray(native['x'],dtype=float)))
    check(arm+'.raw_exitflag_matches_JSON',int(raw['exitflag'])==native['exitflag'])
    record=dict(original_arrays=cg.array_digest(original),submitted_arrays=cg.array_digest(submitted),
        certificate_sha256=sha(folder/'representation_certificate.json'),raw_vector_length=len(vector),
        raw_vector_sha256=digest(vector.tolist()) if len(vector) else None,
        raw_native_fval=np.asarray(raw['fval']).reshape(-1).tolist(),
        raw_MAT_output=raw['output'])
    if len(vector):
        projected=cg.inverse_vector(vector,cert)
        check(arm+'.returned_option_selection_matches_initial',np.array_equal(projected[original['intcon']],original['x0'][original['intcon']]))
        record['same_full_continuous_vector_as_initial']=np.array_equal(projected,original['x0'])
    records[arm]=record
def clean(v):
    if isinstance(v,dict):return {k:clean(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [clean(x) for x in v]
    if isinstance(v,np.ndarray):return clean(v.tolist())
    if isinstance(v,np.generic):return clean(v.item())
    if isinstance(v,float) and not np.isfinite(v):return repr(v)
    return v
result=clean(dict(passed=all(c['passed'] for c in checks),checks=checks,arms=records,wall_s=time.monotonic()-start,
    new_native_calls=0,new_builds=0,new_physical_evaluations=0,
    interpretation='Identity recheck of archived evidence only; no new feasibility, LP or optimality certificate'))
save(ROOT/'work/formal_abc_execution_audit/native_artifact_audit.json',result)
print(json.dumps(dict(passed=result['passed'],checks=len(checks),failed=[c for c in checks if not c['passed']]),ensure_ascii=False))
