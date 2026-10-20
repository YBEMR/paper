"""Small-domain initial witness, numerical completion and x0 checks.

Only the five existing fixtures are used. Cartesian assignments are an
independent correctness oracle and are never inputs to the constructor or
native solver. One optional native invocation starts its 180 s budget before
reading inputs; no original-scale instance is constructed or solved.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
import os
from pathlib import Path
import time
import traceback
from unittest.mock import patch

import numpy as np

import initial_point as initial
import initial_schedule
import diagnostic_search
import matlab_bridge
import milp
from inputs import load_config
from method_runner import execute_milp
from run_milp_precheck import (fixtures, candidate_key, independent_check,
                              structural_checks)
from schedules import validate_schedule
from thermal import Budget, Exhausted
from timing import MethodBudget

HERE = Path(__file__).resolve().parent
CONFIG_SHA = '615be096bfbcb3e7c53ba9b0810d888264d48adbc428f1f7d2f94a5c6a29a4fe'
FLAGS = dict(fix_late_options=True, aggregate_opp_locks=True,
             relax_auxiliary_integrality=True, strengthen_energy_lower_bounds=True)


def require(value, message='assertion failed'):
    if not value:
        raise AssertionError(message)


def save(path, value):
    """Atomic archival; never repeat a calculation after an IO retry."""
    path = Path(path)
    def encode(item):
        if isinstance(item,np.ndarray):
            return item.tolist()
        if isinstance(item,np.generic):
            return item.item()
        return str(item)
    payload = (json.dumps(value, ensure_ascii=False, indent=2,
                          allow_nan=False, default=encode)+'\n').encode('utf-8')
    temporary = path.with_name(path.name+f'.{os.getpid()}.tmp')
    for attempt in range(4):
        try:
            temporary.write_bytes(payload)
            os.replace(temporary, path)
            return
        except OSError as exc:
            if exc.errno not in (13, 22, 32) or attempt == 3:
                raise
            time.sleep((.01, .05, .1)[attempt])


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def model_identity(model):
    """Check complete model identity, rather than numerical x0 alone."""
    payload = dict(names=model.names, rows=model.rows, lb=model.lb, ub=model.ub,
                   integer=model.integer, logical_binary=model.logical_binary,
                   c=model.c, input=model.instance, options=model.options,
                   feedback=model.feedback_log, excluded=sorted(model.excluded_schedules))
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


class Clock:
    def __init__(self):
        self.now = 100.

    def __call__(self):
        return self.now


def prepared_receipt(candidate, energy='2', state='SAFE_POINT_READY'):
    """State-machine fixture; no physical input or energy claim."""
    return {'state': state, 'witness': {'candidate': candidate,
            'evaluation': {'state':'SAFE', 'rankable_energy':True,
                           'safe_upper_bound_J':energy, 'completed_at_elapsed_s':1.},
            'schedule_completed_at_s':.5},
            'x0':np.array([1.]), 'attempts':[],
            'reason':'INITIAL_POINT_READY',
            'completion':{'state':'INITIAL_POINT_READY', 'reason':None,
                          'numerical_acceptance':{'accepted_numerically':True},
                          'decoded_roundtrip':True}}


def state_checks(out, check, model, candidate):
    """Exercise receipts and stop boundaries with injected collaborators."""
    class Session:
        counter = 0
        workdir = out/'mock_session'

    seed = prepared_receipt(candidate)

    def wrapper_case(name, prepared, solver=None, advance=None):
        clock = Clock(); budget = MethodBudget(10, clock=clock)
        def prepare(*args, **kwargs):
            result = deepcopy(prepared)
            if advance:
                clock.now += advance
            return result
        with patch.object(initial, 'prepare_initial_witness', side_effect=prepare):
            with patch.object(diagnostic_search, 'solve_diagnostic', side_effect=solver) as called:
                result = initial.solve_with_initial_witness(model, Session(), {}, budget)
        save(out/(name+'.json'), result)
        return result, called.call_count

    def unready_never_submitted():
        value = deepcopy(seed); value.update(state='SAFE_POINT_REJECTED', x0=None)
        value['completion'].update(state='INITIAL_POINT_REJECTED', reason='injected residual')
        result, calls = wrapper_case('safe_but_x0_rejected', value)
        require(calls == 0 and result['state']=='SAFE')
        require(result['safe_upper_bound_J']=='2' and result['safe_candidate']==candidate)
        require(not result['independently_proven_optimal'])
        return result
    check('state/safe_witness_survives_rejected_x0_without_solver', unready_never_submitted)

    def solver_error_retains():
        result, calls = wrapper_case('solver_error_retains_seed', seed,
                                    solver=RuntimeError('injected solver error'))
        require(calls==1 and result['state']=='SAFE' and result['safe_upper_bound_J']=='2')
        require(not result['independently_proven_infeasible'])
        return result
    check('state/solver_error_preserves_independent_initial_witness', solver_error_retains)

    def expiry_retains():
        result, calls = wrapper_case('expiry_after_safe_receipt', seed, advance=11.)
        require(calls==0 and result['state']=='SAFE' and result['safe_upper_bound_J']=='2')
        return result
    check('state/budget_after_receipt_retains_in_budget_safe_no_submission', expiry_retains)

    def unknown_no_solver():
        value = {'state':'UNRESOLVED', 'witness':None, 'x0':None, 'attempts':[],
                 'completion':None, 'reason':'NO_SAFE_INITIAL_WITNESS'}
        result, calls = wrapper_case('no_safe_seed_unresolved', value)
        require(calls==0 and result['state']=='UNRESOLVED')
        require(result['safe_upper_bound_J'] is None and not result['independently_proven_infeasible'])
        return result
    check('state/construction_unresolved_is_not_infeasibility', unknown_no_solver)

    def solver_better():
        returned = {'state':'SAFE', 'safe_candidate':candidate, 'safe_upper_bound_J':'1.5',
                    'evaluation':{'state':'SAFE', 'rankable_energy':True,
                                  'safe_upper_bound_J':'1.5', 'completed_at_elapsed_s':2.},
                    'rounds':[], 'feedback':[], 'reason':'SAFE_ENGINEERING_CONVERGENCE',
                    'independently_proven_optimal':False, 'independently_proven_infeasible':False}
        result, calls = wrapper_case('solver_improves_seed', seed, solver=lambda *a, **k:returned)
        require(calls==1 and result['safe_upper_bound_J']=='1.5')
        require(result['initialisation']['witness']['evaluation']['safe_upper_bound_J']=='2')
        require(result['solver_diagnostic']==returned)
        return result
    check('state/initial_energy_and_solver_improvement_recorded_separately', solver_better)

    def solver_worse():
        returned = {'state':'SAFE', 'safe_candidate':candidate, 'safe_upper_bound_J':'3',
                    'evaluation':{'state':'SAFE', 'rankable_energy':True,
                                  'safe_upper_bound_J':'3', 'completed_at_elapsed_s':2.},
                    'rounds':[], 'feedback':[], 'reason':'SAFE_INCUMBENT',
                    'independently_proven_optimal':False, 'independently_proven_infeasible':False}
        result, calls = wrapper_case('solver_worse_than_seed', seed, solver=lambda *a, **k:returned)
        require(calls==1 and result['safe_upper_bound_J']=='2')
        require(result['solver_diagnostic']==returned)
        return result
    check('state/worse_solver_candidate_does_not_replace_initial_safe_upper_bound', solver_worse)

    def inject_once():
        class Raw:
            workdir = out/'one_time_transport_mock'
            event_consumer = None
            def __init__(self): self.calls=[]
            def solve(self, payload, **kwargs):
                self.calls.append(kwargs)
                return {'state':'mock'}
        raw=Raw(); vector=np.array([1.]); wrapped=initial._InitialSession(raw,vector)
        wrapped.solve({'fixture':True},remaining_s=5.)
        wrapped.solve({'fixture':True},remaining_s=4.)
        require(raw.calls[0]['x0'] is vector and 'x0' not in raw.calls[1])
        wrapped.event_consumer='callback'
        require(raw.event_consumer=='callback' and wrapped.event_consumer=='callback')
    check('transport/x0_is_passed_once_and_never_becomes_a_constraint',inject_once)


def preparation_checks(out, check, model, candidate, actual_receipt):
    """Keep witness acceptance separate from numerical vector completion."""
    def attempt():
        return {'status':'COMPLETE_LEGAL_CANDIDATE','candidate':deepcopy(candidate)}

    def unresolved_evaluation(state):
        value={'state':state,'rankable_energy':False,'safe_upper_bound_J':None,
               'violations':([{'node':'injected','time_s':'0'}]
                             if state=='THERMAL_VIOLATION' else [])}
        budget=MethodBudget(10)
        with patch.object(initial,'iter_initial_candidates',return_value=iter([attempt()])):
            with patch.object(initial,'evaluate_model_candidate',return_value=value):
                with patch.object(initial,'complete_initial_point') as called:
                    result=initial.prepare_initial_witness(model,{},budget)
        require(result['state']=='UNRESOLVED' and result['witness'] is None and result['x0'] is None)
        require(called.call_count==0 and not result['independently_proven_infeasible'])
        require(result['attempts'][0]['evaluation']==value)
        return result
    for state in ('UNRESOLVED','THERMAL_VIOLATION','INVALID_SCHEDULE'):
        check('preparation/'+state.lower()+'_cannot_become_x0_or_infeasibility',
              lambda state=state:unresolved_evaluation(state))

    def completion_expiry():
        clock=Clock(); budget=MethodBudget(10,clock=clock)
        receipt=deepcopy(actual_receipt);receipt['completed_at_elapsed_s']=1.
        def evaluate(*args):
            clock.now=budget.deadline+1
            return receipt
        with patch.object(initial,'iter_initial_candidates',return_value=iter([attempt()])):
            with patch.object(initial,'evaluate_model_candidate',side_effect=evaluate):
                result=initial.prepare_initial_witness(model,{},budget)
        require(result['state']=='SAFE_POINT_UNRESOLVED' and result['witness'])
        require(result['witness']['evaluation']['safe_upper_bound_J']==receipt['safe_upper_bound_J'])
        require(result['x0'] is None)
        return result
    check('preparation/late_return_preserves_pre_deadline_safe_receipt_before_completion',completion_expiry)

    def completion_error():
        budget=MethodBudget(30)
        receipt=deepcopy(actual_receipt);receipt['completed_at_elapsed_s']=.1
        def lazy():
            yield attempt()
            raise AssertionError('constructor consumed later template after first SAFE')
        with patch.object(initial,'iter_initial_candidates',return_value=lazy()):
            with patch.object(initial,'evaluate_model_candidate',return_value=receipt):
                with patch.object(initial,'complete_initial_point',side_effect=RuntimeError('injected completion error')):
                    result=initial.prepare_initial_witness(model,{},budget)
        require(result['state']=='SAFE_POINT_REJECTED' and result['witness'])
        require(result['x0'] is None and len(result['attempts'])==1)
        return result
    check('preparation/completion_error_retains_safe_and_does_not_consume_later_templates',completion_error)

    def deadline_receipt():
        receipt=deepcopy(actual_receipt);receipt['completed_at_elapsed_s']=10.
        budget=MethodBudget(10)
        with patch.object(initial,'iter_initial_candidates',return_value=iter([attempt()])):
            with patch.object(initial,'evaluate_model_candidate',return_value=receipt):
                with patch.object(initial,'complete_initial_point') as called:
                    result=initial.prepare_initial_witness(model,{},budget)
        require(result['witness'] is None and result['x0'] is None and called.call_count==0)
        return result
    check('preparation/safe_receipt_at_deadline_cannot_be_new_safe_output',deadline_receipt)

    def mismatch_receipt():
        receipt=deepcopy(actual_receipt);receipt['completed_at_elapsed_s']=.1
        receipt['evidence_identity']['candidate_sha256']='incorrect'
        with patch.object(initial,'_propose_vector') as called:
            try:
                initial.complete_initial_point(model,candidate,receipt,MethodBudget(30))
            except ValueError:
                pass
            else:
                raise AssertionError('mismatched SAFE receipt accepted')
        require(called.call_count==0)
    check('completion/receipt_must_match_exact_input_and_candidate',mismatch_receipt)

    def reject_bad_vector(kind):
        budget=MethodBudget(30)
        vector=initial._propose_vector(model,candidate,budget)
        if kind=='logical_fraction':
            vector[model.option_vars[0]]=.5
        else:
            vector[model.scenes[next(iter(model.scenes))]['theta'][0][0]]+=.001
        receipt=deepcopy(actual_receipt);receipt['completed_at_elapsed_s']=.1
        before=model_identity(model)
        with patch.object(initial,'_propose_vector',return_value=vector):
            result=initial.complete_initial_point(model,candidate,receipt,budget)
        require(result['state']=='INITIAL_POINT_REJECTED' and result['x0'] is None)
        require(model_identity(model)==before)
        return result
    check('completion/fractional_logical_aux_or_option_cannot_be_submitted',
          lambda:reject_bad_vector('logical_fraction'))
    check('completion/nonthermal_numeric_row_failure_cannot_be_submitted',
          lambda:reject_bad_vector('row_residual'))


def run(out, with_matlab=False):
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    files = sorted(HERE.glob('*.py'))+[HERE/'solve_model.m', HERE/'config_v01.json',
                                     HERE.parent/'v1_evaluator/interval.py']
    files = list(dict.fromkeys(files))
    hashes = {str(p.relative_to(HERE.parent)):digest(p) for p in files}
    snapshot = out/'source_snapshot'; snapshot.mkdir()
    for path in files:
        target = snapshot/path.relative_to(HERE.parent)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    require(digest(HERE/'config_v01.json')==CONFIG_SHA, 'frozen configuration changed')
    config = load_config(); data = fixtures(config)
    save(out/'fixtures.json', {name:{'instance':i, 'starts':s} for name,(i,s) in data.items()})
    records, details, oracle, models = [], {}, {}, {}

    def check(name, function):
        try:
            value = function()
            records.append({'name':name, 'passed':True})
            if value is not None:
                details[name] = value
        except Exception as exc:
            records.append({'name':name, 'passed':False, 'error':repr(exc),
                            'traceback':traceback.format_exc()})
        save(out/'checks_in_progress.json', {'checks':records, 'details':details})

    try:
        legal = structural_checks(data, check, oracle)
        save(out/'cartesian_oracle.json', oracle)
        constructors = {}
        preparations = {}
        for name,(instance,starts) in data.items():
            budget = MethodBudget(180)
            model = milp.build_model(instance, config, starts=starts, budget=budget, **FLAGS)
            models[name] = model
            before = model_identity(model)
            made = initial_schedule.construct_initial_candidates(instance, starts, budget, 3)
            constructors[name] = made
            candidates = made['candidates']
            allowed = {candidate_key(x) for x in legal[name]}
            check(name+'/constructor_at_most_three_fixed_templates', lambda m=made:require(
                0<len(m['attempts'])<=3 and m['coverage_status']=='BOUNDED_SEEDS_ONLY_NOT_EXHAUSTIVE'))
            for index,attempt in enumerate(candidates):
                candidate = attempt['candidate']
                check(name+f'/seed{index}/independent_exact_legal_and_declared_domain',
                      lambda c=candidate,a=allowed,i=instance:require(
                          independent_check(i,c)['valid'] and candidate_key(c) in a))
                check(name+f'/seed{index}/no_claim_of_heat_or_optimality',
                      lambda a=attempt:require(a['thermal_status']=='NOT_EVALUATED'
                          and a['energy_status']=='NOT_EVALUATED' and a['exclusion']=='NONE'))
            prepared = initial.prepare_initial_witness(model, config['accuracy_targets'],
                                                       budget, starts=starts, max_attempts=3)
            preparations[name] = prepared
            check(name+'/prepare_does_not_change_model_rows_objective_bounds_or_domain',
                  lambda m=model,b=before:require(model_identity(m)==b))
            check(name+'/bounded_attempts_not_an_infeasibility_proof', lambda p=prepared:require(
                len(p['attempts'])<=3 and p['state'] in ('SAFE_POINT_READY','SAFE_POINT_REJECTED',
                                                      'SAFE_POINT_UNRESOLVED','UNRESOLVED')))
            witness = prepared.get('witness')
            if witness is not None:
                receipt = witness['evaluation']
                check(name+'/safe_receipt_complete_rankable_and_in_budget', lambda w=witness,b=budget:require(
                    w['evaluation']['state']=='SAFE' and w['evaluation']['rankable_energy']
                    and w['evaluation']['completed_at_elapsed_s']<b.seconds
                    and w['evaluation'].get('safe_upper_bound_J') is not None))
                check(name+'/safe_witness_independently_structural', lambda w=witness,i=instance:require(
                    independent_check(i,w['candidate'])['valid']))
            if prepared.get('x0') is not None:
                vector = prepared['x0']
                check(name+'/completed_vector_passes_actual_strict_numerical_admission',
                      lambda v=vector,m=model:matlab_bridge._prepare(m.as_solver_dict(),x0=v)['x0_validation'])
                check(name+'/all_logical_auxiliaries_binary_and_schedule_roundtrip',
                      lambda v=vector,m=model,w=witness:require(
                          milp.logical_candidate_diagnostics(m,v)['accepted'] and
                          candidate_key(milp.decode(m,v))==candidate_key(w['candidate'])))
            else:
                check(name+'/no_vector_does_not_erase_safe_witness', lambda p=prepared:require(
                    p.get('completion') is None or p['completion'].get('state')!='INITIAL_POINT_READY'))
            save(out/'constructor_attempts.json', constructors)
            save(out/'preparations.json', preparations)
        state_checks(out, check, models['one_stage_energy'],
                     legal['one_stage_energy'][0])
        one=preparations['one_stage_energy'].get('witness')
        if one is not None:
            preparation_checks(out,check,models['one_stage_energy'],one['candidate'],one['evaluation'])
        else:
            check('preparation/one_stage_fixture_provides_safe_receipt_for_boundary_checks',
                  lambda:require(False,'one-stage fixture produced no SAFE receipt'))

        if with_matlab and all(row['passed'] for row in records):
            def native():
                def loader(budget):
                    # This call, including fixture expansion, is inside the
                    # single method budget; no previously built model is used.
                    loaded = load_config()
                    instance,_starts = fixtures(loaded)['one_stage_energy']
                    return loaded,instance
                def builder(instance,loaded,**kwargs):
                    starts = {scene['id']:{stage['id']:['0'] for stage in scene['stage_instances']}
                              for scene in instance['scenarios']}
                    return milp.build_model(instance,loaded,starts=starts,**FLAGS,**kwargs)
                def solve(model,session,accuracy,budget):
                    starts = {scene['id']:{stage['id']:['0'] for stage in scene['stage_instances']}
                              for scene in model.instance['scenarios']}
                    return initial.solve_with_initial_witness(model,session,accuracy,budget,starts=starts)
                result = execute_milp(loader,out/'native_one_stage',seconds=180,
                                      construct_only=False,model_builder=builder,solve=solve)
                require(result['state']=='SAFE',str(result.get('reason')))
                require(result['safe_upper_bound_J'] is not None and result['safe_candidate'])
                require(result['initialisation']['witness']['evaluation']['state']=='SAFE')
                require(result['initialisation']['completion']['state']=='INITIAL_POINT_READY')
                require(not result['candidate_and_cache_shared_between_calls'])
                require(not result['independently_proven_optimal'])
                require(result['timing']['limit_s']==180)
                require(result['initialisation']['witness']['evaluation']['completed_at_elapsed_s']<180)
                diagnostics=result.get('solver_diagnostic')
                require(diagnostics is not None,'solver diagnostic output missing')
                require(result['solver_request_attempts']>=1,'x0 never submitted to MATLAB')
                rounds=diagnostics.get('rounds',[])
                require(rounds and rounds[0].get('initial_point',{}).get('provided') is True,
                        'native worker did not report receiving x0')
                return {'result':result,'scope':'small native x0 correctness, not performance comparison'}
            check('native/one_stage_same_180s_method_budget_and_continuous_safe_receipt',native)
    except Exception as exc:
        records.append({'name':'unhandled_precheck_exception','passed':False,'error':repr(exc),
                        'traceback':traceback.format_exc()})
    check('sources_unchanged_during_precheck',lambda:require(hashes=={
        str(p.relative_to(HERE.parent)):digest(p) for p in files}))
    check('frozen_configuration_unchanged',lambda:require(digest(HERE/'config_v01.json')==CONFIG_SHA))
    report={'passed':all(row['passed'] for row in records),'count':len(records),
            'checks':records,'details':details,'source_sha256':hashes,
            'wall_seconds':time.monotonic()-started,'original_benchmark_built_or_solved':False,
            'formal_comparison':False,'flags':FLAGS,
            'oracle_candidates_used_by_constructor_or_solver':False}
    save(out/'checks.json',report)
    print(json.dumps({'passed':report['passed'],'count':report['count'],'out':str(out)},ensure_ascii=False))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--with-matlab',action='store_true')
    args=parser.parse_args()
    raise SystemExit(0 if run(args.out,args.with_matlab)['passed'] else 1)
