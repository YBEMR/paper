"""Pure, exact, full-chain domain design. No solver or thermal evaluator import.

Reads one predeclared original input only. Counts legal timing/resource choices,
not thermal safety, energy, a best schedule, or an optimizer result.
"""
from collections import Counter
from copy import deepcopy
from fractions import Fraction as Q
from itertools import product
from pathlib import Path
import hashlib
import json
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SOURCE = REPO / 'research/chapter3_experiments/results/whole_long_budget01/method/input_instance.json'
SOURCE_SHA256 = '01eacb2a653d56419c32f38740021a787ea01ac9e7ade407bef2edd81ec6ef89'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def ceil_grid(value, grid):
    return -((-value) // grid) * grid


def overlap(a, b):
    return a['start'] < b['end'] and b['start'] < a['end']


def is_legal(rows, scene):
    """Exact release/deadline/dependency/unit/shared-domain checks; no heat."""
    by_id = {row['id']: row for row in rows}
    requests = {r['id']: r for r in scene['requests']}
    for row in rows:
        req = requests[row['request_id']]
        if row['start'] < Q(req['release_ms']) or row['end'] > Q(req['deadline_ms']):
            return False
    if any(by_id[left]['end'] > by_id[right]['start'] for left, right in scene['dependencies']):
        return False
    for n, left in enumerate(rows):
        for right in rows[n + 1:]:
            if overlap(left, right):
                if left['unit_id'] == right['unit_id']:
                    return False
                if left['domain_id'] == right['domain_id'] and left['opp_id'] != right['opp_id']:
                    return False
    return True


def row_options(instance, scene):
    groups = []
    for stage in scene['stage_instances']:
        options = []
        for mode in instance['stage_modes'][stage['shared_stage_id']]:
            for stamp in instance['start_domain']['by_scene_stage_ms'][scene['id']][stage['id']]:
                start = Q(stamp)
                options.append(dict(stage, **{key: mode[key] for key in (
                    'unit_id', 'domain_id', 'opp_id')}, start=start,
                    end=start + Q(mode['duration_ms'])))
        groups.append(options)
    return groups


def make_domain(original):
    assert original['id'] == 'base__R1' and original['response_variant'] == 'H'
    assert original['window_ms'] == '400' and original['start_grid_ms'] == '5'
    assert original['platform']['node_order'] == ['CPU1', 'CPU2', 'GPU0', 'NPU0']
    assert original['execution_rules']['idle_policy'] == 'auto_low_immediate_v1'
    assert len(original['scenarios']) == 2
    units = original['platform']['units']
    cpu = sorted(u['id'] for u in units if u['device_class'] == 'CPU')
    assert cpu == ['CPU1', 'CPU2']
    grid = Q(original['start_grid_ms'])
    instance = deepcopy(original)
    instance['id'] = 'quality_full_chain_design_v1__R1'
    instance['condition_id'] = 'quality_full_chain_design_v1'
    instance['experiment_group'] = 'quality_reference_full_chain'
    selected = {}
    limitations = {}
    for stage_id, modes in original['stage_modes'].items():
        if stage_id.endswith('.main'):
            acceleration = sorted({m['unit_id'] for m in modes if not m['unit_id'].startswith('CPU')})
            assert acceleration
            keep_units = {cpu[0], acceleration[0]}
            keep = [m for m in modes if m['unit_id'] in keep_units and m['opp_id'] in {'M', 'H'}]
            assert len(keep) == 4 and len({m['unit_id'] for m in keep}) == 2
            assert len({m['opp_id'] for m in keep}) == 2
        else:
            keep = [m for m in modes if m['unit_id'] == cpu[-1] and m['opp_id'] == 'H']
            assert len(keep) == 1
        selected[stage_id] = deepcopy(keep)
        limitations[stage_id] = {'original_modes': len(modes), 'retained_modes': [m['mode_id'] for m in keep]}
    instance['stage_modes'] = selected
    starts = {}
    for scene in original['scenarios']:
        assert len(scene['requests']) == 2 and len(scene['stage_instances']) == 6
        assert len(scene['dependencies']) == 4
        by_stage = {}
        pre_durations = [Q(selected[stage['shared_stage_id']][0]['duration_ms'])
                         for stage in scene['stage_instances'] if stage['chain_position'] == 0]
        pre_slot = ceil_grid(max(pre_durations), grid)
        # Lexical application order serializes the single reserved pre/post CPU.
        requests = sorted(scene['requests'], key=lambda r: (r['application'], r['id']))
        for ordinal, request in enumerate(requests):
            chain = sorted((s for s in scene['stage_instances'] if s['request_id'] == request['id']),
                           key=lambda s: s['chain_position'])
            assert [s['chain_position'] for s in chain] == [0, 1, 2]
            pre, main, post = chain
            pre_start = ceil_grid(Q(request['release_ms']), grid) + ordinal * pre_slot
            pre_end = pre_start + Q(selected[pre['shared_stage_id']][0]['duration_ms'])
            main_starts = [ceil_grid(pre_end, grid) + j * grid for j in (0, 1)]
            post_duration = Q(selected[post['shared_stage_id']][0]['duration_ms'])
            post_starts = sorted({ceil_grid(start + Q(m['duration_ms']), grid)
                                  for start in main_starts for m in selected[main['shared_stage_id']]
                                  if ceil_grid(start + Q(m['duration_ms']), grid) + post_duration <= Q(request['deadline_ms'])})
            assert post_starts, 'No post start under declared support/duration rule'
            by_stage[pre['id']] = [str(pre_start)]
            by_stage[main['id']] = [str(v) for v in main_starts]
            by_stage[post['id']] = [str(v) for v in post_starts]
        starts[scene['id']] = by_stage
    instance['start_domain'] = {'version': 1, 'kind': 'explicit_grid_subset', 'by_scene_stage_ms': starts}
    return instance, limitations


def main():
    begun = time.perf_counter()
    raw = SOURCE.read_bytes()
    assert sha(raw) == SOURCE_SHA256, 'K187 archived input bytes changed'
    original = json.loads(raw)
    instance, limitations = make_domain(original)
    # Every retained mode is copied verbatim from original support, no new mode.
    for key, modes in instance['stage_modes'].items():
        assert all(mode in original['stage_modes'][key] for mode in modes)
    # All physical fields, execution rules, weights, arrivals and deadlines stay.
    ignored = {'id', 'condition_id', 'experiment_group', 'stage_modes', 'start_domain'}
    for key in original:
        if key not in ignored:
            assert instance[key] == original[key], key
    scene_counts = {}
    total_cartesian = 0
    for scene in instance['scenarios']:
        groups = row_options(instance, scene)
        raw_count = 1
        for group in groups:
            raw_count *= len(group)
        total_cartesian += raw_count
        by_shared_A_unit = Counter()
        by_A_opp = Counter()
        stage_witness_modes = {s['shared_stage_id']: set() for s in scene['stage_instances']}
        stage_witness_starts = {s['shared_stage_id']: set() for s in scene['stage_instances']}
        for rows in product(*groups):
            if not is_legal(rows, scene):
                continue
            main_A = next(row for row in rows if row['shared_stage_id'] == 'A.main')
            by_shared_A_unit[main_A['unit_id']] += 1
            by_A_opp[main_A['opp_id']] += 1
            for row in rows:
                stage_witness_modes[row['shared_stage_id']].add(row['unit_id'] + ':' + row['opp_id'])
                stage_witness_starts[row['shared_stage_id']].add(str(row['start']))
        scene_counts[scene['id']] = {
            'stage_option_counts': {s['id']: len(options) for s, options in zip(scene['stage_instances'], groups)},
            'raw_cartesian_count': raw_count,
            'legal_timing_resource_count': sum(by_shared_A_unit.values()),
            'legal_count_by_shared_A_unit': dict(sorted(by_shared_A_unit.items())),
            'legal_count_by_A_opp': dict(sorted(by_A_opp.items())),
            'main_modes_present_in_static_legal_arrangements': {
                k: sorted(v) for k, v in stage_witness_modes.items() if k.endswith('.main')},
            'main_starts_present_in_static_legal_arrangements': {
                k: sorted(v, key=Q) for k, v in stage_witness_starts.items() if k.endswith('.main')},
        }
    assert all(v['legal_timing_resource_count'] > 0 for v in scene_counts.values())
    # Only A occurs in both scenes. Its pre/post use fixed CPU2; main device is
    # the only cross-scene mapping coupling. OPP/timing remain scene-specific.
    left, right = scene_counts.values()
    a_devices = sorted(set(left['legal_count_by_shared_A_unit']) & set(right['legal_count_by_shared_A_unit']))
    global_count_by_A = {unit: left['legal_count_by_shared_A_unit'][unit] *
                        right['legal_count_by_shared_A_unit'][unit] for unit in a_devices}
    assert len(a_devices) == 2
    total_global = sum(global_count_by_A.values())
    assert SOURCE.read_bytes() == raw
    prohibited = [name for name in sys.modules if name in {'thermal', 'milp', 'matlab_bridge', 'schedules', 'numpy', 'scipy'}]
    assert not prohibited
    result = {
        'schema': 'full-chain-small-domain-static-design-v1', 'status': 'DESIGN_ONLY_NO_THERMAL_OR_SOLVER',
        'source': {'path': str(SOURCE.relative_to(REPO)).replace('\\', '/'), 'sha256': sha(raw),
                   'canonical_instance_sha256': sha(canonical(original))},
        'output_instance_sha256': sha(canonical(instance)),
        'construction': {
            'main_modes': 'lexicographically first CPU plus first supported accelerator; M and H on both',
            'pre_post_modes': 'lexicographically last CPU, original H, retain all Stage instances',
            'pre_start': 'release rounded up plus application ordinal times grid-rounded maximum pre H duration',
            'main_starts': 'grid-rounded pre end, and exactly one original-grid tick later',
            'post_starts': 'union of grid-rounded ends of retained main choices, filtered only by original deadline',
            'historical_schedule_or_energy_or_heat_used': False,
            'restriction_is_research_design_not_hardware_support': True,
        },
        'retained_modes': limitations, 'scene_counts': scene_counts,
        'global_legal_complete_arrangements_by_shared_A_device': global_count_by_A,
        'global_legal_complete_arrangements': total_global,
        'stage_mode_start_options_before_joint_constraint_filtering': sum(
            sum(value['stage_option_counts'].values()) for value in scene_counts.values()),
        'raw_cartesian_arrangements_examined_for_static_count': total_cartesian,
        'scope': {'shared_stage_identities': len(instance['stage_modes']),
                  'stage_executions': sum(len(s['stage_instances']) for s in instance['scenarios']),
                  'window_ms': instance['window_ms'], 'grid_ms': instance['start_grid_ms'],
                  'shared_A_devices_with_static_legal_witnesses': a_devices,
                  'integer_optimization_calls': 0, 'LP_calls': 0, 'thermal_integrations': 0,
                  'candidate_energy_evaluations': 0, 'new_SAFE': 0},
        'enumerability': {
            'finite_exact_static_count_verified': True,
            'thermal_full_coverage_performed': False,
            'naive_full_candidate_evaluations_upper_bound': total_global,
            'separable_scene_evaluations_upper_bound': sum(v['legal_timing_resource_count'] for v in scene_counts.values()),
            'separability_reason': 'Independent scenario entries; normalized additive scenario objective; only shared A device couples scenes; pre/post fixed identically; each scene must be safe. Group by shared A device, exhaust both scene lists, then combine minima with interval bounds.',
            'all_scene_evaluations_must_be_charged': True,
            'unresolved_thermal_evaluations_cannot_be_discarded': True,
            'thermal_cost_estimated': False,
            'full_MILP_auxiliary_size_estimated': False,
            'future_budget': 'No numeric solving budget requested now. First implement a domain-contract adapter and charge a separately authorized deterministic cost pilot; freeze full coverage cap only after pilot.',
        },
        'static_count_wall_s': time.perf_counter() - begun,
        'limitations': [
            'No known thermal-safe arrangement, minimum energy, MILP size or native runtime is asserted.',
            'M CPU main options may become impossible due original deadline or shared OPP interactions; retained support is not a feasibility guarantee.',
            'Single-stage mappings and pre/post timing restrictions are deliberate domain reductions; conclusions apply only to this named subset.',
            'No production planner was modified or run; HEFT and local methods require explicit all-method domain validation before comparison.',
        ],
    }
    (HERE / 'restricted_input.json').write_text(json.dumps(instance, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (HERE / 'design.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'static_count_wall_s': result['static_count_wall_s'], 'scene_counts': scene_counts,
                      'global_count': total_global}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
