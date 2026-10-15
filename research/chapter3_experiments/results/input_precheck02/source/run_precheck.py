"""Input and schedule-accounting prechecks; no optimizer or thermal simulation.

The independent option oracle enumerates local choices only. Hand-built
schedule fixtures test correctness and never enter research-method statistics.
PASS applies to this layer, not to full thermal safety or experiment readiness.
"""
import argparse
from copy import deepcopy
import csv
from fractions import Fraction as F
import hashlib
import itertools
import json
from pathlib import Path
import shutil
import sys
import time

from inputs import load_config, build_instances, expand_options
from schedules import validate_schedule

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def ceil_grid(value, grid):
    return -((-value) // grid) * grid


def mode(problem, stage, unit, opp):
    return next(m for m in problem['stage_modes'][stage]
                if m['unit_id'] == unit and m['opp_id'] == opp)


def fixture(problem, opp='H'):
    """Hand-defined test mapping; not a search method or research result."""
    candidate = {'scenes': {}}
    for scene in problem['scenarios']:
        rows = []
        for req in scene['requests']:
            unit = 'CPU1' if req['application'] == 'A' else 'CPU2'
            start = F(req['release_ms'])
            for sid in req['stage_instance_ids']:
                stage = next(s for s in scene['stage_instances'] if s['id'] == sid)
                start = ceil_grid(start, F(problem['start_grid_ms']))
                rows.append({'stage_id': sid, 'unit': unit, 'opp': opp, 'start_ms': str(start)})
                start += F(mode(problem, stage['shared_stage_id'], unit, opp)['duration_ms'])
        candidate['scenes'][scene['id']] = rows
    return candidate


def all_rows(candidate):
    return [r for rows in candidate['scenes'].values() for r in rows]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=HERE / 'config_v01.json')
    parser.add_argument('--output', type=Path, default=HERE / 'results/input_precheck01')
    args = parser.parse_args()
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    source_dir = folder / 'source'
    source_dir.mkdir()
    sources = [HERE / n for n in ['inputs.py', 'schedules.py', 'run_precheck.py']]
    sources.append(args.config.resolve())
    hashes = {str(p.relative_to(REPO)) if p.is_relative_to(REPO) else str(p):
              hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    for path in sources:
        shutil.copy2(path, source_dir / path.name)
    checks, manifests, stats, fixture_records = [], [], [], {}
    start = time.monotonic()

    def check(name, fn):
        try:
            detail = fn()
            checks.append({'name': name, 'status': 'PASS', 'detail': detail})
        except Exception as exc:
            checks.append({'name': name, 'status': 'FAIL',
                           'error': f'{type(exc).__name__}: {exc}'})

    def equal(actual, expected):
        require(actual == expected, f'{actual!r} != {expected!r}')

    config = load_config(args.config)
    instances = build_instances(config)
    by_id = {p['id']: p for p in instances}
    base = by_id['base__R1']
    check('input_count_and_unique_ids', lambda: equal((len(instances), len(by_id)), (95, 95)))
    check('condition_count', lambda: equal(len(config['conditions']), 19))
    check('complete_stage_catalog', lambda: equal(
        {s['id'] for s in config['stage_catalog']},
        {f'{a}.{s}' for a in 'ABC' for s in ['pre', 'main', 'post']}))
    check('window_and_grid', lambda: equal((F(base['window_ms']), F(base['start_grid_ms'])), (F(400), F(5))))
    check('no_borrowed_old_lattice', lambda: equal(F(mode(base, 'A.main', 'CPU1', 'M')['duration_ms']), F(304, 3)))
    check('minimal_stage_4ms', lambda: equal(F(mode(by_id['base__R2'], 'A.post', 'CPU1', 'H')['duration_ms']), F(4)))
    check('declared_call_count', lambda: equal(
        (len(instances)*(2+len(config['run_protocol']['sa_seeds'])) +
         sum(p['ablation_input'] for p in instances)), 675))
    check('algorithm_protocol_still_incomplete', lambda: equal(
        (config['run_protocol']['method_rules_complete'], config['run_protocol']['solver_options_complete']),
        (False, False)))

    def physical():
        p = config['platform']
        c = list(map(F, p['heat_capacity_J_per_K']))
        g = [list(map(F, row)) for row in p['conductance_W_per_K']]
        require(len(c) == len(g) == 4 and all(x > 0 for x in c), 'heat capacity')
        for i in range(4):
            require(len(g[i]) == 4, 'G dimensions')
            for j in range(4):
                require(g[i][j] == g[j][i], 'G symmetry')
                if i != j:
                    require(g[i][j] <= 0, 'passive coupling')
        equal([sum(row) for row in g], [F('.04'), F('.04'), F('.06'), F('.05')])
        nodes = p['node_order']
        lam_max, min_power = [], []
        low = F(p['power_model_temperature_range_degC'][0])
        for node in nodes:
            unit = next(u for u in p['units'] if u['thermal_node_id'] == node)
            domain = p['domains'][unit['domain_id']]
            lam_max.append(max(map(F, domain['local_temperature_slope_W_per_K'].values())))
            values = []
            for opp in domain['opps']:
                values.append(F(domain['baseline_W'][opp]) * F(domain['baseline_heat_distribution'][nodes.index(node)]) +
                              F(domain['local_temperature_slope_W_per_K'][opp]) * (low-F(p['reference_temperature_degC'])))
            min_power.append(min(values))
        equal(min_power, [F('.29'), F('.29'), F('.38'), F('.235')])
        margins = [sum(g[i])-lam_max[i] for i in range(4)]
        equal(margins, [F('.036'), F('.036'), F('.052'), F('.044')])
        equal(min(margins[i]/c[i] for i in range(4)), F('.65'))
        for domain in p['domains'].values():
            equal(sum(map(F, domain['baseline_heat_distribution'])), F(1))
        equal(sum(map(F, p['external_common_heat_distribution'])), 0)
        return {'minimum_node_power_W': list(map(str, min_power)),
                'leakage_stability_margins_W_per_K': list(map(str, margins)),
                'interpretation': 'algebraic_consistency_not_thermal_safety'}
    check('physical_accounting_and_stability', physical)

    def check_instance(p):
        equal(p['platform'], config['platform'])
        equal(sum(F(s['weight']) for s in p['scenarios']), F(1))
        for pair in [['A', 'B'], ['A', 'C']]:
            equal(sum(F(s['weight']) for s in p['scenarios'] if s['application_pair'] == pair), F(1, 2))
        stages = {s['id']: s for s in config['stage_catalog']}
        expected_means = {}
        for device in ['CPU', 'GPU', 'NPU']:
            terms = [(F(s['profiles'][device]['d_ref_ms'])*F(p['duration_scale'][s['application']]),
                      F(s['profiles'][device]['alpha'])) for s in stages.values() if device in s['profiles']]
            expected_means[device] = sum(w*a for w,a in terms)/sum(w for w,a in terms)
        equal({d:F(v) for d,v in p['catalog_duration_weighted_mean_alpha'].items()}, expected_means)
        for sid, modes in p['stage_modes'].items():
            source = stages[sid]
            legal_units = [u for u in p['platform']['units'] if u['device_class'] in source['profiles']
                           and u['device_class'] in p['settings']['available_device_classes']]
            equal({(m['unit_id'], m['opp_id']) for m in modes},
                  {(u['id'], k) for u in legal_units for k in p['platform']['domains'][u['domain_id']]['opps']})
            for m in modes:
                d = next(u['device_class'] for u in legal_units if u['id'] == m['unit_id'])
                raw = source['profiles'][d]
                ref_time = F(raw['d_ref_ms'])*F(p['duration_scale'][source['application']])
                alpha = (F(1) if p['response_variant']=='R' else expected_means[d]
                         if p['response_variant']=='M' else F(raw['alpha']))
                opps = p['platform']['domains'][d]['opps']
                op, high = opps[m['opp_id']], opps['H']
                equal(F(m['duration_ms']), ref_time*((1-alpha)+alpha*F(high['frequency_GHz'])/F(op['frequency_GHz'])))
                equal(F(m['activity_power_W']), F(raw['q_ref_W'])*(F(op['voltage_V'])/F(high['voltage_V']))**2*
                      F(op['frequency_GHz'])/F(high['frequency_GHz']))
        for scene in p['scenarios']:
            equal(len(scene['requests']), 2*p['settings']['requests_per_application'])
            equal(len(scene['stage_instances']), 3*len(scene['requests']))
            equal(len(scene['dependencies']), 2*len(scene['requests']))
            equal(scene['entry']['unfinished_work'], [])
            equal(scene['entry']['domain_opp'], {'CPU':'L','GPU':'L','NPU':'L'})
            require(all(F(t) <= F(mx) for t,mx in zip(scene['entry']['temperature_degC'],scene['maximum_temperature_degC'])), 'entry')
            for req in scene['requests']:
                app = req['application']
                ref = sum(F(s['profiles']['CPU']['d_ref_ms']) for s in stages.values() if s['application']==app)*F(p['duration_scale'][app])
                equal(F(req['deadline_ms']), F(req['release_ms'])+F(p['settings']['deadline_beta'])*ref)
                require(F(req['deadline_ms']) <= F(p['window_ms']), 'deadline outside window')
        return {'scenarios': len(p['scenarios']), 'shared_stage_identities': len(p['stage_modes'])}

    def check_options(p):
        options = expand_options(p, config)
        # Independent Cartesian oracle: explicit declared grid x modes, then
        # release/window filtering; no reuse of production ceil/floor bounds.
        oracle = set()
        for scene in p['scenarios']:
            reqs = {r['id']: r for r in scene['requests']}
            for st in scene['stage_instances']:
                req = reqs[st['request_id']]
                for m in p['stage_modes'][st['shared_stage_id']]:
                    for t in range(0, 401, 5):
                        if F(t) >= F(req['release_ms']) and F(t)+F(m['duration_ms']) <= F(400):
                            oracle.add((scene['id'], st['id'], m['unit_id'], m['opp_id'], F(t)))
        found = {(o['scenario_id'],o['stage_instance_id'],o['unit_id'],o['opp_id'],F(o['start_ms'])) for o in options}
        equal(found, oracle)
        equal(len(options), len(found))
        require(all(F(o['end_ms']) == F(o['start_ms'])+F(o['duration_ms']) for o in options), 'rounded end')
        require(any(F(o['end_ms'])>F(o['request_deadline_ms']) for o in options), 'options prematurely remove deadline rows')
        scene_stats = []
        for scene in p['scenarios']:
            subset = [o for o in options if o['scenario_id']==scene['id']]
            events = {F(0), F(p['window_ms'])} | {F(o[k]) for o in subset for k in ['start_ms','end_ms']}
            scene_stats.append({'scenario_id': scene['id'], 'stage_instances': len(scene['stage_instances']),
                                'local_options': len(subset), 'potential_events': len(events)})
        stats.extend(dict(instance_id=p['id'], **s) for s in scene_stats)
        manifests.append({'id':p['id'], 'input_sha256':digest(p), 'condition':p['condition_id'],
                          'sample':p['sample_id'], 'local_option_count':len(options), 'scenarios':scene_stats})
        return {'local_options':len(options), 'complete_arrangements_enumerated':False}

    for p in instances:
        check('input/'+p['id'], lambda p=p: check_instance(p))
        check('local_option_coverage/'+p['id'], lambda p=p: check_options(p))
    check('actual_maximum_deadline', lambda: equal(max(F(r['deadline_ms']) for p in instances for s in p['scenarios'] for r in s['requests']), F('290.4')))
    check('single_factor_conditions', lambda: require(all(
        len([k for k,v in p['settings'].items() if v!=base['settings'][k]]) <= 1 for p in instances), 'multiple factors changed'))

    good = fixture(base)
    good_result = validate_schedule(base, good)
    fixture_records['base_hand_built_not_a_method_result'] = {'candidate': good, 'check':good_result}
    check('schedule/same_frequency_cpu_concurrency', lambda: equal(good_result['state'], 'SCHEDULE_VALID_THERMAL_UNCHECKED'))
    check('schedule/no_premature_energy_or_safety', lambda: require(
        good_result['thermal_status']=='NOT_EVALUATED' and good_result['energy_status']=='NOT_EVALUATED' and
        not any(k in good_result for k in ['energy_J','safe','optimal']), 'unsupported output claim'))

    def reconstruction():
        for scene in good_result['scenes'].values():
            segments = scene['segments']
            equal(F(segments[0]['start_ms']), F(0))
            equal(F(segments[-1]['end_ms']), F(400))
            require(all(a['end_ms']==b['start_ms'] for a,b in zip(segments,segments[1:])), 'segment coverage')
            equal(segments[-1]['domain_opps'], {'CPU':'H','GPU':'L','NPU':'L'})
            equal(segments[-1]['active_stage_ids'], [])
            for seg in segments:
                b = seg['baseline_by_node_W']
                equal(F(b['CPU1'])+F(b['CPU2']), F('1.3'))
                equal(sum(map(F, b.values())), sum(map(F, seg['baseline_by_power_group_W'].values())))
                equal(F(seg['external_common_power_W']), F('.3'))
                equal(F(seg['external_common_injected_heat_W']), 0)
                for n in base['platform']['node_order']:
                    equal(F(seg['node_power_constant_at_reference_W'][n]), F(b[n])+F(seg['activity_by_node_W'][n]))
            tail = segments[-1]
            equal(tail['local_leakage_slope_W_per_K']['CPU1'], str(F('.004')))
            # Unequal local temperatures must stay local, even under shared OPP.
            equal(F(tail['node_power_constant_at_reference_W']['CPU1'])+F('.004')*(50-25), F('.75'))
            equal(F(tail['node_power_constant_at_reference_W']['CPU2'])+F('.004')*(60-25), F('.79'))
    check('schedule/whole_window_power_reconstruction', reconstruction)

    def rejected(name, candidate, problem=base, reason=None):
        def run():
            result = validate_schedule(problem, candidate)
            fixture_records[name] = {'state': result['state'], 'reason': result.get('reason')}
            equal(result['state'], 'INVALID_SCHEDULE')
            require('scenes' not in result and 'energy_J' not in result, 'invalid prefix leaked')
            if reason:
                equal(result['reason'], reason)
        check('reject/'+name, run)

    scene_ids = list(good['scenes'])
    c=deepcopy(good); c['scenes'].pop(scene_ids[-1]); rejected('missing_scene', c)
    c=deepcopy(good); c['scenes'][scene_ids[0]].pop(); rejected('missing_stage', c)
    c=deepcopy(good); c['scenes'][scene_ids[0]].append(c['scenes'][scene_ids[0]][0]); rejected('duplicate_stage', c)
    c=deepcopy(good); c['scenes'][scene_ids[0]][0]['start_ms']='1'; rejected('nongrid_start', c, reason='START_OUTSIDE_GRID')
    c=deepcopy(good); c['scenes'][scene_ids[0]][0]['start_ms']=0.0; rejected('float_start', c, reason='NONEXACT_SCALAR')
    c=deepcopy(good); c['scenes'][scene_ids[0]][0]['end_ms']='10'; rejected('forged_end', c, reason='CANDIDATE_ROW_FIELDS')
    c=deepcopy(good); c['scenes'][scene_ids[0]][0]['unit']='GPU0'; rejected('unsupported_mode', c)
    c=deepcopy(good); c['scenes'][scene_ids[0]][1]['start_ms']='5'; rejected('precedence', c, reason='DEPENDENCY_VIOLATION')
    c=deepcopy(good)
    for r in c['scenes'][scene_ids[0]]:
        if '::B_r1::' in r['stage_id']: r['unit']='CPU1'
    rejected('unit_overlap', c, reason='EXECUTION_UNIT_OVERLAP')
    c=deepcopy(good)
    for r in c['scenes'][scene_ids[0]]:
        if '::B_r1::' in r['stage_id']: r['opp']='M'
    # Recompute the B-chain starts to isolate the frequency conflict from DAG timing.
    cm=fixture(base, 'M')
    for i,r in enumerate(c['scenes'][scene_ids[0]]):
        if '::B_r1::' in r['stage_id']: c['scenes'][scene_ids[0]][i]=cm['scenes'][scene_ids[0]][i]
    rejected('overlapping_different_cpu_opps', c, reason='FREQUENCY_DOMAIN_CONFLICT')
    c=deepcopy(good)
    for r in c['scenes'][scene_ids[1]]:
        r['unit']='CPU2' if r['unit']=='CPU1' else 'CPU1'
    rejected('cross_scene_shared_mapping', c, reason='SHARED_DEPLOYMENT_MISMATCH')
    p=deepcopy(base); p['scenarios'][0]['requests'][0]['deadline_ms']='94'
    rejected('individual_request_deadline_before_window_end', good, p, 'REQUEST_DEADLINE_EXCEEDED')
    p=deepcopy(base); p['scenarios'][0]['requests'][0]['release_ms']='5'
    rejected('before_release', good, p, 'BEFORE_RELEASE')
    p=deepcopy(base); p['execution_rules']['idle_holds_last_opp']=False
    rejected('changed_idle_semantics', good, p, 'UNSUPPORTED_EXECUTION_RULE')

    # Single-request fixtures isolate boundary, fractional end, fork/join, and
    # idle OPP retention. They are not modifications to any research instance.
    single=deepcopy(base); single['id']='fixture_single_request'
    single['scenarios']=single['scenarios'][:1]
    s=single['scenarios'][0]; s['weight']='1'; s['requests']=s['requests'][:1]
    s['requests'][0]['deadline_ms']='400'
    ids=set(s['requests'][0]['stage_instance_ids'])
    s['stage_instances']=[x for x in s['stage_instances'] if x['id'] in ids]
    s['dependencies']=[e for e in s['dependencies'] if set(e)<=ids]
    c=fixture(single); rows=c['scenes'][s['id']]
    rows[1]['opp']='M'; rows[2]['start_ms']='115'; rows[2]['opp']='H'
    r=validate_schedule(single,c)
    check('schedule/busy_boundary_switch_and_fractional_finish', lambda: (
        equal(r['state'],'SCHEDULE_VALID_THERMAL_UNCHECKED'),
        equal(F(r['scenes'][s['id']]['rows'][1]['end_ms']),F(334,3)),
        require(any(F(g['start_ms'])==F(334,3) and g['domain_opps']['CPU']=='M'
                    for g in r['scenes'][s['id']]['segments']), 'idle must hold M')))
    fixture_records['single_boundary_fractional']={'candidate':c,'check':r}
    waited=deepcopy(c)
    for row in all_rows(waited): row['start_ms']=str(F(row['start_ms'])+5)
    wr=validate_schedule(single,waited)
    check('schedule/legal_wait_and_entry_opp', lambda: (
        equal(wr['state'],'SCHEDULE_VALID_THERMAL_UNCHECKED'),
        equal(wr['scenes'][s['id']]['segments'][0]['domain_opps']['CPU'],'L')))
    first_segment=wr['scenes'][s['id']]['segments'][0]
    check('schedule/local_temperature_idle_power_1_825W', lambda: equal(
        sum(F(v) for v in first_segment['node_power_constant_at_reference_W'].values())+
        sum(F(v) for v in first_segment['local_leakage_slope_W_per_K'].values())*(50-25)+
        F(first_segment['external_common_power_W']), F('1.825')))

    # NPU queuing and independent GPU activity, with the same A deployment in
    # both scenarios. These are explicit accounting fixtures, not solver output.
    accel=deepcopy(good)
    for scene in base['scenarios']:
        for row in accel['scenes'][scene['id']]:
            shared=next(st['shared_stage_id'] for st in scene['stage_instances'] if st['id']==row['stage_id'])
            if shared=='A.main': row.update(unit='NPU0',start_ms='10')
            elif shared=='A.post': row['start_ms']='40'
            elif shared=='B.main': row.update(unit='NPU0',start_ms='40')
            elif shared=='B.post': row['start_ms']='75'
            elif shared=='C.main': row.update(unit='GPU0',start_ms='15')
            elif shared=='C.post': row['start_ms']='60'
    ar=validate_schedule(base,accel)
    check('schedule/npu_half_open_queue_and_gpu_mapping',lambda:equal(ar['state'],'SCHEDULE_VALID_THERMAL_UNCHECKED'))
    fixture_records['accelerator_queue']={'candidate':accel,'check':ar}
    overlap=deepcopy(accel)
    next(r for r in overlap['scenes'][scene_ids[0]] if r['stage_id'].endswith('B.main'))['start_ms']='35'
    rejected('npu_exclusive_overlap',overlap,reason='EXECUTION_UNIT_OVERLAP')
    switched=deepcopy(accel)
    next(r for r in switched['scenes'][scene_ids[0]] if r['stage_id'].endswith('B.main'))['opp']='L'
    next(r for r in switched['scenes'][scene_ids[0]] if r['stage_id'].endswith('B.post'))['start_ms']='100'
    sr=validate_schedule(base,switched)
    check('schedule/empty_npu_switch_independent_of_busy_cpu',lambda:(
        equal(sr['state'],'SCHEDULE_VALID_THERMAL_UNCHECKED'),
        equal(sr['scenes'][scene_ids[0]]['segments'][-1]['domain_opps']['NPU'],'L')))
    # Add a fourth instance for a genuine fork+join topology.
    dag=deepcopy(single); ds=dag['scenarios'][0]
    a,b,d=ds['requests'][0]['stage_instance_ids']; extra=d+'::branch'
    ds['stage_instances'].append(dict(ds['stage_instances'][2], id=extra))
    ds['requests'][0]['stage_instance_ids'].append(extra)
    ds['dependencies']=[[a,b],[a,extra],[b,d],[extra,d]]
    dc={'scenes':{ds['id']:[{'stage_id':a,'unit':'CPU1','opp':'H','start_ms':'0'},
         {'stage_id':b,'unit':'GPU0','opp':'H','start_ms':'10'},
         {'stage_id':extra,'unit':'CPU2','opp':'H','start_ms':'10'},
         {'stage_id':d,'unit':'CPU2','opp':'H','start_ms':'50'}]}}
    dr=validate_schedule(dag,dc)
    check('schedule/fork_join_fixture',lambda:equal(dr['state'],'SCHEDULE_VALID_THERMAL_UNCHECKED'))
    dc_bad=deepcopy(dc); dc_bad['scenes'][ds['id']][-1]['start_ms']='45'
    rejected('join_must_wait_for_all_predecessors',dc_bad,dag,'DEPENDENCY_VIOLATION')

    # Zero-weight scenes are still part of shared deployment and safety scope.
    p=deepcopy(base); p['scenarios'][0]['weight']='1'; p['scenarios'][1]['weight']='0'
    c=deepcopy(good); c['scenes'][scene_ids[1]].pop()
    rejected('zero_weight_scene_still_required',c,p)
    check('source_not_changed_during_precheck',lambda:equal(
        hashes,{str(p.relative_to(REPO)) if p.is_relative_to(REPO) else str(p):
                hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}))
    passed=sum(c['status']=='PASS' for c in checks)
    report={'scope':'input_and_schedule_accounting_only',
            'status':'PASS' if passed==len(checks) else 'FAIL',
            'passed':passed,'total':len(checks),'checks':checks,'source_sha256':hashes,
            'formal_experiments_ready':False,
            'not_tested':['continuous_thermal_enclosure','energy_integration','MILP_encoding',
                          'HEFT_and_SA','budget_and_interruption_evidence'],
            'wall_seconds':time.monotonic()-start}
    def save(name,value):
        (folder/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    save('checks.json',report)
    save('instance_manifest.json',manifests)
    save('schedule_fixtures.json',fixture_records)
    with (folder/'option_statistics.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.DictWriter(stream,fieldnames=['instance_id','scenario_id','stage_instances','local_options','potential_events'])
        writer.writeheader(); writer.writerows(stats)
    print(json.dumps({k:report[k] for k in ['status','passed','total','wall_seconds']},ensure_ascii=False))
    for c in checks:
        if c['status']=='FAIL': print(c['name']+': '+c['error'])
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())
