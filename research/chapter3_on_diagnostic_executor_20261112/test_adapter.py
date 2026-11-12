"""Adapter/control boundary tests without MATLAB, model builds, or physical evaluation."""
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from adapter import Runtime, decode, schedule_key
from guard import save, sha, verify_plan
from run_on import monitor_owned, terminate_owned_tree
from test_control import local_temp


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.stop=patch('subprocess.Popen',side_effect=AssertionError('No real process in tests'))
        self.stop.start();self.addCleanup(self.stop.stop)
    def test_runtime_native_start_requires_consumed_approval(self):
        with local_temp() as t:
            r=Runtime(t,t,Path(t)/'plan.json',{},t,0.)
            with self.assertRaises(FileNotFoundError):r.start_native()
            save(Path(t)/'approval_consumed.json',{'approved':False})
            save(Path(t)/'plan.json',{})
            with self.assertRaises(PermissionError):r.start_native()
    def test_second_native_request_guard_and_cap_guard(self):
        r=Runtime('.','.','plan',{},'.',0.);r._permit=lambda:None
        r.solve_attempted=True
        with self.assertRaisesRegex(RuntimeError,'already consumed'):r.solve(240.)
        r.solve_attempted=False
        with self.assertRaisesRegex(ValueError,'cap changed'):r.solve(239.)
    def test_physical_attempt_cap_prevents_third_call(self):
        r=Runtime('.','.','plan',{},'.',0.);r.evaluations=2
        with self.assertRaisesRegex(RuntimeError,'limit consumed'):r.evaluate_returned({})
    def test_decode_only_uses_original_option_prefix(self):
        i={'scenarios':[{'id':'s'}]};o=[dict(scenario_id='s',stage_instance_id='A',unit_id='CPU1',opp_id='L',start_ms='0')]
        validate=lambda i,c:{'state':'SCHEDULE_VALID_THERMAL_UNCHECKED'}
        c,_=decode(i,o,[1.,-999.,555.],1e-6,validate)
        self.assertEqual(c['scenes']['s'][0]['stage_id'],'A')
        with self.assertRaises(ValueError):decode(i,o,[.5,0.],1e-6,validate)
    def test_decoded_schedule_requires_legality(self):
        i={'scenarios':[{'id':'s'}]};o=[]
        with self.assertRaises(ValueError):decode(i,o,[1.],1e-6,lambda i,c:{'state':'INVALID'})
    def test_source_and_plan_drift_rejected(self):
        with local_temp() as t:
            root=Path(t);(root/'source.txt').write_text('original',encoding='utf-8')
            p=dict(arm='ON',slots=1,maximum_native_calls=1,retries=0,total_window_s=300.,native_MaxTime_s=240.,
                watchdog_s=380.,physical_evaluation_limit=2,formal_ABC_runs=0,model_builds=0,execution_authorized=False,
                execution_directory='work/on_diagnostic_execution_20261112',workspace_files={'source.txt':sha(root/'source.txt')},package_files={})
            save(root/'plan.json',p);save(root/'plan.identity.json',{'sha256':sha(root/'plan.json')})
            verify_plan(root/'plan.json',root,root)
            (root/'source.txt').write_text('changed',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'drift'):verify_plan(root/'plan.json',root,root)
            (root/'plan.json').write_text('{}',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'plan identity'):verify_plan(root/'plan.json',root,root)
    def test_readonly_identity_runs_even_without_vector(self):
        with local_temp() as t:
            root=Path(t);(root/'matlab').mkdir()
            r=Runtime(root,root,root/'plan',{'native_options':{'MaxTime':240}},root,0.)
            save(root/'matlab/ready.json',{'release':'2023b'})
            save(root/'matlab/request_000001.response.json',{'options':{'MaxTime':239},'x':[]})
            result=r.inspect_identity({'status':'SOLVED','exitflag':0,'x':[]})
            self.assertEqual(result['state'],'INVALID');self.assertFalse(result['checks']['native_options'])
    def test_callback_receipt_time_not_native_timestamp(self):
        with local_temp() as t,patch('adapter.time.monotonic',return_value=400.):
            r=Runtime(t,t,Path(t)/'plan',{},t,100.)
            r.capture({'event_number':1,'request_wall_seconds':1.,'values':{'lowerbound':0.}})
            self.assertEqual(r.events,[])
    def test_duplicate_callback_not_double_counted_vector_preserved(self):
        with local_temp() as t,patch('adapter.time.monotonic',return_value=110.):
            r=Runtime(t,t,Path(t)/'plan',{},t,100.)
            e={'event_number':1,'kind':'callback','x':[1.,2.]}
            r.capture(e);r.capture(e)
            self.assertEqual(len(r.events),1);self.assertEqual(r.events[0]['x'],[1.,2.])
            self.assertEqual(r.events[0]['received_elapsed_s'],10.)


class ProcessTests(unittest.TestCase):
    def test_watchdog_does_not_signal_reused_root_pid(self):
        class Gone(Exception):pass
        p=SimpleNamespace(create_time=lambda:2.)
        module=SimpleNamespace(NoSuchProcess=Gone,Process=lambda pid:p)
        result=terminate_owned_tree(module,123,1.)
        self.assertEqual(result['reason'],'ROOT_PID_REUSED_NO_SIGNAL_SENT')
    def test_controller_tracks_and_cleans_owned_survivor(self):
        now=[0.];killed=[]
        class Gone(Exception):pass
        class P:
            def __init__(self,pid):self.pid=pid
            def create_time(self):return float(self.pid)
            def is_running(self):return self.pid==2 and self.pid not in killed
            def children(self,recursive=True):return [P(2)]
            def kill(self):killed.append(self.pid)
        class Worker:
            pid=1;returncode=None
            def poll(self):
                if now[0]>=.25:self.returncode=1
                return self.returncode
        m=SimpleNamespace(NoSuchProcess=Gone,Process=P,wait_procs=lambda ps,timeout:(ps,[]))
        result=monitor_owned(Worker(),1.,0.,m,clock=lambda:now[0],sleep=lambda s:now.__setitem__(0,now[0]+s))
        self.assertEqual(killed,[2]);self.assertEqual(result['returncode'],1)
        self.assertTrue(result['complete']);self.assertEqual(result['forced_pids'],[2])
    def test_controller_watchdog_ends_stuck_worker(self):
        now=[379.9];killed=[]
        class Gone(Exception):pass
        class P:
            def __init__(self,pid):self.pid=pid
            def create_time(self):return 1.
            def is_running(self):return not killed
            def children(self,recursive=True):return []
            def kill(self):killed.append(self.pid)
        class Worker:
            pid=1;returncode=None
            def poll(self):
                if killed:self.returncode=-9
                return self.returncode
        m=SimpleNamespace(NoSuchProcess=Gone,Process=P,wait_procs=lambda ps,timeout:(ps,[]))
        result=monitor_owned(Worker(),1.,0.,m,clock=lambda:now[0],sleep=lambda s:now.__setitem__(0,now[0]+s))
        self.assertTrue(result['watchdog_expired']);self.assertEqual(killed,[1])


if __name__=='__main__':unittest.main(verbosity=2)
