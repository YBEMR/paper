"""Data-only K144 status boundary checks; no method/solver/thermal imports."""

from copy import deepcopy
import unittest

from execution_status import classify_execution


def base_context():
    return {
        'input_identity_valid': True,
        'source_identity_valid': True,
        'current_request_identity_valid': True,
        'cutoff_s': 300.,
        'hard_errors': [],
        'observed_numerical_rejection': False,
        'worker_isolation': 'NOT_APPLICABLE',
        'prior_requests_complete': True,
        'completion_verified': True,
        'root_deadline_confirmed': False,
        'deadline_causal_trace': False,
        'last_request': {'state': 'NONE'},
        'safe_receipt': {'verified': True, 'identity_valid': True,
                         'complete': True, 'formed_at_s': 40.,
                         'energy_upper_J': '11/10'},
    }


def deadline_context():
    context = base_context()
    context.update(root_deadline_confirmed=True, deadline_causal_trace=True,
                   completion_verified=False, worker_isolation='VERIFIED')
    context['last_request'] = {
        'state': 'PENDING', 'pending_at_cutoff': True,
        'refuses_late_candidate': True, 'deadline_causal_trace': True,
        'deadline_reasons': ['CALLBACK_PUBLICATIONS_NOT_FULLY_CHECKED',
                             'BUDGET_BEFORE_FINAL_ADMISSION',
                             'BUDGET_DURING_ADMISSION_ARCHIVE'],
    }
    return context


class ExecutionStatusTests(unittest.TestCase):
    def classify(self, context=None, result=None):
        return classify_execution({} if result is None else result,
                                  base_context() if context is None else context)

    def test_normal_completion_is_not_optimality_or_infeasibility(self):
        value = self.classify(result={'state': 'OPTIMAL', 'exitflag': -2})
        self.assertEqual(value['execution_status'], 'NORMAL_COMPLETION')
        self.assertTrue(value['safe_witness_preserved'])
        self.assertEqual(value['usable_U_J'], '11/10')
        self.assertFalse(value['independently_proven_optimal'])
        self.assertFalse(value['independently_proven_infeasible'])

    def test_K142_like_deadline_preserves_independent_safe(self):
        context = deadline_context()
        context['safe_receipt'].update(formed_at_s=222.250, energy_upper_J='0.962885037941')
        value = self.classify(context, {'budget_exhausted': True, 'reason': 'wall_time_limit'})
        self.assertEqual(value['execution_status'], 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST')
        self.assertTrue(value['safe_witness_preserved'])
        self.assertEqual(value['last_request'], 'UNRESOLVED')
        self.assertFalse(value['new_or_late_candidate_accepted'])
        self.assertFalse(value['worker_may_be_reused'])

    def test_deadline_without_safe_is_not_infeasibility(self):
        context = deadline_context()
        context.pop('safe_receipt')
        value = self.classify(context)
        self.assertEqual(value['execution_status'], 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST')
        self.assertIsNone(value['usable_U_J'])
        self.assertFalse(value['independently_proven_infeasible'])

    def test_heuristic_normal_deadline_without_native_worker(self):
        context = base_context()
        context.update(root_deadline_confirmed=True, deadline_causal_trace=True,
                       completion_verified=False)
        value = self.classify(context)
        self.assertEqual(value['execution_status'], 'NORMAL_TIME_LIMIT')

    def test_real_error_is_not_hidden_by_budget_reason(self):
        value = self.classify(deadline_context(), {'error': 'wall_time_limit: payload corrupt'})
        self.assertEqual(value['execution_status'], 'TECHNICAL_FAILURE_CONFIRMED')
        self.assertTrue(value['safe_witness_preserved'])

    def test_explicit_hard_fault_and_deadline_coexist(self):
        context = deadline_context()
        context['hard_errors'] = ['RESOURCE_FAILURE']
        self.assertEqual(self.classify(context)['execution_status'], 'TECHNICAL_FAILURE_CONFIRMED')

    def test_actual_numeric_report_rejection_overrides_deadline(self):
        context = deadline_context()
        context['numerical_checks'] = [{'accepted': False, 'report': {'accepted': False}}]
        value = self.classify(context)
        self.assertEqual(value['execution_status'], 'NUMERICAL_ANOMALY_OBSERVED')
        self.assertTrue(value['safe_witness_preserved'])

    def test_aggregate_accepted_false_is_not_numeric_failure(self):
        context = deadline_context()
        context['numerical_checks'] = [{'accepted': False, 'reason': 'BUDGET_EXHAUSTED'}]
        value = self.classify(context, {'accepted': False})
        self.assertEqual(value['execution_status'], 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST')

    def test_unknown_numerical_evidence_stays_unresolved(self):
        context = deadline_context()
        context['observed_numerical_rejection'] = None
        self.assertEqual(self.classify(context)['execution_status'], 'STATUS_UNRESOLVED')

    def test_global_identity_damage_revokes_rankable_safe(self):
        for key in ('input_identity_valid', 'source_identity_valid'):
            with self.subTest(key=key):
                context = deadline_context()
                context[key] = False
                value = self.classify(context)
                self.assertEqual(value['execution_status'], 'TECHNICAL_FAILURE_CONFIRMED')
                self.assertFalse(value['safe_witness_preserved'])
                self.assertTrue(value['archival_evidence_retained'])

    def test_last_request_identity_failure_does_not_erase_old_safe(self):
        context = deadline_context()
        context['current_request_identity_valid'] = False
        value = self.classify(context)
        self.assertEqual(value['execution_status'], 'TECHNICAL_FAILURE_CONFIRMED')
        self.assertTrue(value['safe_witness_preserved'])

    def test_old_receipt_identity_or_completeness_is_required(self):
        for key in ('identity_valid', 'complete', 'verified'):
            with self.subTest(key=key):
                context = deadline_context()
                context['safe_receipt'][key] = False
                value = self.classify(context)
                self.assertEqual(value['execution_status'], 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST')
                self.assertFalse(value['safe_witness_preserved'])
                self.assertIsNone(value['usable_U_J'])

    def test_late_or_invalid_safe_timestamp_never_accepted(self):
        for at in (300., 300.01, -1., None, float('nan'), float('inf'), True):
            with self.subTest(at=at):
                context = deadline_context()
                context['safe_receipt']['formed_at_s'] = at
                self.assertFalse(self.classify(context)['safe_witness_preserved'])
        context['safe_receipt']['formed_at_s'] = 299.999
        self.assertTrue(self.classify(context)['safe_witness_preserved'])

    def test_invalid_energy_is_not_a_safe_upper_bound(self):
        for energy in ('nan', 'inf', '-1', None, {}, True, float('inf')):
            with self.subTest(energy=energy):
                context = base_context()
                context['safe_receipt']['energy_upper_J'] = energy
                self.assertFalse(self.classify(context)['safe_witness_preserved'])

    def test_missing_callback_before_deadline_is_unresolved(self):
        context = deadline_context()
        context['root_deadline_confirmed'] = False
        self.assertEqual(self.classify(context)['execution_status'], 'STATUS_UNRESOLVED')

    def test_missing_or_unknown_deadline_causality_is_unresolved(self):
        for change in ('root', 'pending', 'refusal', 'trace', 'reason'):
            with self.subTest(change=change):
                context = deadline_context()
                if change == 'root':
                    context['deadline_causal_trace'] = False
                elif change == 'pending':
                    context['last_request']['pending_at_cutoff'] = False
                elif change == 'refusal':
                    context['last_request']['refuses_late_candidate'] = None
                elif change == 'trace':
                    context['last_request']['deadline_causal_trace'] = False
                else:
                    context['last_request']['deadline_reasons'].append('UNKNOWN_ERROR')
                self.assertEqual(self.classify(context)['execution_status'], 'STATUS_UNRESOLVED')

    def test_earlier_incomplete_request_not_excused_by_final_deadline(self):
        context = deadline_context()
        context['prior_requests_complete'] = False
        self.assertEqual(self.classify(context)['execution_status'], 'STATUS_UNRESOLVED')

    def test_cleanup_failure_or_unknown_is_not_normal_deadline(self):
        for isolation, expected in (('FAILED', 'TECHNICAL_FAILURE_CONFIRMED'),
                                    ('UNKNOWN', 'STATUS_UNRESOLVED')):
            with self.subTest(isolation=isolation):
                context = deadline_context()
                context['worker_isolation'] = isolation
                value = self.classify(context)
                self.assertEqual(value['execution_status'], expected)
                self.assertTrue(value['safe_witness_preserved'])
        context = base_context()
        self.assertEqual(self.classify(context, {'matlab_worker_ready': True})['execution_status'],
                         'TECHNICAL_FAILURE_CONFIRMED')

    def test_thermal_unresolved_is_not_new_safe_or_violation(self):
        context = deadline_context()
        context['last_request']['state'] = 'THERMAL_UNRESOLVED'
        value = self.classify(context)
        self.assertEqual(value['execution_status'], 'STATUS_UNRESOLVED')
        self.assertTrue(value['thermal_unresolved'])
        self.assertTrue(value['safe_witness_preserved'])
        self.assertFalse(value['known_violation_preserved'])
        self.assertFalse(value['new_or_late_candidate_accepted'])

    def test_verified_budget_time_violation_retained_independently(self):
        context = deadline_context()
        context['known_violation'] = {'verified': True, 'identity_valid': True,
                                      'complete': True, 'formed_at_s': 280.}
        self.assertTrue(self.classify(context)['known_violation_preserved'])
        context['known_violation']['formed_at_s'] = 301.
        self.assertFalse(self.classify(context)['known_violation_preserved'])

    def test_missing_evidence_and_malformed_result_do_not_manufacture_success(self):
        self.assertEqual(classify_execution({}, {})['execution_status'], 'STATUS_UNRESOLVED')
        self.assertEqual(classify_execution(None, base_context())['execution_status'],
                         'TECHNICAL_FAILURE_CONFIRMED')
        context = base_context()
        context['cutoff_s'] = None
        self.assertEqual(self.classify(context)['execution_status'], 'STATUS_UNRESOLVED')

    def test_classifier_does_not_mutate_inputs(self):
        context = deadline_context()
        result = {'accepted': False, 'budget_exhausted': True}
        before = deepcopy((result, context))
        self.classify(context, result)
        self.assertEqual((result, context), before)


if __name__ == '__main__':
    unittest.main()
