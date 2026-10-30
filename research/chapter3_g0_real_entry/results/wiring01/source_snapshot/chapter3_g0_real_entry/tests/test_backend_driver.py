"""Integrated G0 wiring with fake native/model seams and real domain logic.

This is not a C01 scientific call. Handmade six-Stage inputs use only C01's
230/400ms metadata. The old PARTIAL interfaces consume an explicit fake power
ledger. Native transport and augmented-control objects here are mocked; their
separate transport tests cover the actual transport adapter implementation.
"""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ...chapter3_g0.contract import derive_deployment
from ...chapter3_g0.method import make_model_view
from ...chapter3_g0.tests.fixtures import bundle, FakeClock, PLATFORM_SOURCE
from ...chapter3_g0.tests.manual_backend import ManualLedger
from .. import backend as wired
from ..gating import WiringPermit
from .test_receipt_profile import simulated_view_raw


def simulation_bundle():
    config,instance,anchor=bundle(6)
    common=json.loads(PLATFORM_SOURCE.read_text(encoding='utf-8'))
    # Read only the already-frozen scalar metadata; no reference candidate,
    # native initializer output or original task schedules enter this fixture.
    actual=common['instance']['window_ms']
    unused=common['config']['defaults']['window_ms']
    config['defaults']['window_ms']=unused
    instance['window_ms']=actual
    instance['settings']['window_ms']=actual
    return config,instance,anchor


class WiringScenario:
    def __init__(self,config,instance,anchor,clock,*,init_delay=0,cleanup_ok=True):
        self.config,self.instance,self.anchor=config,instance,anchor
        self.clock=clock;self.init_delay=init_delay;self.cleanup_ok=cleanup_ok
        self.ledger=ManualLedger(config,instance,clock)
        self.calls=[];self.sessions=[];self.numeric_contexts=[];self.augment_requests=[]
        self.prepare_calls=[];self.native_requests=[];self.model_views=[]
        self.initializer_root=None

    def initializer(self,instance,config,budget,assess,*,allow_auto_low=False):
        self.calls.append('same_call_initializer')
        self.initializer_root=budget
        if not allow_auto_low:
            raise AssertionError('explicit original auto-L initializer entry missing')
        if instance is not self.instance or config is not self.config:
            raise AssertionError('shared coordinator changed loader input objects')
        assess(deepcopy(self.anchor),'SIMULATION_SAME_CALL_HEFT_SEED')
        self.clock.advance(self.init_delay)
        budget.check()
        return {'status':'BOUNDED_SEARCH_COMPLETED','origin':'FAKE_HEFT_KERNEL_NOT_REAL_RUN'}

    def build(self,config,instance,condition,budget,*,permit,dependencies=None,progress=None):
        self.calls.append(('fake_model_build',condition['phase'],condition['scene_id']))
        if budget is not self.initializer_root:
            raise AssertionError('local model changed root budget')
        view=make_model_view(instance,condition['scene_id'],condition['d0_all'])
        self.model_views.append(deepcopy(view))
        return SimpleNamespace(instance=view,budget=budget,
            as_solver_dict=lambda:{'kind':'HANDMADE_MODEL_PAYLOAD','metadata':{'source':'SIMULATION'}})

    def evaluate(self,model,candidate,accuracy,budget):
        self.calls.append(('fake_model_view',model.instance['scenarios'][0]['id']))
        return simulated_view_raw(self.ledger,model.instance,candidate,budget)

    def complete(self,model,candidate,raw,budget):
        self.prepare_calls.append({'budget_is_root':budget is self.initializer_root,
            'input_view_window_ms':model.instance['window_ms'],
            'raw_has_g0_context':'g0_context' in raw})
        return {'state':'INITIAL_POINT_REJECTED','x0':None,
                'reason':'SIMULATED_NUMERICAL_X0_REJECTION'}

    def dependency_map(self):
        scenario=self
        class FakeSession:
            def __init__(self,workdir,*,budget,permit,dependencies,cut_max_iterations):
                self.workdir=Path(workdir);self.budget=budget
                self.deadline=budget.deadline
                self.startup_deadline=budget.start+budget.effective_deadline_elapsed_s
                self.event_consumer=None;self.request_settled=True
                self.closed=self.request_blocked=False
                self.counter=0;self.cleanup=None
                self.metadata={'kind':'SIMULATED_SESSION_NOT_NATIVE_START',
                    'root_deadline':self.deadline,'startup_deadline':self.startup_deadline}
                scenario.sessions.append(self)
            def solve(self,payload,**options):
                self.counter+=1
                scenario.native_requests.append({'options':options.copy(),
                    'root_is_same':options.get('budget') is scenario.initializer_root,
                    'payload_kind':payload.get('kind'),'session_id':id(self)})
                if options['remaining_s']>self.budget.remaining:
                    raise AssertionError('request cap exceeds active scope')
                if options['solver_max_time_s']>self.budget.remaining:
                    raise AssertionError('native MaxTime exceeds active scope')
                return {'status':'SOLVED','budget_valid':True,'x':[1.0],
                    'accepted_for_evaluation':True,'intlinprog_entered':False}
            def is_idle(self):
                return (not self.closed and not self.request_blocked and self.request_settled
                        and self.event_consumer is None)
            def close(self):
                self.closed=True
                self.cleanup={'observed_tree_verified_terminated':scenario.cleanup_ok,
                    'cleanup_status':'graceful_closed' if scenario.cleanup_ok else 'unresolved',
                    'kind':'SIMULATED_CLEANUP_NO_PROCESS'}

        class FakeRecorder:
            def __init__(self,model,accuracy,budget,folder,*,model_evaluator,on_evaluation,
                         on_safe,witness_validator):
                self.model,self.budget,self.accuracy=model,budget,accuracy
                self.model_evaluator=model_evaluator
                self.on_evaluation,self.on_safe=on_evaluation,on_safe
                self.pending=None;self.assess_count=0
            def begin_request(self):
                self.pending=None
            def poll(self,prefix):
                return None
            def assess(self,vector,source):
                self.assess_count+=1
                condition=self.model.g0_condition;sid=condition['scene_id']
                candidate={'scenes':{sid:deepcopy(condition['anchor']['scenes'][sid])}}
                for row in candidate['scenes'][sid]:
                    if row['stage_id'] in condition['open_ids']:
                        row['opp']='L'
                raw=self.model_evaluator(self.model,candidate,self.accuracy,self.budget)
                self.on_evaluation(candidate,raw,source)
                if raw['state']=='SAFE':
                    self.on_safe(candidate,raw,source)
                return candidate,raw
            def summary(self):
                return {'assessments':self.assess_count,'kind':'FAKE_DECODER_NOT_NATIVE'}
            def release(self):
                pass

        class FakeNumericContext:
            def __init__(self,budget,*,permit,dependencies):
                self.budget=budget;self.failed=False
                self.recorder_factory=FakeRecorder
                scenario.numeric_contexts.append(self)
            def summary(self):
                return {'kind':'MOCK_AUGMENTED_CONTROL_ONLY',
                        'failed':self.failed,'mathematical_transform_executed':False}

        class FakeAugmentedSession:
            def __init__(self,native,context):
                self.native,self.context=native,context
            @property
            def event_consumer(self):
                return self.native.event_consumer
            @event_consumer.setter
            def event_consumer(self,value):
                self.native.event_consumer=value
            def solve(self,payload,**kwargs):
                scenario.augment_requests.append({'kind':'MOCK_AUGMENTED_PATH',
                    'budget_is_root':kwargs.get('budget') is scenario.initializer_root})
                return self.native.solve(payload,**kwargs)

        receipt=self.ledger.deps();receipt['evidence_kind']='SIMULATION'
        dependencies={'initializer':self.initializer,'receipt':receipt,
            'model':{'kind':'PATCHED_FAKE_MODEL'},
            'evaluation':{'evaluate_model_candidate':self.evaluate,
                          'complete_initial_point':self.complete,
                          'checked_thermal_witnesses':lambda *a:[],
                          'add_thermal_feedback':lambda *a:{'added':False}},
            'transport':{'kind':'FAKE_SESSION_DEPENDENCIES'},
            'numeric':{'kind':'FAKE_AUGMENTED_CONTROL_DEPENDENCIES'},
            'recorder_factory':FakeRecorder,'evaluate_model_candidate':self.evaluate,
            'witness_validator':lambda *a:[]}
        return dependencies,FakeSession,FakeNumericContext,FakeAugmentedSession

    def run(self,folder,*,seconds=300):
        deps,session,context,augmented=self.dependency_map()
        with ExitStack() as stack:
            stack.enter_context(self.ledger.patched())
            stack.enter_context(patch.object(wired.model_backend,'build',self.build))
            stack.enter_context(patch.object(wired,'ScopedMatlabSession',session))
            stack.enter_context(patch.object(wired,'ScopeAwareContext',context))
            stack.enter_context(patch.object(wired,'ScopedAugmentedSession',augmented))
            return wired.execute_wiring(lambda:(self.config,self.instance),folder,
                permit=WiringPermit('SIMULATION'),dependencies=deps,seconds=seconds,clock=self.clock)


class BackendDriverTests(unittest.TestCase):
    def run_scenario(self,**kwargs):
        config,instance,anchor=simulation_bundle()
        clock=FakeClock()
        scenario=WiringScenario(config,instance,anchor,clock,**kwargs)
        parent=Path(__file__).resolve().parent
        with TemporaryDirectory(prefix='driver-fixture-',dir=parent) as folder:
            # The only recursive cleanup is this explicitly named test folder.
            self.assertTrue(Path(folder).resolve().is_relative_to(parent))
            result=scenario.run(Path(folder)/'method')
        return result,scenario

    def test_two_stages_same_call_deployment_and_single_session(self):
        result,scenario=self.run_scenario()
        self.assertIsNone(result['failure'])
        self.assertEqual(result['evidence_kind'],'SIMULATION')
        self.assertFalse(result['real_execution'])
        self.assertEqual(scenario.calls.count('same_call_initializer'),1)
        self.assertEqual(result['D0'],derive_deployment(scenario.config,scenario.instance,result['S0']['candidate']))
        self.assertEqual(len(scenario.sessions),1)
        self.assertEqual(len(scenario.numeric_contexts),1)
        self.assertEqual(len(result['stages']['1']),2)
        self.assertEqual(len(result['stages']['2']),2)
        self.assertEqual(len(scenario.native_requests),4)
        self.assertEqual(len(scenario.augment_requests),2)
        self.assertTrue(all(r['root_is_same'] for r in scenario.native_requests))
        self.assertTrue(all(r['model_completed'] and r['solver_entered']
                            for records in result['stages'].values() for r in records))
        self.assertEqual(result['final']['d0'],result['D0'])
        self.assertEqual(result['final']['evidence_kind'],'SIMULATION')
        self.assertTrue(result['cleanup']['verified'])
        self.assertEqual(scenario.sessions[0].deadline,scenario.initializer_root.deadline)

    def test_effective_230_window_ignores_400_default_and_x0_rejection_is_bare(self):
        result,scenario=self.run_scenario()
        self.assertIsNone(result['failure'])
        self.assertEqual(scenario.config['defaults']['window_ms'],'400')
        self.assertEqual(scenario.instance['window_ms'],'230')
        self.assertTrue(scenario.model_views)
        self.assertTrue(all(v['window_ms']=='230' for v in scenario.model_views))
        self.assertTrue(all(p['input_view_window_ms']=='230' and p['budget_is_root']
                            and not p['raw_has_g0_context'] for p in scenario.prepare_calls))
        self.assertTrue(all('x0' not in r['options'] for r in scenario.native_requests))
        self.assertTrue(all(r['warm_start']['state']=='INITIAL_POINT_REJECTED'
                            for records in result['stages'].values() for r in records))

    def test_phase_one_cutoff_keeps_safe_and_second_stage_uses_same_root(self):
        result,scenario=self.run_scenario(init_delay=151)
        self.assertIsNone(result['failure'])
        self.assertIsNotNone(result['S0'])
        self.assertEqual(result['S1']['candidate'],result['S0']['candidate'])
        self.assertEqual(result['stages']['1'],[])
        self.assertEqual(len(result['stages']['2']),2)
        self.assertEqual(len(scenario.sessions),1)
        self.assertEqual(scenario.sessions[0].deadline,300)
        self.assertLess(scenario.sessions[0].startup_deadline,300)
        self.assertIsNotNone(result['final'])

    def test_root_cutoff_preserves_previously_formed_safe_without_session(self):
        result,scenario=self.run_scenario(init_delay=300)
        self.assertIsNone(result['failure'])
        self.assertIsNotNone(result['final'])
        self.assertEqual(result['final']['candidate'],result['S0']['candidate'])
        self.assertEqual(result['reason'],'ROOT_CUTOFF')
        self.assertEqual(scenario.sessions,[])
        self.assertEqual(scenario.native_requests,[])

    def test_cleanup_failure_preserves_safe_and_reports_fault(self):
        result,scenario=self.run_scenario(cleanup_ok=False)
        self.assertIsNotNone(result['final'])
        self.assertIsNotNone(result['S0'])
        self.assertFalse(result['cleanup']['verified'])
        self.assertEqual(result['failure']['kind'],'CLEANUP_FAILURE')
        self.assertEqual(result['reason'],'CLEANUP_FAILURE')
        self.assertEqual(len(scenario.sessions),1)

    def test_reference_information_rejected_before_initializer_or_session(self):
        config,instance,anchor=simulation_bundle()
        instance['provenance']={'reference_timetable':{'answer':'FORBIDDEN'}}
        scenario=WiringScenario(config,instance,anchor,FakeClock())
        parent=Path(__file__).resolve().parent
        with TemporaryDirectory(prefix='driver-fixture-',dir=parent) as folder:
            self.assertTrue(Path(folder).resolve().is_relative_to(parent))
            result=scenario.run(Path(folder)/'method')
        self.assertIsNone(result['final'])
        self.assertEqual(result['failure']['kind'],'TECHNICAL_FAILURE')
        self.assertIn('FORBIDDEN_REFERENCE_INFORMATION',result['failure']['message'])
        self.assertEqual(scenario.calls,[])
        self.assertEqual(scenario.sessions,[])


if __name__=='__main__':
    unittest.main()
