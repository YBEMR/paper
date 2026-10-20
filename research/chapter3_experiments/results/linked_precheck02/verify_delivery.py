"""Read saved K139 evidence and identities only; never build/evaluate/solve."""
from pathlib import Path
import hashlib
import json
import re

HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'AGENTS.md').is_file())
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
c=read(HERE/'checks.json');d=read(HERE/'declaration.json');b=read(HERE/'parent_baseline.json')
r=read(HERE/'fixture_records.json');review=read(HERE/'review_verification.json')
s=read(HERE/'design/reference_scope.json');first=read(HERE.parent/'linked_precheck01/checks.json')
history=b['historical_artifact_sha256'];tiny=r['test_linked_method']['physical_tiny']
mock=r['test_linked_method']['mock'];projection=r['test_linked_neighborhood']['structural']['cartesian']
old_paths=r['test_linked_neighborhood']['structural']['old_dispatch_regression']['checks']
before_first=read(HERE.parent/'linked_precheck01/checks.json')['source_sha256']
first_changed=[name for name,h in before_first.items() if c['source_sha256'][name]!=h]
missing=[]
for path in (HERE/'summary.md',HERE/'independent_review.md',HERE/'design/summary.md'):
    for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
        if '://' in target or target.startswith('#'):continue
        if not (path.parent/target.split('#',1)[0]).resolve().exists():missing.append({'path':path.name,'target':target})
checks={
    '66_passed_without_skips':c['passed'] and c['count']==66 and all(v['passed'] and not v['skipped'] and not v['errors'] and not v['failures'] for v in c['modules'].values()),
    '155_source_current_and_snapshots_equal':len(c['source_sha256'])==155 and all(sha(ROOT/n)==h and sha(HERE/'source_snapshot'/n)==h for n,h in c['source_sha256'].items()),
    '148_inherited_unchanged':len(b['baseline_source_sha256'])==149 and all(sha(ROOT/n)==h for n,h in b['baseline_source_sha256'].items() if n not in b['allowed_existing_source_changes']),
    'only_six_new_declared_sources':set(c['source_sha256'])-set(b['baseline_source_sha256'])==set(b['new_sources']) and len(b['new_sources'])==6,
    '1087_historical_artifacts_unchanged':len(history)==1087 and all(sha(ROOT/n)==h for n,h in history.items()),
    'failed_01_preserved_only_runner_changed':first['passed'] is False and first['count']==66 and first['modules']['test_linked_neighborhood']['passed'] and first['modules']['test_linked_method']['passed'] and first_changed==['research/chapter3_experiments/run_linked_precheck.py'],
    'no_forbidden_native_optimizer_or_original_model_entry':all(value==0 for value in c['blocked_calls'].values()) and all(c[k]==0 for k in ('native_calls','research_calls','original_scale_models')),
    'one_named_tiny_invalid_argument_rejection':c['observed_current_builds']['named_invalid_argument_rejection_checks']==1,
    '1296_cartesian_assignments_96_legal_match':projection['assignments']==1296 and projection['legal']==96 and projection['projection_equal'] and projection['option_projection_equal'],
    'three_old_dispatch_eight_arrays_preserved':len(old_paths)==3 and all(v['all_eight_solver_arrays_equal'] and v['rows_options_names_scenes_formulation_summary_equal'] for v in old_paths),
    'tiny_four_fresh_x0_model_generations':[(x['original_n'],x['dimension']) for x in tiny['calls']]==[(276,276),(320,320),(221,239),(243,262)] and len({x['budget_id'] for x in tiny['calls']})==1,
    'tiny_echo_same_energy_not_performance_result':tiny['result']['weighted_energy_J']==tiny['result']['initial_global_weighted_energy_J'] and not tiny['result']['strict_improvement_over_initial_certified'] and not tiny['result']['augmented_transport']['latched_unresolved'],
    'dual_anchor_mock_and_uncommitted_local_cases_saved':set(mock)=={'committed_warm_closed','uncommitted_local_not_anchor'},
    'original_scope_four_open_two_closed':len(s['scopes'])==2 and all(v['opened_count']==4 and v['closed_count']==2 for v in s['scopes'].values()),
    'static_options_events_reduced_without_model_claim':[(v['all_options_after_deadline'],v['linked_options_after_deadline'],v['all_candidate_start_end_events'],v['linked_candidate_start_end_events']) for v in s['scopes'].values()]==[(441,280,271,173),(405,274,296,201)],
    'activity_floor_preserved_not_safe_system_saving':s['linked_and_all_fixed_unit_activity_floors_equal'] and s['weighted_activity_facts']['linked_independent_activity_floor_J']==s['weighted_activity_facts']['all_fixed_unit_activity_floor_J'],
    'single_structure_only_demonstration_not_free_seed':s['demonstration']['construction_attempts']==1 and s['demonstration']['structurally_legal'] and s['demonstration']['thermal_state']=='NOT_EVALUATED' and s['demonstration']['system_energy_state']=='NOT_EVALUATED' and not s['demonstration']['used_as_method_initialization'],
    'independent_readonly_34_checks_pass':review['passed'] and review['check_count']==34 and all(v['passed'] for v in review['checks']),
    'local_delivery_links_exist':not missing,
    'mermaid_fence_complete':(HERE/'summary.md').read_text(encoding='utf-8').count(chr(96)*3)==2,
}
report={'stage':'K139','scope':'saved delivery identities and evidence only',
    'passed':all(checks.values()),'checks':checks,'missing_links':missing,
    'new_research_native_model_or_thermal_calls':0}
(HERE/'delivery_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
raise SystemExit(0 if report['passed'] else 1)
