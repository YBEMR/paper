"""Small pure postprocessing checks; no archive factory or physical calls."""
import unittest

from summarize_shared_search import (attribution_axes,initial_pool_comparison,
                                     native_failures,plot_end_time,select_plot_records)


class SharedSearchSummaryTests(unittest.TestCase):
    def test_strict_certificate_uses_every_initial_lower_endpoint(self):
        # The first seed has the best upper, while the second may be cheaper.
        result = initial_pool_comparison('4',[['5','10'],['0','11']])
        self.assertEqual(result['min_initial_upper_J'],'10')
        self.assertEqual(result['min_initial_lower_J'],'0')
        self.assertFalse(result['final_hi_below_all_initial_lomin'])

    def test_separated_intervals_are_strict_and_equality_is_not(self):
        self.assertTrue(initial_pool_comparison('4',[['5','10'],['6','11']])[
            'final_hi_below_all_initial_lomin'])
        self.assertFalse(initial_pool_comparison('5',[['5','10']])[
            'final_hi_below_all_initial_lomin'])
        self.assertFalse(initial_pool_comparison('4',[['5','10']],complete=False)[
            'final_hi_below_all_initial_lomin'])

    def test_absent_U_or_initial_pool_does_not_certify_improvement(self):
        self.assertFalse(initial_pool_comparison(None,[['5','10']])[
            'final_hi_below_all_initial_lomin'])
        self.assertEqual(initial_pool_comparison('4',[]),{
            'min_initial_lower_J':None,'min_initial_upper_J':None,
            'final_hi_below_all_initial_lomin':False})
        self.assertEqual(select_plot_records([],900),{'U':[],'initial_reference':[]})

    def test_rejected_and_cutoff_records_cannot_enter_the_U_curve(self):
        def update(formed,committed,valid=True):
            return {'kind':'global_U','formed_at_s':formed,'committed_at_s':committed,
                    'audit_valid':valid,'energy_hi_J':'4'}
        valid = update(10,11)
        selected = select_plot_records([update(20,21,False),update(899,900),
            update(900,900),update(30,float('nan')),valid],900)
        self.assertEqual(selected['U'],[valid])

    def test_no_U_can_still_have_an_already_formed_initial_reference(self):
        initial = {'kind':'initial_baseline','formed_at_s':899,'committed_at_s':901,
                   'audit_valid':True,'energy_hi_J':'5'}
        late = dict(initial,formed_at_s=900)
        selected = select_plot_records([initial,late],900)
        self.assertEqual(selected['U'],[])
        self.assertEqual(selected['initial_reference'],[initial])

    def test_source_and_changed_condition_are_independent_axes(self):
        rows = [{'source':source,'condition_changed':changed}
                for source in ('initial_constructor','inner_MILP') for changed in (False,True)]
        self.assertEqual(attribution_axes(rows),{
            'initial_constructor':{'same_a':1,'changed_a':1},
            'inner_MILP':{'same_a':1,'changed_a':1}})

    def test_early_stop_limits_plot_records_and_trajectory_endpoint(self):
        stop = plot_end_time(763.156,900)
        self.assertEqual(stop,763.156)
        self.assertEqual(plot_end_time(901,900),900)
        before = {'kind':'global_U','formed_at_s':20,'committed_at_s':21,'audit_valid':True}
        after = {'kind':'global_U','formed_at_s':800,'committed_at_s':801,'audit_valid':True}
        late_initial = {'kind':'initial_baseline','formed_at_s':800,'audit_valid':True}
        self.assertEqual(select_plot_records([before,after,late_initial],900,stop),
                         {'U':[before],'initial_reference':[]})

    def test_native_fault_identity_and_message_are_preserved_verbatim(self):
        message = 'Permission\ndenied.\nrequest_000010.request.json'
        record = {'scenes':{'AC':{'solver_result':{'rounds':[
            {'status':'SOLVED'}, {'status':'ERROR','error_identifier':'MATLAB:fileread:cannotOpenFile',
                                 'error_message':message}]}}}}
        self.assertEqual(native_failures(record),[{'scene':'AC','round':2,'status':'ERROR',
            'error_identifier':'MATLAB:fileread:cannotOpenFile','error_message':message}])


if __name__ == '__main__':
    unittest.main()
