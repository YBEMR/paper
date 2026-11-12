"""Pure clocks/receipts plus file-bridge integration. No native process or evaluator."""
import json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import nullcontext,contextmanager
from uuid import uuid4
from control import execute,next_arms,PreparationStop
from evidence import StopWindow,progress
from guard import verify_approval,claim_once,save
from budget_policy import ABC_DYNAMIC,ResponseBudget
from dispatch import allocate_at_publication
TEST_TEMP=Path(__file__).resolve().parent/'test_temp'
TEST_TEMP.mkdir(exist_ok=True)

@contextmanager
def test_directory():
    # Keep small control receipts for audit; Windows temp mode=0700 is unavailable on this host.
    folder=TEST_TEMP/str(uuid4());folder.mkdir()
    yield str(folder)

class Clock:
    def __init__(self,t=0):self.t=t
    def __call__(self):return self.t

def safe(t=110,energy=('1','1.0001')):
    return dict(state='SAFE',rankable_energy=True,weighted_energy_J=list(energy),completed_at_elapsed_s=t,
                scenes={s:dict(state='SAFE',complete=True) for s in ['s1','s2']})

class FakeRuntime:
    arm='A';scene_count=2;objective_reference='1';objective_lower_bound='0'
    def __init__(self,kind='success'):
        self.kind=kind;self.elapsed=0;self.events=[];self.calls=0;self.physical=0;self.started=0
    def check(self):
        if self.elapsed>=600:raise StopWindow()
    def prepare(self):
        self.elapsed=511 if self.kind=='budget_short' else 100
        if self.kind=='source_drift':raise ValueError('Source drift')
        if self.kind=='prepare_timeout':self.elapsed=600;raise StopWindow()
        if self.kind=='initial_reject':raise PreparationStop('INITIAL_CONTINUOUS_POINT_REJECTED_NO_CALL')
    def evaluate_initial(self):return safe()
    def start_native(self):
        self.started+=1;self.elapsed+=420 if self.kind=='slow_start' else 60
    def solve(self,cap):
        self.calls+=1;self.elapsed=560 if self.kind=='late' else 490
        self.events=[dict(event_number=1,received_elapsed_s=480,values=dict(phase='rootlp')),
                     dict(event_number=2,received_elapsed_s=485,values=dict(phase='heuristics',lowerbound=2 if self.kind=='bound_conflict' else .5))]
        if self.kind=='root_entry_only':self.events=self.events[:1]
        if self.kind=='late':self.events=[dict(event_number=1,received_elapsed_s=551,values=dict(phase='heuristics',lowerbound=.5))]
        no=self.kind in ('timeout','no_candidate','late')
        return dict(status='BUDGET_EXHAUSTED' if self.kind in ('timeout','late') else 'SOLVED',
                    budget_valid=not no,accepted_for_evaluation=not no,x=[] if no else [1],exitflag=0)
    def inspect_identity(self,n):return dict(state='INVALID' if self.kind=='options_drift' else 'VERIFIED')
    def validate_returned(self,x):
        return dict(state='REJECTED' if self.kind=='validation_fail' else 'ADMITTED',candidate={'scenes':{}},same_initial=self.kind not in ('improved','new_safe'))
    def evaluate_returned(self,c):
        self.physical+=1;self.elapsed=601 if self.kind=='validation_late' else 520
        if self.kind=='unsafe':return dict(state='UNSAFE')
        e=('0.8','0.9') if self.kind in ('improved','identity_energy_conflict') else ('1','1.0001')
        return safe(self.elapsed,e)
    def close(self):self.elapsed+=7;return dict(complete=self.kind!='cleanup_fail')
    def verify_after(self):return dict(state='INVALID' if self.kind=='after_drift' else 'VERIFIED',native_identity_after=self.inspect_identity({}) if self.calls else None)

class Controls(unittest.TestCase):
    def run_case(self,kind):
        rt=FakeRuntime(kind);r=execute(rt);self.assertLessEqual(rt.calls,1);self.assertLessEqual(rt.physical,1);return rt,r
    def test_budget_shortage(self):
        rt,r=self.run_case('budget_short');self.assertEqual(rt.calls,0);self.assertEqual(rt.started,0)
    def test_slow_start(self):
        rt,r=self.run_case('slow_start');self.assertEqual(rt.calls,0);self.assertEqual(rt.started,1)
    def test_normal_timeout_continues(self):
        rt,r=self.run_case('timeout');self.assertEqual(next_arms(['A','B','C'],['A'],r),['B','C'])
    def test_no_candidate_continues(self):
        rt,r=self.run_case('no_candidate');self.assertFalse(r['returned_complete_SAFE']);self.assertEqual(next_arms(['A','B','C'],['A'],r),['B','C'])
    def test_candidate_rejected(self):
        rt,r=self.run_case('validation_fail');self.assertEqual(rt.physical,0);self.assertEqual(next_arms(['A','B','C'],['A'],r),['B','C'])
    def test_safe_unknown(self):
        rt,r=self.run_case('unsafe');self.assertFalse(r['returned_complete_SAFE'])
    def test_bound_conflict(self):
        rt,r=self.run_case('bound_conflict');self.assertTrue(r['native_bound_conflict']);self.assertFalse(r['progress_usable']);self.assertEqual(next_arms(['A','B','C'],['A'],r),['B','C'])
    def test_late_native_evidence(self):
        rt,r=self.run_case('late');self.assertFalse(r['progress_usable']);self.assertEqual(r['progress']['finite_bounds'],[])
    def test_late_validation(self):
        rt,r=self.run_case('validation_late');self.assertFalse(r['returned_complete_SAFE']);self.assertEqual(r['terminal_state'],'METHOD_WINDOW_EXHAUSTED')
    def test_source_drift_stops(self):
        rt,r=self.run_case('source_drift');self.assertEqual(next_arms(['A','B','C'],['A'],r),[])
    def test_options_drift_stops(self):
        rt,r=self.run_case('options_drift');self.assertEqual(next_arms(['A','B','C'],['A'],r),[])
    def test_cleanup_failure_stops(self):
        rt,r=self.run_case('cleanup_fail');self.assertEqual(next_arms(['A','B','C'],['A'],r),[])
    def test_after_source_drift_stops(self):
        rt,r=self.run_case('after_drift');self.assertEqual(next_arms(['A','B','C'],['A'],r),[])
    def test_native_identity_discovered_after_cleanup_stops(self):
        rt=FakeRuntime('no_candidate')
        rt.verify_after=lambda:dict(state='VERIFIED',native_identity_after={'state':'INVALID'})
        r=execute(rt);self.assertEqual(next_arms(['A','B','C'],['A'],r),[])
    def test_bound_conflict_never_downgrades_shared_fault(self):
        rt=FakeRuntime('identity_energy_conflict')
        original=rt.solve
        def solve(cap):
            n=original(cap);rt.events[-1]['values']['lowerbound']=2;return n
        rt.solve=solve;r=execute(rt)
        self.assertTrue(r['energy_identity_conflict']);self.assertTrue(r['native_bound_conflict'])
        self.assertEqual(next_arms(['A','B','C'],['A'],r),[])
    def test_same_safe_not_improvement(self):
        rt,r=self.run_case('success');self.assertTrue(r['returned_complete_SAFE']);self.assertFalse(r['new_complete_SAFE']);self.assertFalse(r['strict_energy_improvement']);self.assertFalse(r['independent_optimality_proof'])
    def test_new_safe_not_improvement(self):
        rt,r=self.run_case('new_safe');self.assertTrue(r['new_complete_SAFE']);self.assertFalse(r['strict_energy_improvement'])
    def test_strict_improvement(self):
        rt,r=self.run_case('improved');self.assertTrue(r['strict_energy_improvement'])
    def test_same_schedule_conflicting_energy(self):
        rt,r=self.run_case('identity_energy_conflict');self.assertTrue(r['energy_identity_conflict']);self.assertEqual(next_arms(['A','B','C'],['A'],r),[])
    def test_rootlp_callback_is_completion_without_later_phase(self):
        rt,r=self.run_case('root_entry_only');self.assertTrue(r['progress']['root_lp_entry_observed']);self.assertFalse(r['progress']['root_lp_completion_via_later_phase']);self.assertTrue(r['progress']['root_lp_completion_observed'])
    def test_preparation_timeout_continues(self):
        rt,r=self.run_case('prepare_timeout');self.assertEqual(rt.calls,0);self.assertEqual(next_arms(['A','B','C'],['A'],r),['B','C'])
    def test_initial_rejection_no_solver(self):
        rt,r=self.run_case('initial_reject');self.assertEqual(rt.calls,0)
    def test_allocation_edges(self):
        self.assertEqual(ABC_DYNAMIC.allocate(0)['native_seconds'],540)
        self.assertEqual(ABC_DYNAMIC.allocate(100.2)['native_seconds'],439)
        self.assertEqual(ABC_DYNAMIC.allocate(510)['native_seconds'],30)
        self.assertFalse(ABC_DYNAMIC.allocate(510.001)['can_submit'])
    def test_evidence_strict_cutoff(self):
        for t,wanted in [(549.999,True),(550,False),(600,False),(float('nan'),False)]:
            p=progress([dict(received_elapsed_s=t,values=dict(phase='heuristics',lowerbound=.5))],'1',550,'0')
            self.assertEqual(p['root_lp_completion_via_later_phase'],wanted)
    def test_feature_scoped_stop(self):
        base=dict(cleanup={'complete':True},identity_after={'state':'VERIFIED'},fault_scope='FEATURE',affected_arms=['B','C'])
        self.assertEqual(next_arms(['A','B','C'],['B'],base),['A'])
        base['affected_arms']=['C'];self.assertEqual(next_arms(['A','B','C'],[],base),['A','B'])
    def test_approval_template_and_old_ON_rejected(self):
        for a in [dict(approved=False),dict(approved=True,arm='ON',total_window_s=420)]:
            with self.assertRaises(PermissionError):verify_approval(a,'hash')
    def test_atomic_claim_no_retry(self):
        with test_directory() as t:
            p={'execution_directory':'run'};claim_once(t,p,{'x':1})
            with self.assertRaises(FileExistsError):claim_once(t,p,{'x':1})

class BridgeIntegration(unittest.TestCase):
    def test_real_serialization_then_dynamic_publication_no_native(self):
        # This invokes only the Python file transport on a session created without __init__.
        from representation import load_science
        workspace=Path(__file__).resolve().parents[2]
        _,cg=load_science(workspace)
        import numpy as np,matlab_bridge as bridge
        from scipy.sparse import csc_matrix
        from timing import MethodBudget
        clock=Clock(100)
        budget=MethodBudget(600,clock=clock);budget.start=0;budget.deadline=600
        payload=dict(c=np.array([1.]),A=csc_matrix((0,1)),b=np.array([],dtype=float),
            Aeq=csc_matrix((0,1)),beq=np.array([],dtype=float),lb=np.array([0.]),ub=np.array([1.]),intcon=np.array([0],dtype=np.int64))
        with test_directory() as t:
            s=bridge.MatlabSession.__new__(bridge.MatlabSession)
            s.closed=False;s.request_blocked=False;s.clock=clock;s.started=0;s.deadline=600;s.budget=budget
            s.counter=0;s.workdir=Path(t);s.metadata={};s.proc=SimpleNamespace(poll=lambda:None);s.event_consumer=None
            real_save=bridge.savemat;allocations=[]
            def serialize(*a,**k):
                real_save(*a,**k);clock.t+=17.25
            def receipt(*a,**k):
                req=json.loads((Path(t)/'request_000001.request.json').read_text())
                self.assertEqual(req['solver_max_time_s'],422)
                self.assertEqual(req['solver_max_time_s_declared'],422)
                self.assertEqual(req['remaining_s'],432.75)
                return dict(status='SOLVED',x=[],exitflag=0),{}
            with patch('subprocess.Popen',side_effect=AssertionError('No processes')),patch.object(bridge,'savemat',serialize),patch.object(bridge,'_read_json_until',receipt):
                with allocate_at_publication(bridge,clock,allocations.append):
                    r=s.solve(payload,x0=np.array([0.]),budget=ResponseBudget(budget,ABC_DYNAMIC,clock))
            self.assertEqual(s.counter,1);self.assertEqual(allocations[0]['measured_elapsed_s'],117.25)
            self.assertFalse(r['accepted_for_evaluation'])
            from saved_adapter_base import Runtime
            reader=Runtime(workspace,Path(__file__).parent,Path('unused'),{},Path(t),0);reader.cg=cg
            expected=dict(payload,x0=np.array([0.]))
            self.assertEqual(cg.array_digest(reader.payload(Path(t)/'request_000001.mat')),cg.array_digest(expected))
    def test_late_publication_never_writes_request(self):
        class Bridge:
            _json=staticmethod(lambda p,v: (_ for _ in ()).throw(AssertionError('Published late request')))
        from evidence import InsufficientNativeBudget
        with allocate_at_publication(Bridge,lambda:511,lambda a:None):
            with self.assertRaises(InsufficientNativeBudget):Bridge._json(Path('request_000001.request.json'),{'remaining_s':39})

if __name__=='__main__':unittest.main(verbosity=2)
