"""Verify completed K145 artifacts using hashes and stored evidence only."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
CODE = ROOT/'research/chapter3_experiments'
read = lambda p: json.loads(p.read_text(encoding='utf-8'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    declaration, ledger = read(HERE/'declaration.json'), read(HERE/'ledger.json')
    analysis = read(HERE/'k145_analysis.json')
    independent = read(HERE/'k145_independent_verification.json')
    context = read(HERE/'k145_phase_context.json')
    old = CODE/'results/fair_comparison_preparation01'
    prior = read(CODE/'results/budget_end_review01/audit.json')
    base = read(old/'declaration.json')
    sources = declaration['source_sha256']
    metrics = {m['method']: m for m in analysis['methods']}
    calls = {c['id']: c for c in ledger['calls']}
    raw = {name: read(HERE/name/'result.json') for name in metrics}
    checks = {
        'frozen_source165_and_snapshot_match': len(sources)==165 and all(sha(ROOT/n)==h==sha(HERE/'source_snapshot'/n) for n,h in sources.items()),
        'inherited159_unchanged': len(base['source_sha256'])==159 and all(sources.get(n)==h for n,h in base['source_sha256'].items()),
        'original_input_and_bytes_unchanged': declaration['input_identities']==base['input_identities'] and all(sha(HERE/n)==h for n,h in declaration['input_file_sha256'].items()),
        'original_K142_301_files_unchanged': len(prior['raw_artifact_sha256'])==301 and all(sha(old/n)==h for n,h in prior['raw_artifact_sha256'].items()),
        'old_batch_not_reset': read(old/'ledger.json')['state']=='BLOCKED' and read(old/'ledger.json')['consumed']==2,
        'explicit_user_execution_authorization_saved': (HERE/'k145_execution_authorization.md').is_file(),
        'exact_two_consumed_calls_ordered': ledger['state']=='COMPLETED' and ledger['consumed']==2 and [c['id'] for c in ledger['calls']]==['heft','sa101'],
        'fixed_two_300_second_caps': ledger['reserved_method_budget_s']==600 and all(r['timing']['limit_s']==300 for r in raw.values()),
        'exact_seed101_and_heft_deterministic': raw['heft']['seed'] is None and raw['sa101']['seed']==101,
        'one_global_and_two_method_claims': (CODE/'results/heuristic_followup_claim01.json').is_file() and len(list((HERE/'claims').glob('*_result.json')))==2 and all((HERE/'claims'/(n+'.json')).is_file() for n in raw),
        'HEFT_normal_completion': calls['heft']['execution']['execution_status']=='NORMAL_COMPLETION' and metrics['heft']['method_elapsed_s']==43.25,
        'SA_normal_cutoff_old_safe_and_pending': calls['sa101']['execution']['execution_status']=='NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST' and calls['sa101']['execution']['safe_witness_preserved'] and metrics['sa101']['method_elapsed_s']==300,
        'no_late_or_partial_U': all(not c['execution']['new_or_late_candidate_accepted'] for c in calls.values()) and raw['sa101']['evaluations'][-1]['accepted_safe'] is False and raw['sa101']['evaluations'][-1]['evaluation']['weighted_energy_J'] is None,
        'no_actual_error_or_numerical_failure': all(not c['errors'] and c['execution']['safe_witness_preserved'] for c in calls.values()),
        'mathematical_stored_evidence_audit_pass': analysis['passed'] and analysis['extra_solver_or_heat_calls']==0,
        'independent_stored_evidence_review_pass': independent['passed'] and not independent['failures'] and not any(independent['reviewer_invocation_counts'].values()),
        '44_and_241_distinct_safe_schedules': metrics['heft']['distinct_safe_schedules']==44 and metrics['sa101']['distinct_safe_schedules']==241,
        'not_claiming_optimum_or_infeasibility': all(not r['independently_proven_optimal'] and not r['independently_proven_infeasible'] and not r['coverage_complete'] for r in raw.values()),
        'separate_archive_postrecord_and_wrapper_timing': all(m['archive_only_wall_s']>=0 and m['post_method_record_wall_s']>=0 for m in metrics.values()) and context['external_process_wall_status']=='NOT_SEPARATELY_MEASURED',
        'analysis_revision_failure_retained': (HERE/'k145_analysis_revision01.py').is_file() and read(HERE/'k145_analysis_revision01_failure.json')['analysis_only_failure'],
        'curves_and_csv_available': all((HERE/n).is_file() for n in ['k145_metrics.csv','k145_schedules.csv','k145_progress.csv','k145_energy_progress.png','k145_energy_progress.svg']),
        'project_records_K145_synced': all('K.145' in (ROOT/n).read_text(encoding='utf-8') for n in ['RESEARCH_BRIEF.md','research/03_证据与检索记录.md','research/第三章当前进展与正式实验推进计划_审查稿.md','research/chapter3_experiments/README.md']),
        'no_retry_extension_or_extra_seed': context['research_calls']==2 and not any(context[k] for k in ['retry','extension','extra_seeds']),
        'new_batch_not_spliced_into_K142': context['no_four_method_same_round_claim'] is True,
    }
    result = dict(stage='K145', passed=all(checks.values()), check_count=len(checks), checks=checks,
                  research_calls=2, postrun_method_or_heat_calls=0,
                  stored_result_sha256={name:sha(HERE/name/'result.json') for name in raw},
                  declaration_sha256=sha(HERE/'declaration.json'),
                  independent_review_sha256=sha(HERE/'k145_independent_verification.json'),
                  scope='delivery checks on already formed artifacts; no search or new physical evidence')
    (HERE/'k145_delivery_verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    return result['passed']

if __name__=='__main__':
    raise SystemExit(0 if main() else 1)
