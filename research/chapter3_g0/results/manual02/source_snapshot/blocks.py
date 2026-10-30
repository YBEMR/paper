"""Deterministic G0 whole-copy blocks; exact activity proxy, never a bound.

No scheduling/search/thermal backends are imported or invoked.  Declaration
is returned only after all choices and the final budget check complete.
"""
from .contract import (q, require, check_budget, candidate_rows, scenes,
                       canonical_hash, validate_deployment)


def _overlap(a, b):
    return max(q(a['start_ms']), q(b['start_ms'])) < min(q(a['end_ms']), q(b['end_ms']))


def _group_data(config, instance, anchor, d0, scene_id, budget):
    validate_deployment(config, instance, d0)
    normalized = candidate_rows(config, instance, anchor)
    for by_stage in normalized.values():
        for row in by_stage.values():
            require(row['unit'] == d0[row['shared_stage_id']], 'ANCHOR_D0_MISMATCH')
    require(scene_id in normalized, 'UNKNOWN_BLOCK_SCENE')
    scene, rows = scenes(instance)[scene_id], normalized[scene_id]
    requests = {r['id']: r for r in scene['requests']}
    groups = {}
    for identity, row in rows.items():
        check_budget(budget)
        groups.setdefault(row['shared_stage_id'], []).append(identity)
    data = {}
    for shared in sorted(groups):
        check_budget(budget)
        members = sorted(groups[shared])
        choices = [m for m in instance['stage_modes'][shared] if m['unit_id'] == d0[shared]]
        require(choices, 'NO_SAME_DEVICE_MODES')
        minimum = min(q(m['duration_ms']) * q(m['activity_power_W']) / 1000 for m in choices)
        headroom, slack = q(0), []
        for identity in members:
            row = rows[identity]
            activity = q(row['duration_ms']) * q(row['activity_power_W']) / 1000
            headroom += max(q(0), activity - minimum)
            limits = [q(requests[row['request_id']]['deadline_ms']), q(instance['window_ms'])]
            limits.extend(q(rows[b]['start_ms']) for a, b in scene['dependencies'] if a == identity)
            slack.append(min(limits) - q(row['end_ms']))
        data[shared] = {'members': members, 'H_J': headroom, 'slack_ms': min(slack)}
    adjacency = set()
    by_unit = {}
    for identity, row in rows.items():
        by_unit.setdefault(row['unit'], []).append(identity)
    for values in by_unit.values():
        ordered = sorted(values, key=lambda i: (q(rows[i]['start_ms']), q(rows[i]['end_ms']), i))
        adjacency.update(frozenset((a, b)) for a, b in zip(ordered, ordered[1:]))
    return scene, rows, data, adjacency


def select_block(config, instance, anchor, d0, scene_id, capacity, *,
                 previous_open=None, phase=1, budget=None):
    """Select the frozen-anchor G0 B1/B2, capped by execution instances.

    ``previous_open`` is None, a list of B1 execution IDs, or a complete B1
    declaration. B1 NOT_DECLARED is the empty set, not a failed half-block.
    A returned empty block is a legitimate skip (no complementary seed fits).
    """
    check_budget(budget)
    require(phase in (1, 2), 'INVALID_PHASE')
    require(type(capacity) is int and capacity == (2 if phase == 1 else 4), 'G0_CAPACITY_MISMATCH')
    scene, rows, groups, adjacency = _group_data(config, instance, anchor, d0, scene_id, budget)
    if isinstance(previous_open, dict):
        require(previous_open.get('scene_id') == scene_id, 'PREVIOUS_BLOCK_SCENE')
        require(previous_open.get('state') in ('DECLARED', 'NOT_DECLARED'), 'PREVIOUS_BLOCK_STATE')
        if previous_open['state'] == 'NOT_DECLARED':
            require(not previous_open.get('open_ids', []), 'UNDECLARED_BLOCK_MUST_BE_EMPTY')
        else:
            unhashed = dict(previous_open)
            digest = unhashed.pop('declaration_sha256', None)
            require(digest == canonical_hash(unhashed), 'PREVIOUS_BLOCK_MODIFIED')
            require(previous_open.get('phase') == 1
                    and previous_open.get('source_input_sha256') == canonical_hash(instance)
                    and previous_open.get('config_sha256') == canonical_hash(config)
                    and previous_open.get('d0_sha256') == canonical_hash(d0), 'PREVIOUS_BLOCK_IDENTITY')
        previous_open = previous_open.get('open_ids', [])
    previous = set(previous_open or [])
    require(previous <= set(rows), 'UNKNOWN_PREVIOUS_OPEN_INSTANCE')
    for item in groups.values():
        require(not (set(item['members']) & previous) or set(item['members']) <= previous,
                'SPLIT_PREVIOUS_COPY_GROUP')
    previous_groups = {shared for shared, item in groups.items() if set(item['members']) <= previous}
    remaining = [shared for shared, item in groups.items()
                 if len(item['members']) <= capacity and (phase == 1 or shared not in previous_groups)]
    selected, log = [], []
    if remaining:
        seed = min(remaining, key=lambda v: (-groups[v]['H_J'], groups[v]['slack_ms'], v))
        selected.append(seed)
        log.append({'group': seed, 'kind': 'seed', 'relation_level': None})
    units = {u['id']: u for u in instance['platform']['units']}
    edges = {frozenset(e) for e in scene['dependencies']}

    def relation(shared):
        chosen = [i for v in selected for i in groups[v]['members']]
        level = 4
        for left in groups[shared]['members']:
            for right in chosen:
                a, b = rows[left], rows[right]
                if (units[a['unit']]['device_class'] == 'CPU'
                        and units[b['unit']]['device_class'] == 'CPU'
                        and a['domain_id'] == b['domain_id'] and _overlap(a, b)):
                    level = min(level, 1)
                if frozenset((left, right)) in adjacency:
                    level = min(level, 2)
                if frozenset((left, right)) in edges:
                    level = min(level, 3)
        return level

    while selected:
        check_budget(budget)
        used = sum(len(groups[v]['members']) for v in selected)
        fitting = [v for v in sorted(groups) if v not in selected
                   and len(groups[v]['members']) <= capacity - used]
        if not fitting:
            break
        levels = {v: relation(v) for v in fitting}
        if phase == 1:
            key = lambda v: (levels[v], -groups[v]['H_J'], groups[v]['slack_ms'], v)
        else:
            key = lambda v: (levels[v], v in previous_groups, -groups[v]['H_J'], groups[v]['slack_ms'], v)
        picked = min(fitting, key=key)
        selected.append(picked)
        log.append({'group': picked, 'kind': 'extension', 'relation_level': levels[picked]})
    out = {'protocol': 'g0-whole-copy-block-v1', 'phase': phase, 'scene_id': scene_id,
           'capacity': capacity, 'state': 'DECLARED', 'groups': selected,
           'open_ids': sorted(i for v in selected for i in groups[v]['members']),
           'previous_open_ids': sorted(previous), 'selection_trace': log,
           'scores': {v: {'members': item['members'], 'H_J': str(item['H_J']),
                          'slack_ms': str(item['slack_ms'])} for v, item in groups.items()},
           'source_input_sha256': canonical_hash(instance), 'config_sha256': canonical_hash(config),
           'anchor_sha256': canonical_hash(anchor), 'd0_sha256': canonical_hash(d0)}
    out['declaration_sha256'] = canonical_hash(out)
    check_budget(budget)
    return out


def coverage(instance, scene_id, blocks):
    """Separate declared, built and entered coverage; no optimization claim."""
    stage_ids = {s['id'] for s in scenes(instance)[scene_id]['stage_instances']}
    declared, built, entered = set(), set(), set()
    for block in blocks:
        if block is None or block.get('state') == 'NOT_DECLARED':
            continue
        require(block.get('scene_id') == scene_id, 'COVERAGE_SCENE')
        ids = set(block['open_ids'])
        require(ids <= stage_ids, 'COVERAGE_UNKNOWN_STAGE')
        declared |= ids
        if block.get('model_completed', False):
            built |= ids
        if block.get('solver_entered', False):
            entered |= ids
    return {'total_executions': len(stage_ids), 'declared_union_ids': sorted(declared),
            'built_union_ids': sorted(built), 'entered_union_ids': sorted(entered),
            'declared_fraction': str(q(len(declared)) / len(stage_ids)),
            'entered_fraction': str(q(len(entered)) / len(stage_ids)),
            'scope': 'local_block_execution_coverage_not_initializer_or_full_physics_coverage'}
