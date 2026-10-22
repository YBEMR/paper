"""Small hand-written record fixtures only; no solver, constructor or heat."""
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
import unittest
import uuid
import analyse_deadline as a


def instance():
    return {'id': 'fixture_deadline', 'stage_modes': {
        'pre': [{'unit_id': 'CPU1', 'opp_id': 'L', 'duration_ms': '11/2'}],
        'post': [{'unit_id': 'CPU1', 'opp_id': 'L', 'duration_ms': '2'}]},
        'scenarios': [{'id': 'AB', 'weight': '1', 'stage_instances': [
            {'id': 'pre1', 'shared_stage_id': 'pre', 'request_id': 'A'},
            {'id': 'post1', 'shared_stage_id': 'post', 'request_id': 'A'}],
            'requests': [{'id': 'A', 'application': 'A', 'stage_instance_ids': ['pre1', 'post1'],
                          'release_ms': '0', 'deadline_ms': '12'}]}]}


def candidate():
    return {'scenes': {'AB': [{'stage_id': 'pre1', 'unit': 'CPU1', 'opp': 'L', 'start_ms': '0'},
                              {'stage_id': 'post1', 'unit': 'CPU1', 'opp': 'L', 'start_ms': '10'}]}}


def summary_fixture(*, U='1', post=True, current=True):
    slot = {'ordinal': 1, 'problem_id': 'beta_1.0__R1', 'id': 'heft', 'method': 'heft', 'seed': None}
    evaluation = {'weighted_energy_J': ['1', '1'], 'state': 'SAFE', 'rankable_energy': True}
    raw = {'state': 'SAFE', 'reason': 'DECLARED_SEARCH_COMPLETED', 'evaluation': evaluation,
           'safe_candidate': candidate(), 'safe_upper_bound_J': U,
           'independent_lower_bound': {'lower_bound_J': '1/2', 'formed_at_s': .1,
               'is_global_lower_bound': True, 'scope': 'original_full_domain', 'solver_reported': False}}
    metrics = {'root_stop_at_s': 10, 'complete_SAFE_receipts': [
        {'completed_at_s': 1, 'energy_interval_J': ['1', '1'], 'safe_upper_bound_J': '1'}]}
    record = {'state': 'COMPLETED', 'records': {'usable_U_J': U, 'completion_metrics': metrics,
        'execution': {'execution_status': 'NORMAL_COMPLETION'},
        'context': {'safe_receipt': {'verified': True}}, 'current_schedule_audit': {'passed': current}},
        'postcheck': {'passed': post}}
    return slot, record, raw


class PureTests(unittest.TestCase):
    def row(self, values):
        slot, record, raw = values
        return a.summary_row(slot, record, raw, a.REPO/'.runtime/not_a_real_call', instance(),
                             lambda path: self.fail('Fixture must not read archived bounds'))

    def test_01_interval_strictness_and_missing_energy(self):
        self.assertTrue(a.strictly_lower(['1', '2'], ['3', '4']))
        self.assertFalse(a.strictly_lower(['1', '3'], ['3', '4']))
        self.assertIsNone(a.strictly_lower(None, ['3', '4']))
        self.assertIsNone(a.interval(['4', '3']))

    def test_02_exact_fractional_deadline_boundary(self):
        one, schedule = instance(), candidate()
        one['scenarios'][0]['requests'][0]['deadline_ms'] = '11/2'
        schedule['scenes']['AB'][1]['start_ms'] = '7/2'
        result = a.deadline_margins(one, schedule)
        self.assertTrue(result['complete'])
        self.assertTrue(result['all_deadlines_met'])
        self.assertEqual(result['minimum_margin_exact_ms'], '0')
        self.assertEqual(result['requests'][0]['completion_exact_ms'], '11/2')

    def test_03_fractionally_late_not_rounded(self):
        one = instance()
        one['scenarios'][0]['requests'][0]['deadline_ms'] = '119999/10000'
        result = a.deadline_margins(one, candidate())
        self.assertTrue(result['complete'])
        self.assertFalse(result['all_deadlines_met'])
        self.assertEqual(F(result['minimum_margin_exact_ms']), F(-1, 10000))

    def test_04_missing_or_duplicate_saved_stage_is_not_complete(self):
        for kind in ('missing', 'duplicate', 'mode', 'scene'):
            c = candidate()
            if kind == 'missing': c['scenes']['AB'].pop()
            elif kind == 'duplicate': c['scenes']['AB'][1] = deepcopy(c['scenes']['AB'][0])
            elif kind == 'mode': c['scenes']['AB'][0]['opp'] = 'H'
            else: c['scenes']['AC'] = []
            self.assertFalse(a.deadline_margins(instance(), c)['complete'])

    def test_05_complete_safe_row_keeps_U_and_margin(self):
        row = self.row(summary_fixture())
        self.assertEqual(row['safe_U_J'], 1.)
        self.assertEqual(row['comparison_safe_U_J'], 1.)
        self.assertTrue(row['comparison_usable'])
        self.assertEqual(row['min_deadline_margin_exact_ms'], '0')
        self.assertTrue(row['safe_curve_minimum_matches_final_U'])

    def test_06_bad_post_does_not_rank_retained_original_U(self):
        row = self.row(summary_fixture(post=False))
        self.assertEqual(row['safe_U_J'], 1.)
        self.assertIsNone(row['comparison_safe_U_J'])
        self.assertFalse(row['comparison_usable'])

    def test_07_current_deadline_gate_required(self):
        row = self.row(summary_fixture(current=False))
        self.assertEqual(row['safe_U_J'], 1.)
        self.assertIsNone(row['comparison_safe_U_J'])
        self.assertFalse(row['comparison_usable'])

    def test_08_explanatory_negative_margin_blocks_comparison(self):
        slot, record, raw = summary_fixture()
        raw['safe_candidate']['scenes']['AB'][1]['start_ms'] = '15'
        row = self.row((slot, record, raw))
        self.assertTrue(row['final_deadline_anomaly'])
        self.assertFalse(row['comparison_usable'])

    def test_09_normal_without_U_does_not_get_zero_energy(self):
        slot, record, raw = summary_fixture(U=None)
        raw.update(state='UNRESOLVED', reason='NO_COMPLETE_SAFE_LINKED_SEED',
                   safe_candidate=None, evaluation=None)
        record['records']['context'] = {}
        record['records']['no_safe_seed_audit'] = {'method_outcome': 'NO_COMPLETE_SAFE_SEED_WITHIN_FIXED_THREE_TEMPLATE_RULE'}
        record['records']['completion_metrics'] = {}
        row = self.row((slot, record, raw))
        self.assertIsNone(row['safe_U_J'])
        self.assertIsNone(row['comparison_safe_U_J'])
        self.assertFalse(row['comparison_usable'])
        self.assertEqual(row['deadline_audit']['requests'], [])
        self.assertIsNotNone(row['normal_method_outcome'])

    def test_10_running_minimum_filters_late_and_preserves_source(self):
        curve = [{'completed_at_s': 10, 'safe_upper_bound_J': '5'},
                 {'completed_at_s': 20, 'safe_upper_bound_J': '6'},
                 {'completed_at_s': 30, 'safe_upper_bound_J': '4'},
                 {'completed_at_s': 300, 'safe_upper_bound_J': '1'}]
        prior = deepcopy(curve)
        self.assertEqual([r['saved_running_min_U_exact_J'] for r in a.running_safe_minimum(curve)], ['5', '5', '4'])
        self.assertEqual(curve, prior)

    def test_11_safe_interval_mismatch_is_not_a_curve_point(self):
        curve = [{'completed_at_s': 10, 'safe_upper_bound_J': '5', 'energy_interval_J': ['1', '4']}]
        self.assertEqual(a.running_safe_minimum(curve), [])

    def test_12_sa_success_median_keeps_declared_denominator(self):
        values = []
        for i, u in enumerate((1., None, 3., None, None), 101):
            values.append({'problem_id': 'beta_1.0__R1', 'method': 'sa'+str(i), 'method_kind': 'sa',
                'slot_state': 'COMPLETED', 'safe_U_J': u, 'safe_energy_interval_J': None,
                'rankable_original_receipt': u is not None, 'post_passed': u is not None,
                'comparison_usable': u is not None})
        c = a.cohorts(values)[0]
        self.assertEqual((c['SA_safe_n'], c['SA_declared_n'], c['SA_missing_or_unusable_n']), (2, 5, 3))
        self.assertEqual(c['SA_median_J'], 2.)
        self.assertIsNone(c['linked_vs_HEFT_reduction_fraction'])

    def test_13_no_sa_success_is_missing_not_zero(self):
        row = {'problem_id': 'beta_1.0__R1', 'method': 'sa101', 'method_kind': 'sa',
            'slot_state': 'NOT_STARTED', 'safe_U_J': None, 'safe_energy_interval_J': None,
            'rankable_original_receipt': False, 'post_passed': None, 'comparison_usable': False}
        c = a.cohorts([row])[0]
        self.assertIsNone(c['SA_median_J'])
        self.assertEqual(c['observed_calls'], 0)

    def test_14_feedback_ignores_aliases(self):
        raw = {'feedback': [{'rows_added': 1}], 'phases': [{'scenes': {'AB': {'solver_result': {'feedback': [{'rows_added': 2}]}}}}],
               'scenes': {'AB': {'feedback': [{'rows_added': 2}]}}}
        self.assertEqual(len(a.saved_feedback(raw)), 2)

    def test_15_phases_keep_no_change_as_no_change(self):
        metrics = {'initial_complete_SAFE_energy_interval_J': ['10', '10'], 'phases': [
            {'kind': 'method_phase', 'phase_index': 1, 'baseline_complete_energy_interval_J': ['10', '10']},
            {'kind': 'method_phase', 'phase_index': 2, 'baseline_complete_energy_interval_J': ['10', '10']}]}
        result = a.phase_energies({'global_updates': [{'phase_index': 2, 'weighted_energy_J': ['8', '9']}]}, metrics)
        self.assertFalse(result[0]['strict_energy_reduction_from_entry'])
        self.assertTrue(result[1]['strict_energy_reduction_from_entry'])

    def test_16_local_solver_bound_is_not_L0(self):
        raw = {'independent_lower_bound': {'scope': 'local_domain', 'lower_bound_J': '1',
               'is_global_lower_bound': False, 'solver_reported': True}}
        self.assertIsNone(a.choose_L0(raw, a.REPO/'.runtime/does_not_exist', lambda path: self.fail('no read')))

    def test_17_no_terminal_refuses_before_output_creation(self):
        root = a.REPO/'.runtime'/('deadline_analysis_fixture_'+uuid.uuid4().hex)
        with self.assertRaises(RuntimeError):
            a.main(['--campaign', str(root/'not_started'), '--out', str(root/'must_not_create')])
        self.assertFalse(root.exists())

    def test_18_evaluator_object_dedup_not_call_count(self):
        value = {'problem_id': 'beta_1.0__R1', 'scenes': {}, 'numerical_protocol': {}, 'state': 'THERMAL_VIOLATION'}
        self.assertEqual(len(a.evaluation_records({'a': value, 'copy': value})), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
