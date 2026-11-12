"""Read-only structural audit of an archived MILP; never constructs or solves it.

Recounts individual input choices and event intervals with exact rationals,
checks the archived variable layout, and reads sparse coefficient statistics.
No production planner/evaluator imports, candidate schedules, or thermal runs.
"""
import argparse
from collections import Counter, defaultdict
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat


def digest(path):
    with path.open('rb') as stream:
        result = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def audit(source):
    instance_path = source / 'input_instance.json'
    matrix_path = source / 'matlab/request_000001.mat'
    inst = json.loads(instance_path.read_text(encoding='utf-8'))
    saved_hashes = json.loads((source / 'source_hashes.json').read_text(encoding='utf-8'))
    code = Path(__file__).resolve().parent
    source_paths = {name: code / name for name in saved_hashes}
    source_paths['interval.py'] = code.parent / 'v1_evaluator/interval.py'
    unchanged = {name: digest(source_paths[name]) == value for name, value in saved_hashes.items()}
    assert all(unchanged.values()), 'Audit layout requires the archived production source.'
    raw = loadmat(matrix_path, variable_names=['A', 'b', 'c', 'lb', 'ub', 'intcon', 'Aeq'])
    a = raw['A'].tocsc()
    lb, ub = (raw[name].ravel() for name in ['lb', 'ub'])
    integer = set(raw['intcon'].ravel().astype(int) - 1)
    p, grid, window = inst['platform'], F(inst['start_grid_ms']), F(inst['window_ms'])
    domain_opps = {key: tuple(value['opps']) for key, value in p['domains'].items()}
    groups, scene_info, stage_counts = defaultdict(list), [], []
    total_options = 0
    # Local option counts only: no Cartesian product of Stage assignments.
    for scene in inst['scenarios']:
        reqs = {r['id']: r for r in scene['requests']}
        choices, events, starts, ends = [], {F(0), window}, defaultdict(list), defaultdict(list)
        for stage in scene['stage_instances']:
            r = reqs[stage['request_id']]
            count = late = 0
            first = max(0, -(-F(r['release_ms']) // grid))
            for mode in inst['stage_modes'][stage['shared_stage_id']]:
                duration = F(mode['duration_ms'])
                assert duration > 0
                last = (window - duration) // grid
                for k in range(first, last + 1):
                    start, end = k * grid, k * grid + duration
                    key = (mode['unit_id'], mode['opp_id'])
                    choices.append((start, end, key))
                    starts[start].append(key)
                    ends[end].append(key)
                    events.update((start, end))
                    count += 1
                    late += end > F(r['deadline_ms'])
            stage_counts.append({'scenario': scene['id'], 'stage': stage['shared_stage_id'],
                                 'options': count, 'necessarily_zero_by_deadline': late})
            total_options += count
        events = sorted(events)
        active = Counter()
        lock_rows = aggregate_rows = 0
        for left in events[:-1]:
            active.subtract(ends[left])
            active.update(starts[left])
            assert all(value >= 0 for value in active.values())
            lock_rows += sum(active.values())
            aggregate_rows += sum(value > 0 for value in active.values())
        # Current base has all domain OPPs potentially starting at t=0.
        first_opps = defaultdict(set)
        unit_domain = {u['id']: u['domain_id'] for u in p['units']}
        for unit, opp in starts[F(0)]:
            first_opps[unit_domain[unit]].add(opp)
        assert all(first_opps[d] == set(opps) for d, opps in domain_opps.items())
        scene_info.append({'scenario': scene['id'], 'intervals': len(events) - 1,
                           'smallest_interval_ms': str(min(b - a for a, b in zip(events, events[1:]))),
                           'active_locks_current': lock_rows,
                           'active_locks_unit_opp_aggregate_nonempty': aggregate_rows})
    cursor = 0

    def allocate(kind, count):
        nonlocal cursor
        groups[kind].extend(range(cursor, cursor + count))
        cursor += count

    allocate('y_option', total_options)
    allocate('x_shared_unit', sum(len({m['unit_id'] for m in modes}) for modes in inst['stage_modes'].values()))
    joint_count = int(np.prod([len(opps) for opps in domain_opps.values()]))
    n = len(p['node_order'])
    for info in scene_info:
        k = info['intervals']
        for _ in range(k):
            for opps in domain_opps.values():
                allocate('rho_domain_opp', len(opps))
                allocate('J_start_trigger', 1)
            allocate('w_joint_state', joint_count)
        allocate('theta_temperature', n * (k + 1))
        for _ in range(k):
            allocate('q_activity_power', n)
            allocate('E_interval_energy', 1)
    assert cursor == len(lb) == a.shape[1]
    bins = {'y_option', 'x_shared_unit', 'rho_domain_opp', 'J_start_trigger', 'w_joint_state'}
    assert integer == {j for kind in bins for j in groups[kind]}
    assert all(lb[j] == 0 and ub[j] in (0, 1) for j in integer)
    c = raw['c'].ravel()
    assert set(np.flatnonzero(c)) == set(groups['E_interval_energy'])
    assert all(lb[j] == 0 for j in groups['E_interval_energy'])
    family = {key: {'variables': len(indices), 'fixed_by_bounds': int(np.sum(lb[indices] == ub[indices])),
                    'integer_declared': key in bins} for key, indices in groups.items()}
    row_tags = Counter()
    row_tags['shared_unique'] = 2 * len(inst['stage_modes'])
    for scene, info in zip(inst['scenarios'], scene_info):
        k, d = info['intervals'], len(domain_opps)
        num_opps = sum(map(len, domain_opps.values()))
        row_tags.update({'stage_unique': 2 * len(scene['stage_instances']),
                         'shared_link': 2 * sum(len({m['unit_id'] for m in inst['stage_modes'][s['shared_stage_id']]}) for s in scene['stage_instances']),
                         'request_deadline': len(scene['stage_instances']),
                         'dependency': len(scene['dependencies']), 'unit_mutex': k * len(p['units']),
                         'domain_unique': 2 * d * k, 'start_or_upper': d * k,
                         'idle_hold': 2 * num_opps * k, 'active_locks_opp': info['active_locks_current'],
                         'joint_unique': 2 * k, 'joint_marginal': 2 * num_opps * k,
                         'entry_temperature': 2 * n, 'activity_power': 2 * n * k,
                         'thermal_propagation': 2 * n * joint_count * k,
                         'complete_energy': 2 * joint_count * k})
    row_tags['start_or_lower'] = total_options
    assert sum(row_tags.values()) == a.shape[0]
    absolute = np.abs(a.data[a.data != 0])
    min_temp = F(p['power_model_temperature_range_degC'][0])
    reference = F(p['reference_temperature_degC'])
    floor_power = F(p['external_common_power_W'])
    for domain in p['domains'].values():
        assert all(F(v) >= 0 for v in domain['local_temperature_slope_W_per_K'].values())
        floor_power += min(F(domain['baseline_W'][opp]) + len(domain['unit_ids']) *
                           F(domain['local_temperature_slope_W_per_K'][opp]) * (min_temp - reference)
                           for opp in domain['opps'])
    activity_lb = sum(F(scene['weight']) * sum(min(F(m['activity_energy_J'])
                      for m in inst['stage_modes'][s['shared_stage_id']]) for s in scene['stage_instances'])
                      for scene in inst['scenarios'])
    assert sum(F(scene['weight']) for scene in inst['scenarios']) == 1
    physical_lb = floor_power * window / 1000 + activity_lb
    return {'audit_kind': 'static archived-input and matrix inspection; zero solver calls',
            'archive': source.as_posix(), 'matrix_sha256': digest(matrix_path),
            'input_sha256': digest(instance_path), 'audit_script_sha256': digest(Path(__file__)),
            'production_source_matches_archive': unchanged,
            'matrix': {'variables': a.shape[1], 'rows': a.shape[0], 'nonzeros': a.nnz,
                       'integer_variables': len(integer), 'Aeq_rows': raw['Aeq'].shape[0],
                       'min_nonzero_abs_coefficient': float(absolute.min()),
                       'max_abs_coefficient': float(absolute.max()),
                       'nonzeros_abs_below_1e_9': int(np.sum(absolute < 1e-9))},
            'variable_families': family, 'source_recounted_row_families': dict(row_tags),
            'scenarios': scene_info, 'deadline_counts': stage_counts,
            'necessarily_zero_options_by_deadline': sum(x['necessarily_zero_by_deadline'] for x in stage_counts),
            'physical_energy_lower_bound': {'minimum_baseline_power_W': str(floor_power),
                'baseline_energy_J': str(floor_power * window / 1000),
                'weighted_independent_activity_energy_J': str(activity_lb),
                'total_J_exact': str(physical_lb), 'total_J_display': float(physical_lb),
                'scope': 'algebraic bound for actual modeled energy within declared temperature range; '
                         'not installed as a bound on rounded MILP energy variables'}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Refusing to overwrite an existing audit receipt.')
    result = audit(args.archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
