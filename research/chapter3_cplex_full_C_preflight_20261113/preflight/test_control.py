"""Pure fake-CPLEX controls + bounded Python-only Windows Job checks. No cplex import."""
import ast,copy,json,sys,time,types,unittest
from pathlib import Path
import numpy as np
from scipy import sparse
from transport_contract import MatrixPacket,ContractError
from native_adapter import load,readback,compare,bounds_to_native,bounds_from_native,seal_algorithms
from common import monitor_decision,classify,claim_once,Deadline
from controller import run_owned

OUT=Path(sys.argv[1]).resolve();OUT.mkdir(exist_ok=False)

class Pair:
    def __init__(self,ind,val):self.ind=list(ind);self.val=list(val)
class Vars:
    def add(self,**kw):self.d=copy.deepcopy(kw)
    def get_num(self):return len(self.d['obj'])
    def get_names(self):return self.d['names']
    def get_types(self):return list(self.d['types'])
    def get_lower_bounds(self):return self.d['lb']
    def get_upper_bounds(self):return self.d['ub']
class Rows:
    def __init__(self):self.rows=[];self.senses=[];self.rhs=[];self.names=[]
    def add(self,lin_expr,senses,rhs,names):
        self.rows.extend(copy.deepcopy(lin_expr));self.senses.extend(senses);self.rhs.extend(rhs);self.names.extend(names)
    def get_num(self):return len(self.rows)
    def get_names(self):return self.names
    def get_senses(self):return self.senses
    def get_rhs(self):return self.rhs
    def get_num_nonzeros(self):return sum(len(x.val) for x in self.rows)
    def get_rows(self,begin,end):return copy.deepcopy(self.rows[begin:end+1])
class Starts:
    effort_level=types.SimpleNamespace(check_feasibility=1)
    def add(self,pair,effort,name):self.pair=copy.deepcopy(pair);self.effort=effort;self.name=name
    def get_num(self):return 1
    def get_starts(self,index):return copy.deepcopy(self.pair),self.effort
    def get_names(self):return [self.name]
class Objective:
    sense=types.SimpleNamespace(minimize=1)
    def __init__(self,v):self.v=v
    def set_sense(self,x):self.s=x
    def set_offset(self,x):self.offset=x
    def get_sense(self):return self.s
    def get_offset(self):return self.offset
    def get_linear(self):return self.v.d['obj']
class FakeModel:
    def __init__(self):
        self.variables=Vars();self.linear_constraints=Rows();self.MIP_starts=Starts();self.objective=Objective(self.variables)
        self.quadratic_constraints=self.indicator_constraints=self.SOS=types.SimpleNamespace(get_num=lambda:0)
API=types.SimpleNamespace(SparsePair=Pair,infinity=1e20)

def packet():
    d=dict(c=np.array([0.,.5,.5,0.]),A=sparse.csr_matrix([[1.,1.5,0.,0.],[0.,1.25e-8,-1.25e-8,0.]]),
        Aeq=sparse.csr_matrix([[0.,1.,-1.,0.]]),b=np.array([1.375,1.4e-63]),beq=np.array([0.]),
        lb=np.array([0.,-5.,-np.inf,0.]),ub=np.array([1.,55.,np.inf,1.]),intcon=np.array([1.,4.]),x0=np.array([1.,.25,.25,0.]))
    return MatrixPacket.read(d,intcon_base=1,sense='min',objective_constant=0.,column_ids=range(4))
def roundtrip(p=None):
    p=p or packet();m=FakeModel();load(m,API,p,lambda:None,lambda *a,**k:None,block_rows=1)
    return p,m
def check(p,m):
    q,inv=readback(m,API,p,lambda:None,lambda *a,**k:None,block_rows=1)
    return compare(p,q,inv)
LIMITS=dict(total_window_s=300,worker_deadline_s=280,worker_hard_commit_bytes=2*2**30,
    worker_soft_private_bytes=int(1.8*2**30),parent_private_bytes=512*2**20,
    minimum_available_at_entry_bytes=3*2**30,system_available_floor_bytes=2**30,
    sample_period_s=.1,evidence_cap_bytes=64*2**20,cleanup_reserve_s=20)

class Tests(unittest.TestCase):
    def test_fake_native_roundtrip_every_field(self):
        p,m=roundtrip();r=check(p,m);self.assertTrue(r['passed']);self.assertEqual(r['expected_hashes'],r['native_hashes'])
    def test_single_ulp_coeff_change(self):
        p,m=roundtrip();m.linear_constraints.rows[0].val[1]=np.nextafter(1.5,np.inf)
        self.assertFalse(check(p,m)['passed'])
    def test_tiny_rhs_not_rounded(self):
        p,m=roundtrip();m.linear_constraints.rhs[1]=0.;self.assertFalse(check(p,m)['passed'])
    def test_objective_and_bounds_mutation(self):
        for field in ('obj','lb','ub'):
            p,m=roundtrip();m.variables.d[field][0]=.125;self.assertFalse(check(p,m)['passed'])
    def test_objective_direction_constant(self):
        for field,val in [('s',-1),('offset',1.)]:
            p,m=roundtrip();setattr(m.objective,field,val);self.assertFalse(check(p,m)['passed'])
    def test_row_and_column_names_permuted(self):
        p,m=roundtrip();m.variables.d['names'].reverse();self.assertFalse(check(p,m)['passed'])
        p,m=roundtrip();m.linear_constraints.names.reverse();self.assertFalse(check(p,m)['passed'])
    def test_coordinates_reordered_or_dropped(self):
        for mode in ('reverse','drop','coordinate'):
            p,m=roundtrip();r=m.linear_constraints.rows[0]
            if mode=='reverse':r.ind.reverse();r.val.reverse()
            if mode=='drop':r.ind.pop();r.val.pop()
            if mode=='coordinate':r.ind[0]=3
            self.assertFalse(check(p,m)['passed'])
    def test_eq_direction_mutation(self):
        p,m=roundtrip();m.linear_constraints.senses[-1]='L';self.assertFalse(check(p,m)['passed'])
    def test_integer_domain_mutation(self):
        p,m=roundtrip();m.variables.d['types']='CCCC';self.assertFalse(check(p,m)['passed'])
    def test_partial_start_and_wrong_order(self):
        p,m=roundtrip();m.MIP_starts.pair.ind.pop();m.MIP_starts.pair.val.pop();self.assertFalse(check(p,m)['passed'])
        p,m=roundtrip();m.MIP_starts.pair.ind.reverse();self.assertFalse(check(p,m)['passed'])
    def test_start_bit_drift_effort_and_name(self):
        p,m=roundtrip();m.MIP_starts.pair.val[1]=np.nextafter(.25,np.inf);self.assertFalse(check(p,m)['passed'])
        p,m=roundtrip();m.MIP_starts.effort=4;self.assertFalse(check(p,m)['passed'])
        p,m=roundtrip();m.MIP_starts.name='other';self.assertFalse(check(p,m)['passed'])
    def test_infinity_semantics_and_finite_collision(self):
        for values in ([1e20],[-1e20],[1e25]):
            with self.assertRaises(ContractError):bounds_to_native(np.array(values),1e20)
        with self.assertRaises(ContractError):bounds_from_native([100.],np.array([np.inf]),1e20)
        self.assertEqual(bounds_to_native(np.array([-np.inf,np.inf]),1e20),[-1e20,1e20])
    def test_deadline_before_api_loading(self):
        p=packet();m=FakeModel()
        with self.assertRaises(TimeoutError):load(m,API,p,Deadline(time.perf_counter()-5,1).check,lambda *a,**k:None)
        self.assertFalse(hasattr(m.variables,'d'))
    def test_algorithm_guard_fake_modules(self):
        class C:
            def solve(self):raise AssertionError('Unblocked')
            def populate_solution_pool(self):raise AssertionError('Unblocked')
        proc=types.SimpleNamespace(__name__='fake_proc',mipopt=lambda:None,presolve=lambda:None,refineconflictext=lambda:None)
        py=types.SimpleNamespace(__name__='fake_swig',CPXXlpopt=lambda:None,CPXXfeasopt=lambda:None,CPXXtuneparam=lambda:None)
        fake=types.SimpleNamespace(Cplex=C,_internal=types.SimpleNamespace(_procedural=proc,_pycplex=py))
        attempts,blocked,deny=seal_algorithms(fake)
        for f in [C().solve,C().populate_solution_pool,proc.mipopt,proc.presolve,py.CPXXlpopt,py.CPXXfeasopt,py.CPXXtuneparam]:
            with self.assertRaises(RuntimeError):f()
        self.assertEqual(len(attempts),7);self.assertGreaterEqual(len(blocked),8)
    def test_time_memory_protection(self):
        self.assertEqual(monitor_decision(280,0,0,4*2**30,LIMITS),'TIME_LIMIT')
        self.assertEqual(monitor_decision(1,2*2**30,0,4*2**30,LIMITS),'WORKER_MEMORY_LIMIT')
        self.assertEqual(monitor_decision(1,0,2**30,4*2**30,LIMITS),'CONTROLLER_MEMORY_LIMIT')
        self.assertEqual(monitor_decision(1,0,0,0,LIMITS),'SYSTEM_MEMORY_LOW')
        self.assertEqual(monitor_decision(float('nan'),0,0,4*2**30,LIMITS),'INVALID_MONITOR')
    def test_late_failed_and_cleanup_receipts(self):
        r=dict(passed=True,native_objects_created=1,algorithm_attempts=[],sealed_elapsed_s=10)
        self.assertEqual(classify(r,0,True,11,LIMITS),'PASS')
        for change,expected in [({'sealed_elapsed_s':281},'LATE_EVIDENCE'),({'algorithm_attempts':['solve']},'FORBIDDEN_SCOPE'),
                                ({'native_objects_created':2},'FORBIDDEN_SCOPE'),({'sealed_elapsed_s':float('nan')},'INVALID_TIMING')]:
            self.assertEqual(classify(r|change,0,True,11,LIMITS),expected)
        self.assertEqual(classify(r,0,False,11,LIMITS),'CLEANUP_FAILURE')
        self.assertEqual(classify(None,1,True,11,LIMITS),'WORKER_FAILURE')
        self.assertEqual(classify(r,0,True,301,LIMITS),'TOTAL_WINDOW_EXCEEDED')
    def test_no_automatic_retry_claim(self):
        path=OUT/'claim';claim_once(path,{'one_use':True})
        with self.assertRaises(FileExistsError):claim_once(path,{'one_use':True})
    def test_no_optimizer_calls_in_real_code(self):
        forbidden={'solve','populate_solution_pool','presolve','refine','refine_MIP_start','feasopt','tune_problem','tune_problem_set'}
        for name in ('worker.py','native_adapter.py','controller.py'):
            tree=ast.parse((Path(__file__).parent/name).read_text(encoding='utf-8'))
            calls=[n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
            self.assertFalse(set(calls)&forbidden,name)
    def child(self,name,body,changes=None):
        out=OUT/name;out.mkdir();limits=LIMITS|dict(worker_deadline_s=5,total_window_s=8,cleanup_reserve_s=2,
            minimum_available_at_entry_bytes=0,system_available_floor_bytes=0)
        limits.update(changes or {})
        script='import sys\nassert sys.stdin.readline().strip()=="D282_GO"\n'+body
        r=run_owned([sys.executable,'-B','-c',script],out,time.perf_counter(),limits)
        (out/'result.json').write_text(json.dumps(r,indent=2),encoding='utf-8',newline='\n')
        return r
    def test_windows_job_normal_exit(self):
        r=self.child('job_normal','print("CONTROL_ONLY")')
        self.assertEqual(r['exit_code'],0);self.assertTrue(r['cleanup_ok']);self.assertEqual(r['job_accounting']['active_processes'],0)
    def test_windows_job_timeout_cleanup(self):
        r=self.child('job_timeout','import time\ntime.sleep(20)',dict(worker_deadline_s=.5))
        self.assertEqual(r['stop_reason'],'TIME_LIMIT');self.assertTrue(r['cleanup_ok'])
    def test_windows_job_commit_limit(self):
        r=self.child('job_memory','x=bytearray(160*1024*1024)',dict(worker_hard_commit_bytes=64*2**20,worker_soft_private_bytes=64*2**20))
        self.assertNotEqual(r['exit_code'],0);self.assertTrue(r['cleanup_ok'])
        self.assertEqual(r['job']['job_memory'],64*2**20)
    def test_windows_job_never_admit_second_process(self):
        body='import subprocess\ntry:\n p=subprocess.Popen([sys.executable,"-c","pass"])\n p.wait()\n raise RuntimeError("unexpected child")\nexcept OSError:\n print("child blocked")'
        r=self.child('job_child_blocked',body)
        self.assertEqual(r['exit_code'],0);self.assertTrue(r['cleanup_ok'])

if __name__=='__main__':
    started=time.perf_counter();suite=unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    record=dict(passed=result.wasSuccessful(),tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        elapsed_s=time.perf_counter()-started,CPLEX_imports=0,CPLEX_objects=0,optimization_calls=0,
        full_R1_builds=0,thermal_evaluations=0,scope='Fake CPLEX + small Python-only Windows job children')
    (OUT/'results.json').write_text(json.dumps(record,indent=2),encoding='utf-8',newline='\n')
    raise SystemExit(not result.wasSuccessful())
