"""Exact identities and strict Stage/candidate schema, no physical evaluator."""
from fractions import Fraction as F
from copy import deepcopy
import hashlib,json,math
BASE_SHA='20fb232a81d69782b8ebd1fc1972a6bc96fff09e'
POLICY='auto_low_immediate_v1'
class ContractError(ValueError): pass

def require(ok,reason):
    if not ok: raise ContractError(reason)
def exact(v):
    require(not isinstance(v,bool) and isinstance(v,(str,int,F)),'NONEXACT_SCALAR')
    try: return F(v)
    except (ValueError,ZeroDivisionError): raise ContractError('INVALID_EXACT_SCALAR')
def encoded(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
def sha(v): return hashlib.sha256(encoded(v)).hexdigest()
def byte_sha(v): return hashlib.sha256(v).hexdigest()
def copy(v): return deepcopy(v)
def timely(value,seconds): return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and 0<=value<seconds

def mode_index(instance):
    out={}; orders={}
    for sid,rows in instance['stage_modes'].items():
        orders[sid]=[]
        for row in rows:
            key=(sid,row['unit_id'],row['opp_id'])
            require(key not in out,'DUPLICATE_MODE_KEY'); require(row['shared_stage_id']==sid,'SHARED_STAGE_ID_MISMATCH')
            require(row['mode_id']==f"{sid}@{row['unit_id']}:{row['opp_id']}",'MODE_ID_MISMATCH')
            out[key]=row; orders[sid].append(key)
    return out,orders

def candidate_identity(instance,candidate):
    require(isinstance(candidate,dict) and set(candidate)=={'scenes'} and isinstance(candidate['scenes'],dict),'CANDIDATE_FIELDS')
    scenes={s['id']:s for s in instance['scenarios']}
    require(set(candidate['scenes'])==set(scenes),'CANDIDATE_SCENE_COVERAGE')
    modes,_=mode_index(instance); shared={}; semantic={}; instances=0
    for scene_id,scene in scenes.items():
        stages={s['id']:s for s in scene['stage_instances']}; rows=candidate['scenes'][scene_id]
        require(isinstance(rows,list) and len(rows)==len(stages),'CANDIDATE_STAGE_COVERAGE')
        ids=[]; normalized=[]
        for row in rows:
            require(isinstance(row,dict) and set(row)=={'stage_id','unit','opp','start_ms'},'CANDIDATE_ROW_FIELDS')
            sid=row['stage_id']; require(sid in stages and sid not in ids,'CANDIDATE_DUPLICATE_OR_UNKNOWN_STAGE'); ids.append(sid)
            stage=stages[sid]; shared_id=stage['shared_stage_id']; key=(shared_id,row['unit'],row['opp'])
            require(key in modes,'CANDIDATE_UNSUPPORTED_MODE'); start=exact(row['start_ms']); grid=exact(instance['start_grid_ms'])
            require(start>=0 and (start/grid).denominator==1,'CANDIDATE_START_DOMAIN')
            require(shared_id not in shared or shared[shared_id]==row['unit'],'SHARED_DEPLOYMENT_CONFLICT'); shared[shared_id]=row['unit']
            normalized.append(dict(stage_id=sid,unit=row['unit'],opp=row['opp'],start_ms=str(start))); instances+=1
        semantic[scene_id]=sorted(normalized,key=lambda r:r['stage_id'])
    return dict(candidate_raw_sha256=sha(candidate),candidate_semantic_sha256=sha({'scenes':semantic}),stage_instances=instances,shared_deployment=shared)

def raw_candidate(raw):
    require(isinstance(raw,bytes),'CANDIDATE_RAW_BYTES_REQUIRED')
    def unique_pairs(pairs):
        d={}
        for k,v in pairs:
            require(k not in d,'DUPLICATE_JSON_FIELD'); d[k]=v
        return d
    def nonexact(_): raise ContractError('FLOAT_OR_NONFINITE_CANDIDATE_FORBIDDEN')
    try: x=json.loads(raw.decode('utf-8'),parse_float=nonexact,parse_constant=nonexact,object_pairs_hook=unique_pairs)
    except (UnicodeError,json.JSONDecodeError): raise ContractError('BAD_CANDIDATE_JSON')
    return x
