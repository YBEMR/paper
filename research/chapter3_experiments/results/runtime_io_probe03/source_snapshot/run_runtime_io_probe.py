"""K130 bounded I/O/startup diagnostic; no model, solver or thermal call.

Preserve every error without retrying a native startup or changing user caches.
The optional native phase constructs one exact existing MatlabSession and
closes it without sending any request.
"""
import argparse
from contextlib import ExitStack
import ctypes
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import time
import traceback
from unittest.mock import patch

import matlab_bridge as bridge

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
PROTOCOL='K130-bounded-filesystem-and-worker-startup-no-solve-v1'

def utc(): return datetime.now(timezone.utc).isoformat()
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def exception(exc):
    return {'type':type(exc).__name__,'message':str(exc),'errno':getattr(exc,'errno',None),
        'winerror':getattr(exc,'winerror',None),'filename':getattr(exc,'filename',None),
        'diagnostics':getattr(exc,'diagnostics',None)}
def save(p,v):
    Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False,default=str)+'\n',encoding='utf-8')
def low_level_read(path):
    """Independent Win32 error at the same name; never create the ready file."""
    if platform.system()!='Windows': return {'not_windows':True}
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.CreateFileW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32,
        ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p]
    api.CreateFileW.restype=ctypes.c_void_p
    api.CloseHandle.argtypes=[ctypes.c_void_p]; api.CloseHandle.restype=ctypes.c_int
    handle=api.CreateFileW(str(Path(path).resolve()),0x80000000,7,None,3,0x80,None)
    if handle==ctypes.c_void_p(-1).value:
        code=ctypes.get_last_error();return {'opened':False,'winerror':code,'message':ctypes.FormatError(code)}
    api.CloseHandle(handle);return {'opened':True}

def run(out,native,native_startups=1,execution_context='workspace_sandbox'):
    out=out.resolve();out.relative_to(REPO);out.mkdir(parents=True,exist_ok=False)
    started=time.monotonic(); sources={p.name:sha(p) for p in
        [Path(__file__),HERE/'matlab_bridge.py',HERE/'solve_model.m']}
    cache=Path('C:/Users/86130/AppData/Local/MathWorks/MATLAB/R2023b/toolbox_cache-23.2.0-972814494-win64.xml')
    cache_before={'exists':cache.exists(),'sha256':sha(cache) if cache.exists() else None,
        'bytes':cache.stat().st_size if cache.exists() else None}
    total_limit=240 if native_startups==2 else 180
    declaration={'protocol':PROTOCOL,'declared_at_utc':utc(),'native_startup_limit':native_startups if native else 0,
        'execution_context_declared_by_launcher':execution_context,
        'startup_budget_s_max':90,'total_diagnostic_budget_s':total_limit,'no_native_retry':True,
        'sequential_same_python_and_preferences':native_startups==2,
        'solver_requests_allowed':0,'research_calls':0,'models':0,'thermal_evaluations':0,
        'user_cache_modifications_allowed':False,'sources_sha256':sources}
    save(out/'declaration.json',declaration)
    snapshots=out/'source_snapshot';snapshots.mkdir()
    for name,h in sources.items():
        assert sha(HERE/name)==h;shutil.copyfile(HERE/name,snapshots/name)
    events=[]
    def event(stage,**fields):
        item={'stage':stage,'elapsed_s':time.monotonic()-started,'utc':utc(),**fields}
        events.append(item)
        if fields.get('error') or stage in ('native_ready','native_failed','native_closed'):
            print(json.dumps(item,ensure_ascii=False,default=str),flush=True)
    def check():
        if time.monotonic()-started>=total_limit:raise TimeoutError('Fixed total diagnostic cap reached')
    folders=[out/'file_probe',REPO/'.runtime'/('k130_probe_'+out.name)]
    probes=[]
    for folder in folders:
        folder.mkdir(parents=True,exist_ok=False);missing=folder/'never_published_ready.json';counts={}
        for i in range(100):
            check()
            try:missing.read_text(encoding='utf-8-sig')
            except OSError as exc:
                key=(type(exc).__name__,exc.errno,getattr(exc,'winerror',None));counts[str(key)]=counts.get(str(key),0)+1
                if not isinstance(exc,FileNotFoundError):event('missing_read_unexpected',error=exception(exc),win32=low_level_read(missing))
            else:raise AssertionError('Unexpected publication in missing-file probe')
        for i in range(100):
            check();bridge._json(folder/'session.json',{'sequence':i,'kind':'technical I/O probe'})
            assert json.loads((folder/'session.json').read_text(encoding='utf-8'))['sequence']==i
        probes.append({'folder':str(folder.relative_to(REPO)),'missing_reads':counts,
            'atomic_write_and_read_count':100,'native_win32_missing':low_level_read(missing)})
    session=None;native_error=None;cleanup=None;cleanups=[];completed_startups=0
    if native:
        original_json=bridge._json;original_wait=bridge._read_json_until
        def traced_json(path,value):
            event('json_write_begin',path=str(path))
            try:result=original_json(path,value)
            except BaseException as exc:
                event('json_write_failed',path=str(path),error=exception(exc));raise
            event('json_write_complete',path=str(path));return result
        def traced_wait(path,*args,**kwargs):
            event('ready_wait_begin',path=str(path))
            try:result=original_wait(path,*args,**kwargs)
            except BaseException as exc:
                event('ready_wait_failed',path=str(path),error=exception(exc),win32=low_level_read(path));raise
            event('ready_wait_complete',read_diagnostics=result[1]);return result
        for index in range(native_startups):
            session=None;cleanup=None
            try:
                check()
                # The fixed outer cap has priority over a second startup.
                # Reserve the existing worst-case 40 s cleanup allowance.
                startup_cap=min(90,total_limit-(time.monotonic()-started)-40)
                if startup_cap<=0:raise TimeoutError('No startup time after reserving cleanup')
                folder=out/('matlab' if native_startups==1 else f'matlab_{index:03d}')
                with patch.object(bridge,'_json',traced_json),patch.object(bridge,'_read_json_until',traced_wait):
                    session=bridge.MatlabSession(folder,total_budget_s=startup_cap,cut_max_iterations=10)
                    event('native_ready',index=index,environment=session.environment,metadata=session.metadata)
                    # Same writes that previously failed, while the worker idles.
                    for i in range(50):
                        check();original_json(out/'input_config_probe.json',{'sequence':i,'startup':index})
                        original_json(session.workdir/'session_probe.json',{'sequence':i})
                    assert session.counter==0
                    session.close();cleanup=session.cleanup;cleanups.append(cleanup)
                    event('native_closed',index=index,cleanup=cleanup,requests=session.counter)
                    if (cleanup.get('returncode')!=0 or cleanup.get('cleanup_pending_pid')
                            or any(k.endswith('_error') for k in cleanup)):
                        raise RuntimeError('Cleanup not complete; no next startup')
                    completed_startups+=1
            except BaseException as exc:
                native_error={**exception(exc),'traceback':traceback.format_exc(),
                    'startup_metadata':getattr(exc,'matlab_startup_metadata',None),
                    'cleanup':getattr(exc,'matlab_cleanup',None)}
                event('native_failed',index=index,error=native_error)
                break
            finally:
                if session is not None and not session.closed:
                    session.close();cleanup=session.cleanup
    raw_request_files=[p for f in out.glob('matlab*') if f.is_dir() for p in f.glob('request_*')]
    cache_after={'exists':cache.exists(),'sha256':sha(cache) if cache.exists() else None}
    passed=bool((not native or (completed_startups==native_startups and native_error is None)) and not raw_request_files)
    report={'protocol':PROTOCOL,'passed':passed,'events':events,'file_probes':probes,
        'native_startups_completed':completed_startups,'native_startup_limit':native_startups if native else 0,
        'solver_requests':0,'research_calls':0,'native_error':native_error,
        'cleanup':cleanup,'cleanups':cleanups,'cache_before':cache_before,'cache_after':cache_after,
        'cache_bytes_unchanged':cache_before['sha256']==cache_after['sha256'],
        'source_unchanged':all(sha(HERE/name)==h for name,h in sources.items()),
        'elapsed_s':time.monotonic()-started,'disk_free_bytes':shutil.disk_usage(REPO).free,
        'environment':{'python':platform.python_version(),'platform':platform.platform()},
        'scope':'I/O and worker startup only; no original-case retry or quality evidence'}
    save(out/'checks.json',report)
    print(json.dumps({k:report[k] for k in ['passed','native_startups_completed','solver_requests','native_error','elapsed_s']},ensure_ascii=False),flush=True)
    return passed

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--native',action='store_true');p.add_argument('--native-startups',type=int,choices=(1,2),default=1)
    p.add_argument('--execution-context',choices=('workspace_sandbox','approved_host'),default='workspace_sandbox');args=p.parse_args()
    raise SystemExit(0 if run(args.out,args.native,args.native_startups,args.execution_context) else 1)
