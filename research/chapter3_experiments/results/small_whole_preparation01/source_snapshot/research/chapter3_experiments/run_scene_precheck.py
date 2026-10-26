"""Fixed-deployment scene-interface prechecks; no solver or research run.

All enumeration is confined to the existing correctness fixtures and explicit
boundary variants. Original physical parameters are unchanged. Rebuilt event
grids are checked against complete legal schedules and continuous RC energy;
their numerical outer matrices are not claimed row-equivalent to each other.
"""
import argparse
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import importlib.util
from itertools import product
import json
from pathlib import Path
import subprocess
import time
from unittest.mock import patch

import numpy as np
import scipy

import milp
import scene_adapter as adapter
from inputs import load_config
from thermal import Budget, Exhausted, I, evaluate_candidate, evaluate_piecewise
from run_milp_precheck import (fixtures, independent_assignments, independent_check,
    canonical_structure_vector, exact_row_residuals, candidate_key, require, equal, save)
from run_energy_bound_precheck import box_certificate_check

HERE = Path(__file__).resolve().parent
REFERENCE = '724dc01'
CONFIG_SHA = '615be096bfbcb3e7c53ba9b0810d888264d48adbc428f1f7d2f94a5c6a29a4fe'
FLAGS = dict(fix_late_options=True, aggregate_opp_locks=True,
             relax_auxiliary_integrality=True, strengthen_energy_lower_bounds=True)


def deployments(instance):
    keys = sorted({s['shared_stage_id'] for sc in instance['scenarios']
                   for s in sc['stage_instances']})
    choices = [sorted({m['unit_id'] for m in instance['stage_modes'][k]}) for k in keys]
    for values in product(*choices):
        yield dict(zip(keys, values))


def compatible(instance, candidate, deployment):
    checked = independent_check(instance, candidate)
    return checked['valid'] and checked['shared_deployment'] == deployment


def build(instance, config, starts, *, deployment=None, scene=None, physics=False,
          prefilter=True, module=milp):
    extra = {} if deployment is None and scene is None and not prefilter else dict(
        fixed_deployment=deployment, fixed_scene_id=scene, prefilter_deadlines=prefilter)
    return module.build_model(instance, config, starts=starts, include_physics=physics,
                              budget=Budget(seconds=600), **FLAGS, **extra)


def row_acceptance(model, candidate):
    vector = canonical_structure_vector(model, candidate)
    return (all(r <= 0 for r in exact_row_residuals(model, vector)) and
            all(F.from_float(float(a)) <= F.from_float(float(v)) <= F.from_float(float(b))
                for a, v, b in zip(model.lb, vector, model.ub)))


def coefficient_signature(model):
    return {str(k): {'temperature': [[v.data() for v in r] for r in c['temperature']],
                     'energy': [v.data() for v in c['energy']]}
            for k, c in model.coefficients.cache.items()}


def overlap(left, right):
    return max(F(left[0]), F(right[0])) <= min(F(left[1]), F(right[1]))


def enclosed_flow(model,candidate,scene_id):
    """Propagate fresh coefficient intervals, independently of row generation."""
    checked=independent_check(model.instance,candidate)
    require(checked['valid'],'interval propagation needs legal full schedule')
    scene=next(s for s in model.instance['scenarios'] if s['id']==scene_id)
    platform=model.instance['platform']
    theta=[I.rational(F(t)-F(platform['ambient_temperature_degC']))
           for t in scene['entry']['temperature_degC']]
    energy=I(0)
    for left,right in zip(model.scenes[scene_id]['events'],model.scenes[scene_id]['events'][1:]):
        segment=next(p for p in checked['scenes'][scene_id]['segments']
                     if F(p['start_ms'])/1000<=left<F(p['end_ms'])/1000)
        state=tuple(segment['domain_opps'][d] for d in platform['domains'])
        coeff=model.coefficients.get(state,right-left)
        sources=theta+[I.rational(F(segment['activity_by_node_W'][n])) for n in platform['node_order']]+[I(1)]
        energy+=sum((a*b for a,b in zip(coeff['energy'],sources)),I(0))
        theta=[sum((a*b for a,b in zip(row,sources)),I(0)) for row in coeff['temperature']]
    return {'energy_J':energy.data(),'final_temperature_degC':{
        node:(v+I.rational(F(platform['ambient_temperature_degC']))).data()
        for node,v in zip(platform['node_order'],theta)}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error('Never overwrite previous evidence')
    args.out.mkdir(parents=True)
    started = time.monotonic()
    config = load_config()
    require(hashlib.sha256((HERE/'config_v01.json').read_bytes()).hexdigest() == CONFIG_SHA,
            'frozen config changed')
    checks, records = [], {}

    def check(name, fn):
        try:
            fn()
            checks.append({'name': name, 'status': 'PASS'})
        except Exception as error:
            checks.append({'name': name, 'status': 'FAIL', 'error': repr(error)})
        save(args.out/'checks.json', checks)

    source_names = ['run_scene_precheck.py', 'scene_adapter.py', 'milp.py', 'milp_coefficients.py',
                    'schedules.py', 'thermal.py', 'inputs.py', 'config_v01.json',
                    'run_milp_precheck.py','run_energy_bound_precheck.py','../v1_evaluator/interval.py']
    source_hashes = {n: hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in source_names}
    save(args.out/'source_integrity.json', {'sha256': source_hashes, 'reference': REFERENCE,
         'numpy_version':np.__version__,'scipy_version':scipy.__version__,
         'scope': 'small correctness fixtures only; no solver, no original-scale model'})
    source = subprocess.run(['git', 'show', REFERENCE+':research/chapter3_experiments/milp.py'],
                            cwd=HERE, check=True, capture_output=True).stdout
    path = args.out/'reference_milp.py'
    path.write_bytes(source)
    spec = importlib.util.spec_from_file_location('_scene_reference_milp', path)
    old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
    fixture_map = fixtures(config)
    # The named variants alter only correctness-test task/start/entry bounds.
    boundary = deepcopy(fixture_map['one_stage_energy'])
    boundary[0]['id'] = 'fixture_scene_deadline_fraction'
    boundary[0]['scenarios'][0]['requests'][0]['deadline_ms'] = '34/3'
    sid = boundary[0]['scenarios'][0]['id']
    stage = boundary[0]['scenarios'][0]['stage_instances'][0]['id']
    boundary[1][sid][stage] = ['0', '5', '120']
    fixture_map['deadline_fraction'] = boundary
    projection_records = {}
    legal_sets = {}
    for name, (instance, starts) in fixture_map.items():
        all_candidates = list(independent_assignments(instance, starts))
        legal_sets[name] = [c for c in all_candidates if independent_check(instance, c)['valid']]
        if name != 'deadline_fraction':
            original = build(instance, config, starts, prefilter=False, module=old)
            current = build(instance, config, starts, prefilter=False)
            check('default/'+name+'/original_rows_variables_unchanged', lambda a=original,b=current:
                equal((a.names,a.lb,a.ub,a.integer,a.logical_binary,a.c,a.options,a.shared,a.rows,a.scenes),
                      (b.names,b.lb,b.ub,b.integer,b.logical_binary,b.c,b.options,b.shared,b.rows,b.scenes)))
        domain_records = []
        for deployment in deployments(instance):
            whole = build(instance, config, starts, deployment=deployment)
            expected = {candidate_key(c) for c in all_candidates if compatible(instance,c,deployment)}
            observed = {candidate_key(c) for c in all_candidates if row_acceptance(whole,c)}
            check('projection/'+name+'/'+str(deployment)+'/whole_domain', lambda a=expected,b=observed: equal(a,b))
            local_sets = {}
            for scene in instance['scenarios']:
                scene_id = scene['id']
                model = build(instance,config,starts,deployment=deployment,scene=scene_id)
                view = adapter.make_scene_instance(instance,scene_id)
                local = list(independent_assignments(view,{scene_id:starts[scene_id]}))
                local_expected = set()
                for c in local:
                    oracle = independent_check(view,c)
                    if oracle['valid'] and all(deployment[k]==u for k,u in oracle['shared_deployment'].items()):
                        local_expected.add(candidate_key(c))
                local_observed = {candidate_key(c) for c in local if row_acceptance(model,c)}
                check('projection/'+name+'/'+str(deployment)+'/'+scene_id, lambda a=local_expected,b=local_observed: equal(a,b))
                local_sets[scene_id] = local_observed
                check('physical_domain/'+name+'/'+str(deployment)+'/'+scene_id, lambda m=model,i=instance:
                      equal(m.instance['platform'],i['platform']))
                check('unweighted_objective/'+name+'/'+str(deployment)+'/'+scene_id,
                      lambda m=model: equal(m.instance['scenarios'][0]['weight'],'1'))
            joined = set()
            scene_ids = list(local_sets)
            for local_tuple in product(*(local_sets[s] for s in scene_ids)):
                joined.add(tuple(sorted(item for c in local_tuple for item in c)))
            check('factorization/'+name+'/'+str(deployment),lambda a=expected,b=joined: equal(a,b))
            domain_records.append({'deployment': deployment,'whole_legal_count':len(expected),
                                   'local_legal_counts': {s:len(v) for s,v in local_sets.items()},
                                   'model_summary':whole.summary()})
        projection_records[name] = {'cartesian_assignments':len(all_candidates),
                                    'legal_assignments':len(legal_sets[name]),'deployments':domain_records}
    save(args.out/'projection.json',projection_records)
    records['projection'] = projection_records

    # Observe, rather than presume, the requested schedule cases in the oracle.
    observed = set()
    for c in legal_sets['parallel_cpu']:
        rows = next(iter(c['scenes'].values()))
        if rows[0]['unit'] != rows[1]['unit'] and rows[0]['opp']==rows[1]['opp'] and rows[0]['start_ms']==rows[1]['start_ms']:
            observed.add('same_frequency_parallel')
        if any(F(r['start_ms'])>0 for r in rows): observed.add('waiting')
    for c in independent_assignments(*fixture_map['parallel_cpu']):
        if independent_check(fixture_map['parallel_cpu'][0],c).get('reason')=='busy_domain_conflict':
            observed.add('different_frequency_conflict')
    for c in legal_sets['chain_fractional']:
        oracle=independent_check(fixture_map['chain_fractional'][0],c)
        if any(r['end'].denominator!=1 for s in oracle['scenes'].values() for r in s['rows'].values()):
            observed.add('fractional_end')
    check('oracle/requested_schedule_cases',lambda: require({'same_frequency_parallel','waiting',
          'different_frequency_conflict','fractional_end'}<=observed,str(observed)))
    check('deadline/exact_boundary_retained',lambda: require(any(
        r['end']==F('34/3') for c in legal_sets['deadline_fraction']
        for s in independent_check(fixture_map['deadline_fraction'][0],c)['scenes'].values()
        for r in s['rows'].values()),'no exact-deadline legal assignment'))

    # Fresh interval kernels and old/new physical matrices on one tiny fixture.
    instance,starts=fixture_map['one_stage_energy']
    mapping={'A.pre':'CPU1'}
    old_physics=build(instance,config,starts,prefilter=False,module=old,physics=True)
    default_physics=build(instance,config,starts,prefilter=False,physics=True)
    check('default/physics_rows_and_bounds_unchanged',lambda: equal(
        (old_physics.names,old_physics.rows,old_physics.lb,old_physics.ub,old_physics.integer,old_physics.c),
        (default_physics.names,default_physics.rows,default_physics.lb,default_physics.ub,default_physics.integer,default_physics.c)))
    check('default/physics_interval_coefficients_unchanged',lambda: equal(
          coefficient_signature(old_physics),coefficient_signature(default_physics)))
    rebuilt=build(instance,config,starts,deployment=mapping,scene=instance['scenarios'][0]['id'],physics=True)
    scene_id=instance['scenarios'][0]['id']
    physical_records=[]
    for candidate in legal_sets['one_stage_energy']:
        if not compatible(instance,candidate,mapping): continue
        vectors=[]
        for label,model in [('old',old_physics),('rebuilt',rebuilt)]:
            vector=milp.lift_candidate(model,candidate)
            vectors.append((model,vector))
            residual=max(exact_row_residuals(model,vector),default=F(0))
            bounds=max([0.]+[a-v for a,v in zip(model.lb,vector)]+[v-b for v,b in zip(vector,model.ub)])
            check('physical_lift/'+candidate_key(candidate).__repr__()+'/'+label,lambda r=residual,b=bounds:
                  require(r<=F('1e-9') and b<=1e-9,str((r,b))))
            check('roundtrip/'+candidate_key(candidate).__repr__()+'/'+label,lambda m=model,v=vector,c=candidate:
                  equal(candidate_key(milp.decode(m,v)),candidate_key(c)))
            physical_records.append({'candidate':candidate,'model':label,'maximum_row_residual':str(residual),
                                     'maximum_bound_residual':bounds,'objective_J':float(np.dot(model.c,vector))})
        energy=[float(np.dot(m.c,v)) for m,v in vectors]
        check('resegmentation/independent_exponential_energy/'+candidate_key(candidate).__repr__(),
              lambda e=energy: require(abs(e[0]-e[1])<=1e-12,str(e)))
        evaluation=evaluate_candidate(instance,candidate,config['accuracy_targets'],Budget(seconds=60))
        check('resegmentation/common_continuous_enclosure/'+candidate_key(candidate).__repr__(),
              lambda e=evaluation,v=energy: require(e['state']=='SAFE' and all(
                  F(e['weighted_energy_J'][0])-F('1e-12')<=F.from_float(x)<=F(e['weighted_energy_J'][1])+F('1e-12') for x in v),str(e)))
    save(args.out/'physical_lifts.json',physical_records)
    certificate_records=[]
    for certificate in rebuilt.energy_bound_certificates:
        certificate_records.append([str(v) for v in box_certificate_check(rebuilt,certificate)])
    check('fresh_energy_bounds/all_exported_box_certificates',lambda: require(
          len(certificate_records)==sum(len(m['energy']) for m in rebuilt.scenes.values()),'missing bound certificate'))
    save(args.out/'energy_bound_certificates.json',certificate_records)
    meta=rebuilt.scenes[scene_id]
    units={u['id']:u for u in instance['platform']['units']}
    unused=['GPU','NPU']
    actual_unused=[d for d,data in instance['platform']['domains'].items()
                   if all(uid!='CPU1' for uid in data['unit_ids'])]
    for d in actual_unused:
        entry=instance['scenarios'][0]['entry']['domain_opp'][d]
        check('unused_domain/'+d+'/entry_opp_fixed',lambda d=d,e=entry: require(all(
            rebuilt.lb[meta['rho'][l,d,o]]==rebuilt.ub[meta['rho'][l,d,o]]==float(o==e)
            for l in range(len(meta['events'])-1) for o in instance['platform']['domains'][d]['opps']),d))
    state=tuple(instance['scenarios'][0]['entry']['domain_opp'][d] for d in instance['platform']['domains'])
    baseline,slopes=rebuilt.coefficients.power(state)
    check('unused_physics/all_nodes_baseline_leakage_retained',lambda: require(
          len(baseline)==len(slopes)==4 and all(v>0 for v in baseline) and all(v>0 for v in slopes),str((baseline,slopes))))
    check('unused_physics/conductance_retained',lambda: equal(
          rebuilt.instance['platform']['conductance_W_per_K'],instance['platform']['conductance_W_per_K']))
    check('unused_physics/full_node_state_retained',lambda: require(all(len(row)==4 for row in meta['theta']),'deleted thermal node'))

    # Genuine event removal: the old A.main CPU/GPU alternatives contribute
    # endpoints absent after fixing A.main=NPU0. Keep all retained NPU OPPs
    # and both declared start choices; do not freeze a candidate's frequency.
    chain,chain_starts=fixture_map['chain_fractional']
    chain_sid=chain['scenarios'][0]['id']
    chain_mapping={'A.pre':'CPU1','A.main':'NPU0'}
    chain_old=build(chain,config,chain_starts,prefilter=False,physics=True)
    chain_new=build(chain,config,chain_starts,deployment=chain_mapping,scene=chain_sid,physics=True)
    deleted=set(chain_old.scenes[chain_sid]['events'])-set(chain_new.scenes[chain_sid]['events'])
    check('resegmentation/genuinely_removed_events',lambda: require(bool(deleted) and
          set(chain_new.scenes[chain_sid]['events'])<=set(chain_old.scenes[chain_sid]['events']),str(deleted)))
    compatible_chain=[c for c in legal_sets['chain_fractional'] if compatible(chain,c,chain_mapping)]
    selected_chain=[compatible_chain[0],compatible_chain[-1]]
    require(candidate_key(selected_chain[0])!=candidate_key(selected_chain[-1]),'need two distinct chain schedules')
    chain_records=[]
    for candidate in selected_chain:
        common_chain=evaluate_candidate(chain,candidate,config['accuracy_targets'],Budget(seconds=60))
        flows={}
        for label,model in [('old',chain_old),('rebuilt',chain_new)]:
            vector=milp.lift_candidate(model,candidate)
            residual=max(exact_row_residuals(model,vector),default=F(0))
            bounds=max([0.]+[a-v for a,v in zip(model.lb,vector)]+[v-b for v,b in zip(vector,model.ub)])
            check('resegmentation/chain/'+label+'/matrix_admission/'+candidate_key(candidate).__repr__(),
                  lambda r=residual,b=bounds:require(r<=F('1e-9') and b<=1e-9,str((r,b))))
            flow=enclosed_flow(model,candidate,chain_sid)
            flows[label]=flow
            continuous=common_chain['scenes'][chain_sid]
            check('resegmentation/chain/'+label+'/energy_and_temperature_enclosure/'+candidate_key(candidate).__repr__(),
                  lambda f=flow,c=continuous:require(overlap(f['energy_J'],c['energy_J']) and all(
                      overlap(f['final_temperature_degC'][n],c['final_temperature_degC'][n]) for n in chain['platform']['node_order']),str((f,c))))
            check('resegmentation/chain/'+label+'/unbounded_expm_only_crosscheck/'+candidate_key(candidate).__repr__(),
                  lambda m=model,v=vector,c=common_chain:require(c['state']=='SAFE' and
                      F(c['weighted_energy_J'][0])-F('1e-12')<=F.from_float(float(np.dot(m.c,v)))<=
                      F(c['weighted_energy_J'][1])+F('1e-12'),'physical exponential energy mismatch'))
        check('resegmentation/chain/old_and_fresh_enclosures_overlap/'+candidate_key(candidate).__repr__(),
              lambda f=flows:require(overlap(f['old']['energy_J'],f['rebuilt']['energy_J']) and all(
                  overlap(f['old']['final_temperature_degC'][n],f['rebuilt']['final_temperature_degC'][n]) for n in chain['platform']['node_order']),str(f)))
        chain_records.append({'candidate':candidate,'coefficient_interval_flows':flows,
                              'common_evaluation':common_chain})
    chain_certificates=[box_certificate_check(chain_new,c) for c in chain_new.energy_bound_certificates]
    check('fresh_energy_bounds/changed_event_grid_certificates',lambda: require(
          len(chain_certificates)==len(chain_new.scenes[chain_sid]['energy']),'missing regenerated certificate'))
    save(args.out/'changed_event_physics.json',{'deleted_event_times_s':sorted(map(str,deleted)),
        'original_model':chain_old.summary(),'rebuilt_model':chain_new.summary(),'checks':chain_records,
        'certificate_maxima':[[str(v) for v in row] for row in chain_certificates],
        'scope':'interval enclosures and independent expm numerical crosscheck; no old/fresh matrix equivalence claim'})

    # The idle-control simplification follows the declared entrance, not a
    # hardcoded low OPP. No thermal node or idle physical parameter is removed.
    high=deepcopy(instance)
    high['id']='fixture_scene_unused_entry_H'
    for d in actual_unused: high['scenarios'][0]['entry']['domain_opp'][d]='H'
    high_model=build(high,config,starts,deployment=mapping,scene=scene_id)
    check('unused_domain/non_L_entry_preserved',lambda:require(all(
        high_model.lb[high_model.scenes[scene_id]['rho'][l,d,o]]==
        high_model.ub[high_model.scenes[scene_id]['rho'][l,d,o]]==float(o=='H')
        for d in actual_unused for l in range(len(high_model.scenes[scene_id]['events'])-1)
        for o in high['platform']['domains'][d]['opps']),'hardcoded idle L'))
    no_options=deepcopy(instance);no_options['id']='fixture_scene_no_remaining_options'
    no_options['scenarios'][0]['requests'][0]['deadline_ms']='1'
    empty_model=build(no_options,config,starts,deployment=mapping,scene=scene_id)
    check('domain/empty_stage_is_explicit_contradiction',lambda:require(
        empty_model.preprocessing['empty_stage_option_sets'] and any(
            not row['coef'] and row['rhs']<0 for row in empty_model.rows),'empty Stage removed'))
    def rejects(fn):
        try:fn()
        except ValueError:return
        raise AssertionError('invalid fixed-deployment interface accepted')
    for label,x in [('missing',{}),('extra',dict(mapping,unknown='CPU1')),('illegal',{'A.pre':'NPU0'})]:
        check('input/'+label+'_deployment_rejected',lambda x=x:rejects(lambda:
            build(instance,config,starts,deployment=x,scene=scene_id)))
    check('input/unknown_scene_rejected',lambda:rejects(lambda:
          build(instance,config,starts,deployment=mapping,scene='unknown')))
    shared_instance,shared_starts=fixture_map['shared_two_scenes']
    # Completeness is validated against all scenes before projecting one.
    two_stage=deepcopy(chain)
    two_stage['scenarios'].append(deepcopy(shared_instance['scenarios'][1]))
    two_stage['stage_modes']['A.pre']=deepcopy(chain['stage_modes']['A.pre'])
    def rejects_before_projection():
        with patch.object(milp,'Model',side_effect=AssertionError('invalid deployment reached model construction')):
            rejects(lambda:build(two_stage,config,{**chain_starts,**shared_starts},deployment={'A.pre':'CPU1'},
                                 scene=shared_instance['scenarios'][1]['id']))
    check('input/full_deployment_required_before_scene_projection',rejects_before_projection)

    # Single-scene receipts carry no original scenario weight; one outer sum.
    full,starts=fixture_map['shared_two_scenes']
    deployment={'A.pre':'CPU1'}
    whole_candidate=next(c for c in legal_sets['shared_two_scenes'] if compatible(full,c,deployment))
    candidates={s['id']:{'scenes':{s['id']:whole_candidate['scenes'][s['id']]}} for s in full['scenarios']}
    budget=Budget(seconds=180)
    receipts={sid:adapter.evaluate_scene(full,sid,deployment,c,config['accuracy_targets'],budget) for sid,c in candidates.items()}
    combined=adapter.aggregate_scene_receipts(full,deployment,receipts,candidates,config['accuracy_targets'],budget)
    common=evaluate_candidate(full,whole_candidate,config['accuracy_targets'],Budget(seconds=60))
    check('receipts/unweighted_and_original_weight_aggregation',lambda: require(
        all(r['state']=='SAFE' and r['unweighted'] and r['deployment_feasibility']=='NOT_DECIDED' for r in receipts.values())
        and combined['state']=='SAFE' and combined['deployment_feasibility']=='ALL_SCENES_SAFE_WITNESS'
        and overlap(combined['weighted_energy_J'],common['weighted_energy_J']),str(combined)))
    expected=I(0)
    for s in full['scenarios']: expected+=I(*receipts[s['id']]['energy_J'])*I.rational(F(s['weight']))
    check('receipts/weights_applied_exactly_once',lambda: equal(combined['weighted_energy_J'],expected.data()))
    check('receipts/not_optimality_or_deployment_exclusion',lambda: require(
        not any(k in combined for k in ('optimal','optimality_proven','deployment_infeasible')),'unsupported proof field'))
    wrong=deepcopy(deployment);wrong['A.pre']='CPU2'
    sid=full['scenarios'][0]['id']
    check('receipts/deployment_mismatch_rejected',lambda: equal(adapter.evaluate_scene(
        full,sid,wrong,candidates[sid],config['accuracy_targets'],Budget(seconds=60))['reason'],'FIXED_DEPLOYMENT_MISMATCH'))
    missing=dict(receipts);missing.pop(sid)
    check('receipts/missing_scene_no_global_U',lambda: require(not adapter.aggregate_scene_receipts(
        full,deployment,missing,candidates,config['accuracy_targets'],budget)['rankable_energy'],'missing accepted'))
    altered=deepcopy(receipts);altered[sid]['energy_J']=['0','0']
    check('receipts/tampering_rejected',lambda: require(adapter.aggregate_scene_receipts(
        full,deployment,altered,candidates,config['accuracy_targets'],budget)['receipt_errors'][sid]=='RECEIPT_PAYLOAD_MISMATCH','tampering accepted'))
    check('receipts/different_budget_rejected',lambda: require(adapter.aggregate_scene_receipts(
        full,deployment,receipts,candidates,config['accuracy_targets'],Budget(seconds=60))['state']=='UNRESOLVED','cross-budget accepted'))
    # Expiry at the outer handoff retains old SAFE receipts but creates no U.
    with patch.object(budget,'check',side_effect=Exhausted('wall_time_limit')):
        expired=adapter.aggregate_scene_receipts(full,deployment,receipts,candidates,config['accuracy_targets'],budget)
    check('budget/no_after_deadline_global_U',lambda: require(expired['state']=='UNRESOLVED' and
        not expired['rankable_energy'] and expired['weighted_energy_J'] is None and len(expired['scenes'])==2,str(expired)))
    # No numerical propagation panel, no false SAFE or violation.
    limited_budget=Budget(seconds=60,panels=0)
    limited_receipts={s:adapter.evaluate_scene(full,s,deployment,c,config['accuracy_targets'],limited_budget) for s,c in candidates.items()}
    limited=adapter.aggregate_scene_receipts(full,deployment,limited_receipts,candidates,config['accuracy_targets'],limited_budget)
    check('budget/panel_limit_remains_unresolved',lambda: require(limited['state']=='UNRESOLVED' and
          limited['weighted_energy_J'] is None and not limited['violations'],str(limited)))
    # Entry violations are exact witnesses even before propagation; zero-weight
    # scenes must also block global SAFE aggregation.
    unsafe=deepcopy(full)
    unsafe['id']='fixture_scene_unsafe_entry'
    unsafe['scenarios'][0]['weight']='1';unsafe['scenarios'][1]['weight']='0'
    unsafe['scenarios'][1]['maximum_temperature_degC'][0]='29'
    unsafe_budget=Budget(seconds=120)
    unsafe_receipts={s:adapter.evaluate_scene(unsafe,s,deployment,c,config['accuracy_targets'],unsafe_budget) for s,c in candidates.items()}
    with patch.object(unsafe_budget,'check',side_effect=Exhausted('wall_time_limit')):
        violation=adapter.aggregate_scene_receipts(unsafe,deployment,unsafe_receipts,candidates,config['accuracy_targets'],unsafe_budget)
    check('budget/committed_violation_survives_handoff_expiry',lambda: require(
          violation['state']=='THERMAL_VIOLATION' and violation['violations'] and
          violation['weighted_energy_J'] is None and len(violation['scenes'])==2,str(violation)))
    check('receipts/zero_weight_scene_still_requires_safety',lambda: require(
          unsafe_receipts[unsafe['scenarios'][1]['id']]['state']=='THERMAL_VIOLATION','zero weight skipped'))
    # Adapter envelopes are not the old model-feedback schema.
    unsafe_sid=unsafe['scenarios'][1]['id']
    feedback_model=build(unsafe,config,starts,deployment=deployment,scene=unsafe_sid,physics=True)
    def reject_adapter_feedback():
        try: milp.add_thermal_feedback(feedback_model,candidates[unsafe_sid],unsafe_receipts[unsafe_sid])
        except (KeyError,ValueError): return
        raise AssertionError('adapter receipt admitted as model-feedback receipt')
    check('feedback/adapter_identity_not_silently_reused',reject_adapter_feedback)
    model_receipt=milp.evaluate_model_candidate(feedback_model,candidates[unsafe_sid],config['accuracy_targets'],Budget(seconds=60))
    check('feedback/model_view_receipt_identity_matches',lambda: equal(model_receipt['evidence_identity'],{
        'input_sha256':milp._digest(feedback_model.instance),
        'candidate_sha256':milp._digest(candidates[unsafe_sid])}))
    feedback=milp.add_thermal_feedback(feedback_model,candidates[unsafe_sid],model_receipt)
    check('feedback/model_view_violation_accepted',lambda: require(feedback['rows_added']>0,str(feedback)))
    save(args.out/'scene_receipts.json',{'full_input':full,'deployment':deployment,'candidates':candidates,
        'receipts':receipts,'aggregate':combined,'common_evaluation':common,
        'expired_aggregate':expired,'limited_aggregate':limited,'violation_aggregate':violation,
        'model_feedback':feedback})
    # No source or frozen input changed during the checks.
    final_hashes={n:hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in source_names}
    check('integrity/source_and_frozen_config_stable',lambda: equal(source_hashes,final_hashes))
    summary={'state':'PASS' if all(c['status']=='PASS' for c in checks) else 'FAIL',
        'checks_passed':sum(c['status']=='PASS' for c in checks),'checks_total':len(checks),
        'elapsed_s':time.monotonic()-started,'reference_commit':REFERENCE,
        'solver_called':False,'original_scale_model_built':False,'formal_experiment_result':False,
        'scope':'scheduling projection exact over correctness Cartesian domain; physical interval and numerical admission crosschecks; no performance comparison'}
    save(args.out/'summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False))
    return 0 if summary['state']=='PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())
