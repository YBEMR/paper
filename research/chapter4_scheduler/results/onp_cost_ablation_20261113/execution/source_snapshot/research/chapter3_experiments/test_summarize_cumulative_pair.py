"""Small saved-data checks only; no files, production imports or execution."""
import unittest

from summarize_cumulative_pair import arrangement_identity,compare_model_arrays,compare_native_options,first_new_legal_time


class CumulativePairSummaryTests(unittest.TestCase):
    def test_arrangement_identity_normalizes_fraction_and_order(self):
        a = {'stage_id':'A','unit':'CPU1','opp':'L','start_ms':'5/2'}
        b = {'stage_id':'B','unit':'NPU0','opp':'H','start_ms':'10'}
        left = {'scenes':{'AB':[a,b]}}
        right = {'scenes':{'AB':[dict(b,start_ms='10.000'),dict(a,start_ms='2.5')]}}
        self.assertEqual(arrangement_identity(left),arrangement_identity(right))
        right['scenes']['AB'][1]['opp'] = 'M'
        self.assertNotEqual(arrangement_identity(left),arrangement_identity(right))

    def test_missing_or_invalid_candidate_is_unknown(self):
        self.assertIsNone(arrangement_identity(None))
        self.assertIsNone(arrangement_identity({'scenes':{'AB':[{'start_ms':'NaN'}]}}))

    def test_matrix_prefix_and_append_cost_checked_independently(self):
        import numpy as np
        from scipy.sparse import csr_matrix,vstack
        off = {'A':csr_matrix([[1.,1.,0.]]),'b':np.array([[1.]]),
            'c':np.zeros((3,1)),'Aeq':csr_matrix((0,3)),'beq':np.zeros((0,1)),
            'lb':np.zeros((3,1)),'ub':np.ones((3,1)),'intcon':np.array([[1.,2.,3.]])}
        on = dict(off,A=vstack([off['A'],csr_matrix([[1.,-1.,0.]])]),b=np.array([[1.],[0.]]))
        compared = compare_model_arrays(off,on,(1,2),option_count=2)
        self.assertTrue(compared['old_A_prefix_equal'])
        self.assertTrue(compared['append_count_matches_static_audit'])
        self.assertTrue(compared['appended_columns_only_existing_y'])
        on['A'] = csr_matrix([[1.,1.,0.],[1.,0.,-1.]])
        self.assertFalse(compare_model_arrays(off,on,(1,2),option_count=2)['appended_columns_only_existing_y'])
        on['b'] = np.array([[2.],[0.]])
        self.assertFalse(compare_model_arrays(off,on,(1,2),option_count=2)['old_b_prefix_equal'])

    def test_both_cut10_and_MaxTime_difference_is_explicit(self):
        compared = compare_native_options({'CutMaxIterations':10,'MaxTime':59.5},
                                          {'CutMaxIterations':10,'MaxTime':59.7})
        self.assertTrue(compared['both_CutMaxIterations_10'])
        self.assertFalse(compared['raw_options_equal'])
        self.assertTrue(compared['settings_equal_except_MaxTime'])
        self.assertEqual(compared['differences']['MaxTime'],{'off':59.5,'on':59.7})

    def test_native_feasible_point_count_is_not_new_legal_evidence(self):
        changes = [{'scene_id':'AB','source':'event4','different_from_initial_decoded_candidate':True}]
        native_only = {'AB':[{'source':'event4','numfeaspoints':1,'completed_at_s':50}]}
        self.assertIsNone(first_new_legal_time(changes,native_only,300))

    def test_new_legal_requires_changed_arrangement_and_timely_matching_source(self):
        changes = [{'scene_id':'AB','source':'event4','different_from_initial_decoded_candidate':True}]
        record = {'source':'event4','state':'LEGAL','within_budget':True,'completed_at_s':50}
        self.assertEqual(first_new_legal_time(changes,{'AB':[record]},300),50)
        self.assertIsNone(first_new_legal_time(changes,{'AB':[dict(record,source='other')]},300))
        self.assertIsNone(first_new_legal_time(changes,{'AB':[dict(record,completed_at_s=300)]},300))
        changes[0]['different_from_initial_decoded_candidate'] = False
        self.assertIsNone(first_new_legal_time(changes,{'AB':[record]},300))


if __name__ == '__main__':
    unittest.main()
