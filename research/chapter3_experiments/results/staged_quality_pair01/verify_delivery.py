"""Audit stored K138 delivery; no model, thermal evaluator, optimizer or process."""
from pathlib import Path
from fractions import Fraction as F
import hashlib
import json
import re

HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'AGENTS.md').is_file())
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
d=read(HERE/'declaration.json'); l=read(HERE/'ledger.json')
f=read(HERE/'analysis01/facts.json'); v=read(HERE/'verification.json')
old=read(HERE/'old_n1/result.json'); new=read(HERE/'staged_n1_all/result.json')
context=read(HERE/'phase_context.json')
source_ok=all(sha(ROOT/n)==h and sha(HERE/'source_snapshot'/n)==h for n,h in d['source_sha256'].items())
history_ok=all(sha(ROOT/n)==h for n,h in d['historical_artifact_sha256'].items())
raw_mismatch=[]; missing_binaries=[]
for n,h in f['raw_hashes_before'].items():
    path=HERE/n
    if not path.exists() and path.suffix.lower()=='.mat': missing_binaries.append(n)
    elif not path.is_file() or sha(path)!=h:raw_mismatch.append(n)
missing_links=[]
for path in (HERE/'summary.md',HERE/'independent_review.md',HERE/'analysis01/summary.md'):
    for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
        if '://' in target or target.startswith('#'):continue
        name=target.split('#',1)[0]
        if not (path.parent/name).resolve().exists():missing_links.append({'path':str(path.relative_to(HERE)),'target':target})
p1,p2=new['phases']
e0=list(map(F,new['initial_global_weighted_energy_J'])); eo=list(map(F,old['weighted_energy_J'])); en=list(map(F,new['weighted_energy_J']))
checks={
    'terminal_two_method_calls_only':l['state']=='COMPLETED' and l['consumed']==2 and l['method_budget_s_reserved']==600 and [r['id'] for r in l['calls']]==['old_n1','staged_n1_all'],
    '149_source_and_snapshots_match':len(d['source_sha256'])==149 and source_ok,
    '147_inherited_sources_unchanged':all(d['source_sha256'][n]==h for n,h in read(HERE/'method_checks.json')['source_sha256'].items()),
    '452_historical_artifacts_unchanged':len(d['historical_artifact_sha256'])==452 and history_ok,
    'both_check_gates_pass':read(HERE/'method_checks.json')['passed'] and read(HERE/'method_checks.json')['count']==99 and read(HERE/'wrapper_checks.json')['passed'] and read(HERE/'wrapper_checks.json')['tests_run']==22,
    'independent_admission_pass':read(HERE/'admission_verification.json')['passed'],
    'independent_final_37_checks_pass':v['passed'] and len(v['checks'])==37 and all(v['checks'].values()),
    'frozen_auxiliary_execution_documents_unchanged':all(sha(HERE/n)==context[k] for n,k in [('protocol.md','protocol_sha256'),('launcher.py','launcher_sha256'),('declaration.json','declaration_sha256')]),
    'stored_analysis_raw_and_source_audit_pass':f['raw_unchanged'] and f['frozen_sources']['all_match'] and not raw_mismatch,
    'analysis_same_task_pair_and_complete_receipts_valid':f['comparison']['same_task_pair_comparison_valid'] and f['comparison']['all_final_complete_SAFE_receipts_consistent'],
    'both_SAFE_and_initial_energy_equal':all(r['state']=='SAFE' for r in (old,new)) and old['initial_global_weighted_energy_J']==new['initial_global_weighted_energy_J'],
    'both_strictly_improve_their_seed':eo[1]<e0[0] and en[1]<e0[0],
    'micro_improvement_strict_but_belongs_to_phase1':en[1]<eo[0] and F(0)<eo[0]-en[1]<F('0.000001') and new['committed_safe_snapshot']['phase_index']==1,
    'both_phases_visited_and_no_phase2_U_update':len(new['phases'])==2 and all(p['search_sequence_complete'] for p in new['phases']) and not any(u['phase_index']==2 for u in new['global_updates']),
    'stage_clock_preserves_setup_cost':abs((p1['completed_at_s']-p1['started_at_s'])-141.359)<0.001 and abs((p2['completed_at_s']-p1['completed_at_s'])-141.203)<0.001,
    'all_complete_U_before_300s':all(u['committed_at_s']<300 for r in (old,new) for u in r['global_updates']),
    'both_root_methods_stop_before_300s':all(r['timing']['method_elapsed_s']<300 for r in (old,new)),
    'native_six_budget_valid_not_six_method_calls':len(f['native_call_times'])==6 and all(r['budget_valid'] for r in f['native_call_times']),
    'both_workers_closed_with_observed_identities_exited':all(r['cleanup']['observed_tree_verified_terminated'] for r in l['calls']),
    'launcher_exit_zero':read(HERE/'launcher_timing.json')['returncode']==0,
    'all_delivery_links_exist':not missing_links,
}
report={'scope':'stored K138 evidence delivery audit only','passed':all(checks.values()),'checks':checks,
    'raw_mismatches':raw_mismatch,'missing_local_ignored_MAT':missing_binaries,'missing_links':missing_links,
    'binary_policy':'MAT files stay local and ignored; hashes retained; missing MAT on another clone does not replace stored SAFE receipts',
    'new_solver_model_or_thermal_calls':0}
(HERE/'delivery_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
raise SystemExit(0 if report['passed'] else 1)
