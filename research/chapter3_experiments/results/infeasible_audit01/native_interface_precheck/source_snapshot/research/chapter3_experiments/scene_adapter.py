"""Fixed-deployment, single-scene evaluation and guarded outer aggregation.

Scene views use objective weight one only to expose an *unweighted* interface.
The original weights are applied once, after every scene (including weight-zero
scenes) has a matching SAFE receipt.  Receipts belong to one shared Budget;
these hashes detect accidental mixing, not adversarially forged evidence.
No search, repair, deployment exclusion or optimum certificate is performed.
"""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import uuid

from schedules import validate_schedule
from start_domain import explicit_start_sets
from thermal import Budget, Exhausted, I, _accuracy, _energy_accuracy, _q, evaluate_piecewise

PROTOCOL = 'fixed-deployment-unweighted-scene-v1'


def canonical_hash(value):
    """Stable JSON identity; exact Fraction values retain their type."""
    def encode(item):
        if isinstance(item, Fraction):
            return {'__exact_fraction__': str(item)}
        raise TypeError('non-JSON identity value: ' + type(item).__name__)
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), default=encode, allow_nan=False).encode('utf-8')).hexdigest()


def _scenes(instance):
    items = instance['scenarios']
    result = {scene['id']: scene for scene in items}
    if not result or len(result) != len(items):
        raise ValueError('empty or duplicate scenario identities')
    return result


def validate_fixed_deployment(instance, fixed_deployment):
    """Validate a complete outer deployment, before any scene projection.

    Unused catalog stages are not outer decisions. Every Stage actually used
    anywhere in the instance must appear, with one legal specific unit.
    """
    if not isinstance(fixed_deployment, dict):
        raise ValueError('fixed deployment must be a dict')
    scenes = _scenes(instance)
    used = {stage['shared_stage_id'] for scene in scenes.values()
            for stage in scene['stage_instances']}
    if not used or set(fixed_deployment) != used:
        raise ValueError('fixed deployment must cover exactly all used shared Stages')
    units = {unit['id']: unit for unit in instance['platform']['units']}
    if len(units) != len(instance['platform']['units']):
        raise ValueError('duplicate execution unit identities')
    result = {}
    for shared_id in sorted(used):
        unit_id = fixed_deployment[shared_id]
        if not isinstance(unit_id, str) or unit_id not in units:
            raise ValueError('unknown fixed execution unit: ' + str(unit_id))
        modes = instance['stage_modes'][shared_id]
        legal = [mode for mode in modes if mode['unit_id'] == unit_id
                 and mode['shared_stage_id'] == shared_id]
        if not legal:
            raise ValueError('illegal fixed deployment for ' + shared_id)
        result[shared_id] = unit_id
    return result


def make_scene_instance(instance, scene_id, *, unweighted=True):
    """Deep-copy one scene; retain every physical node, domain and legal mode.

    Mapping filtering is deliberately a separate builder responsibility. The
    view does not create a new physical workload or delete unused-device heat.
    """
    scene = _scenes(instance).get(scene_id)
    if scene is None:
        raise ValueError('unknown scene: ' + str(scene_id))
    explicit_start_sets(instance)  # Validate complete source identity before projection.
    out = deepcopy(instance)
    out['scenarios'] = [deepcopy(scene)]
    if 'start_domain' in out:
        out['start_domain']['by_scene_stage_ms'] = {
            scene_id: deepcopy(instance['start_domain']['by_scene_stage_ms'][scene_id])}
    if unweighted:
        out['scenarios'][0]['weight'] = '1'
    used = {stage['shared_stage_id'] for stage in scene['stage_instances']}
    out['stage_modes'] = {key: deepcopy(instance['stage_modes'][key]) for key in sorted(used)}
    return out


def _budget_identity(budget):
    # One unpredictable token per object, rather than a reusable memory address.
    # Snapshot it once: deterministic expiry hooks may shorten the live budget,
    # which must not invalidate already committed evidence from this invocation.
    if not hasattr(budget, '_scene_adapter_budget_identity'):
        budget._scene_adapter_budget_identity = {
            'token': uuid.uuid4().hex, 'start': repr(budget.start),
            'seconds': repr(budget.seconds), 'panel_limit': budget.panel_limit,
            'refinement_limit': budget.refinement_limit}
    return deepcopy(budget._scene_adapter_budget_identity)


def _source_identity():
    folder = Path(__file__).resolve().parent
    sources = [Path(__file__), folder / 'schedules.py', folder / 'thermal.py',
               folder / 'start_domain.py', folder.parent / 'v1_evaluator' / 'interval.py']
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}


def _identity(instance, scene_id, deployment, candidate, accuracy, budget):
    scene = _scenes(instance)[scene_id]
    return {'protocol': PROTOCOL, 'full_input_sha256': canonical_hash(instance),
            'fixed_deployment_sha256': canonical_hash(deployment),
            'scenario_id': scene_id, 'scenario_sha256': canonical_hash(scene),
            'entry_sha256': canonical_hash(scene['entry']),
            'platform_sha256': canonical_hash(instance['platform']),
            'execution_rules_sha256': canonical_hash(instance['execution_rules']),
            'accuracy_sha256': canonical_hash(accuracy),
            'candidate_sha256': canonical_hash(candidate),
            'source_sha256': _source_identity(), 'budget': _budget_identity(budget)}


def _receipt_hash(receipt):
    return canonical_hash({key: value for key, value in receipt.items()
                           if key != 'receipt_sha256'})


def evaluate_scene(instance, scene_id, fixed_deployment, candidate, accuracy=None, budget=None):
    """Validate and continuously evaluate one complete fixed-deployment scene.

    Use the same explicitly supplied Budget for all scene calls and the later
    aggregation. A failed arrangement says nothing about other arrangements of
    its deployment; no deployment-infeasible field is produced.
    """
    budget = Budget() if budget is None else budget
    out = {'protocol': PROTOCOL, 'state': 'UNRESOLVED', 'reason': None,
           'scenario_id': scene_id, 'identity': None, 'legality': None, 'result': None,
           'violations': [], 'energy_J': None, 'safe_upper_bound_J': None,
           'rankable_energy': False, 'unweighted': True,
           'deployment_feasibility': 'NOT_DECIDED', 'formal_experiment_result': False}
    try:
        budget.check()
        original, supplied = deepcopy(instance), deepcopy(candidate)
        deployment = validate_fixed_deployment(original, fixed_deployment)
        requested_accuracy = _accuracy(accuracy)
        out['identity'] = _identity(original, scene_id, deployment, supplied,
                                    requested_accuracy, budget)
        view = make_scene_instance(original, scene_id)
        checked = validate_schedule(view, supplied)
        out['legality'] = checked
        if checked['state'] != 'SCHEDULE_VALID_THERMAL_UNCHECKED':
            out.update(state='INVALID_SCHEDULE', reason=checked['reason'])
        elif any(deployment[key] != unit for key, unit in checked['shared_deployment'].items()):
            out.update(state='INVALID_SCHEDULE', reason='FIXED_DEPLOYMENT_MISMATCH')
        else:
            budget.check()
            scene = view['scenarios'][0]
            result = evaluate_piecewise(view['platform'], scene['entry']['temperature_degC'],
                scene['maximum_temperature_degC'], checked['scenes'][scene_id]['segments'],
                view['window_ms'], requested_accuracy, budget, scene_id=scene_id)
            # Transfer committed evidence before any outer expiry check.
            out['result'] = result
            out['violations'] = deepcopy(result['violations'])
            budget.check()
            if out['violations']:
                out.update(state='THERMAL_VIOLATION', reason='POINT_WITNESS')
            elif result['state'] == 'SAFE' and result['complete']:
                budget.mark('before_scene_adapter_commit')
                completed_at = budget.elapsed
                if completed_at >= budget.seconds:
                    raise Exhausted('wall_time_limit')
                out.update(state='SAFE', reason='COMPLETE_CONTINUOUS_ENCLOSURE',
                    energy_J=deepcopy(result['energy_J']),
                    safe_upper_bound_J=str(I(*result['energy_J']).hi), rankable_energy=True,
                    completed_at_elapsed_s=completed_at)
            else:
                out.update(state=result['state'], reason=result['reason'])
    except Exhausted as error:
        out.update(state='THERMAL_VIOLATION' if out['violations'] else 'UNRESOLVED',
                   reason=str(error), budget_exhausted=True)
    except MemoryError:
        out.update(state='THERMAL_VIOLATION' if out['violations'] else 'UNRESOLVED',
                   reason='RESOURCE_LIMIT')
    except ArithmeticError as error:
        out.update(state='THERMAL_VIOLATION' if out['violations'] else 'UNRESOLVED',
                   reason='NUMERICAL_ERROR', error_type=type(error).__name__, error_details=str(error))
    except (KeyError, TypeError, ValueError) as error:
        out.update(state='THERMAL_VIOLATION' if out['violations'] else 'INVALID_INPUT',
                   reason=str(error), error_type=type(error).__name__)
    out.update(elapsed_s=budget.elapsed, panels=budget.panels, refinements=budget.refinements)
    out['receipt_sha256'] = _receipt_hash(out)
    return out


def aggregate_scene_receipts(instance, fixed_deployment, receipts, candidates,
                             accuracy=None, budget=None):
    """Apply original weights only to complete matching budget-local SAFE receipts.

    Already committed violations survive expiry at entry. Existing per-scene
    SAFE receipts remain visible after expiry, but no new global U is accepted.
    No solver bound, optimality or deployment exclusion is inferred here.
    """
    budget = Budget() if budget is None else budget
    out = {'protocol': PROTOCOL, 'state': 'UNRESOLVED', 'reason': None,
           'problem_id': instance.get('id'), 'scenes': {}, 'violations': [],
           'receipt_errors': {}, 'weighted_energy_J': None, 'safe_upper_bound_J': None,
           'rankable_energy': False, 'deployment_feasibility': 'NOT_DECIDED',
           'formal_experiment_result': False}
    try:
        original = deepcopy(instance)
        deployment = validate_fixed_deployment(original, fixed_deployment)
        requested_accuracy = _accuracy(accuracy)
        scenes = _scenes(original)
        weights = {sid: _q(scene['weight']) for sid, scene in scenes.items()}
        if any(weight < 0 for weight in weights.values()) or sum(weights.values()) != 1:
            raise ValueError('scenario weights must be nonnegative and sum to one')
        if not isinstance(receipts, dict) or not isinstance(candidates, dict):
            raise ValueError('receipts and candidates must be scenario dictionaries')
        if set(receipts) - set(scenes) or set(candidates) != set(scenes):
            raise ValueError('candidate or receipt scene identities do not match full input')
        # Matching existing evidence may be transferred even after the deadline.
        for scene_id in scenes:
            receipt = receipts.get(scene_id)
            if receipt is None:
                out['receipt_errors'][scene_id] = 'MISSING_SCENE_RECEIPT'
                continue
            expected = _identity(original, scene_id, deployment, candidates[scene_id],
                                 requested_accuracy, budget)
            if not isinstance(receipt, dict) or receipt.get('identity') != expected:
                out['receipt_errors'][scene_id] = 'RECEIPT_IDENTITY_MISMATCH'
                continue
            if receipt.get('receipt_sha256') != _receipt_hash(receipt):
                out['receipt_errors'][scene_id] = 'RECEIPT_PAYLOAD_MISMATCH'
                continue
            out['scenes'][scene_id] = deepcopy(receipt)
            out['violations'].extend(deepcopy(receipt.get('violations', [])))
        budget.check()
        if out['violations']:
            out.update(state='THERMAL_VIOLATION', reason='MATCHING_POINT_WITNESS')
        elif out['receipt_errors']:
            out.update(state='UNRESOLVED', reason='NOT_ALL_RECEIPTS_MATCH')
        elif any(receipt['state'] != 'SAFE' or not receipt['rankable_energy']
                 for receipt in out['scenes'].values()):
            out.update(state='UNRESOLVED', reason='NOT_ALL_SCENES_COMPLETE_AND_SAFE')
        else:
            total = I(0)
            for scene_id, receipt in out['scenes'].items():
                result = receipt['result']
                if (result['state'] != 'SAFE' or not result['complete']
                    or result['scene_id'] != scene_id
                    or _q(result['covered_until_s']) != _q(original['window_ms']) / 1000
                    or result['energy_J'] != receipt['energy_J']
                    or not result['energy_accuracy_met']
                    or str(I(*result['energy_J']).hi) != receipt['safe_upper_bound_J']
                    or receipt['completed_at_elapsed_s'] >= budget.seconds):
                    raise ValueError('inconsistent SAFE scene receipt')
                total += I(*receipt['energy_J']) * I.rational(weights[scene_id])
            if not _energy_accuracy(total, requested_accuracy):
                out['reason'] = 'WEIGHTED_ENERGY_ERROR_TARGET'
            else:
                budget.mark('before_scene_aggregate_commit')
                completed_at = budget.elapsed
                if completed_at >= budget.seconds:
                    raise Exhausted('wall_time_limit')
                out.update(state='SAFE', reason='ALL_MATCHING_SCENES_COMPLETE_AND_SAFE',
                    weighted_energy_J=total.data(), safe_upper_bound_J=str(total.hi),
                    rankable_energy=True, completed_at_elapsed_s=completed_at,
                    fixed_deployment_sha256=canonical_hash(deployment),
                    deployment_feasibility='ALL_SCENES_SAFE_WITNESS')
    except Exhausted as error:
        out.update(state='THERMAL_VIOLATION' if out['violations'] else 'UNRESOLVED',
                   reason=str(error), budget_exhausted=True)
    except MemoryError:
        out.update(state='THERMAL_VIOLATION' if out['violations'] else 'UNRESOLVED',
                   reason='RESOURCE_LIMIT')
    except ArithmeticError as error:
        out.update(state='THERMAL_VIOLATION' if out['violations'] else 'UNRESOLVED',
                   reason='NUMERICAL_ERROR', error_type=type(error).__name__, error_details=str(error))
    except (KeyError, TypeError, ValueError) as error:
        out.update(state='THERMAL_VIOLATION' if out['violations'] else 'INVALID_INPUT',
                   reason=str(error), error_type=type(error).__name__)
    out.update(elapsed_s=budget.elapsed, panels=budget.panels, refinements=budget.refinements)
    return out
