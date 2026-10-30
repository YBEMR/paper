"""Bounded worker/runner tests using only fake evaluation/process providers.

The providers deliberately use original evaluator output shape, including its
absence of evidence_identity, so mocks cannot hide an incompatible real API.
No subprocess, native solver or temperature propagation is invoked here.
"""
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
from . import support as tempfile
import unittest

from ...chapter3_g0.contract import canonical_hash
from ...chapter3_g0.tests.fixtures import bundle, FakeClock
from ..gating import WiringPermit
from ..worker import normalize, execute_post
from ..runner import run_once


class TestWorkerRunner(unittest.TestCase):
    def setUp(self):
        self.scratch=tempfile.TemporaryDirectory(prefix='g0_worker_mock_')
        self.folder=Path(self.scratch.name)
        self.config,self.instance,self.candidate=bundle(4)
        self.common=self.folder/'common.json'
        self.common.write_text(json.dumps({'schema':'HANDMADE_SIMULATION_COMMON',
            'config':self.config,'instance':self.instance},ensure_ascii=False),encoding='utf-8')
        self.sha=hashlib.sha256(self.common.read_bytes()).hexdigest()
        self.permit=WiringPermit()

    def tearDown(self):
        self.scratch.cleanup()

    def raw_method(self):
        aggregate={'state':'SAFE','rankable_energy':True,'safe_candidate':deepcopy(self.candidate),
            'safe_upper_bound_J':'1','identity':{'candidate_sha256':canonical_hash(self.candidate),
                'full_input_sha256':canonical_hash(self.instance)}}
        final={'aggregate':aggregate,'candidate':deepcopy(self.candidate),'U_J':'1',
               'completed_at_elapsed_s':1.0}
        return {'evidence_kind':'SIMULATION','input_sha256':canonical_hash(self.instance),
            'final':final,'failure':None,'reason':'ROOT_CUTOFF','stopped_s':300.0,
            'first_legal_s':0.2,'first_safe_s':1.0,
            'stages':{'1':[{'solver_entered':True,'status':'COMPLETED'}],
                      '2':[{'solver_entered':True,'status':'ROOT_CUTOFF'}]}}

    def original_post_shape(self,budget,state='SAFE'):
        physical={sid:{'state':'SAFE','complete':True,'rankable_energy':True,
            'energy_accuracy_met':True,'covered_until_s':str(F(self.instance['window_ms'])/1000),
            'energy_J':['1','1'],'violations':[],'completed_at_elapsed_s':budget.elapsed}
            for sid in self.candidate['scenes']}
        result={'state':state,'reason':'SIMULATED_ORIGINAL_EVALUATOR_RESULT',
            'problem_id':self.instance['id'],'rankable_energy':state=='SAFE',
            'weighted_energy_J':['1','1'] if state=='SAFE' else None,
            'safe_upper_bound_J':'1' if state=='SAFE' else None,
            'scenes':physical if state=='SAFE' else {},'violations':[],
            'completed_at_elapsed_s':budget.elapsed}
        # thermal.evaluate_candidate returns no evidence_identity.  The worker
        # must use its own current-call binding, not require a fabricated field.
        self.assertNotIn('evidence_identity',result)
        return result

    def test_normalize_preserves_complete_safe_on_cutoff(self):
        raw=self.raw_method()
        result=normalize(raw,input_sha256=self.sha,method_seconds=300,process_seconds=310)
        self.assertTrue(result['safe_retained'])
        self.assertEqual(result['safe_upper_bound_J'],'1')
        self.assertEqual(result['execution_state'],'NORMAL_TIME_LIMIT')
        self.assertTrue(result['post_eligible'])
        self.assertEqual(result['phase_native_entries'],{'1':1,'2':1})

    def test_normalize_keeps_safe_but_does_not_hide_numerical_fault(self):
        raw=self.raw_method();raw['failure']={'kind':'TECHNICAL_FAILURE',
            'error_type':'ArithmeticError','message':'NUMERICAL_CONFLICT'}
        result=normalize(raw,input_sha256=self.sha,method_seconds=300,process_seconds=310)
        self.assertTrue(result['safe_retained'])
        self.assertEqual(result['execution_state'],'NUMERICAL_ANOMALY')
        self.assertFalse(result['post_eligible'])

    def test_normalize_malformed_timestamps_never_crash_or_rank(self):
        for timestamp in (None,'1',True,float('nan'),300.0,-1):
            with self.subTest(timestamp=timestamp):
                raw=self.raw_method();raw['final']['completed_at_elapsed_s']=timestamp
                result=normalize(raw,input_sha256=self.sha,method_seconds=300,process_seconds=310)
                self.assertFalse(result['safe_retained'])
                self.assertIsNone(result['safe_upper_bound_J'])

    def test_normalize_rejects_mismatched_candidate(self):
        raw=self.raw_method();raw['final']['aggregate']['identity']['candidate_sha256']='WRONG'
        result=normalize(raw,input_sha256=self.sha,method_seconds=300,process_seconds=310)
        self.assertFalse(result['safe_retained'])
        self.assertFalse(result['post_eligible'])

    def test_post_accepts_original_evaluator_shape_via_current_call_binding(self):
        clock=FakeClock();raws=[]
        def evaluator(instance,candidate,accuracy,budget):
            self.assertEqual(instance,self.instance);self.assertEqual(candidate,self.candidate)
            result=self.original_post_shape(budget);raws.append(deepcopy(result));return result
        result=execute_post(self.common,self.sha,self.candidate,permit=self.permit,
            dependencies={'evaluate_candidate':evaluator},clock=clock)
        self.assertEqual(result['state'],'SAFE')
        self.assertEqual(result['evaluation'],raws[0])
        self.assertNotIn('evidence_identity',result['evaluation'])

    def test_post_semantic_rejections_are_not_technical_failures(self):
        for state in ('THERMAL_VIOLATION','INVALID_SCHEDULE','UNRESOLVED'):
            with self.subTest(state=state):
                clock=FakeClock()
                def evaluator(instance,candidate,accuracy,budget):
                    result=self.original_post_shape(budget,state)
                    if state=='THERMAL_VIOLATION':
                        result['violations']=[dict(scene_id=self.instance['scenarios'][0]['id'],
                            node='CPU1',temperature_degC=['81','82'],limit_degC='80',
                            time_s='1/20',formed_at_elapsed_s=budget.elapsed)]
                    return result
                result=execute_post(self.common,self.sha,self.candidate,permit=self.permit,
                    dependencies={'evaluate_candidate':evaluator},clock=clock)
                self.assertEqual(result['state'],state)
                if state=='THERMAL_VIOLATION':
                    self.assertTrue(result['evaluation']['violations'])

    def test_post_full_clock_expiry_does_not_accept_new_safe(self):
        clock=FakeClock()
        def evaluator(instance,candidate,accuracy,budget):
            result=self.original_post_shape(budget)
            clock.advance(61)
            return result
        result=execute_post(self.common,self.sha,self.candidate,permit=self.permit,
            dependencies={'evaluate_candidate':evaluator},clock=clock)
        self.assertEqual(result['state'],'UNRESOLVED')
        self.assertGreaterEqual(result['process_elapsed_s'],60)

    def test_post_missing_scene_is_unresolved(self):
        clock=FakeClock()
        def evaluator(instance,candidate,accuracy,budget):
            result=self.original_post_shape(budget)
            result['scenes'].pop(next(iter(result['scenes'])))
            return result
        result=execute_post(self.common,self.sha,self.candidate,permit=self.permit,
            dependencies={'evaluate_candidate':evaluator},clock=clock)
        self.assertEqual(result['state'],'UNRESOLVED')

    def test_post_backend_error_is_technical(self):
        def evaluator(*args):raise MemoryError('SIMULATED_POST_MEMORY_FAILURE')
        result=execute_post(self.common,self.sha,self.candidate,permit=self.permit,
            dependencies={'evaluate_candidate':evaluator},clock=FakeClock())
        self.assertEqual(result['state'],'TECHNICAL_FAILURE')
        self.assertEqual(result['error_type'],'MemoryError')

    def plan(self):
        return dict(research_method_calls_max=1,method_seconds_max=300,post_calls_max=1,
            post_seconds_max=60,method_process_wall_seconds=480,batch_wall_seconds=720,retry_count=0)

    def method_receipt(self,*,safe=True,state='NORMAL_COMPLETION'):
        return dict(process_state='COMPLETED',result=dict(execution_state=state,
            post_eligible=safe,safe_retained=safe,
            full_input_sha256=canonical_hash(self.instance),
            weighted_energy_J=['1','1'] if safe else None,
            safe_candidate=deepcopy(self.candidate) if safe else None))

    def post_receipt(self,*,energy=('1','1')):
        result={'state':'SAFE','identity':{'input_sha256':canonical_hash(self.instance),
            'candidate_sha256':canonical_hash(self.candidate)}}
        if energy is not None:
            result['evaluation']={'weighted_energy_J':list(energy)}
        return {'process_state':'COMPLETED','result':result}

    def test_runner_one_method_one_post_and_no_real_process_claim(self):
        clock=FakeClock();calls=[]
        def process(mode,**kwargs):
            calls.append((mode,deepcopy(kwargs)))
            clock.advance(20 if mode=='method' else 3)
            return self.method_receipt() if mode=='method' else self.post_receipt()
        result=run_once(self.plan(),self.folder/'batch',permit=self.permit,process_factory=process,clock=clock)
        self.assertEqual((result['method_calls'],result['post_calls']),(1,1))
        self.assertEqual(result['stop_reason'],'COMPLETED')
        self.assertFalse(result['real_os_process_validation'])
        self.assertEqual(calls[0][1]['limit_s'],480)
        self.assertEqual(calls[1][1]['limit_s'],60)
        self.assertEqual(calls[1][1]['candidate'],self.candidate)

    def test_runner_does_not_post_without_complete_safe(self):
        calls=[]
        def process(mode,**kwargs):calls.append(mode);return self.method_receipt(safe=False)
        result=run_once(self.plan(),self.folder/'no-safe',permit=self.permit,process_factory=process,clock=FakeClock())
        self.assertEqual(calls,['method'])
        self.assertEqual(result['post_calls'],0)
        self.assertEqual(result['stop_reason'],'NO_COMPLETE_SAFE_NO_POST')

    def test_runner_method_clock_overrun_cannot_be_hidden_by_factory(self):
        clock=FakeClock();calls=[]
        def process(mode,**kwargs):
            calls.append(mode);clock.advance(481)
            return self.method_receipt()
        result=run_once(self.plan(),self.folder/'method-overrun',permit=self.permit,process_factory=process,clock=clock)
        self.assertEqual(calls,['method'])
        self.assertEqual(result['post_calls'],0)
        self.assertNotEqual(result['stop_reason'],'COMPLETED')

    def test_runner_post_clock_overrun_cannot_be_reported_complete(self):
        clock=FakeClock()
        def process(mode,**kwargs):
            clock.advance(10 if mode=='method' else 61)
            return self.method_receipt() if mode=='method' else self.post_receipt()
        result=run_once(self.plan(),self.folder/'post-overrun',permit=self.permit,process_factory=process,clock=clock)
        self.assertEqual(result['post_calls'],1)
        self.assertNotEqual(result['stop_reason'],'COMPLETED')

    def test_runner_post_semantic_statuses_are_preserved(self):
        for state in ('THERMAL_VIOLATION','INVALID_SCHEDULE','UNRESOLVED'):
            with self.subTest(state=state):
                def process(mode,**kwargs):
                    return self.method_receipt() if mode=='method' else dict(process_state='COMPLETED',result={'state':state})
                result=run_once(self.plan(),self.folder/state,permit=self.permit,process_factory=process,clock=FakeClock())
                self.assertEqual(result['stop_reason'],'POST_'+state)

    def test_runner_same_candidate_post_energy_conflict_stops(self):
        def process(mode,**kwargs):
            return self.method_receipt() if mode=='method' else self.post_receipt(energy=('2','2'))
        result=run_once(self.plan(),self.folder/'energy-conflict',permit=self.permit,
            process_factory=process,clock=FakeClock())
        self.assertEqual(result['stop_reason'],'POST_ENERGY_CONFLICT')
        self.assertTrue(result['method']['result']['safe_retained'])
        self.assertEqual(result['method']['result']['weighted_energy_J'],['1','1'])
        self.assertEqual((result['method_calls'],result['post_calls']),(1,1))

    def test_runner_missing_method_or_post_energy_cannot_complete(self):
        for missing in ('method','post'):
            with self.subTest(missing=missing):
                def process(mode,**kwargs):
                    if mode=='method':
                        receipt=self.method_receipt()
                        if missing=='method':
                            receipt['result'].pop('weighted_energy_J')
                        return receipt
                    return self.post_receipt(energy=None if missing=='post' else ('1','1'))
                result=run_once(self.plan(),self.folder/('missing-energy-'+missing),
                    permit=self.permit,process_factory=process,clock=FakeClock())
                self.assertEqual(result['stop_reason'],'POST_INCOMPLETE_RECEIPT')
                self.assertTrue(result['method']['result']['safe_retained'])

    def test_runner_same_energy_different_candidate_identity_stops(self):
        def process(mode,**kwargs):
            if mode=='method':
                return self.method_receipt()
            receipt=self.post_receipt()
            receipt['result']['identity']['candidate_sha256']='OTHER_CANDIDATE'
            return receipt
        result=run_once(self.plan(),self.folder/'identity-conflict',permit=self.permit,
            process_factory=process,clock=FakeClock())
        self.assertEqual(result['stop_reason'],'POST_IDENTITY_CONFLICT')
        self.assertTrue(result['method']['result']['safe_retained'])
        self.assertEqual(result['method']['result']['safe_candidate'],self.candidate)

    def test_runner_no_retry_after_fault_or_existing_batch(self):
        calls=[]
        def process(mode,**kwargs):
            calls.append(mode);return self.method_receipt(state='NUMERICAL_ANOMALY')
        path=self.folder/'once'
        result=run_once(self.plan(),path,permit=self.permit,process_factory=process,clock=FakeClock())
        self.assertEqual(calls,['method']);self.assertEqual(result['post_calls'],0)
        with self.assertRaises(FileExistsError):
            run_once(self.plan(),path,permit=self.permit,process_factory=process,clock=FakeClock())
        self.assertEqual(calls,['method'])
