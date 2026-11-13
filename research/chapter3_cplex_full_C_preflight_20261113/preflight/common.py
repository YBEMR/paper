"""D282 bounded I/O and policies; no native solver import."""
import hashlib,json,math,time
from pathlib import Path

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,v):
    with Path(p).open('x',encoding='utf-8',newline='\n') as f:
        json.dump(v,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')

def verify_files(root,entries):
    for name,expected in entries.items():
        if sha(Path(root)/name)!=expected:raise ValueError('Identity drift: '+name)

def monitor_decision(elapsed,private_bytes,parent_private,available,limits):
    if any(not math.isfinite(float(x)) or x<0 for x in (elapsed,private_bytes,parent_private,available)):
        return 'INVALID_MONITOR'
    if elapsed>=limits['worker_deadline_s']:return 'TIME_LIMIT'
    if private_bytes>=limits['worker_soft_private_bytes']:return 'WORKER_MEMORY_LIMIT'
    if parent_private>=limits['parent_private_bytes']:return 'CONTROLLER_MEMORY_LIMIT'
    if available<limits['system_available_floor_bytes']:return 'SYSTEM_MEMORY_LOW'
    return None

def classify(receipt,worker_exit,cleanup_ok,elapsed,limits):
    if cleanup_ok is not True:return 'CLEANUP_FAILURE'
    if not math.isfinite(elapsed) or elapsed<0:return 'INVALID_TIMING'
    if elapsed>limits['total_window_s']:return 'TOTAL_WINDOW_EXCEEDED'
    if worker_exit!=0:return 'WORKER_FAILURE'
    if not receipt or receipt.get('passed') is not True:return 'READBACK_FAILED'
    if receipt.get('native_objects_created')!=1 or receipt.get('algorithm_attempts')!=[]:return 'FORBIDDEN_SCOPE'
    stamp=receipt.get('sealed_elapsed_s',math.inf)
    if not isinstance(stamp,(float,int)) or not math.isfinite(stamp) or stamp<0:return 'INVALID_TIMING'
    if stamp>limits['worker_deadline_s']:return 'LATE_EVIDENCE'
    return 'PASS'

class Deadline:
    def __init__(self,t0,stop):self.t0=t0;self.stop=stop
    def check(self):
        if time.perf_counter()-self.t0>=self.stop:raise TimeoutError('D282 worker deadline')

def claim_once(path,claim):
    p=Path(path);p.mkdir(exist_ok=False);save(p/'claim.json',claim);return p
