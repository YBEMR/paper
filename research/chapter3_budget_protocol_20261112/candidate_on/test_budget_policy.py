"""Synthetic budgets and receipts only. No MATLAB, MILP, LP, model, or evaluator."""
from contextlib import contextmanager
from types import SimpleNamespace
import unittest
from budget_policy import BudgetPolicy,NEXT_ON,ABC_DYNAMIC,ResponseBudget,ResponseDeadline,candidate_admission,remaining_arms,box_objective_bound
from startup_observer import observe_startup
from control import execute,progress
from test_control import FakeRuntime,event,safe


class BudgetTests(unittest.TestCase):
    def test_actual_slow_start_fits_new_fixed_budget(self):
        self.assertFalse(300.-71.047>=250.)
        a=NEXT_ON.allocate(71.047)
        self.assertTrue(a['can_submit']);self.assertEqual(a['native_seconds'],240.)
        self.assertAlmostEqual(420.-71.047-240.-60.,48.953)
    def test_even_slower_start_still_can_stop_without_tuning(self):
        self.assertTrue(NEXT_ON.allocate(120.)['can_submit'])
        self.assertFalse(NEXT_ON.allocate(120.001)['can_submit'])
        self.assertFalse(NEXT_ON.allocate(420.)['can_submit'])
    def test_no_matlab_start_when_budget_already_insufficient(self):
        r=FakeRuntime()
        def initial():r.elapsed=121.;return safe(121.)
        r.evaluate_initial=initial
        s=execute(r);self.assertEqual(s['native_request_attempts'],0);self.assertNotIn('startup',r.calls)
    def test_dynamic_300_and_600_are_distinct_protocols(self):
        b300=BudgetPolicy(300.,'dynamic',240.)
        self.assertEqual(b300.allocate(71.047)['native_seconds'],168)
        self.assertEqual(ABC_DYNAMIC.allocate(71.047)['native_seconds'],468)
    def test_dynamic_native_time_charges_preparation(self):
        self.assertEqual([ABC_DYNAMIC.allocate(t)['native_seconds'] for t in [150,250,350]],[390,290,190])
        self.assertEqual(ABC_DYNAMIC.allocate(510)['native_seconds'],30)
        self.assertIsNone(ABC_DYNAMIC.allocate(510.01)['native_seconds'])
    def test_late_serialization_must_recheck_before_publish(self):
        self.assertTrue(NEXT_ON.allocate(100.)['can_submit'])
        self.assertFalse(NEXT_ON.allocate(121.)['can_submit'])
        self.assertEqual(ABC_DYNAMIC.allocate(100)['native_seconds'],440)
        self.assertEqual(ABC_DYNAMIC.allocate(112)['native_seconds'],428)
    def test_same_function_has_no_arm_specific_parameter(self):
        quotas={arm:ABC_DYNAMIC.allocate(200)['native_seconds'] for arm in ['A','B','C']}
        self.assertEqual(set(quotas.values()),{340})
    def test_changed_actual_cap_not_accepted_as_same_settings(self):
        self.assertTrue(NEXT_ON.actual_cap_matches(240.,240.))
        for value in [239.9,None,True,float('nan')]:self.assertFalse(NEXT_ON.actual_cap_matches(240.,value))
    def test_invalid_budgets_and_elapsed_rejected(self):
        for value in [-1,True,float('nan'),float('inf')]:
            with self.subTest(value=value),self.assertRaises(ValueError):NEXT_ON.allocate(value)
        with self.assertRaises(ValueError):BudgetPolicy(300,'fixed',300)
    def test_solver_deadline_does_not_move_parent_deadline(self):
        now=[100.]
        @contextmanager
        def phase(name):yield
        p=SimpleNamespace(start=100.,deadline=520.,phase=phase,check=lambda:None)
        b=ResponseBudget(p,NEXT_ON,lambda:now[0]);self.assertEqual(b.deadline,470.)
        now[0]=469.;self.assertEqual(b.remaining,1.)
        now[0]=470.
        with self.assertRaises(ResponseDeadline):b.check()
        self.assertEqual(p.deadline,520.)
    def test_callback_after_response_cutoff_not_credited(self):
        p=progress([event('heuristics',.5,time=375.)],'1',cutoff=370.)
        self.assertFalse(p['root_lp_completion_via_later_phase']);self.assertEqual(p['finite_bounds'],[])
    def test_reserved_window_can_validate_timely_response(self):
        r=FakeRuntime();r.native.update(x=[1.,0.],exitflag=2,accepted_for_evaluation=True)
        r.solve_finish=360.;r.validate_finish=380.;r.final['completed_at_elapsed_s']=419.
        r.solver_evidence_cutoff_s=370.
        self.assertTrue(execute(r)['new_complete_SAFE'])
    def test_same_initial_with_disjoint_energy_is_conflict_not_improvement(self):
        r=FakeRuntime();r.native.update(x=[1.,0.],exitflag=2,accepted_for_evaluation=True)
        r.validation['same_initial']=True
        s=execute(r);self.assertFalse(s['strict_energy_improvement']);self.assertTrue(s['energy_identity_conflict'])
        self.assertEqual(s['evidence_integrity'],'NOT_ESTABLISHED')
    def test_finite_trivial_bound_is_not_scientific_progress(self):
        r=FakeRuntime();r.events=[event(bound=0.)]
        s=execute(r);self.assertIsNotNone(s['progress']['best_consistent_native_bound'])
        self.assertFalse(s['progress_observed'])
    def test_exact_box_bound_without_optimization(self):
        self.assertEqual(box_objective_bound([1.,-2.,0.],[3.,0.,float('-inf')],[5.,7.,float('inf')]),'-11')
        self.assertIsNone(box_objective_bound([1.],[float('-inf')],[1.]))
    def test_no_call_has_separate_lifecycle_integrity(self):
        r=FakeRuntime();r.start_finish=121.;s=execute(r)
        self.assertEqual(s['native_observation_state'],'NOT_REQUESTED')
        self.assertEqual(s['lifecycle_integrity'],'VERIFIED');self.assertFalse(s['progress_usable'])


class ArmAndReceiptTests(unittest.TestCase):
    def test_ordinary_A_timeout_keeps_B_C(self):
        self.assertEqual(remaining_arms(['A','B','C'],['A'],{'kind':'TIMEOUT'}),['B','C'])
    def test_empty_B_and_rejected_candidate_keep_C(self):
        for kind in ['NO_VECTOR','CANDIDATE_REJECTED','NO_IMPROVEMENT']:
            self.assertEqual(remaining_arms(['A','B','C'],['A','B'],{'kind':kind}),['C'])
    def test_verified_local_error_stops_only_affected_group(self):
        self.assertEqual(remaining_arms(['A','B','C'],['A'],{'kind':'ARM_CORRECTNESS_ERROR','affected_arms':['B']}),['C'])
        self.assertEqual(remaining_arms(['A','B','C'],['A'],{'kind':'ARM_CORRECTNESS_ERROR','affected_arms':['B','C']}),[])
    def test_shared_fault_or_cleanup_unknown_stops_all_pending(self):
        for kind in ['SHARED_IDENTITY_DRIFT','SHARED_CORRECTNESS_ERROR','CLEANUP_UNKNOWN']:
            self.assertEqual(remaining_arms(['A','B','C'],['A'],{'kind':kind}),[])
    def test_ambiguous_fault_cannot_silently_continue(self):
        with self.assertRaises(ValueError):remaining_arms(['A','B','C'],[],{'kind':'ARM_CORRECTNESS_ERROR'})
    def test_receipt_layers_no_empty_or_late_SAFE(self):
        self.assertEqual(candidate_admission(None,600),'NO_VECTOR')
        r=dict(received_elapsed_s=500.,vector_present=True,new_rows=True,original_rows=True,schedule_legal=True,
               physical_complete=True,physical_state='SAFE',physical_completed_s=599.,same_initial=False)
        self.assertEqual(candidate_admission(r,600),'NEW_SAFE')
        for changes,expected in [({'vector_present':False},'NO_VECTOR'),({'received_elapsed_s':600.},'LATE_UNCREDITED'),
            ({'original_rows':False},'REJECTED_ROWS'),({'schedule_legal':False},'REJECTED_SCHEDULE'),
            ({'physical_completed_s':600.},'SAFE_NOT_ESTABLISHED'),({'same_initial':True},'SAME_INITIAL_SAFE'),
            ({'received_elapsed_s':float('nan')},'INVALID_TIME')]:
            self.assertEqual(candidate_admission(dict(r,**changes),600),expected)


class ObserverTests(unittest.TestCase):
    def test_instrumentation_preserves_calls_and_poll_parameters(self):
        now=[0.];calls=[];records=[];handle=object()
        def popen(*args,**kwargs):calls.append(('popen',args,kwargs));now[0]+=2.;return handle
        def read(*args,**kwargs):calls.append(('read',args,kwargs));now[0]+=8.;return {'status':'READY'},{}
        module=SimpleNamespace(Popen=popen,CREATE_NO_WINDOW=123)
        b=SimpleNamespace(subprocess=module,_read_json_until=read)
        with observe_startup(b,lambda:now[0],records):
            self.assertIs(b.subprocess.Popen(['matlab','-batch','x'],creationflags=123),handle)
            b._read_json_until('ready.json',999.,sleep='original',process=handle)
        self.assertIs(b.subprocess,module);self.assertIs(b._read_json_until,read)
        self.assertEqual(calls[1][2]['sleep'],'original');self.assertEqual([r['elapsed_s'] for r in records],[2.,8.])
    def test_instrumentation_restores_on_exception(self):
        def fail(*a,**k):raise RuntimeError('launch')
        module=SimpleNamespace(Popen=fail);reader=lambda *a:None;b=SimpleNamespace(subprocess=module,_read_json_until=reader)
        records=[]
        with self.assertRaises(RuntimeError):
            with observe_startup(b,lambda:1.,records):b.subprocess.Popen('unused')
        self.assertIs(b.subprocess,module);self.assertIs(b._read_json_until,reader)
        self.assertEqual(records[0]['exception'],'RuntimeError')


if __name__=='__main__':unittest.main(verbosity=2)
