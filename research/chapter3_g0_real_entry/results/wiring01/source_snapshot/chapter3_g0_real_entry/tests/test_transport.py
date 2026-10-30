"""Simulated session and augmented-lifecycle tests. No native process/model.

Numerical helpers here are deliberately simple stubs to exercise ownership
and classification, not evidence about the original matrix or thermal model.
"""
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch

import numpy as np

from research.chapter3_g0.budget import G0Budget,ScopeExhausted
from research.chapter3_g0.tests.fixtures import FakeClock
from research.chapter3_g0_real_entry.gating import WiringPermit
from research.chapter3_g0_real_entry.session import ScopedMatlabSession
from research.chapter3_g0_real_entry.numeric_transport import ScopeAwareContext,ScopedAugmentedSession


class FakeProcess:
    pid=777
    returncode=None
    def poll(self):return self.returncode


class FakeLog:
    def close(self):pass


class FakeNativeMethods:
    @staticmethod
    def solve(owner,model,**options):
        owner.counter+=1
        state=owner.dependencies['state'];state['requests'].append(options)
        if state.get('unsettled'):
            owner.request_blocked=True
            return {'status':'BUDGET_EXHAUSTED','budget_valid':False,'x':[]}
        return {'status':'SOLVED','budget_valid':True,'x':[1.0],'accepted_for_evaluation':True}
    @staticmethod
    def close(owner):
        owner.closed=True
        if owner.proc is not None:owner.proc.returncode=0
        owner.cleanup={'verified':True,'kind':'SIMULATED_CLEANUP'}
        return owner.cleanup


def session_dependencies(folder,clock,*,ready_timeout=False):
    state={'requests':[],'launches':[],'read_deadlines':[]}
    kernel=SimpleNamespace(HERE=Path(folder),MatlabSession=FakeNativeMethods,
                           _cut_iteration_limit=lambda value:value)
    def launch(args,**kwargs):
        state['launches'].append({'args':args,'kwargs':kwargs});return FakeProcess()
    def read(path,deadline,callback_clock,process):
        state['read_deadlines'].append(deadline)
        if ready_timeout:
            clock.advance(deadline-clock())
        return {'status':'READY','release':'2023b'},{'kind':'SIMULATED_READY'}
    def write(path,value):
        Path(path).write_text(json.dumps(value,default=str),encoding='utf-8')
    return dict(kernel=kernel,launch=launch,read_json=read,write_json=write,
                capture_tree=lambda proc,phase:{'pid':proc.pid,'phase':phase},
                open_log=lambda path:FakeLog(),preference_directory=Path(folder)/'prefs',
                matlab_path=Path(folder)/'fake_matlab.exe',environment={},creationflags=0,state=state)


class FakeRecorderBase:
    def __init__(self,model,accuracy,budget,folder,**kwargs):
        self.model,self.budget,self.folder=model,budget,Path(folder)
        self.folder.mkdir(parents=True,exist_ok=True)
        self.current_prefix=None;self.next_event={};self.event_count=0
        self.progress=[];self.solver_entered_s=None;self.assessments=[];self.pending=None
    def assess(self,vector,source):
        self.assessments.append((vector,source));return {'manual':vector},{'state':'SIMULATED'}
    def log(self,row):pass
    def summary(self):return {'assessments':len(self.assessments)}
    def release(self):self.model=None
    def begin_request(self):self.pending=None


class FakeNumericNative:
    def __init__(self,folder,clock,behavior=None):
        self.workdir=Path(folder);self.counter=0;self.event_consumer=None
        self.closed=self.request_blocked=False;self.request_settled=True
        self.clock=clock;self.behavior=behavior;self.calls=[]
    def solve(self,payload,**kwargs):
        self.counter+=1;self.calls.append((payload,kwargs))
        result={'status':'SOLVED','budget_valid':True,'x':[1.,0.],
                'fval':1.,'callbacks':[],'intlinprog_entered':False,'accepted_for_evaluation':True}
        if self.behavior is not None:return self.behavior(result)
        return result
    def is_idle(self):
        return not self.closed and not self.request_blocked and self.request_settled and self.event_consumer is None
    def close(self):self.closed=True


def numeric_dependencies(clock,state):
    def transform(payload,labels):
        if state.get('cut_during_prepare'):
            clock.advance(100)
        return {'dim':2},{'original_n':1}
    def validate(vector,original,augmented,mapping):
        state['validation_calls']=state.get('validation_calls',0)+1
        if state.get('cut_during_validation'):
            clock.advance(100)
        if state.get('raise_numerical'):
            raise ValueError('MANUAL_BAD_MATRIX')
        projected=np.asarray(vector,dtype=float).reshape(-1)[:1]
        return projected,{'accepted':state.get('accepted',True),'original':{'objective':float(projected[0])}}
    return dict(transform=transform,validate=validate,
        append=lambda vector,mapping:np.asarray([*vector,1-float(vector[0])]),
        matrix_identity=lambda payload:{'manual_dim':payload['dim']},
        recorder_base=FakeRecorderBase,vector_present=lambda value:value is not None and np.asarray(value).size>0,
        np=np,conflict_state='MANUAL_NUMERICAL_CONFLICT')


class TransportTests(unittest.TestCase):
    def test_root_lifetime_and_two_different_slot_caps(self):
        with TemporaryDirectory() as folder:
            clock=FakeClock(1000);budget=G0Budget(300,clock=clock)
            deps=session_dependencies(folder,clock)
            identity=budget.root_identity
            with budget.scope('phase1',150):
                with budget.scope('slot1',50,kind='slot'):
                    session=ScopedMatlabSession(Path(folder)/'session',budget=budget,
                        permit=WiringPermit(),dependencies=deps,total_budget_s=budget.remaining)
                    self.assertEqual(session.deadline,1300)
                    self.assertEqual(session.startup_deadline,1050)
                    clock.advance(20);session.solve({},budget=budget)
                    self.assertEqual(deps['state']['requests'][-1]['remaining_s'],30)
            clock.advance(160)
            with budget.scope('phase2',300):
                with budget.scope('slot2',240,kind='slot'):
                    session.solve({},budget=budget)
                    self.assertEqual(deps['state']['requests'][-1]['remaining_s'],60)
                    self.assertEqual(deps['state']['requests'][-1]['solver_max_time_s'],60)
                    self.assertEqual(session.deadline,1300)
            self.assertEqual(identity,budget.root_identity)
            self.assertEqual(len(deps['state']['launches']),1)
            self.assertTrue(session.is_idle());session.close()

    def test_startup_cutoff_cleans_and_does_not_restart(self):
        with TemporaryDirectory() as folder:
            clock=FakeClock();budget=G0Budget(300,clock=clock)
            deps=session_dependencies(folder,clock,ready_timeout=True)
            with budget.scope('slot',5,kind='slot'):
                with self.assertRaises(ScopeExhausted) as caught:
                    ScopedMatlabSession(Path(folder)/'session',budget=budget,
                        permit=WiringPermit(),dependencies=deps)
                self.assertTrue(caught.exception.matlab_cleanup['verified'])
                self.assertEqual(caught.exception.matlab_startup_metadata['startup_outcome'],'FAILED_OR_DEADLINE')
            self.assertEqual(len(deps['state']['launches']),1)

    def test_unsettled_native_request_cannot_be_reused(self):
        with TemporaryDirectory() as folder:
            clock=FakeClock();budget=G0Budget(300,clock=clock)
            deps=session_dependencies(folder,clock);deps['state']['unsettled']=True
            session=ScopedMatlabSession(Path(folder)/'session',budget=budget,
                        permit=WiringPermit(),dependencies=deps)
            returned=session.solve({},budget=budget)
            self.assertFalse(returned['request_settled']);self.assertFalse(session.is_idle())
            with self.assertRaises(RuntimeError):session.solve({},budget=budget)
            self.assertEqual(len(deps['state']['requests']),1);session.close()

    def test_other_root_and_missing_permit_rejected(self):
        with TemporaryDirectory() as folder:
            clock=FakeClock();budget=G0Budget(300,clock=clock)
            deps=session_dependencies(folder,clock)
            with self.assertRaises(PermissionError):
                ScopedMatlabSession(Path(folder)/'bad',budget=budget,permit=None,dependencies=deps)
            with self.assertRaises(PermissionError):
                ScopedMatlabSession(Path(folder)/'bad2',budget=budget,permit=WiringPermit())
            session=ScopedMatlabSession(Path(folder)/'session',budget=budget,permit=WiringPermit(),dependencies=deps)
            with self.assertRaises(ValueError):session.solve({},budget=G0Budget(300,clock=clock))
            self.assertFalse(deps['state']['requests']);session.close()

    def _numeric(self,folder,state=None,behavior=None):
        clock=FakeClock();budget=G0Budget(10,clock=clock);state={} if state is None else state
        context=ScopeAwareContext(budget,permit=WiringPermit(),dependencies=numeric_dependencies(clock,state))
        model=SimpleNamespace(names=['y:manual'],rows=[{'tag':'manual'}])
        recorder=context.recorder_factory(model,{},budget,Path(folder)/'recorder')
        native=FakeNumericNative(folder,clock,behavior)
        session=ScopedAugmentedSession(native,context)
        return clock,budget,state,context,recorder,native,session

    def test_original_prefix_is_the_only_accepted_vector(self):
        with TemporaryDirectory() as folder:
            clock,budget,state,context,recorder,native,session=self._numeric(folder)
            result=session.solve({'dim':1},budget=budget,x0=[1.])
            self.assertEqual(result['x'],[1.,0.]);self.assertFalse(context.failed)
            recorder.assess(result['x'],'final-original-decode')
            self.assertEqual(recorder.assessments[-1][0],[1.])
            self.assertEqual(native.calls[0][1]['x0'].tolist(),[1.,0.])
            self.assertEqual(state['validation_calls'],3)

    def test_cutoff_before_initial_admission_is_not_numerical_failure(self):
        with TemporaryDirectory() as folder:
            clock,budget,state,context,recorder,native,session=self._numeric(folder,{'cut_during_prepare':True})
            result=session.solve({'dim':1},budget=budget,x0=[1.])
            self.assertFalse(context.failed);self.assertTrue(context.cutoffs)
            self.assertFalse(native.calls);self.assertFalse(result['accepted_for_evaluation'])

    def test_cutoff_during_validation_does_not_accept_new_vector(self):
        with TemporaryDirectory() as folder:
            clock,budget,state,context,recorder,native,session=self._numeric(folder,{'cut_during_validation':True})
            result=session.solve({'dim':1},budget=budget,x0=[1.])
            self.assertFalse(context.failed);self.assertTrue(context.cutoffs)
            self.assertFalse(native.calls);self.assertFalse(result['accepted_for_evaluation'])

    def test_real_numerical_rejection_is_not_masked_by_cutoff(self):
        with TemporaryDirectory() as folder:
            clock,budget,state,context,recorder,native,session=self._numeric(folder,
                {'cut_during_validation':True,'accepted':False})
            result=session.solve({'dim':1},budget=budget,x0=[1.])
            self.assertTrue(context.failed);self.assertTrue(context.cutoffs)
            self.assertIn('ORIGINAL_OR_AUGMENTED_NUMERICAL_CHECK_FAILED',context.failure_reasons)
            self.assertEqual(result['numerical_consistency']['state'],'MANUAL_NUMERICAL_CONFLICT')

    def test_native_result_at_cutoff_retained_only_as_diagnostic(self):
        with TemporaryDirectory() as folder:
            clock,budget,state,context,recorder,native,session=self._numeric(folder)
            native.behavior=lambda result:(clock.advance(10) or result)
            result=session.solve({'dim':1},budget=budget)
            self.assertFalse(context.failed);self.assertEqual(state.get('validation_calls',0),0)
            self.assertEqual(result['x'],[]);self.assertEqual(result['native_candidate_diagnostic'],[1.,0.])

    def test_native_conflict_and_cutoff_still_latch_conflict(self):
        with TemporaryDirectory() as folder:
            clock,budget,state,context,recorder,native,session=self._numeric(folder)
            def behavior(result):
                clock.advance(10)
                result['numerical_consistency']={'state':'MANUAL_NUMERICAL_CONFLICT'}
                return result
            native.behavior=behavior
            result=session.solve({'dim':1},budget=budget)
            self.assertTrue(context.failed);self.assertFalse(result['accepted_for_evaluation'])

    def test_archive_cutoff_is_not_a_numeric_failure(self):
        import research.chapter3_g0_real_entry.numeric_transport as module
        with TemporaryDirectory() as folder:
            clock,budget,state,context,recorder,native,session=self._numeric(folder)
            original=module._save
            def delayed(path,value):
                original(path,value)
                if Path(path).name=='admission.json' and budget.elapsed<10:clock.advance(10)
            with patch.object(module,'_save',delayed):result=session.solve({'dim':1},budget=budget)
            self.assertFalse(context.failed);self.assertTrue(context.cutoffs)
            self.assertFalse(result['accepted_for_evaluation']);self.assertEqual(result['x'],[])

    def test_callback_poll_cutoff_does_not_invoke_original_recorder(self):
        with TemporaryDirectory() as folder:
            clock,budget,state,context,recorder,native,session=self._numeric(folder)
            context.prepare({'dim':1});clock.advance(10)
            recorder.poll(Path(folder)/'request_000001')
            self.assertFalse(context.failed);self.assertTrue(context.cutoffs)
            self.assertEqual(recorder.assessments,[])

    def test_true_validation_exception_stops_and_never_retries(self):
        with TemporaryDirectory() as folder:
            clock,budget,state,context,recorder,native,session=self._numeric(folder,{'raise_numerical':True})
            result=session.solve({'dim':1},budget=budget,x0=[1.])
            self.assertTrue(context.failed);self.assertFalse(native.calls)
            again=session.solve({'dim':1},budget=budget)
            self.assertEqual(again['status'],'NUMERICAL_ADMISSION_BLOCKED');self.assertFalse(native.calls)
