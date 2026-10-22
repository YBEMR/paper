"""Pure saved-data checks, without files, plotting or production imports."""
import unittest

from summarize_cut_pair import compare_options,first_strict_time,interval_comparison


class CutPairSummaryTests(unittest.TestCase):
    def test_upper_reduction_does_not_imply_strict_energy_separation(self):
        self.assertEqual(interval_comparison(['5','10'],['4','6']),
            {'upper_bound_improved':True,'strict_improvement_certified':False})
        self.assertFalse(interval_comparison(['5','10'],['4','5'])['strict_improvement_certified'])
        self.assertTrue(interval_comparison(['5','10'],['3','4'])['strict_improvement_certified'])

    def test_absent_complete_SAFE_interval_is_unknown(self):
        self.assertEqual(interval_comparison(None,['3','4']),
            {'upper_bound_improved':None,'strict_improvement_certified':None})
        self.assertIsNone(first_strict_time(None,[]))

    def test_first_strict_time_uses_initial_lower_endpoint(self):
        updates = [{'committed_at_s':80,'energy_J':['3','4']},
                   {'committed_at_s':40,'energy_J':['4','6']},
                   {'committed_at_s':60,'energy_J':['4','5']}]
        self.assertEqual(first_strict_time(['5','10'],updates),80)

    def test_raw_MaxTime_difference_stays_visible_without_hiding_other_settings(self):
        left = {'CutMaxIterations':10,'MaxTime':59.8,'Heuristics':'basic'}
        right = {'CutMaxIterations':1,'MaxTime':59.7,'Heuristics':'basic'}
        result = compare_options(left,right)
        self.assertFalse(result['all_other_options_equal_raw'])
        self.assertTrue(result['other_settings_equal_excluding_budget_MaxTime'])
        self.assertIn('MaxTime',result['differences'])
        right['Heuristics'] = 'none'
        self.assertFalse(compare_options(left,right)['other_settings_equal_excluding_budget_MaxTime'])


if __name__ == '__main__':
    unittest.main()
