"""K195 execution-chain simulations only; no process, model, solve or heat."""
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import run_once as run


class EntryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=run.RESULTS)
        self.root=Path(self.temp.name)
        self.prep=self.root/'prep'; self.prep.mkdir()
        self.out=self.root/'output'
        self.approval=self.root/'approval.json'
        self.instance={'id':'fixture_only_not_real'}; self.config={'accuracy_targets':{}}
        for name,data in [('input_instance.json',self.instance),('input_config.json',self.config)]:
            run.write_new(self.prep/name,data)
        run.write_new(self.prep/'source_compatibility.json',{'fixture_only':True})
        self.plan={'authorized':False,'execution_enabled':False,'fixture_only':True,
            'method_calls':1,'method_seconds':300,'post_calls_at_most':1,
            'post_seconds':60,'calendar_seconds':480,'source_sha256':{},
            'wrapper_sha256':{},'payload_sha256':{n:run.digest(self.prep/n)
                for n in ('input_instance.json','input_config.json')},
            'compatibility_sha256':run.digest(self.prep/'source_compatibility.json'),
            'builder_flags':dict(include_physics=True, fix_late_options=True,
                aggregate_opp_locks=True,relax_auxiliary_integrality=True,
                strengthen_energy_lower_bounds=True,prefilter_deadlines=True,
                cumulative_precedence=False,fixed_deployment=None,
                fixed_shared_deployment=None,fixed_scene_id=None,
                neighborhood_condition=None,preeliminate_closed_anchors=False),
            'spec':{'input_sha256':run.canonical(self.instance),'config_sha256':run.canonical(self.config)}}
        run.write_new(self.prep/'plan.json',self.plan)
        self.approved={'approved_by_user':True,'human_authorization_text':'PURE FIXTURE NOT ACTUAL CONSENT',
            'plan_sha256':run.digest(self.prep/'plan.json'),'output_directory':str(self.out.resolve()),
            'method_calls':1,'method_seconds':300,'post_calls_at_most':1,'post_seconds':60,'calendar_seconds':480}
        run.write_new(self.approval,self.approved)
        run.write_new(self.prep/'pure_checks.json',{'passed':True,'plan_sha256':run.digest(self.prep/'plan.json')})

    def tearDown(self): self.temp.cleanup()

    def replace(self,path,obj): path.write_text(json.dumps(obj),encoding='utf-8')

    def gate(self): return run.authorize(self.prep,self.out,self.approval,allow_fixture=True)

    def test_fixture_approval_exact_scope(self):
        self.assertTrue(self.gate()['fixture_only'])

    def test_real_launch_refuses_fixture_before_process(self):
        process=unittest.mock.Mock()
        with self.assertRaises(ValueError):run.launch(self.prep,self.out,self.approval,popen=process)
        process.assert_not_called(); self.assertFalse(self.out.exists())

    def test_missing_approval_zero_launch(self):
        self.approval.unlink()
        with self.assertRaises(FileNotFoundError): self.gate()
        self.assertFalse(self.out.exists())

    def test_wrong_plan_sha_refused(self):
        self.approved['plan_sha256']='wrong';self.replace(self.approval,self.approved)
        with self.assertRaises(ValueError):self.gate()

    def test_extra_budget_refused(self):
        self.approved['method_seconds']=301;self.replace(self.approval,self.approved)
        with self.assertRaises(ValueError):self.gate()

    def test_different_output_refused(self):
        self.approved['output_directory']=str(self.root/'other');self.replace(self.approval,self.approved)
        with self.assertRaises(ValueError):self.gate()

    def test_self_enabled_plan_refused(self):
        self.plan['authorized']=True;self.replace(self.prep/'plan.json',self.plan)
        self.approved['plan_sha256']=run.digest(self.prep/'plan.json');self.replace(self.approval,self.approved)
        with self.assertRaises(ValueError):self.gate()

    def test_input_drift_refused_before_method_claim(self):
        self.replace(self.prep/'input_instance.json',{'id':'changed'})
        with self.assertRaises(ValueError):run.method(self.prep,self.out,self.approval,engine=object())
        self.assertFalse((self.out/'method.claim.json').exists())

    def phase_request(self,*,phase='method',deadline=1480):
        self.out.mkdir()
        run.write_new(self.out/'launch.claim.json',{'plan_sha256':run.digest(self.prep/'plan.json'),
            'approval_sha256':run.digest(self.approval),'start':1000,'deadline':1480})
        run.write_new(self.out/'method.request.json',{'phase':phase,
            'plan_sha256':run.digest(self.prep/'plan.json'),'calendar_deadline':deadline})

    def test_matching_supervisor_phase_request(self):
        self.phase_request()
        with patch.object(run.time,'monotonic',return_value=1001):
            run.require_phase(self.prep,self.out,self.approval,'method',self.plan)

    def test_expired_supervisor_phase_refused(self):
        self.phase_request()
        with patch.object(run.time,'monotonic',return_value=1480):
            with self.assertRaises(ValueError):run.require_phase(self.prep,self.out,self.approval,'method',self.plan)

    def test_other_phase_calendar_request_refused(self):
        self.phase_request(phase='post',deadline=1481)
        with patch.object(run.time,'monotonic',return_value=1001):
            with self.assertRaises(ValueError):run.require_phase(self.prep,self.out,self.approval,'method',self.plan)

    def engine(self):
        observations={}
        class Budget:
            start=1000.;deadline=1300.;elapsed=1.;seconds=300.
            def check(self):pass
            def phase(self,name):return nullcontext()
        def formal(loader,out,**kwargs):
            Path(out).mkdir()
            observations['formal_kwargs']=kwargs
            budget=Budget(); config,instance=loader(budget)
            kwargs['model_builder'](instance,config,budget=budget,progress=None,
                fix_late_options=True,aggregate_opp_locks=True,
                relax_auxiliary_integrality=True,strengthen_energy_lower_bounds=True)
            return {'state':'UNRESOLVED','reason':'NO_INTEGER_CANDIDATE','safe_upper_bound_J':None}
        def builder(instance,config,**kwargs):
            observations['builder_input']=(deepcopy(instance),deepcopy(config))
            observations['builder_flags']=kwargs
            return SimpleNamespace()
        def lower(instance,none,budget):
            observations['fresh_lower_called']=True
            return {'state':'MOCK_ONLY_NOT_SCIENCE'}
        domain=SimpleNamespace(validate_model=lambda *args:{'passed':True,'fixture_only':True},
            validate_candidate=lambda *args:{'passed':True})
        audit=lambda *a,**k:{'execution':{'execution_status':'NORMAL_COMPLETION'},'usable_U_J':None}
        engine=SimpleNamespace(formal=SimpleNamespace(execute_formal_milp=formal),
            milp=SimpleNamespace(build_model=builder),bounds=SimpleNamespace(independent_lower_bound=lower),
            domain=domain,original_audit=audit)
        return engine,observations

    def test_simulated_method_passes_exact_input_flags_and_root(self):
        engine,observations=self.engine()
        self.assertEqual(run.method(self.prep,self.out,self.approval,engine=engine),0)
        self.assertEqual(observations['builder_input'],(self.instance,self.config))
        self.assertEqual(observations['formal_kwargs']['seconds'],300)
        self.assertNotIn('diagnostic_solver',observations['formal_kwargs'])
        self.assertTrue(observations['fresh_lower_called'])
        identity=run.read(self.out/'method/method_budget_identity.json')
        self.assertEqual(identity['deadline'],identity['start']+300)
        returned=run.read(self.out/'method_return.json')
        self.assertTrue(returned['fixture_only']);self.assertFalse(returned['post_eligible'])

    def test_duplicate_method_refuses_second_call(self):
        engine,_=self.engine();run.method(self.prep,self.out,self.approval,engine=engine)
        with self.assertRaises(FileExistsError):run.method(self.prep,self.out,self.approval,engine=engine)

    def test_fake_builder_cannot_drop_original_flag(self):
        engine,_=self.engine()
        original=engine.formal.execute_formal_milp
        def wrong(loader,out,**kwargs):
            kwargs['model_builder']=unittest.mock.Mock(side_effect=ValueError('flag drift'))
            return original(loader,out,**kwargs)
        engine.formal.execute_formal_milp=wrong
        self.assertEqual(run.method(self.prep,self.out,self.approval,engine=engine),2)
        self.assertTrue(run.read(self.out/'method_return.json')['errors'])

    def supervisor(self,*,post=True,late=False,watchdog=False,returncode=0,duration=None):
        calls=[];clock=[0.]
        def fake_clock():return clock[0]
        def fake_sleep(delta):clock[0]+=delta
        def popen(args,**kwargs):
            phase=args[3];calls.append(phase)
            run.write_new(self.out/(phase+'.claim.json'),{'fixture_only':True})
            if phase=='method':run.write_new(self.out/'method_return.json',{'post_eligible':post})
            class Process:
                returncode=None
                def poll(self):
                    if watchdog and self.returncode is None:return None
                    if self.returncode is None:
                        clock[0]+=duration if duration is not None else 410 if late else 1
                        self.returncode=returncode
                    return self.returncode
                def wait(self,timeout):return self.returncode
            return Process()
        def terminate(process,identity):
            process.returncode=-1
            return {'identities':[identity],'verified_closed':True,'fixture_only':True}
        with patch.object(run,'authorize',return_value=self.plan):
            result=run.launch(self.prep,self.out,self.approval,popen=popen,clock=fake_clock,
                sleep=fake_sleep,context_factory=lambda:({},lambda host:True),terminator=terminate,
                capturer=lambda proc:{'pid':999,'created':1,'fixture_only':True})
        return result,calls

    def test_supervisor_two_simulated_children_only(self):
        result,calls=self.supervisor()
        self.assertEqual(calls,['method','post']);self.assertEqual(result['research_calls'],1)
        self.assertEqual(result['post_calls'],1)

    def test_supervisor_no_post_on_no_safe(self):
        result,calls=self.supervisor(post=False)
        self.assertEqual(calls,['method']);self.assertEqual(result['post_skip'],'NO_NORMAL_COMPLETE_SAFE')

    def test_calendar_never_shortens_post_or_extends_limit(self):
        result,calls=self.supervisor(late=True)
        self.assertEqual(calls,['method']);self.assertIn('INSUFFICIENT_CALENDAR',result['post_skip'])

    def test_calendar_reserves_cleanup_after_post_watchdog(self):
        result,calls=self.supervisor(duration=400)
        self.assertEqual(calls,['method'])
        self.assertEqual(result['calendar_cleanup_reserve_s'],15)
        self.assertTrue(result['calendar_limit_respected'])

    def test_blocking_return_calendar_overrun_cannot_be_success(self):
        result,calls=self.supervisor(duration=481)
        self.assertEqual(calls,['method'])
        self.assertEqual(result['state'],'STOPPED_CALENDAR_OVERRUN')
        self.assertFalse(result['calendar_limit_respected'])

    def test_method_failure_stops_no_retry(self):
        result,calls=self.supervisor(returncode=2)
        self.assertEqual(calls,['method']);self.assertEqual(result['state'],'STOPPED')

    def test_watchdog_terminates_only_fake_owned_process(self):
        result,calls=self.supervisor(watchdog=True)
        self.assertEqual(calls,['method']);self.assertEqual(result['state'],'STOPPED')
        self.assertTrue(result['phases'][0]['watchdog_stop'])
        self.assertLessEqual(result['calendar_s'],480)

    def test_resource_gate_uses_zero_calls(self):
        with patch.object(run,'authorize',return_value=self.plan):
            result=run.launch(self.prep,self.out,self.approval,popen=unittest.mock.Mock(),
                context_factory=lambda:({},lambda host:False))
        self.assertEqual(result['research_calls'],0);self.assertFalse(self.out.exists())

    def exception_supervisor(self, failure, *, archive_failure=False):
        """Injected fake Popen only; no operating-system child is created."""
        calls=[];cleanups=[];processes=[];clock=[0.]
        safe={'state':'SAFE','safe_upper_bound_J':'1','fixture_only':True}
        original_write=run.write_new
        def writer(path,value):
            if archive_failure and Path(path).name=='terminal.json':
                raise OSError('fixture terminal storage failure')
            return original_write(path,value)
        def popen(args,**kwargs):
            phase=args[3];calls.append(phase)
            if failure=='popen':raise OSError('fixture Popen failure')
            original_write(self.out/(phase+'.claim.json'),{'fixture_only':True})
            if phase=='method':
                original_write(self.out/'preserved_safe.json',safe)
                if failure!='missing_return':original_write(self.out/'method_return.json',{'post_eligible':True})
            class Process:
                pid=999;returncode=None;polls=0
                def poll(self):
                    self.polls+=1
                    if self.returncode is not None:return self.returncode
                    if failure=='poll':raise OSError('fixture poll failure')
                    if failure=='sleep':return None
                    if failure=='wait':return 0 if self.polls==1 else None
                    self.returncode=0;return 0
                def wait(self,timeout):
                    if failure=='wait' and self.returncode is None:
                        raise run.subprocess.TimeoutExpired('fake',timeout)
                    return self.returncode
                def kill(self):
                    self.returncode=-9
            process=Process();processes.append(process);return process
        def sleep(delta):
            clock[0]+=delta
            if failure=='sleep':raise OSError('fixture sleep failure')
        def terminate(process,identity):
            cleanups.append(identity);process.returncode=-1
            return {'verified_closed':True,'identities':[identity],'fixture_only':True}
        with patch.object(run,'authorize',return_value=self.plan),patch.object(run,'write_new',side_effect=writer):
            result=run.launch(self.prep,self.out,self.approval,popen=popen,clock=lambda:clock[0],
                sleep=sleep,context_factory=lambda:({},lambda host:True),terminator=terminate,
                capturer=lambda proc:{'pid':999,'created':1,'fixture_only':True})
        return result,calls,cleanups,processes,safe

    def test_popen_failure_is_archived_without_post_or_retry(self):
        result,calls,cleanups,processes,_=self.exception_supervisor('popen')
        self.assertEqual(result['state'],'STOPPED_EXCEPTION')
        self.assertEqual(calls,['method']);self.assertFalse(cleanups);self.assertFalse(processes)
        self.assertTrue((self.out/'terminal.json').is_file())
        self.assertEqual(result['research_calls'],0)

    def test_active_poll_exception_cleans_only_fake_owned_child(self):
        result,calls,cleanups,processes,_=self.exception_supervisor('poll')
        self.assertEqual(result['state'],'STOPPED_EXCEPTION');self.assertEqual(calls,['method'])
        self.assertEqual(len(cleanups),1);self.assertEqual(cleanups[0]['pid'],999)
        self.assertEqual(processes[0].returncode,-1);self.assertEqual(result['post_calls'],0)

    def test_active_sleep_exception_is_finalized(self):
        result,calls,cleanups,processes,_=self.exception_supervisor('sleep')
        self.assertEqual(result['state'],'STOPPED_EXCEPTION');self.assertEqual(calls,['method'])
        self.assertEqual(len(cleanups),1);self.assertIsNotNone(processes[0].returncode)

    def test_wait_exception_with_active_handle_is_finalized(self):
        result,calls,cleanups,processes,_=self.exception_supervisor('wait')
        self.assertEqual(result['state'],'STOPPED_EXCEPTION');self.assertEqual(calls,['method'])
        self.assertEqual(len(cleanups),1);self.assertIsNotNone(processes[0].returncode)

    def test_missing_method_return_stops_before_post(self):
        result,calls,cleanups,processes,_=self.exception_supervisor('missing_return')
        self.assertEqual(result['state'],'STOPPED_EXCEPTION');self.assertEqual(calls,['method'])
        self.assertFalse(cleanups);self.assertEqual(processes[0].returncode,0)
        self.assertEqual(result['post_calls'],0)

    def test_already_saved_safe_evidence_is_not_cleared_on_supervisor_error(self):
        result,_,_,_,safe=self.exception_supervisor('poll')
        self.assertEqual(result['state'],'STOPPED_EXCEPTION')
        self.assertEqual(run.read(self.out/'preserved_safe.json'),safe)

    def test_terminal_storage_failure_happens_after_owned_cleanup(self):
        result,calls,cleanups,processes,safe=self.exception_supervisor('poll',archive_failure=True)
        self.assertEqual(result['state'],'STOPPED_EXCEPTION');self.assertEqual(calls,['method'])
        self.assertEqual(len(cleanups),1);self.assertEqual(processes[0].returncode,-1)
        self.assertTrue((self.out/'terminal_archive_failure.json').is_file())
        self.assertEqual(run.read(self.out/'preserved_safe.json'),safe)

    def test_creation_time_capture_uses_only_supplied_fake_pid(self):
        proc=SimpleNamespace(pid=123,poll=lambda:None)
        fake_process=SimpleNamespace(pid=123,create_time=lambda:456.0)
        factory=unittest.mock.Mock(return_value=fake_process)
        with patch.dict(sys.modules,psutil=SimpleNamespace(Process=factory)):
            identity=run.capture_owned(proc)
        factory.assert_called_once_with(123)
        self.assertEqual(identity,{'pid':123,'created':456.0,'state':'CAPTURED'})

    def test_reused_pid_is_never_terminated(self):
        proc=SimpleNamespace(pid=123,poll=lambda:None)
        parent=unittest.mock.Mock();parent.create_time.return_value=789.0
        fake_psutil=SimpleNamespace(Process=unittest.mock.Mock(return_value=parent),
            NoSuchProcess=type('NoSuchProcess',(Exception,),{}))
        with patch.dict(sys.modules,psutil=fake_psutil):
            result=run.stop_owned(proc,{'pid':123,'created':456.0})
        self.assertEqual(result['reason'],'ROOT_PID_REUSED_NOT_KILLED')
        self.assertFalse(result['attempted']);parent.children.assert_not_called()
        parent.terminate.assert_not_called();parent.kill.assert_not_called()

    def test_uncaptured_identity_uses_fake_popen_handle_only(self):
        proc=unittest.mock.Mock(pid=123,returncode=None)
        proc.poll.return_value=None
        proc.kill.side_effect=lambda:setattr(proc,'returncode',-9)
        fake_psutil=SimpleNamespace(Process=unittest.mock.Mock())
        with patch.dict(sys.modules,psutil=fake_psutil):result=run.stop_owned(proc,None)
        fake_psutil.Process.assert_not_called();proc.kill.assert_called_once()
        self.assertTrue(result['verified_closed']);self.assertTrue(result['descendant_cleanup_unverified'])


if __name__=='__main__':unittest.main(verbosity=2)
