"""Small mathematical/record fixtures only; no campaign or scientific calls."""
import unittest
from pathlib import Path
import uuid
import analyse_p2 as a


class PureTests(unittest.TestCase):
    def test_interval_strictness_and_missing_energy(self):
        self.assertTrue(a.strictly_lower(['1', '2'], ['3', '4']))
        self.assertFalse(a.strictly_lower(['1', '3'], ['3', '4']))
        self.assertIsNone(a.strictly_lower(None, ['3', '4']))
        self.assertIsNone(a.interval(['4', '3']))

    def test_feedback_ignores_final_scene_alias(self):
        raw = {'feedback': [{'rows_added': 1}], 'phases': [{'scenes': {'AB': {'solver_result': {'feedback': [{'rows_added': 2}]}}}}],
               'scenes': {'AB': {'feedback': [{'rows_added': 2}]}}}
        self.assertEqual(len(a.saved_feedback(raw)), 2)

    def test_phase_no_improvement_and_strict_change(self):
        metrics = {'initial_complete_SAFE_energy_interval_J': ['10', '10'],
            'phases': [{'kind': 'method_phase', 'phase_index': 1, 'baseline_complete_energy_interval_J': ['10', '10']},
                       {'kind': 'method_phase', 'phase_index': 2, 'baseline_complete_energy_interval_J': ['10', '10']}]}
        rows = a.phase_energies({'global_updates': [{'phase_index': 2, 'weighted_energy_J': ['8', '9']}]}, metrics)
        self.assertFalse(rows[0]['strict_energy_reduction_from_entry'])
        self.assertTrue(rows[1]['strict_energy_reduction_from_entry'])
        self.assertEqual(rows[1]['upper_bound_reduction_J'], 1)

    def test_stored_evaluation_dedup_not_heat_call_count(self):
        ev = {'problem_id': 'initial_78__R1', 'scenes': {}, 'numerical_protocol': {}, 'state': 'THERMAL_VIOLATION'}
        self.assertEqual(len(a.evaluation_records({'evaluation': ev, 'copy': ev})), 1)

    def test_partial_cohort_keeps_unstarted_and_no_sa_energy(self):
        def row(method, kind, state, safe):
            return {'problem_id': 'initial_78__R1', 'method': method, 'method_kind': kind,
                'slot_state': state, 'safe_U_J': safe, 'safe_energy_interval_J': None,
                'rankable_original_receipt': safe is not None, 'post_passed': None,
                'comparison_usable': False}
        c = a.cohorts([row('whole_milp', 'milp', 'BLOCKED', None), row('heft', 'heft', 'NOT_STARTED', None),
                       row('sa101', 'sa', 'NOT_STARTED', None)])[0]
        self.assertEqual(c['observed_calls'], 1)
        self.assertEqual(c['safe_calls'], 0)
        self.assertIsNone(c['SA_median_J'])
        self.assertIsNone(c['linked_vs_HEFT_reduction_fraction'])

    def test_retained_safe_U_with_bad_post_is_not_ranked(self):
        row = {'problem_id': 'initial_78__R1', 'method': 'sa101', 'method_kind': 'sa',
               'slot_state': 'BLOCKED', 'safe_U_J': 1, 'safe_energy_interval_J': ['1', '1'],
               'rankable_original_receipt': True, 'post_passed': False, 'comparison_usable': False}
        c = a.cohorts([row])[0]
        self.assertEqual(c['safe_calls'], 1)
        self.assertEqual(c['SA_safe_n'], 0)
        self.assertIsNone(c['SA_median_J'])

    def test_no_terminal_refuses_before_output_creation(self):
        root = a.REPO/'.runtime'/('p2_analysis_fixture_'+uuid.uuid4().hex)
        with self.assertRaises(RuntimeError):
            a.main(['--campaign', str(root/'not_started'), '--out', str(root/'must_not_create')])
        self.assertFalse(root.exists())


if __name__ == '__main__': unittest.main()
