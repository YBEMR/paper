"""Read stored K137 receipts and hashes; no model, evaluator or optimizer."""
from pathlib import Path
import hashlib
import json
import re

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
c=read(HERE/'checks.json')
d=read(HERE/'declaration.json')
base=read(HERE/'parent_baseline.json')
f=read(HERE/'fixture_records.json')['test_staged_method']
tiny=f['real_tiny_two_pass_echo']; t=tiny['result']
sources=all(sha(ROOT/n)==h and sha(HERE/'source_snapshot'/n)==h for n,h in c['source_sha256'].items())
history=all(sha(ROOT/n)==h for n,h in d['historical_artifact_sha256'].items())
inherited=all(sha(ROOT/n)==h for n,h in base['baseline_source_sha256'].items()
              if n not in base['allowed_existing_source_changes'])
first=read(HERE.parent/'staged_method_precheck01/checks.json')
unchanged_production=all(c['source_sha256'][n]==h for n,h in first['source_sha256'].items()
                         if n!='research/chapter3_experiments/test_staged_method.py')
warm=f['partial_local_store_not_warm']['result']
mock=f['one_invocation_two_passes']['result']
sub=f['residual_budget_dominates']
call=sub['calls'][2]
missing=[]
for p in [HERE/'summary.md',HERE/'independent_review.md']:
    for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
        if '://' in target or target.startswith('#'):continue
        name=target.split('#',1)[0]
        if not (p.parent/name).resolve().exists():missing.append({'source':p.name,'target':target})
checks={
    '99_passed_no_skips':c['passed'] is True and c['count']==99 and all(v['skipped']==0 for v in c['modules'].values()),
    '147_source_and_snapshots_match':sources and len(c['source_sha256'])==147,
    '143_inherited_sources_unchanged':inherited and len(base['baseline_source_sha256'])-len(base['allowed_existing_source_changes'])==143,
    '452_historical_artifacts_unchanged':history and len(d['historical_artifact_sha256'])==452,
    'PASS01_preserved_only_test_changed_for_PASS02':first['passed'] is True and first['count']==99 and unchanged_production,
    'native_optimizer_and_process_attempts_zero':all(v==0 for v in c['blocked_native_launch_attempts'].values()),
    'no_research_or_original_scale_calls':all(c[k]==0 for k in ('native_calls','research_calls','original_scale_models')),
    'both_mock_complete_ledger_snapshots_match':all(r['committed_safe_snapshot']['safe_candidate']==r['safe_candidate']
        and r['committed_safe_snapshot']['aggregation']==r['aggregation']
        and r['committed_safe_snapshot']['safe_upper_bound_J']==r['safe_upper_bound_J'] for r in (warm,mock)),
    'residual_fraction_dominates':0<call['solver_max_time_s']<60 and abs(call['solver_max_time_s']-call['budget_remaining_s']/2)<1e-10,
    'real_tiny_both_passes_one_budget':len(t['phases'])==2 and len(tiny['calls'])==4 and len({r['budget_id'] for r in tiny['calls']})==1,
    'real_tiny_is_echo_not_quality_improvement':t['weighted_energy_J']==t['initial_global_weighted_energy_J'] and not t['strict_improvement_over_initial_certified'],
    'real_tiny_new_vectors_and_mapping_gate':[(r['original_n'],r['dimension']) for r in tiny['calls']]==[(276,276),(320,320),(377,417),(443,486)]
        and not t['augmented_transport']['latched_unresolved']
        and all(r['callback_publications_complete'] for r in t['augmented_transport']['requests']),
    'local_delivery_links_exist':not missing,
}
out={'scope':'stored evidence delivery audit, not optimization or performance verification','checks':checks,
     'passed':all(checks.values()),'missing_links':missing}
(HERE/'delivery_verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(out,ensure_ascii=False))
raise SystemExit(0 if out['passed'] else 1)
