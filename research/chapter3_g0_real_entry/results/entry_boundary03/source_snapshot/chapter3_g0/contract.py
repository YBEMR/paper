"""G0 structural/time contract. No optimizer, physical propagation or I/O.

The scientific dictionary schema is the existing chapter3-input-v0.1 schema:
platform.units/domains/node_order; window_ms/start_grid_ms; scenarios with
requests, stage_instances and explicit dependencies; stage_modes.  Fractions
are exact ms/W scalars.  This validates timing, never certifies thermal SAFE.
"""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json


class ContractError(ValueError):
    pass


def require(test, reason):
    if not test:
        raise ContractError(reason)


def q(value):
    require(not isinstance(value, bool) and isinstance(value, (str, int, Fraction)),
            'NONEXACT_SCALAR')
    return Fraction(value)


def canonical_hash(value):
    def encode(item):
        if isinstance(item, Fraction):
            return {'__exact_fraction__': str(item)}
        raise TypeError('non-JSON identity value: ' + type(item).__name__)
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), default=encode, allow_nan=False).encode('utf-8')).hexdigest()


def check_budget(budget):
    if budget is not None:
        budget.check()


def scenes(instance):
    values = instance['scenarios']
    require(isinstance(values, list) and values, 'EMPTY_SCENARIOS')
    result = {value['id']: value for value in values}
    require(len(result) == len(values) and all(isinstance(v, str) and v for v in result),
            'DUPLICATE_OR_INVALID_SCENARIO')
    return result


def by_id(values, label):
    require(isinstance(values, list), 'EXPECTED_LIST_' + label)
    out = {item['id']: item for item in values}
    require(len(out) == len(values) and all(isinstance(k, str) and k for k in out),
            'DUPLICATE_OR_INVALID_' + label)
    return out


_FORBIDDEN = frozenset({
    'reference_timetable', 'reference_timetables', 'reference_schedule',
    'reference_deployment', 'H_reference_timetable', 'historical_safe',
    'historical_SAFE', 'external_heft_result', 'heft_initial_solution',
    'heat_cache', 'thermal_cache', 'formal_initial_solution',
})


def assert_reference_isolation(value):
    """Reject reference/other-run artifacts, including nested accidental fields."""
    if isinstance(value, dict):
        for key, item in value.items():
            require(key not in _FORBIDDEN, 'FORBIDDEN_REFERENCE_INFORMATION:' + str(key))
            assert_reference_isolation(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            assert_reference_isolation(item)


def explicit_starts(instance):
    if 'start_domain' not in instance:
        return None
    declaration = instance['start_domain']
    require(isinstance(declaration, dict) and set(declaration) == {
        'version', 'kind', 'by_scene_stage_ms'}, 'INVALID_START_DOMAIN_FIELDS')
    require(type(declaration['version']) is int and declaration['version'] == 1
            and declaration['kind'] == 'explicit_grid_subset', 'INVALID_START_DOMAIN_VERSION')
    supplied = declaration['by_scene_stage_ms']
    ss = scenes(instance)
    require(isinstance(supplied, dict) and set(supplied) == set(ss), 'START_DOMAIN_SCENES')
    grid, window = q(instance['start_grid_ms']), q(instance['window_ms'])
    result = {}
    for sid, scene in ss.items():
        expected = {st['id'] for st in scene['stage_instances']}
        require(isinstance(supplied[sid], dict) and set(supplied[sid]) == expected,
                'START_DOMAIN_STAGES')
        result[sid] = {}
        for stage, values in supplied[sid].items():
            require(isinstance(values, list), 'START_DOMAIN_LIST_REQUIRED')
            values = list(map(q, values))
            require(len(values) == len(set(values)) and all(
                0 <= v <= window and (v / grid).denominator == 1 for v in values),
                'INVALID_START_DOMAIN_VALUE')
            result[sid][stage] = frozenset(values)  # Empty stays empty.
    return result


def validate_inputs(config, instance):
    """Validate explicit scientific identities without constructing any options.

    Does not invent beta, deadlines, a window or a fallback start set.  Optional
    required_stage_instance_ids / required_output_stage_ids are checked when
    supplied; arbitrary DAG shape is retained and need not resemble a chain.
    """
    require(isinstance(config, dict) and isinstance(instance, dict), 'SCIENTIFIC_DICTS_REQUIRED')
    assert_reference_isolation(config)
    assert_reference_isolation(instance)
    require(instance.get('schema_version') == 'chapter3-input-v0.1', 'INPUT_SCHEMA')
    require(q(instance['window_ms']) > 0 and q(instance['start_grid_ms']) > 0,
            'INVALID_WINDOW_GRID')
    require(config['platform'] == instance['platform'], 'CONFIG_PLATFORM_MISMATCH')
    require(config['execution_rules'] == instance['execution_rules'], 'CONFIG_RULES_MISMATCH')
    platform = instance['platform']
    units = by_id(platform['units'], 'UNIT')
    domains, nodes = platform['domains'], platform['node_order']
    require(len(nodes) == 4 and len(set(nodes)) == 4, 'EXPECTED_FOUR_THERMAL_NODES')
    require(bool(units) and isinstance(domains, dict) and domains, 'EMPTY_PLATFORM')
    for uid, unit in units.items():
        did = unit['domain_id']
        require(did in domains and uid in domains[did]['unit_ids']
                and unit['thermal_node_id'] in nodes, 'UNIT_DOMAIN_MEMBERSHIP')
    rules = instance['execution_rules']
    for key in ('preemption', 'migration', 'in_stage_opp_change'):
        require(rules[key] is False, 'UNSUPPORTED_EXECUTION_RULE:' + key)
    require(rules['switch_only_when_domain_empty'] is True
            and rules['interval_convention'] == '[start,end)', 'UNSUPPORTED_EXECUTION_RULE')
    require(rules.get('idle_holds_last_opp') is False
            and rules.get('idle_policy') == 'auto_low_immediate_v1'
            and q(rules['idle_delay_ms']) == 0, 'G0_REQUIRES_DECLARED_IMMEDIATE_AUTO_L')
    for key in ('extra_transfer_time_ms', 'extra_switch_time_ms', 'extra_handoff_time_ms',
                'extra_transfer_energy_J', 'extra_switch_energy_J', 'extra_handoff_energy_J'):
        require(q(rules[key]) == 0, 'UNSUPPORTED_NONZERO_OVERHEAD:' + key)
    for did, domain in domains.items():
        low = domain['opps']['L']
        require(q(low['frequency_GHz']) > 0 and q(low['voltage_V']) > 0
                and all(q(other['frequency_GHz']) > q(low['frequency_GHz'])
                        for name, other in domain['opps'].items() if name != 'L'),
                'L_NOT_UNIQUE_LOWEST_OPP:' + did)
    ss = scenes(instance)
    used, occurrences, global_ids = set(), {}, set()
    window = q(instance['window_ms'])
    for sid, scene in ss.items():
        weight = q(scene['weight'])
        require(weight >= 0, 'NEGATIVE_SCENE_WEIGHT')
        stages, requests = by_id(scene['stage_instances'], 'STAGE'), by_id(scene['requests'], 'REQUEST')
        require(stages and requests, 'EMPTY_SCENE')
        require(not (set(stages) & global_ids), 'GLOBAL_STAGE_ID_COLLISION')
        global_ids.update(stages)
        for rid, request in requests.items():
            members = request['stage_instance_ids']
            expected = {i for i, st in stages.items() if st['request_id'] == rid}
            require(isinstance(members, list) and members and len(members) == len(set(members))
                    and set(members) == expected, 'REQUEST_STAGE_MEMBERSHIP')
            require(0 <= q(request['release_ms']) <= q(request['deadline_ms']) <= window,
                    'REQUEST_WINDOW')
        for stage in stages.values():
            require(stage['request_id'] in requests, 'UNKNOWN_STAGE_REQUEST')
            v = stage['shared_stage_id']
            require(isinstance(v, str) and v in instance['stage_modes'], 'UNKNOWN_SHARED_STAGE')
            used.add(v)
            occurrences.setdefault(v, []).append((sid, stage))
        edge_list = scene['dependencies']
        require(isinstance(edge_list, list) and all(isinstance(e, list) and len(e) == 2
                and set(e) <= set(stages) and e[0] != e[1] for e in edge_list), 'INVALID_DAG_EDGE')
        require(len(edge_list) == len({tuple(e) for e in edge_list}), 'DUPLICATE_DAG_EDGE')
        remaining = set(stages)
        while remaining:
            roots = {v for v in remaining if not any(b == v and a in remaining for a, b in edge_list)}
            require(roots, 'CYCLIC_INSTANCE_DAG')
            remaining -= roots
        if 'required_stage_instance_ids' in scene:
            require(set(scene['required_stage_instance_ids']) == set(stages), 'MISSING_REQUIRED_BRANCH')
        if 'required_output_stage_ids' in scene:
            require(set(scene['required_output_stage_ids']) <= set(stages), 'MISSING_REQUIRED_OUTPUT')
    require(sum(q(scene['weight']) for scene in ss.values()) > 0, 'ZERO_TOTAL_WEIGHT')
    allowed = {}
    for shared in sorted(used):
        modes, keys = instance['stage_modes'][shared], set()
        require(isinstance(modes, list) and modes, 'EMPTY_STAGE_MODE_SET')
        for mode in modes:
            uid, opp = mode['unit_id'], mode['opp_id']
            key = uid, opp
            require(key not in keys and uid in units, 'DUPLICATE_OR_UNKNOWN_MODE')
            keys.add(key)
            require(mode['shared_stage_id'] == shared and mode['domain_id'] == units[uid]['domain_id']
                    and opp in domains[mode['domain_id']]['opps'], 'MODE_PLATFORM_MISMATCH')
            for name in ('thermal_node_id', 'power_group_id'):
                if name in mode:
                    require(mode[name] == units[uid][name], 'MODE_LOCAL_SOURCE_MISMATCH')
            working_point = domains[mode['domain_id']]['opps'][opp]
            for name in ('frequency_GHz', 'voltage_V'):
                if name in mode:
                    require(q(mode[name]) == q(working_point[name]), 'MODE_WORKING_POINT_MISMATCH')
            require(q(mode['duration_ms']) > 0 and q(mode['activity_power_W']) >= 0,
                    'INVALID_MODE_COST')
        legal = {uid for uid, opp in keys}
        for sid, stage in occurrences[shared]:
            if 'legal_units' in stage:
                declared = stage['legal_units']
                require(isinstance(declared, list) and len(declared) == len(set(declared)),
                        'INVALID_OCCURRENCE_LEGAL_UNITS')
                legal &= set(declared)
        require(legal, 'EMPTY_CURRENT_OCCURRENCE_SUPPORT_INTERSECTION')
        allowed[shared] = sorted(legal)
    explicit_starts(instance)
    return {'state': 'G0_INPUT_VALID_PHYSICS_UNCHECKED',
            'source_input_sha256': canonical_hash(instance), 'config_sha256': canonical_hash(config),
            'scene_ids': sorted(ss), 'legal_units': allowed,
            'execution_count': sum(len(scene['stage_instances']) for scene in ss.values())}


def validate_deployment(config, instance, d0):
    data = validate_inputs(config, instance)
    require(isinstance(d0, dict) and set(d0) == set(data['legal_units']), 'D0_ALL_COVERAGE')
    for shared, uid in d0.items():
        require(uid in data['legal_units'][shared], 'D0_ILLEGAL_DEVICE:' + shared)
    return {shared: d0[shared] for shared in sorted(d0)}


def cross_projection(instance, d0):
    occurred = {}
    for sid, scene in scenes(instance).items():
        for stage in scene['stage_instances']:
            occurred.setdefault(stage['shared_stage_id'], set()).add(sid)
    require(set(d0) == set(occurred), 'D0_ALL_COVERAGE')
    return {shared: d0[shared] for shared in sorted(occurred) if len(occurred[shared]) >= 2}


def mode_for(instance, shared, unit, opp):
    matches = [m for m in instance['stage_modes'][shared] if m['unit_id'] == unit and m['opp_id'] == opp]
    require(len(matches) == 1, 'ILLEGAL_OR_AMBIGUOUS_MODE')
    return matches[0]


def candidate_rows(config, instance, candidate, *, scene_id=None):
    """Check exact complete timing; return normalized full rows by scene.

    A scene projection is accepted only when scene_id explicitly selects it.
    No energy or thermal SAFE flag is produced.
    """
    data = validate_inputs(config, instance)
    ss = scenes(instance)
    expected = set(ss) if scene_id is None else {scene_id}
    require(expected <= set(ss) and isinstance(candidate, dict) and set(candidate) == {'scenes'}
            and isinstance(candidate['scenes'], dict) and set(candidate['scenes']) == expected,
            'CANDIDATE_SCENE_COVERAGE')
    grid, window = q(instance['start_grid_ms']), q(instance['window_ms'])
    starts = explicit_starts(instance)
    normalized, deployment = {}, {}
    for sid in sorted(expected):
        scene = ss[sid]
        stages, requests = by_id(scene['stage_instances'], 'STAGE'), by_id(scene['requests'], 'REQUEST')
        supplied = candidate['scenes'][sid]
        require(isinstance(supplied, list) and all(isinstance(r, dict) and set(r) == {
            'stage_id', 'unit', 'opp', 'start_ms'} for r in supplied), 'CANDIDATE_ROW_FIELDS')
        by_stage = {r['stage_id']: r for r in supplied}
        require(len(by_stage) == len(supplied) and set(by_stage) == set(stages), 'CANDIDATE_STAGE_COVERAGE')
        rows = {}
        for stage_id in sorted(stages):
            row, stage = by_stage[stage_id], stages[stage_id]
            shared = stage['shared_stage_id']
            require(row['unit'] in data['legal_units'][shared], 'ILLEGAL_OCCURRENCE_DEVICE')
            mode = mode_for(instance, shared, row['unit'], row['opp'])
            start, duration = q(row['start_ms']), q(mode['duration_ms'])
            end, req = start + duration, requests[stage['request_id']]
            require(start >= 0 and (start / grid).denominator == 1, 'START_OUTSIDE_GRID')
            require(starts is None or start in starts[sid][stage_id], 'START_OUTSIDE_DECLARED_DOMAIN')
            require(start >= q(req['release_ms']), 'BEFORE_RELEASE')
            require(end <= window and end <= q(req['deadline_ms']), 'REQUEST_DEADLINE_EXCEEDED')
            require(shared not in deployment or deployment[shared] == row['unit'], 'SHARED_DEPLOYMENT_MISMATCH')
            deployment[shared] = row['unit']
            rows[stage_id] = dict(row, shared_stage_id=shared, request_id=stage['request_id'],
                domain_id=mode['domain_id'], end_ms=str(end), duration_ms=str(duration),
                activity_power_W=mode['activity_power_W'])
        for a, b in scene['dependencies']:
            require(q(rows[a]['end_ms']) <= q(rows[b]['start_ms']), 'DEPENDENCY_VIOLATION')
        values = list(rows.values())
        for k, left in enumerate(values):
            for right in values[k+1:]:
                overlap = max(q(left['start_ms']), q(right['start_ms'])) < min(q(left['end_ms']), q(right['end_ms']))
                if overlap:
                    require(left['unit'] != right['unit'], 'EXECUTION_UNIT_OVERLAP')
                    require(left['domain_id'] != right['domain_id'] or left['opp'] == right['opp'],
                            'FREQUENCY_DOMAIN_CONFLICT')
        normalized[sid] = rows
    return normalized


def derive_deployment(config, instance, candidate):
    rows = candidate_rows(config, instance, candidate)
    d0 = {r['shared_stage_id']: r['unit'] for by_stage in rows.values() for r in by_stage.values()}
    return validate_deployment(config, instance, d0)


def make_scene_view(instance, scene_id, *, unweighted=True):
    """Pure projection with explicit finite starts retained; no input mutation."""
    ss = scenes(instance)
    require(scene_id in ss, 'UNKNOWN_SCENE')
    view = deepcopy(instance)
    view['scenarios'] = [deepcopy(ss[scene_id])]
    if unweighted:
        view['scenarios'][0]['weight'] = '1'
    used = {st['shared_stage_id'] for st in ss[scene_id]['stage_instances']}
    view['stage_modes'] = {key: value for key, value in view['stage_modes'].items() if key in used}
    if 'start_domain' in view:
        view['start_domain']['by_scene_stage_ms'] = {
            scene_id: deepcopy(view['start_domain']['by_scene_stage_ms'][scene_id])}
    return view
