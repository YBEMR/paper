"""Summarize already completed LP records; no numerical optimization."""
import csv
import hashlib
import json
from pathlib import Path

h=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_text())
plan=read(h/'plan.json')
rows=[]
for v in plan['order']:
 r=read(h/v/'result.json');ret=read(h/v/'worker_return.json')
 assert r['new_lp_calls']==1 and r['seven_arrays_unchanged']
 rows.append(dict(variant=v,status=r['status'],message=r['message'],objective=r['objective'],
     iterations=r['iterations'],solver_call_s=r['solver_call_s'],method_elapsed_s=r['method_elapsed_s'],
     completed_within_budget=r['completed_within_method_budget'],
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
      comparison_scope='archived hold-last matrices with common SciPy/HiGHS settings; separate from new auto-L static construction'),f,indent=2)
 f.write('\n')
print(json.dumps(rows,indent=2))
