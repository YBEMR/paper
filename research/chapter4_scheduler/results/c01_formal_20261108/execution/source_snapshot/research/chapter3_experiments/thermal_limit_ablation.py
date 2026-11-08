"""Input-view adapter and read-only posterior summary for one thermal ablation.

The no-operating-limit view keeps the original power-model validity range.
All existing planning stages consume that view, so no 80 C filter survives
in initialization, MILP boxes, candidate admission or thermal feedback.
This module never solves, integrates, repairs, or changes a candidate.
"""
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
import math


PROFILE = 'operating_temperature_limit_ablation_v1'
COMPONENTS = ('baseline', 'activity', 'external_common', 'temperature_correction')


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), default=str).encode('utf-8')).hexdigest()


def _interval(value):
    _require(isinstance(value, (list, tuple)) and len(value) == 2, 'INTERVAL_PAIR_REQUIRED')
    lower, upper = map(F, value)
    _require(lower <= upper, 'INTERVAL_ORDER')
    return lower, upper


def _timely(value, cutoff):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value < cutoff


def planning_instance(original, enforce_limit):
    """Return an independent view; only scene planning ceilings may differ.

Replacing 80 by the *existing* validity ceiling is removal of the operating
constraint within the model domain, not an extension of that domain. The
declaration must stay outside the instance to preserve all other input bytes.
"""
    _require(type(enforce_limit) is bool, 'ENFORCE_LIMIT_BOOL_REQUIRED')
    platform = original['platform']
    nodes = platform['node_order']
    lower, upper = map(F, platform['power_model_temperature_range_degC'])
    _require(lower < F(80) < upper and nodes and len(set(nodes)) == len(nodes),
             'OPERATING_LIMIT_AND_VALIDITY_RANGE')
    _require(original['scenarios'], 'SCENARIOS_REQUIRED')
    original_limits, planning_limits, modified = {}, {}, []
    view = deepcopy(original)
    for index, (source, target) in enumerate(zip(original['scenarios'], view['scenarios'])):
        limits = list(map(F, source['maximum_temperature_degC']))
        initial = list(map(F, source['entry']['temperature_degC']))
        _require(len(limits) == len(initial) == len(nodes) and all(t == 80 for t in limits),
                 'COMMON_80_C_LIMIT_REQUIRED')
        _require(all(lower <= t <= upper for t in initial), 'INITIAL_OUTSIDE_VALIDITY_RANGE')
        sid = source['id']
        _require(sid not in original_limits, 'DUPLICATE_SCENARIO')
        original_limits[sid] = dict(zip(nodes, source['maximum_temperature_degC']))
        if not enforce_limit:
            target['maximum_temperature_degC'] = [str(upper)] * len(nodes)
            modified.append(f'/scenarios/{index}/maximum_temperature_degC')
        planning_limits[sid] = dict(zip(nodes, target['maximum_temperature_degC']))
    declaration = {
        'profile': PROFILE, 'enforce_operating_limit': enforce_limit,
        'original_input_sha256': _digest(original), 'planning_input_sha256': _digest(view),
        'original_limits_degC': original_limits, 'planning_limits_degC': planning_limits,
        'power_model_validity_range_degC': deepcopy(platform['power_model_temperature_range_degC']),
        'modified_paths': modified,
        'planning_SAFE_scope': 'operating_80_C' if enforce_limit else 'physical_model_validity_only',
        'posterior_limits': 'original unmodified 80 C instance',
        'all_planning_stages_use_same_view': [
            'initialization', 'temperature_variable_boxes', 'energy_variable_bounds',
            'conditional_row_big_M', 'energy_lower_bound_rows', 'candidate_admission',
            'thermal_feedback'],
        'scientific_calls': 0, 'physical_evaluations': 0,
    }
    return view, declaration


def summarize_post(original, candidate, evaluation, cutoff_s=60):
    """Read one original-80-C receipt, including complete unsafe scene energies.

Unsafe energy is diagnostic, never a feasible upper bound or a replacement
output. A partial scene cannot yield a full weighted energy. Interval sums are
exact rational arithmetic on already archived bounds, without reintegration.
    """
    _require(type(cutoff_s) in (int, float) and math.isfinite(cutoff_s) and cutoff_s > 0,
             'POST_CUTOFF_REQUIRED')
    _, declaration = planning_instance(original, True)
    _require(evaluation.get('problem_id') == original['id'] and
             evaluation.get('evidence_identity') == {
                 'input_sha256': _digest(original), 'candidate_sha256': _digest(candidate)},
             'POST_IDENTITY_MISMATCH')
    raw_state = evaluation.get('state')
    _require(raw_state in ('SAFE', 'THERMAL_VIOLATION', 'UNRESOLVED', 'INVALID_SCHEDULE', 'INVALID_INPUT'),
             'POST_STATE_UNKNOWN')
    nodes = original['platform']['node_order']
    valid_low, valid_high = map(F, original['platform']['power_model_temperature_range_degC'])
    definitions = {scene['id']: scene for scene in original['scenarios']}
    receipts = evaluation.get('scenes', {})
    out = {'profile': PROFILE, 'raw_state': raw_state, 'state': raw_state,
           'common_80_C_feasible': None, 'complete_physical_evaluation': False,
           'diagnostic_weighted_energy_J': None, 'weighted_energy_components_J': {},
           'maximum_peak_degC': None, 'scene_peaks_degC': {},
           'energy_is_feasible_upper_bound': False, 'new_candidate_accepted': False,
           'new_physical_evaluations': 0, 'full_energy_unavailable_reason': None,
           'original_input_sha256': declaration['original_input_sha256'],
           'candidate_sha256': _digest(candidate)}
    violations = evaluation.get('violations', [])
    valid_witnesses = []
    for witness in violations:
        sid, node = witness.get('scene_id'), witness.get('node')
        if sid not in definitions or node not in nodes:
            continue
        low, high = _interval(witness['temperature_degC'])
        limit = F(definitions[sid]['maximum_temperature_degC'][nodes.index(node)])
        if (F(witness['limit_degC']) == limit and valid_low <= low <= high <= valid_high
                and low > limit and F(0) <= F(witness['time_s']) <= F(original['window_ms'])/1000
                and _timely(witness.get('formed_at_elapsed_s'), cutoff_s)):
            valid_witnesses.append(deepcopy(witness))
    out['timely_original_limit_violations'] = valid_witnesses
    if valid_witnesses:
        out['common_80_C_feasible'] = False
    elif raw_state == 'THERMAL_VIOLATION':
        out['state'] = 'UNRESOLVED'
    try:
        _require(evaluation.get('legality', {}).get('state') == 'SCHEDULE_VALID_THERMAL_UNCHECKED',
                 'COMPLETE_LEGALITY_REQUIRED')
        _require(set(receipts) == set(definitions), 'ALL_SCENES_REQUIRED')
        _require(sum(F(scene['weight']) for scene in definitions.values()) == 1
                 and all(F(scene['weight']) >= 0 for scene in definitions.values()), 'SCENE_WEIGHTS')
        total = [F(0), F(0)]
        parts = {name: [F(0), F(0)] for name in COMPONENTS}
        peak_pairs, all_safe = [], True
        for sid, scene in definitions.items():
            receipt = receipts[sid]
            _require(receipt.get('complete') is True and
                     F(receipt['covered_until_s']) == F(original['window_ms'])/1000 and
                     _timely(receipt.get('completed_at_elapsed_s'), cutoff_s), 'SCENE_INCOMPLETE_OR_LATE')
            _require(receipt.get('state') in ('SAFE', 'THERMAL_VIOLATION', 'UNRESOLVED')
                     and receipt.get('energy_accuracy_met') is True, 'SCENE_ENERGY_NOT_ACCURATE')
            _require(set(receipt['peaks_degC']) == set(receipt['minimum_degC']) == set(nodes),
                     'THERMAL_NODE_COVERAGE')
            peaks = {}
            for node in nodes:
                peak = _interval(receipt['peaks_degC'][node])
                minimum = _interval(receipt['minimum_degC'][node])
                _require(valid_low <= minimum[0] <= minimum[1] and peak[0] <= peak[1] <= valid_high,
                         'PHYSICAL_VALIDITY_NOT_CERTIFIED')
                peaks[node] = list(map(str, peak))
                peak_pairs.append(peak)
                all_safe = all_safe and peak[1] <= F(scene['maximum_temperature_degC'][nodes.index(node)])
            out['scene_peaks_degC'][sid] = peaks
            weight = F(scene['weight'])
            energy = _interval(receipt['energy_J'])
            _require(set(receipt['energy_components_J']) == set(COMPONENTS), 'ENERGY_COMPONENTS_REQUIRED')
            component_total = [F(0), F(0)]
            for name in COMPONENTS:
                pair = _interval(receipt['energy_components_J'][name])
                for i in (0, 1):
                    parts[name][i] += weight*pair[i]
                    component_total[i] += pair[i]
            _require(max(energy[0], component_total[0]) <= min(energy[1], component_total[1]),
                     'COMPONENT_ENERGY_CONFLICT')
            for i in (0, 1):
                total[i] += weight*energy[i]
        out.update(complete_physical_evaluation=True,
                   diagnostic_weighted_energy_J=list(map(str, total)),
                   weighted_energy_components_J={name: list(map(str, pair)) for name, pair in parts.items()},
                   maximum_peak_degC=[str(max(pair[i] for pair in peak_pairs)) for i in (0, 1)])
        if raw_state == 'SAFE':
            _require(all_safe and not valid_witnesses and evaluation.get('rankable_energy') is True
                     and _timely(evaluation.get('completed_at_elapsed_s'), cutoff_s), 'SAFE_ADMISSION')
            low, high = _interval(evaluation['weighted_energy_J'])
            _require(low <= total[0] <= total[1] <= high
                     and F(evaluation['safe_upper_bound_J']) == high, 'SAFE_AGGREGATE_IDENTITY')
            out.update(common_80_C_feasible=True, energy_is_feasible_upper_bound=True)
    except (ValueError, KeyError, TypeError, ArithmeticError) as error:
        out['full_energy_unavailable_reason'] = str(error)
        if not out['complete_physical_evaluation']:
            out.update(diagnostic_weighted_energy_J=None, weighted_energy_components_J={}, maximum_peak_degC=None)
        if raw_state == 'SAFE':
            out['state'] = 'UNRESOLVED'
    return out
