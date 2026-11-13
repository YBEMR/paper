"""D284 pure controls: fresh science wiring, cumulative scopes, nested process ownership."""
import ast,copy,io,json,os,subprocess,sys,time,types,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from scipy import sparse
from core import *
from batch import dispatch,accumulate,read_terminal
from science import Science
from representation import flags
from test_control import FakeClock,evaluation,Tests as LegacyTests
from windows_job import Job

OUT=None
class FakeExhausted(Exception):pass
class FakeBackend:
    instances=[]
    def __init__(self,root,clock):
        self.clock=clock;self.budget=types.SimpleNamespace();self.exhausted=FakeExhausted
        self.log=[];self.instances.append(self);self.validate=lambda *a:dict(state='SCHEDULE_VALID_THERMAL_UNCHECKED')
    def step(self,name,seconds=1):self.log.append(name);self.clock.t+=seconds
    def build(self,instance,config,base,arm):
        self.step('build:'+arm,75);self.arm=arm
        options=[dict(scenario_id=s,stage_instance_id='stage',unit_id='CPU1',opp_id='H',start_ms='0') for s in ('AB','AC')]
        return types.SimpleNamespace(options=options,summary=lambda:dict(synthetic=True,arm=arm)),{}
    def reduction(self,*a):self.step('reduction',20);return dict(passed=True)
    def candidates(self,instance,**kw):
        self.step('candidates')
        yield dict(status='COMPLETE_LEGAL_CANDIDATE',candidate=candidate())
    def evaluate(self,*a,**kw):self.step('evaluate',2);return evaluation()
    def complete(self,*a):self.step('complete');return dict(x0=np.array([1.,1.,.25,0.]))
    def export(self,model,x0):
        self.step('export',3)
        return dict(c=np.array([0.,0.,1.,0.]),A=sparse.csr_matrix([[1.,1.,0.,0.]]),b=np.array([2.]),
                    Aeq=sparse.csr_matrix([[0.,0.,1.,0.]]),beq=np.array([.25]),
                    lb=np.array([0.,0.,0.,0.]),ub=np.array([1.,1.,1.,1.]),intcon=np.array([0,1]),x0=x0)
    def transform(self,old,gates):self.step('transform',10);return copy.deepcopy(old),dict(checks={'synthetic_identity':True})
    def archive(self,*a):self.step('archive',5)

def candidate():
    return dict(scenes={s:[dict(stage_id='stage',unit='CPU1',opp='H',start_ms='0')] for s in ('AB','AC')})
def record(outcome='TIME_LIMIT',scope='THIS_RUN',affected=(),cleanup=True,reasons=()):
    return dict(outer_cleanup_ok=cleanup,receipt=dict(outcome=dict(outcome=outcome,stop_scope=scope,affected_arms=list(affected),reasons=list(reasons))),supervisor_error=None)

class Tests(unittest.TestCase):
    def setUp(self):
        self.out=OUT/self._testMethodName;self.out.mkdir();self.clock=FakeClock()
    def fixture(self,backend=FakeBackend,arm='A'):
        root=self.out/'root';d=root/'work/stable_expression/full';d.mkdir(parents=True)
        instance=dict(scenarios=[dict(id=s) for s in ('AB','AC')])
        save(d/'input_instance.json',instance);save(d/'input_config.json',dict(accuracy_targets={'artificial':True}))
        out=self.out/arm;out.mkdir()
        plan=dict(input_identity=digest(instance),initial_candidate_identity=digest(candidate()),baseline_flags={})
        return Science(root,plan,out,self.clock,backend),plan
    def test_fresh_wiring_all_costs_before_quota(self):
        s,p=self.fixture();s.prepare()
        self.assertEqual(s.model_builds,1);self.assertEqual(s.evaluations,1)
        self.assertEqual(s.backend.log,['build:A','reduction','candidates','evaluate','complete','export','transform','archive'])
        self.assertEqual(quota(self.clock.elapsed),413);self.assertIs(s.evaluate_initial(),s.initial_evaluation)
        self.assertEqual(s.evaluations,1);self.assertTrue(s.initial_admission['passed'])
    def test_fresh_science_through_fake_native_final_SAFE(self):
        from native import Native,Events
        from fake_api import FakeModel,api
        from worker import run_pipeline
        s,p=self.fixture();out=s.out
        dll=out/'fake_dll.txt';dll.write_text('CONTROL ONLY')
        p.update(parameter_baseline={'parameters.timelimit':1e75,'parameters.threads':0},parameter_overrides={'threads':1,'timelimit':'N(t)'},
            native_runtime=dict(cplex_version='FAKE_CONTROL',dll_path=str(dll),dll_sha256=sha(dll)),
            historical_common_energy_J=dict(lower='1.084',upper='1.086'),bound_objective_consistency_tolerance=1e-7)
        m=FakeModel();m.vector=np.array([1.,1.,.25,0.]);events=Events(out,self.clock)
        n=Native(api(m),p,out,self.clock,events);solve=n.solve_once
        def responded(h):
            r=solve(h);save(out/'response_ack.json',receive_response(out,self.clock,h));return r
        n.solve_once=responded
        with patch('native.loaded_dll',return_value=str(dll)):r=run_pipeline(s,n,events,self.clock,out,p,'h')
        events.close()
        self.assertEqual(r['outcome'],'COMMON_INITIAL_RETURNED_SAFE');self.assertEqual(r['full_build_attempts'],1)
        self.assertEqual(r['solve_attempts'],1);self.assertEqual(r['complete_evaluation_attempts'],2)
        self.assertEqual(read(out/'allocation.json')['native_seconds'],413)
    def test_real_three_independent_controller_processes_with_fake_receipts(self):
        from batch import launch_arm
        here=self.out/'fake_executor';here.mkdir();batch=self.out/'batch';batch.mkdir()
        script='''import argparse,json,os,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1] if False else REPLACE)
from core import read,save,sha
p=argparse.ArgumentParser();p.add_argument('--arm');p.add_argument('--batch');p.add_argument('--t0',type=float)
a,_=p.parse_known_args();b=Path(a.batch);claim=read(b/(a.arm+'_launch.json'))
assert sys.stdin.readline().strip()=='D284_ARM_GO '+claim['nonce']
o=b/a.arm;o.mkdir();save(o/'controller_receipt.json',dict(plan_sha256='h',synthetic=True,pid=os.getpid(),outcome=dict(outcome='TIME_LIMIT',stop_scope='THIS_RUN',reasons=[],strict_success=False,scientific_snapshot_accepted=True)))
save(o/'controller_completion.json',dict(within_method_window=True,after_receipt_and_hash_elapsed_s=time.monotonic()-a.t0,receipt_sha256=sha(o/'controller_receipt.json')))
'''.replace('REPLACE',repr(str(Path(__file__).parent.resolve())))
        (here/'controller.py').write_text(script,encoding='utf-8')
        plan=dict(native_runtime=dict(python=sys.executable),limits=dict(job_and_process_hard_commit_bytes=128*1024*1024,parent_private_bytes=128*1024*1024))
        rows=[launch_arm(arm,self.out,here,here/'fake.json','h',plan,batch,here/'fakeapproval.json',shared_setup_s=1.5) for arm in ('A','B','C')]
        self.assertTrue(all(r['outer_cleanup_ok'] and not r['supervisor_error'] for r in rows),rows)
        self.assertEqual(len({r['receipt']['pid'] for r in rows}),3)
        self.assertTrue(all(r['actual_arm_wall_including_outer_cleanup_s']>0 for r in rows))
        self.assertTrue(all(r['method_elapsed_including_shared_setup_s']-r['actual_arm_wall_including_outer_cleanup_s']>1.49 for r in rows))
    def test_outer_archive_cost_revokes_after_600(self):
        from batch import persist_arm
        save(self.out/'A_launch.json',dict(start_monotonic=0))
        r=record();r['receipt']['outcome'].update(strict_success=True,scientific_snapshot_accepted=True)
        with patch('batch.time.monotonic',return_value=600.1):persist_arm(self.out,'A',r,[])
        self.assertFalse(r['receipt']['outcome']['strict_success']);self.assertTrue((self.out/'A_outer_budget_invalidated.json').exists())
    def test_groups_have_private_build_init_cert_and_evaluation(self):
        seen=[]
        for arm in ('A','B','C'):
            root=self.out/arm;root.mkdir()
            instance=dict(scenarios=[dict(id=s) for s in ('AB','AC')])
            full=root/'work/stable_expression/full';full.mkdir(parents=True)
            save(full/'input_instance.json',instance);save(full/'input_config.json',dict(accuracy_targets={}))
            out=root/arm;out.mkdir()
            s=Science(root,dict(input_identity=digest(instance),initial_candidate_identity=digest(candidate()),baseline_flags={}),out,FakeClock(),FakeBackend)
            s.prepare();seen.append(s.backend)
        self.assertEqual(len({id(x) for x in seen}),3)
        self.assertEqual([x.log[0] for x in seen],['build:A','build:B','build:C'])
        self.assertTrue(all(x.log.count('evaluate')==1 and x.log.count('transform')==1 for x in seen))
    def test_original_switches_only(self):
        base=dict(x=3)
        self.assertEqual(flags(base,'A'),dict(x=3,propagate_support=False,prune_joint_states=False))
        self.assertEqual(flags(base,'B'),dict(x=3,propagate_support=True,prune_joint_states=False))
        self.assertEqual(flags(base,'C'),dict(x=3,propagate_support=True,prune_joint_states=True))
    def test_fresh_projection_failure_no_native(self):
        class Bad(FakeBackend):
            def transform(self,old,g):return old,dict(checks={'bad':False})
        s,p=self.fixture(Bad)
        with self.assertRaises(IntegrityError):s.prepare()
    def test_fresh_initial_identity_failure(self):
        s,p=self.fixture();p['initial_candidate_identity']='wrong'
        with self.assertRaises(IntegrityError):s.prepare()
        self.assertNotIn('complete',s.backend.log)
    def test_no_rebuild(self):
        s,p=self.fixture();s.prepare()
        with self.assertRaises(IntegrityError):s.prepare()
    def test_slow_build_exhaustion_is_window_not_infeasible(self):
        class Slow(FakeBackend):
            def build(self,*a):raise FakeExhausted('wall_time_limit')
        s,p=self.fixture(Slow)
        with self.assertRaises(WindowExpired):s.prepare()
    def test_no_saved_scientific_reuse(self):
        source=(Path(__file__).parent/'science.py').read_text()
        self.assertNotIn('loadmat',source);self.assertNotIn('mechanism_trials',source)
        self.assertNotIn('cplex_C_scientific_execution',source)
    def test_timeout_and_no_candidate_continue_all(self):
        calls=[];states=['TIME_LIMIT','NO_FINAL_NATIVE_VECTOR','INSUFFICIENT_NATIVE_BUDGET']
        r=dispatch(lambda a:(calls.append(a),record(states[len(calls)-1]))[1])
        self.assertEqual(calls,['A','B','C']);self.assertEqual(r['blocked_arms'],[])
    def test_cumulative_C_stop_survives_B_timeout(self):
        calls=[]
        def launch(a):calls.append(a);return record('REDUCTION_CERTIFICATE_ERROR',affected=['C']) if a=='A' else record()
        r=dispatch(launch);self.assertEqual(calls,['A','B']);self.assertTrue(r['arms']['C']['skipped'])
    def test_cumulative_support_stop_skips_B_and_C(self):
        calls=[]
        r=dispatch(lambda a:(calls.append(a),record('REDUCTION_CERTIFICATE_ERROR',affected=['B','C']))[1])
        self.assertEqual(calls,['A']);self.assertEqual(r['blocked_arms'],['B','C'])
    def test_global_stop_cannot_be_cleared_counterfactually(self):
        b=accumulate(set(),'A',record(scope='GLOBAL'))
        self.assertEqual(accumulate(b,'B',record()),set('ABC'))
    def test_cleanup_failure_global(self):
        r=dispatch(lambda a:record(cleanup=False));self.assertEqual(r['blocked_arms'],list('ABC'))
    def test_identity_and_bound_conflict_global(self):
        for outcome in ('IDENTITY_OR_CORRECTNESS_ERROR','BOUND_CONFLICT','LICENSE_ERROR'):
            self.assertEqual(accumulate(set(),'A',record(outcome)),set('ABC'))
    def test_candidate_rejection_and_memory_limit_continue(self):
        for outcome in ('FINAL_VECTOR_REJECTED','NATIVE_MEMORY_LIMIT','FINAL_NOT_COMPLETE_SAFE'):
            self.assertEqual(accumulate(set(),'A',record(outcome)),set())
    def test_unknown_scope_fail_closed(self):
        self.assertEqual(accumulate(set(),'A',record('REDUCTION_CERTIFICATE_ERROR',affected=['Z'])),set('ABC'))
    def test_prior_D283_approval_rejected(self):
        with self.assertRaises(PermissionError):authorize(dict(protocol='D283-CPLEX-one-solve-approval-v1',decision='APPROVE'),'h')
    def test_new_ABC_approval_fields(self):
        a=dict(protocol='D284-CPLEX-fresh-ABC-approval-v1',decision='APPROVE',plan_sha256='h',
               maximum_solve_calls=3,maximum_solve_calls_per_arm=1,arms=list('ABC'),total_window_s=600,response_cutoff_s=550,
               retries=0,scope='FRESH_FULL_R1_CPLEX_ABC_ONCE',approval_id='synthetic',user_message_reference='CONTROL',frozen_commit='a'*40)
        self.assertTrue(authorize(a,'h'))
        a['maximum_solve_calls_per_arm']=2
        with self.assertRaises(PermissionError):authorize(a,'h')
    def test_scoped_error_pipeline_keeps_scope(self):
        from worker import run_pipeline
        s=types.SimpleNamespace(evaluations=0,model_builds=1,phase_records=[])
        def fail():raise ScopedCorrectnessError('artificial',['C'])
        s.prepare=fail;n=types.SimpleNamespace(calls=0,close=lambda:None)
        r=run_pipeline(s,n,None,self.clock,self.out,{},'h')
        self.assertEqual(r['affected_arms'],['C']);self.assertEqual(r['solve_attempts'],0)
    def test_preparation_stop_is_ordinary_pipeline(self):
        from worker import run_pipeline
        s=types.SimpleNamespace(evaluations=0,model_builds=1,phase_records=[])
        def fail():raise PreparationStop('INITIAL_CONTINUOUS_POINT_REJECTED_NO_CALL')
        s.prepare=fail;n=types.SimpleNamespace(calls=0,close=lambda:None)
        r=run_pipeline(s,n,None,self.clock,self.out,{},'h')
        self.assertEqual(r['outcome'],'INITIAL_CONTINUOUS_POINT_REJECTED_NO_CALL')
    def test_single_real_solve_site_and_no_other_optimization_entry(self):
        here=Path(__file__).parent
        for name in ('science.py','representation.py','reduction_replay.py','batch.py'):
            tree=ast.parse((here/name).read_text())
            self.assertFalse(any(isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute) and x.func.attr in ('solve','populate_solution_pool','refine','feasopt') for x in ast.walk(tree)))
        tree=ast.parse((here/'native.py').read_text())
        self.assertEqual(sum(isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute) and x.func.attr=='solve' for x in ast.walk(tree)),1)
    def test_nested_job_protection_without_science(self):
        outer=Job(256*1024*1024,active_limit=2);inner=Job(128*1024*1024,active_limit=1);p=None
        try:
            p=subprocess.Popen([sys.executable,'-B','-c','import sys;sys.stdin.readline()'],stdin=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
            outer.assign(p);inner.assign(p);p.stdin.write(b'GO\n');p.stdin.flush();p.stdin.close();p.wait(timeout=5)
            end=time.monotonic()+2
            while (outer.accounting()['active_processes'] or inner.accounting()['active_processes']) and time.monotonic()<end:time.sleep(.02)
            self.assertEqual(outer.accounting()['active_processes'],0);self.assertEqual(inner.accounting()['active_processes'],0)
        finally:
            if p is not None and p.poll() is None:inner.terminate();p.wait(timeout=2)
            inner.close();outer.close()
    def test_final_archive_late_revokes_terminal(self):
        receipt=dict(plan_sha256='h',outcome=dict(strict_success=True,scientific_snapshot_accepted=True,reasons=[]))
        save(self.out/'controller_receipt.json',receipt)
        save(self.out/'controller_completion.json',dict(within_method_window=False,after_receipt_and_hash_elapsed_s=601,receipt_sha256=sha(self.out/'controller_receipt.json')))
        self.assertFalse(read_terminal(self.out,0,'h')['outcome']['strict_success'])

def main():
    global OUT
    import test_control
    OUT=Path(sys.argv[1]).resolve();OUT.mkdir(exist_ok=False);test_control.OUT=OUT
    suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(LegacyTests),unittest.defaultTestLoader.loadTestsFromTestCase(Tests)])
    buf=io.StringIO();t=time.monotonic();r=unittest.TextTestRunner(stream=buf,verbosity=2).run(suite)
    (OUT/'unittest.txt').write_text(buf.getvalue(),encoding='utf-8')
    result=dict(passed=r.wasSuccessful(),tests_run=r.testsRun,failures=len(r.failures),errors=len(r.errors),elapsed_s=time.monotonic()-t,
        CPLEX_imported='cplex' in sys.modules,CPLEX_objects=0,optimization_calls=0,full_R1_builds=0,thermal_evaluations=0,
        original_science_imported=any(x in sys.modules for x in ('milp','thermal','complement_gate')),
        code_hashes={p.name:sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))},
        scope='Synthetic four-column models, API/evaluator doubles, tiny Python process/Job controls only')
    save(OUT/'results.json',result);print(buf.getvalue());return 0 if r.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(main())

