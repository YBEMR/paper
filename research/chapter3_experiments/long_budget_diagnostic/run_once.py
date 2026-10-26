"""K187: one original P0/R1 whole MILP call, 3600 s; no scientific edits."""
from __future__ import annotations
import argparse
import ctypes
from ctypes import wintypes as w
from datetime import datetime, timezone
from fractions import Fraction as F
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SCIENCE = REPO/'research/chapter3_experiments'
OUT = SCIENCE/'results/whole_long_budget01'
SNAP = OUT/'source_snapshot'
CALL = OUT/'method'
OLD = SCIENCE/'results/p0_execution01'
PREP = SCIENCE/'results/p0_batch_preparation01'
SECONDS, POST_SECONDS = 3600, 60
CHECKPOINTS = (300, 900, 1800, 3600)
CALENDAR = 3900  # Includes imports, cleanup, postcheck; never extends science.

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def canonical(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()

def now(): return datetime.now(timezone.utc).isoformat()

def write_new(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')

def context():
    import psutil
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    a=ctypes.WinDLL('advapi32',use_last_error=True)
    a.OpenProcessToken.argtypes=[w.HANDLE,w.DWORD,ctypes.POINTER(w.HANDLE)]
    a.GetTokenInformation.argtypes=[w.HANDLE,ctypes.c_int,w.LPVOID,w.DWORD,ctypes.POINTER(w.DWORD)]
    k.GetCurrentProcess.restype=w.HANDLE;k.CloseHandle.argtypes=[w.HANDLE]
    token=w.HANDLE();flag=w.DWORD();size=w.DWORD()
    if not a.OpenProcessToken(k.GetCurrentProcess(),8,ctypes.byref(token)):raise ctypes.WinError()
    try:
        if not a.GetTokenInformation(token,29,ctypes.byref(flag),ctypes.sizeof(flag),ctypes.byref(size)):raise ctypes.WinError()
    finally:k.CloseHandle(token)
    class Memory(ctypes.Structure):
        _fields_=[('length',w.DWORD),('load',w.DWORD)]+[(n,ctypes.c_ulonglong) for n in ('total_phys','avail_phys','total_page','avail_page','total_virtual','avail_virtual','avail_extended')]
    mem=Memory();mem.length=ctypes.sizeof(mem)
    if not k.GlobalMemoryStatusEx(ctypes.byref(mem)):raise ctypes.WinError()
    processes=[]
    for p in psutil.process_iter(['name','pid','create_time']):
        if (p.info['name'] or '').lower()=='matlab.exe':processes.append(p.info)
    return dict(token_is_appcontainer=bool(flag.value),python=sys.executable,pid=os.getpid(),
        temp=os.environ.get('TEMP'),physical_available_bytes=mem.avail_phys,
        commit_available_bytes=mem.avail_page,matlab_processes=processes,
        disk_free_bytes=shutil.disk_usage(REPO).free,utc=now())

def resource_ok(c):
    return (not c['token_is_appcontainer'] and not c['matlab_processes']
        and c['physical_available_bytes']>=2*1024**3
        and c['commit_available_bytes']>=4*1024**3 and c['disk_free_bytes']>=2*1024**3)

def prepare():
    """Only copy/read original sources; no model, candidate or thermal calculation."""
    if OUT.exists():raise FileExistsError('Preparation already exists; do not overwrite')
    original=read(OLD/'declaration.json')['source_sha256']
    origins={}
    for name,digest in original.items():
        options=[PREP/'source_snapshot'/name,OLD/'execution_source_snapshot'/name]
        src=next((p for p in options if p.is_file() and sha(p)==digest),None)
        if src is None:raise ValueError('Frozen source missing: '+name)
        dst=SNAP/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
        origins[name]=str(src.relative_to(REPO)).replace('\\','/')
    spec=read(PREP/'declaration.json')['inputs']['base__R1']
    declaration=dict(protocol='K187-P0-R1-original-whole-long-3600-once-v1',authorized=True,
        authorization_origin='Explicit human authorization in current conversation, 2026-10-26',
        method='whole_milp',problem_id='base__R1',method_seconds=SECONDS,method_calls=1,
        post_seconds=POST_SECONDS,post_calls_at_most=1,calendar_seconds=CALENDAR,
        method_return_watchdog_seconds=SECONDS+120,post_return_watchdog_seconds=POST_SECONDS+30,
        checkpoints=list(CHECKPOINTS),input_declaration=spec,source_sha256=original,source_origins=origins,
        wrapper_sha256={p.name:sha(p) for p in sorted(HERE.iterdir()) if p.suffix in ('.py','.md')},
        original_declaration_sha256=sha(OLD/'declaration.json'),
        scientific_changes=['method seconds 300 -> 3600; native MaxTime and worker guard derived from remaining root time'],
        path_binding='Frozen modules; matlab_bridge.REPO binds original F:/by/11111 only for unchanged preference directory',
        frozen_at_utc=now(),no_retry=True,seed='fresh original constructor; no supplied history',
        watchdog='Cooperative original root; 120 s cleanup only, then owned process termination; no late evidence',
        minimum_resources={'physical_GiB':2,'commit_GiB':4,'disk_GiB':2})
    write_new(OUT/'declaration.json',declaration)
    print(json.dumps({'prepared':True,'sources':len(original),'declaration_sha256':sha(OUT/'declaration.json')}))

def admission():
    d=read(OUT/'declaration.json')
    if (d['method_seconds'],d['method_calls'],d['post_seconds'],d['post_calls_at_most'])!=(3600,1,60,1):raise ValueError('Budget drift')
    for n,h in d['source_sha256'].items():
        if sha(SNAP/n)!=h:raise ValueError('Frozen source drift: '+n)
    for n,h in d['wrapper_sha256'].items():
        if sha(HERE/n)!=h:raise ValueError('Wrapper drift: '+n)
    if sha(OLD/'declaration.json')!=d['original_declaration_sha256']:raise ValueError('Original identity drift')
    return d

def bind():
    """Use only byte-identical original archived research sources."""
    science=SNAP/'research/chapter3_experiments'
    sys.path[:0]=[str(science/'p0_batch'),str(science)]
    import run_p0, formal_milp, milp, matlab_bridge, partial_bounds
    matlab_bridge.REPO=REPO  # Environmental path only; use original MATLAB prefs.
    return run_p0,formal_milp,milp,matlab_bridge,partial_bounds

def modules_used(d):
    checked={}
    for name,module in list(sys.modules.items()):
        path=getattr(module,'__file__',None)
        if not path:continue
        path=Path(path).resolve()
        if path.is_relative_to(SNAP):
            rel=path.relative_to(SNAP).as_posix()
            if rel not in d['source_sha256'] or sha(path)!=d['source_sha256'][rel]:raise ValueError('Unbound scientific import: '+rel)
            checked[name]=rel
        elif path.is_relative_to(SCIENCE) and not path.is_relative_to(HERE):
            raise ValueError('Current or historical nonfrozen scientific import: '+str(path))
    return checked

def method():
    d=admission();host=context()
    if host['token_is_appcontainer']:raise ValueError('Requires verified host context')
    write_new(OUT/'method_host.json',host)
    t=time.monotonic();p,f,m,b,bounds=bind()
    write_new(OUT/'imports.json',{'seconds':time.monotonic()-t,'modules':modules_used(d),
        'scope':'scientific imports only, same convention as P0; input/init/build/native startup remain billed'})
    write_new(OUT/'method.claim.json',{'utc':now(),'declaration_sha256':sha(OUT/'declaration.json'),'reserved_seconds':SECONDS,'no_retry':True})
    lower={};identity={'input_verified':None}
    def loader(budget):
        write_new(CALL/'method_budget_identity.json',{'start':budget.start,'deadline':budget.deadline,'limit_s':SECONDS,'clock':'monotonic'})
        raw,config,instance=p.fresh_input('base__R1',budget)
        actual=dict(zip(('raw_config_sha256','config_sha256','input_sha256'),map(canonical,(raw,config,instance))))
        identity['input_verified']=actual==d['input_declaration']['input_identities']
        if not identity['input_verified']:raise ValueError('Input differs from P0')
        with budget.phase('comparison_independent_lower_bound'):
            lower['L0']=bounds.independent_lower_bound(instance,None,budget)
        budget.check();return config,instance
    started=time.monotonic();result=None;errors=[]
    try:
        result=f.execute_formal_milp(loader,CALL,seconds=SECONDS,feedback_kind='conditional',
            model_builder=partial(m.build_model,prefilter_deadlines=True,cumulative_precedence=False),
            session_factory=partial(b.MatlabSession,cut_max_iterations=10))
    except BaseException:errors.append(traceback.format_exc())
    method_wall=time.monotonic()-started
    CALL.mkdir(parents=True,exist_ok=True)
    if result is not None:write_new(CALL/'wrapper_raw_result.json',result)
    if lower:write_new(CALL/'independent_bounds.json',lower)
    source_valid=True
    try:admission();loaded=modules_used(d)
    except Exception:source_valid=False;loaded={};errors.append(traceback.format_exc())
    from read_audit import audit_result
    records=audit_result(result,d['input_declaration'],CALL,input_valid=identity['input_verified'],source_valid=source_valid,errors=errors,seconds=SECONDS)
    write_new(OUT/'method_return.json',dict(utc=now(),wall_including_cleanup_s=method_wall,identity=identity,
        errors=errors,records=records,actual_loaded_modules=loaded,post_authorized=records.get('usable_U_J') is not None))
    return 0 if not errors else 2

def post():
    d=admission();returned=read(OUT/'method_return.json')
    if returned['records'].get('usable_U_J') is None:raise ValueError('No audit-usable final SAFE')
    p,_,_,_,_=bind()
    from thermal import Budget,evaluate_candidate
    from schedules import validate_schedule
    result=read(CALL/'wrapper_raw_result.json');candidate=result['safe_candidate'];receipt=result['evaluation']
    write_new(OUT/'post.claim.json',dict(utc=now(),seconds=POST_SECONDS,no_retry=True,candidate_sha256=canonical(candidate),new_U=False))
    root=Budget(seconds=POST_SECONDS)
    raw,config,instance=p.fresh_input('base__R1',root)
    root.check();legality=validate_schedule(instance,candidate);root.check()
    fresh=evaluate_candidate(instance,candidate,config['accuracy_targets'],root)
    write_new(OUT/'postcheck.json',fresh)
    old=tuple(map(F,receipt['weighted_energy_J']));new=tuple(map(F,fresh.get('weighted_energy_J') or [-1,-1]))
    tests=dict(legal=legality.get('state')=='SCHEDULE_VALID_THERMAL_UNCHECKED',safe=fresh.get('state')=='SAFE',
        rankable=fresh.get('rankable_energy') is True,energy_overlap=max(old[0],new[0])<=min(old[1],new[1]),
        full_window=all(s.get('complete') and F(s['covered_until_s'])==F(2,5) for s in fresh.get('scenes',{}).values()),
        all_scenes=set(fresh.get('scenes',{}))==set(candidate['scenes']))
    write_new(OUT/'post_return.json',dict(passed=all(tests.values()),checks=tests,wall_s=root.elapsed,new_U=False,
        context=context(),modules=modules_used(d)))
    return 0 if all(tests.values()) else 2

def terminate_owned(proc):
    import psutil
    if proc.poll() is not None:return []
    parent=psutil.Process(proc.pid)
    owned=parent.children(recursive=True)+[parent]
    ids=[dict(pid=p.pid,created=p.create_time()) for p in owned]
    for p in reversed(owned):
        try:p.terminate()
        except psutil.NoSuchProcess:pass
    _,alive=psutil.wait_procs(owned,timeout=5)
    for p in alive:
        try:p.kill()
        except psutil.NoSuchProcess:pass
    return ids

def supervise():
    d=admission();host=context()
    if not resource_ok(host):
        print(json.dumps({'not_started':'resource_or_context_precheck','context':host}));return 3
    pure=read(OUT/'pure_checks.json')
    if not pure['passed'] or pure['declaration_sha256']!=sha(OUT/'declaration.json'):raise ValueError('Pure checks absent/drift')
    write_new(OUT/'launch.claim.json',dict(utc=now(),host=host,declaration_sha256=sha(OUT/'declaration.json'),no_retry=True))
    start=time.monotonic();deadline=start+CALENDAR;sent=set();phases=[]
    from read_audit import read_checkpoint
    for phase,watchdog in [('method',SECONDS+120),('post',POST_SECONDS+30)]:
        if phase=='post':
            returned=read(OUT/'method_return.json') if (OUT/'method_return.json').exists() else {}
            if not returned.get('post_authorized'):break
            if time.monotonic()+POST_SECONDS+30>=deadline:break
        t=time.monotonic()
        with (OUT/(phase+'.stdout.txt')).open('xb') as log:
            proc=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),phase],cwd=str(REPO),stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            stopped=False;terminated=[]
            while proc.poll() is None:
                stamp=time.monotonic()
                if phase=='method' and (CALL/'method_budget_identity.json').exists():
                    try:
                        root=read(CALL/'method_budget_identity.json')
                        for cut in CHECKPOINTS:
                            if cut not in sent and stamp>=root['start']+cut:
                                snap=read_checkpoint(CALL,cut,stamp)
                                write_new(OUT/'checkpoints'/f'{cut:04d}.json',snap);sent.add(cut)
                                print(json.dumps({'checkpoint':cut,'observed_elapsed':stamp-root['start']}),flush=True)
                    except (json.JSONDecodeError,PermissionError):pass
                if stamp>=min(t+watchdog,deadline):
                    stopped=True;terminated=terminate_owned(proc);break
                time.sleep(0.5)
            proc.wait(timeout=15)
        phases.append(dict(phase=phase,returncode=proc.returncode,wall_s=time.monotonic()-t,watchdog_stop=stopped,terminated=terminated))
        print(json.dumps(phases[-1]),flush=True)
        if stopped or proc.returncode!=0:break
    # If scientific method stops early, do not run until remaining checkpoints.
    write_new(OUT/'terminal.json',dict(utc=now(),phases=phases,wall_s=time.monotonic()-start,
        research_calls=int((OUT/'method.claim.json').exists()),post_calls=int((OUT/'post.claim.json').exists()),
        observed_checkpoints=sorted(sent),not_reached_checkpoints=sorted(set(CHECKPOINTS)-sent),no_retries=True))
    return 0 if phases and all(p['returncode']==0 and not p['watchdog_stop'] for p in phases) else 2

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','method','post','execute'])
    args=parser.parse_args()
    raise SystemExit({'prepare':prepare,'method':method,'post':post,'execute':supervise}[args.action]() or 0)
