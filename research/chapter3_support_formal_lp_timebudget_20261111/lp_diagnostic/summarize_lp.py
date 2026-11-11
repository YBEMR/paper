"""Summarize already completed LP records; no numerical optimization."""
import csv
import hashlib
import json
import re
from pathlib import Path

h=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_text())
plan=read(h/'plan.json')
rows=[]
for v in plan['order']:
 r=read(h/v/'result.json');ret=read(h/v/'worker_return.json')
 assert r['new_lp_calls']==1 and r['seven_arrays_unchanged']
 log=(h/v/'stdout.log').read_text()
 native_objectives=re.findall(r'^\s*Objective\s+value\s*:\s*([-+0-9.eE]+)\s*$',log,re.M)
 native_states=re.findall(r'^\s*Model\s+status\s*:\s*(.*?)\s*$',log,re.M)
 native_iterations=re.findall(r'^\s*Simplex\s+iterations\s*:\s*(\d+)\s*$',log,re.M)
 rows.append(dict(variant=v,status=r['status'],message=r['message'],objective=r['objective'],
     termination_reason=r['termination_reason'],solver_reported_success=r.get('success'),
     interface_bound=r['solver_reported_bound'],
     terminal_log_objective=float(native_objectives[-1]) if native_objectives else None,
     terminal_log_model_status=native_states[-1] if native_states else None,
     terminal_log_iterations=int(native_iterations[-1]) if native_iterations else None,
     vector_returned=(h/v/'solution.npz').exists(),
     original_primal_residual_within_1e_9=r.get('primal_residual_within_1e_9'),
     objective_recomputed=r.get('objective_recomputed'),numerical_dual_checks=r.get('numerical_dual_checks'),
     iterations=r['iterations'],solver_call_s=r['solver_call_s'],method_elapsed_s=r['method_elapsed_s'],
     completed_within_budget=r['completed_within_method_budget'],worker_wall_s=ret['wall_s'],
     worker_wall_within_300_s=ret['wall_s']<=300,
     load_and_verification_s=r.get('load_and_verification_s'),
     solver_returned_at_method_s=r.get('solver_returned_at_s'),
     iteration_cap=plan['options']['maxiter'],
     native_time_limit_s=r['options']['time_limit'],residuals=r['residuals'],
     source_mat_sha256=r['source_sha256'],seven_arrays_unchanged=r['seven_arrays_unchanged'],
     worker_returncode=ret['returncode'],watchdog_expired=ret['watchdog_expired'],
     started_utc=r['started_utc'],ended_utc=r['ended_utc'],
     original_integer_indices=plan['records'][v]['integer_indices']))
with (h/'comparison.csv').open('x',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
with (h/'summary.json').open('x') as f:
 json.dump(dict(plan_sha256=hashlib.sha256((h/'plan.json').read_bytes()).hexdigest(),
      new_lp_calls=2,new_milp_calls=0,new_thermal_calls=0,rows=rows,
      missing_value_semantics='null/blank objective and residuals mean no vector/objective returned; never zero or a SAFE result',
      comparison_scope='archived hold-last matrices with common SciPy/HiGHS settings; separate from new auto-L static construction',
      objective_and_bound_semantics='Interface fun/x absent means no auditable returned point/objective. Terminal-log objective is retained as internal solver output only. Separate best bound is not exposed and none is independently certified.',
      timing_semantics='method_elapsed_s includes imports/load/native/array/returned-point checks but is sampled before final JSON write and stdout. worker_wall_s additionally covers process startup/archive/exit; watchdog330 is not extra scientific budget.',
      residual_semantics='Null means no returned-vector residual check possible. When present, original arrays are checked in floating-point arithmetic independently of solver residual outputs, not exact rational or interval certification.'),f,indent=2)
 f.write('\n')
print(json.dumps(rows,indent=2))
