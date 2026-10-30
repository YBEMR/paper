"""Independent G0 fixed-device/open-OPP-start domain and exact implications.

This code does not reuse the AB/AC validators.  A condition establishes
membership and exact timing only; its caller must separately certify the
complete SAFE anchor through the real receipt chain (or label a manual fake).
"""
from copy import deepcopy
import hashlib
from pathlib import Path

from .contract import (canonical_hash, require, q, scenes, check_budget,
                       candidate_rows, validate_deployment, cross_projection,
                       mode_for, validate_inputs, explicit_starts)


PROTOCOL = 'g0-fixed-device-opp-start-v1'


def _source_hashes():
    root = Path(__file__).parent
    return {f'research/chapter3_g0/{name}': hashlib.sha256((root/name).read_bytes()).hexdigest()
            for name in ('contract.py', 'local_domain.py')}


def _validate_hashes(hashes):
    require(isinstance(hashes, dict) and hashes, 'CONDITION_SOURCE_HASHES_REQUIRED')
    for name, value in hashes.items():
        path = Path(name)
        require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == value,
                'CONDITION_SOURCE_CHANGED:' + str(name))
    local = _source_hashes()
    require(all(hashes.get(path) == value for path, value in local.items()), 'MISSING_CONDITION_DEPENDENCY_HASH')


def make_condition(config, instance, anchor, d0, scene_id, open_ids, *, phase,
                   source_hashes=None, budget=None):
    """Bind one scene's complete copy groups to an immutable full-input anchor."""
    check_budget(budget)
    validate_inputs(config, instance)
    deployment = validate_deployment(config, instance, d0)
    normalized = candidate_rows(config, instance, anchor)
    require(scene_id in normalized and phase in (1, 2), 'INVALID_CONDITION_SCENE_PHASE')
    for by_stage in normalized.values():
        for row in by_stage.values():
            require(row['unit'] == deployment[row['shared_stage_id']], 'ANCHOR_D0_MISMATCH')
    require(isinstance(open_ids, (list, tuple)) and len(open_ids) == len(set(open_ids))
            and set(open_ids) <= set(normalized[scene_id]), 'INVALID_OPEN_IDS')
    require(len(open_ids) <= (2 if phase == 1 else 4), 'OPEN_CAPACITY_EXCEEDED')
    opened = set(open_ids)
    groups = {}
    for identity, row in normalized[scene_id].items():
        groups.setdefault(row['shared_stage_id'], set()).add(identity)
    for values in groups.values():
        require(not (values & opened) or values <= opened, 'SPLIT_COPY_GROUP')
    actual_hashes = _source_hashes()
    if source_hashes is not None:
        actual_hashes.update(deepcopy(source_hashes))
    _validate_hashes(actual_hashes)
    warm = {sid: {r['stage_id']: deepcopy(r) for r in rows}
            for sid, rows in anchor['scenes'].items()}
    out = {'protocol': PROTOCOL, 'source_input_sha256': canonical_hash(instance),
           'config_sha256': canonical_hash(config), 'scene_id': scene_id, 'phase': phase,
           'd0_all': deployment, 'd0_cross': cross_projection(instance, deployment),
           'open_ids': sorted(opened),
           'opened_by_scene': {sid: (sorted(opened) if sid == scene_id else []) for sid in sorted(normalized)},
           'anchor': deepcopy(anchor), 'anchor_sha256': canonical_hash(anchor),
           'warm_options_by_scene': warm, 'source_hashes': actual_hashes}
    out['condition_sha256'] = canonical_hash(out)
    check_budget(budget)
    return out


def validate_condition(config, instance, condition, *, budget=None):
    check_budget(budget)
    require(isinstance(condition, dict), 'INVALID_G0_CONDITION')
    values = deepcopy(condition)
    supplied = values.pop('condition_sha256', None)
    require(supplied == canonical_hash(values), 'MODIFIED_CONDITION')
    require(values.get('protocol') == PROTOCOL, 'G0_PROTOCOL_REQUIRED')
    expected = make_condition(config, instance, values['anchor'], values['d0_all'],
        values['scene_id'], values['open_ids'], phase=values['phase'],
        source_hashes=values['source_hashes'], budget=budget)
    require(expected == condition, 'CONDITION_INPUT_OR_ANCHOR_MISMATCH')
    return deepcopy(expected)


def member(condition, scene_id, stage_id, unit, opp, start):
    """Pure predicate after validate_condition; closed choices remain exact."""
    require(scene_id in condition['warm_options_by_scene'] and
            stage_id in condition['warm_options_by_scene'][scene_id], 'UNKNOWN_G0_STAGE')
    row = condition['warm_options_by_scene'][scene_id][stage_id]
    if unit != row['unit']:
        return False
    return (stage_id in condition['opened_by_scene'][scene_id] or
            (opp == row['opp'] and q(start) == q(row['start_ms'])))


def assert_member(config, instance, candidate, condition, *, budget=None):
    """Check full candidate or the explicitly bound single-scene projection."""
    condition = validate_condition(config, instance, condition, budget=budget)
    require(isinstance(candidate, dict) and isinstance(candidate.get('scenes'), dict),
            'CANDIDATE_FIELDS')
    supplied = set(candidate['scenes'])
    scene_id = condition['scene_id']
    view = None if supplied == set(scenes(instance)) else scene_id
    checked = candidate_rows(config, instance, candidate, scene_id=view)
    for sid, by_stage in checked.items():
        for identity, row in by_stage.items():
            check_budget(budget)
            require(row['unit'] == condition['d0_all'][row['shared_stage_id']], 'D0_CHANGED')
            require(member(condition, sid, identity, row['unit'], row['opp'], row['start_ms']),
                    'OUTSIDE_G0_LOCAL_DOMAIN:' + sid + '/' + identity)
    check_budget(budget)
    return {'state': 'G0_MEMBER_SCHEDULE_VALID_THERMAL_UNCHECKED',
            'condition_sha256': condition['condition_sha256'], 'scene_ids': sorted(checked)}


def filter_options(config, instance, options, condition, *, budget=None,
                   preeliminate=True, scene_ids=None):
    """Order-preserving domain intersection and optional four exact implications.

    All supplied options are checked against original modes. The whitelist
    removes no option for estimated heat, activity proxy H or lower bound.
    No partial result is returned on interruption. The current anchor's own
    option must survive for every scene Stage, even when it is open.
    """
    condition = validate_condition(config, instance, condition, budget=budget)
    require(type(preeliminate) is bool, 'PREELIMINATE_BOOL_REQUIRED')
    require(isinstance(options, list), 'COMPLETE_OPTION_LIST_REQUIRED')
    sid = condition['scene_id']
    require(scene_ids is None or list(scene_ids) == [sid], 'G0_FILTER_SCENE_MISMATCH')
    scene = scenes(instance)[sid]
    stages = {s['id']: s for s in scene['stage_instances']}
    requests = {r['id']: r for r in scene['requests']}
    grid, window = q(instance['start_grid_ms']), q(instance['window_ms'])
    declared_starts = explicit_starts(instance)
    edges = {tuple(e) for e in scene['dependencies']}
    opened = set(condition['open_ids'])
    warm = candidate_rows(config, instance, condition['anchor'])[sid]
    anchors = [r for identity, r in warm.items() if identity not in opened]
    counts = {identity: {'before': 0, 'after': 0} for identity in stages}
    seen, kept, removals, domain_removed, anchor_seen = set(), [], [], 0, set()
    for option in options:
        check_budget(budget)
        require(isinstance(option, dict) and option.get('scenario_id') == sid, 'OPTION_SCENE_MISMATCH')
        identity = option['stage_instance_id']
        require(identity in stages, 'UNKNOWN_OPTION_STAGE')
        stage = stages[identity]
        mode = mode_for(instance, stage['shared_stage_id'], option['unit_id'], option['opp_id'])
        require(all(option.get(key) == value for key, value in mode.items()), 'NONORIGINAL_MODE_OPTION')
        require(option.get('request_id') == stage['request_id'], 'OPTION_REQUEST_MISMATCH')
        request = requests[stage['request_id']]
        require(q(option['request_deadline_ms']) == q(request['deadline_ms']),
                'OPTION_REQUEST_DEADLINE_MISMATCH')
        if 'request_release_ms' in option:
            require(q(option['request_release_ms']) == q(request['release_ms']),
                    'OPTION_REQUEST_RELEASE_MISMATCH')
        start, end = q(option['start_ms']), q(option['end_ms'])
        require(end == start + q(mode['duration_ms']), 'NONORIGINAL_END_TIME')
        require(start >= 0 and (start / grid).denominator == 1, 'OPTION_START_OUTSIDE_GRID')
        require(start >= q(request['release_ms']), 'OPTION_BEFORE_RELEASE')
        require(end <= window, 'OPTION_WINDOW_EXCEEDED')
        require(declared_starts is None or start in declared_starts[sid][identity],
                'OPTION_START_OUTSIDE_DECLARED_DOMAIN')
        # End > request deadline is deliberately NOT rejected here. The
        # inherited deadline prefilter/fix-zero stage retains that responsibility.
        unique = identity, option['unit_id'], option['opp_id'], start
        require(unique not in seen, 'DUPLICATE_OPTION')
        seen.add(unique)
        counts[identity]['before'] += 1
        if not member(condition, sid, identity, option['unit_id'], option['opp_id'], start):
            domain_removed += 1
            continue
        reasons = []
        if preeliminate and identity in opened:
            for anchor in anchors:
                check_budget(budget)
                astart, aend = q(anchor['start_ms']), q(anchor['end_ms'])
                overlap = max(start, astart) < min(end, aend)
                rules = []
                if overlap and option['unit_id'] == anchor['unit']:
                    rules.append('same_unit_overlap')
                if (overlap and option['domain_id'] == anchor['domain_id']
                        and option['opp_id'] != anchor['opp']):
                    rules.append('same_domain_different_opp_overlap')
                if (identity, anchor['stage_id']) in edges and end > astart:
                    rules.append('open_predecessor_finishes_after_closed_start')
                if (anchor['stage_id'], identity) in edges and start < aend:
                    rules.append('open_successor_starts_before_closed_end')
                if rules:
                    reasons.append({'rules': rules, 'anchor_stage_id': anchor['stage_id']})
        if reasons:
            removals.append({'scenario_id': sid, 'stage_instance_id': identity,
                'option_id': option.get('option_id'), 'start_ms': str(start), 'end_ms': str(end),
                'reasons': reasons})
            continue
        kept.append(option)
        counts[identity]['after'] += 1
        row = warm[identity]
        if (row['unit'] == option['unit_id'] and row['opp'] == option['opp_id']
                and q(row['start_ms']) == start):
            anchor_seen.add(identity)
    require(anchor_seen == set(stages), 'ANCHOR_OPTION_MISSING_FROM_COMPLETE_DOMAIN')
    out = {'protocol': 'g0-closed-anchor-exact-filter-v1',
           'source_input_sha256': canonical_hash(instance),
           'condition_sha256': condition['condition_sha256'], 'anchor_sha256': condition['anchor_sha256'],
           'input_options_sha256': canonical_hash(options), 'output_options_sha256': canonical_hash(kept),
           'before': len(options), 'after': len(kept), 'removed': len(options)-len(kept),
           'domain_removed': domain_removed, 'closed_anchor_removed': len(removals),
           'removals': removals, 'by_scene_stage': {sid: counts}, 'scene_ids': [sid],
           'complete': True, 'preeliminate': preeliminate,
           'proof_scope': 'original G0-domain legal integer schedules; no thermal/global proof'}
    check_budget(budget)
    return kept, out


def filter_domain_options(config, instance, options, condition, *, budget=None):
    return filter_options(config, instance, options, condition, budget=budget, preeliminate=False)
