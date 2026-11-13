"""K195 static domain admission; no model construction, solve or integration.

The numerical builder remains the original whole MILP.  These checks inspect
its returned metadata and supplied schedules; they never generate a physical
trajectory, reuse an enumeration witness or add a search restriction.
"""
from collections import Counter
from copy import deepcopy
from fractions import Fraction as Q
from hashlib import sha256
import json

from inputs import expand_options
from schedules import validate_schedule


DOMAIN_ID = 'quality_full_chain_domain_v2__R1'
EXPECTED_GROUPS = {('AB_offset_0ms', 'CPU1'): 450,
                   ('AB_offset_0ms', 'NPU0'): 650,
                   ('AC_offset_0ms', 'CPU1'): 90,
                   ('AC_offset_0ms', 'NPU0'): 360}
BUILDER_FLAGS = dict(include_physics=True, fix_late_options=True,
    aggregate_opp_locks=True, relax_auxiliary_integrality=True,
    strengthen_energy_lower_bounds=True, prefilter_deadlines=True,
    cumulative_precedence=False, fixed_deployment=None,
    fixed_shared_deployment=None, fixed_scene_id=None,
    neighborhood_condition=None, preeliminate_closed_anchors=False)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'))


def option_key(option):
    return (option['scenario_id'], option['stage_instance_id'],
            option['unit_id'], option['opp_id'], Q(option['start_ms']))


def retained_catalog(instance, config):
    """Original option expansion and original exact deadline prefilter only."""
    require(instance.get('id') == DOMAIN_ID, 'Wrong declared small-domain identity')
    require(instance.get('window_ms') == '400' and
            instance.get('start_grid_ms') == '5', 'Window/start grid changed')
    require(instance['platform']['node_order'] == ['CPU1', 'CPU2', 'GPU0', 'NPU0'],
            'Original four-node platform changed')
    require(instance['execution_rules']['idle_policy'] == 'auto_low_immediate_v1',
            'Original auto-L control policy changed')
    raw = expand_options(instance, config)
    kept = [row for row in raw if Q(row['end_ms']) <= Q(row['request_deadline_ms'])]
    removed = [row for row in raw if Q(row['end_ms']) > Q(row['request_deadline_ms'])]
    require(len(raw) == 78 and len(kept) == 72 and len(removed) == 6,
            'Frozen 78-to-72 catalog changed')
    require(len({row['option_id'] for row in raw}) == len(raw), 'Duplicate option ID')
    require(len({option_key(row) for row in raw}) == len(raw), 'Duplicate local choice')
    expected_late = {('AB_offset_0ms', 'AB_offset_0ms::B_r1::B.main', 'CPU1', 'M', Q(t))
                     for t in (30, 35, 40, 45, 50)}
    expected_late.add(('AC_offset_0ms', 'AC_offset_0ms::C_r1::C.main', 'CPU1', 'M', Q(35)))
    require({option_key(row) for row in removed} == expected_late,
            'Deadline prefilter removed a different choice')
    return raw, kept, removed


def validate_candidate(instance, candidate, config):
    """Complete structural and declared-domain membership admission, no heat."""
    _, kept, _ = retained_catalog(instance, config)
    result = validate_schedule(instance, candidate)
    require(result.get('state') == 'SCHEDULE_VALID_THERMAL_UNCHECKED',
            'Complete candidate fails original structural checker')
    allowed = {option_key(row) for row in kept}
    chosen = {(sid, row['stage_id'], row['unit'], row['opp'], Q(row['start_ms']))
              for sid, rows in candidate['scenes'].items() for row in rows}
    require(len(chosen) == 12 and chosen <= allowed,
            'Candidate not a full member of the frozen retained catalog')
    return {'passed': True, 'errors': [], 'state': 'COMPLETE_STRUCTURAL_DOMAIN_MEMBER',
            'stage_choices': len(chosen), 'raw_count': 78, 'retained_count': len(kept),
            'thermal_evaluations': 0, 'legality': result}


def audit_static(instance, config, manifest):
    """Check every K194 scene arrangement survives the original prefilter."""
    raw, kept, removed = retained_catalog(instance, config)
    require(len(manifest) == 1550, 'Wrong manifest size')
    allowed = {option_key(row) for row in kept}
    identities, groups = set(), Counter()
    scenes = {scene['id']: scene for scene in instance['scenarios']}
    for position, entry in enumerate(manifest, 1):
        require(entry['ordinal'] == position, 'Manifest order changed')
        sid, candidate = entry['scene_id'], entry['candidate']
        require(sid in scenes and set(candidate['scenes']) == {sid},
                'Manifest is not one declared complete scene')
        identity = sha256(canonical(candidate).encode('utf-8')).hexdigest()
        require(entry['id'] == identity and identity not in identities,
                'Manifest identity mismatch/duplicate')
        identities.add(identity)
        view = deepcopy(instance)
        view['scenarios'] = [deepcopy(scenes[sid])]
        view['scenarios'][0]['weight'] = '1'
        view['start_domain']['by_scene_stage_ms'] = {
            sid: deepcopy(instance['start_domain']['by_scene_stage_ms'][sid])}
        require(validate_schedule(view, candidate).get('state') ==
                'SCHEDULE_VALID_THERMAL_UNCHECKED', 'Manifest structural legality failed')
        rows = candidate['scenes'][sid]
        require(len(rows) == 6 and all((sid, r['stage_id'], r['unit'], r['opp'],
                Q(r['start_ms'])) in allowed for r in rows),
                'Manifest arrangement lost a retained option')
        main = next(r for r in rows if r['stage_id'].endswith('::A.main'))
        require(main['unit'] == entry['shared_A_device'], 'Manifest shared device mismatch')
        groups[sid, main['unit']] += 1
    require(dict(groups) == EXPECTED_GROUPS, 'Manifest group coverage changed')
    joint = sum(groups['AB_offset_0ms', unit] * groups['AC_offset_0ms', unit]
                for unit in ('CPU1', 'NPU0'))
    require(joint == 274500, 'Compatible complete arrangement count changed')
    return {'passed': True, 'errors': [], 'state': 'STATIC_DOMAIN_PASS',
            'raw_count': len(raw), 'retained_count': len(kept), 'raw_options': len(raw),
            'retained_options': len(kept), 'deadline_removed': len(removed),
            'removed_option_ids': [row['option_id'] for row in removed],
            'scene_arrangements': len(manifest), 'compatible_joint_arrangements': joint,
            'groups': [{'scene_id': sid, 'shared_A_device': unit, 'count': count}
                       for (sid, unit), count in EXPECTED_GROUPS.items()],
            'model_constructions': 0, 'optimizer_calls': 0, 'thermal_evaluations': 0}


def validate_model(model, instance, config):
    """Inspect the actual returned original model before any native request.

    Pure tests supply metadata fakes.  Passing such a fake is not evidence that
    the full numerical model was constructed or is feasible.
    """
    _, kept, _ = retained_catalog(instance, config)
    require(model.instance == instance, 'Builder changed frozen input')
    require(model.options == kept, 'Actual numerical model option catalog drift')
    columns = list(model.option_vars)
    require(len(columns) == 72 and len(set(columns)) == 72,
            'Stage option variables are not one-to-one')
    require(all(type(column) is int and 0 <= column < len(model.names)
                for column in columns), 'Invalid Stage option variable index')
    require(len(model.integer) == 72 and set(model.integer) == set(columns),
            'Stage options lost integer status or auxiliaries became integer')
    require(set(columns) <= set(model.logical_binary), 'Stage options lost logical status')
    for option, column in zip(kept, columns):
        require(model.names[column] == 'y:' + option['option_id'],
                'Stage option name/order mismatch')
        require(Q(model.lb[column]) == 0 and Q(model.ub[column]) == 1,
                'Stage option binary bounds changed')
    formulation = model.formulation
    for key in ('fix_late_options', 'aggregate_opp_locks', 'relax_auxiliary_integrality',
                'energy_lower_bounds', 'prefilter_deadlines'):
        require(formulation.get(key) is True, 'Original whole flag missing: ' + key)
    require(formulation.get('idle_policy') == 'auto_low_immediate_v1', 'Model idle policy drift')
    for key in ('fixed_deployment', 'fixed_shared_deployment', 'fixed_device_neighborhood',
                'cumulative_precedence', 'preeliminate_closed_anchors'):
        require(formulation.get(key, False) is False, 'Whole model restricted: ' + key)
    require(formulation.get('fixed_scene_id') is None, 'Whole model contains one scene only')
    preprocessing = model.preprocessing
    require(preprocessing.get('options_before_deadline_filter') == 78 and
            preprocessing.get('deadline_removed_count') == 6 and
            preprocessing.get('empty_stage_option_sets') == [],
            'Original deadline prefilter metadata drift')
    for key in ('fixed_deployment', 'fixed_shared_deployment', 'fixed_scene_id',
                'neighborhood_condition_sha256', 'closed_anchor_preelimination'):
        require(preprocessing.get(key) is None, 'Unexpected search restriction: ' + key)
    require(getattr(model, 'neighborhood_condition', None) is None,
            'Neighborhood condition attached to whole model')
    require(set(model.scenes) == {s['id'] for s in instance['scenarios']},
            'Full AB/AC model coverage missing')
    for meta in model.scenes.values():
        require(bool(meta.get('theta')) and bool(meta.get('energy')),
                'Whole model physical variables absent')
    return {'passed': True, 'errors': [], 'state': 'WHOLE_MODEL_METADATA_PASS',
            'raw_count': 78, 'retained_count': len(kept), 'y_count': len(columns),
            'stage_integer_options': 72,
            'auxiliary_integer_variables': 0, 'scope': 'metadata admission, not feasibility proof'}
