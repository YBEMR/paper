"""K194 receipt admission only; no propagation, integration or optimization.

The caller binds the immutable input/manifest/receipt files.  This module
rechecks exact one-scene schedule identity and validates *already formed*
continuous-kernel evidence.  Late delivery does not erase timely evidence;
late completion cannot create a usable energy bound.
"""
from copy import deepcopy
from fractions import Fraction as Q
import math
from pathlib import Path
import sys

PRODUCTION = Path(__file__).resolve().parent.parent
if str(PRODUCTION) not in sys.path:
    sys.path.insert(0, str(PRODUCTION))
from schedules import validate_schedule

TECHNICAL_REASONS = {
    'RESOURCE_LIMIT', 'INTERNAL_CONSISTENCY_ERROR', 'NUMERICAL_ERROR',
    'INVALID_INPUT', 'INVALID_SCHEDULE', 'MemoryError', 'ArithmeticError',
}
NORMAL_REASONS = {
    None, 'wall_time_limit', 'panel_limit', 'peak_refinement_limit',
    'POWER_MODEL_RANGE_UNRESOLVED', 'ENERGY_ERROR_TARGET',
    'TEMPERATURE_LIMIT_UNRESOLVED', 'NOT_ALL_SCENES_COMPLETE_AND_SAFE',
    'WEIGHTED_ENERGY_ERROR_TARGET', 'POINT_WITNESS',
    'COMPLETE_CONTINUOUS_ENCLOSURE', 'ALL_SCENES_COMPLETE_AND_SAFE',
}
ALLOWED_STATES = {'SAFE', 'UNRESOLVED', 'THERMAL_VIOLATION',
                  'INVALID_INPUT', 'INVALID_SCHEDULE'}


def scene_view(instance, scene_id):
    """Physical input unchanged; isolate a scene with unit accounting weight."""
    matches = [s for s in instance['scenarios'] if s['id'] == scene_id]
    if len(matches) != 1:
        raise ValueError('SCENE_IDENTITY_MISMATCH')
    view = deepcopy(instance)
    view['scenarios'] = [deepcopy(matches[0])]
    view['scenarios'][0]['weight'] = '1'
    if 'start_domain' in view:
        view['start_domain']['by_scene_stage_ms'] = {
            scene_id: deepcopy(instance['start_domain']['by_scene_stage_ms'][scene_id])}
    return view


def _exact(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, Q)):
        raise ValueError('NONEXACT_PHYSICAL_SCALAR')
    return Q(value)


def _clock(value):
    if isinstance(value, bool):
        raise ValueError('INVALID_CLOCK')
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError('INVALID_CLOCK')
        return Q.from_float(value)
    return _exact(value)


def _interval(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError('INVALID_INTERVAL')
    lo, hi = map(_exact, value)
    if hi < lo:
        raise ValueError('REVERSED_INTERVAL')
    return lo, hi


def _overlap(a, b):
    return max(a[0], b[0]) <= min(a[1], b[1])


def _sum_intervals(values):
    return sum((v[0] for v in values), Q(0)), sum((v[1] for v in values), Q(0))


def _formed_timely(elapsed, start, deadline):
    elapsed = _clock(elapsed)
    if elapsed < 0:
        raise ValueError('NEGATIVE_FORMATION_TIME')
    return start + elapsed < deadline


def _technical(receipt):
    return (receipt.get('state') in {'INVALID_INPUT', 'INVALID_SCHEDULE'} or
            receipt.get('reason') in TECHNICAL_REASONS or
            receipt.get('error_type') is not None or
            receipt.get('reason') not in NORMAL_REASONS or
            receipt.get('state') not in ALLOWED_STATES)


def _safe_energy(scene, nodes, limits, valid, window_s, accuracy):
    if not (scene.get('state') == 'SAFE' and scene.get('complete') is True and
            scene.get('rankable_energy') is True and
            scene.get('energy_accuracy_met') is True and
            _exact(scene['covered_until_s']) == window_s):
        raise ValueError('SAFE_NOT_COMPLETE_AND_RANKABLE')
    tol = _exact(accuracy['temperature_enclosure_width_K'])
    for field in ('peaks_degC', 'minimum_degC', 'final_temperature_degC'):
        if set(scene[field]) != set(nodes):
            raise ValueError('THERMAL_NODE_IDENTITY_MISMATCH')
    for node, limit in zip(nodes, limits):
        peak = _interval(scene['peaks_degC'][node])
        minimum = _interval(scene['minimum_degC'][node])
        final = _interval(scene['final_temperature_degC'][node])
        if (minimum[0] < valid[0] or peak[1] > valid[1] or
                peak[1] > limit or minimum[0] > peak[0] or
                final[0] < minimum[0] or final[1] > peak[1] or
                any(v[1]-v[0] > tol for v in (peak, minimum, final))):
            raise ValueError('INVALID_SAFE_THERMAL_ENCLOSURE')
    energy = _interval(scene['energy_J'])
    allowed = max(_exact(accuracy['energy_absolute_error_J']),
                  _exact(accuracy['energy_relative_error'])*max(Q(0), energy[0]))
    if energy[0] < 0 or energy[1]-energy[0] > allowed:
        raise ValueError('ENERGY_ACCURACY_MISMATCH')
    conservation = _interval(scene['conservation_energy_J'])
    parts = scene['energy_components_J']
    if set(parts) != {'baseline', 'activity', 'external_common', 'temperature_correction'}:
        raise ValueError('ENERGY_COMPONENT_IDENTITIES')
    component_intervals = {k: _interval(v) for k, v in parts.items()}
    if any(component_intervals[k][0] < 0 for k in ('baseline', 'activity', 'external_common')):
        raise ValueError('NEGATIVE_NONNEGATIVE_ENERGY_COMPONENT')
    node_energy = scene['node_injected_energy_J']
    if set(node_energy) != set(nodes):
        raise ValueError('ENERGY_NODE_IDENTITY_MISMATCH')
    node_intervals = [_interval(node_energy[n]) for n in nodes]
    if any(v[0] < 0 for v in node_intervals):
        raise ValueError('NEGATIVE_NODE_ENERGY')
    accounting = _sum_intervals(node_intervals + [component_intervals['external_common']])
    summed = _sum_intervals(component_intervals.values())
    if any(not _overlap(energy, other) for other in (conservation, accounting, summed)):
        raise ValueError('ENERGY_CONSERVATION_MISMATCH')
    return [str(energy[0]), str(energy[1])]


def admit(instance, entry, raw_receipt, call_start, call_deadline,
          root_deadline, accuracy):
    """Return admitted scene state and a separate technical-stop flag.

    A verified timely point violation wins over outer timeout, while a later
    technical error is still exposed through ``technical_stop``.  Physical
    formation timestamps are relative to the evaluator budget's start, which
    must be the caller-supplied ``call_start`` (not a prior wrapper timestamp).
    """
    out = {'state': 'TECHNICAL_UNRESOLVED', 'energy_J': None,
           'reason': None, 'technical_stop': True, 'timely_violations': [],
           'late_violation_count': 0, 'safe_completed_before_deadline': False}
    try:
        start = _clock(call_start)
        deadline = min(_clock(call_deadline), _clock(root_deadline))
        if deadline <= start:
            raise ValueError('INVALID_CALL_DEADLINE')
        if any(_exact(accuracy[k]) <= 0 for k in (
                'temperature_enclosure_width_K', 'energy_absolute_error_J', 'energy_relative_error')):
            raise ValueError('INVALID_ACCURACY')
        sid = entry['scene_id']
        view = scene_view(instance, sid)
        checked = validate_schedule(view, entry['candidate'])
        if checked['state'] != 'SCHEDULE_VALID_THERMAL_UNCHECKED':
            raise ValueError('FROZEN_CANDIDATE_NOT_LEGAL')
        if 'shared_A_device' in entry and checked['shared_deployment']['A.main'] != entry['shared_A_device']:
            raise ValueError('SHARED_DEPLOYMENT_IDENTITY_MISMATCH')
        if not isinstance(raw_receipt, dict):
            raise ValueError('RECEIPT_NOT_OBJECT')
        if raw_receipt.get('problem_id') != view['id']:
            raise ValueError('RECEIPT_INPUT_OR_LEGALITY_IDENTITY_MISMATCH')
        if raw_receipt.get('numerical_protocol') != 'directed-decimal60-taylor18-scaled100-v1':
            raise ValueError('CONTINUOUS_KERNEL_PROTOCOL_MISMATCH')
        # An outer deadline can occur before the common checker commits its
        # result.  There is then no usable evidence, but no numerical fault.
        if ('legality' not in raw_receipt and raw_receipt.get('state') == 'UNRESOLVED'
                and raw_receipt.get('reason') == 'wall_time_limit'
                and not raw_receipt.get('scenes') and not raw_receipt.get('violations')):
            out.update(state='UNRESOLVED', reason='TIMEOUT_BEFORE_LEGALITY_COMMIT', technical_stop=False)
            return out
        if raw_receipt.get('legality') != checked:
            raise ValueError('RECEIPT_INPUT_OR_LEGALITY_IDENTITY_MISMATCH')
        raw_scenes = raw_receipt.get('scenes', {})
        if not isinstance(raw_scenes, dict) or set(raw_scenes) - {sid}:
            raise ValueError('RECEIPT_SCENE_IDENTITY_MISMATCH')
        scene = raw_scenes.get(sid)
        technical = _technical(raw_receipt)
        if scene is None:
            if raw_receipt.get('violations'):
                raise ValueError('UNBOUND_OUTER_VIOLATIONS')
            out.update(state='TECHNICAL_UNRESOLVED' if technical else 'UNRESOLVED',
                       reason=raw_receipt.get('reason') or 'NO_SCENE_RECEIPT', technical_stop=technical)
            return out
        if not isinstance(scene, dict) or scene.get('scene_id') != sid:
            raise ValueError('INNER_SCENE_IDENTITY_MISMATCH')
        technical = technical or _technical(scene)
        nodes = view['platform']['node_order']
        if len(nodes) != 4:
            raise ValueError('EXPECTED_FOUR_THERMAL_NODES')
        definition = view['scenarios'][0]
        limits = list(map(_exact, definition['maximum_temperature_degC']))
        valid = list(map(_exact, view['platform']['power_model_temperature_range_degC']))
        if len(limits) != len(nodes) or len(valid) != 2 or valid[0] >= valid[1]:
            raise ValueError('INVALID_THERMAL_LIMIT_OR_RANGE_DIMENSIONS')
        window_s = _exact(view['window_ms']) / 1000
        witnesses = scene.get('violations', [])
        if not isinstance(witnesses, list):
            raise ValueError('INVALID_VIOLATION_COLLECTION')
        # The production wrapper copies the same inner point witnesses.  It
        # may timeout before aggregation but cannot legitimately change them.
        if raw_receipt.get('violations', []) != witnesses:
            raise ValueError('INNER_OUTER_VIOLATION_MISMATCH')
        for witness in witnesses:
            if not isinstance(witness, dict) or witness.get('scene_id') != sid or witness.get('node') not in nodes:
                raise ValueError('VIOLATION_IDENTITY_MISMATCH')
            node_index = nodes.index(witness['node'])
            point = _interval(witness['temperature_degC'])
            when = _exact(witness['time_s'])
            if (_exact(witness['limit_degC']) != limits[node_index] or
                    when < 0 or when > window_s or
                    point[0] <= limits[node_index] or
                    point[0] < valid[0] or point[1] > valid[1]):
                raise ValueError('INVALID_STRICT_POINT_WITNESS')
            if _formed_timely(witness['formed_at_elapsed_s'], start, deadline):
                out['timely_violations'].append(deepcopy(witness))
            else:
                out['late_violation_count'] += 1
        if out['timely_violations']:
            out.update(state='VIOLATION', reason='TIMELY_STRICT_POINT_WITNESS',
                       technical_stop=technical)
            if technical:
                out['technical_reason'] = scene.get('reason') or raw_receipt.get('reason')
            return out
        if witnesses:
            out.update(state='UNRESOLVED', reason='NO_TIMELY_POINT_WITNESS',
                       technical_stop=technical)
            return out
        if (scene.get('state') == 'THERMAL_VIOLATION' or
                raw_receipt.get('state') == 'THERMAL_VIOLATION'):
            raise ValueError('VIOLATION_STATE_WITHOUT_POINT_WITNESS')
        if technical:
            out.update(reason=scene.get('reason') or raw_receipt.get('reason'))
            return out
        if scene.get('state') != 'SAFE':
            out.update(state='UNRESOLVED', reason=scene.get('reason') or 'NO_COMPLETE_SAFE_SCENE',
                       technical_stop=False)
            return out
        energy = _safe_energy(scene, nodes, limits, valid, window_s, accuracy)
        if not _formed_timely(scene['completed_at_elapsed_s'], start, deadline):
            out.update(state='UNRESOLVED', reason='SAFE_FORMED_AFTER_DEADLINE',
                       technical_stop=False)
            return out
        out.update(state='SAFE', reason='TIMELY_COMPLETE_CONTINUOUS_SCENE',
                   energy_J=energy, technical_stop=False,
                   safe_completed_before_deadline=True)
        return out
    except (KeyError, TypeError, ValueError, ArithmeticError, MemoryError) as error:
        out.update(reason=str(error) or type(error).__name__, error_type=type(error).__name__)
        # Never erase earlier independently validated point evidence.
        if out['timely_violations']:
            out['state'] = 'VIOLATION'
        return out
