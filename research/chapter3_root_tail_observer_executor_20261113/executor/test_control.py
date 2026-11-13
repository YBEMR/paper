"""Synthetic receipts/clocks/processes only. Running this file never starts MATLAB."""
import copy,json,os,sys,tempfile,types,unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch
from scope import ScopeLedger
from control import execute
from evidence import StopWindow,progress
from budget_policy import ABC_DYNAMIC
from dispatch import allocate_at_publication
from observation import analyze_profile,grade,OwnedSampler,HISTORY_LIMIT
from guard import verify_approval,claim_once,PROTOCOL,ARM

def good(**kw):
    return dict(dict(cleanup={'complete':True},identity_after={'state':'VERIFIED'},fault_scope=None,affected_arms=[]),**kw)

def safe(t=20,e=('1.08','1.09')):
    return dict(state='SAFE',rankable_energy=True,completed_at_elapsed_s=t,weighted_energy_J=list(e),
        scenes={s:dict(state='SAFE',complete=True) for s in ('AB','AC')})

def profile_fixture():
    import numpy as np
    # Three marker functions and an opaque core; chronological, balanced events.
    table=[dict(FunctionName='solve_model>'+n,FileName='native/solve_model.m',Type='M-function',TotalTime=1.,PartialData=False)
           for n in ('d279_begin_marker','d279_root_marker','d279_end_marker','opaque')]
    events=[(0,1,100),(1,1,100.001),(0,4,101),(0,2,110),(1,2,110.001),(1,4,120),(0,3,121),(1,3,121.001)]
    history=np.array([[kind,f,int(t),(t-int(t))*1e6] for kind,f,t in events]).T
    obs={'anchors':[dict(label=l,before_s=t-.002,inside_s=t+.0005,after_s=t+.002)
                     for l,t in [('begin',.01),('root',10.01),('end',21.01)]]}
    return dict(FunctionTable=table,FunctionHistory=history),obs

class FakeRuntime:
    def __init__(self,**changes):
        self.arm=ARM;self.elapsed=0.;self.scene_count=2;self.events=[];self.objective_reference='1.085';self.objective_lower_bound='0'
        self.calls=[];self.start_time=40;self.prepare_time=10;self.solve_time=540;self.finish_time=560;self.freeze_time=565
        self.native=dict(status='SOLVED',budget_valid=True,accepted_for_evaluation=True,x=[1,0])
        self.identity='VERIFIED';self.admitted=True;self.same=True;self.energy=('1.08','1.09');self.clean=True;self.source=True
        self.validation_time=545;self.eval_time=548
        self.__dict__.update(changes)
    def check(self):
        if self.elapsed>=600: raise StopWindow()
    def prepare(self): self.elapsed=self.prepare_time;self.calls.append('prepare')
    def evaluate_initial(self): self.calls.append('initial');return safe(self.elapsed)
    def start_native(self): self.elapsed=self.start_time;self.calls.append('start')
    def solve(self,_): self.elapsed=self.solve_time;self.calls.append('solve');return self.native
    def inspect_identity(self,n): return {'state':self.identity}
    def validate_returned(self,x):
        self.elapsed=self.validation_time;self.calls.append('validate')
        return dict(state='ADMITTED' if self.admitted else 'REJECTED',candidate={},same_initial=self.same)
    def evaluate_returned(self,c): self.elapsed=self.eval_time;self.calls.append('final');return safe(self.elapsed,self.energy)
    def finish_observation(self,n):
        self.elapsed=max(self.elapsed,self.finish_time);self.check();self.calls.append('observation')
        p,o=profile_fixture()
        return dict(response_timely=self.solve_time<550,profile_packet_timely=self.solve_time<550,root_observed=True,
            native_settings_verified=self.identity=='VERIFIED',profile_settings_verified=True,
            sampler=dict(complete=True,sample_count=20),profile_analysis=analyze_profile(p,o))
    def freeze(self,r):
        self.elapsed=max(self.elapsed,self.freeze_time);self.check();self.calls.append('freeze');return dict(sha256='mock',completed_at_elapsed_s=self.elapsed)
    def close(self): self.calls.append('close');self.elapsed+=5;return dict(complete=self.clean)
    def verify_after(self): self.calls.append('verify');return dict(state='VERIFIED' if self.source else 'INVALID')

class ScopeTests(unittest.TestCase):
    def new(self): return ScopeLedger(['C_repeat','B_repeat','C_noheur'],{a:{'model_arm':m} for a,m in [('C_repeat','C'),('B_repeat','B'),('C_noheur','C')]})
    def test_c_then_b_cannot_restore_c(self):
        s=self.new();self.assertEqual(s.consume('C_repeat',good(fault_scope='FEATURE',affected_arms=['C'])),['B_repeat'])
        self.assertEqual(s.consume('B_repeat',good()),[]);self.assertEqual(s.snapshot()['blocked'],['C'])
    def test_trial_local_does_not_block_same_model(self):
        s=self.new();s.consume('C_repeat',good(fault_scope='TRIAL'));self.assertEqual(s.consume('B_repeat',good()),['C_noheur'])
    def test_support_scope_covers_b_and_c(self): self.assertEqual(self.new().consume('C_repeat',good(fault_scope='FEATURE',affected_arms=['B','C'])),[])
    def test_timeout_does_not_block(self): self.assertEqual(self.new().consume('C_repeat',good()),['B_repeat','C_noheur'])
    def test_all_is_irreversible(self):
        s=self.new();s.consume('C_repeat',good(fault_scope='ALL'));self.assertEqual(s.consume('B_repeat',good()),[])
    def test_cleanup_stops_everything(self): self.assertEqual(self.new().consume('C_repeat',good(cleanup={'complete':False})),[])
    def test_identity_stops_everything(self): self.assertEqual(self.new().consume('C_repeat',good(identity_after={'state':'INVALID'})),[])
    def test_controller_failure_stops_everything(self): self.assertEqual(self.new().consume('C_repeat',good(),False),[])
    def test_double_consumption_rejected(self):
        s=self.new();s.consume('C_repeat',good())
        with self.assertRaises(ValueError): s.consume('C_repeat',good())
    def test_unknown_or_unspecified_feature_scope_fails_closed(self):
        for r in [good(fault_scope='UNKNOWN'),good(fault_scope='FEATURE'),good(affected_arms=['unknown'])]:
            self.assertEqual(self.new().consume('C_repeat',r),[])
    def test_counterfactual_old_bug_is_reproduced_without_importing_old_executor(self):
        def old_filter(completed,current):
            return [a for a in ['C_repeat','B_repeat','C_noheur'] if a not in completed and
                {'C_repeat':'C','B_repeat':'B','C_noheur':'C'}[a] not in current.get('affected_arms',[])]
        self.assertEqual(old_filter(['C_repeat'],{'affected_arms':['C']}),['B_repeat'])
        self.assertEqual(old_filter(['C_repeat','B_repeat'],{}),['C_noheur'])

class LifecycleTests(unittest.TestCase):
    def test_normal_same_safe_is_not_improvement(self):
        f=FakeRuntime();r=execute(f);self.assertTrue(r['returned_complete_SAFE']);self.assertFalse(r['scientific_success'])
        self.assertTrue(r['observability']['O1']);self.assertEqual(r['observability']['O2'],'NOT_ESTABLISHED')
        self.assertEqual(f.calls.count('solve'),1);self.assertLess(f.calls.index('freeze'),f.calls.index('close'))
    def test_slow_start_blocks_call(self):
        f=FakeRuntime(start_time=511);r=execute(f);self.assertNotIn('solve',f.calls);self.assertEqual(r['native_request_attempts'],0)
    def test_slow_prepare_blocks_session(self):
        f=FakeRuntime(prepare_time=511);execute(f);self.assertNotIn('start',f.calls)
    def test_timeout_has_no_vector_or_retry(self):
        f=FakeRuntime(native=dict(status='BUDGET_EXHAUSTED',budget_valid=False,x=[]),solve_time=550);r=execute(f)
        self.assertNotIn('final',f.calls);self.assertEqual(f.calls.count('solve'),1);self.assertIsNone(r['fault_scope'])
    def test_empty_return_has_no_thermal_validation(self):
        f=FakeRuntime(native=dict(status='SOLVED',budget_valid=True,accepted_for_evaluation=False,x=[]));execute(f);self.assertNotIn('final',f.calls)
    def test_rejected_vector(self):
        f=FakeRuntime(admitted=False);r=execute(f);self.assertEqual(r['terminal_state'],'RETURNED_VECTOR_REJECTED');self.assertNotIn('final',f.calls)
    def test_different_safe_strict_improvement(self):
        r=execute(FakeRuntime(same=False,energy=('1.02','1.03')));self.assertTrue(r['scientific_success'])
    def test_different_equal_energy_not_improvement(self): self.assertFalse(execute(FakeRuntime(same=False))['scientific_success'])
    def test_same_schedule_disjoint_energy_conflict(self):
        r=execute(FakeRuntime(energy=('1.02','1.03')));self.assertEqual(r['fault_scope'],'ALL');self.assertFalse(r['scientific_success'])
    def test_bound_conflict_is_trial_local(self):
        f=FakeRuntime(events=[dict(received_elapsed_s=100,values={'lowerbound':2.})]);r=execute(f)
        self.assertEqual(r['fault_scope'],'TRIAL');self.assertFalse(r['evidence_integrity'])
    def test_late_bound_not_credited(self):
        f=FakeRuntime(events=[dict(received_elapsed_s=550,values={'lowerbound':2.})]);self.assertFalse(execute(f)['native_bound_conflict'])
    def test_source_drift_stops(self):
        r=execute(FakeRuntime(identity='INVALID'));self.assertEqual(r['fault_scope'],'ALL');self.assertFalse(r['observability']['O0'])
    def test_cleanup_failure_revokes(self):
        r=execute(FakeRuntime(same=False,energy=('1.02','1.03'),clean=False));self.assertFalse(r['scientific_success']);self.assertEqual(r['fault_scope'],'ALL')
    def test_after_identity_revokes(self): self.assertFalse(execute(FakeRuntime(source=False))['observability']['O0'])
    def test_archive_at_deadline_rejects(self):
        r=execute(FakeRuntime(freeze_time=600));self.assertFalse(r['scientific_archive_timely']);self.assertFalse(r['observability']['O0'])
    def test_observation_overrun_rejects(self): self.assertFalse(execute(FakeRuntime(finish_time=601))['scientific_archive_timely'])
    def test_thermal_overrun_rejects(self): self.assertFalse(execute(FakeRuntime(eval_time=601))['scientific_archive_timely'])

class BudgetAndAuthorizationTests(unittest.TestCase):
    def test_exact_boundary(self):
        self.assertEqual(ABC_DYNAMIC.allocate(510)['native_seconds'],30);self.assertFalse(ABC_DYNAMIC.allocate(510.001)['can_submit'])
    def test_quota_at_publication_after_serialization(self):
        rows=[];bridge=types.SimpleNamespace(_json=lambda p,v:rows.append(v));clock=[80.1]
        with allocate_at_publication(bridge,lambda:clock[0],lambda a:None): bridge._json(Path('x.request.json'),{'remaining_s':470})
        self.assertEqual(rows[0]['solver_max_time_s'],459)
    def test_quota_crossed_while_recording_no_dispatch(self):
        from evidence import InsufficientNativeBudget
        rows=[];clock=[80.999];bridge=types.SimpleNamespace(_json=lambda p,v:rows.append(v))
        def delay(a): clock[0]=81.001
        with self.assertRaises(InsufficientNativeBudget):
            with allocate_at_publication(bridge,lambda:clock[0],delay): bridge._json(Path('x.request.json'),{'remaining_s':470})
        self.assertEqual(rows,[])
    def test_prior_consumed_approval_cannot_authorize(self):
        with self.assertRaises(PermissionError): verify_approval({'approved':True,'protocol':'full-R1-mechanism-trials-v1'},'new')
    def test_unapproved_template_cannot_authorize(self):
        with self.assertRaises(PermissionError): verify_approval({'approved':False},'new')
    def test_exact_approval_requires_user_reference(self):
        a=dict(approved=True,protocol=PROTOCOL,plan_sha256='new',arms=[ARM],maximum_native_calls=1,maximum_MATLAB_sessions=1,total_window_s=600,response_cutoff_s=550,retries=0)
        with self.assertRaises(PermissionError): verify_approval(a,'new')
        a['user_decision_reference']='SYNTHETIC_TEST_ONLY';verify_approval(a,'new')
    def test_claim_is_one_use(self):
        with tempfile.TemporaryDirectory() as t:
            claim_once(Path(t),{'execution_directory':'trial'},{'mock':True})
            with self.assertRaises(FileExistsError): claim_once(Path(t),{'execution_directory':'trial'},{'mock':True})

class ProfileTests(unittest.TestCase):
    def test_cross_clock_bracket_uncertainty(self):
        from observation import request_clock_alignment
        self.assertEqual(request_clock_alignment([{'received_elapsed_s':110.01,'request_wall_seconds':10}],100)['state'],'BOUNDED')
        self.assertEqual(request_clock_alignment([{'received_elapsed_s':111,'request_wall_seconds':10}],100)['state'],'UNKNOWN')
    def test_complete_aligned_history(self):
        p,o=profile_fixture();a=analyze_profile(p,o);self.assertTrue(a['history_complete']);self.assertEqual(a['alignment'],'BOUNDED')
    def test_no_timestamp_history(self):
        p,o=profile_fixture();p['FunctionHistory']=p['FunctionHistory'][:2];self.assertFalse(analyze_profile(p,o)['history_complete'])
    def test_history_capacity_truncation(self):
        import numpy as np
        p,o=profile_fixture();p['FunctionHistory']=np.tile(p['FunctionHistory'][:,:2],(1,HISTORY_LIMIT//2));p['FunctionHistory'][2,:]=100;p['FunctionHistory'][3,:]=0
        self.assertFalse(analyze_profile(p,o)['history_complete'])
    def test_partial_function_data(self):
        p,o=profile_fixture();p['FunctionTable'][0]['PartialData']=True;self.assertFalse(analyze_profile(p,o)['history_complete'])
    def test_clock_jump(self):
        p,o=profile_fixture();o['anchors'][-1]['before_s']+=1;o['anchors'][-1]['inside_s']+=1;o['anchors'][-1]['after_s']+=1
        self.assertEqual(analyze_profile(p,o)['alignment'],'UNKNOWN')
    def test_missing_root_marker(self):
        p,o=profile_fixture();o['anchors'].pop(1);self.assertEqual(analyze_profile(p,o)['alignment'],'UNKNOWN')
    def test_bad_index(self):
        p,o=profile_fixture();p['FunctionHistory'][1,0]=999;self.assertEqual(analyze_profile(p,o)['reason'],'BAD_FUNCTION_INDEX')
    def test_nonnested_history(self):
        p,o=profile_fixture();p['FunctionHistory'][1,4]=4;self.assertFalse(analyze_profile(p,o)['history_complete'])
    def test_snapshot_open_call_outside_markers_is_not_false_truncation(self):
        import numpy as np
        p,o=profile_fixture();p['FunctionHistory']=np.column_stack([p['FunctionHistory'],[0,4,122,0]])
        self.assertTrue(analyze_profile(p,o)['history_complete'])
    def test_same_marker_name_wrong_source_rejected(self):
        p,o=profile_fixture();p['FunctionTable'][0]['FileName']='untrusted.m'
        self.assertEqual(analyze_profile(p,o)['alignment'],'UNKNOWN')
    def test_opaque_core_never_becomes_O2(self):
        p,o=profile_fixture();g=grade(dict(profile_analysis=analyze_profile(p,o),sampler=dict(complete=True,sample_count=10),response_timely=True,root_observed=True,
            profile_packet_timely=True,profile_settings_verified=True,native_settings_verified=True),True,True,True)
        self.assertTrue(g['O2_review_eligible']);self.assertEqual(g['O2'],'NOT_ESTABLISHED');self.assertFalse(g['targeted_intervention_eligible'])
    def test_late_profile_disqualifies_O0(self):
        self.assertFalse(grade(dict(response_timely=True,profile_packet_timely=False),True,True,True)['O0'])

class SamplerTests(unittest.TestCase):
    def module(self,reused=False):
        class Missing(Exception): pass
        class Proc:
            def __init__(self,pid): self.pid=pid
            def create_time(self): return 2 if reused else 1
            def children(self,recursive=True): return []
            def cpu_times(self): return types.SimpleNamespace(user=1,system=2)
            def memory_info(self): return types.SimpleNamespace(rss=3,vms=4)
            def io_counters(self): return types.SimpleNamespace(read_bytes=5,write_bytes=6)
        return types.SimpleNamespace(Process=Proc,NoSuchProcess=Missing)
    def test_resources_and_buffered_log_arrival_not_stage_time(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'matlab').mkdir();clock=[1.]
            s=OwnedSampler(p,0,self.module(),clock=lambda:clock[0]);s.sample()
            (p/'matlab/matlab.log').write_bytes(b'cut summary\nD279_NATIVE_END\n');clock[0]=30;s.sample();r=s.stop()
            self.assertTrue(r['complete']);self.assertTrue(r['log_native_end_seen']);self.assertEqual(r['log_arrivals'][0]['received_elapsed_s'],30)
    def test_pid_reuse_is_error_without_signal(self):
        with tempfile.TemporaryDirectory() as t:
            s=OwnedSampler(t,0,self.module(),clock=lambda:1.);s.pm=self.module(True);s.sample();self.assertFalse(s.stop()['complete'])
    def test_no_log_bytes_after_deadline(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'matlab').mkdir();(p/'matlab/matlab.log').write_bytes(b'D279_NATIVE_END');clock=[1.]
            s=OwnedSampler(p,0,self.module(),clock=lambda:clock[0]);clock[0]=600;s.sample();self.assertEqual(s.stop()['log_bytes'],0)
    def test_log_overflow_explicit(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'matlab').mkdir();(p/'matlab/matlab.log').write_bytes(b'a'*128)
            s=OwnedSampler(p,0,self.module(),clock=lambda:1.)
            with patch('observation.LOG_LIMIT',64):
                s.sample();r=s.stop()
            self.assertTrue(r['log_truncated']);self.assertEqual(r['log_bytes'],64)

class StaticTests(unittest.TestCase):
    def test_native_one_call_only_display_option_changed(self):
        p=Path(__file__).parent;s=(p/'native/solve_model.m').read_text()
        self.assertEqual(s.count('= intlinprog('),1);self.assertIn("'Display','iter'",s)
        self.assertIn("opts.Heuristics = 'none'",s);self.assertNotIn('iter-detailed',s)
        self.assertEqual(s.count("profileData=profile('info')"),1)
        self.assertNotIn('profileData=',s[s.index('function stop = callback'):s.index('function publish')])
        self.assertIn('Exactly one request',s)
    def test_runtime_has_no_build_transform_or_other_solver_call(self):
        import ast
        tree=ast.parse((Path(__file__).parent/'runtime.py').read_text())
        forbidden={'build','build_model','transform','verify_equivalence','linprog','milp','intlinprog','complete_initial_point','iter_initial_candidates'}
        names=[getattr(n.func,'attr',getattr(n.func,'id','')) for n in ast.walk(tree) if isinstance(n,ast.Call)]
        self.assertFalse(forbidden.intersection(names))
    def test_coordinator_consumes_persistent_scope(self):
        s=(Path(__file__).parent/'run_observation.py').read_text()
        self.assertIn('scope=ScopeLedger(',s);self.assertIn('scope.consume(arm,receipt,intact)',s);self.assertNotIn('next_arms(',s)

if __name__=='__main__':
    # Hard test fence: no process launch or OS command path is available.
    with patch('subprocess.Popen',side_effect=AssertionError('TEST FORBIDS PROCESS LAUNCH')),patch('os.system',side_effect=AssertionError('TEST FORBIDS OS COMMAND')):
        import test_adapter
        suite=unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(test_adapter))
        r=unittest.TextTestRunner(verbosity=2).run(suite)
    result=dict(tests=r.testsRun,failures=len(r.failures),errors=len(r.errors),passed=r.wasSuccessful(),
        scope='Synthetic control tests, no scientific execution',
        scientific_calls=dict(MATLAB_sessions=0,MILP=0,LP=0,full_R1_builds=0,complete_evaluations=0))
    out=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).with_name('control_test_result.json')
    out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if r.wasSuccessful() else 1)
