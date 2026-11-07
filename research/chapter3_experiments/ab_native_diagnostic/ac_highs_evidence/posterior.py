"""No seed fallback. Check native points after cleanup within the original root."""
from pathlib import Path
import hashlib,json,time
def validate(root,result,origin,deadline,cancellation):
 root=Path(root);vectors=[]
 if result:
  # Final vector is in original native MAT; callback vectors in the raw JSON.
  for i,e in enumerate(result.get('events',[]),1):
   if e.get('x'):vectors.append(('callback%d'%i,e['x']))
 if not result:return {'state':'NO_NATIVE_RESULT','candidates':[],'SAFE_claim':False}
 report={'state':'NO_RETURNED_CANDIDATE','candidates':[],'SAFE_claim':False,'scope':'posterior only, no solver feedback or retry'}
 try:
  import numpy as np
  # HiGHS returned vector; no saved reference x0 fallback
  selected=result.get('selected_timely_vector_file'); raw=np.load(root/selected)['x'].reshape(-1) if selected else np.array([])
  if raw.size:vectors.insert(0,('final',raw))
  if not vectors:return report
  from timing import MethodBudget
  from shared_mapping_adapter import ParentOriginClock,payload_sha256
  from native_entry_prepared import load_frozen_inputs
  from milp import build_model,decode
  from scene_method import DEFAULT_BUILDER_OPTIONS
  from scene_adapter import evaluate_partial_scene
  from thermal import _accuracy
  import psutil,matlab_bridge
  class Budget(MethodBudget):
   def check(self):
    super().check();cancellation.raise_if_requested()
    available=psutil.virtual_memory().available
    with (root/'post_memory.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps({'elapsed_s':self.elapsed,'available_bytes':available})+'\n')
    if available<2**31:raise MemoryError('Posterior available memory below2GiB')
  b=Budget(420,clock=ParentOriginClock(time.monotonic,origin));b.check()
  P=Path('C:/Users/86130/Documents/Codex/2026-11-04/task/abac_exact_eq_verify_20261106T135623Z');frozen=json.loads((P/'FROZEN.json').read_text(encoding='utf-8'))
  for name,h in frozen['files'].items():
   if name.startswith(('baseline/','inputs/')) and hashlib.sha256((P/name).read_bytes()).hexdigest()!=h:raise ValueError('Original source/input drift')
  config,instance=load_frozen_inputs(b,folder=P/'inputs');mapping={'A.pre':'CPU1','A.main':'NPU0','A.post':'CPU1'}
  model=build_model(instance,config,budget=b,fixed_scene_id='AC_offset_0ms',fixed_shared_deployment=mapping,**DEFAULT_BUILDER_OPTIONS)
  payload=model.as_solver_dict()
  if payload_sha256(payload)!='7c6454a946273f5ccc2d76b0ebfa264a2fee7ce326de537b474db9bb493c6e1c':raise ValueError('Original AC payload identity mismatch')
  seen=set()
  for source,vector in vectors:
   b.check();x=np.asarray(vector,dtype=float).reshape(-1);h=hashlib.sha256(x.tobytes()).hexdigest()
   if h in seen:continue
   seen.add(h);row={'source':source,'vector_sha256':h,'completed_within_root':False}
   try:
    try:
     row['original_numeric_admission']=matlab_bridge._prepare(payload,x0=x)['x0_validation'];row['original_linear_pass']=True
    except Exception as error:
     row['original_linear_pass']=False;row['original_numeric_error']={'type':type(error).__name__,'message':str(error)}
    candidate=decode(model,x);receipt=evaluate_partial_scene(instance,'AC_offset_0ms',mapping,candidate,_accuracy(config['accuracy_targets']),b)
    row.update(candidate=candidate,receipt=receipt,completed_at_s=b.elapsed,completed_within_root=b.elapsed<420)
   except Exception as e:row['error']={'type':type(e).__name__,'message':str(e)}
   report['candidates'].append(row)
   with (root/('POST_CANDIDATE_%03d.json'%len(report['candidates']))).open('x',encoding='utf-8') as f:json.dump(row,f,ensure_ascii=False,indent=2);f.write('\n')
  report['SAFE_claim']=any(r.get('original_linear_pass') and r.get('completed_within_root') and (r.get('receipt') or {}).get('state')=='SAFE' and (r.get('receipt') or {}).get('rankable_energy') for r in report['candidates'])
  report['state']='SAFE_RETURNED_CANDIDATE' if report['SAFE_claim'] else 'NO_ACCEPTED_SAFE_CANDIDATE'
 except BaseException as e:report.update(state='POSTERIOR_UNRESOLVED',error={'type':type(e).__name__,'message':str(e)})
 return report
