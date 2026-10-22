"""Read the stopped R2 whole-MILP numerical-status conflict, without rerunning it."""
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPO = ROOT.parents[1]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def inspect():
    out = ROOT/'results/deadline_resume01'
    if not (out/'process_terminal.json').is_file():
        raise RuntimeError('Stopped supervisor evidence required')
    slot_id = 'beta_1.0__R2__whole_milp'
    folder = out/'calls/beta_1.0__R2/whole_milp'
    frozen = read(out/'declaration.json')
    original = read(ROOT/'results/deadline_execution01/declaration.json')
    row = read(out/'claims'/(slot_id+'_result.json'))
    raw = read(folder/'wrapper_raw_result.json')
    record, context = row['records'], row['records']['context']
    python = read(folder/'matlab/request_000001.python.json')
    native = read(folder/'matlab/request_000001.response.json')
    root_budget = read(folder/'method_budget_identity.json')
    meta = read(folder/'matlab/request_000001.input.json')
    conflict = python.get('numerical_consistency') or {}
    admission = conflict.get('python_x0_admission') or {}
    callbacks = native.get('callbacks') or []
    done = [v for v in callbacks if v.get('state') == 'done']
    archive_hashes = {p.relative_to(REPO).as_posix(): sha(p)
        for p in sorted(folder.rglob('*')) if p.is_file()}
    old_hashes = frozen['prior_artifact_sha256']
    sources = frozen['source_sha256']
    audits = read(HERE/'joint_terminal_review01.json')
    actual_rejected_point_reports = [v for v in walk(raw)
        if v.get('accepted_numerically') is False
        or (v.get('accepted') is False and ('constraint_tolerance' in v or 'integer_tolerance' in v))]
    checks = {
        'stopped_on_numerical_status_conflict': row['state'] == 'BLOCKED'
            and record['execution']['execution_status'] == 'NUMERICAL_ANOMALY_OBSERVED'
            and raw['reason'] == 'SOLVER_NUMERICAL_CONSISTENCY_UNRESOLVED'
            and conflict['state'] == 'NUMERICAL_ADMISSION_STATUS_CONFLICT',
        'same_request_diagnostic_consistent_across_original_records': conflict
            == raw['numerical_consistency'] == raw['rounds'][0]['numerical_consistency'],
        'explicit_x0_python_row_admission_passed': conflict['explicit_x0_in_this_request'] is True
            and admission['provided'] is True and admission['accepted_numerically'] is True
            and admission['length'] == 23464 and admission['reasons'] == []
            and admission['inequality_violation'] < admission['constraint_tolerance']
            and admission['equality_violation'] == admission['integer_violation'] == 0,
        'no_actual_rejected_point_residual_report_found': not actual_rejected_point_reports,
        'worker_received_x0_without_independent_solver_acceptance':
            conflict['worker_reported_x0_received'] is True
            and conflict['worker_solver_x0_acceptance'] == 'not_independently_observed',
        'native_infeasible_report_not_accepted_as_solution': python['status'] == native['status'] == 'SOLVED'
            and python['exitflag'] == native['exitflag'] == -2
            and python['x'] == native['x'] == [] and native['output']['numfeaspoints'] == 0
            and python['accepted_for_evaluation'] is False,
        'native_done_callback_retained_without_reconciling_contradictory_counts':
            len(done) == 1 and done[0]['values']['numfeaspoints'] == 1,
        'response_formed_before_root300_deadline': root_budget['limit_s'] == 300
            and meta['method_deadline_bound'] is True
            and F(str(meta['absolute_deadline'])) == F(str(root_budget['deadline']))
            == F(str(root_budget['start']))+300
            and root_budget['start'] <= python['solver_response_complete_at_monotonic'] < root_budget['deadline']
            and python['budget_valid'] is True and conflict['formed_within_request_budget'] is True,
        'not_a_normal_root_cutoff': raw['budget_exhausted'] is False
            and raw['timing']['method_elapsed_s'] < 300
            and context['root_deadline_confirmed'] is False
            and context['deadline_causal_trace'] is False
            and context['last_request']['deadline_reasons'] == [],
        'no_identity_or_process_fault_observed': context['hard_errors'] == []
            and all(context[v] is True for v in ('input_identity_valid', 'source_identity_valid',
                                                'current_request_identity_valid', 'prior_requests_complete'))
            and context['worker_isolation'] == 'VERIFIED',
        'prior_complete_safe_U_retained_exactly': record['execution']['safe_witness_preserved'] is True
            and record['usable_U_J'] == record['execution']['usable_U_J'] == raw['safe_upper_bound_J']
            and record['execution']['usable_safe_formed_at_s'] == raw['evaluation']['completed_at_elapsed_s']
            and 0 <= raw['evaluation']['completed_at_elapsed_s'] < 300,
        'no_post_or_new_safe_value_added': not (folder/'postcheck.json').exists()
            and not (folder/'postcheck.claim.json').exists() and not row.get('postcheck')
            and record['execution']['new_or_late_candidate_accepted'] is False,
        'no_independent_infeasibility_or_optimality_claim': conflict['independent_certificate'] is False
            and record['execution']['independently_proven_optimal'] is False
            and record['execution']['independently_proven_infeasible'] is False,
        'joint_audit_preserves_stopped16_total_and24_unstarted': audits['passed'] is True
            and audits['campaign_completed_40'] is False
            and audits['combined_accounting']['consumed_total'] == 16
            and audits['combined_accounting']['reserved_method_seconds'] == 4800
            and audits['combined_accounting']['unstarted_remaining'] == 24
            and audits['post_verified_safe_outputs'] == 14,
        'source248_and_old_archive_unchanged': len(sources) == 248
            and all(sha(REPO/name) == h for name, h in sources.items())
            and all(sha(REPO/name) == h for name, h in old_hashes.items()),
        'stopped_method_files_unchanged': all(sha(REPO/name) == h for name, h in archive_hashes.items()),
    }
    by_status = {}
    for item in audits['rows']:
        state = item['derived_execution_status']
        by_status[state] = by_status.get(state, 0)+1
    return {'protocol': 'K164-stopped-R2-whole-numerical-status-review-v1',
        'passed': all(checks.values()), 'checks_run': len(checks), 'checks': checks,
        'failed_checks': [name for name, value in checks.items() if not value],
        'slot_id': slot_id, 'recorded_execution_status': record['execution']['execution_status'],
        'diagnostic_kind': conflict['state'], 'raw_reason': raw['reason'],
        'root_deadline_related': False, 'point_row_rejection_observed': False,
        'archival_audit_passed_is_not_method_success': True,
        'scientific_run_outcome': 'STOPPED_NUMERICAL_CONSISTENCY_UNRESOLVED',
        'next_24_calls_outcome': 'UNSTARTED_NO_RETRY_OR_NEW_AUTHORIZATION_INFERRED',
        'safe_U_J_preserved': record['usable_U_J'],
        'safe_U_formed_at_s_preserved': record['execution']['usable_safe_formed_at_s'],
        'safe_U_post_verification': 'NOT_EXECUTED_AFTER_STOP_NOT_RANKED_AS_POST_VERIFIED',
        'root_method_elapsed_s': raw['timing']['method_elapsed_s'],
        'method_budget': root_budget, 'initial_point_admission': admission,
        'solver_reported_only': {'status': native['status'], 'exitflag': native['exitflag'],
            'output': native['output'], 'done_callback': done,
            'native_x0_received': conflict['worker_reported_x0_received'],
            'native_solver_x0_acceptance': conflict['worker_solver_x0_acceptance']},
        'combined_partition': {'consumed_total': 16, 'post_verified_safe': 14,
            'normal_no_U_no_post': sum(v['derived_execution_status'] in ('NORMAL_COMPLETION',
                'NORMAL_TIME_LIMIT', 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST')
                and v['original_usable_U_J'] is None for v in audits['rows']),
            'numerical_unresolved_with_archived_U_without_post': 1,
            'unstarted': 24, 'derived_status_counts': by_status},
        'frozen_input_sha256': original['inputs']['beta_1.0__R2']['input_sha256'],
        'scientific_source_locations': {
            'same_request_status_conflict': 'matlab_bridge.py:223-249',
            'budget_and_native_status_handling': 'matlab_bridge.py:690-706',
            'formal_loop_stops_on_conflict': 'formal_milp.py:121-127',
            'stored_reason_classification': 'p0_batch/audit_whole.py:105-109'},
        'source_sha256': sources, 'stopped_method_file_sha256': archive_hashes,
        'original_archive_hashes_rechecked': len(old_hashes),
        'joint_audit_sha256': sha(HERE/'joint_terminal_review01.json'),
        'review_script_sha256': sha(__file__),
        'new_research_calls': 0, 'new_models': 0, 'new_thermal_evaluations': 0,
        'new_post_evaluations': 0, 'original_raw_or_receipt_modified': False,
        'tolerances_changed': False, 'record_reclassified': False,
        'scope': 'Python admitted the explicit numerical payload while the same native request '
                 'reported infeasible. Native solver acceptance of x0 was not independently observed. '
                 'This is a retained engineering consistency diagnostic, not an exact contradiction, '
                 'solver-defect finding or mathematical infeasibility certificate. No rerun, '
                 'post check or tolerance change is authorized by this audit.'}


if __name__ == '__main__':
    result = inspect()
    with (HERE/'numerical_stop_review01.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps({k: result[k] for k in ('passed', 'checks_run', 'failed_checks',
        'diagnostic_kind', 'root_deadline_related', 'point_row_rejection_observed',
        'safe_U_J_preserved', 'combined_partition')}, ensure_ascii=False))
    raise SystemExit(0 if result['passed'] else 1)
