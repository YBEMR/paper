"""Deterministic lifecycle tests: mock physics/native, real receipt identities.

Events are published through the actual Recorder polling protocol. Mock
energies and temperatures test control flow only, never physical effects.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest
from unittest.mock import patch

from control_policy import with_auto_low_idle
from diagnostic_search import Recorder
from inputs import build_instance, load_config
from milp import _digest
from run_milp_precheck import select_fixture
from schedules import validate_schedule
import scene_adapter as adapter
from thermal import Exhausted

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
RECORDS={'scope':'mock physical/native lifecycle control flow; not physical or performance evidence'}
_BASE=None


def small_input(budget=None):
    """Rebuild a named one-Stage/two-scene correctness input on every call."""
    config=load_config(); base=build_instance(config,'base__R1',budget=budget)
    ab,ac=[s['id'] for s in base['scenarios']]
    instance,starts=select_fixture(base,'partial_lifecycle',
        {ab:['A.pre'],ac:['A.pre']},{'A.pre':[0]})
    instance['start_domain']={'version':1,'kind':'explicit_grid_subset','by_scene_stage_ms':starts}
    return with_auto_low_idle(config),with_auto_low_idle(instance)


def fixture_for_units():
    global _BASE
    if _BASE is None: _BASE=small_input()
    return deepcopy(_BASE)


def candidate(model,number):
    scene=model.instance['scenarios'][0]; sid=scene['id']
    opp={0:'H',1:'M',2:'L'}[int(number)]
    return {'scenes':{sid:[{'stage_id':scene['stage_instances'][0]['id'],
                              'unit':'CPU1','opp':opp,'start_ms':'0'}]}}


class Clock:
    def __init__(self): self.now=0.0
    def __call__(self): return self.now
    def tick(self,seconds=0.25): self.now+=seconds


class Harness:
    def __init__(self,**options):
        self.options=options; self.clock=Clock(); self.trace=[]; self.models={}
        self.sessions=[]; self.budgets=[]; self.aggregate_values=[]; self.inside=False
        self.requests={}; self.primary_budget=None

    def loader(self,budget):
        self.primary_budget=budget; self.budgets.append(id(budget)); self.clock.tick()
        return fixture_for_units()

    def builder(self,instance,config,**kwargs):
        budget=kwargs['budget']; sid=kwargs['fixed_scene_id']
        self.budgets.append(id(budget)); self.clock.tick()
        view=adapter.make_scene_instance(instance,sid)
        for shared,unit in kwargs['fixed_shared_deployment'].items():
            if shared in view['stage_modes']:
                view['stage_modes'][shared]=[m for m in view['stage_modes'][shared] if m['unit_id']==unit]
        model=SimpleNamespace(instance=view,budget=budget,names=['y_fixture'],scenes={sid:{}},
            preprocessing={'source_input_sha256':_digest(instance),'fixed_shared_deployment':{'A.pre':'CPU1'}})
        model.summary=lambda:{'problem_id':view['id'],'variables':1,'rows':0}
        model.as_solver_dict=lambda:{'marker':sid}
        self.models[sid]=model
        if self.options.get('expire_construction'): self.clock.tick(100)
        return model

    def evaluator(self,model,proposed,accuracy,budget):
        self.budgets.append(id(budget)); self.clock.tick()
        sid=next(iter(proposed['scenes'])); opp=proposed['scenes'][sid][0]['opp']
        checked=validate_schedule(model.instance,proposed)
        assert checked['state']=='SCHEDULE_VALID_THERMAL_UNCHECKED',checked
        violation=self.options.get('violation') and opp=='M'
        points=[]
        if violation:
            limit=model.instance['scenarios'][0]['maximum_temperature_degC'][0]
            points=[{'scene_id':sid,'node':'CPU1','time_s':'0',
                'temperature_degC':['81','81'],'limit_degC':limit,
                'formed_at_elapsed_s':budget.elapsed}]
        value=str({'H':10,'M':8,'L':6}[opp])
        return {'state':'THERMAL_VIOLATION' if violation else 'SAFE',
            'problem_id':model.instance['id'],'legality':checked,'violations':points,
            'weighted_energy_J':None if violation else [value,value],
            'safe_upper_bound_J':None if violation else value,'rankable_energy':not violation,
            'completed_at_elapsed_s':budget.elapsed,'reason':'MOCK_PROTOCOL_ONLY',
            'evidence_identity':{'input_sha256':_digest(model.instance),'candidate_sha256':_digest(proposed)}}

    def initial(self,model,accuracy,budget,*args,**kwargs):
        self.budgets.append(id(budget)); self.clock.tick()
        if self.options.get('no_seed'):
            return {'state':'UNRESOLVED','reason':'NO_SAFE_INITIAL_WITNESS','witness':None,
                    'x0':None,'attempts':[],'completion':None}
        proposal=candidate(model,0); receipt=self.evaluator(model,proposal,accuracy,budget)
        return {'state':'SAFE_WITNESS_X0_REJECTED' if self.options.get('no_x0') else 'SAFE_POINT_READY',
            'reason':'INITIAL_POINT_REJECTED' if self.options.get('no_x0') else 'INITIAL_POINT_READY',
            'witness':{'candidate':proposal,'evaluation':receipt},
            'x0':None if self.options.get('no_x0') else [0.0],'attempts':[],
            'completion':{'state':'MOCK_COMPLETION'}}

    def physical(self,platform,entry,limits,segments,window,accuracy,budget,*,scene_id):
        opp=segments[0]['domain_opps']['CPU']; value=str({'H':10,'M':8,'L':6}[opp])
        return {'scene_id':scene_id,'state':'SAFE','reason':'MOCK_PHYSICS_ONLY',
            'complete':True,'rankable_energy':True,'violations':[],
            'energy_J':[value,value],'energy_accuracy_met':True,'covered_until_s':'2/5',
            'completed_at_elapsed_s':budget.elapsed}

    def scene_evaluator(self,instance,sid,mapping,proposal,accuracy,budget):
        self.budgets.append(id(budget)); self.clock.tick()
        if self.options.get('expire_recheck') and proposal['scenes'][sid][0]['opp']!='H':
            self.clock.tick(100)
        with patch.object(adapter,'evaluate_piecewise',side_effect=self.physical):
            receipt=adapter.evaluate_partial_scene(instance,sid,mapping,proposal,accuracy,budget)
        self.trace.append(('scene_receipt',sid,receipt['state'],self.inside))
        return receipt

    def aggregator(self,instance,mapping,receipts,candidates,accuracy,budget):
        self.budgets.append(id(budget)); self.clock.tick()
        result=adapter.aggregate_partial_scene_receipts(instance,mapping,receipts,candidates,accuracy,budget)
        if result['state']=='SAFE':
            self.aggregate_values.append(result['safe_upper_bound_J'])
            self.trace.append(('aggregate',result['safe_upper_bound_J'],self.inside,budget.elapsed))
            if self.options.get('late_aggregate_return') and len(self.aggregate_values)>1:
                self.clock.tick(100)
        return result

    def recorder(self,*args,**kwargs):
        from partial_method import PartialRecorder
        def decoder(model,x):
            if len(x)!=1 or x[0] not in (0,1,2): raise ValueError('Mock noninteger candidate')
            return candidate(model,x[0])
        return PartialRecorder(*args,decoder=decoder,**kwargs)

    def feedback(self,model,proposed,evaluation):
        assert not self.inside,'Feedback must wait until native request finishes'
        assert evaluation['state']=='THERMAL_VIOLATION'
        self.clock.tick(); self.trace.append(('feedback',next(iter(proposed['scenes']))))
        return {'state':'ROWS_ADDED','rows_added':1,'scope':'MOCK_CONTROL_ONLY'}

    def session_factory(self,workdir,**kwargs):
        harness=self
        class Session:
            def __init__(self):
                self.workdir=Path(workdir); self.workdir.mkdir(parents=True)
                self.counter=0; self.event_consumer=None
                harness.budgets.append(id(kwargs['budget'])); harness.clock.tick()
                harness.sessions.append(self)
            def solve(self,payload,**request):
                sid=payload['marker']; self.counter+=1
                harness.requests[sid]=harness.requests.get(sid,0)+1
                harness.budgets.append(id(request['budget']))
                harness.trace.append(('request',sid,request['remaining_s'],request.get('x0')))
                harness.inside=True; prefix=self.workdir/('request_%03d'%self.counter)
                limit=2 if harness.options.get('repeat_violation') else 1
                number=2 if harness.options.get('violation') and harness.requests[sid]>limit else 1
                for sequence,event in enumerate(({'kind':'solver_entered'},
                        {'kind':'incumbent','x':[number],'values':{'lowerbound':1.0}}),1):
                    harness.clock.tick()
                    Path(str(prefix)+'.event_%06d.json'%sequence).write_text(json.dumps(event),encoding='utf-8')
                    if self.event_consumer: self.event_consumer(prefix)
                cancelled=Path(str(prefix)+'.cancel').exists()
                harness.trace.append(('return',sid,cancelled))
                harness.inside=False; harness.clock.tick()
                if harness.options.get('raise_after_callback'): raise RuntimeError('MOCK_WORKER_ERROR')
                if harness.options.get('expire_after_callback'): harness.clock.tick(100)
                within=request['budget'].remaining>0
                return {'status':'SOLVED','x':[] if cancelled else [number],
                    'exitflag':-1 if cancelled else 1,'budget_valid':within,
                    'accepted_for_evaluation':within and not cancelled,
                    'intlinprog_entered':True,'output':{'lowerbound':1.0},'callbacks':[]}
            def close(self): harness.trace.append(('closed',)); harness.clock.tick(2)
        if self.options.get('startup_error'): raise RuntimeError('MOCK_STARTUP_ERROR')
        return Session()

    def run(self,workdir,**extra):
        from partial_method import execute_shared_deployment
        return execute_shared_deployment(self.loader,workdir,shared_deployment={'A.pre':'CPU1'},
            seconds=60,clock=self.clock,model_builder=self.builder,session_factory=self.session_factory,
            initial_preparer=self.initial,model_evaluator=self.evaluator,
            scene_evaluator=self.scene_evaluator,aggregator=self.aggregator,
            recorder_factory=self.recorder,feedback_adder=self.feedback,**extra)


class PartialMethodLifecycle(unittest.TestCase):
    def setUp(self):
        home=REPO/'.runtime/partial_method_unit'; home.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='unit_',dir=home)
        self.path=Path(self.temp.name).resolve(); self.path.relative_to(home.resolve())
    def tearDown(self):
        self.path.relative_to((REPO/'.runtime/partial_method_unit').resolve())
        self.temp.cleanup()

    def test_single_budget_session_and_callback_updates_before_return(self):
        h=Harness(); result=h.run(self.path/'run')
        self.assertEqual(result['state'],'SAFE',result)
        self.assertEqual(len(h.sessions),1)
        self.assertEqual(len(set(h.budgets)),1)
        self.assertEqual(len(h.requests),2)
        self.assertTrue(any(r[0]=='aggregate' and r[2] for r in h.trace))
        self.assertGreater(len(set(h.aggregate_values)),1)
        self.assertTrue(all(r[2]<60 for r in h.trace if r[0]=='request'))
        self.assertFalse(result['independently_proven_optimal'])
        self.assertFalse(result['independently_proven_infeasible'])
        RECORDS['mock_success']={'result':result,'trace':h.trace}

    def test_callback_violation_cancel_return_then_feedback(self):
        h=Harness(violation=True); result=h.run(self.path/'run')
        self.assertEqual(result['state'],'SAFE',result)
        cuts=[i for i,r in enumerate(h.trace) if r[0]=='feedback']
        self.assertTrue(cuts,h.trace)
        for i in cuts:
            self.assertTrue(any(r[0]=='return' and r[2] for r in h.trace[:i]))
        self.assertTrue(all(count==2 for count in h.requests.values()),h.trace)
        self.assertFalse(result['independently_proven_infeasible'])
        RECORDS['mock_feedback']={'result':result,'trace':h.trace}

    def test_repeated_final_candidate_does_not_republish_global_improvement(self):
        h=Harness(); result=h.run(self.path/'run')
        self.assertEqual(result['state'],'SAFE')
        # Initial H/H, first callback M/H, second callback M/M.
        self.assertEqual(len(h.aggregate_values),3,h.trace)

    def test_cached_violation_is_cancelled_again_in_next_request(self):
        h=Harness(violation=True,repeat_violation=True); result=h.run(self.path/'run')
        self.assertEqual(result['state'],'SAFE',result)
        self.assertTrue(all(count==3 for count in h.requests.values()),h.trace)
        self.assertEqual(sum(r[0]=='feedback' for r in h.trace),4)

    def test_committed_violation_survives_request_deadline_without_new_cut(self):
        h=Harness(violation=True,expire_after_callback=True); result=h.run(self.path/'run')
        self.assertEqual(result['state'],'SAFE',result)
        self.assertEqual(float(result['safe_upper_bound_J']),10.0)
        self.assertTrue(result['violations'])
        self.assertFalse(any(r[0]=='feedback' for r in h.trace))

    def test_late_original_recheck_retains_initial_global_safe(self):
        h=Harness(expire_recheck=True); result=h.run(self.path/'run')
        self.assertEqual(result['state'],'SAFE',result)
        self.assertEqual(float(result['safe_upper_bound_J']),10.0)
        self.assertTrue(result['budget_exhausted'])
        self.assertEqual(len(h.aggregate_values),1)

    def test_callback_safe_survives_late_native_final(self):
        h=Harness(expire_after_callback=True); result=h.run(self.path/'run')
        self.assertEqual(result['state'],'SAFE',result)
        self.assertLess(float(result['safe_upper_bound_J']),10.0)
        self.assertTrue(any(r[0]=='aggregate' and r[2] for r in h.trace))

    def test_already_committed_aggregate_survives_late_transfer(self):
        h=Harness(late_aggregate_return=True); result=h.run(self.path/'run')
        self.assertEqual(result['state'],'SAFE',result)
        self.assertLess(float(result['safe_upper_bound_J']),10.0)

    def test_worker_error_keeps_callback_safe_and_old_evidence(self):
        h=Harness(raise_after_callback=True); result=h.run(self.path/'run')
        self.assertEqual(result['state'],'SAFE',result)
        self.assertLess(float(result['safe_upper_bound_J']),10.0)

    def test_startup_error_preserves_all_initial_scenes(self):
        h=Harness(startup_error=True); result=h.run(self.path/'run')
        self.assertEqual(result['state'],'SAFE',result)
        self.assertEqual(float(result['safe_upper_bound_J']),10.0)
        self.assertFalse(h.requests)

    def test_rejected_x0_falls_back_without_deleting_legal_domain(self):
        h=Harness(no_x0=True); result=h.run(self.path/'run')
        self.assertEqual(result['state'],'SAFE',result)
        self.assertTrue(h.requests)
        self.assertTrue(all(r[3] is None for r in h.trace if r[0]=='request'))

    def test_no_seed_can_still_search_without_x0(self):
        h=Harness(no_seed=True); result=h.run(self.path/'run')
        self.assertEqual(result['state'],'SAFE',result)
        self.assertTrue(h.requests)
        self.assertFalse(result['independently_proven_infeasible'])

    def test_construction_deadline_cannot_start_worker_or_create_U(self):
        h=Harness(expire_construction=True); result=h.run(self.path/'run')
        self.assertNotEqual(result['state'],'SAFE')
        self.assertIsNone(result['safe_upper_bound_J'])
        self.assertFalse(h.sessions)

    def test_conditional_bound_interrupt_keeps_completed_global_bound(self):
        import partial_bounds
        original=partial_bounds.independent_lower_bound; h=Harness()
        def interrupted(instance,mapping=None,budget=None):
            if mapping is not None:
                h.clock.tick(100); raise Exhausted('wall_time_limit')
            return original(instance,None,budget)
        with patch.object(partial_bounds,'independent_lower_bound',side_effect=interrupted):
            result=h.run(self.path/'run')
        self.assertIsNotNone(result['deployment_bounds']['L0'])
        self.assertIsNone(result['deployment_bounds']['L_a'])
        self.assertIsNone(result['safe_upper_bound_J'])
        self.assertFalse(h.sessions)

    def test_given_directory_is_never_overwritten(self):
        h=Harness(); directory=self.path/'exists'; directory.mkdir()
        with self.assertRaises(FileExistsError): h.run(directory)
        self.assertIsNone(h.primary_budget)


if __name__=='__main__':
    unittest.main()
