"""Control tests: fake clocks/receipts only; prohibit real process launches."""
from copy import deepcopy
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path
import shutil
import uuid
import unittest
from unittest.mock import patch
from control import execute, progress, full_safe, StopWindow
from guard import verify_approval, claim_once, save, sha, verify_plan, inside
import run_on


@contextmanager
def local_temp():
    root=Path(__file__).resolve().parent/'.test_temp'; root.mkdir(exist_ok=True)
    t=root/('case_'+uuid.uuid4().hex);t.mkdir()
    try:
        yield str(t)
    finally:
        assert t.resolve().is_relative_to(root.resolve()) and t.name.startswith('case_')
        shutil.rmtree(t)


def safe(time=20., energy=('1', '1.01')):
    return dict(state='SAFE', rankable_energy=True, completed_at_elapsed_s=time,
                scenes={'a': dict(state='SAFE', complete=True)}, weighted_energy_J=list(energy))


def event(phase='', bound=None, time=80., vector=None):
    return dict(kind='callback', event_number=2, received_elapsed_s=time, state='iter',
                values=dict(phase=phase, lowerbound=bound, numfeaspoints=0), x=vector or [])


class FakeRuntime:
    def __init__(self):
        self.elapsed=1.; self.scene_count=1; self.events=[]; self.objective_reference='1'
        self.calls=[]; self.native=dict(status='SOLVED', exitflag=0, x=[], budget_valid=True, accepted_for_evaluation=False)
        self.identity=dict(state='VERIFIED'); self.after=dict(state='VERIFIED'); self.cleanup=True
        self.validation=dict(state='ADMITTED', candidate={'test':True}, same_initial=False)
        self.initial=safe(); self.final=safe(270., ('0.8','0.9')); self.solve_finish=260.
        self.start_finish=25.; self.validate_finish=261.; self.close_error=False
    @property
    def remaining(self): return max(0,300.-self.elapsed)
    def check(self):
        if self.elapsed>=300.: raise StopWindow()
    def prepare(self): self.calls.append('prepare')
    def evaluate_initial(self): self.calls.append('initial_eval'); self.elapsed=20.; return self.initial
    def start_native(self): self.calls.append('startup'); self.elapsed=self.start_finish
    def solve(self,cap):
        self.calls.append(('solve',cap)); self.elapsed=self.solve_finish; return self.native
    def inspect_identity(self,native): self.calls.append('identity'); return self.identity
    def validate_returned(self,vector): self.calls.append('validate'); self.elapsed=self.validate_finish; return self.validation
    def evaluate_returned(self,candidate):
        self.calls.append('final_eval'); self.elapsed=max(self.elapsed,self.final['completed_at_elapsed_s']); return self.final
    def close(self):
        self.calls.append('close')
        if self.close_error: raise RuntimeError('cleanup failed')
        return dict(complete=self.cleanup)
    def verify_after(self): self.calls.append('after'); return self.after


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.no_process=patch('subprocess.Popen', side_effect=AssertionError('Real process forbidden in control tests'))
        self.no_process.start(); self.addCleanup(self.no_process.stop)
    def vector_runtime(self):
        r=FakeRuntime(); r.native.update(x=[1.,0.],accepted_for_evaluation=True,exitflag=2); return r
    def test_timeout_one_call_no_exception_no_retry(self):
        r=FakeRuntime(); s=execute(r)
        self.assertEqual(s['terminal_state'],'ORDINARY_NATIVE_LIMIT_NO_ACCEPTED_VECTOR')
        self.assertIsNone(s['error']); self.assertEqual(r.calls.count(('solve',240.)),1)
        self.assertIn('identity',r.calls); self.assertNotIn('final_eval',r.calls)
        self.assertFalse(s['progress_usable']); self.assertEqual(s['next_action'],'STOP_NO_RETRY_NO_AUTOMATIC_ABC')
    def test_timeout_retains_bound_and_later_phase(self):
        r=FakeRuntime(); r.events=[event('heuristics',0.5)]; s=execute(r)
        self.assertTrue(s['progress_usable']); self.assertFalse(s['returned_complete_SAFE'])
        self.assertFalse(s['progress']['independent_lower_bound_certificate'])
    def test_root_entry_does_not_prove_completion(self):
        p=progress([event('rootlp')],'1')
        self.assertTrue(p['root_lp_entry_observed']); self.assertEqual(p['root_lp_actual_completion'],'UNKNOWN')
    def test_zero_bound_valid_and_nonfinite_ignored(self):
        p=progress([event(bound=b) for b in [0,True,None,[],float('inf'),float('nan')]],'1')
        self.assertEqual(len(p['finite_bounds']),1); self.assertEqual(p['best_consistent_native_bound']['value'],0)
    def test_conflicting_bound_not_usable(self):
        r=FakeRuntime(); r.events=[event(bound=2.)]; s=execute(r)
        self.assertEqual(s['progress']['finite_bounds'][0]['consistency'],'CONFLICT'); self.assertFalse(s['progress_usable'])
    def test_no_reference_does_not_certify_bound(self):
        self.assertIsNone(progress([event(bound=.5)],None)['best_consistent_native_bound'])
    def test_late_events_not_credited_and_counter_not_vector(self):
        e=event(bound=.5,time=300.); before=event(time=299.); before['values']['numfeaspoints']=1
        p=progress([e,before],'1')
        self.assertEqual(p['finite_bounds'],[]); self.assertEqual(p['callback_vectors'],[])
    def test_callback_vector_is_only_available_unvalidated(self):
        p=progress([event(vector=[1.,2.])],'1')
        self.assertEqual(p['callback_vectors'][0]['state'],'AVAILABLE_UNVALIDATED')
    def test_same_initial_not_new_SAFE_or_improvement(self):
        r=self.vector_runtime(); r.validation['same_initial']=True; r.final=safe(270.)
        s=execute(r); self.assertTrue(s['returned_complete_SAFE']); self.assertFalse(s['new_complete_SAFE'])
        self.assertFalse(s['strict_energy_improvement']); self.assertFalse(s['progress_usable'])
    def test_new_SAFE_and_strict_interval_improvement(self):
        r=self.vector_runtime(); s=execute(r)
        self.assertTrue(s['new_complete_SAFE']); self.assertTrue(s['strict_energy_improvement']); self.assertTrue(s['progress_usable'])
        self.assertEqual(s['physical_evaluation_attempts'],2)
    def test_exitflag_zero_with_vector_is_independently_checked(self):
        r=self.vector_runtime(); r.native['exitflag']=0
        self.assertTrue(execute(r)['new_complete_SAFE']); self.assertIn('validate',r.calls)
    def test_native_error_with_vector_not_evaluated(self):
        r=self.vector_runtime(); r.native['status']='CALLBACK_ERROR'
        execute(r); self.assertNotIn('validate',r.calls)
    def test_rejected_rows_no_physical_evaluation(self):
        r=self.vector_runtime(); r.validation=dict(state='REJECTED',reason='original row')
        s=execute(r); self.assertEqual(s['terminal_state'],'RETURNED_VECTOR_REJECTED'); self.assertNotIn('final_eval',r.calls)
    def test_thermal_unsafe_not_SAFE(self):
        r=self.vector_runtime(); r.final['state']='UNSAFE'
        self.assertFalse(execute(r)['returned_complete_SAFE'])
    def test_late_response_keeps_prior_bound_without_evaluation(self):
        r=self.vector_runtime(); r.native.update(status='BUDGET_EXHAUSTED',budget_valid=False,accepted_for_evaluation=False)
        r.solve_finish=301.; r.events=[event(bound=.5)]
        s=execute(r); self.assertNotIn('validate',r.calls); self.assertTrue(s['progress_usable'])
    def test_validation_overruns_no_physical_evaluation(self):
        r=self.vector_runtime(); r.validate_finish=301.
        s=execute(r); self.assertNotIn('final_eval',r.calls); self.assertFalse(s['returned_complete_SAFE'])
    def test_physical_receipt_at_deadline_not_SAFE(self):
        r=self.vector_runtime(); r.final=safe(300.)
        self.assertFalse(execute(r)['returned_complete_SAFE'])
    def test_initial_not_SAFE_prevents_native_start(self):
        r=FakeRuntime(); r.initial['state']='UNKNOWN'; s=execute(r)
        self.assertEqual(s['native_request_attempts'],0); self.assertNotIn('startup',r.calls)
    def test_insufficient_cap_reserve_no_shorten_or_call(self):
        r=FakeRuntime(); r.start_finish=51.; s=execute(r)
        self.assertEqual(s['native_request_attempts'],0); self.assertEqual(s['terminal_state'],'INSUFFICIENT_FIXED_CAP_RESERVE_NO_CALL')
    def test_transport_or_option_drift_invalidates_progress(self):
        r=self.vector_runtime(); r.events=[event('heuristics',.5)]; r.identity={'state':'INVALID'}
        s=execute(r); self.assertFalse(s['progress_usable']); self.assertNotIn('validate',r.calls)
    def test_source_drift_after_invalidates_progress(self):
        r=FakeRuntime(); r.events=[event('heuristics',.5)]; r.after={'state':'INVALID'}
        self.assertFalse(execute(r)['progress_usable'])
    def test_late_identity_cannot_erase_prior_mismatch(self):
        r=FakeRuntime();r.events=[event(bound=.5)];r.identity={'state':'INVALID'}
        r.after={'state':'VERIFIED','native_identity_after':{'state':'VERIFIED'}}
        self.assertFalse(execute(r)['progress_usable'])
    def test_readonly_late_identity_can_validate_earlier_progress(self):
        r=FakeRuntime(); r.events=[event(bound=.5)]; r.identity={'state':'UNKNOWN'}
        r.after={'state':'VERIFIED','native_identity_after':{'state':'VERIFIED','post_cutoff':True}}
        s=execute(r); self.assertTrue(s['progress_usable']); self.assertNotIn('final_eval',r.calls)
    def test_cleanup_failure_preserves_but_invalidates_progress(self):
        r=FakeRuntime(); r.events=[event('heuristics',.5)]; r.close_error=True
        s=execute(r); self.assertTrue(s['progress_observed']); self.assertFalse(s['progress_usable'])
    def test_preparation_exception_no_native_call_and_cleanup(self):
        r=FakeRuntime()
        def fail(): raise ValueError('input changed')
        r.prepare=fail; s=execute(r)
        self.assertEqual(s['native_request_attempts'],0); self.assertIn('close',r.calls)
    def test_unapproved_controller_never_launches(self):
        with patch.object(run_on,'verify_plan',return_value={}), patch.object(run_on,'read',return_value={'approved':False}), patch.object(run_on,'sha',return_value='hash'):
            with self.assertRaises(PermissionError): run_on.run('.', 'plan', 'approval')
    def test_approval_requires_exact_scope_and_user_reference(self):
        valid=dict(approved=True,plan_sha256='x',arm='ON',maximum_native_calls=1,total_window_s=300.,native_MaxTime_s=240.,retries=0,user_decision_reference='test fixture only')
        verify_approval(valid,'x')
        for key,value in [('arm','OFF'),('maximum_native_calls',2),('total_window_s',301),('native_MaxTime_s',241),('retries',1),('user_decision_reference','')]:
            with self.subTest(key=key), self.assertRaises(PermissionError): verify_approval(dict(valid,**{key:value}),'x')
        with self.assertRaises(PermissionError): verify_approval(valid,'wrong-plan')
    def test_once_claim_consumed_even_without_solver(self):
        with local_temp() as t:
            plan={'execution_directory':'slot'}
            claim_once(t,plan,{'once_only':True})
            with self.assertRaises(FileExistsError): claim_once(t,plan,{'once_only':True})
    def test_path_escape_rejected(self):
        with local_temp() as t, self.assertRaises(ValueError): inside(t,'../escape')
    def test_partial_SAFE_cannot_pass(self):
        self.assertFalse(full_safe(safe(),2))
        s=safe(); s['scenes']['a']['complete']=False; self.assertFalse(full_safe(s,1))


if __name__=='__main__': unittest.main(verbosity=2)
