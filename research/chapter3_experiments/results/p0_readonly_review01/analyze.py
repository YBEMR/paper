"""K157: stored-evidence P0/R3 analysis. Standard library only; no solver/heat calls."""
from collections import Counter
import csv
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
REPO = next(p for p in OUT.parents if (p / 'AGENTS.md').is_file())
EXP = REPO / 'research/chapter3_experiments'
EVIDENCE = EXP / 'results/p0_resume01'
SOURCES = {}


def read(path):
    data = path.read_bytes()
    SOURCES[path.relative_to(REPO).as_posix()] = hashlib.sha256(data).hexdigest()
    return json.loads(data.decode('utf-8'))


def write(name, value):
    with (OUT / name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def interval(value):
    return tuple(map(F, value))


def encoded(value):
    return [str(v) for v in value]


def difference(left, right):
    return left[0] - right[1], left[1] - right[0]


def overlap(left, right):
    return max(left[0], right[0]) <= min(left[1], right[1])


def rows_by_stage(candidate, sid):
    return {r['stage_id']: r for r in candidate['scenes'][sid]}


def membership(condition, candidate, *, phase, swap_cpu=False):
    """Exact option membership only. A label swap is NOT a new SAFE witness."""
    violations = []
    for sid in condition['seed_options_by_scene']:
        for stage_id, row in rows_by_stage(candidate, sid).items():
            seed = condition['seed_options_by_scene'][sid][stage_id]
            fixed = seed if phase == 1 else condition['warm_options_by_scene'][sid][stage_id]
            unit = {'CPU1': 'CPU2', 'CPU2': 'CPU1'}.get(row['unit'], row['unit']) if swap_cpu else row['unit']
            causes = []
            if unit != seed['unit']:
                causes.append('fixed_unit')
            if stage_id not in condition['opened_by_scene'][sid]:
                if row['opp'] != fixed['opp']:
                    causes.append('closed_opp')
                if F(row['start_ms']) != F(fixed['start_ms']):
                    causes.append('closed_start')
            if causes:
                violations.append({'scene': sid, 'stage': stage_id, 'causes': causes,
                    'tested': {'unit': unit, 'opp': row['opp'], 'start_ms': row['start_ms']},
                    'unit_anchor': seed['unit'], 'closed_anchor': fixed})
    return {'member': not violations, 'violations': violations,
            'CPU_label_swap_only': swap_cpu, 'thermal_safety_of_transformation_claimed': False}


def main():
    facts = read(EVIDENCE / 'analysis01/facts.json')
    input_ = read(EVIDENCE / 'calls/base__R3/anchor_linked4/input_instance.json')
    raw = {m: read(EVIDENCE / 'calls/base__R3' / m / 'wrapper_raw_result.json')
           for m in ('anchor_linked4', 'heft')}
    posts = {m: read(EVIDENCE / 'calls/base__R3' / m / 'postcheck.json') for m in raw}
    conditions = [p['condition'] for p in raw['anchor_linked4']['phases']]
    checks = {'P0_40_distinct': len(facts['rows']) == len({(r['problem_id'], r['method']) for r in facts['rows']}) == 40,
              'P0_all_SAFE_post': all(r['comparison_usable'] and r['post_SAFE'] for r in facts['rows']),
              'P0_no_L0_anomaly': facts['independent_bound_anomalies'] == 0,
              'R3_two_stored_SAFE_posts': all(p['state'] == 'SAFE' and p['rankable_energy'] for p in posts.values()),
              'R3_weights_sum_one': sum(F(s['weight']) for s in input_['scenarios']) == 1}
    schedule = []
    for m, result in raw.items():
        for scene in input_['scenarios']:
            sid = scene['id']
            stages = {s['id']: s for s in scene['stage_instances']}
            deadlines = {r['id']: F(r['deadline_ms']) for r in scene['requests']}
            for row in result['safe_candidate']['scenes'][sid]:
                stage = stages[row['stage_id']]
                mode = next(v for v in input_['stage_modes'][stage['shared_stage_id']]
                            if v['unit_id'] == row['unit'] and v['opp_id'] == row['opp'])
                end = F(row['start_ms']) + F(mode['duration_ms'])
                schedule.append({'method': m, 'scene': sid, 'stage': stage['shared_stage_id'],
                    'stage_instance': row['stage_id'], 'unit': row['unit'], 'opp': row['opp'],
                    'start_ms': row['start_ms'], 'duration_ms_exact': mode['duration_ms'],
                    'end_ms_exact': str(end), 'end_ms': float(end),
                    'request_deadline_ms': float(deadlines[stage['request_id']]),
                    'activity_energy_J_exact': mode['activity_energy_J']})
    with (OUT / 'r3_schedules.csv').open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, list(schedule[0])); writer.writeheader(); writer.writerows(schedule)

    energies, deltas = {}, []
    weighted_delta = (F(0), F(0))
    weighted_components = {key: [F(0), F(0)] for key in ('baseline', 'activity', 'external_common', 'temperature_correction')}
    for scene in input_['scenarios']:
        sid, weight = scene['id'], F(scene['weight'])
        l, h = posts['anchor_linked4']['scenes'][sid], posts['heft']['scenes'][sid]
        delta = difference(interval(l['energy_J']), interval(h['energy_J']))
        weighted_delta = tuple(a + weight*b for a, b in zip(weighted_delta, delta))
        energies[sid] = {m: {'energy_J': p['scenes'][sid]['energy_J'],
            'components_J': p['scenes'][sid]['energy_components_J'],
            'max_peak_upper_degC': max(float(F(v[1])) for v in p['scenes'][sid]['peaks_degC'].values())}
            for m, p in posts.items()}
        component_sum = [F(0), F(0)]
        for key in weighted_components:
            d = difference(interval(l['energy_components_J'][key]), interval(h['energy_components_J'][key]))
            for k in (0, 1):
                component_sum[k] += d[k]
                weighted_components[key][k] += weight*d[k]
            deltas.append({'scene': sid, 'component': key, 'delta_J_lo': str(d[0]),
                           'delta_J_hi': str(d[1]), 'weighted_delta_J': float(weight*(d[0]+d[1])/2)})
        checks[sid+'/component_delta_matches_total'] = overlap(tuple(component_sum), delta)
        checks[sid+'/stored_original_and_post_energy_overlap'] = all(overlap(
            interval((raw[m]['aggregation'] if m == 'anchor_linked4' else raw[m]['evaluation'])['scenes'][sid]['energy_J']),
            interval(posts[m]['scenes'][sid]['energy_J'])) for m in raw)
    original_delta = difference(interval(raw['anchor_linked4']['aggregation']['weighted_energy_J']),
                                interval(raw['heft']['evaluation']['weighted_energy_J']))
    checks['R3_weighted_delta_matches_original'] = overlap(weighted_delta, original_delta)
    checks['R3_linked_strictly_worse'] = original_delta[0] > 0
    with (OUT / 'r3_component_deltas.csv').open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, list(deltas[0])); writer.writeheader(); writer.writerows(deltas)

    membership_results = {}
    for i, c in enumerate(conditions, 1):
        check_candidate = c['seed_candidate'] if i == 1 else c['warm_candidate']
        checks[f'phase{i}_positive_anchor_is_member'] = membership(c, check_candidate, phase=i)['member']
        for swap in (False, True):
            key = f'phase{i}_HEFT_' + ('CPU_swap' if swap else 'original')
            membership_results[key] = membership(c, raw['heft']['safe_candidate'], phase=i, swap_cpu=swap)
            checks[key+'/outside_condition'] = not membership_results[key]['member']
    checks['final_linked_is_phase2_member'] = membership(conditions[1], raw['anchor_linked4']['safe_candidate'], phase=2)['member']
    ab = input_['scenarios'][0]['id']
    ab_swapped = [v for v in membership_results['phase2_HEFT_CPU_swap']['violations'] if v['scene'] == ab]
    checks['AB_after_CPU_swap_phase2_only_B_main_closed'] = (
        len(ab_swapped) == 1 and ab_swapped[0]['stage'].endswith('::B.main')
        and set(ab_swapped[0]['causes']) == {'closed_opp', 'closed_start'})
    warm_ab = conditions[1]['warm_candidate']['scenes'][ab]
    checks['AB_phase2_kept_phase1_complete_anchor'] = (
        rows_by_stage({'scenes': {ab: warm_ab}}, ab) == rows_by_stage(raw['anchor_linked4']['safe_candidate'], ab))

    phases = []
    for ph in raw['anchor_linked4']['phases']:
        for sid, s in ph['scenes'].items():
            rounds = s['solver_result']['rounds']
            phases.append({'phase': ph['phase_index'], 'scene': sid,
                'model_complete_at_s': s['model_completed_at_s'],
                'search_started_at_s': s['search_started_at_s'], 'search_returned_at_s': s['search_returned_at_s'],
                'reason': s['reason'], 'scene_cap_s': s['scene_slice_s'],
                'rounds': [{'native_exitflag': r.get('exitflag'), 'objective_J': r.get('fval'),
                    'native_options_MaxTime_s': r.get('solver_max_time_s_used'),
                    'native_call_s': (r.get('phase_seconds') or {}).get('intlinprog_call'),
                    'native_output': r.get('output'), 'solver_reported_only': True} for r in rounds]})
    timing = raw['anchor_linked4']['timing']
    sa = []
    for row in facts['rows']:
        if row['problem_id'] == 'base__R3' and row['seed'] is not None:
            saved = read(EVIDENCE / 'calls/base__R3' / row['method'] / 'wrapper_raw_result.json')
            sa.append({'method': row['method'], 'U_J': row['safe_U_exact'],
                       'opp_counts': dict(Counter(r['opp'] for group in saved['safe_candidate']['scenes'].values() for r in group))})
    cfg = read(EXP / 'config_v01.json')
    plan = read(EXP / 'plans/k153_execution_plan_v1.json')
    picks = [('A', 'P1', 'response_R', '仅频率响应H→R；R为α=1，期限参考不改。'),
             ('B', 'P5', 'beta_1.0', '已有CPU-H链参考的单位期限；较基准1.3收紧23.08%，先查压力，不据单档写趋势。'),
             ('C', 'P8', 'requests_2', '保留三Stage链，每应用1→2个同时释放副本，隔离请求规模；须先适配目录。'),
             ('D', 'P2', 'initial_78', '原78°C入口、80°C上限，保持响应和物理参数，不新增扫描。')]
    next_batches = []
    for category, batch_id, cid, reason in picks:
        condition = next(c for c in cfg['conditions'] if c['id'] == cid)
        batch = next(b for b in plan['batches'] if b['id'] == batch_id)
        checks[cid+'/preexisting_condition'] = cid in batch['condition_ids']
        next_batches.append({'category': category, 'batch_id': batch_id, 'condition_id': cid,
            'overrides': condition['overrides'], 'selection_status': 'ASSISTANT_RECOMMENDATION_NOT_USER_CONFIRMED',
            'reason': reason, 'problems': [cid+'__R'+str(i) for i in range(1, 6)],
            'methods_per_problem': ['whole_milp', 'anchor_linked4', 'heft'] + ['sa'+str(i) for i in range(101, 106)],
            'calls': 40, 'method_limit_s': 300, 'method_seconds_max': 12000,
            'calendar_seconds_proposed': 19200, 'post_seconds_per_admitted_final_SAFE': 60,
            'authorised_to_execute': False, 'interface_prechecked': False,
            'domain_adaptation_pending': cid == 'requests_2'})
    checks['sources_unchanged_during_analysis'] = all(hashlib.sha256((REPO/name).read_bytes()).hexdigest() == h for name, h in SOURCES.items())
    output = {'material_passport': {'stage': 'K157', 'mode': 'stored-evidence analysis and next-batch proposal',
                'review_commit': '0e8a69c26d1946b1d103e5d394a62b60b83ccba6', 'date': '2026-10-21',
                'verification': 'ANALYZED_STORED_RECORDS_NO_REPRODUCTION_RUN'},
        'research_calls': 0, 'solver_calls': 0, 'new_thermal_evaluations': 0,
        'scientific_input_or_method_changed': False, 'source_sha256': SOURCES,
        'P0_cohorts': facts['cohorts'], 'R3_scene_energy': energies,
        'R3_weighted_energy_difference_J': encoded(original_delta),
        'R3_weighted_component_differences_J': {k: encoded(v) for k, v in weighted_components.items()},
        'R3_phases': phases, 'R3_method_elapsed_s': timing['method_elapsed_s'],
        'R3_unused_root_time_s': timing['limit_s']-timing['method_elapsed_s'],
        'R3_SA_observed': sa,
        'conclusion': 'AB dominates the gap. Exact HEFT schedule is outside both saved local domains; after a global CPU-label swap AB still violates phase2 B.main closed OPP/start. This does not prove all comparably good schedules absent or isolate a causal gain from untested modifications.'}
    write('diagnosis.json', output)
    write('r3_membership.json', membership_results)
    write('next_conditions_draft.json', {'status': 'DRAFT_NOT_EXECUTABLE', 'new_call_authorisation': False,
        'recommended_order': ['response_R', 'initial_78', 'beta_1.0', 'requests_2'], 'batches': next_batches,
        'all_four_if_later_approved': {'calls': 160, 'method_seconds_max': 48000, 'calendar_seconds_proposed': 76800},
        'deferred_unchanged': ['resources_CPU/anchor_linked4', 'resources_CPU_GPU/anchor_linked4']})
    write('checks.json', {'passed': all(checks.values()), 'count': len(checks), 'checks': checks,
        'scope': 'Stored arithmetic, identities and domain membership; no solver/heat rerun or independent MILP certificate',
        'research_calls': 0, 'new_thermal_evaluations': 0})
    assert all(checks.values()), [k for k, v in checks.items() if not v]
    print({'passed': True, 'checks': len(checks), 'weighted_R3_extra_J': float(original_delta[1]),
           'component_extra_J': {k: float(v[1]) for k,v in weighted_components.items()},
           'unused_root_s': output['R3_unused_root_time_s'], 'new_research_calls': 0})


if __name__ == '__main__':
    main()
