"""Exact one-pass implications of mandatory closed linked-domain anchors.

No optimizer, thermal evaluation, cache, open/open propagation or repair.
This preserves the linked subproblem's legal integer schedules, not the
pointwise floating outer approximation after rebuilding event coefficients.
"""
import hashlib
from pathlib import Path

from scene_adapter import canonical_hash, _scenes
from thermal import _q


PROTOCOL = 'closed-anchor-original-resource-and-direct-edge-filter-v1'


def filter_closed_anchor_options(instance, condition, options, *, budget, scene_ids=None):
    """Filter an already linked/deadline-intersected option list in order.

    Full original input/condition identities are retained even when the model
    projects one explicit scene. All times use original exact ms scalars.
    An interruption raises; it never publishes a partly complete filter.
    """
    from linked_neighborhood import validate_linked_condition, _member
    condition = validate_linked_condition(instance, condition, budget=budget)
    scenes = _scenes(instance)
    selected = list(scenes) if scene_ids is None else list(scene_ids)
    if not selected or len(selected) != len(set(selected)) or not set(selected) <= set(scenes):
        raise ValueError('Anchor filter requires unique original scene identities')
    if not isinstance(options, list):
        raise ValueError('Anchor filter requires a complete option list')
    units = {u['id']: u for u in instance['platform']['units']}
    if len(units) != len(instance['platform']['units']):
        raise ValueError('Duplicate execution unit identity')
    stages, edges, modes, anchors, counts = {}, {}, {}, {}, {}
    for sid in selected:
        budget.check()
        scene = scenes[sid]
        by_stage = {s['id']: s for s in scene['stage_instances']}
        if len(by_stage) != len(scene['stage_instances']):
            raise ValueError('Duplicate Stage instance identity')
        stages[sid] = by_stage
        edges[sid] = {tuple(edge) for edge in scene['dependencies']}
        if any(len(edge) != 2 or not set(edge) <= set(by_stage) for edge in edges[sid]):
            raise ValueError('Unknown original direct dependency')
        anchors[sid] = []
        counts[sid] = {stage: {'before': 0, 'after': 0} for stage in by_stage}
        for stage_id, stage in by_stage.items():
            budget.check()
            shared = stage['shared_stage_id']
            catalog = {}
            for mode in instance['stage_modes'][shared]:
                budget.check()
                key = mode['unit_id'], mode['opp_id']
                unit = units.get(mode['unit_id'])
                if (key in catalog or unit is None or mode['shared_stage_id'] != shared
                        or mode['domain_id'] != unit['domain_id']
                        or mode['opp_id'] not in instance['platform']['domains'][unit['domain_id']]['opps']
                        or _q(mode['duration_ms']) <= 0):
                    raise ValueError('Invalid or ambiguous original mode')
                catalog[key] = mode
            modes[sid, stage_id] = catalog
            if stage_id not in condition['opened_by_scene'][sid]:
                row = condition['warm_options_by_scene'][sid][stage_id]
                mode = catalog[row['unit'], row['opp']]
                start = _q(row['start_ms'])
                anchors[sid].append({'stage_id': stage_id, 'unit_id': row['unit'],
                    'opp_id': row['opp'], 'domain_id': mode['domain_id'],
                    'start_ms': str(start), 'end_ms': str(start+_q(mode['duration_ms']))})
    budget.check()
    before_hash = canonical_hash(options)
    kept, removals, seen, closed_seen = [], [], set(), set()
    for option in options:
        budget.check()
        sid, stage_id = option['scenario_id'], option['stage_instance_id']
        if sid not in stages or stage_id not in stages[sid]:
            raise ValueError('Unknown or unselected option scene/Stage identity')
        stage = stages[sid][stage_id]
        mode = modes[sid, stage_id].get((option['unit_id'], option['opp_id']))
        if (mode is None or any(option.get(key) != value for key, value in mode.items())
                or option['request_id'] != stage['request_id']
                or not _member(condition, sid, stage_id, option['unit_id'], option['opp_id'], option['start_ms'])):
            raise ValueError('Option differs from original mode or linked domain')
        start, end = _q(option['start_ms']), _q(option['end_ms'])
        identity = sid, stage_id, option['unit_id'], option['opp_id'], start
        if identity in seen or end != start+_q(mode['duration_ms']):
            raise ValueError('Duplicate option or nonoriginal end time')
        seen.add(identity)
        counts[sid][stage_id]['before'] += 1
        if stage_id not in condition['opened_by_scene'][sid]:
            closed_seen.add((sid, stage_id))
            kept.append(option)
            counts[sid][stage_id]['after'] += 1
            continue
        reasons = []
        for anchor in anchors[sid]:
            budget.check()
            astart, aend = _q(anchor['start_ms']), _q(anchor['end_ms'])
            overlap = max(start, astart) < min(end, aend)
            rules = []
            if overlap and option['unit_id'] == anchor['unit_id']:
                rules.append('same_unit_overlap')
            if (overlap and option['domain_id'] == anchor['domain_id']
                    and option['opp_id'] != anchor['opp_id']):
                rules.append('same_domain_different_opp_overlap')
            if (stage_id, anchor['stage_id']) in edges[sid] and end > astart:
                rules.append('open_predecessor_finishes_after_closed_start')
            if (anchor['stage_id'], stage_id) in edges[sid] and start < aend:
                rules.append('open_successor_starts_before_closed_end')
            if rules:
                reasons.append({'rules': rules, 'anchor': dict(anchor)})
        if reasons:
            removals.append({'scenario_id': sid, 'stage_instance_id': stage_id,
                'option_id': option['option_id'], 'unit_id': option['unit_id'],
                'opp_id': option['opp_id'], 'domain_id': option['domain_id'],
                'start_ms': str(start), 'end_ms': str(end), 'reasons': reasons})
        else:
            kept.append(option)
            counts[sid][stage_id]['after'] += 1
    expected_closed = {(sid, a['stage_id']) for sid, values in anchors.items() for a in values}
    if closed_seen != expected_closed:
        raise ValueError('Mandatory closed anchor missing from supplied option domain')
    stats = {'protocol': PROTOCOL, 'source_input_sha256': canonical_hash(instance),
        'condition_sha256': condition['condition_sha256'],
        'warm_candidate_sha256': condition['warm_candidate_sha256'],
        'filter_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'scene_ids': selected, 'input_options_sha256': before_hash,
        'output_options_sha256': canonical_hash(kept),
        'before': len(options), 'after': len(kept), 'removed': len(removals),
        'by_scene_stage': counts, 'anchors_by_scene': anchors, 'removals': removals,
        'empty_open_stage_option_sets': [{'scenario_id': sid, 'stage_instance_id': stage}
            for sid, values in counts.items() for stage, count in values.items()
            if stage in condition['opened_by_scene'][sid] and count['after'] == 0],
        'complete': True, 'passes': 1,
        'proof_scope': 'original linked-domain legal integer schedules; no thermal or global infeasibility proof'}
    budget.check()
    return kept, stats
