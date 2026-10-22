"""Pure fabricated fixtures and guarded replay; no solver/model/heat work."""
from contextlib import ExitStack
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import cancel_adapter as adapter


class CancelAdapterTests(unittest.TestCase):
    def setUp(self):
        tmp_root = adapter.ROOT.parents[1]/'.runtime/k163_cancel_adapter_tests'
        tmp_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=tmp_root)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        (self.folder/'matlab').mkdir()
        self.job = {'id': 'anchor_linked4', 'method': 'linked_fixed_unit_opp_start'}
        self.request = {'cancel_requested': True, 'cancel_published_at_s': 300.0,
            'native_status': 'BUDGET_EXHAUSTED', 'within_budget': False,
            'latched_unresolved': True, 'callback_publications_complete': False,
            'failure_reasons': ['BUDGET_BEFORE_FINAL_ADMISSION'],
            'numerical_checks': [self.numeric()]}
        prior = {'latched_unresolved': False, 'within_budget': True,
            'failure_reasons': [], 'callback_publications_complete': True,
            'expected_callback_numbers': [1], 'checked_callback_numbers': [1],
            'numerical_checks': [self.numeric()]}
        self.raw = {'budget_exhausted': True, 'reason': 'wall_time_limit',
            'timing': {'limit_s': 300, 'method_elapsed_s': 300.0},
            'condition': {'budget_identity': {'start': '1000'}},
            'augmented_transport': {'requests': [prior, self.request]},
            'phases': [{'phase_index': 2, 'scenes': {'AC': {'solver_result': {
                'rounds': [{'request_number': 2, 'augmented_admission': self.request}]}}}}]}
        scopes = ['AC:round:1', 'phase:2:AC:round:1']
        context = {'input_identity_valid': True, 'source_identity_valid': True,
            'current_request_identity_valid': True, 'prior_requests_complete': True,
            'root_deadline_confirmed': True, 'deadline_causal_trace': True,
            'worker_isolation': 'VERIFIED', 'observed_numerical_rejection': False,
            'cutoff_s': 300, 'completion_verified': False, 'thermal_unresolved': False,
            'hard_errors': [adapter.MARKER_ERROR], 'numerical_checks': [self.numeric()],
            'last_request': {'state': 'PENDING', 'pending_at_cutoff': True,
                'refuses_late_candidate': True, 'deadline_causal_trace': True,
                'deadline_reasons': ['BUDGET_BEFORE_FINAL_ADMISSION']},
            'safe_receipt': {'verified': True, 'identity_valid': True, 'complete': True,
                'formed_at_s': 255.0, 'energy_upper_J': '0.9'}}
        execution = adapter.classify_execution(self.raw, context)
        self.original = {'execution': execution, 'context': context,
            'usable_U_J': '0.9', 'current_schedule_audit': {'passed': True},
            'completion_metrics': {'unchanged_fixture': True},
            'cutoff_audit': {'applied': True, 'method_deadline_bound': True,
                'cancel_published_at_s': 300.0, 'method_stop_s': 300.0,
                'absolute_deadline': 1300.0, 'exact_request_scopes': scopes,
                'cancel_file_verified': False, 'removed_hard_records': [
                    {'scope': 'AC:round:1', 'reason': None, 'status': 'BUDGET_EXHAUSTED',
                     'technical_state': None, 'error': None}]}}
        self.python = {'status': 'BUDGET_EXHAUSTED', 'request_number': 2,
            'budget_valid': False, 'accepted_for_evaluation': False, 'x': [],
            'response_may_arrive_later': True,
            'publication_read': {'transient_read_errors': {'FileNotFoundError': 4}}}
        self.metadata = {'request_number': 2, 'method_deadline_bound': True,
                         'absolute_deadline': 1300.0}
        self.cancel = self.folder/'matlab/request_000002.cancel'
        self.cancel.write_text(adapter.OVERWRITTEN_MARKER+'\n', encoding='ascii')

    @staticmethod
    def numeric():
        return {'accepted': True, 'report': {'accepted': True, 'reasons': []},
                'within_budget': True, 'completed_at_s': 250.0}

    def execute(self, *, input_valid=True, source_valid=True):
        for suffix, value in (('python', self.python), ('input', self.metadata)):
            (self.folder/f'matlab/request_000002.{suffix}.json').write_text(
                json.dumps(value), encoding='utf-8')
        raw_before, original_before = deepcopy(self.raw), deepcopy(self.original)
        with patch.object(adapter.inherited, 'result_records', return_value=self.original) as call:
            result = adapter.result_records(self.job, self.raw, {}, self.folder,
                input_valid=input_valid, source_valid=source_valid)
        call.assert_called_once()
        self.assertEqual(self.raw, raw_before)
        self.assertEqual(self.original, original_before)
        self.assertEqual(result['usable_U_J'], self.original['usable_U_J'])
        return result

    def reject(self, **kw):
        result = self.execute(**kw)
        self.assertFalse(result['cancel_overwrite_audit']['applied'])
        self.assertEqual(result['execution'], self.original['execution'])
        self.assertEqual(result['context']['hard_errors'], self.original['context']['hard_errors'])

    def test_01_complete_root_cutoff_derives_status_only(self):
        result = self.execute()
        self.assertTrue(result['cancel_overwrite_audit']['applied'])
        self.assertEqual(result['execution']['execution_status'], adapter.NORMAL)
        self.assertEqual(result['context']['hard_errors'], [])
        self.assertEqual(result['cancel_overwrite_audit']['original_context_hard_errors'],
                         [adapter.MARKER_ERROR])
        self.assertEqual(result['cancel_overwrite_audit']['original_execution_status'],
                         'TECHNICAL_FAILURE_CONFIRMED')
        self.assertEqual(result['completion_metrics'], self.original['completion_metrics'])
        self.assertFalse(result['execution']['new_or_late_candidate_accepted'])
        self.assertFalse(result['cutoff_audit']['cancel_file_verified'])

    def test_02_cutoff_chain_absent_rejected(self):
        self.original['cutoff_audit']['applied'] = False
        self.reject()

    def test_03_extra_hard_error_preserved(self):
        self.original['context']['hard_errors'].append('TRUE_FAULT')
        self.reject()

    def test_04_current_deadline_violation_preserved(self):
        self.original['current_schedule_audit']['passed'] = False
        self.reject()

    def test_05_input_or_source_identity_missing(self):
        self.reject(input_valid=False)
        self.reject(source_valid=False)

    def test_06_prior_incomplete_request_preserved(self):
        self.raw['augmented_transport']['requests'][0]['within_budget'] = False
        self.reject()

    def test_07_actual_numeric_rejection_preserved(self):
        self.original['context']['observed_numerical_rejection'] = True
        self.reject()

    def test_08_rejected_transport_report_cannot_hide_behind_marker(self):
        self.request['numerical_checks'][0]['report']['accepted'] = False
        self.reject()

    def test_09_nondeadline_reason_preserved(self):
        self.request['failure_reasons'].append('NATIVE_NUMERICAL_CONSISTENCY_CONFLICT')
        self.reject()

    def test_10_missing_marker_preserved(self):
        self.cancel.unlink()
        self.reject()

    def test_11_arbitrary_marker_preserved(self):
        self.cancel.write_text('arbitrary cancel\n', encoding='ascii')
        self.reject()

    def test_12_wrong_budget_rejected(self):
        self.raw['timing']['limit_s'] = 301
        self.reject()

    def test_13_absolute_deadline_mismatch_rejected(self):
        self.metadata['absolute_deadline'] = 1301.0
        self.reject()

    def test_14_late_native_vector_rejected(self):
        self.python['x'] = [1]
        self.reject()

    def test_15_late_native_admission_rejected(self):
        self.python['accepted_for_evaluation'] = True
        self.reject()

    def test_16_late_check_rejected(self):
        self.request['numerical_checks'][0]['completed_at_s'] = 300.1
        self.reject()

    def test_17_missing_isolation_proof_rejected(self):
        self.original['context']['worker_isolation'] = 'UNKNOWN'
        self.reject()

    def test_18_request_identity_mismatch_rejected(self):
        self.metadata['request_number'] = 3
        self.reject()

    def test_19_generic_marker_without_budget_refusal_rejected(self):
        self.python['status'] = 'NUMERICAL_FAILURE'
        self.reject()

    def test_20_no_safe_U_does_not_become_zero_or_new_U(self):
        self.original['context'].pop('safe_receipt')
        self.original['usable_U_J'] = None
        self.original['execution'] = adapter.classify_execution(self.raw, self.original['context'])
        result = self.execute()
        self.assertTrue(result['cancel_overwrite_audit']['applied'])
        self.assertIsNone(result['execution']['usable_U_J'])
        self.assertFalse(result['execution']['safe_witness_preserved'])

    def test_21_wrong_final_scope_rejected(self):
        self.original['cutoff_audit']['removed_hard_records'][0]['scope'] = 'unrelated'
        self.reject()

    def test_22_late_safe_receipt_not_accepted(self):
        self.original['context']['safe_receipt']['formed_at_s'] = 301.0
        self.reject()

    def test_23_method_error_survives(self):
        self.raw['error'] = 'real technical failure'
        self.reject()

    def test_24_late_native_response_is_not_read(self):
        # Deliberately invalid JSON: any read/admission would fail this test.
        late = self.folder/'matlab/request_000002.response.json'
        late.write_text('LATE NATIVE VECTOR MUST NOT BE READ', encoding='ascii')
        result = self.execute()
        self.assertTrue(result['cancel_overwrite_audit']['applied'])


def real_replay(test_result):
    root, repo = adapter.ROOT, adapter.ROOT.parents[1]
    archive = root/'results/deadline_execution01'
    if not (archive/'process_terminal.json').is_file():
        raise RuntimeError('Original campaign must be stopped before replay')
    read = lambda p: json.loads(Path(p).read_text(encoding='utf-8'))
    d = read(archive/'declaration.json')
    slot_id = 'beta_1.0__R1__anchor_linked4'
    row = read(archive/'claims'/(slot_id+'_result.json'))
    folder = archive/'calls/beta_1.0__R1/anchor_linked4'
    raw = read(folder/'wrapper_raw_result.json')
    original_paths = sorted(p for p in archive.rglob('*') if p.is_file())
    before = {p.relative_to(repo).as_posix(): adapter._hash(p) for p in original_paths}
    source_hash = {name: adapter._hash(repo/name) for name in d['source_sha256']}
    if source_hash != d['source_sha256']:
        raise RuntimeError('Original frozen source changed')
    guards = dict.fromkeys(('whole', 'linked', 'heuristic', 'matlab', 'milp', 'linprog',
                           'model', 'heat', 'candidate_heat', 'scene_heat', 'subprocess', 'seed'), 0)
    def forbidden(key):
        def stop(*args, **kw):
            guards[key] += 1
            raise AssertionError('Forbidden replay scientific call: '+key)
        return stop
    import formal_milp, linked_method, heuristic_runner, matlab_bridge, milp
    import thermal, scene_adapter, initial_schedule, scipy.optimize
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
        job = {k: v for k, v in row.items() if k in
               ('id', 'method', 'seed', 'opened_count', 'preeliminate_closed_anchors')}
        derived = adapter.result_records(job, raw, d['inputs'][row['problem_id']], folder,
            input_valid=row['records']['context']['input_identity_valid'],
            source_valid=row['records']['context']['source_identity_valid'], errors=row['errors'])
    original = row['records']
    proof = derived['cancel_overwrite_audit']
    checks = {
        'pure_fixture_suite_passed': test_result.wasSuccessful(),
        'original_sole_cancel_error': original['context']['hard_errors'] == [adapter.MARKER_ERROR],
        'derived_adapter_applied': proof['applied'] is True,
        'original_status_preserved_in_explanation': proof['original_execution_status']
            == original['execution']['execution_status'] == 'TECHNICAL_FAILURE_CONFIRMED',
        'original_hard_errors_preserved_in_explanation': proof['original_context_hard_errors']
            == original['context']['hard_errors'],
        'normal_cutoff_derived': derived['execution']['execution_status'] == adapter.NORMAL,
        'exact_existing_U_preserved': derived['usable_U_J'] == original['usable_U_J'],
        'safe_formation_time_preserved': derived['execution']['usable_safe_formed_at_s']
            == original['execution']['usable_safe_formed_at_s'],
        'current_deadline_schedule_audit_passed': derived['current_schedule_audit']['passed'] is True,
        'original_record_reproduced_before_derivation': proof['original_execution'] == original['execution'],
        'original_campaign_files_unchanged': all(adapter._hash(repo/p) == digest for p, digest in before.items()),
        'all_240_frozen_sources_unchanged': len(source_hash) == 240 and source_hash == d['source_sha256'],
        'no_scientific_calls': not any(guards.values()),
        'no_late_candidate_or_new_safe_result': derived['execution']['new_or_late_candidate_accepted'] is False
            and proof['new_safe_evaluation'] is False,
    }
    return {'protocol': 'K163-read-only-cancel-repair-review-v1', 'passed': all(checks.values()),
        'checks': checks, 'checks_run': len(checks),
        'failed_checks': [k for k, value in checks.items() if not value],
        'pure_fixture_tests': test_result.testsRun,
        'fixture_failures': len(test_result.failures), 'fixture_errors': len(test_result.errors),
        'slot_id': slot_id, 'original_slot_state': row['state'],
        'original_execution_status': original['execution']['execution_status'],
        'derived_execution_status': derived['execution']['execution_status'],
        'original_hard_errors': original['context']['hard_errors'],
        'derived_hard_errors': derived['context']['hard_errors'],
        'original_U_J': original['usable_U_J'], 'derived_U_J': derived['usable_U_J'],
        'original_safe_formed_at_s': original['execution']['usable_safe_formed_at_s'],
        'cancel_overwrite_audit': proof, 'blocked_calls': guards,
        'source_sha256': source_hash, 'original_archive_file_sha256': before,
        'adapter_sha256': adapter._hash(adapter.__file__),
        'test_script_sha256': adapter._hash(__file__),
        'new_research_calls': 0, 'new_models': 0, 'new_thermal_evaluations': 0,
        'new_safe_U': False, 'original_data_modified': False,
        'original_terminal_overwritten': False, 'original_claims_modified': False,
        'automatic_continuation_or_new_budget_authorized': False,
        'conclusion': 'Only the derived record is a normal root-time cutoff with the final '
            'request still pending. The original technical-failure record remains intact. '
            'Its pre-cutoff complete safe U is preserved exactly; no late vector was admitted. '
            'This read-only review grants neither a rerun nor a new research budget.'}


if __name__ == '__main__':
    replay = '--replay-original' in sys.argv
    output = None
    if '--output' in sys.argv:
        output = Path(sys.argv[sys.argv.index('--output')+1])
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CancelAdapterTests)
    results = unittest.TextTestRunner(verbosity=2).run(suite)
    report = real_replay(results) if replay else None
    if report is not None:
        if output is None:
            raise ValueError('Replay requires an explicit new --output path')
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
        print(json.dumps({k: report[k] for k in ('passed', 'checks_run', 'failed_checks',
            'pure_fixture_tests', 'original_execution_status', 'derived_execution_status',
            'original_U_J', 'derived_U_J', 'blocked_calls')}, ensure_ascii=False))
    raise SystemExit(0 if results.wasSuccessful() and (report is None or report['passed']) else 1)
