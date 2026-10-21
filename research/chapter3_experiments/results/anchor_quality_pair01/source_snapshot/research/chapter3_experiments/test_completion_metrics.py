"""Pure saved-record fixtures; no project physics or solver imports."""
from copy import deepcopy
import unittest

from completion_metrics import build_completion_metrics


def receipt(at, low='9', high='10'):
    return dict(state='SAFE', rankable_energy=True,
                scenes={'AB': {'state': 'SAFE', 'rankable_energy': True, 'complete': True},
                        'AC': {'state': 'SAFE', 'rankable_energy': True, 'complete': True}},
                completed_at_elapsed_s=at, weighted_energy_J=[low, high],
                safe_upper_bound_J=high)


def candidate():
    return {'scenes': {'AB': [], 'AC': []}}


def item(at, low='9', high='10', accepted=True):
    return dict(accepted_safe=accepted, candidate=candidate(), evaluation=receipt(at, low, high))


def result(*items):
    return dict(method='heft', state='SAFE', evaluations=list(items),
                timing=dict(limit_s=300, method_elapsed_s=299, phase_records=[]))


class CompletionMetricsTests(unittest.TestCase):
    def test_unrun_is_not_applicability_or_zero(self):
        measured = build_completion_metrics(None)
        self.assertEqual(measured['status'], 'NOT_RUN')
        self.assertEqual(measured['matlab_startup']['status'], 'NOT_RUN')
        self.assertIsNone(measured['matlab_startup']['wall_s'])

    def test_executed_heuristic_matlab_is_not_applicable(self):
        measured = build_completion_metrics(result(item(3)))
        self.assertEqual(measured['matlab_startup']['status'], 'NOT_APPLICABLE')
        self.assertIsNone(measured['matlab_startup']['wall_s'])
        self.assertEqual(measured['first_complete_SAFE_at_s'], 3)

    def test_matlab_missing_log_is_unknown(self):
        self.assertEqual(build_completion_metrics(result(), uses_matlab=True)
                         ['matlab_startup']['status'], 'UNKNOWN')

    def test_measured_startup_and_phase_actual_are_distinct(self):
        saved = result(item(5))
        saved['timing']['phase_records'] = [dict(phase='solver_startup',
            start_s=6, end_s=24, wall_s=18, depth=0)]
        measured = build_completion_metrics(saved, uses_matlab=True)
        self.assertEqual(measured['matlab_startup']['wall_s'], 18)
        self.assertEqual(measured['phases'][0]['actual_interval_s'], 18)
        self.assertEqual(measured['phases'][0]['root_remaining_at_entry_s'], 294)
        self.assertIsNone(measured['phases'][0]['planned_total_cap_s'])

    def test_initial_safe_is_not_improvement(self):
        measured = build_completion_metrics(result(item(3)))
        self.assertEqual(measured['strict_improvement_status'], 'NOT_OBSERVED_BEFORE_CUTOFF')
        self.assertIsNone(measured['first_strict_improvement_at_s'])

    def test_heuristic_accounting_frame_has_no_phase_improvement_claim(self):
        saved = result(item(3), item(9, '7', '8'))
        saved['timing']['phase_records'] = [dict(phase='continuous_thermal_energy_evaluation',
            start_s=7, end_s=10, wall_s=3, depth=1)]
        measured = build_completion_metrics(saved)
        self.assertEqual(measured['first_strict_improvement_at_s'], 9)
        frame = measured['phases'][0]
        self.assertEqual(frame['actual_interval_s'], 3)
        self.assertIsNone(frame['first_strict_improvement_at_s'])
        self.assertEqual(frame['strict_improvement_status'],
                         'NOT_APPLICABLE_ACCOUNTING_OR_LOCAL_SLICE')

    def test_strict_improvement_requires_interval_separation(self):
        measured = build_completion_metrics(result(item(3), item(9, '8', '8.5')))
        self.assertEqual(measured['first_strict_improvement_at_s'], 9)
        self.assertEqual(measured['strict_improvement_status'], 'OBSERVED_INTERVAL_STRICT')

    def test_upper_decrease_with_overlap_is_not_strict(self):
        measured = build_completion_metrics(result(item(3), item(9, '8.5', '9.5')))
        self.assertIsNone(measured['first_strict_improvement_at_s'])
        self.assertEqual(measured['strict_improvement_status'], 'UPPER_DECREASE_WITHOUT_INTERVAL_SEPARATION')

    def test_equal_boundary_is_not_strict(self):
        measured = build_completion_metrics(result(item(3), item(9, '8', '9')))
        self.assertIsNone(measured['first_strict_improvement_at_s'])

    def test_late_receipt_and_unaccepted_receipt_cannot_improve(self):
        measured = build_completion_metrics(result(item(3), item(300, '1', '2'), item(5, '1', '2', False)))
        self.assertEqual(len(measured['complete_SAFE_receipts']), 1)
        self.assertIsNone(measured['first_strict_improvement_at_s'])

    def test_unknown_initial_safe_does_not_invent_improvement(self):
        measured = build_completion_metrics(result())
        self.assertEqual(measured['strict_improvement_status'], 'NO_INITIAL_COMPLETE_SAFE')
        self.assertIsNone(measured['first_complete_SAFE_at_s'])

    def test_partial_scene_safe_and_broken_upper_are_rejected(self):
        a, b = item(3), item(4)
        del a['evaluation']['scenes']['AC']
        b['evaluation']['safe_upper_bound_J'] = '9'
        measured = build_completion_metrics(result(a, b))
        self.assertFalse(measured['complete_SAFE_receipts'])

    def test_events_alone_are_not_full_receipts(self):
        saved = result()
        saved['events'] = [dict(event='safe_upper_bound', at_s=3, safe_upper_bound_J='1')]
        saved['first_safe_at_s'] = 3
        self.assertIsNone(build_completion_metrics(saved)['first_complete_SAFE_at_s'])

    def test_prefix_or_missing_completion_flag_cannot_be_full_safe(self):
        prefix, unknown = item(4, '1', '2'), item(5, '1', '2')
        prefix['evaluation']['scenes']['AB']['complete'] = False
        del unknown['evaluation']['scenes']['AC']['complete']
        measured = build_completion_metrics(result(item(3), prefix, unknown))
        self.assertEqual(len(measured['complete_SAFE_receipts']), 1)
        self.assertIsNone(measured['first_strict_improvement_at_s'])

    def test_wrapped_physical_scene_completion_is_required(self):
        complete, prefix = item(3), item(4, '1', '2')
        for record in (complete, prefix):
            record['evaluation']['scenes'] = {
                scene: dict(state='SAFE', rankable_energy=True, result=physical)
                for scene, physical in record['evaluation']['scenes'].items()}
        prefix['evaluation']['scenes']['AB']['result']['complete'] = False
        measured = build_completion_metrics(result(complete, prefix))
        self.assertEqual(len(measured['complete_SAFE_receipts']), 1)
        self.assertEqual(measured['first_complete_SAFE_at_s'], 3)
        self.assertIsNone(measured['first_strict_improvement_at_s'])

    def test_whole_initial_witness_and_nested_diagnostic(self):
        saved = result()
        saved.pop('evaluations')
        saved['initialisation'] = dict(witness=dict(candidate=candidate(), evaluation=receipt(3)))
        saved['solver_diagnostic'] = dict(diagnostic=dict(evaluations=[item(8, '7', '8')]))
        measured = build_completion_metrics(saved, uses_matlab=True)
        self.assertEqual(measured['first_strict_improvement_at_s'], 8)
        self.assertEqual(measured['initial_complete_SAFE_energy_interval_J'], ['9', '10'])

    def test_linked_phase_baseline_requires_full_aggregate(self):
        initial, first, second = receipt(3), receipt(40, '7', '8'), receipt(90, '6', '6.5')
        aggregates, updates = [], []
        for evaluation, phase in ((initial, 0), (first, 1), (second, 2)):
            aggregate = dict(evaluation, safe_candidate=candidate())
            aggregates.append(aggregate)
            updates.append(dict(weighted_energy_J=evaluation['weighted_energy_J'],
                safe_upper_bound_J=evaluation['safe_upper_bound_J'],
                committed_at_s=evaluation['completed_at_elapsed_s'], phase_index=phase))
        saved = result()
        saved.update(global_updates=updates, aggregation_attempts=aggregates,
            initial_global_weighted_energy_J=['9', '10'], phases=[
                dict(phase_index=1, name='N1', started_at_s=10, completed_at_s=50, scenes={}),
                dict(phase_index=2, name='linked', started_at_s=70, completed_at_s=100, scenes={})])
        measured = build_completion_metrics(saved, uses_matlab=True)
        self.assertEqual(measured['first_strict_improvement_at_s'], 40)
        self.assertEqual(measured['phases'][1]['first_strict_improvement_at_s'], 90)
        self.assertEqual(measured['phases'][1]['first_strict_improvement_after_entry_s'], 20)
        self.assertEqual(measured['phases'][1]['pre_record_transition_s'], 20)
        self.assertEqual(measured['phases'][1]['baseline_complete_energy_interval_J'], ['7', '8'])

    def test_native_request_upper_not_relabelled_effective(self):
        saved = result()
        saved['rounds'] = [dict(request_number=1, solver_max_time_s=60, budget_valid=False),
                           dict(request_number=2, solver_max_time_s=60,
                                response=dict(options={'MaxTime': 12},
                                              phase_seconds={'intlinprog_call': 13}))]
        measured = build_completion_metrics(saved, uses_matlab=True)
        self.assertIsNone(measured['native_requests'][0]['native_effective_MaxTime_s'])
        self.assertEqual(measured['native_requests'][1]['native_effective_MaxTime_s'], 12)
        self.assertEqual(measured['native_requests'][1]['actual_native_call_s'], 13)
        self.assertTrue(measured['native_requests'][1]['diagnostic_only_not_new_U'])

    def test_input_not_mutated_and_invalid_arguments_rejected(self):
        saved = result(item(3))
        original = deepcopy(saved)
        build_completion_metrics(saved)
        self.assertEqual(saved, original)
        for seconds in (True, 0, float('inf')):
            with self.assertRaises(ValueError):
                build_completion_metrics(saved, seconds=seconds)


if __name__ == '__main__':
    unittest.main()
