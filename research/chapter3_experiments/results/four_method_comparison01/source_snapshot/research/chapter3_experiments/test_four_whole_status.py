"""Data-only K152 whole-result audit regressions; no optimizer or evaluator."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import four_whole_status as audit
from run_heuristic_followup import scene_spec

HERE = Path(__file__).resolve().parent
OLD = HERE/'results/fair_comparison_preparation01'


class WholeResultAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=HERE/'../../.runtime')
        self.folder = Path(self.tmp.name)
        (self.folder/'matlab').mkdir()
        self.r = audit._read(OLD/'whole_milp/result.json')
        self.d = audit._read(OLD/'declaration.json')
        self.d['scene_spec'] = scene_spec(audit._read(OLD/'input_instance.json'))
        for name in ('session.json', 'closed.json', 'request_000001.input.json', 'request_000001.python.json'):
            self.write('matlab/'+name, audit._read(OLD/'whole_milp/matlab'/name))
        (self.folder/'matlab/request_000001.cancel').write_text('budget\n', encoding='ascii')
        deadline = self.load('matlab/session.json')['external_absolute_deadline']
        self.write('method_budget_identity.json', {'start': deadline-300, 'deadline': deadline,
            'limit_s': 300, 'clock': 'monotonic'})

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, value):
        (self.folder/name).write_text(json.dumps(value), encoding='utf-8')

    def load(self, name):
        return audit._read(self.folder/name)

    def check(self, **kw):
        return audit.result_records(self.r, self.d, self.folder,
            input_valid=kw.get('input_valid', True), source_valid=kw.get('source_valid', True),
            errors=kw.get('errors'))

    def mutate_native(self, key, value):
        self.r['rounds'][0][key] = value
        self.write('matlab/request_000001.python.json', self.r['rounds'][0])

    def test_archived_timeout_preserves_initial_safe(self):
        before = deepcopy(self.r)
        out = self.check()
        self.assertEqual(out['execution']['execution_status'], 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST')
        self.assertEqual(out['usable_U_J'], self.r['safe_upper_bound_J'])
        self.assertEqual(before, self.r)
        self.assertFalse(out['execution']['independently_proven_optimal'])

    def test_own_completed_solver_request(self):
        self.r.update(reason='SAFE_INCUMBENT', budget_exhausted=False)
        self.r['timing']['method_elapsed_s'] = 299
        for key, value in {'status': 'SOLVED', 'budget_valid': True, 'accepted_for_evaluation': True,
            'x': [1]}.items():
            self.mutate_native(key, value)
        self.assertEqual(self.check()['execution']['execution_status'], 'NORMAL_COMPLETION')

    def test_timeout_without_witness_is_not_infeasibility(self):
        self.r.update(state='UNRESOLVED', safe_upper_bound_J=None, evaluation=None, safe_candidate=None)
        self.r['initialisation']['witness'] = None
        out = self.check()
        self.assertEqual(out['execution']['execution_status'], 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST')
        self.assertIsNone(out['usable_U_J'])
        self.assertFalse(out['execution']['independently_proven_infeasible'])

    def test_late_safe_cannot_be_ranked(self):
        self.r['evaluation']['completed_at_elapsed_s'] = 300
        self.assertIsNone(self.check()['usable_U_J'])

    def test_candidate_mismatch_is_not_safe(self):
        self.r['safe_candidate']['scenes']['AB_offset_0ms'][0]['start_ms'] = '5'
        self.assertIsNone(self.check()['usable_U_J'])

    def test_incomplete_idle_tail(self):
        self.r['evaluation']['scenes']['AB_offset_0ms']['covered_until_s'] = '0.3'
        self.assertIsNone(self.check()['usable_U_J'])

    def test_peak_above_limit(self):
        self.r['evaluation']['scenes']['AB_offset_0ms']['peaks_degC']['CPU1'] = ['80', '81']
        self.assertIsNone(self.check()['usable_U_J'])

    def test_energy_aggregation_corruption(self):
        self.r['evaluation']['weighted_energy_J'][0] = '0'
        self.assertIsNone(self.check()['usable_U_J'])

    def test_input_mismatch_invalidates_U(self):
        out = self.check(input_valid=False)
        self.assertEqual(out['execution']['execution_status'], 'TECHNICAL_FAILURE_CONFIRMED')
        self.assertIsNone(out['usable_U_J'])

    def test_source_mismatch_invalidates_U(self):
        self.assertIsNone(self.check(source_valid=False)['usable_U_J'])

    def test_real_error_overrides_time_limit(self):
        out = self.check(errors=['REAL_INTERFACE_ERROR'])
        self.assertEqual(out['execution']['execution_status'], 'TECHNICAL_FAILURE_CONFIRMED')
        self.assertEqual(out['usable_U_J'], self.r['safe_upper_bound_J'])

    def test_actual_numerical_rejection_not_exempt(self):
        self.r['initialisation']['completion']['numerical_acceptance']['accepted_numerically'] = False
        self.assertEqual(self.check()['execution']['execution_status'], 'NUMERICAL_ANOMALY_OBSERVED')

    def test_cleanup_failure_is_fault(self):
        row = self.load('matlab/closed.json')
        row['observed_tree_verified_terminated'] = False
        self.write('matlab/closed.json', row)
        self.assertEqual(self.check()['execution']['execution_status'], 'TECHNICAL_FAILURE_CONFIRMED')

    def test_unbound_native_deadline_is_fault(self):
        row = self.load('matlab/request_000001.input.json')
        row['absolute_deadline'] += 1
        self.write('matlab/request_000001.input.json', row)
        self.assertEqual(self.check()['execution']['execution_status'], 'TECHNICAL_FAILURE_CONFIRMED')

    def test_unbound_root_budget_is_fault(self):
        row = self.load('method_budget_identity.json')
        row['deadline'] += 1
        self.write('method_budget_identity.json', row)
        self.assertEqual(self.check()['execution']['execution_status'], 'TECHNICAL_FAILURE_CONFIRMED')

    def test_late_native_vector_is_never_accepted(self):
        self.mutate_native('x', [1])
        out = self.check()
        self.assertEqual(out['execution']['execution_status'], 'STATUS_UNRESOLVED')
        self.assertFalse(out['execution']['new_or_late_candidate_accepted'])

    def test_unknown_poll_error_not_deadline(self):
        self.mutate_native('publication_read', {'transient_read_errors': {'PermissionError': 1}})
        self.assertEqual(self.check()['execution']['execution_status'], 'STATUS_UNRESOLVED')

    def test_missing_cancel_is_unresolved(self):
        (self.folder/'matlab/request_000001.cancel').unlink()
        self.assertEqual(self.check()['execution']['execution_status'], 'STATUS_UNRESOLVED')

    def test_timely_response_archive_crosses_deadline(self):
        root = self.load('method_budget_identity.json')
        self.mutate_native('status', 'BUDGET_EXHAUSTED_BEFORE_RETURN')
        self.mutate_native('solver_response_complete_at_monotonic', root['deadline']-.01)
        (self.folder/'matlab/request_000001.cancel').unlink()
        out = self.check()
        self.assertEqual(out['execution']['execution_status'], 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST')
        self.assertEqual(out['context']['last_request']['deadline_reasons'], ['BUDGET_DURING_ADMISSION_ARCHIVE'])
        self.assertEqual(out['usable_U_J'], self.r['safe_upper_bound_J'])

    def test_archive_timeout_without_timely_read_stays_unresolved(self):
        root = self.load('method_budget_identity.json')
        self.mutate_native('status', 'BUDGET_EXHAUSTED_BEFORE_RETURN')
        self.mutate_native('solver_response_complete_at_monotonic', root['deadline']+1)
        self.assertEqual(self.check()['execution']['execution_status'], 'STATUS_UNRESOLVED')

    def test_prior_incomplete_round_not_excused(self):
        self.r['rounds'].append(deepcopy(self.r['rounds'][0]))
        self.r['solver_request_attempts'] = 2
        self.assertNotIn(self.check()['execution']['execution_status'], ('NORMAL_COMPLETION',
            'NORMAL_TIME_LIMIT', 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST'))

    def test_solver_infeasible_is_report_not_proof(self):
        self.r.update(reason='SOLVER_REPORTED_INFEASIBLE', budget_exhausted=False)
        self.r['timing']['method_elapsed_s'] = 290
        self.mutate_native('status', 'SOLVED')
        self.mutate_native('budget_valid', True)
        self.mutate_native('exitflag', -2)
        out = self.check()
        self.assertEqual(out['execution']['execution_status'], 'NORMAL_COMPLETION')
        self.assertFalse(out['execution']['independently_proven_infeasible'])


if __name__ == '__main__':
    unittest.main()
