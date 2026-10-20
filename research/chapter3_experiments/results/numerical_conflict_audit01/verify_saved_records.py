"""K132 delivery checks: hashes and saved arithmetic, no rebuild/solver/heat."""
from pathlib import Path
import hashlib, json

repo=next(p for p in Path(__file__).resolve().parents if (p/'AGENTS.md').is_file() and (p/'RESEARCH_BRIEF.md').is_file())
root=repo/'research/chapter3_experiments/results/numerical_conflict_audit01'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
d=read(root/'declaration.json'); r=read(root/'row_trace/rebuild_comparison.json')
a=read(root/'row_trace/rebuild_attempt.json'); f=read(root/'numeric_route/facts.json')
v=read(root/'row_trace/independent_affine_facts.json'); alias=f['physical_alias_only']
checks=[]
def check(name,value):
    checks.append({'name':name,'passed':bool(value)})
    if not value:raise AssertionError(name)

check('135_production_sources_unchanged',len(d['source_sha256'])==135 and all(sha(repo/n)==h for n,h in d['source_sha256'].items()))
check('96_K131_original_artifacts_unchanged',len(d['K131_artifact_sha256'])==96 and all(sha(repo/n)==h for n,h in d['K131_artifact_sha256'].items()))
check('single_bounded_rebuild_matches_all_8_arrays',r['all_arrays_identical'] and len(r['arrays'])==8 and all(x['equal_elementwise'] for x in r['arrays'].values()) and a['status']=='EXACT_MATCH_LABELS_RESTORED' and a['build_and_export_wall_s']<120)
check('no_new_native_or_SAFE_credential',a['solver_calls']==a['matlab_starts']==a['candidate_thermal_evaluations']==0 and not a['production_validators_modified_or_skipped'] and not a['new_SAFE_or_method_budget_credential_created'])
check('labels_and_route_script_identities',f['labels_sha256']==sha(root/'row_trace/labels.json') and f['script_sha256']==sha(root/'numeric_route/audit_saved_affine_route.py') and v['route_script_sha256_matches_facts'])
check('reject_full_complement_269_rhs',f['complement']['rhs_not_binary64_exact_count']==269 and not f['certificates']['exact_equivalence_of_stored_polyhedron_for_joint_complement'] and v['full_global_complement_not_exact_binary64_rows_count']==269)
check('24000_physical_rows_exact_and_original_rows_preserved',alias['eligible_physical_rows']==alias['physical_rows_exact_after_eliminating_alias']==24000 and alias['nonrepresentable_physical_rhs_count']==0 and alias['nonphysical_original_rows_unchanged_exactly'] and not v['physical_b_minus_gate_not_exact_binary64_rows'])
check('integer_objective_bounds_prefix_preserved',alias['original_integer_index_array_unchanged'] and alias['original_objective_coefficients_unchanged_new_costs_zero'] and alias['x0_original_prefix_bitwise_unchanged'] and v['all_gate_bounds_0_1'] and v['gate_columns_in_intcon']==0)
check('continuous_gate_row_identity',alias['nonintegral_sample_original_new_exact_residual_equal_rows']==39733 and alias['nonintegral_sample_exact_link_equalities']==2400 and alias['nonintegral_sample_original_integer_coordinates_unchanged'] and alias['original_objective_on_sample_exactly_preserved'])
check('costs_and_floating_limits_disclosed',alias['new_total_variables']==10925 and alias['new_total_rows']==42133 and alias['new_total_nnz']==362283 and not alias['floating_acceptance_region_identical'] and not alias['native_acceptance_or_infeasibility_resolution_tested'] and not f['certificates']['exact_x0_feasibility'] and not f['certificates']['thermal_safety'] and not f['certificates']['native_solver_success'])
check('review_and_failure_record_saved',(root/'independent_review.md').is_file() and (root/'row_trace/failure_record.json').is_file() and '通过本阶段限定范围' in (root/'independent_review.md').read_text(encoding='utf-8'))
markers=[('RESEARCH_BRIEF.md','K.132／D156'),('research/03_证据与检索记录.md','E577：'),('research/第三章当前进展与正式实验推进计划_审查稿.md','## K.132：'),('research/chapter3_experiments/README.md','3.12ak')]
check('state_and_unique_next_action_registered',all(marker in (repo/name).read_text(encoding='utf-8') for name,marker in markers))
out={'stage':'K132','scope':'delivery integrity checks only; mathematical arguments and independent saved-array checks cited separately','passed':True,'count':len(checks),'checks':checks,'research_solver_calls':0,'matlab_startups':0,'candidate_thermal_evaluations':0,'technical_rebuilds':1,'rebuild_and_export_wall_s':a['build_and_export_wall_s'],'source_script_sha256':sha(Path(__file__))}
(root/'verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(root/'verify_saved_records.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps({'passed':True,'delivery_checks':len(checks),'optimizer_calls':0,'native_check_pending':True}))
