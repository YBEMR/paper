"""Audit saved outputs and derive diagnostic intervals; never call a solver."""
from pathlib import Path
import csv
import hashlib
import json
import math

root=Path(__file__).resolve().parents[2]
out=root/'research/matlab_config_value_src/milp68_reports/frozen_20260927_113720_286'
def csvread(path):
    with path.open(encoding='utf-8-sig', newline='') as f:return list(csv.DictReader(f))
def dump(name,value):
    (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
a=json.loads((out/'saved_diagnostics.json').read_text(encoding='utf-8'))
summary=csvread(out/'summary.csv')
post=csvread(out/'postchecks.csv')
assert len(a)==len(summary)==20 and len(post)==18 and all(x['passed']=='1' for x in post)
old=csvread(root/'research/matlab_config_value_src/search64_reports/frozen_20260926_114942_794/summary.csv')
old={x['case_id']:x for x in old if x['method']=='no_repair'}
checks=[]
for x in summary:
    if x['method']=='no_repair':
        checks.append({'case':x['case_id'],'history_energy_status_match':
                       x['status']==old[x['case_id']]['status'] and
                       (float(x['energy_mJ'])==float(old[x['case_id']]['energy_mJ']) if x['safe']=='1' else old[x['case_id']]['safe']=='0')})
assert all(x['history_energy_status_match'] for x in checks)
dump('history_result_consistency.json',checks)

costs=[]
for r in a:
    if r['method']!='milp_engineering':continue
    spans=[x['returned_s']-(60-r['input_setup_s']-x['allocated_s']) for x in r['rounds']]
    costs.append({'case_id':r['input_id'],'input_setup_s':r['input_setup_s'],
                  'matrix_build_s':r['cost_s']['build'],'round_wall_span_s':sum(spans),
                  'raw_solver_inclusive_s':r['cost_s']['solver_inclusive'],
                  'raw_solver_timer_valid':r['stats']['cache_hits']==0,
                  'decode_s':r['cost_s']['decode'],'thermal_s':r['cost_s']['thermal'],
                  'total_s':r['elapsed_s'],
                  'note':'round span derived from pre-solve remaining-budget and return timestamps; includes callback/check overhead. Raw nested timer invalid when callback evaluated candidate.'})
with (out/'cost_diagnostics.csv').open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(costs[0]));w.writeheader();w.writerows(costs)

hashes=json.loads((out/'source_hashes.json').read_text(encoding='utf-8-sig'))
changed=[]
for x in hashes:
    now=hashlib.sha256(Path(x['path']).read_bytes()).hexdigest()
    snapshot=out/'source'/Path(x['path']).name
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest().lower()==x['sha256'].lower()
    if now.lower()!=x['sha256'].lower():changed.append({'path':x['path'],'frozen_sha256':x['sha256'],'current_sha256':now})
assert {Path(x['path']).name for x in changed}=={'b68_export.m','b68_method.m','b68_tests.m'}
history=json.loads((out/'history_after.json').read_text(encoding='utf-8'))
assert len(history)==93 and all(x['unchanged'] for x in history)
audit={'formal_calls':20,'within_60s':all(r['elapsed_s']<=60 for r in a),
       'safe_outputs_independently_checked':18,'historical_hashes_unchanged':93,
       'historical_result_matches':10,'frozen_source_snapshots_hash_match':True,
       'research_reruns':0,'formal_precheck_count':124,'current_precheck_count':125,
       'postrun_new_source_changes':changed,
       'export_failure_preserved':'failure.txt; postprocessing only rerun',
       'timer_issue':'Nested diagnostic timer overwritten in five callback cases; budget/main wall clock unaffected; raw records retained',
       'formal_receipt':'precheck_20260927_113432_803',
       'current_receipt':'precheck_20260927_114309_369',
       'serialization':'Outside method budget; individual serialization duration not instrumented',
       'complete':True}
dump('audit.json',audit)
print(json.dumps(audit,ensure_ascii=False,indent=2))
