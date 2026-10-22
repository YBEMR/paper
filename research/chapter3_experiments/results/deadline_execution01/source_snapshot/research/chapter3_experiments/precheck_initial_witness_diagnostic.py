"""Admission and budget checks for the solver-free initial witness diagnostic.

Two existing small correctness fixtures and injected state-machine receipts
are used. This script never constructs the original benchmark, starts MATLAB
or calls an integer solver. It produces the entry credential required before
the separately authorized one-shot original-scale diagnostic.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import time
import traceback
from unittest.mock import patch

import numpy as np
from scipy import sparse

import initial_point
import matlab_bridge
import milp
from inputs import load_config
from run_milp_precheck import fixtures, independent_check, candidate_key
import run_initial_witness_diagnostic as entry

HERE=Path(__file__).resolve().parent


def require(value,message='assertion failed'):
    if not value:
        raise AssertionError(message)


def save(path,value):
    def encode(item):
        if isinstance(item,np.ndarray): return item.tolist()
        if isinstance(item,np.generic): return item.item()
        return str(item)
    path=Path(path)
    temporary=path.with_name(path.name+f'.{os.getpid()}.tmp')
    payload=(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False,default=encode)+'\n').encode('utf-8')
    for attempt in range(4):
        try:
            temporary.write_bytes(payload);os.replace(temporary,path);return
        except OSError as exc:
            if exc.errno not in (13,22,32) or attempt==3: raise
            time.sleep((.01,.05,.1)[attempt])


class Clock:
    def __init__(self): self.now=100.
    def __call__(self): return self.now
    def advance(self,value): self.now+=value


class FakeModel:
    def __init__(self,instance,budget):
        self.instance,self.budget=instance,budget
        self.names=['fixture_point'];self.c=[1.];self.lb=[0.];self.ub=[1.]
        self.integer=[0];self.logical_binary=[0];self.rows=[]
        self.input_sha256=milp._digest(instance)
    def summary(self): return {'fixture':True,'variables':1,'rows':0}
    def as_solver_dict(self):
        return {'c':np.array([1.]),'lb':np.array([0.]),'ub':np.array([1.]),
                'A':sparse.csc_matrix((0,1)),'b':np.array([]),
                'Aeq':sparse.csc_matrix((0,1)),'beq':np.array([]),'intcon':np.array([0])}


def fake_preparation(instance,*,state='SAFE_POINT_READY',safe_time=3.,point_time=4.):
    candidate={'scenes':{}}
    evaluation={'state':'SAFE','rankable_energy':True,'safe_upper_bound_J':'2',
                'completed_at_elapsed_s':safe_time,'weighted_energy_J':['1.9','2'],
                'evidence_identity':{'input_sha256':milp._digest(instance),
                                     'candidate_sha256':milp._digest(candidate)}}
    return {'state':state,'reason':'INITIAL_POINT_READY','witness':{
            'candidate':candidate,'evaluation':evaluation,'schedule_completed_at_s':2.},
            'x0':np.array([1.]),'attempts':[],
            'completion':{'state':'INITIAL_POINT_READY','completed_at_s':point_time,
                          'numerical_acceptance':{'accepted_numerically':True},
                          'decoded_roundtrip':True}}


def run(out,core_precheck):
    out.mkdir(parents=True,exist_ok=False)
    before=entry.source_hashes()
    checks=[];details={};integer_calls=[];matlab_calls=[]
    started=time.monotonic()

    def check(name,function):
        try:
            value=function();checks.append({'name':name,'passed':True})
            if value is not None: details[name]=value
        except Exception as exc:
            checks.append({'name':name,'passed':False,'error':repr(exc),
                           'traceback':traceback.format_exc()})
        save(out/'checks_in_progress.json',{'checks':checks,'details':details})

    def denied_solver(*args,**kwargs):
        integer_calls.append('forbidden');raise AssertionError('integer solver call forbidden')
    def denied_matlab(*args,**kwargs):
        matlab_calls.append('forbidden');raise AssertionError('MATLAB startup forbidden')

    def reject(function,path):
        try: function(path)
        except (ValueError,FileNotFoundError,KeyError,TypeError): return
        raise AssertionError('invalid prerequisite accepted: '+str(path))

    with patch.object(matlab_bridge.MatlabSession,'__init__',side_effect=denied_matlab),\
         patch.object(initial_point,'solve_with_initial_witness',side_effect=denied_solver):
        check('admission/actual_109_core_record',lambda:entry.validate_core_precheck(core_precheck))
        original=json.loads(core_precheck.read_text(encoding='utf-8-sig'))
        tests=[('failed',lambda p:p.update(passed=False)),
               ('missing_check',lambda p:(p['checks'].pop(),p.update(count=108))),
               ('failed_individual_check',lambda p:p['checks'][0].update(passed=False)),
               ('wrong_flags',lambda p:p['flags'].update(strengthen_energy_lower_bounds=False)),
               ('hash_mismatch',lambda p:p['source_sha256'].update({next(k for k in p['source_sha256'] if k.endswith('config_v01.json')):'0'*64})),
               ('missing_native_check',lambda p:[c.update(name='removed_native_item') for c in p['checks']
                    if c['name']=='native/one_stage_same_180s_method_budget_and_continuous_safe_receipt']),
               ('missing_hashes',lambda p:p.pop('source_sha256'))]
        for name,change in tests:
            payload=deepcopy(original);change(payload);path=out/('bad_core_'+name+'.json');save(path,payload)
            check('admission/core_reject_'+name,lambda p=path:reject(entry.validate_core_precheck,p))
        check('admission/core_reject_missing_file',lambda:reject(entry.validate_core_precheck,out/'missing.json'))

        valid_entry={'passed':True,'count':1,'checks':[{'name':'synthetic_entry','passed':True}],
                     'source_sha256':before,'seconds':180,'flags':entry.FLAGS,
                     'original_benchmark_built_or_solved':False,'integer_solver_calls':0}
        valid_path=out/'synthetic_valid_entry.json';save(valid_path,valid_entry)
        check('admission/entry_metadata_current_hashes_and_protocol',lambda:entry.validate_entry_precheck(valid_path))
        entry_mutations=[('failed',lambda p:p.update(passed=False)),
                         ('individual_failure',lambda p:p['checks'][0].update(passed=False)),
                         ('count_mismatch',lambda p:p.update(count=2)),
                         ('seconds',lambda p:p.update(seconds=900)),
                         ('flags',lambda p:p['flags'].update(relax_auxiliary_integrality=False)),
                         ('original_scale_used',lambda p:p.update(original_benchmark_built_or_solved=True)),
                         ('solver_calls',lambda p:p.update(integer_solver_calls=1)),
                         ('hash',lambda p:p['source_sha256'].update({next(iter(p['source_sha256'])):'0'*64})),
                         ('missing_hash',lambda p:p.pop('source_sha256'))]
        for name,change in entry_mutations:
            payload=deepcopy(valid_entry);change(payload);path=out/('bad_entry_'+name+'.json');save(path,payload)
            check('admission/entry_reject_'+name,lambda p=path:reject(entry.validate_entry_precheck,p))

        def invalid_original_entry_cannot_read_workload():
            destination=out/'forbidden_original_output'
            with patch.object(entry,'build_instance',side_effect=AssertionError('original input read')) as called:
                try:
                    entry.run_original(destination,out/'missing_core.json',valid_path)
                except FileNotFoundError:
                    pass
                else:
                    raise AssertionError('original invocation passed without core record')
            require(called.call_count==0 and not destination.exists())
        check('admission/missing_core_stops_before_original_workload_read',invalid_original_entry_cannot_read_workload)

        def claim_once():
            folder=out/'claim_fixture';folder.mkdir()
            path=folder/'checks.json';save(path,valid_entry)
            value=entry.claim_original_run(path,folder/'unused_original_output')
            try: entry.claim_original_run(path,folder/'another_unused_output')
            except (FileExistsError,ValueError): pass
            else: raise AssertionError('second original-run claim accepted')
            claim=folder/'original_seed_run_claim.json'
            require(claim.exists() and not (folder/'unused_original_output').exists())
            return {'first_claim':value,'record':json.loads(claim.read_text(encoding='utf-8-sig')),
                    'original_benchmark_ran':False}
        check('admission/one_shot_claim_is_exclusive_without_running_original',claim_once)

        for name in ('one_stage_energy','chain_fractional'):
            def real_fixture(name=name):
                shared={};budget_ids=[]
                def loader(budget):
                    budget_ids.append(id(budget));loaded=load_config()
                    instance,starts=fixtures(loaded)[name]
                    require(instance['id'].startswith('fixture_'))
                    shared['starts']=starts
                    return loaded,instance
                def builder(instance,cfg,**kwargs):
                    budget_ids.append(id(kwargs['budget']))
                    require({k:kwargs[k] for k in entry.FLAGS}==entry.FLAGS)
                    return milp.build_model(instance,cfg,starts=shared['starts'],**kwargs)
                def prepare(model,accuracy,budget):
                    budget_ids.append(id(budget))
                    return initial_point.prepare_initial_witness(model,accuracy,budget,starts=shared['starts'])
                result=entry.execute_seed_diagnostic(loader,out/('actual_'+name),seconds=180,
                                                     model_builder=builder,prepare=prepare)
                require(result['state']=='SAFE' and result['safe_candidate'] and result['safe_upper_bound_J'])
                require(result['model_complete'] and result['point_ready'])
                require(result['integer_solver_entered'] is False and result['solver_request_attempts']==0)
                require(result['matlab_actual_acceptance']=='NOT_TESTED')
                require(len(set(budget_ids))==1 and result['timing']['limit_s']==180)
                vector=out/('actual_'+name)/'initial_point_vector.json'
                require(vector.exists(),'complete admitted vector not archived')
                require('x0' not in result['initialisation'])
                require(not result.get('independently_proven_optimal',False))
                loaded=load_config();instance,_=fixtures(loaded)[name]
                require(independent_check(instance,result['safe_candidate'])['valid'])
                return result
            check('actual/'+name+'/seed_safe_point_ready_same_budget_without_solver',real_fixture)

        def fake_case(name,*,build_error=None,prepare_error=None,advance=0.,kind='ready',safe_time=3.,point_time=4.):
            clock=Clock();budget_ids=[];instance={'id':'fixture_entry_'+name}
            def loader(budget):
                budget_ids.append(id(budget));clock.advance(1.)
                return {'accuracy_targets':{}},instance
            def builder(loaded,cfg,budget,progress,**flags):
                budget_ids.append(id(budget));require(flags==entry.FLAGS)
                clock.advance(1.)
                if build_error=='budget': clock.advance(180.);budget.check()
                if build_error=='memory': raise MemoryError('injected construction memory')
                if build_error=='exception': raise RuntimeError('injected construction error')
                return FakeModel(loaded,budget)
            def prepare(model,accuracy,budget):
                budget_ids.append(id(budget));clock.advance(advance)
                if prepare_error=='memory': raise MemoryError('injected preparation memory')
                if prepare_error=='exception': raise RuntimeError('injected preparation error')
                prepared=fake_preparation(instance,safe_time=safe_time,point_time=point_time)
                if kind in ('unknown','violation'):
                    prepared.update(state='UNRESOLVED',witness=None,x0=None,completion=None,
                                    reason='injected '+kind)
                    prepared['attempts']=[{'evaluation':{'state':'THERMAL_VIOLATION' if kind=='violation' else 'UNRESOLVED',
                                                       'rankable_energy':False,'safe_upper_bound_J':None}}]
                elif kind=='safe_without_point':
                    prepared.update(state='SAFE_POINT_REJECTED',x0=None)
                    prepared['completion'].update(state='INITIAL_POINT_REJECTED')
                return prepared
            result=entry.execute_seed_diagnostic(loader,out/('fake_'+name),seconds=180,clock=clock,
                                                 model_builder=builder,prepare=prepare)
            require(len(set(budget_ids))==1 and result['timing']['limit_s']==180)
            require(not result['integer_solver_entered'] and result['solver_request_attempts']==0)
            require(result['matlab_actual_acceptance']=='NOT_TESTED')
            return result

        def build_interrupted():
            result=fake_case('build_interrupted',build_error='budget')
            require(result['state']=='UNRESOLVED' and not result['model_complete'])
            require(result['safe_upper_bound_J'] is None and not result['point_ready'])
            return result
        check('budget/construction_expiry_never_returns_solver_ready_model',build_interrupted)

        def timely_witness_late_completion():
            result=fake_case('late_completion',advance=180.,safe_time=3.,point_time=182.)
            require(result['state']=='SAFE' and result['safe_upper_bound_J']=='2')
            require(not result['point_ready'])
            require(not result['matrix_complete'])
            require(not (out/'fake_late_completion/initial_point_vector.json').exists())
            return result
        check('budget/pre_deadline_safe_survives_late_completion_but_late_vector_not_admitted',timely_witness_late_completion)

        def timely_completion_late_return():
            result=fake_case('late_return',advance=180.,safe_time=3.,point_time=4.)
            require(result['state']=='SAFE' and result['safe_upper_bound_J']=='2')
            require(result['point_ready'])
            require(result['matrix_complete'])
            require((out/'fake_late_return/initial_point_vector.json').exists())
            return result
        check('budget/already_completed_safe_and_point_survive_late_outer_return',timely_completion_late_return)

        def late_safe():
            result=fake_case('late_safe',advance=180.,safe_time=180.,point_time=182.)
            require(result['state']=='UNRESOLVED' and result['safe_upper_bound_J'] is None)
            require(not result['point_ready'])
            return result
        check('budget/safe_commit_at_deadline_is_not_in_budget_evidence',late_safe)

        for kind in ('unknown','violation','safe_without_point'):
            def status(kind=kind):
                result=fake_case(kind,kind=kind,advance=3.)
                safe=kind=='safe_without_point'
                require(result['state']==('SAFE' if safe else 'UNRESOLVED'))
                require((result['safe_upper_bound_J'] is not None)==safe and not result['point_ready'])
                return result
            check('state/'+kind+'_retains_exact_evidence_status',status)
        for stage in ('build','prepare'):
            for error in ('memory','exception'):
                def failed(stage=stage,error=error):
                    result=fake_case(stage+'_'+error,**{stage+'_error':error})
                    require(result['state']=='UNRESOLVED' and result['safe_upper_bound_J'] is None)
                    require(not result['point_ready'])
                    return result
                check('state/'+stage+'_'+error+'_cannot_generate_false_safe',failed)

    check('scope/no_matlab_start_or_integer_solver_calls',lambda:require(not matlab_calls and not integer_calls))
    check('integrity/source_hashes_unchanged',lambda:require(before==entry.source_hashes()))
    report={'passed':all(row['passed'] for row in checks),'count':len(checks),'checks':checks,
            'details':details,'source_sha256':before,'seconds':entry.LIMIT_SECONDS,'flags':entry.FLAGS,
            'original_benchmark_built_or_solved':False,'integer_solver_calls':len(integer_calls),
            'matlab_startups':len(matlab_calls),'wall_seconds':time.monotonic()-started}
    save(out/'checks.json',report)
    print(json.dumps({'passed':report['passed'],'count':report['count'],'out':str(out)},ensure_ascii=False))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--core-precheck',type=Path,default=HERE/'results/initial_point_precheck01/checks.json')
    args=parser.parse_args()
    raise SystemExit(0 if run(args.out,args.core_precheck)['passed'] else 1)
