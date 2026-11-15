"""Read-only recovery after post-stop memory telemetry failure; no propagation."""
import json,sys
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from support import paths,read,save,verify_sources,sha
paths()
from archive import read_result
from runtime import digest,semantic
from schedules import validate_schedule
from h02_pair_preflight.receipts import safe_receipt

folder=root/'execution/01_U07__n24_A';raw=read_result(folder/'method/result.json')
instance=read(folder/'method/input_instance.json');config=read(folder/'method/input_config.json')
events=[json.loads(x) for x in (folder/'journal.jsonl').read_text(encoding='utf-8').splitlines()]
calls=[{k:v for k,v in e.items() if k!='event'} for e in events if e['event']=='EVALUATION_RETURN']
assess=[e for e in events if e['event']=='ASSESSMENT_END']
assert raw['run_terminal']=='BUDGET_EXHAUSTED' and raw['state']=='SAFE'
assert len(calls)==len([r for r in raw['evaluations'] if not r.get('cache_hit')])
bykey={r['candidate_sha256']:r for r in calls};accepted=0;best=None;current=None
for row in raw['evaluations']:
    assert row['candidate_sha256']==digest(row['candidate'])
    receipt=deepcopy(row['receipt'])
    legal=validate_schedule(instance,row['candidate'])
    assert digest(legal)==receipt['legality_sha256'];receipt['legality']=legal
    assert receipt['semantic_sha256']==bykey[row['candidate_sha256']]['semantic_sha256']
    if 'evaluation_admitted_at_s' in row:assert row['evaluation_admitted_at_s']<180
    if not row['accepted_safe']:continue
    e=safe_receipt(instance,row['candidate'],receipt,config['accuracy_targets'],300)
    assert e==row['energy'];accepted+=1
    lo,hi=F(e['lower']),F(e['upper'])
    if row['phase']=='initialization':
        replace=best is None or hi<best[1]
        if replace:best=(lo,hi)
    else:
        if current is None:current=tuple(F(raw['initial_safe_snapshot']['energy'][k]) for k in ['lower','upper'])
        replace=hi<current[0]
        if replace:current=(lo,hi)
    assert replace==row['incumbent_replaced']
final=safe_receipt(instance,raw['safe_candidate'],raw['evaluation'],config['accuracy_targets'],300)
key=digest(raw['safe_candidate']);assert digest(semantic(raw['evaluation']))==bykey[key]['semantic_sha256']
plan=read(root/'execution/freeze.json')
assert digest(instance)==plan['inputs']['U07__n24']['instance'] and digest(config)==plan['inputs']['U07__n24']['config']
for name,h in plan['code_sha256'].items():
    archived=root/'versions/v1/support.py' if name=='support.py' and (root/'versions/v1/support.py').exists() else root/name
    assert sha(archived)==h,name
source=verify_sources()
result={'status':'RECOVERED_READ_ONLY','case':'U07__n24','arm':'A','search_terminal':raw['run_terminal'],
  'worker_terminal':'POST_STOP_MEMORY_API_ERROR','search_invocations':1,'additional_scientific_calls':0,
  'final_SAFE_contract_valid':True,'accepted_safe_receipts_rechecked':accepted,'numeric_calls':len(calls),
  'returned_states':{s:sum(r['state']==s for r in calls) for s in ['SAFE','UNRESOLVED','THERMAL_VIOLATION','INTERRUPTED']},
  'final_energy':final,'final_candidate_sha256':key,'final_formed_at_s':raw['evaluation']['completed_at_elapsed_s'],
  'initial_energy':raw['initial_safe_snapshot']['energy'],'initial_candidate_sha256':raw['initial_safe_snapshot']['candidate_sha256'],
  'method_charged_s':raw['timing']['method_elapsed_s'],'process_wall_s':read(root/'execution/batch_summary.json')['returns'][0]['process_wall_s'],
  'physical_panels':sum(r['new_panels'] for r in calls),'extremum_calls':sum(r['new_extrema'] for r in calls),
  'refinements':sum(r['new_refinements'] for r in calls),'strict_search_improvements':raw['graph_strict_improvements'],
  'full_hash_hits':raw['cache_hits'],'sources_verified':source,
  'missing_irrecoverable':['worker_peak_memory','worker_cpu_time','observer_total_time','cache_accept_callback_total_time','worker_read_only_audit_time'],
  'note':'Original worker did not write summary.json or numerical_calls.json. Derived recovery is separate; no fabricated CPU/memory measurements or overwritten failure status.'}
save(root/'repair/recovered_A_evidence.json',result);save(root/'repair/recovered_A_numerical_calls.json',calls)
print(json.dumps(result,ensure_ascii=False))
