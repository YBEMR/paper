"""Independent highspy diagnostic:420 root, native300,2GiB,owned20/40 cleanup."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess,sys,time,re
R=Path(__file__).resolve().parent;P=Path('C:/Users/86130/Documents/Codex/2026-11-04/task/abac_exact_eq_verify_20261106T135623Z')
def utc():return datetime.now(timezone.utc).isoformat()
def save(n,d):
 with (R/n).open('x',encoding='utf-8') as f:json.dump(d,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def main():
 origin=time.monotonic();started=utc();deadline=origin+420
 plan_path=R/'PLAN.json'
 plan=json.loads(plan_path.read_bytes())
 approval=json.loads((R/'APPROVAL.json').read_bytes())
 if approval != {'plan_sha256':hashlib.sha256(plan_path.read_bytes()).hexdigest(),'authorization':'user_confirmed_new_single_native_call'}:
  raise ValueError('New single-call approval not bound to frozen plan')
 for name,digest in plan['source_sha256'].items():
  if hashlib.sha256((R/name).read_bytes()).hexdigest()!=digest:raise ValueError('Prepared source drift: '+name)
 sys.path[:0]=[str(P),str(P/'native_source/research/chapter3_experiments'),str(P/'baseline/research/chapter3_experiments'),str(P/'baseline')]
 import psutil,matlab_bridge as bridge
 from cancellation import CancellationState,DeferredSignals,CancelSafeProcess
 available=psutil.virtual_memory().available
 visible=[p.info for p in psutil.process_iter(['pid','name','create_time']) if 'matlab' in (p.info['name'] or '').lower()]
 save('PREFLIGHT.json',{'utc':utc(),'available_GiB':available/2**30,'visible_matlab':visible,'root_seconds':420,'native_seconds':300,'memory_stop_bytes':2**31,'launch_margin_bytes':int(2.25*2**30)})
 if available<2.25*2**30 or visible:raise RuntimeError('Resource margin/visible MATLAB gate failed; no worker launched')
 frozen=json.loads((P/'FROZEN.json').read_text(encoding='utf-8'))
 for n,h in frozen['files'].items():
  if n.startswith(('baseline/','inputs/')) and hashlib.sha256((P/n).read_bytes()).hexdigest()!=h:raise ValueError('Science source/input drift')
 if hashlib.sha256((R/'request.mat').read_bytes()).hexdigest()!='bde54760351d94569dbc7524dd7fc1e30eb1efe5fa97d9e9a59938fe7ec44af7':raise ValueError('Input drift')
 save('CLAIM.json',{'started_utc':started,'max_launches':1,'max_native_runs':1,'automatic_retry':False,'formal_comparison':False,'root_seconds':420,
  'options':{'small_matrix_value':1e-12,'presolve':'off','time_limit':300.0,'mip_rel_gap':0.0,'threads':1},
  'threads_reason':'bounded memory and CPU impact on user computer; independent diagnostic, no speed-comparison claim',
  'admission':'native300 cutoff for publication; original linear and full thermal acceptance completed within420 root; no historical seed'})
 argv=['C:/Users/86130/Documents/Codex/2026-11-04/task/ac_highspy_20261107T013936Z/env/Scripts/python.exe','-B','-u',str(R/'worker.py'),str(origin)]
 state=CancellationState();owner=bridge.MatlabSession.__new__(bridge.MatlabSession)
 owner.workdir=R;owner.clock=time.monotonic;owner.started=origin;owner.closed=False;owner.proc=None;owner.log=None
 reason='WORKER_EXITED';failure=None;samples=[];permission=False;log_dims=None
 with DeferredSignals(state):
  try:
   owner.log=(R/'worker.log').open('wb');launch=utc()
   owner.proc=CancelSafeProcess(subprocess.Popen(argv,cwd=R,stdout=owner.log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW),state=state,clock=time.monotonic)
   owner.process_tree=bridge._capture_owned_process_tree(owner.proc,phase='launch')
   save('LAUNCH.json',{'utc':launch,'argv':argv,'pid':owner.proc.pid,'tree':owner.process_tree});print(json.dumps({'event':'WORKER_LAUNCHED','utc':launch,'pid':owner.proc.pid}),flush=True)
   if not owner.process_tree.get('root_identity_verified'):raise RuntimeError('Owned process identity unavailable')
   while owner.proc.poll() is None:
    now=time.monotonic();row={'utc':utc(),'elapsed_s':now-origin,'available_bytes':psutil.virtual_memory().available};samples.append(row)
    with (R/'memory.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row)+'\n')
    owner.process_tree=bridge._capture_owned_process_tree(owner.proc,owner.process_tree,phase='monitor')
    if not owner.process_tree.get('capture_complete'):reason='IDENTITY_UNRESOLVED';break
    if row['available_bytes']<2**31:reason='LOW_MEMORY';break
    if state.requested:reason='USER_CANCELLED';break
    if now>=deadline:reason='ROOT_DEADLINE';break
    if not permission and (R/'GATE_READY').exists():
     gate=json.loads((R/'NATIVE_GATE.json').read_text())
     if not gate['gate_passed'] or not gate['readback']['all_passed'] or gate['scaling_audit']['predicted_deletions']!=0 or gate['effective_options']['small_matrix_value']['value']!=1e-12:reason='NATIVE_GATE_FAILED';break
     if deadline-now<330:reason='INSUFFICIENT_REMAINING_ROOT';break
     save('RUN_ALLOWED.json',{'utc':utc(),'elapsed_s':now-origin,'available_GiB':row['available_bytes']/2**30,'native_gate_passed':True})
     permission=True;print(json.dumps({'event':'NATIVE_GATE_PASSED_RUN_ALLOWED','utc':utc(),'available_GiB':row['available_bytes']/2**30}),flush=True)
    log=(R/'worker.log').read_text(encoding='utf-8',errors='replace')
    found=re.search(r'Solving MIP model with:\s*(\d+) rows\s*(\d+) cols.*?\n\s*(\d+) nonzeros',log,re.S)
    if found:
     log_dims=list(map(int,found.groups()))
     if log_dims!=[85266,14014,906181]:reason='BACKEND_DIMENSION_MISMATCH';break
    time.sleep(.25)
  except BaseException as e:reason='SUPERVISOR_ERROR';failure={'type':type(e).__name__,'message':str(e)}
  finally:
   if owner.proc is not None:owner.close()
  path=R/'SOLVER_RESULT.json';result=json.loads(path.read_text()) if path.exists() else None
  admissible=(reason=='WORKER_EXITED' and owner.cleanup.get('returncode')==0 and bridge.cleanup_is_complete(owner.cleanup)
   and time.monotonic()<deadline and result and result['public_model_after_run']['all_passed'] and log_dims==[85266,14014,906181])
  import posterior
  if Path(posterior.__file__).resolve()!=R/'posterior.py':raise RuntimeError('Wrong posterior module')
  post=posterior.validate(R,result,origin,deadline,state) if admissible else {'state':'NOT_EVALUATED_RUN_NOT_ADMISSIBLE','SAFE_claim':False}
 record={'started_utc':started,'ended_utc':utc(),'elapsed_s':time.monotonic()-origin,'reason':reason,'failure':failure,'native_run_allowed':permission,
  'native_log_dimensions':log_dims,'minimum_available_GiB':min((s['available_bytes']/2**30 for s in samples),default=available/2**30),
  'cleanup':getattr(owner,'cleanup',None),'cleanup_complete':bridge.cleanup_is_complete(getattr(owner,'cleanup',None)),
  'solver':result,'post_validation':post,'root_seconds':420,'native_seconds':300,'formal_comparison':False,'exact_certificate':False,'automatic_retries':0}
 save('RESULT.json',record)
 print(json.dumps({k:record[k] for k in ['started_utc','ended_utc','elapsed_s','reason','minimum_available_GiB','cleanup_complete']}|{'post_state':post['state']}),flush=True)
 return 0 if admissible else 2
if __name__=='__main__':raise SystemExit(main())
