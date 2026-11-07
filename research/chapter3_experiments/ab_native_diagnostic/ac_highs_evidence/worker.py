"""One run with native API readback, no solution injection, guarded callback."""
from pathlib import Path
from datetime import datetime,timezone
import json,time,sys,math
import numpy as np,highspy
from model_gate import prepare,compare
R=Path(__file__).resolve().parent
def utc():return datetime.now(timezone.utc).isoformat()
def safe(x):
 if isinstance(x,np.generic):return safe(x.item())
 if isinstance(x,float) and not math.isfinite(x):return str(x)
 if isinstance(x,np.ndarray):return safe(x.tolist())
 if isinstance(x,dict):return {k:safe(v) for k,v in x.items()}
 if isinstance(x,(tuple,list)):return [safe(v) for v in x]
 return x
def save(n,d):
 with (R/n).open('x',encoding='utf-8') as f:json.dump(safe(d),f,indent=2,allow_nan=False);f.write('\n')
def main():
 origin=float(sys.argv[1]);deadline=origin+420
 h,d,m,ints,gate,rs,cs=prepare(R/'request.mat');gate['utc']=utc();gate['root_elapsed_s']=time.monotonic()-origin
 np.savez(R/'SCALING_CERT.npz',row_scales=rs,column_scales=cs)
 save('NATIVE_GATE.json',gate);(R/'GATE_READY').write_text('complete\n');h.setOptionValue('log_file',str(R/'native.log'))
 # Parent observes native gate and current memory before permitting the one run.
 while not (R/'RUN_ALLOWED.json').exists():
  if (R/'stop').exists() or time.monotonic()>deadline or time.monotonic()-origin>60:raise RuntimeError('No timely run permission; no solve')
  time.sleep(.1)
 events=[];last=0.;snapshots=[];native_origin=[None]
 def record_event(row):
  events.append(row)
  with (R/'CALLBACKS_LIVE.jsonl').open('a',encoding='utf-8') as stream:
   stream.write(json.dumps(safe(row),allow_nan=False)+'\n')
 def interrupt(e):
  nonlocal last
  now=time.monotonic();reason='stop_file' if (R/'stop').exists() else ('root_deadline' if now>=deadline else ('native_300_seconds' if native_origin[0] is not None and now-native_origin[0]>=300 else None))
  if reason:
   e.interrupt();record_event({'utc':utc(),'root_elapsed_s':now-origin,'type':'interrupt','reason':reason})
  elif now-last>2:
   last=now;out=e.data_out;record_event({'utc':utc(),'root_elapsed_s':now-origin,'type':'observe',
     'running_time':out.running_time,'primal_bound':out.mip_primal_bound,'dual_bound':out.mip_dual_bound,'gap':out.mip_gap})
 def improving(e):
  now=time.monotonic();elapsed=now-native_origin[0];out=e.data_out
  row={'utc':utc(),'root_elapsed_s':now-origin,'native_elapsed_s':elapsed,'type':'improving_solution','objective':out.objective_function_value,
    'primal_bound':out.mip_primal_bound,'dual_bound':out.mip_dual_bound,'gap':out.mip_gap,'timely':elapsed<=300 and now<deadline and not (R/'stop').exists()}
  if row['timely']:
   x=np.asarray(out.mip_solution,float).copy()
   if x.size!=m.shape[1] or not np.isfinite(x).all():raise ValueError('Invalid callback solution')
   name='callback_%04d.npz'%(len(snapshots)+1);np.savez(R/name,x=x);row['vector_file']=name;snapshots.append(row.copy())
  record_event(row)
 try:
  h.cbMipInterrupt.subscribe(interrupt);h.cbSimplexInterrupt.subscribe(interrupt);h.cbIpmInterrupt.subscribe(interrupt);h.cbMipImprovingSolution.subscribe(improving)
 except Exception as e:raise RuntimeError('Interrupt protection could not be registered') from e
 if time.monotonic()>=deadline or (R/'stop').exists():raise RuntimeError('Gate cancelled before solve')
 start=time.monotonic();native_origin[0]=start;started=utc();save('CALL_STARTED.json',{'utc':started,'root_elapsed_s':start-origin,'native_run_calls':1,'no_x0':True})
 print('HIGHS_NATIVE_CALL_STARTED '+started,flush=True)
 status=h.run();ended=utc();wall=time.monotonic()-start
 info=h.getInfo();solution=h.getSolution();model_status=h.getModelStatus()
 fields=['valid','objective_function_value','mip_dual_bound','mip_gap','mip_node_count','simplex_iteration_count','ipm_iteration_count','primal_solution_status','dual_solution_status',
  'num_primal_infeasibilities','max_primal_infeasibility','sum_primal_infeasibilities','max_integrality_violation','num_dual_infeasibilities','max_dual_infeasibility','primal_dual_integral']
 output={key:getattr(info,key) for key in fields if hasattr(info,key)}
 valid=bool(solution.value_valid);x=np.asarray(solution.col_value,float) if valid else np.array([])
 readback=compare(h,d,m,ints);has=bool(len(x)==m.shape[1] and np.isfinite(x).all())
 if has:np.savez(R/'returned_vector.npz',x=x)
 selected='returned_vector.npz' if has and wall<=300 else (snapshots[-1]['vector_file'] if snapshots else None)
 residual=None
 if has:
  ni=d['A'].shape[0];v=m@x;residual={'inequality_max':float(max(0,np.max(v[:ni]-d['b'].ravel()))),
   'equality_max':float(max(abs(v[ni:]-d['beq'].ravel()))),'bound_max':float(max(0,max(d['lb'].ravel()-x),max(x-d['ub'].ravel()))),
   'integer_max':float(max(abs(x[ints!=0]-np.rint(x[ints!=0])))),'c_dot_x':float(d['c'].ravel()@x),'vector_sha256':__import__('hashlib').sha256(x.tobytes()).hexdigest()}
 save('CALLBACKS.json',events)
 save('SOLVER_RESULT.json',{'started_utc':started,'ended_utc':ended,'native_wall_seconds':wall,'native_run_calls':1,'run_status':str(status),
  'model_status':str(model_status),'model_status_string':h.modelStatusToString(model_status),'info':output,'solution_value_valid':valid,'x_length':len(x) if has else 0,
  'equivalent_matrix_residual':residual,'public_model_after_run':readback,'runtime_seconds':h.getRunTime(),'completed_at_root_s':time.monotonic()-origin,
  'floating_lower_bound_only':True,'exact_certificate':False,'native_internal_mip_snapshot_available':False,
  'final_vector_returned_within_native300':bool(has and wall<=300),'timely_callback_count':len(snapshots),'selected_timely_vector_file':selected,
  'selection_rule':'final only if returned within300s; otherwise latest timely improving callback; never saved historical x0'})
 print('HIGHS_WORKER_COMPLETED '+utc(),flush=True)
if __name__=='__main__':main()
