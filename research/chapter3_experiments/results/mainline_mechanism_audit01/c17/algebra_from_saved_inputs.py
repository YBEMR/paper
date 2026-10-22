"""K169 C17 audit: stored JSON + Fraction arithmetic only, no science import.

This computes proposed algebraic bounds for discussion. It never constructs
starts, a schedule, thermal states, model rows, a payload or a solver request.
Old L0/U receipts are read, never changed or promoted retroactively.
"""
from fractions import Fraction as F
import argparse
import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
RESULTS = REPO / 'research/chapter3_experiments/results'
SEEN = {}


def read(path):
    data = path.read_bytes()
    SEEN[str(path.relative_to(REPO)).replace('\\', '/')] = hashlib.sha256(data).hexdigest()
    return json.loads(data.decode('utf-8-sig'))


def locate(case, method, filename):
    paths = [RESULTS / group / 'calls' / case / method / filename
             for group in ('p0_execution01', 'p0_resume01')]
    existing = [p for p in paths if p.is_file()]
    if len(existing) != 1:
        raise ValueError(f'Expected exactly one original P0 file: {paths}')
    return existing[0]


def encode(value):
    return {'exact': str(value), 'decimal_display': float(value)}


def main(output=None):
    output = HERE / 'facts.json' if output is None else Path(output)
    if output.exists():
        raise FileExistsError('Do not overwrite an existing algebra audit')
    source_paths = [REPO / 'research/chapter3_experiments' / name for name in
                    ('partial_bounds.py', 'milp.py', 'milp_coefficients.py')]
    source_before = {str(p.relative_to(REPO)).replace('\\', '/'):
                     hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    cases = []
    for sample in range(1, 6):
        case = 'base__R' + str(sample)
        instance = read(locate(case, 'whole_milp', 'input_instance.json'))
        old = read(locate(case, 'whole_milp', 'independent_bounds.json'))['L0']
        p = instance['platform']; nodes = p['node_order']
        domains = p['domains']; units = {u['id']: u for u in p['units']}
        W = F(instance['window_ms']) / 1000
        ambient, reference = F(p['ambient_temperature_degC']), F(p['reference_temperature_degC'])
        valid_low = F(p['power_model_temperature_range_degC'][0])
        capacities = list(map(F, p['heat_capacity_J_per_K']))
        G = [list(map(F, row)) for row in p['conductance_W_per_K']]
        assert ambient == reference == 25
        assert all(c > 0 for c in capacities)
        assert all(G[i][j] == G[j][i] and (i == j or G[i][j] <= 0)
                   for i in range(len(nodes)) for j in range(len(nodes)))
        assert all(sum(row) > 0 for row in G)
        assert all(F(scene['weight']) >= 0 for scene in instance['scenarios'])
        assert sum(F(scene['weight']) for scene in instance['scenarios']) == 1
        assert all(F(t) == 50 for s in instance['scenarios'] for t in s['entry']['temperature_degC'])
        lam = [F(0)] * len(nodes)
        base_heat = [F(0)] * len(nodes)
        base_L = F(p['external_common_power_W'])
        floors = []
        for domain in domains.values():
            assert all(F(domain['baseline_W'][opp]) >= F(domain['baseline_W']['L']) >= 0
                       and F(domain['local_temperature_slope_W_per_K'][opp]) >=
                           F(domain['local_temperature_slope_W_per_K']['L']) >= 0
                       for opp in domain['opps'])
            assert all(F(v) >= 0 for v in domain['baseline_heat_distribution'])
            assert sum(map(F, domain['baseline_heat_distribution'])) == 1
            base_L += F(domain['baseline_W']['L'])
            for i, share in enumerate(domain['baseline_heat_distribution']):
                base_heat[i] += F(share) * F(domain['baseline_W']['L'])
            for uid in domain['unit_ids']:
                lam[nodes.index(units[uid]['thermal_node_id'])] += F(
                    domain['local_temperature_slope_W_per_K']['L'])
            floors.append(min(F(domain['baseline_W'][opp]) + len(domain['unit_ids']) *
                F(domain['local_temperature_slope_W_per_K'][opp]) * (valid_low-reference)
                for opp in domain['opps']))
        a = max(sum(row) / c for row, c in zip(G, capacities))
        rho = min(b / c for b, c in zip(base_heat, capacities))
        x_initial = F(50)-ambient
        # Exact integral of the degree-3 odd Taylor lower polynomial of exp(-a*t).
        poly_area = W - a*W**2/2 + a*a*W**3/6 - a**3*W**4/24
        assert poly_area > 0 and x_initial >= rho/a >= 0
        init_area = x_initial * poly_area
        base_area = (rho/a)*W + (x_initial-rho/a)*poly_area
        beta = max((sum(row)-slope)/c for row, slope, c in zip(G, lam, capacities))
        assert beta > 0 and x_initial >= rho/beta >= 0
        poly_leak_area = W-beta*W**2/2+beta**2*W**3/6-beta**3*W**4/24
        base_leak_area = (rho/beta)*W + (x_initial-rho/beta)*poly_leak_area
        old_activity = F(0)
        occurrences = []
        for scene in instance['scenarios']:
            weight = F(scene['weight'])
            requests = {r['id']: r for r in scene['requests']}
            for stage in scene['stage_instances']:
                modes = instance['stage_modes'][stage['shared_stage_id']]
                old_activity += weight * min(F(m['activity_power_W']) * F(m['duration_ms']) / 1000
                                              for m in modes)
                deadline = F(requests[stage['request_id']]['deadline_ms'])/1000
                assert 0 <= deadline <= W
                costs = []
                for mode in modes:
                    uid = mode['unit_id']; unit = units[uid]
                    k = nodes.index(unit['thermal_node_id'])
                    domain = domains[unit['domain_id']]
                    duration = F(mode['duration_ms'])/1000
                    q = F(mode['activity_power_W'])
                    assert duration > 0 and q >= 0
                    damping = (G[k][k]-lam[k])/capacities[k]
                    assert damping > 0
                    tail = W-deadline
                    # Closed polynomial lower bound on the own-node impulse
                    # leakage kernel at the absolute request deadline.
                    h = lam[k]/capacities[k] * (tail-damping*tail*tail/2)
                    h = max(F(0), h)
                    assert h >= 0
                    # At most N distinct units execute concurrently at an OPP.
                    # Sharing the baseline increment equally among N units is
                    # an additive workload relaxation of the residency union.
                    baseline_add = (F(domain['baseline_W'][mode['opp_id']]) -
                                    F(domain['baseline_W']['L'])) * duration / len(domain['unit_ids'])
                    costs.append({'unit': uid, 'opp': mode['opp_id'],
                                  'direct': q*duration,
                                  'direct_plus_source': q*duration*(1+h),
                                  'with_workload_increment': q*duration*(1+h)+baseline_add,
                                  'source_kernel_lower': h})
                occurrences.append(dict(scene=scene['id'], weight=weight,
                    shared=stage['shared_stage_id'], stage=stage['id'], costs=costs))
        old_baseline = (F(p['external_common_power_W']) + sum(floors))*W
        old_total = old_baseline + old_activity
        assert old_total == F(old['lower_bound_J'])
        init_bound = base_L*W + sum(lam)*init_area + old_activity
        background_bound = base_L*W + sum(lam)*base_area + old_activity
        background_leak_bound = base_L*W + sum(lam)*base_leak_area + old_activity
        source_activity = sum(o['weight']*min(m['direct_plus_source'] for m in o['costs'])
                              for o in occurrences)
        workload_activity = sum(o['weight']*min(m['with_workload_increment'] for m in o['costs'])
                                for o in occurrences)
        # Shared deployment consistency can be imposed in this algebraic
        # relaxation without constructing a schedule or choosing start times.
        shared_ids = set(old['shared_stage_ids'])
        shared_total = sum(o['weight']*min(m['with_workload_increment'] for m in o['costs'])
                           for o in occurrences if o['shared'] not in shared_ids)
        for shared in shared_ids:
            copies = [o for o in occurrences if o['shared'] == shared]
            available = set.intersection(*(set(m['unit'] for m in o['costs']) for o in copies))
            shared_total += min(sum(o['weight']*min(m['with_workload_increment'] for m in o['costs']
                                                 if m['unit'] == uid) for o in copies)
                                for uid in available)
        source_bound = base_L*W + sum(lam)*base_leak_area + source_activity
        workload_bound = base_L*W + sum(lam)*base_leak_area + workload_activity
        shared_bound = base_L*W + sum(lam)*base_leak_area + shared_total
        upper = []
        for method in ('whole_milp', 'anchor_linked4', 'heft', 'sa101', 'sa102', 'sa103', 'sa104', 'sa105'):
            result_path = locate(case, method, 'result.json')
            result = read(result_path)
            if result.get('safe_upper_bound_J') is not None:
                U = F(result['safe_upper_bound_J'])
                assert old_total <= init_bound <= background_bound <= background_leak_bound <= source_bound <= workload_bound <= shared_bound <= U
                upper.append({'method': method, 'stored_U_J': encode(U),
                              'gap_to_init_only_bound_J': encode(U-init_bound),
                              'gap_to_shared_algebra_bound_J': encode(U-shared_bound),
                              'source_path': str(result_path.relative_to(REPO)).replace('\\', '/'),
                              'old_receipt_not_re_evaluated': True})
        cases.append({'case': case, 'old_L0_reproduced_exactly': True,
            'old_L0_J': encode(old_total), 'reference_baseline_J': encode(base_L*W),
            'old_temperature_floor_component_J': encode(old_baseline-base_L*W),
            'sum_lambda_min_W_per_K': encode(sum(lam)), 'a_per_s': encode(a),
            'rho_K_per_s': encode(rho), 'initial_only_area_K_s': encode(init_area),
            'background_comparison_area_K_s': encode(base_area),
            'beta_with_minimum_leakage_per_s': encode(beta),
            'background_minimum_leakage_area_K_s': encode(base_leak_area),
            'init_only_proposed_LB_J': encode(init_bound),
            'guaranteed_init_only_increment_over_old_J': encode(init_bound-old_total),
            'background_proposed_LB_J': encode(background_bound),
            'background_minimum_leakage_proposed_LB_J': encode(background_leak_bound),
            'deadline_source_proposed_LB_J': encode(source_bound),
            'additive_OPP_workload_proposed_LB_J': encode(workload_bound),
            'shared_consistent_proposed_LB_J': encode(shared_bound),
            'shared_deployment_additional_gain_J': encode(shared_total-workload_activity),
            'OPP_workload_additional_gain_J': encode(workload_activity-source_activity),
            'all_minimal_stage_costs_allow_L': all(any(m['opp']=='L' and m['with_workload_increment']==
                min(n['with_workload_increment'] for n in o['costs']) for m in o['costs']) for o in occurrences),
            'stored_upper_bounds': upper})
    after = {name: hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in SEEN}
    source_after = {name: hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in source_before}
    report = {'protocol': 'K169-C17-mainline-Fraction-algebra-only-v1',
        'scope': 'Proposed bounds on all original safe schedules, calculated only from saved inputs; no production change, no retrospective change to original bounds',
        'cases': cases, 'inputs_before_sha256': SEEN, 'inputs_after_sha256': after,
        'inputs_unchanged': SEEN==after, 'source_before_sha256': source_before,
        'source_after_sha256': source_after, 'source_unchanged': source_before==source_after,
        'guard': {'scientific_modules_loaded': sorted(n for n in sys.modules if n.split('.')[0] in
            {'numpy','scipy','milp','thermal','partial_bounds','matlab_bridge','milp_coefficients'}),
            'model_builds': 0, 'solver_calls': 0, 'thermal_trajectory_or_candidate_evaluations': 0,
            'original_payload_transformations': 0, 'new_schedules': 0, 'research_calls': 0}}
    with output.open('x', encoding='utf8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'cases':len(cases),'inputs':len(SEEN),'unchanged':report['inputs_unchanged'],
                      'research_calls':0,'report':str(output)}))


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
                        help='New output path for reproducing the same algebra; never overwrite facts')
    main(parser.parse_args().output)
