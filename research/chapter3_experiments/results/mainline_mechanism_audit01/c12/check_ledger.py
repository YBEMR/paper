"""K169: exact stored-input ledger checks, not a scheduler/thermal evaluator.

Only four explicit schedules are supplied. No input/model builder, optimizer,
trajectory propagation, quadrature, exponential evaluation or scientific
module is imported. The passive-RC difference bound is a paper inequality.
"""
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
REPO = ROOT.parents[1]
PREP = ROOT / 'results/p0_batch_preparation01'
PILOT_SHA = 'a8ecd41e41010f13b34962f057323bcd3624b9a2'


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def save_new(path, value):
    if path.exists():
        raise FileExistsError(path)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                               allow_nan=False) + '\n', encoding='utf-8')


def stringify(value):
    if isinstance(value, F):
        return str(value)
    if isinstance(value, dict):
        return {k: stringify(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [stringify(v) for v in value]
    return value


def mode(instance, stage, unit, opp):
    selected = [m for m in instance['stage_modes'][stage]
                if m['unit_id'] == unit and m['opp_id'] == opp]
    assert len(selected) == 1, 'unsupported hand-supplied option'
    return selected[0]


def hand_schedule(instance, covered, cpu_target):
    """R3 only: all numbers are explicit declared choices, never searched."""
    main_unit = 'CPU1' if covered else 'NPU0'
    main_opp = 'H' if covered else 'L'
    choices = {
        'A.pre': ('CPU1', 'H', '0'),
        'A.main': (main_unit, main_opp, '15'),
        'A.post': ('CPU1', 'L', '120'),
        'B.pre': ('CPU2', 'H', '0'),
        'B.main': ('CPU2', 'H', '15'),
        'B.post': ('CPU2', 'L', '120'),
        'C.pre': ('CPU2', 'H', '0'),
        'C.main': ('CPU2' if cpu_target else 'GPU0', 'H', '15'),
        'C.post': ('CPU2', 'L', '120')}
    return {'scenes': {scene['id']: [dict(stage_id=stage['id'],
        unit=choices[stage['shared_stage_id']][0],
        opp=choices[stage['shared_stage_id']][1],
        start_ms=choices[stage['shared_stage_id']][2])
        for stage in scene['stage_instances']] for scene in instance['scenarios']}}


def check_and_ledger(instance, candidate):
    platform, rules = instance['platform'], instance['execution_rules']
    nodes, domains = platform['node_order'], platform['domains']
    units = {u['id']: u for u in platform['units']}
    assert nodes == ['CPU1', 'CPU2', 'GPU0', 'NPU0']
    assert rules['idle_policy'] == 'auto_low_immediate_v1'
    assert rules['idle_holds_last_opp'] is False and F(rules['idle_delay_ms']) == 0
    assert rules['switch_only_when_domain_empty'] is True
    assert all(rules[k] is False for k in ('preemption', 'migration', 'in_stage_opp_change'))
    assert rules['interval_convention'] == '[start,end)'
    assert all(F(v) == 0 for k, v in rules.items() if k.startswith('extra_'))
    assert F(instance['window_ms']) == 400 and F(instance['start_grid_ms']) == 5
    assert instance['response_variant'] == 'H'
    assert set(candidate) == {'scenes'}
    assert set(candidate['scenes']) == {s['id'] for s in instance['scenarios']}
    shared, scenes = {}, {}
    for scene in instance['scenarios']:
        assert scene['entry']['unfinished_work'] == []
        assert set(scene['entry']['domain_opp'].values()) == {'L'}
        assert list(map(F, scene['entry']['temperature_degC'])) == [F(50)] * 4
        assert list(map(F, scene['maximum_temperature_degC'])) == [F(80)] * 4
        stages = {s['id']: s for s in scene['stage_instances']}
        requests = {r['id']: r for r in scene['requests']}
        supplied = candidate['scenes'][scene['id']]
        assert len(stages) == len(supplied) == 6
        assert len({s['stage_id'] for s in supplied}) == 6
        assert {s['stage_id'] for s in supplied} == set(stages)
        rows = []
        for row in supplied:
            assert set(row) == {'stage_id', 'unit', 'opp', 'start_ms'}
            stage = stages[row['stage_id']]
            m = mode(instance, stage['shared_stage_id'], row['unit'], row['opp'])
            u = units[row['unit']]
            assert m['domain_id'] == u['domain_id']
            assert m['thermal_node_id'] == u['thermal_node_id']
            assert m['power_group_id'] == u['power_group_id'] == u['domain_id']
            point = domains[u['domain_id']]['opps'][row['opp']]
            assert F(m['frequency_GHz']) == F(point['frequency_GHz'])
            assert F(m['voltage_V']) == F(point['voltage_V'])
            start, duration = F(row['start_ms']), F(m['duration_ms'])
            request = requests[stage['request_id']]
            assert (start / 5).denominator == 1 and start >= F(request['release_ms'])
            assert duration > 0 and F(m['activity_power_W']) >= 0
            assert start + duration <= F(request['deadline_ms']) <= 400
            if stage['shared_stage_id'] in shared:
                assert shared[stage['shared_stage_id']] == row['unit']
            shared[stage['shared_stage_id']] = row['unit']
            rows.append(dict(row, end_ms=start + duration, start_ms=start,
                shared_stage_id=stage['shared_stage_id'], domain=u['domain_id'],
                node=u['thermal_node_id'], activity=F(m['activity_power_W'])))
        by_id = {r['stage_id']: r for r in rows}
        for before, after in scene['dependencies']:
            assert by_id[before]['end_ms'] <= by_id[after]['start_ms']
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                if max(a['start_ms'], b['start_ms']) < min(a['end_ms'], b['end_ms']):
                    assert a['unit'] != b['unit'], 'execution-unit conflict'
                    assert a['domain'] != b['domain'] or a['opp'] == b['opp'], 'OPP conflict'
        events = sorted({F(0), F(400)} | {r[k] for r in rows for k in ('start_ms', 'end_ms')})
        segments, e = [], F(0)
        for a, b in zip(events, events[1:]):
            active = [r for r in rows if r['start_ms'] <= a < r['end_ms']]
            opps = {}
            reference, slopes = {n: F(0) for n in nodes}, {n: F(0) for n in nodes}
            group_base = {}
            for domain, data in domains.items():
                chosen = {r['opp'] for r in active if r['domain'] == domain}
                assert len(chosen) <= 1
                opps[domain] = next(iter(chosen)) if chosen else 'L'
                baseline = F(data['baseline_W'][opps[domain]])
                group_base[domain] = baseline
                for n, share in zip(nodes, data['baseline_heat_distribution']):
                    reference[n] += baseline * F(share)
                for unit_id in data['unit_ids']:
                    slopes[units[unit_id]['thermal_node_id']] += F(
                        data['local_temperature_slope_W_per_K'][opps[domain]])
            assert sum(reference.values()) == sum(group_base.values())
            for row in active:
                reference[row['node']] += row['activity']
            h = (b - a) / 1000
            e += (sum(reference.values()) + F(platform['external_common_power_W'])) * h
            segments.append(dict(start_ms=a, end_ms=b, opps=opps,
                                 reference_W=reference, lambda_W_per_K=slopes))
        scenes[scene['id']] = dict(rows=rows, segments=segments, reference_energy_J=e)
    return {'shared_deployment': shared, 'scenes': scenes,
            'weighted_reference_energy_J': sum(F(s['weight']) * scenes[s['id']]['reference_energy_J']
                                              for s in instance['scenarios']),
            'legality': 'COMPLETE_RESOURCE_DEADLINE_DOMAIN_VALID_THERMAL_UNCHECKED'}


def difference(instance, cpu, gpu):
    """D+J+R: no temperature path or numerical heat integral is evaluated."""
    sid = 'AC_offset_0ms'
    a, b = cpu['scenes'][sid], gpu['scenes'][sid]
    assert cpu['scenes']['AB_offset_0ms'] == gpu['scenes']['AB_offset_0ms']
    nodes = instance['platform']['node_order']
    temp_low, temp_high = map(F, instance['platform']['power_model_temperature_range_degC'])
    ref = F(instance['platform']['reference_temperature_degC'])
    low, high = temp_low - ref, temp_high - ref
    events = sorted({r[k] for plan in (a, b) for r in plan['segments'] for k in ('start_ms', 'end_ms')})
    d = v = jlo = jhi = jabs = F(0)
    for left, right in zip(events, events[1:]):
        pa = next(p for p in a['segments'] if p['start_ms'] <= left < p['end_ms'])
        pb = next(p for p in b['segments'] if p['start_ms'] <= left < p['end_ms'])
        h = (right - left) / 1000
        for node in nodes:
            dr = pa['reference_W'][node] - pb['reference_W'][node]
            dl = (pa['lambda_W_per_K'][node] - pb['lambda_W_per_K'][node]) * h
            d += dr * h
            v += abs(dr) * h
            jlo += min(dl * low, dl * high)
            jhi += max(dl * low, dl * high)
            jabs += abs(dl) * max(abs(low), abs(high))
    eps = F(1, 24)  # exp(.1*.4)-1 < .04/(1-.04); no exponential computed.
    residual = eps * (v + jabs)
    return {'scene': sid, 'D_reference_J': d, 'V_abs_reference_source_J': v,
            'J_signed_interval_J': [jlo, jhi], 'abs_J_force_integral_upper_J': jabs,
            'epsilon_strict_upper': eps, 'abs_R_upper_J': residual,
            'scene_full_energy_difference_interval_J': [d + jlo - residual, d + jhi + residual],
            'weighted_full_energy_difference_interval_J': [(d + jlo - residual) / 2,
                                                          (d + jhi + residual) / 2],
            'definition': 'CPU-plan minus GPU-plan; DeltaE=D+J+R; |R|<=epsilon*(V+integral|DeltaLambda*x_GPU|)',
            'continuous_80degC_safety_proven': False}


def main():
    declarations = load(PREP / 'declaration.json')['inputs']
    paths = [ROOT / n for n in ('config_v01.json', 'control_policy.py', 'schedules.py', 'thermal.py')]
    paths += [PREP / 'declaration.json', Path(__file__)]
    inputs = {}
    for rid in range(1, 6):
        pid = f'base__R{rid}'
        path = PREP / 'inputs' / pid / 'instance.json'
        paths.append(path)
        instance = load(path)
        assert canonical(instance) == declarations[pid]['input_sha256']
        assert instance['settings']['deadline_beta'] == '1.3'
        assert instance['response_variant'] == 'H'
        inputs[pid] = instance
    pilot = HERE / 'pilot_sources'
    paths += [pilot / n for n in ('C12.md', 'C18.md')]
    before = {str(p): sha(p) for p in paths}
    instance = inputs['base__R3']
    schedules, ledgers = {}, {}
    for context in ('uncovered', 'covered'):
        for device in ('CPU', 'GPU'):
            key = context + '_' + device
            schedules[key] = hand_schedule(instance, context == 'covered', device == 'CPU')
            ledgers[key] = check_and_ledger(instance, schedules[key])
    differences = {context: difference(instance, ledgers[context + '_CPU'], ledgers[context + '_GPU'])
                   for context in ('uncovered', 'covered')}
    assert differences['uncovered']['D_reference_J'] == F(63, 1000)
    assert differences['covered']['D_reference_J'] == 0
    assert differences['uncovered']['scene_full_energy_difference_interval_J'][0] == F('0.0246375')

    table = []
    first = inputs['base__R1']
    for stage in ('A.main', 'C.main'):
        for copp in ('L', 'M', 'H'):
            cm = mode(first, stage, 'CPU1', copp)
            for gopp in ('L', 'M', 'H'):
                gm = mode(first, stage, 'GPU0', gopp)
                dc, dg = F(cm['duration_ms']), F(gm['duration_ms'])
                qc, qg = F(cm['activity_power_W']), F(gm['activity_power_W'])
                domain = first['platform']['domains']
                d0 = qc * dc - qg * dg - (F(domain['GPU']['baseline_W'][gopp]) - F(domain['GPU']['baseline_W']['L'])) * dg
                slope = (F(domain['CPU']['baseline_W'][copp]) - F(domain['CPU']['baseline_W']['L'])) * dc
                table.append({'stage': stage, 'CPU_opp': copp, 'GPU_opp': gopp,
                    'D_u0_mJ': d0, 'D_u1_mJ': d0 + slope, 'coefficient_u_mJ': slope,
                    'strict_reference_crossing': d0 < 0 < d0 + slope,
                    'endpoint_tie': d0 == 0 or d0 + slope == 0,
                    'CPU_L_full_chain_deadline_impossible': copp == 'L'})
    assert len(table) == 18 and not any(v['strict_reference_crossing'] for v in table)
    assert [v for v in table if v['endpoint_tie']] == [v for v in table
            if v['stage'] == 'C.main' and v['CPU_opp'] == v['GPU_opp'] == 'H']
    cpu_low_exclusions = []
    for pid, inst in inputs.items():
        for scene in inst['scenarios']:
            for request in scene['requests']:
                stages = [s for s in scene['stage_instances'] if s['request_id'] == request['id']]
                app = next(s['shared_stage_id'].split('.')[0] for s in stages)
                lower = sum(min(F(m['duration_ms']) for m in inst['stage_modes'][s['shared_stage_id']])
                    if not s['shared_stage_id'].endswith('.main') else
                    F(mode(inst, s['shared_stage_id'], 'CPU1', 'L')['duration_ms']) for s in stages)
                assert lower > F(request['relative_deadline_ms'])
                cpu_low_exclusions.append({'problem': pid, 'scene': scene['id'], 'application': app,
                    'CPU_L_chain_lower_ms': lower, 'relative_deadline_ms': F(request['relative_deadline_ms'])})

    platform = first['platform']
    capacities = list(map(F, platform['heat_capacity_J_per_K']))
    g = [list(map(F, row)) for row in platform['conductance_W_per_K']]
    assert all(g[i][j] == g[j][i] for i in range(4) for j in range(4))
    assert all(g[i][j] <= 0 for i in range(4) for j in range(4) if i != j)
    assert all(sum(row) > 0 for row in g)
    source_max, alpha = {}, F(0)
    for index, node in enumerate(platform['node_order']):
        unit = next(u for u in platform['units'] if u['thermal_node_id'] == node)
        domain = platform['domains'][unit['domain_id']]
        bounds = []
        for opp in domain['opps']:
            active = max(F(m['activity_power_W']) for ms in first['stage_modes'].values()
                         for m in ms if m['unit_id'] == unit['id'] and m['opp_id'] == opp)
            share = F(domain['baseline_heat_distribution'][index])
            lam = F(domain['local_temperature_slope_W_per_K'][opp])
            bounds.append((active + share * F(domain['baseline_W'][opp]) + lam * 75) / capacities[index])
            alpha = max(alpha, lam / capacities[index])
        source_max[node] = max(bounds)
    assert alpha == F(1, 10)
    assert max(source_max.values()) == F('111.25')
    assert F(50) + max(source_max.values()) * F(2, 5) == F('94.5') < 100
    after = {str(p): sha(p) for p in paths}
    assert before == after
    report = {
        'protocol': 'K169-P0-C12-exact-ledger-and-paper-bound-v1', 'passed': True,
        'result': 'REFERENCE_COST_CONTEXT_DEPENDENT; STRICT_COMPLETE_ENERGY_REVERSAL_NOT_CERTIFIED',
        'pilot_subject_sha': PILOT_SHA, 'input_identities': {pid: canonical(v) for pid, v in inputs.items()},
        'source_and_artifact_sha256': before, 'read_files_unchanged': before == after,
        'hand_schedule_count': 4, 'hand_schedules': schedules, 'ledgers': ledgers,
        'differences': differences, 'mode_pair_table_R1': table,
        'all_R1_to_R5_endpoint_signs_same_by_positive_application_scale': True,
        'CPU_L_chain_exclusions': cpu_low_exclusions,
        'paper_range_bound': {'lower_degC': F(25), 'upper_degC': F('94.5'),
            'maximum_source_rate_K_per_s_by_node': source_max, 'alpha_per_s': alpha,
            'proof_scope': 'passive maximum/minimum comparison until first exit; no temperature trajectory evaluated',
            'is_80degC_safety_certificate': False},
        'operations': {'input_builds': 0, 'models_built': 0, 'solver_calls': 0,
            'heat_integrations': 0, 'formal_candidate_evaluations': 0,
            'candidate_search_or_optimization': False, 'new_parameters': False,
            'K168_started': False, 'remaining24_started': False},
        'limits': ['No full-energy reversal proved or refuted', 'No 80degC continuous safety or SAFE U',
                   'No ranking, optimum, pruning rule or algorithm benefit',
                   'Pilot five-node U model is not the mainline four-node model']}
    save_new(HERE / 'ledger_review.json', stringify(report))
    print(json.dumps({'passed': True, 'hand_schedules': 4, 'mode_pairs': 18,
                      'strict_reference_crossings': 0,
                      'uncovered_DeltaE_scene_lower_J': '0.0246375',
                      'covered_full_energy_order': 'UNRESOLVED'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
