"""Inspect the stopped K163 cancellation-marker conflict; no new scientific work.

Only stored evidence and a tiny file-writing fixture are used. The fixture calls
the existing _Request.fail method on a hand-constructed object, never its model
or solver lifecycle. Current method/slot states are neither changed nor approved.
"""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
from unittest.mock import patch
import audit_terminal as a


def inspect():
    out = a.ROOT/'results/deadline_execution01'
    if not (out/'process_terminal.json').is_file():
        raise RuntimeError('Stopped supervisor record required')
    slot_id = 'beta_1.0__R1__anchor_linked4'
    folder = out/'calls/beta_1.0__R1/anchor_linked4'
    paths = [out/'declaration.json', out/'process_terminal.json',
             out/'claims'/(slot_id+'_method_return.json'), out/'claims'/(slot_id+'_result.json'),
             folder/'wrapper_raw_result.json', folder/'matlab/request_000004.python.json',
             folder/'matlab/request_000004.input.json', folder/'matlab/request_000004.cancel',
             folder/'matlab/closed.json']
    before = {p.relative_to(a.REPO).as_posix(): a.sha(p) for p in paths}
    row = a.read(out/'claims'/(slot_id+'_result.json'))
    raw = a.read(folder/'wrapper_raw_result.json')
    d = a.read(out/'declaration.json')
    record = row['records']
    guards = dict.fromkeys(('whole', 'linked', 'heuristic', 'matlab', 'milp', 'linprog',
                           'model', 'heat', 'candidate_heat', 'scene_heat', 'subprocess', 'seed'), 0)
    def forbidden(key):
        def fail(*args, **kw):
            guards[key] += 1
            raise AssertionError('Forbidden cancellation-review scientific call: '+key)
        return fail
    sys.path[:0] = [str(a.ROOT/'deadline_batch'), str(a.ROOT/'p0_batch'), str(a.ROOT)]
    import formal_milp, linked_method, heuristic_runner, matlab_bridge, milp
    import thermal, scene_adapter, initial_schedule, scipy.optimize
    import augmented_method, audit_cutoff
    with ExitStack() as stack:
        for obj, name, key in (
                (formal_milp, 'execute_formal_milp', 'whole'),
                (linked_method, 'execute_linked_fixed_unit_opp_start', 'linked'),
                (heuristic_runner, 'execute_heuristic', 'heuristic'),
                (matlab_bridge.MatlabSession, '__init__', 'matlab'),
                (scipy.optimize, 'milp', 'milp'), (scipy.optimize, 'linprog', 'linprog'),
                (milp, 'build_model', 'model'), (thermal, 'evaluate_piecewise', 'heat'),
                (thermal, 'evaluate_candidate', 'candidate_heat'),
                (scene_adapter, 'evaluate_piecewise', 'scene_heat'),
                (initial_schedule, 'iter_initial_candidates', 'seed')):
            stack.enter_context(patch.object(obj, name, side_effect=forbidden(key)))
        stack.enter_context(patch('subprocess.Popen', side_effect=forbidden('subprocess')))
        definition = d['inputs'][row['problem_id']]
        job = {k: v for k, v in row.items() if k in
               ('id', 'method', 'seed', 'opened_count', 'preeliminate_closed_anchors')}
        underlying = audit_cutoff.correct_records(job, raw, definition, folder,
            input_valid=record['context']['input_identity_valid'],
            source_valid=record['context']['source_identity_valid'], errors=row['errors'])
        fixture_root = a.REPO/'.runtime/k163_cancel_fixture'
        fixture_root.mkdir(parents=True, exist_ok=True)
        fixture = []
        for reason in ('CALLBACK_PUBLICATIONS_NOT_FULLY_CHECKED', 'NATIVE_NUMERICAL_CONSISTENCY_CONFLICT'):
            with tempfile.TemporaryDirectory(dir=fixture_root) as tmp:
                prefix = Path(tmp)/'request_000001'
                cancel = prefix.with_suffix('.cancel')
                cancel.write_text('budget\n', encoding='ascii')
                calls = []
                request = object.__new__(augmented_method._Request)
                request.receipt = {'failure_reasons': []}
                request.context = SimpleNamespace(fail=calls.append)
                request.prefix = prefix
                request.budget = SimpleNamespace(elapsed=300.0)
                prior = cancel.read_text(encoding='ascii').strip()
                request.fail(reason)
                fixture.append({'failure_reason': reason, 'prior_marker': prior,
                    'after_marker': cancel.read_text(encoding='ascii').strip(),
                    'cancel_requested': request.receipt.get('cancel_requested'),
                    'cancel_published_at_s': request.receipt.get('cancel_published_at_s'),
                    'context_fail_calls': calls})
    python = a.read(folder/'matlab/request_000004.python.json')
    last = raw['augmented_transport']['requests'][-1]
    marker = (folder/'matlab/request_000004.cancel').read_text(encoding='ascii').strip()
    expected_reasons = {'CALLBACK_PUBLICATIONS_NOT_FULLY_CHECKED', 'BUDGET_BEFORE_FINAL_ADMISSION',
                        'BUDGET_DURING_ADMISSION_ARCHIVE'}
    checks = {
        'original_slot_is_stopped_not_reclassified': row['state'] == 'BLOCKED'
            and record['execution']['execution_status'] == 'TECHNICAL_FAILURE_CONFIRMED',
        'sole_hard_error_is_cancel_content_gate': record['context']['hard_errors'] == ['MISSING_MATCHING_ROOT_CANCEL_FILE'],
        'actual_current_deadline_schedule_check_passed': record['current_schedule_audit']['passed'] is True,
        'cancel_file_exists_but_is_generic_augmented_marker': marker == 'augmented numerical admission unresolved',
        'root_cutoff_adapter_already_applied': record['cutoff_audit']['applied'] is True
            and record['cutoff_audit']['method_stop_s'] == 300
            and record['cutoff_audit']['cancel_published_at_s'] == 300
            and record['cutoff_audit']['method_deadline_bound'] is True,
        'last_transport_has_only_known_root_deadline_failures': set(last['failure_reasons']) == expected_reasons,
        'no_actual_numerical_report_rejected': record['context']['observed_numerical_rejection'] is False
            and all((v.get('report') or {}).get('accepted') is True for v in last['numerical_checks']),
        'late_native_vector_was_refused': python['status'] == 'BUDGET_EXHAUSTED'
            and python['budget_valid'] is False and python['accepted_for_evaluation'] is False
            and python['response_may_arrive_later'] is True and python['x'] == [],
        'native_tree_isolation_verified': record['context']['worker_isolation'] == 'VERIFIED',
        'underlying_cutoff_adapter_has_no_other_hard_error': underlying['context']['hard_errors'] == []
            and underlying['execution']['execution_status'] == 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST',
        'underlying_derived_view_preserves_exact_U': underlying['usable_U_J'] == record['usable_U_J'],
        'tiny_fixture_reproduces_overwrite': all(v['prior_marker'] == 'budget'
            and v['after_marker'] == marker and v['cancel_requested'] is True
            and v['cancel_published_at_s'] == 300 for v in fixture),
        'same_marker_can_also_mean_real_numerical_failure': fixture[0]['after_marker'] == fixture[1]['after_marker'],
        'all_original_evidence_files_unchanged': all(a.sha(a.REPO/name) == digest for name, digest in before.items()),
        'all_scientific_guards_zero': not any(guards.values()),
    }
    return {'protocol': 'K163-stopped-cancel-overwrite-review-v1', 'passed': all(checks.values()),
        'checks': checks, 'checks_run': len(checks), 'failed_checks': [k for k, v in checks.items() if not v],
        'slot_id': slot_id, 'original_execution_status': record['execution']['execution_status'],
        'original_hard_errors': record['context']['hard_errors'], 'current_schedule_audit_passed': True,
        'current_frozen_cancel_content_gate_passes': marker == 'budget',
        'actual_cancel_marker': marker, 'cancel_file_sha256': a.sha(folder/'matlab/request_000004.cancel'),
        'original_U_J': record['usable_U_J'], 'original_SAFE_formed_at_s': record['execution']['usable_safe_formed_at_s'],
        'underlying_cutoff_adapter_derived_status_only': underlying['execution']['execution_status'],
        'derived_view_is_new_execution_authorization': False,
        'failure_reasons': last['failure_reasons'], 'overwrite_fixtures': fixture,
        'source_locations': {'budget_marker_writer': 'matlab_bridge.py:663-675',
            'generic_marker_overwriter': 'augmented_method.py:140-152',
            'root_budget_reasons': 'augmented_method.py:436-450',
            'strict_budget_only_marker_gate': 'deadline_batch/deadline_entry.py:151-157'},
        'source_sha256': {f'research/chapter3_experiments/{name}': a.sha(a.ROOT/name)
                          for name in ('matlab_bridge.py', 'augmented_method.py', 'deadline_batch/deadline_entry.py')},
        'original_evidence_sha256': before, 'blocked_calls': guards,
        'new_research_calls': 0, 'new_models': 0, 'new_thermal_evaluations': 0,
        'new_SAFE_or_U': False, 'original_data_modified': False,
        'review_script_sha256': a.sha(__file__),
        'conclusion': 'The frozen batch stopped on a too-narrow cancellation-content audit gate. A generic augmented marker can overwrite the budget marker, so accepting that string alone would be unsafe; any future record adapter must retain the complete original root-cutoff, identity, numerical and isolation chain. No original state or research authorization is changed here.'}


if __name__ == '__main__':
    result = inspect()
    with (a.HERE/'cancel_overwrite_review01.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({k: result[k] for k in ('passed', 'checks_run', 'failed_checks', 'blocked_calls')}, ensure_ascii=False))
    raise SystemExit(0 if result['passed'] else 1)
