"""Frozen-source verification and serialization; no scheduling decisions."""
import hashlib,json,os,sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
INPUTS='research/chapter4_scheduler/results/onp_new24_20261113/execution/frozen_inputs'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def save(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def paths():
    sys.dont_write_bytecode=True
    for p in [HERE/'frozen',HERE/'frozen/research/chapter3_experiments',HERE/'reuse']:
        sys.path.insert(0,str(p))
def verify_sources():
    m=read(HERE/'sources.json')
    for row in m['frozen']:
        p=HERE/'frozen'/row['path'];b=p.read_bytes()
        assert sha(p)==row['sha256'] and len(b)==row['bytes'],row['path']
        assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==row['git_blob']
    for row in m['reused']:assert sha(HERE/row['path'])==row['sha256'],row['path']
    return {'frozen':len(m['frozen']),'reused':len(m['reused'])}
def integration_identity():
    return {('controlled_search/'+p.relative_to(HERE).as_posix()):sha(p) for p in sorted(HERE.glob('*.py'))}|{
      'controlled_search/reuse/'+p.name:sha(p) for p in sorted((HERE/'reuse').glob('*.py'))}
def peak_memory():
    if os.name=='nt':
        import ctypes
        from ctypes import wintypes
        class PMC(ctypes.Structure):
            _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in
              ['PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage']]
        p=PMC();p.cb=ctypes.sizeof(p)
        h=ctypes.windll.kernel32.GetCurrentProcess
        h.restype=wintypes.HANDLE
        if not ctypes.windll.psapi.GetProcessMemoryInfo(h(),ctypes.byref(p),p.cb):raise OSError('PROCESS_MEMORY_QUERY')
        return {'peak_rss_bytes':p.PeakWorkingSetSize,'current_rss_bytes':p.WorkingSetSize,'kind':'process_lifetime_peak_working_set'}
    import resource
    return {'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,'kind':'process_lifetime_maxrss'}
