"""Read saved K131 records only; no solver, model, decoding or thermal calls."""
from pathlib import Path
import hashlib, json

repo=next(p for p in Path(__file__).resolve().parents if (p/'AGENTS.md').is_file() and (p/'RESEARCH_BRIEF.md').is_file())
root=repo/'research/chapter3_experiments/results/fixed_unit_pair02'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
checks=[]
def check(name,condition):
    checks.append({'name':name,'passed':bool(condition)})
    if not condition: raise AssertionError(name)

d=read(root/'declaration.json'); l=read(root/'ledger.json'); f=read(root/'analysis01/facts.json')
v=read(root/'independent_payload_audit.json'); gate=read(root/'checks.json')
check('terminal_blocked_two_consumed_no_retries',l['state']=='BLOCKED' and l['consumed']==2 and len(l['calls'])==2)
check('declared_call_and_time_caps',d['method_call_limit']==2 and d['per_method_budget_s']==300)
check('two_terminal_statuses_preserved',[x['state'] for x in l['calls']]==['COMPLETED','TECHNICAL_BLOCK'])
check('precheck_129_matches',gate['passed'] and gate['count']==129 and sha(root/'checks.json')==d['checks_sha256'])
check('135_source_snapshots_and_current_match',len(d['source_sha256'])==135 and all(sha(repo/n)==h and sha(root/'source_snapshot'/n)==h for n,h in d['source_sha256'].items()))
check('precheck_source_map_matches',gate['source_sha256']==d['source_sha256'])
check('raw_receipt_hashes_unchanged',all(sha(root/n)==h for n,h in f['raw_hashes_before'].items()))
check('same_fresh_seed_and_initial_energy',f['comparison']['identical_fresh_seed_candidate_and_energy'] and v['fresh_seed_identical'] and v['initial_energy_interval_identical'])
check('all_final_full_SAFE_receipts_verified',all(x['final_SAFE_receipt_verified'] and not x['stored_receipt_errors'] for x in f['calls']))
check('technical_status_and_safe_seed_coexist',f['calls'][1]['technical_state']=='FAILED' and f['comparison']['new_result_is_verified_seed_only'])
check('all_original_full_window_and_budget_receipts',all(s['complete'] and s['covered_until_s']=='2/5' and s['within_300_s'] and s['all_peak_uppers_below_80'] for j in v['jobs'].values() for s in j['scene_checks'].values()))
check('method_times_within_300',all(c['timing']['method_elapsed_s']<=300 for c in l['calls']))
check('both_graceful_closed_identity_confirmed',all(c['cleanup']['cleanup_status']=='graceful_closed' and c['cleanup']['returncode']==0 and c['cleanup']['observed_tree_verified_terminated'] for c in l['calls']))
check('quality_pair_not_ranked',not f['comparison']['quality_pair_completed'] and not f['comparison']['performance_ranking_valid'])
check('no_false_global_proofs',all(not x['independently_proven_optimal'] and not x['independently_proven_infeasible'] for x in f['calls']))
check('no_thermal_violation_or_feedback_claim',all(x['feedback_records']==0 and x['timely_distinct_saved_violation_receipts']==0 for x in f['calls']))
check('native_x0_same_not_exact_certificate',v['payload']['native_received_x0_bitwise_identical'] and not v['payload']['exact_feasibility_certificate'])
check('native_minus2_and_empty_x_preserved',v['payload']['native_exitflag']==-2 and v['payload']['native_x_size']==0)
for doc,marker in [('RESEARCH_BRIEF.md','K.131／D155'),('research/03_证据与检索记录.md','E576：'),('research/第三章当前进展与正式实验推进计划_审查稿.md','## K.131：'),('research/chapter3_experiments/README.md','3.12aj')]:
    check('state_registered_'+doc,marker in (repo/doc).read_text(encoding='utf-8'))
out={'stage':'K131','scope':'stored-record and hash checks only; not solver/thermal certification',
     'passed':all(x['passed'] for x in checks),'count':len(checks),'checks':checks,
     'new_research_calls':2,'extra_solves_or_thermal_evaluations':0,
     'script_sha256':sha(Path(__file__))}
(root/'verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(root/'verify_saved_records.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps({'passed':out['passed'],'count':out['count']},ensure_ascii=False))
