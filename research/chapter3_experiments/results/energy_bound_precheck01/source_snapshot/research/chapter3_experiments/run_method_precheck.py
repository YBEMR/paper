"""Deterministic method-budget checks; no research solver comparisons."""
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

from scipy.sparse import csr_matrix
import numpy as np

import milp
from inputs import build_instance, build_instances, load_config
from method_runner import execute_milp, SOURCES
from thermal import Exhausted
from timing import MethodBudget
from build_observer import BuildObserver
from run_milp_precheck import select_fixture

HERE = Path(__file__).resolve().parent


class Clock:
    def __init__(self): self.now = 100.0
    def __call__(self): return self.now
    def advance(self, value): self.now += value


def require(value, message='assertion failed'):
    if not value: raise AssertionError(message)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def run(out):
    out.mkdir(parents=True, exist_ok=False)
    records = []
    def check(name, fn):
        try:
            fn(); records.append({'name': name, 'passed': True})
        except Exception as e:
            records.append({'name': name, 'passed': False, 'error': f'{type(e).__name__}: {e}'})

    def phase_accounting():
        c=Clock(); b=MethodBudget(10, clock=c)
        with b.phase('outer'):
            c.advance(1)
            with b.phase('inner'): c.advance(2)
            c.advance(1)
        s=b.summary()
        require(s['phases_exclusive_s']=={'inner': 2, 'outer': 2})
        require(sum(s['phases_exclusive_s'].values())==s['method_elapsed_s'])
        c.advance(6)
        try: b.check()
        except Exhausted: pass
        else: raise AssertionError('exact deadline was accepted')
    check('nested_exclusive_phases_and_exact_deadline', phase_accounting)

    def inputs_equal():
        spec=importlib.util.spec_from_file_location('old_inputs', HERE/'results/milp_precheck04/source_snapshot/inputs.py')
        old=importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
        config=load_config(); expected=old.build_instances(config)
        require(build_instances(config)==expected)
        for instance in expected:
            require(build_instance(config,instance['id'])==instance,instance['id'])
        require(len(expected)==95)
    check('all_95_single_inputs_equal_preserved_generator', inputs_equal)

    def observer_equivalence():
        config=load_config(); base=build_instance(config,'base__R1')
        sid=base['scenarios'][0]['id']
        shared=base['scenarios'][0]['stage_instances'][0]['shared_stage_id']
        fixture,starts=select_fixture(base,'observer',{sid:[shared]},{shared:['0','5']})
        plain=milp.build_model(fixture,config,starts=starts,include_physics=False)
        b=MethodBudget(60); observer=BuildObserver(b)
        observed=milp.build_model(fixture,config,starts=starts,budget=b,include_physics=False,progress=observer)
        for attr in ('names','bounds','rows','integer','c'):
            require(getattr(plain,attr)==getattr(observed,attr),attr)
        require((plain.as_solver_dict()['A']!=observed.as_solver_dict()['A']).nnz==0)
        observer.finish('MODEL_CONSTRUCTED'); first=observer.snapshot()
        require(first['nonzeros_in_rows']==sum(len(row['coef']) for row in observed.rows))
        observed.as_solver_dict()
        require(observer.snapshot()['method_elapsed_seconds']==first['method_elapsed_seconds'])
    check('observer_preserves_encoded_model_and_freezes_construction_time',observer_equivalence)

    def component_accounting():
        from types import SimpleNamespace
        config=load_config(); instance=build_instance(config,'base__R1')
        progress=SimpleNamespace(observation_wall_seconds=0.0)
        model=milp.Model(instance,MethodBudget(60),progress=progress)
        with patch('milp.time.perf_counter',side_effect=[10.0,15.0]):
            try:
                with model.measure_construction('fixture_interrupted_rows'):
                    progress.observation_wall_seconds=2.0
                    raise Exhausted('fixture')
            except Exhausted: pass
        require(model.construction_costs['fixture_interrupted_rows']==
            {'calls':1,'inclusive_s':5.0,'nested_observation_s':2.0,'exclusive_s':3.0})
    check('component_costs_disjoint_and_preserved_on_interruption',component_accounting)

    def partial_observer():
        config=load_config(); base=build_instance(config,'base__R1')
        b=MethodBudget(60); observer=BuildObserver(b)
        def observe(stage,model,detail):
            observer(stage,model,detail)
            if stage=='shared_mapping': raise Exhausted('injected_stage_stop')
        try: milp.build_model(base,config,budget=b,progress=observe)
        except Exhausted: pass
        else: raise AssertionError('partial model returned')
        s=observer.finish('CONSTRUCTION_INTERRUPTED')
        require(s['variables']>0 and s['partial_counts_are_not_solver_ready'])
    check('interrupted_construction_is_partial_not_solver_ready',partial_observer)

    def startup_cleanup_separate(cleanup_seconds=4):
        c=Clock()
        def loader(b): c.advance(1); return {'accuracy_targets':{}},{'id':'fixture_startup_failure'}
        class Model:
            def summary(self): return {'fixture':True}
        def builder(*a,**kw): c.advance(1); return Model()
        def session(*a,**kw):
            c.advance(1); e=RuntimeError('startup interface'); c.advance(cleanup_seconds)
            e.matlab_cleanup={'cleanup_wall_seconds':cleanup_seconds}; raise e
        r=execute_milp(loader,out/f'startup_failure_cleanup_{cleanup_seconds}',seconds=10,clock=c,
                       construct_only=False,model_builder=builder,session_factory=session)
        require(r['state']=='UNRESOLVED' and r['timing']['cleanup_s']==cleanup_seconds)
        require(r['timing']['method_elapsed_excluding_cleanup_s']==3)
        require(r['timing']['phases_exclusive_s']['solver_startup']==1)
        require(r['reason']=='INTERFACE_ERROR' and not r['budget_exhausted'])
    check('failed_startup_cleanup_not_counted_as_solver_work',startup_cleanup_separate)
    check('long_cleanup_does_not_turn_startup_error_into_budget_expiry',lambda:startup_cleanup_separate(12))

    def invocation(name, fail_at=None, construct_only=False):
        c=Clock(); seen=[]; sessions=[]
        def step(phase,b):
            seen.append((phase,id(b),b.deadline,b.remaining))
            c.advance(11 if phase==fail_at else 1)
        class FakeModel:
            def __init__(self,b): self.budget=b
            def as_solver_dict(self):
                step('export',self.budget); self.budget.check()
                return {'A':csr_matrix((1,1))}
            def summary(self): return {'fixture':True}
        def loader(b):
            step('input',b)
            return {'accuracy_targets':{}},{'id':'fixture_timing'}
        def build(instance,config,budget,progress):
            step('construction',budget); budget.check(); return FakeModel(budget)
        class Session:
            def __init__(self,path,total_budget_s,budget):
                self.budget=budget; sessions.append(self)
                step('startup',budget); budget.check()
            def close(self): c.advance(4)
        def solve(model,session,accuracy,budget):
            require(model.budget is session.budget is budget)
            with budget.phase('solver_transport_and_solve'):
                step('solve',budget); budget.check()
            return {'state':'SAFE','safe_upper_bound_J':'1','safe_candidate':{'fixture':True},
                    'evaluation':{'completed_at_elapsed_s':budget.elapsed},'reason':'fixture_safe'}
        r=execute_milp(loader,out/name,seconds=10,construct_only=construct_only,clock=c,
                       model_builder=build,session_factory=Session,solve=solve)
        require(len({x[1] for x in seen})==1 and len({x[2] for x in seen})==1)
        require(all(a[3]>b[3] for a,b in zip(seen,seen[1:])))
        if fail_at:
            require(r['state']=='UNRESOLVED' and r['safe_upper_bound_J'] is None)
            require(r['budget_exhausted'])
            if fail_at in ('input','construction','export'): require(not sessions)
        elif construct_only:
            require(r['state']=='CONSTRUCTION_COMPLETE' and not sessions)
        else:
            require(r['state']=='SAFE' and r['timing']['cleanup_s']==4)
            require(r['timing']['method_elapsed_s']==4 and not r['budget_exhausted'])
        s=r['timing']; require(sum(s['phases_exclusive_s'].values())<=s['method_elapsed_s']+1e-9)
        if fail_at: require(any('exception' in f for f in s['phase_records']) or fail_at=='input')
        return r

    for phase in ('input','construction','startup','solve'):
        check('expiry_'+phase,lambda phase=phase:invocation('expiry_'+phase,phase))
    check('expiry_export_no_solver',lambda:invocation('expiry_export','export',True))
    check('construct_only_never_starts_solver',lambda:invocation('construct_ok',construct_only=True))
    check('one_deadline_and_cleanup_separate',lambda:invocation('complete'))
    check('fresh_independent_invocation',lambda:invocation('complete_again'))

    def feedback_flow(name):
        c=Clock(); b=MethodBudget(10,clock=c); identity=[]; remaining=[]
        class FakeModel:
            budget=b
            def as_solver_dict(self):
                c.advance(11 if name=='export_expiry' else .1)
                return {'c':np.array([1.])}
        class Session:
            count=0
            def solve(self,payload,remaining_s,budget):
                require(budget is b); identity.append(id(budget)); remaining.append(remaining_s)
                self.count+=1; c.advance(11 if name=='late_solver' else .2)
                return {'budget_valid':True,'accepted_for_evaluation':True,'x':[1.],
                        'exitflag':1}
        model=FakeModel(); session=Session(); evaluations=[]; feedbacks=[]
        def decode(*a): c.advance(.1); return {'fixture':True}
        def evaluate(*a):
            c.advance(.2)
            state=('THERMAL_VIOLATION' if name in ('violation_before_expiry','feedback_expiry','feedback_late_return','two_rounds')
                   and not evaluations else 'SAFE')
            if name=='unresolved': state='UNRESOLVED'
            if name=='safe_exact_deadline': c.now=b.deadline
            r={'state':state,'rankable_energy':state=='SAFE','safe_upper_bound_J':'2',
               'completed_at_elapsed_s':b.elapsed,'witnesses':[{'id':'kept'}] if state=='THERMAL_VIOLATION' else []}
            evaluations.append(r)
            if name in ('safe_before_expiry','violation_before_expiry'): c.advance(11)
            return r
        def feedback(*a):
            feedbacks.append(1)
            if name=='feedback_expiry': c.advance(11); b.check()
            if name=='feedback_late_return': c.advance(11)
            c.advance(.1); return {'rows_added':1}
        with patch.object(milp,'decode',decode),patch.object(milp,'evaluate_model_candidate',evaluate),patch.object(milp,'add_thermal_feedback',feedback):
            r=milp.solve_with_feedback(model,session,{},budget=b)
        save(out/(name+'.json'), {'result':r,'timing':b.summary(),'round_remaining_s':remaining})
        if name in ('late_solver','export_expiry'):
            require(not evaluations and r['state']=='UNRESOLVED')
        elif name=='safe_before_expiry':
            require(r['state']=='SAFE' and r['safe_upper_bound_J']=='2')
        elif name=='violation_before_expiry':
            require(r['evaluation']['witnesses']==[{'id':'kept'}] and not feedbacks)
        elif name=='unresolved':
            require(not feedbacks and r['state']=='UNRESOLVED')
        elif name=='feedback_expiry':
            require(r['state']=='UNRESOLVED' and len(remaining)==1)
        elif name=='feedback_late_return':
            require(r['state']=='UNRESOLVED' and not r['feedback'])
            require(len(r['late_feedback_diagnostics'])==1 and len(remaining)==1)
        elif name=='safe_exact_deadline':
            require(r['state']=='UNRESOLVED' and r['safe_upper_bound_J'] is None)
        elif name=='two_rounds':
            require(r['state']=='SAFE' and len(remaining)==2 and remaining[1]<remaining[0])
        require(len(set(identity))<=1)
        require(sum(b.summary()['phases_exclusive_s'].values())<=b.elapsed+1e-9)
    for case in ('export_expiry','late_solver','safe_before_expiry','violation_before_expiry',
                 'unresolved','feedback_expiry','feedback_late_return','safe_exact_deadline','two_rounds'):
        check(case,lambda case=case:feedback_flow(case))

    def transport_timing(fail_at):
        import matlab_bridge as bridge
        c=Clock(); b=MethodBudget(10,clock=c); c.advance(2)
        folder=out/('transport_'+str(fail_at)); folder.mkdir()
        session=bridge.MatlabSession.__new__(bridge.MatlabSession)
        session.clock=c; session.budget=b; session.deadline=b.deadline
        session.started=b.start; session.workdir=folder; session.counter=0
        session.closed=False; session.request_blocked=False; session.proc=None
        original_prepare=bridge._prepare; original_json=bridge._json
        payload={'c':np.array([1.]),'A':csr_matrix((0,1)), 'Aeq':csr_matrix((0,1)),
                 'b':[], 'beq':[], 'lb':[0.], 'ub':[1.], 'intcon':np.array([0])}
        def prepare(value):
            c.advance(9 if fail_at=='conversion' else .2)
            return original_prepare(value)
        def serialize(path,*args,**kw):
            c.advance(9 if fail_at=='serialization' else .3)
            Path(path).write_bytes(b'fixture only; mocked MAT transport')
        def read(path,deadline,*args):
            require(deadline==b.deadline,'deadline reset')
            if fail_at=='wait':
                c.now=deadline
                raise bridge.PublicationTimeout(path,{'fixture':True})
            c.advance(.4)
            return {'status':'SOLVED','x':[1.],'intlinprog_entered':True,'exitflag':1},{}
        def archive(path,value):
            original_json(path,value)
            if path.name.endswith('.python.json') and fail_at=='archive': c.advance(9)
            else: c.advance(.01)
        with patch.object(bridge,'_prepare',prepare), patch.object(bridge,'savemat',serialize), \
             patch.object(bridge,'_read_json_until',read), patch.object(bridge,'_json',archive):
            returned=session.solve(payload,remaining_s=b.remaining,budget=b)
        require(session.counter==1 and b.deadline==110)
        phases=b.summary()['phases_exclusive_s']
        require('transport_numerical_conversion' in phases)
        require(sum(phases.values())<=b.elapsed+1e-9,'nested timing double counted')
        if fail_at:
            require(not returned['budget_valid'] and not returned['accepted_for_evaluation'])
            if fail_at in ('conversion','serialization'):
                require(not list(folder.glob('*.request.json')),'late work submitted')
            if fail_at=='wait': require(session.request_blocked)
        else:
            require(returned['accepted_for_evaluation'] and returned['intlinprog_entered'])
            require(set(['transport_mat_serialization','transport_request_publication',
                         'solver_wait_and_response_read']) <= set(phases))
        save(folder/'check.json',{'result':returned,'timing':b.summary(),
                                 'scope':'mock transport accounting, no MATLAB execution'})
    for point in (None,'conversion','serialization','wait','archive'):
        check('transport_accounting_'+str(point),lambda point=point:transport_timing(point))

    hashes={name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in SOURCES}
    hashes['run_method_precheck.py']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result={'status':'PASS' if all(r['passed'] for r in records) else 'FAIL',
            'passed':sum(r['passed'] for r in records),'total':len(records),'checks':records,
            'source_sha256':hashes,'scope':'deterministic interface checks; not research results',
            'formal_comparisons_run':False}
    save(out/'checks.json',result)
    print(json.dumps(result,ensure_ascii=False))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(); result=run(args.out)
    raise SystemExit(0 if result['status']=='PASS' else 1)
