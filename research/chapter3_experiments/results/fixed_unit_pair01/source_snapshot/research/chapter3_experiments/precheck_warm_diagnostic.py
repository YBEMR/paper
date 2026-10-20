"""Warm diagnostic admission, checkpoint, accounting and small native checks.

No original research instance is built or solved. The optional native test
uses the existing one-Stage fixture under one 180 s method clock. The 900 s
field in the final credential declares the subsequent original-call protocol,
not a 900 s allowance for this precheck or its fixture.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import time
import traceback
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

import diagnostic_search
import initial_point
import milp
from inputs import load_config
from run_milp_precheck import fixtures
from timing import MethodBudget
from thermal import Exhausted
from precheck_initial_witness_diagnostic import Clock,FakeModel,fake_preparation,save,require
import run_warm_diagnostic as warm

HERE=Path(__file__).resolve().parent


def returned_safe(candidate,upper='2',interval=None):
    interval=interval or [upper,upper]
    evaluation={'state':'SAFE','rankable_energy':True,'safe_upper_bound_J':upper,
                'weighted_energy_J':interval,'completed_at_elapsed_s':6.}
    return {'state':'SAFE','safe_candidate':candidate,'safe_upper_bound_J':upper,
            'evaluation':evaluation,'reason':'SAFE_ENGINEERING_CONVERGENCE','rounds':[],
            'feedback':[],'independently_proven_optimal':False,
            'independently_proven_infeasible':False,'remaining_domain':'retained'}


def run(out,with_matlab=False):
    out.mkdir(parents=True,exist_ok=False)
    before=warm.source_hashes();started=time.monotonic()
    checks=[];details={};native_passed=False
    snapshot=out/'source_snapshot'
    for name,path in warm.source_paths().items():
        target=snapshot/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(path.read_bytes())

    def check(name,function):
        try:
            value=function();checks.append({'name':name,'passed':True})
            if value is not None: details[name]=value
            passed=True
        except Exception as exc:
            checks.append({'name':name,'passed':False,'error':repr(exc),
                           'traceback':traceback.format_exc()});passed=False
        save(out/'checks_in_progress.json',{'checks':checks,'details':details})
        return passed

    valid={'passed':True,'count':1,'checks':[{'name':'synthetic_gate','passed':True}],
           'source_sha256':before,'seconds':900,'flags':dict(warm.FLAGS),
           'native_small_domain_passed':True,'original_benchmark_built_or_solved':False}
    valid_path=out/'synthetic_valid_gate.json';save(valid_path,valid)
    check('gate/current_sources_and_declared_protocol',lambda:warm.validate_precheck(valid_path))
    mutations=[('failed',lambda p:p.update(passed=False)),
               ('failed_check',lambda p:p['checks'][0].update(passed=False)),
               ('count_mismatch',lambda p:p.update(count=2)),
               ('wrong_seconds',lambda p:p.update(seconds=180)),
               ('wrong_flags',lambda p:p['flags'].update(strengthen_energy_lower_bounds=False)),
               ('hash_mismatch',lambda p:p['source_sha256'].update({next(iter(p['source_sha256'])):'0'*64})),
               ('missing_hashes',lambda p:p.pop('source_sha256')),
               ('native_not_run',lambda p:p.update(native_small_domain_passed=False)),
               ('original_was_used',lambda p:p.update(original_benchmark_built_or_solved=True))]
    def reject(path):
        try:warm.validate_precheck(path)
        except (ValueError,KeyError,TypeError,FileNotFoundError):return
        raise AssertionError('invalid warm credential accepted')
    for name,change in mutations:
        value=deepcopy(valid);change(value);path=out/('bad_gate_'+name+'.json');save(path,value)
        check('gate/reject_'+name,lambda path=path:reject(path))
    check('gate/reject_missing_record',lambda:reject(out/'missing.json'))

    def once_claim():
        folder=out/'claim_fixture';folder.mkdir()
        path=folder/'checks.json';save(path,valid)
        first=warm.claim_original_run(path,folder/'unused_original_output')
        try:warm.claim_original_run(path,folder/'second_unused_original_output')
        except FileExistsError:pass
        else:raise AssertionError('second original run claim accepted')
        require(not (folder/'unused_original_output').exists())
        return {'claim':str(first),'content':json.loads(first.read_text(encoding='utf-8-sig')),
                'original_problem_executed':False}
    check('gate/claim_is_exclusive_without_executing_original',once_claim)

    def mocked_invocation(name,mode='replay',checkpoint_mode=None):
        clock=Clock();ids=[];calls=[];sessions=[]
        instance={'id':'fixture_warm_'+name}
        def loader(budget):
            ids.append(id(budget));clock.advance(1.)
            return {'accuracy_targets':{}},instance
        def builder(loaded,config,budget,progress,**flags):
            require(flags==warm.FLAGS);ids.append(id(budget));clock.advance(1.)
            return FakeModel(loaded,budget)
        class Session:
            counter=0;event_consumer=None
            def __init__(self,path,total_budget_s,budget):
                self.workdir=path;self.budget=budget;sessions.append(self)
                ids.append(id(budget));clock.advance(1.)
            def solve(self,payload,**kwargs):
                self.counter+=1;calls.append(kwargs);ids.append(id(kwargs['budget']))
                require(kwargs['budget'] is self.budget);clock.advance(.1)
                return {'status':'MOCK'}
            def close(self):clock.advance(.2)
        def prepare(model,accuracy,budget,*args):
            ids.append(id(budget));clock.advance(1.)
            return fake_preparation(instance,safe_time=3.5,point_time=3.9)
        original_save=warm.seed.save
        def counted_save(path,value):
            if Path(path).name=='initial_receipt_checkpoint.json':
                clock.advance(901. if checkpoint_mode=='expire' else 1.)
                if checkpoint_mode=='fail':raise OSError('injected checkpoint failure')
            original_save(path,value)
        def solver(model,session,accuracy,budget):
            ids.append(id(budget))
            if mode=='error':raise RuntimeError('injected solver error')
            if mode=='timeout':clock.advance(901.);raise Exhausted('injected solver timeout')
            session.solve(model.as_solver_dict(),remaining_s=budget.remaining,budget=budget)
            if mode=='two_rounds':
                session.solve(model.as_solver_dict(),remaining_s=budget.remaining,budget=budget)
            clock.advance(1.)
            if mode=='improve':return returned_safe({'scenes':{}},'1.5',['1.4','1.5'])
            if mode=='overlap_improve':return returned_safe({'scenes':{}},'1.95',['1.85','1.95'])
            return returned_safe({'scenes':{}},'2',['1.9','2'])
        with patch.object(initial_point,'prepare_initial_witness',side_effect=prepare),\
             patch.object(diagnostic_search,'solve_diagnostic',side_effect=solver),\
             patch.object(warm.seed,'save',side_effect=counted_save):
            result=warm.execute_warm(loader,out/('fake_'+name),seconds=900,clock=clock,
                                     model_builder=builder,session_factory=Session)
        require(len(set(ids))==1 and len(sessions)==1)
        require(result['timing']['limit_s']==900)
        require(result['state']=='SAFE' and result['initial_safe_upper_bound_J']=='2')
        require(result['timing']['phases_exclusive_s'].get('initial_receipt_checkpoint',0)>0)
        require(result['timing']['method_elapsed_s']>=4.)
        if calls:
            require('x0' in calls[0],'first request lost admitted x0')
            require(all('x0' not in call for call in calls[1:]),'later request reuses initial x0')
        return result,calls

    def replay():
        result,calls=mocked_invocation('seed_replay')
        require(calls and result['safe_upper_bound_J']=='2')
        require(not result['milp_improved_initial_upper_bound'] and not result['strict_energy_improvement_certified'])
        require(result['initial_checkpoint']['completed'])
        return result
    check('warm/seed_replay_is_not_milp_energy_improvement',replay)

    def improves():
        result,calls=mocked_invocation('solver_improves',mode='improve')
        require(calls and result['safe_upper_bound_J']=='1.5')
        require(result['milp_improved_initial_upper_bound'] and result['strict_energy_improvement_certified'])
        require(result['milp_safe_upper_bound_J']=='1.5' and result['initial_safe_upper_bound_J']=='2')
        return result
    check('warm/solver_improvement_and_initial_energy_separately_recorded',improves)

    def intervals_overlap():
        result,calls=mocked_invocation('overlapping_energy_intervals',mode='overlap_improve')
        require(result['milp_improved_initial_upper_bound'] and not result['strict_energy_improvement_certified'])
        return result
    check('warm/smaller_upper_endpoint_is_not_strict_energy_gain_when_intervals_overlap',intervals_overlap)

    def checkpoint_expiry():
        result,calls=mocked_invocation('checkpoint_expiry',checkpoint_mode='expire')
        require(not calls and result['solver_diagnostic'] is None)
        require(result['safe_upper_bound_J']=='2' and result['budget_exhausted'])
        require(result['initial_checkpoint']['completed_at_s']>=900)
        return result
    check('warm/checkpoint_budget_exhaustion_retains_safe_without_solver_or_cold_restart',checkpoint_expiry)

    def checkpoint_failure():
        result,calls=mocked_invocation('checkpoint_error',checkpoint_mode='fail')
        require(result['initial_checkpoint'].get('error') and result['safe_upper_bound_J']=='2')
        require(calls and all('x0' in c for c in calls))
        return result
    check('warm/checkpoint_io_error_preserves_safe_and_never_starts_cold',checkpoint_failure)

    for mode in ('error','timeout'):
        def interrupted(mode=mode):
            result,calls=mocked_invocation('solver_'+mode,mode=mode)
            require(result['safe_upper_bound_J']=='2' and result['solver_diagnostic']['state']=='UNRESOLVED')
            require(not result['milp_improved_initial_upper_bound'])
            return result
        check('warm/solver_'+mode+'_retains_initial_safe',interrupted)
    check('warm/only_first_round_receives_x0',lambda:mocked_invocation('two_rounds',mode='two_rounds')[0])

    def late_callback():
        clock=Clock();budget=MethodBudget(10,clock=clock)
        folder=out/'late_callback';folder.mkdir()
        evaluated=[]
        def evaluation(model,candidate,accuracy,budget):
            evaluated.append(candidate)
            return {'state':'SAFE','rankable_energy':True,'completed_at_elapsed_s':1.,
                    'safe_upper_bound_J':'2'}
        recorder=diagnostic_search.Recorder(None,{},budget,folder,
                                           decoder=lambda model,x:{'fixture':x[0]},evaluator=evaluation)
        recorder.assess([1.],'early')
        before_best=deepcopy(recorder.best)
        prefix=folder/'request'
        save(Path(str(prefix)+'.event_000001.json'),{'kind':'callback','x':[.5],
                                                   'values':{'lowerbound':999}})
        clock.advance(10.)
        recorder.poll(prefix)
        require(recorder.best==before_best and len(evaluated)==1)
        require(recorder.event_count==0 and not recorder.summary()['solver_bounds_independently_certified'])
        return recorder.summary()
    check('budget/late_callback_neither_creates_new_safe_nor_promotes_internal_bound',late_callback)

    def late_final():
        clock=Clock();budget=MethodBudget(10,clock=clock)
        folder=out/'late_final';folder.mkdir()
        class Session:
            workdir=folder/'worker';event_consumer=None
            def solve(self,*args,**kwargs):
                clock.advance(10.)
                return {'x':[1.],'budget_valid':True,'accepted_for_evaluation':True,'exitflag':1}
        with patch.object(diagnostic_search,'evaluate_model_candidate') as evaluation:
            result=diagnostic_search.solve_diagnostic(SimpleNamespace(as_solver_dict=lambda:{}),Session(),{},budget)
        require(result['state']=='UNRESOLVED' and result['safe_upper_bound_J'] is None)
        require(not result['diagnostic']['evaluations'] and evaluation.call_count==0)
        return result
    check('budget/late_final_vector_is_not_decoded_or_evaluated_as_budget_evidence',late_final)

    if with_matlab and all(row['passed'] for row in checks):
        def native():
            shared={}
            def loader(budget):
                config=load_config();instance,starts=fixtures(config)['one_stage_energy']
                shared['starts']=starts
                return config,instance
            def builder(instance,config,**kwargs):
                require({k:kwargs[k] for k in warm.FLAGS}==warm.FLAGS)
                return milp.build_model(instance,config,starts=shared['starts'],**kwargs)
            def solve(model,session,accuracy,budget,checkpoint):
                return initial_point.solve_with_initial_witness(model,session,accuracy,budget,
                            starts=shared['starts'],checkpoint=checkpoint)
            result=warm.execute_warm(loader,out/'native_one_stage',seconds=180,
                                     model_builder=builder,solver=solve)
            require(result['state']=='SAFE' and result['safe_upper_bound_J'])
            require(result['initialisation']['completion']['state']=='INITIAL_POINT_READY')
            require(result['initial_checkpoint']['completed'])
            require((out/'native_one_stage/initial_receipt_checkpoint.json').exists())
            require(result['timing']['limit_s']==180 and result['timing']['phases_exclusive_s']['initial_receipt_checkpoint']>=0)
            require(result['initial_safe_upper_bound_J'] is not None and result['first_initial_safe_s']<180)
            diagnostic=result['solver_diagnostic'];require(diagnostic is not None)
            rounds=diagnostic.get('rounds',[])
            require(rounds and rounds[0].get('initial_point',{}).get('provided') is True)
            require(all(not row.get('initial_point',{}).get('provided',False) for row in rounds[1:]))
            require(result['solver_request_attempts']>=1 and result['integer_solver_entered'] is True)
            require(not result['independently_proven_optimal'])
            require(result['problem_id'].startswith('fixture_') and not result['candidate_and_cache_shared_between_calls'])
            return {'result_path':str((out/'native_one_stage/result.json').resolve()),'result':result,
                    'scope':'small native correctness; no original research run and no performance claim'}
        native_passed=check('native/one_stage_checkpoint_actual_x0_and_separate_energies_same_180s_budget',native)

    check('integrity/source_hashes_unchanged',lambda:require(before==warm.source_hashes()))
    report={'passed':all(row['passed'] for row in checks),'count':len(checks),'checks':checks,
            'details':details,'source_sha256':before,'seconds':warm.LIMIT_SECONDS,'flags':warm.FLAGS,
            'native_small_domain_passed':native_passed,'original_benchmark_built_or_solved':False,
            'wall_seconds':time.monotonic()-started,'formal_comparison':False}
    save(out/'checks.json',report)
    print(json.dumps({'passed':report['passed'],'count':report['count'],
                      'native_small_domain_passed':native_passed,'out':str(out)},ensure_ascii=False))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--with-matlab',action='store_true')
    args=parser.parse_args()
    raise SystemExit(0 if run(args.out,args.with_matlab)['passed'] else 1)
