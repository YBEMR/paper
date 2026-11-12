"""K.96 fixed-deployment scene lifecycle checks; no original-scale run.

Default mode uses fake sessions solely for interface and deadline checks. The
explicit --with-matlab mode requires a passing, source-matched default record,
predeclares three existing correctness fixtures, then invokes each exactly
once with a fresh 180 s method budget and worker. No precheck vector, witness,
or thermal cache is supplied to an actual solver.
"""
import argparse
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import platform
import shutil
import sys
import time
from unittest.mock import patch

import numpy as np
import scipy

import milp
import scene_adapter as adapter
from inputs import load_config
from run_milp_precheck import fixtures, independent_assignments, independent_check, require, equal
from thermal import Budget, Exhausted, evaluate_candidate

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CONFIG_SHA = '615be096bfbcb3e7c53ba9b0810d888264d48adbc428f1f7d2f94a5c6a29a4fe'
PROTOCOL = 'K96-fixed-deployment-scene-small-end-to-end-v1'
NATIVE_SECONDS = 180
FLAGS = dict(fix_late_options=True, aggregate_opp_locks=True,
             relax_auxiliary_integrality=True, strengthen_energy_lower_bounds=True,
             prefilter_deadlines=True)
SOURCES = ['run_scene_method_precheck.py', 'scene_method.py', 'scene_adapter.py',
           'milp.py', 'milp_coefficients.py', 'matlab_bridge.py', 'solve_model.m',
           'timing.py', 'build_observer.py', 'inputs.py', 'schedules.py', 'thermal.py',
           'run_milp_precheck.py', 'config_v01.json', 'scene_method_protocol.md',
           '../v1_evaluator/interval.py']


def save(path, value):
    path = Path(path)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n',
                    encoding='utf-8')


def source_hashes():
    return {str((HERE/name).resolve().relative_to(REPO)):
            hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in SOURCES}


def existing_cases(config):
    """Recipes copied from the existing small checks, never research inputs."""
    fm = fixtures(config)
    shared, shared_starts = deepcopy(fm['shared_two_scenes'])
    chain, chain_starts = deepcopy(fm['chain_fractional'])
    analytic, analytic_starts = deepcopy(fm['one_stage_energy'])
    analytic['id'] = 'fixture_analytic_internal_peak'
    analytic['fixture_scope'] = 'synthetic_analytic_correctness_only_not_a_research_parameter_change'
    analytic['window_ms'] = '1000'
    p = analytic['platform']
    p['heat_capacity_J_per_K'] = ['1']*4
    p['conductance_W_per_K'] = [['2','-1','0','0'], ['-1','2','0','0'],
                               ['0','0','1','0'], ['0','0','0','1']]
    p['external_common_power_W'] = '0'
    for domain in p['domains'].values():
        for opp in domain['opps']:
            domain['baseline_W'][opp] = '0'
            domain['local_temperature_slope_W_per_K'][opp] = '0'
    for modes in analytic['stage_modes'].values():
        for mode in modes:
            mode['activity_power_W'] = '0'
            mode['activity_energy_J'] = '0'
    analytic['scenarios'][0]['entry']['temperature_degC'] = ['25','28','25','25']
    analytic['scenarios'][0]['maximum_temperature_degC'] = ['25.55','40','40','40']
    return {
        'shared_two_scenes': (shared, shared_starts, {'A.pre':'CPU1'}),
        'chain_fractional': (chain, chain_starts, {'A.pre':'CPU1','A.main':'NPU0'}),
        'analytic_internal_peak': (analytic, analytic_starts, {'A.pre':'CPU1'})}


def manifest(config):
    cases = existing_cases(config)
    return {'protocol':PROTOCOL, 'scope':'existing correctness fixtures only; no original-scale model or formal comparison',
            'method_budget_s':NATIVE_SECONDS, 'calls_per_case':1, 'reruns_allowed':False,
            'timeout_extension_allowed':False, 'worker':'one fresh worker per complete fixed-deployment invocation',
            'scene_weighting':'unweighted individual scenes, original weights once after all matching SAFE receipts',
            'builder_flags':FLAGS, 'native_warm_start_provided':False,
            'native_candidate_or_thermal_result_shared':False,
            'cases':{name:{'input':instance, 'starts':starts, 'fixed_deployment':mapping,
                'input_sha256':adapter.canonical_hash(instance), 'starts_sha256':adapter.canonical_hash(starts),
                'fixed_deployment_sha256':adapter.canonical_hash(mapping)}
                     for name,(instance,starts,mapping) in cases.items()},
            'analytic_recipe_source':'run_milp_precheck.py: analytic_internal_peak; same four-node embedding and closed form',
            'closed_form':'T_CPU1(t)=25+1.5*(exp(-t)-exp(-3*t)); t in seconds; max=25+1/sqrt(3)'}


class FakeClock:
    def __init__(self): self.now=0.0
    def __call__(self): return self.now
    def advance(self, seconds): self.now+=seconds


def fake_invocation(out, config, case, *, clock=None, mode='safe',
                    scene_evaluator=adapter.evaluate_scene, aggregator=adapter.aggregate_scene_receipts):
    """Vectors are assembled only inside the fake worker, never the native path."""
    from scene_method import execute_fixed_deployment
    instance, starts, deployment = deepcopy(case)
    models, workers, native_calls = [], [], []
    live_clock = time.monotonic if clock is None else clock

    def loader(budget):
        budget.check()
        if mode=='input_expiry':
            clock.advance(181); budget.check()
        return deepcopy(config), deepcopy(instance)

    def builder(*args, **kwargs):
        model=milp.build_model(*args, **kwargs); models.append(model); return model

    class Worker:
        def __init__(self, workdir, total_budget_s, budget):
            self.counter=0; self.closed=False; self.budget=budget
            self.environment={'status':'FAKE_PRECHECK_ONLY','release':'2023b'}
            self.calls=[]; workers.append(self)
            self.deadline=budget.deadline
            if clock: clock.advance(.1)
        def close(self): self.closed=True
        def solve(self, payload, remaining_s=None, budget=None, x0=None):
            require(x0 is None,'fake precheck unexpectedly supplied an initial point')
            require(budget is self.budget,'solver did not receive original method budget')
            require(budget.deadline==self.deadline,'method deadline changed between rounds')
            require(0<remaining_s<=budget.remaining+1e-5,'remaining budget reset or invalid')
            self.counter+=1
            index=min(self.counter-1,len(models)-1)
            if mode in ('repeat_violation','reported_infeasible'): index=0
            model=models[index]
            self.calls.append({'remaining_s':remaining_s,'deadline':budget.deadline,
                               'rows':payload['A'].shape[0],'scene':next(iter(model.scenes))})
            if clock: clock.advance(.1)
            if mode=='late_solver':
                clock.advance(budget.seconds+1)
                return {'x':[],'exitflag':0,'budget_valid':False,'accepted_for_evaluation':False,
                        'intlinprog_entered':True}
            if mode=='reported_infeasible' or (mode=='repeat_violation' and self.counter>=3):
                return {'x':[],'exitflag':-2,'budget_valid':True,'accepted_for_evaluation':False,
                        'status':'SOLVER_REPORTED_INFEASIBLE','intlinprog_entered':True}
            local_starts={sid:starts[sid] for sid in model.scenes}
            allowed=[c for c in independent_assignments(model.instance,local_starts)
                if independent_check(model.instance,c)['valid'] and all(
                    deployment[s['shared_stage_id']]==r['unit']
                    for scene in model.instance['scenarios'] for s in scene['stage_instances']
                    for r in c['scenes'][scene['id']] if r['stage_id']==s['id'])]
            # This vector only tests noninteger decoding. Actual solver choices
            # are never restricted to this fake-only representative.
            if model.instance['id']=='fixture_chain_fractional':
                allowed.sort(key=lambda c:not any(F(r['end']).denominator!=1
                    for sc in independent_check(model.instance,c)['scenes'].values()
                    for r in sc['rows'].values()))
            candidate=allowed[0]
            vector=milp.lift_candidate(model,candidate)
            if mode=='fractional_logical': vector[model.logical_binary[0]]=.5
            return {'x':vector.tolist(),'exitflag':1,'budget_valid':True,'accepted_for_evaluation':True,
                    'status':'SOLVED','intlinprog_entered':True,'output':{'lowerbound':-1.0},
                    'scope':'fake interface only; lifted vector is not a native search result'}

    result=execute_fixed_deployment(loader,out,fixed_deployment=deployment,starts=starts,
        seconds=180,clock=live_clock,model_builder=builder,session_factory=Worker,
        scene_evaluator=scene_evaluator,aggregator=aggregator)
    require(not native_calls,'native solver reached by fake mode')
    return result,models,workers


def run_fake(out, config, check):
    cases=existing_cases(config)
    records={}
    shared,models,workers=fake_invocation(out/'fake_shared',config,cases['shared_two_scenes'])
    records['shared']=shared
    check('fake/shared_all_scenes_safe',lambda:equal(shared['state'],'SAFE'))
    check('fake/one_worker_for_complete_deployment',lambda:require(len(workers)==1 and workers[0].closed,'worker lifecycle'))
    check('fake/all_scene_models_built',lambda:equal(len(models),2))
    check('fake/separate_unweighted_objectives',lambda:require(all(
        m.instance['scenarios'][0]['weight']=='1' for m in models),'scenario weight not one'))
    check('fake/one_solver_request_per_safe_scene',lambda:equal(workers[0].counter,2))
    check('fake/one_absolute_deadline',lambda:require(len({r['deadline'] for r in workers[0].calls})==1,'deadline changed'))
    check('fake/remaining_budget_never_replenished',lambda:require(all(
        a['remaining_s']>=b['remaining_s'] for a,b in zip(workers[0].calls,workers[0].calls[1:])),str(workers[0].calls)))
    check('fake/upper_bound_from_original_aggregate',lambda:equal(shared['safe_upper_bound_J'],shared['aggregation']['safe_upper_bound_J']))
    check('fake/no_independent_optimality_or_infeasibility_claim',lambda:require(
        not shared.get('independently_proven_optimal',False) and not shared.get('independently_proven_infeasible',False),'unsupported proof'))
    check('fake/all_four_nodes_and_unused_device_baseline_kept',lambda:require(all(
        m.instance['platform']==cases['shared_two_scenes'][0]['platform'] for m in models),'physical platform changed'))
    combined=evaluate_candidate(cases['shared_two_scenes'][0],shared['safe_candidate'],
                                config['accuracy_targets'],Budget(seconds=60))
    check('fake/global_energy_matches_common_evaluator',lambda:equal(
        combined['weighted_energy_J'],shared['aggregation']['weighted_energy_J']))

    chain,cm,cw=fake_invocation(out/'fake_chain',config,cases['chain_fractional'])
    records['chain']=chain
    check('fake/chain_safe',lambda:equal(chain['state'],'SAFE'))
    check('fake/chain_fractional_finish_retained',lambda:require(any(
        F(r['end']).denominator!=1 for s in independent_check(cases['chain_fractional'][0],chain['safe_candidate'])['scenes'].values()
        for r in s['rows'].values()),'noninteger finish lost'))
    check('fake/call_isolation_no_worker_or_model_reuse',lambda:require(
        cw[0] is not workers[0] and all(m is not n for m in cm for n in models),'shared mutable search state'))

    incomplete=deepcopy(cases['chain_fractional'])
    incomplete[2].pop('A.main')
    rejected,rm,rw=fake_invocation(out/'fake_incomplete_deployment',config,incomplete)
    records['incomplete_deployment']=rejected
    check('identity/incomplete_outer_deployment_rejected_before_projection',lambda:require(
        not rm and not rw and rejected['safe_upper_bound_J'] is None and
        rejected['reason']=='INVALID_INPUT_OR_INTERFACE','partial outer deployment accepted'))
    clock=FakeClock()
    input_expired,em,ew=fake_invocation(out/'fake_input_expiry',config,cases['shared_two_scenes'],clock=clock,mode='input_expiry')
    records['input_expiry']=input_expired
    check('budget/input_expiry_does_not_build_or_launch',lambda:require(
        not em and not ew and input_expired['safe_upper_bound_J'] is None,'work after input expiry'))

    analytic,am,aw=fake_invocation(out/'fake_analytic',config,cases['analytic_internal_peak'],mode='repeat_violation')
    records['analytic']=analytic
    sr=next(iter(analytic['scenes'].values()))['solver_result']
    check('fake/analytic_continuous_peak_rejected',lambda:require(
        analytic['safe_upper_bound_J'] is None and sr['evaluation']['state']=='THERMAL_VIOLATION','peak not rejected'))
    check('fake/thermal_feedback_and_complete_assignment_exclusion',lambda:require(
        any(r['tag']=='continuous_thermal_feedback' for r in am[0].rows) and
        any(r['tag']=='certified_scene_assignment_exclusion' for r in am[0].rows),'missing feedback coverage'))
    check('fake/repeated_rounds_share_remaining_budget',lambda:require(len(aw[0].calls)==3 and all(
        a['remaining_s']>=b['remaining_s'] for a,b in zip(aw[0].calls,aw[0].calls[1:])),str(aw[0].calls)))
    check('fake/reported_infeasible_is_not_independent_proof',lambda:require(
        sr['reason']=='SOLVER_REPORTED_INFEASIBLE' and not sr['independently_proven_infeasible'],'upgraded solver report'))

    invalid,_,_=fake_invocation(out/'fake_fractional',config,cases['chain_fractional'],mode='fractional_logical')
    records['fractional_logical']=invalid
    check('fake/noninteger_logical_candidate_not_accepted',lambda:require(
        invalid['safe_upper_bound_J'] is None and any('NUMERICAL_CANDIDATE_ANOMALY' in str(s.get('solver_result',{}).get('reason'))
        for s in invalid['scenes'].values()),str(invalid)))

    clock=FakeClock()
    late,_,lw=fake_invocation(out/'fake_late_solver',config,cases['chain_fractional'],clock=clock,mode='late_solver')
    records['late_solver']=late
    check('budget/late_solver_no_new_safe_U',lambda:require(late['safe_upper_bound_J'] is None,'late safe accepted'))
    check('budget/late_solver_no_restart',lambda:equal(lw[0].counter,1))
    check('budget/late_raw_solver_entry_not_budget_entry',lambda:require(
        late.get('raw_native_solver_entry_seen') is True and
        late.get('in_budget_solver_entry_confirmed') is not True and
        late.get('integer_solver_entered') is not True,'late entry promoted'))

    clock=FakeClock()
    def commit_scene_safe_then_expire(*args,**kwargs):
        receipt=adapter.evaluate_scene(*args,**kwargs)
        require(receipt['state']=='SAFE','fixture must commit SAFE before expiry')
        clock.advance(181)
        return receipt
    handoff,_,_=fake_invocation(out/'fake_scene_handoff',config,cases['shared_two_scenes'],
                               clock=clock,scene_evaluator=commit_scene_safe_then_expire)
    records['safe_scene_handoff']=handoff
    check('budget/committed_scene_safe_receipt_retained',lambda:require(any(
        s.get('scene_receipt',{}).get('state')=='SAFE' for s in handoff['scenes'].values()),str(handoff)))
    check('budget/partial_scene_safe_cannot_be_global_U',lambda:require(
        handoff['safe_upper_bound_J'] is None and handoff['state']!='SAFE','partial safe became global'))

    def unresolved_scene(*args,**kwargs):
        receipt=adapter.evaluate_scene(*args,**kwargs)
        receipt.update(state='UNRESOLVED',rankable_energy=False,safe_upper_bound_J=None,energy_J=None,
                       reason='INJECTED_PRECHECK_NUMERICAL_UNRESOLVED')
        receipt['receipt_sha256']=adapter._receipt_hash(receipt)
        return receipt
    uncertain,_,_=fake_invocation(out/'fake_unresolved',config,cases['chain_fractional'],scene_evaluator=unresolved_scene)
    records['unresolved_scene']=uncertain
    check('numerics/scene_unresolved_cannot_accept_view_safe',lambda:require(
        uncertain['safe_upper_bound_J'] is None and uncertain['state']=='UNRESOLVED','view accepted without full receipt'))

    clock=FakeClock()
    def expire_inside_second_check(*args,**kwargs):
        # The first independent model-view SAFE has already committed. The
        # original-input check receives no time and must return UNRESOLVED.
        clock.advance(181)
        return adapter.evaluate_scene(*args,**kwargs)
    recheck_late,_,_=fake_invocation(out/'fake_second_evaluation_expiry',config,cases['chain_fractional'],
                                   clock=clock,scene_evaluator=expire_inside_second_check)
    records['second_evaluation_expiry']=recheck_late
    check('budget/view_safe_survives_original_recheck_expiry',lambda:require(any(
        s.get('solver_view_safe_evidence',{}).get('safe_candidate') is not None
        for s in recheck_late['scenes'].values()),'old view SAFE lost'))
    check('budget/no_global_U_without_original_recheck',lambda:require(
        recheck_late['safe_upper_bound_J'] is None and recheck_late['state']!='SAFE','late original check accepted'))

    clock=FakeClock()
    def expire_at_aggregate(*args,**kwargs):
        # Receipt matching remains meaningful, but the new weighted commit
        # itself is forbidden after the common deadline.
        clock.advance(181)
        return adapter.aggregate_scene_receipts(*args,**kwargs)
    aggregate_late,_,_=fake_invocation(out/'fake_aggregate_expiry',config,cases['shared_two_scenes'],
                                     clock=clock,aggregator=expire_at_aggregate)
    records['aggregate_expiry']=aggregate_late
    check('budget/all_scene_SAFE_retained_at_aggregate_expiry',lambda:require(all(
        s['scene_receipt']['state']=='SAFE' for s in aggregate_late['scenes'].values()),'committed receipts lost'))
    check('budget/aggregate_expiry_no_new_weighted_U',lambda:require(
        aggregate_late['safe_upper_bound_J'] is None and aggregate_late['aggregation']['state']=='UNRESOLVED','late aggregate accepted'))

    def mismatched_scene(*args,**kwargs):
        receipt=adapter.evaluate_scene(*args,**kwargs)
        receipt['identity']['fixed_deployment_sha256']='different-deployment'
        receipt['receipt_sha256']=adapter._receipt_hash(receipt)
        return receipt
    wrong,_,_=fake_invocation(out/'fake_receipt_mismatch',config,cases['shared_two_scenes'],scene_evaluator=mismatched_scene)
    records['mismatched_scene_receipt']=wrong
    check('identity/foreign_receipt_no_global_U',lambda:require(wrong['safe_upper_bound_J'] is None and wrong['state']!='SAFE','identity mismatch accepted'))

    def late_timestamp_scene(*args,**kwargs):
        receipt=adapter.evaluate_scene(*args,**kwargs)
        receipt['completed_at_elapsed_s']=args[-1].seconds
        receipt['receipt_sha256']=adapter._receipt_hash(receipt)
        return receipt
    late_stamp,_,_=fake_invocation(out/'fake_late_receipt_stamp',config,cases['chain_fractional'],scene_evaluator=late_timestamp_scene)
    records['late_receipt_timestamp']=late_stamp
    check('budget/SAFE_timestamp_at_deadline_not_accepted',lambda:require(
        late_stamp['safe_upper_bound_J'] is None and all(s['safe_upper_bound_J'] is None
        for s in late_stamp['scenes'].values()),'out-of-budget receipt accepted'))

    def late_timestamp_aggregate(*args,**kwargs):
        value=adapter.aggregate_scene_receipts(*args,**kwargs)
        value['completed_at_elapsed_s']=args[-1].seconds
        return value
    late_global,_,_=fake_invocation(out/'fake_late_aggregate_stamp',config,cases['shared_two_scenes'],aggregator=late_timestamp_aggregate)
    records['late_aggregate_timestamp']=late_global
    check('budget/weighted_SAFE_timestamp_at_deadline_not_accepted',lambda:require(
        late_global['safe_upper_bound_J'] is None and late_global['state']!='SAFE','out-of-budget global receipt accepted'))

    # Budget expires immediately after an already committed strict point
    # witness from the view evaluator. It must survive, without a late cut/U.
    clock=FakeClock()
    original_evaluator=milp.evaluate_model_candidate
    def commit_violation_then_expire(*args,**kwargs):
        receipt=original_evaluator(*args,**kwargs)
        require(receipt['state']=='THERMAL_VIOLATION','analytic point witness expected')
        clock.advance(181)
        return receipt
    with patch.object(milp,'evaluate_model_candidate',side_effect=commit_violation_then_expire):
        violation,vm,_=fake_invocation(out/'fake_violation_handoff',config,cases['analytic_internal_peak'],clock=clock)
    records['violation_handoff']=violation
    vsolver=next(iter(violation['scenes'].values()))['solver_result']
    check('budget/committed_view_violation_retained',lambda:require(
        vsolver['evaluation']['state']=='THERMAL_VIOLATION' and vsolver['evaluation']['violations'],'point witness lost'))
    check('budget/no_after_deadline_feedback_or_energy',lambda:require(
        not vsolver['feedback'] and violation['safe_upper_bound_J'] is None and
        not any(r['tag']=='continuous_thermal_feedback' for r in vm[0].rows),'late feedback or U'))
    save(out/'fake_records.json',records)


def run_native(out, config, check, precheck_record, frozen_manifest):
    """Actual MATLAB execution is requested only by root with the explicit flag."""
    from scene_method import execute_fixed_deployment
    record=json.loads((precheck_record/'summary.json').read_text(encoding='utf-8'))
    old_hashes=json.loads((precheck_record/'source_integrity.json').read_text(encoding='utf-8'))
    old_manifest=json.loads((precheck_record/'declaration.json').read_text(encoding='utf-8'))
    require(record['state']=='PASS' and not record['matlab_called'],'passing fake-only precheck required')
    require(old_hashes['after']==source_hashes() and old_hashes['match'],'precheck/source hash mismatch')
    equal(old_manifest,frozen_manifest)
    results={}
    for name in frozen_manifest['cases']:
        # Fresh configuration and fixture expansion are charged by the method.
        # Only immutable declaration metadata is read before invocation.
        declaration=frozen_manifest['cases'][name]
        def loader(budget,name=name):
            budget.check(); fresh_config=load_config()
            fresh_instance,fresh_starts,fresh_mapping=existing_cases(fresh_config)[name]
            require(adapter.canonical_hash(fresh_instance)==declaration['input_sha256'],'declared input changed')
            require(adapter.canonical_hash(fresh_starts)==declaration['starts_sha256'],'declared start set changed')
            require(adapter.canonical_hash(fresh_mapping)==declaration['fixed_deployment_sha256'],'declared deployment changed')
            budget.check(); return fresh_config,fresh_instance
        result=execute_fixed_deployment(loader,out/name,fixed_deployment=declaration['fixed_deployment'],
            starts=declaration['starts'],seconds=NATIVE_SECONDS)
        results[name]=result
        save(out/'native_results.json',results)
        check('native/'+name+'/single_method_budget',lambda r=result:equal(r['timing']['limit_s'],NATIVE_SECONDS))
        check('native/'+name+'/one_fresh_worker',lambda r=result:require(
            r.get('matlab_worker_ready') and r.get('candidate_and_cache_shared_between_calls') is False,str(r.get('reason'))))
        check('native/'+name+'/all_reported_bounds_engineering_only',lambda r=result:require(
            not r.get('independently_proven_optimal',False) and not r.get('independently_proven_infeasible',False),'unsupported independent proof'))
        rounds=[a for s in result['scenes'].values() for a in (s.get('solver_result') or {}).get('rounds',[])]
        check('native/'+name+'/intlinprog_actually_entered',lambda a=rounds:require(
            any(r.get('intlinprog_entered') is True and r.get('budget_valid') is True for r in a),
            'no in-budget worker intlinprog entry receipt'))
        check('native/'+name+'/no_native_initial_point',lambda a=rounds:require(all(
            not r.get('initial_point',{}).get('provided',False) for r in a),'native warm-start injection'))
        if not result.get('matlab_worker_ready'):
            save(out/'native_blocker.json',{'case':name,'reason':result.get('reason'),
                'error':result.get('error'),'policy':'stop without rerun, new solver, or budget extension',
                'unexecuted_cases':[n for n in frozen_manifest['cases'] if n not in results]})
            break
        if name!='analytic_internal_peak':
            check('native/'+name+'/complete_safe_output',lambda r=result:equal(r['state'],'SAFE'))
            if result['safe_candidate'] is not None:
                # Existing witness only: no new search or budget-local credit.
                post=evaluate_candidate(declaration['input'],result['safe_candidate'],
                                        config['accuracy_targets'],Budget(seconds=60))
                save(out/name/'post_stop_witness_verification.json',{'scope':'archive-only independent recheck of saved witness; no new budget-local search evidence',
                    'evaluation':post})
                check('native/'+name+'/saved_witness_independently_safe',lambda p=post:equal(p['state'],'SAFE'))
                check('native/'+name+'/unweighted_aggregation_matches_common_enclosure',lambda r=result,p=post:require(
                    max(F(r['aggregation']['weighted_energy_J'][0]),F(p['weighted_energy_J'][0]))<=
                    min(F(r['aggregation']['weighted_energy_J'][1]),F(p['weighted_energy_J'][1])),'energy enclosure mismatch'))
        else:
            sr=next(iter(result['scenes'].values())).get('solver_result') or {}
            check('native/analytic/continuous_peak_feedback_activated',lambda s=sr:require(
                len(s.get('rounds',[]))>=2 and any(f['rows_added']>0 for f in s.get('feedback',[])),str(s)))
            check('native/analytic/no_false_safe_U',lambda r=result:require(r['safe_upper_bound_J'] is None and r['state']!='SAFE','unsafe accepted'))
            check('native/analytic/solver_reported_infeasible_not_certified',lambda s=sr:require(
                s.get('reason')=='SOLVER_REPORTED_INFEASIBLE' and not s.get('independently_proven_infeasible',False),str(s.get('reason'))))
        check('native/'+name+'/source_identity_stable',lambda:equal(source_hashes(),old_hashes['after']))
    return results


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--with-matlab',action='store_true')
    parser.add_argument('--precheck-record',type=Path)
    args=parser.parse_args(argv)
    if args.out.exists(): parser.error('Never overwrite previous evidence')
    if args.with_matlab and args.precheck_record is None:
        parser.error('--with-matlab requires --precheck-record')
    args.out.mkdir(parents=True)
    started=time.monotonic(); checks=[]
    def check(name,fn):
        try:
            fn(); checks.append({'name':name,'status':'PASS'})
        except Exception as error:
            checks.append({'name':name,'status':'FAIL','error':repr(error)})
        save(args.out/'checks.json',checks)
    config=load_config()
    require(hashlib.sha256((HERE/'config_v01.json').read_bytes()).hexdigest()==CONFIG_SHA,'frozen configuration changed')
    hashes=source_hashes(); declared=manifest(config)
    save(args.out/'declaration.json',declared)
    snapshot=args.out/'source_snapshot'
    for relative in hashes:
        target=snapshot/relative; target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(REPO/relative,target)
    environment={'python':sys.version,'host':platform.platform(),'numpy':np.__version__,'scipy':scipy.__version__,
        'matlab_environment_source':'per-invocation matlab/ready.json and session.json only; not inferred from installation',
        'scope':'correctness precheck only; no original base__R1 construction/solve, no formal comparison'}
    save(args.out/'environment.json',environment)
    save(args.out/'source_integrity.json',{'before':hashes,'after':hashes,'match':True,'scope':'snapshot taken before invocation'})
    try:
        if args.with_matlab:
            run_native(args.out,config,check,args.precheck_record,declared)
        else:
            run_fake(args.out,config,check)
    except Exception as error:
        checks.append({'name':'precheck/unhandled_error','status':'FAIL','error':repr(error)})
        import traceback
        (args.out/'failure_traceback.txt').write_text(traceback.format_exc(),encoding='utf-8')
    after=source_hashes()
    check('integrity/source_and_input_unchanged',lambda:equal(hashes,after))
    save(args.out/'source_integrity.json',{'before':hashes,'after':after,'match':hashes==after,
        'scope':'sources and frozen config; precheck fixture recipes and starts archived separately'})
    native_results={}
    if (args.out/'native_results.json').exists():
        native_results=json.loads((args.out/'native_results.json').read_text(encoding='utf-8'))
    summary={'protocol':PROTOCOL,'state':'PASS' if checks and all(c['status']=='PASS' for c in checks) else 'FAIL',
        'checks_passed':sum(c['status']=='PASS' for c in checks),'checks_total':len(checks),
        'elapsed_s':time.monotonic()-started,'matlab_called':args.with_matlab,
        'native_calls_predeclared':3 if args.with_matlab else 0,'native_method_budget_s':NATIVE_SECONDS,
        'native_complete_deployment_invocations_attempted':len(native_results),
        'native_solver_request_attempts':sum(r.get('solver_request_attempts',0) for r in native_results.values()),
        'native_cases_unexecuted':[n for n in declared['cases'] if n not in native_results] if args.with_matlab else [],
        'original_scale_model_built':False,'formal_experiment_result':False,
        'scope':'small fixture end-to-end correctness and evidence handling; not efficiency or energy-advantage evidence'}
    save(args.out/'checks.json',checks); save(args.out/'summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False))
    return 0 if summary['state']=='PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())
