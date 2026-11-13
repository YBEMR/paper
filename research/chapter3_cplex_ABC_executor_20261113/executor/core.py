"""D284 protocol, atomic evidence and approval gate. No solver imports."""
from pathlib import Path
from fractions import Fraction
import hashlib, json, math, os, time

class IntegrityError(ValueError): pass
class WindowExpired(TimeoutError): pass
class PreparationStop(Exception): pass
class ScopedCorrectnessError(Exception):
    def __init__(self,message,affected_arms):
        super().__init__(message);self.affected_arms=list(affected_arms)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()

def digest(x): return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def save(path,value):
    path=Path(path)
    if path.exists(): raise FileExistsError(path)
    temp=path.with_name(path.name+'.partial')
    with temp.open('x',encoding='utf-8',newline='\n') as f:
        json.dump(value,f,ensure_ascii=False,allow_nan=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    os.rename(temp,path)

def verify(root,files):
    for p,h in files.items():
        if sha(Path(root)/p)!=h: raise IntegrityError('Identity drift: '+p)

def authorize(approval,plan_hash):
    required={'protocol':'D284-CPLEX-fresh-ABC-approval-v1','decision':'APPROVE',
        'plan_sha256':plan_hash,'maximum_solve_calls':3,'maximum_solve_calls_per_arm':1,'arms':['A','B','C'],'total_window_s':600,
        'response_cutoff_s':550,'retries':0,'scope':'FRESH_FULL_R1_CPLEX_ABC_ONCE'}
    if any(approval.get(k)!=v for k,v in required.items()): raise PermissionError('Independent D284 approval absent or incompatible')
    for k in ('approval_id','user_message_reference','frozen_commit'):
        if not isinstance(approval.get(k),str) or not approval[k].strip(): raise PermissionError('Missing '+k)
    commit=approval['frozen_commit']
    if len(commit)!=40 or any(c not in '0123456789abcdef' for c in commit): raise PermissionError('Invalid frozen commit')
    return True

def quota(elapsed):
    if not isinstance(elapsed,(int,float)) or not math.isfinite(elapsed) or elapsed<0: raise IntegrityError('Invalid elapsed time')
    return math.floor(min(540,max(0,600-elapsed-10-50)))

def finite_native(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or abs(value)>=1e20: return None
    return value

def safe_interval(result,scene_ids,cutoff=590):
    """Fail closed on missing, partial, late or unrankable evaluation evidence."""
    if not isinstance(result,dict) or result.get('state')!='SAFE' or result.get('rankable_energy') is not True: return None
    if result.get('numerical_protocol')!='directed-decimal60-taylor18-scaled100-v1': return None
    scenes=result.get('scenes',{})
    if set(scenes)!=set(scene_ids) or not all(s.get('state')=='SAFE' and s.get('complete') is True and s.get('energy_accuracy_met') is True for s in scenes.values()): return None
    for k in ('completed_at_elapsed_s','elapsed_s','archived_elapsed_s'):
        v=result.get(k)
        if not isinstance(v,(float,int)) or not math.isfinite(v) or not 0<=v<cutoff: return None
    try:
        lo,hi=map(Fraction,result['weighted_energy_J'])
        if lo<0 or lo>hi: return None
    except (KeyError,ValueError,TypeError,ZeroDivisionError): return None
    return lo,hi

def strict_improvement(initial,final,scenes,different,admitted,legal):
    a=safe_interval(initial,scenes);b=safe_interval(final,scenes)
    return bool(a and b and different is True and admitted is True and legal is True and b[1]<a[0])

def classify_native(status,error=None):
    """Native status is a reported exit reason, never an independent proof."""
    if error:
        text=(error.get('type','')+' '+error.get('message','')).lower()
        if 'memory' in text or '1001' in text: return 'RESOURCE_ERROR'
        if 'license' in text or 'licence' in text or '1016' in text or '32201' in text: return 'LICENSE_ERROR'
        return 'NATIVE_ERROR'
    # CPLEX public MIP codes (also checked against installed status constants).
    if status in (107,108,131,132): return 'TIME_LIMIT'
    if status in (111,112): return 'NATIVE_MEMORY_LIMIT'
    if status in (104,105,106): return 'SEARCH_LIMIT'
    if status in (113,114): return 'ABORTED'
    if status==103: return 'NATIVE_REPORTED_INFEASIBLE'
    if status in (101,102): return 'NATIVE_REPORTED_OPTIMAL'
    if status in (109,110,115,116,117): return 'NUMERICAL_FAILURE'
    return 'OTHER_OR_UNKNOWN_NATIVE_STATUS'

def stop_scope(*reasons):
    # Monotone cumulative rule; a subsequent ordinary result never clears it.
    if any(r in ('CLEANUP_FAILURE','IDENTITY_DRIFT','BOUND_CONFLICT','CONTROLLER_ERROR','EVIDENCE_INTEGRITY','UNCLASSIFIED_WORKER_ERROR') for r in reasons): return 'GLOBAL'
    return 'THIS_RUN'

class Clock:
    def __init__(self,start,now=time.monotonic): self.start=start;self.now=now
    @property
    def elapsed(self): return self.now()-self.start
    def check(self,cutoff=590):
        if not 0<=self.elapsed<cutoff: raise WindowExpired('Absolute window expired: '+str(cutoff))

def error_record(exc):
    import traceback
    return dict(type=type(exc).__name__,message=str(exc),args=[repr(x) for x in exc.args],traceback=traceback.format_exc())

def receive_response(out,clock,plan_hash):
    """Parent reads entire final vector bytes before assigning arrival credit."""
    out=Path(out);p=out/'native_response.json'
    raw=p.read_bytes();r=json.loads(raw)
    if r.get('plan_sha256')!=plan_hash: raise IntegrityError('Response source drift')
    v=r.get('vector');vector_hash=None
    if v:
        if v.get('file')!='final_vector.npy': raise IntegrityError('Unexpected final vector path')
        q=out/v['file']
        if q.stat().st_size>1024*1024: raise IntegrityError('Oversize candidate packet')
        vector_hash=sha(q)
        if vector_hash!=v['sha256']: raise IntegrityError('Final vector hash mismatch')
    elapsed=clock.elapsed
    return dict(plan_sha256=plan_hash,response_sha256=hashlib.sha256(raw).hexdigest(),
        vector_sha256=vector_hash,received_elapsed_s=elapsed,timely=0<=elapsed<550,
        source='parent_complete_read',candidate_present=bool(v))
