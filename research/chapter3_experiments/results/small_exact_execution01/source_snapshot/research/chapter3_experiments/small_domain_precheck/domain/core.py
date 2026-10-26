"""K192 exact small-domain construction; no solver or thermal evaluation.

The original C method keeps its actual shared deployment and seed constructor.
The common problem retains both CPU1 and NPU0 for A.main.  A method's smaller
visited subset is not presented as the complete common decision domain.
"""
from collections import Counter
from copy import deepcopy
from fractions import Fraction as Q
from itertools import product
from math import prod
from pathlib import Path
import sys


C_SHARED = {'A.pre': 'CPU1', 'A.main': 'NPU0', 'A.post': 'CPU1'}
DOMAIN_ID = 'quality_full_chain_domain_v2__R1'
_IDENTITY_FIELDS = {'id', 'condition_id', 'experiment_group', 'stage_modes', 'start_domain'}


def ceil_grid(value, grid):
    return -((-Q(value)) // Q(grid)) * Q(grid)


def row_options(instance, scene):
    """All local options, independently formed with exact rational endpoints."""
    groups = []
    for stage in scene['stage_instances']:
        options = []
        for mode in instance['stage_modes'][stage['shared_stage_id']]:
            for stamp in instance['start_domain']['by_scene_stage_ms'][scene['id']][stage['id']]:
                start = Q(stamp)
                options.append(dict(stage, **{key: mode[key] for key in (
                    'unit_id', 'domain_id', 'opp_id')}, mode_id=mode['mode_id'],
                    start=start, end=start + Q(mode['duration_ms'])))
        groups.append(options)
    return groups


def is_legal(rows, scene):
    """Independent exact static check, without power, heat or objective."""
    if len(rows) != len(scene['stage_instances']):
        return False
    by_id = {row['id']: row for row in rows}
    if set(by_id) != {stage['id'] for stage in scene['stage_instances']}:
        return False
    requests = {request['id']: request for request in scene['requests']}
    for row in rows:
        request = requests[row['request_id']]
        if row['start'] < Q(request['release_ms']) or row['end'] > Q(request['deadline_ms']):
            return False
    if any(by_id[left]['end'] > by_id[right]['start'] for left, right in scene['dependencies']):
        return False
    for i, left in enumerate(rows):
        for right in rows[i + 1:]:
            overlap = max(left['start'], right['start']) < min(left['end'], right['end'])
            if overlap and (left['unit_id'] == right['unit_id'] or
                            left['domain_id'] == right['domain_id'] and left['opp_id'] != right['opp_id']):
                return False
    return True


def make_domain(original):
    """Deterministic declared subset derived only from the original input."""
    if not (original['id'] == 'base__R1' and original['response_variant'] == 'H'
            and original['window_ms'] == '400' and original['start_grid_ms'] == '5'
            and original['platform']['node_order'] == ['CPU1', 'CPU2', 'GPU0', 'NPU0']
            and original['execution_rules']['idle_policy'] == 'auto_low_immediate_v1'
            and len(original['scenarios']) == 2):
        raise ValueError('Only the original P0/R1 full-chain auto-L input is supported')
    instance = deepcopy(original)
    instance.update(id=DOMAIN_ID, condition_id='quality_full_chain_domain_v2',
                    experiment_group='quality_reference_full_chain')
    main_units = {'A.main': {'CPU1', 'NPU0'}, 'B.main': {'CPU1', 'NPU0'},
                  'C.main': {'CPU1', 'GPU0'}}
    retained = {}
    for shared, modes in original['stage_modes'].items():
        if shared.endswith('.main'):
            keep = [mode for mode in modes if mode['unit_id'] in main_units[shared]
                    and mode['opp_id'] in {'M', 'H'}]
            if len(keep) != 4:
                raise ValueError('Expected two original units and M/H for every main Stage')
        else:
            unit = 'CPU1' if shared.startswith('A.') else 'CPU2'
            keep = [mode for mode in modes if mode['unit_id'] == unit and mode['opp_id'] == 'H']
            if len(keep) != 1:
                raise ValueError('Expected one original pre/post H mode')
        retained[shared] = deepcopy(keep)
    instance['stage_modes'] = retained
    grid = Q(original['start_grid_ms'])
    starts = {}
    for scene in instance['scenarios']:
        if len(scene['requests']) != 2 or len(scene['stage_instances']) != 6 or len(scene['dependencies']) != 4:
            raise ValueError('Expected two complete three-Stage chains')
        by_stage, chains = {}, {}
        pre_slot = ceil_grid(max(Q(retained[s['shared_stage_id']][0]['duration_ms'])
                                 for s in scene['stage_instances'] if s['chain_position'] == 0), grid)
        for ordinal, request in enumerate(sorted(scene['requests'], key=lambda r: (r['application'], r['id']))):
            pre, main, post = chain = sorted((s for s in scene['stage_instances'] if s['request_id'] == request['id']),
                                             key=lambda s: s['chain_position'])
            chains[request['application']] = (request, chain)
            pre_start = ceil_grid(request['release_ms'], grid) + ordinal * pre_slot
            pre_end = pre_start + Q(retained[pre['shared_stage_id']][0]['duration_ms'])
            by_stage[pre['id']] = [pre_start]
            by_stage[main['id']] = [ceil_grid(pre_end, grid), ceil_grid(pre_end, grid) + grid]
        # Original C's H seed requires B to wait for A on the same NPU.
        # Add only the ends relevant to that shared resource, no CPU/GPU ends.
        if 'B' in chains:
            _, (_, a_main, _) = chains['A']
            b_request, (_, b_main, _) = chains['B']
            ends = {ceil_grid(start + Q(mode['duration_ms']), grid)
                    for start in by_stage[a_main['id']]
                    for mode in retained['A.main'] if mode['unit_id'] == 'NPU0'}
            by_stage[b_main['id']] = sorted(set(by_stage[b_main['id']]) | {
                stamp for stamp in ends if Q(b_request['release_ms']) <= stamp <= Q(b_request['deadline_ms'])})
        for request, (_, main, post) in chains.values():
            post_duration = Q(retained[post['shared_stage_id']][0]['duration_ms'])
            by_stage[post['id']] = sorted({ceil_grid(start + Q(mode['duration_ms']), grid)
                for start in by_stage[main['id']] for mode in retained[main['shared_stage_id']]
                if ceil_grid(start + Q(mode['duration_ms']), grid) + post_duration <= Q(request['deadline_ms'])})
            if not by_stage[post['id']]:
                raise ValueError('Empty declared post start domain')
        starts[scene['id']] = {key: [str(value) for value in values] for key, values in by_stage.items()}
    instance['start_domain'] = {'version': 1, 'kind': 'explicit_grid_subset', 'by_scene_stage_ms': starts}
    assert_preserved(original, instance)
    return instance


def assert_preserved(original, instance):
    """No physical field, retained mode coefficient, dependency or deadline drift."""
    if set(original) - {'start_domain'} != set(instance) - {'start_domain'}:
        raise ValueError('Unexpected input fields changed')
    for key, value in original.items():
        if key not in _IDENTITY_FIELDS and instance[key] != value:
            raise ValueError('Original physical/scenario field changed: ' + key)
    for shared, modes in instance['stage_modes'].items():
        if not modes or any(mode not in original['stage_modes'][shared] for mode in modes):
            raise ValueError('A retained mode is not an unmodified original record')
    grid = Q(original['start_grid_ms'])
    for scene in instance['scenarios']:
        for values in instance['start_domain']['by_scene_stage_ms'][scene['id']].values():
            if any(Q(stamp) < 0 or Q(stamp) > Q(original['window_ms']) or (Q(stamp) / grid).denominator != 1 for stamp in values):
                raise ValueError('Invalid explicit original-grid start')
    return True


def enumerate_legal(instance):
    legal_by_scene, scene_counts = {}, {}
    for scene in instance['scenarios']:
        groups = row_options(instance, scene)
        legal = [rows for rows in product(*groups) if is_legal(rows, scene)]
        by_a = Counter(next(row for row in rows if row['shared_stage_id'] == 'A.main')['unit_id'] for rows in legal)
        legal_by_scene[scene['id']] = legal
        scene_counts[scene['id']] = {'raw_cartesian_count': prod(map(len, groups)),
            'stage_option_count': sum(map(len, groups)), 'legal_timing_resource_count': len(legal),
            'legal_count_by_shared_A_unit': dict(sorted(by_a.items()))}
    left, right = scene_counts.values()
    devices = set(left['legal_count_by_shared_A_unit']) | set(right['legal_count_by_shared_A_unit'])
    joint = {unit: left['legal_count_by_shared_A_unit'].get(unit, 0) *
                   right['legal_count_by_shared_A_unit'].get(unit, 0) for unit in sorted(devices)}
    counts = {'by_scene': scene_counts,
        'stage_mode_start_options': sum(row['stage_option_count'] for row in scene_counts.values()),
        'global_legal_complete_arrangements_by_shared_A_device': joint,
        'global_legal_complete_arrangements': sum(joint.values()),
        'scene_evaluations_for_full_coverage': sum(len(rows) for rows in legal_by_scene.values())}
    return legal_by_scene, counts


def constructor_prechecks(instance):
    """Run only existing deterministic structural constructors, no search/eval."""
    production = Path(__file__).resolve().parents[2]
    if str(production) not in sys.path:
        sys.path.insert(0, str(production))
    from initial_schedule import construct_initial_candidates
    from heft_method import build_heft_candidate
    from schedules import validate_schedule
    view = deepcopy(instance)
    for shared, unit in C_SHARED.items():
        view['stage_modes'][shared] = [mode for mode in view['stage_modes'][shared] if mode['unit_id'] == unit]
    attempts = construct_initial_candidates(view)['attempts']
    complete = [attempt for attempt in attempts if attempt['status'] == 'COMPLETE_LEGAL_CANDIDATE']
    seed = None if not complete else complete[0]['candidate']
    if seed is not None and validate_schedule(instance, seed)['state'] != 'SCHEDULE_VALID_THERMAL_UNCHECKED':
        raise ValueError('C seed is outside the common original input domain')
    heft = build_heft_candidate(instance)
    return seed, {'C_shared_deployment': deepcopy(C_SHARED), 'C_templates': attempts,
                  'HEFT_constructor': heft, 'thermal_status': 'NOT_EVALUATED',
                  'new_SAFE': 0, 'solver_calls': 0, 'thermal_integrations': 0}


def produce(original):
    instance = make_domain(original)
    legal, counts = enumerate_legal(instance)
    seed, checks = constructor_prechecks(instance)
    return {'instance': instance, 'counts': counts, 'legal_by_scene': legal,
            'C_seed': seed, 'constructor_prechecks': checks,
            'construction': {'source': 'original P0/R1 input only, no historical candidate/energy/heat',
                'main_modes': 'A/B CPU1,NPU0; C CPU1,GPU0; original M/H',
                'pre_post_modes': 'A CPU1/H; B/C CPU2/H',
                'extra_wait_starts': 'B.main additionally admits all retained A.NPU0 end times rounded upward to original grid',
                'post_starts': 'union of grid-rounded retained main ends, filtered by original deadline',
                'common_A_main_deployment_open': ['CPU1', 'NPU0'],
                'C_actual_shared_deployment': deepcopy(C_SHARED),
                'C_scope': 'original method-specific subset of this common problem, not full-domain coverage'}}
