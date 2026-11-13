"""Pure controls: fake API/evaluator and tiny owned Python jobs; no CPLEX import."""
import ast,copy,io,json,os,subprocess,sys,time,types,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from core import *
from science import admit,decode,exact_objective
from native import Native,Events,parse_observed_logs,callback_class
from worker import run_pipeline
from controller import run_owned,monitor_reason,accept_snapshot,layered_evidence
from fake_api import api,FakeModel,packet

OUT=None
class FakeClock:
    def __init__(self):self.t=10.
    @property
    def elapsed(self):return self.t
    def check(self,cutoff=590):
        if not 0<=self.t<cutoff:raise WindowExpired('fake cutoff')

def evaluation(lo='1.084',hi='1.086'):
    return dict(state='SAFE',rankable_energy=True,numerical_protocol='directed-decimal60-taylor18-scaled100-v1',
        scenes={s:dict(state='SAFE',complete=True,energy_accuracy_met=True) for s in ('AB','AC')},weighted_energy_J=[lo,hi],
        completed_at_elapsed_s=11.,elapsed_s=11.,archived_elapsed_s=11.)

class FakeScience:
    def __init__(self):self.new=packet();self.initial={'tag':'initial'};self.scenes=['AB','AC'];self.evaluations=0;self.reject=False;self.safe=True;self.same=False;self.energy=('1.029','1.031')
    def prepare(self):pass
    def validate_vector(self,x,name):
        passed=admit(self.new,x)['passed'] and not self.reject
        return dict(passed=passed,candidate={'tag':'final'},same_initial=self.same,objective_exact_binary64=str(exact_objective(self.new,x)),legality={'state':'SCHEDULE_VALID_THERMAL_UNCHECKED'})
    def evaluate(self,candidate,name):
        self.evaluations+=1
        r=evaluation() if self.evaluations==1 else evaluation(*self.energy)
        if self.evaluations==2 and not self.safe:r['state']='THERMAL_VIOLATION'
        return r

class Tests(unittest.TestCase):
    def setUp(self):
        self.out=OUT/self._testMethodName;self.out.mkdir();self.clock=FakeClock()
    def fixture(self):
        model=FakeModel();dll=self.out/'fake_dll.txt';dll.write_text('ARTIFICIAL API; not a DLL')
        plan=dict(parameter_baseline={'parameters.timelimit':1e75,'parameters.threads':0},parameter_overrides={'threads':1,'timelimit':'N(t)'},
            native_runtime=dict(cplex_version='FAKE_CONTROL',dll_path=str(dll),dll_sha256=sha(dll)),
            historical_common_energy_J=dict(lower='1.084',upper='1.086'),bound_objective_consistency_tolerance=1e-7)
        events=Events(self.out,self.clock);native=Native(api(model),plan,self.out,self.clock,events)
        science=FakeScience();return model,dll,plan,events,native,science
    def pipeline(self,modify=lambda m,s,c:None):
        model,dll,plan,events,native,science=self.fixture();modify(model,science,self.clock)
        original=native.solve_once
        def solve(h):
            r=original(h)
            if r is not None:save(self.out/'response_ack.json',receive_response(self.out,self.clock,h))
            return r
        native.solve_once=solve
        with patch('native.loaded_dll',return_value=str(dll)):
            r=run_pipeline(science,native,events,self.clock,self.out,plan,'control-plan')
        events.close();return r,model,science
    def test_full_fake_chain_strict_success(self):
        r,m,s=self.pipeline();self.assertTrue(r['strict_success']);self.assertEqual(m.calls,1);self.assertEqual(s.evaluations,2);self.assertTrue(m.closed)
    def test_rejected_start_no_modification_or_retry(self):
        r,m,s=self.pipeline(lambda m,s,c:setattr(m,'accept_start',False));self.assertEqual(m.MIP_starts.count,1);self.assertEqual(m.calls,1)
        self.assertEqual(m.MIP_starts.pair.val,packet().x0.tolist());self.assertTrue(r['strict_success'])
    def test_no_final_vector_no_initial_substitution(self):
        r,m,s=self.pipeline(lambda m,s,c:setattr(m,'vector',None));self.assertEqual(r['outcome'],'NO_FINAL_NATIVE_VECTOR');self.assertIsNone(r['final']);self.assertEqual(s.evaluations,1)
    def test_empty_final_vector(self):
        r,m,s=self.pipeline(lambda m,s,c:setattr(m,'vector',np.array([])));self.assertEqual(r['outcome'],'NO_FINAL_NATIVE_VECTOR')
    def test_candidate_matrix_rejected_no_heat(self):
        r,m,s=self.pipeline(lambda m,s,c:setattr(m,'vector',np.array([.2,.25,.25,1.])));self.assertEqual(r['outcome'],'FINAL_VECTOR_REJECTED');self.assertEqual(s.evaluations,1)
    def test_independent_legality_rejected(self):
        r,m,s=self.pipeline(lambda m,s,c:setattr(s,'reject',True));self.assertEqual(r['outcome'],'FINAL_VECTOR_REJECTED')
    def test_unsafe_final_cannot_improve(self):
        r,m,s=self.pipeline(lambda m,s,c:setattr(s,'safe',False));self.assertFalse(r['strict_success']);self.assertEqual(r['outcome'],'FINAL_NOT_COMPLETE_SAFE')
    def test_same_schedule_not_strict_success(self):
        r,m,s=self.pipeline(lambda m,s,c:setattr(s,'same',True));self.assertFalse(r['strict_success'])
    def test_overlapping_energy_intervals(self):
        r,m,s=self.pipeline(lambda m,s,c:setattr(s,'energy',('1.083','1.085')));self.assertFalse(r['strict_success'])
    def test_native_bound_conflict(self):
        r,m,s=self.pipeline(lambda m,s,c:setattr(m,'bound',.9));self.assertEqual(r['outcome'],'BOUND_CONFLICT');self.assertFalse(r['strict_success']);self.assertEqual(s.evaluations,1)
    def test_low_budget_no_solve(self):
        r,m,s=self.pipeline(lambda m,s,c:setattr(c,'t',520));self.assertEqual(r['outcome'],'INSUFFICIENT_NATIVE_BUDGET');self.assertEqual(m.calls,0)
    def test_memory_exception_preserved(self):
        r,m,s=self.pipeline(lambda m,s,c:setattr(m,'error',MemoryError('CONTROL native allocation denied')))
        self.assertEqual(read(self.out/'native_error.json')['type'],'MemoryError');self.assertEqual(m.calls,1);self.assertTrue(m.closed)
    def test_native_timeout_not_infeasible(self):
        for n in (107,108,131,132):self.assertEqual(classify_native(n),'TIME_LIMIT')
        self.assertEqual(classify_native(103),'NATIVE_REPORTED_INFEASIBLE')
    def test_license_exception_not_infeasible(self):
        self.assertEqual(classify_native(None,dict(type='CplexSolverError',message='CPLEX Error 1016: Community size limit')),'LICENSE_ERROR')
    def test_allocation_boundary(self):
        self.assertEqual(quota(8.7),531);self.assertEqual(quota(510),30);self.assertEqual(quota(510.01),29)
        for t in (float('nan'),-1):
            with self.assertRaises(IntegrityError):quota(t)
    def test_strict_exact_decimal_no_roundoff_credit(self):
        a=evaluation('1.0000000000000000000001','1.1');b=evaluation('0.9','1.0000000000000000000000')
        self.assertTrue(strict_improvement(a,b,['AB','AC'],True,True,True));b['weighted_energy_J'][1]=a['weighted_energy_J'][0]
        self.assertFalse(strict_improvement(a,b,['AB','AC'],True,True,True))
    def test_partial_late_or_unrankable_SAFE(self):
        for mutate in [lambda r:r['scenes'].pop('AC'),lambda r:r.update(archived_elapsed_s=590),lambda r:r.update(rankable_energy=False),lambda r:r['scenes']['AC'].update(complete=False)]:
            r=evaluation();mutate(r);self.assertIsNone(safe_interval(r,['AB','AC']))
    def test_native_infinity_not_finite_bound(self):
        for v in (1e20,-1e20,float('inf'),float('nan'),None):self.assertIsNone(finite_native(v))
        self.assertEqual(finite_native(.9),.9)
    def test_absolute_and_scaled_residual_both_required(self):
        p=packet();p.A=(p.A[0],p.A[1],p.A[2],p.A[3]*1e8);r=admit(p,p.x0);self.assertFalse(r['passed'])
    def test_integer_not_repaired(self):
        p=packet();x=p.x0.copy();x[0]=.999;before=x.tobytes();self.assertFalse(admit(p,x)['passed']);self.assertEqual(x.tobytes(),before)
    def test_full_tiny_rhs_preserved_admission(self):
        p=packet();self.assertTrue(admit(p,p.x0)['passed']);self.assertEqual(p.b[1],1.4e-63)
    def test_start_and_root_log_parser_split(self):
        rows=[dict(parent_received_elapsed_s=20,event=dict(kind='native_log',text="MIP start 'common_complete_x0' defined initial ")),
              dict(parent_received_elapsed_s=21,event=dict(kind='native_log',text='solution with objective 1.0.\nRoot relaxation solution time = 2.0 sec.\n'))]
        r=parse_observed_logs(rows);self.assertEqual(r['MIP_start_acceptance'],'ACCEPTED');self.assertEqual(r['root_LP_completed'],'PASS')
    def test_log_late_and_finite_bound_no_root_inference(self):
        rows=[dict(parent_received_elapsed_s=550,event=dict(kind='native_log',text='Root relaxation solution time = 1 sec.\n')),
              dict(parent_received_elapsed_s=20,event=dict(kind='mip_info_callback',best_bound=.5))]
        self.assertEqual(parse_observed_logs(rows)['root_LP_completed'],'UNKNOWN')
    def test_rejected_start_parser(self):
        r=parse_observed_logs([dict(parent_received_elapsed_s=20,event=dict(kind='native_log',text='Warning: No solution found from 1 MIP starts.\n'))]);self.assertEqual(r['MIP_start_acceptance'],'REJECTED')
    def test_response_arrival_not_worker_timestamp(self):
        save(self.out/'native_response.json',dict(plan_sha256='p',returned_elapsed_s=100,vector=None));self.clock.t=550
        self.assertFalse(receive_response(self.out,self.clock,'p')['timely'])
    def test_response_source_drift(self):
        save(self.out/'native_response.json',dict(plan_sha256='wrong',vector=None))
        with self.assertRaises(IntegrityError):receive_response(self.out,self.clock,'p')
    def test_one_solve_guard(self):
        m,d,p,e,n,s=self.fixture();n.calls=1
        with self.assertRaises(IntegrityError):n.solve_once('p')
        e.close()
    def test_approval_fails_closed(self):
        for a in ({},{'protocol':'D282-CPLEX-C-native-load-no-solve-v1','decision':'APPROVE'}):
            with self.assertRaises(PermissionError):authorize(a,'p')
    def test_stop_scope_accumulates_counterfactual(self):
        for first in ('CLEANUP_FAILURE','IDENTITY_DRIFT','BOUND_CONFLICT'):
            self.assertEqual(stop_scope(first,'TIME_LIMIT','COMMON_INITIAL_RETURNED_SAFE'),'GLOBAL')
    def test_cleanup_failure_revokes_success(self):
        r=accept_snapshot(self.out,self.clock,'p',dict(cleanup_ok=False,exit_code=0));self.assertFalse(r['strict_success']);self.assertEqual(r['stop_scope'],'GLOBAL')
    def test_static_only_one_optimizer_and_no_real_import_in_tests(self):
        tree=ast.parse((Path(__file__).parent/'native.py').read_text());calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='solve'];self.assertEqual(len(calls),1)
        self.assertNotIn('cplex',sys.modules)
    def test_callback_vector_is_not_final_vector(self):
        events=Events(self.out,self.clock)
        class Base:
            def has_incumbent(self):return True
            def get_incumbent_objective_value(self):return .5
            def get_best_objective_value(self):return .1
            def get_num_nodes(self):return 0
            def get_num_iterations(self):return 4
            def get_MIP_relative_gap(self):return .8
            def get_incumbent_values(self):return [1.,0.]
            def abort(self):self.aborted=True
        c=callback_class(Base,self.out,self.clock,events)();c();c();events.close()
        self.assertTrue((self.out/'callback_vector_000001.npy').exists());self.assertFalse((self.out/'final_vector.npy').exists())
        self.assertEqual(len((self.out/'events.jsonl').read_text().splitlines()),1)
    def test_callback_deadline_aborts_without_candidate(self):
        events=Events(self.out,self.clock)
        class Base:
            def abort(self):self.aborted=True
        c=callback_class(Base,self.out,self.clock,events)();self.clock.t=550;c();events.close();self.assertTrue(c.aborted)
    def test_runtime_parameter_default_drift(self):
        m,d,p,e,n,s=self.fixture();m.parameters.threads.value=8
        with patch('native.loaded_dll',return_value=str(d)):
            with self.assertRaises(IntegrityError):n.prepare(packet())
        n.close();e.close();self.assertEqual(m.calls,0)
    def test_admitted_initial_evaluator_connector_uses_original_accuracy(self):
        from science import Science
        s=Science('.',{},self.out,self.clock);s.instance={'scenarios':[]};s.config={'accuracy_targets':{'test':'unchanged'}};s.budget=object()
        calls=[]
        def fake(instance,candidate,accuracy,budget):calls.append((instance,candidate,accuracy,budget));return evaluation()
        s.evaluate_fn=fake;r=s.evaluate({'tag':'control'},'evaluation.json');self.assertEqual(calls[0][2],s.config['accuracy_targets']);self.assertEqual(s.evaluations,1)
    def test_native_memory_error_never_awards_success(self):
        r,m,s=self.pipeline(lambda m,s,c:setattr(m,'error',MemoryError('CONTROL allocation failure')))
        self.assertEqual(r['outcome'],'RESOURCE_ERROR');self.assertFalse(r['strict_success']);self.assertEqual(s.evaluations,1)
    def test_received_vector_hash_drift(self):
        from native import array_archive
        v=array_archive(self.out/'final_vector.npy',np.array([1.]))
        save(self.out/'native_response.json',dict(plan_sha256='p',vector=v));(self.out/'final_vector.npy').write_bytes(b'corrupt')
        with self.assertRaises(IntegrityError):receive_response(self.out,self.clock,'p')
    def test_initial_complete_SAFE_failure_prevents_solve(self):
        m,d,p,e,n,s=self.fixture();s.evaluate=lambda *args:dict(state='UNRESOLVED')
        with patch('native.loaded_dll',return_value=str(d)):r=run_pipeline(s,n,e,self.clock,self.out,p,'p')
        e.close();self.assertEqual(r['outcome'],'INITIAL_NOT_COMPLETE_SAFE');self.assertEqual(m.calls,0)
    def test_cleanup_exception_overrides_valid_success(self):
        m,d,p,e,n,s=self.fixture()
        def fail_close():raise OSError('CONTROL end() failure')
        n.close=fail_close;self.clock.t=520
        with patch('native.loaded_dll',return_value=str(d)):r=run_pipeline(s,n,e,self.clock,self.out,p,'p')
        e.close();self.assertEqual(r['outcome'],'CLEANUP_FAILURE');self.assertFalse(r['strict_success'])
    def test_monitor_slow_start_and_memory_stop(self):
        limits=dict(scientific_seal_s=590,native_response_cutoff_s=550,worker_soft_private_bytes=100,parent_private_bytes=50,system_available_floor_bytes=10)
        self.assertEqual(monitor_reason(551,1,1,20,False,limits),'NATIVE_RESPONSE_DEADLINE')
        self.assertIsNone(monitor_reason(551,1,1,20,True,limits))
        self.assertEqual(monitor_reason(3,101,1,20,False,limits),'WORKER_MEMORY_LIMIT')
        self.assertEqual(monitor_reason(590,1,1,20,True,limits),'SCIENTIFIC_WINDOW_EXPIRED')
    def job(self,mode,job_class=None):
        limits=dict(job_and_process_hard_commit_bytes=96*2**20,worker_soft_private_bytes=200*2**20,parent_private_bytes=512*2**20,
            minimum_available_at_entry_bytes=0,system_available_floor_bytes=0,scientific_seal_s=3,native_response_cutoff_s=1,
            total_window_s=5,evidence_cap_bytes=8*2**20,sample_period_s=.02)
        if mode=='memory':limits['native_response_cutoff_s']=2
        argv=[sys.executable,'-B',str(Path(__file__).parent/'control_child.py'),mode]
        kw=dict(job_class=job_class) if job_class else {}
        r=run_owned(argv,self.out,Clock(time.monotonic()),limits,'control-plan','control-nonce',**kw);save(self.out/'process_result.json',r);return r
    def test_owned_process_normal_and_cleanup(self):
        r=self.job('normal');self.assertEqual(r['exit_code'],0);self.assertTrue(r['cleanup_ok']);self.assertEqual(r['job_accounting']['active_processes'],0)
    def test_owned_process_timeout_preserves_log(self):
        r=self.job('timeout');self.assertEqual(r['stop_reason'],'NATIVE_RESPONSE_DEADLINE');self.assertTrue(r['cleanup_ok']);self.assertIn('ARTIFICIAL',(self.out/'stdout.log').read_text())
    def test_owned_process_memory_original_error_retained(self):
        r=self.job('memory');self.assertTrue(r['cleanup_ok']);self.assertEqual(read(self.out/'memory_exception.json')['type'],'MemoryError');self.assertIn('original MemoryError',(self.out/'stderr.log').read_text())
    def test_owned_process_child_limit(self):
        r=self.job('child_blocked');self.assertTrue(r['cleanup_ok']);s=read(self.out/'spawn_result.json');self.assertNotEqual(s.get('returncode'),0)
    def test_owned_process_cleanup_failure_counterfactual(self):
        from windows_job import Job
        class FailClose(Job):
            def close(self):
                super().close();raise OSError('CONTROL cleanup acknowledgment failure after real release')
        r=self.job('normal',FailClose);self.assertFalse(r['cleanup_ok']);self.assertTrue(r['errors'])
    def test_owned_job_delayed_exit_accounting(self):
        from windows_job import Job
        class DelayedAccounting(Job):
            def accounting(self):
                r=super().accounting()
                if r['active_processes']==0 and getattr(self,'artificial_delay',0)<2:
                    self.artificial_delay=getattr(self,'artificial_delay',0)+1;r['active_processes']=1
                return r
        r=self.job('normal',DelayedAccounting);self.assertTrue(r['cleanup_ok']);self.assertEqual(r['job_accounting']['active_processes'],0)
    def test_real_parent_response_handshake_no_solver(self):
        r=self.job('response');self.assertEqual(r['exit_code'],0);self.assertTrue(r['response_ack']['timely']);self.assertTrue(read(self.out/'child_ack_seen.json')['timely'])
    def make_snapshot(self):
        save(self.out/'scientific_snapshot.json',dict(plan_sha256='p',in_window_sources_verified=True,evidence_hashes={},strict_success=True,outcome='STRICT_ENERGY_IMPROVEMENT'))
        save(self.out/'worker_receipt.json',dict(plan_sha256='p',snapshot_sha256=sha(self.out/'scientific_snapshot.json'),sealed_elapsed_s=10))
    def test_late_snapshot_cannot_use_early_worker_timestamp(self):
        self.make_snapshot();self.clock.t=590
        r=accept_snapshot(self.out,self.clock,'p',dict(cleanup_ok=True,exit_code=0));self.assertFalse(r['strict_success']);self.assertIn('LATE_SNAPSHOT',r['reasons'])
    def test_cleanup_failure_revokes_existing_strict_snapshot(self):
        self.make_snapshot();r=accept_snapshot(self.out,self.clock,'p',dict(cleanup_ok=False,exit_code=0));self.assertFalse(r['strict_success']);self.assertEqual(r['stop_scope'],'GLOBAL')
    def test_snapshot_hash_drift_revokes_success(self):
        self.make_snapshot();(self.out/'scientific_snapshot.json').write_text('{}')
        r=accept_snapshot(self.out,self.clock,'p',dict(cleanup_ok=True,exit_code=0));self.assertIn('EVIDENCE_INTEGRITY',r['reasons']);self.assertFalse(r['strict_success'])
    def test_native_memory_status_stops_before_heat(self):
        r,m,s=self.pipeline(lambda m,s,c:setattr(m,'status',111));self.assertEqual(r['outcome'],'NATIVE_MEMORY_LIMIT');self.assertEqual(s.evaluations,1)
    def test_single_claim_directory_cannot_be_reused(self):
        p=self.out/'claimed';p.mkdir(exist_ok=False);save(p/'claim.json',dict(consumed=True))
        with self.assertRaises(FileExistsError):p.mkdir(exist_ok=False)
    def test_independent_row_sum_audit_agrees_on_tiny_fixture(self):
        from audit_result import residuals
        from scipy import sparse
        p=packet();d={k:getattr(p,k) for k in ('c','b','beq','lb','ub','intcon')}
        for key in ('A','Aeq'):
            shape,r,c,v=getattr(p,key);d[key]=sparse.csr_matrix((v,(r,c)),shape=shape)
        self.assertTrue(all(v['passed'] for v in residuals(d,p.x0,0).values()))
        x=p.x0.copy();x[0]=.5;self.assertFalse(residuals(d,x,0)['integer']['passed'])
    def test_independent_audit_SAFE_interval_rejects_partial(self):
        from audit_result import interval
        self.assertIsNotNone(interval(evaluation(),['AB','AC']))
        r=evaluation();r['scenes']['AC']['complete']=False;self.assertIsNone(interval(r,['AB','AC']))
    def test_empty_layered_receipt_cannot_invent_native_success(self):
        r=layered_evidence(dict(snapshot=None,strict_success=False,scientific_snapshot_accepted=False,reasons=['NO_VECTOR']),
                           dict(root_LP_entered='UNKNOWN',root_LP_completed='UNKNOWN'),['AB','AC'])
        self.assertEqual(r['native_candidate'],'NOT_REACHED');self.assertFalse(r['strict_energy_improvement']);self.assertIsNone(r['native_finite_lower_bound'])

def main():
    global OUT
    OUT=Path(sys.argv[1]).resolve();OUT.mkdir(exist_ok=False)
    buf=io.StringIO();start=time.monotonic();run=unittest.TextTestRunner(stream=buf,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    (OUT/'unittest.txt').write_text(buf.getvalue(),encoding='utf-8')
    save(OUT/'results.json',dict(passed=run.wasSuccessful(),tests_run=run.testsRun,failures=len(run.failures),errors=len(run.errors),elapsed_s=time.monotonic()-start,
        CPLEX_imported='cplex' in sys.modules,CPLEX_objects=0,optimization_calls=0,full_R1_builds=0,thermal_evaluations=0,
        code_hashes={p.name:sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))},scope='Artificial API/evaluator; synthetic controls only'))
    print(buf.getvalue());return 0 if run.wasSuccessful() else 1

if __name__=='__main__':raise SystemExit(main())
