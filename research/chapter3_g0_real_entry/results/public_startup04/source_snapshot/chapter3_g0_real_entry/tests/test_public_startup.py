"""Seven V2 groups, explicit fake sessions/ledger/clocks; zero native work."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from . import test_backend_driver as old
from .support import TemporaryDirectory
from ...chapter3_g0.tests.fixtures import FakeClock
from ...chapter3_g0.budget import G0Budget,ScopeExhausted
from .. import backend as wired
from ..execution_costs import PUBLIC,LEGACY
from ..gating import WiringPermit
from ..worker import normalize
from ..real_runner import before_post


class PublicScenario(old.WiringScenario):
    def __init__(self,*args,startup_delay=58,cleanup_delay=7,no_safe=False,
                 startup_error=False,reuse_fault=None,admission_delay=0,**kwargs):
        super().__init__(*args,**kwargs)
        self.startup_delay,self.cleanup_delay=startup_delay,cleanup_delay
        self.no_safe,self.startup_error,self.reuse_fault=no_safe,startup_error,reuse_fault
        self.admission_delay=admission_delay
        self.created_scopes=[];self.public_requests=[]

    def initializer(self,instance,config,budget,assess,*,allow_auto_low=False):
        if allow_auto_low is not True:raise AssertionError('AUTO_L_EXPLICIT_BINDING_REQUIRED')
        if self.no_safe:return {'status':'NO_SAFE_UNRESOLVED'}
        return super().initializer(instance,config,budget,assess,allow_auto_low=allow_auto_low)

    def build(self,config,instance,condition,budget,**kwargs):
        self.clock.advance(1);budget.check()
        return super().build(config,instance,condition,budget,**kwargs)

    def complete(self,model,candidate,raw,budget):
        self.clock.advance(1);budget.check()
        return super().complete(model,candidate,raw,budget)

    def dependency_map(self):
        deps,base,context,augmented=super().dependency_map();scenario=self
        class Session(base):
            def __init__(self,*args,**kwargs):
                super().__init__(*args,**kwargs);self.alive=True
                b=self.budget;scenario.created_scopes.append(deepcopy(b.capture_scope()))
                self.metadata['startup_intervals']={}
                available=b.remaining;scenario.clock.advance(min(2,scenario.startup_delay))
                self.metadata['startup_intervals']['ready_wait_start_s']=b.elapsed
                failed=scenario.startup_delay>=available or scenario.startup_error
                scenario.clock.advance(max(0,available-min(2,scenario.startup_delay)) if scenario.startup_delay>=available
                                       else max(0,scenario.startup_delay-2))
                self.metadata['startup_intervals']['ready_wait_end_s']=b.elapsed
                if failed:
                    try:
                        b.check()
                        raise RuntimeError('SIMULATED_STARTUP_ERROR')
                    except Exception as error:
                        self.metadata['startup_intervals']['failure_cleanup_start_s']=b.elapsed
                        self.close()
                        self.metadata['startup_intervals']['failure_cleanup_end_s']=b.elapsed
                        error.matlab_cleanup=deepcopy(self.cleanup)
                        error.matlab_startup_metadata=deepcopy(self.metadata)
                        raise
                b.check()
                scenario.clock.advance(scenario.admission_delay)
            def solve(self,payload,**options):
                scenario.public_requests.append({'root_s':self.budget.elapsed,
                    'remaining_s':options['remaining_s'],'deadline':self.budget.effective_deadline_elapsed_s})
                returned=super().solve(payload,**options)
                scenario.clock.advance(3);self.budget.check()
                if len(scenario.native_requests)==2 and scenario.reuse_fault:
                    if scenario.reuse_fault=='unsettled':self.request_settled=False
                    elif scenario.reuse_fault=='blocked':self.request_blocked=True
                    elif scenario.reuse_fault=='exited':self.alive=False
                    elif scenario.reuse_fault=='closed':self.closed=True
                return returned
            def is_idle(self):return self.alive and super().is_idle()
            def close(self):
                if self.closed:return
                scenario.clock.advance(scenario.cleanup_delay);super().close()
        return deps,Session,context,augmented


class PublicStartupTests(unittest.TestCase):
    def scenario(self,**kwargs):
        config,instance,anchor=old.simulation_bundle()
        return PublicScenario(config,instance,anchor,FakeClock(),**kwargs)

    def run_case(self,**kwargs):
        s=self.scenario(**kwargs)
        with TemporaryDirectory(prefix='public-start-') as folder:
            result=s.run(Path(folder)/'method',execution_organization=PUBLIC)
        return result,s

    def test_group1_phase_public_ready_then_allocate_slots_and_reuse_once(self):
        r,s=self.run_case(init_delay=52)
        self.assertIsNone(r['failure']);self.assertEqual(r['execution_organization'],PUBLIC)
        self.assertEqual(len(s.sessions),1)
        self.assertEqual(s.created_scopes[0]['kind'],'phase')
        self.assertEqual(s.created_scopes[0]['name'],'phase1')
        self.assertEqual(s.sessions[0].startup_deadline,150)
        first=r['stages']['1'][0]
        self.assertEqual(first['started_s'],110)
        self.assertEqual(first['deadline_elapsed_s'],130)
        self.assertEqual(len(s.native_requests),4)
        self.assertEqual([x['new_attempt'] for x in r['public_start_records']],[True,False])
        self.assertEqual(r['session_lifecycle']['attempts'],1)

    def test_group2_no_safe_and_phase2_first_attempt_after_initialization_cutoff(self):
        r,s=self.run_case(no_safe=True)
        self.assertIsNone(r['final']);self.assertEqual(s.sessions,[])
        r,s=self.run_case(init_delay=150)
        self.assertIsNone(r['failure']);self.assertIsNotNone(r['S0'])
        self.assertEqual(r['stages']['1'],[])
        self.assertEqual(s.created_scopes[0]['name'],'phase2')
        self.assertEqual(s.sessions[0].startup_deadline,300)
        self.assertEqual(len(s.sessions),1);self.assertEqual(len(s.native_requests),2)
        self.assertEqual(r['S0']['candidate'],r['S1']['candidate'])

    def test_group3_exact_late_failed_or_unclean_start_stops_without_retry(self):
        for args in ({'startup_delay':98},{'startup_delay':99},
                     {'startup_delay':97,'admission_delay':2},
                     {'startup_error':True},{'startup_delay':98,'cleanup_ok':False}):
            r,s=self.run_case(init_delay=52,**args)
            self.assertIsNotNone(r['S0']);self.assertEqual(r['final']['candidate'],r['S0']['candidate'])
            self.assertEqual(len(s.sessions),1);self.assertEqual(s.native_requests,[])
            self.assertEqual(r['stages']['2'],[])
            self.assertEqual(r['session_lifecycle']['attempts'],1)
            if args.get('cleanup_ok') is False:self.assertEqual(r['failure']['kind'],'CLEANUP_FAILURE')
            elif args.get('startup_error'):self.assertIsNotNone(r['failure'])
            else:self.assertEqual(r['reason'],'STARTUP_PHASE_CUTOFF')
        r,s=self.run_case(init_delay=150,startup_delay=150)
        self.assertEqual(r['reason'],'STARTUP_ROOT_CUTOFF')
        self.assertIsNotNone(r['final']);self.assertEqual(len(s.sessions),1)
        self.assertEqual(s.native_requests,[])

    def test_group4_early_second_phase_and_unchanged_root_scope_deadlines(self):
        r,s=self.run_case(init_delay=52)
        self.assertLess(r['phase2_started_s'],150)
        self.assertEqual(r['budget']['limit_s'],300)
        self.assertEqual(s.initializer_root.start,0)
        self.assertEqual(s.initializer_root.deadline,300)
        self.assertTrue(all(x['root_is_same'] for x in s.native_requests))
        self.assertTrue(all(x['remaining_s']<=x['deadline']-x['root_s'] for x in s.public_requests))

    def test_group5_no_implicit_start_and_unsettled_blocked_exited_not_reused(self):
        for fault in ('unsettled','blocked','exited','closed'):
            r,s=self.run_case(init_delay=52,reuse_fault=fault)
            self.assertIsNotNone(r['final']);self.assertIsNotNone(r['failure'])
            self.assertEqual(len(s.sessions),1);self.assertEqual(len(s.native_requests),2)
            self.assertEqual(r['stages']['2'],[])
        s=self.scenario();deps,_,_,_=s.dependency_map();b=G0Budget(300,clock=s.clock)
        with TemporaryDirectory(prefix='no-implicit-') as folder:
            backend=wired.G0Backend(folder,permit=WiringPermit(),dependencies=deps,execution_organization=PUBLIC)
            backend.budget=b
            with self.assertRaises(RuntimeError):backend.prepare(None,None,b)
            self.assertEqual(backend.session_attempts,0)
            with b.scope('phase1',150,kind='phase'):
                with b.scope('slot',100,kind='slot'):
                    with self.assertRaises(ValueError):backend.start_public_session(b,phase=1)
            self.assertEqual(backend.session_attempts,0)

    def test_group6_success_failure_cost_partitions_and_final_close(self):
        for args in ({'init_delay':52},{'init_delay':52,'startup_delay':98}):
            r,s=self.run_case(**args);t=r['execution_timing'];startup=t['startup']
            self.assertAlmostEqual(sum(x['seconds'] for x in startup['exclusive_segments']),startup['overview']['seconds'])
            self.assertFalse(startup['overview']['add_to_components'])
            self.assertEqual(t['body_stopped_s'],r['stopped_s'])
            self.assertEqual(t['observed_elapsed_through_close_s'],t['final_close']['end_s'])
            if args.get('startup_delay')==98:
                self.assertEqual(startup['exclusive_seconds']['failed_startup_cleanup'],7)
                self.assertEqual(t['final_close']['seconds'],0)  # Do not count failed-start cleanup twice.
            else:
                self.assertEqual(startup['overview']['seconds'],58)
                self.assertEqual(startup['exclusive_seconds']['ready_wait'],56)
                self.assertEqual(t['final_close']['seconds'],7)
            self.assertEqual(t['root_deadline_elapsed_s'],300)

    def test_group7_failed_public_start_retains_original_scope_and_recovery_gate(self):
        r,s=self.run_case(init_delay=52,startup_delay=98)
        self.assertEqual(r['S0'],r['final'])
        self.assertIsInstance(r['S0']['scope'],str)
        phase=[x for x in r['scope_records'] if x['name']=='phase1'][0]
        self.assertEqual(r['S0']['scope'],phase['token'])
        self.assertLess(r['S0']['completed_at_elapsed_s'],150)
        self.assertEqual(r['public_start_records'][0]['scope']['token'],phase['token'])
        n=normalize(r,input_sha256='HANDMADE',method_seconds=300,process_seconds=r['stopped_s'])
        self.assertTrue(n['safe_retained'])
        slot={'worker':{'result':n},'error':None,'cleanup_verified':True,'wall_limit':False,
              'returncode':0,'within_process_deadline':True}
        self.assertEqual(before_post(slot,{'status':'ERROR','retained':False,'record':None,'rejected':[{'error':'FAKE_SCOPE_ERROR'}]}),
                         'RECOVERY_TECHNICAL_STOP')
