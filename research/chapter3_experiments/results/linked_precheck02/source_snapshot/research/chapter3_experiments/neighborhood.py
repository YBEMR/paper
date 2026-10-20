"""Budget-local N1 conditions on an existing complete SAFE witness.

N1 fixes every execution unit, and fixes OPP/start for closed Stage instances.
Only explicitly opened scene-local instances keep their original legal OPPs
and starts. This module does not evaluate heat, propagate starts, generate a
candidate, prune by energy, or assert global/neighborhood optimality. Receipt
identities detect accidental mixing; they are not anti-forgery certificates.
"""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

from scene_adapter import (PARTIAL_PROTOCOL, canonical_hash, _budget_identity,
    _partial_identity, _partial_scene_energy, _receipt_hash, _scenes,
    make_scene_instance, shared_deployment_ids, validate_shared_deployment)
from schedules import validate_schedule
from thermal import I, _accuracy, _q

PROTOCOL = 'fixed-unit-local-opp-start-n1-v1'
_FIELDS = {'protocol', 'source_input_sha256', 'shared_deployment', 'accuracy',
    'seed_candidate', 'seed_receipt', 'seed_candidate_sha256',
    'seed_receipt_sha256', 'budget_identity', 'evaluator_source_sha256',
    'condition_source_sha256', 'opened_by_scene', 'seed_options_by_scene',
    'condition_sha256'}


def _json_copy(value):
    """Persist ordinary JSON values; no float conversion of exact times."""
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as error:
        raise ValueError('N1 archived input must use ordinary JSON scalars') from error


def _source_hash():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _condition_hash(value):
    return canonical_hash({k: v for k, v in value.items() if k != 'condition_sha256'})


def _formed_before_deadline(value, budget):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and 0 <= value < budget.seconds
            and value <= budget.elapsed)


def _checked_seed(instance, deployment, candidate, budget):
    budget.check()
    if (not isinstance(candidate, dict) or set(candidate) != {'scenes'}
            or not isinstance(candidate['scenes'], dict)
            or set(candidate['scenes']) != set(_scenes(instance))):
        raise ValueError('N1 seed must cover exactly every original scene')
    checked = validate_schedule(instance, candidate)
    budget.check()
    if checked['state'] != 'SCHEDULE_VALID_THERMAL_UNCHECKED':
        raise ValueError('N1 seed is structurally illegal: '+str(checked['reason']))
    if any(checked['shared_deployment'].get(key) != unit
           for key, unit in deployment.items()):
        raise ValueError('N1 seed does not match shared deployment')
    return checked


def _validate_seed_receipt(instance, deployment, candidate, receipt, accuracy, budget):
    """Recheck saved evidence identities/completeness, without physical work."""
    checked = _checked_seed(instance, deployment, candidate, budget)
    expected = _partial_identity(instance, deployment, accuracy, budget,
        candidate=candidate, local_deployment=checked['shared_deployment'])
    scenes = _scenes(instance)
    if (not isinstance(receipt, dict) or receipt.get('protocol') != PARTIAL_PROTOCOL
            or receipt.get('state') != 'SAFE' or receipt.get('rankable_energy') is not True
            or receipt.get('safe_candidate') != candidate
            or receipt.get('identity') != expected
            or receipt.get('shared_deployment') != deployment
            or receipt.get('shared_stage_ids') != shared_deployment_ids(instance)
            or receipt.get('merged_deployment') != checked['shared_deployment']
            or receipt.get('legality') != checked
            or receipt.get('receipt_errors') != {} or receipt.get('violations') != []
            or receipt.get('deployment_feasibility') != 'ALL_SCENES_SAFE_WITNESS'
            or receipt.get('receipt_sha256') != _receipt_hash(receipt)
            or not _formed_before_deadline(receipt.get('completed_at_elapsed_s'), budget)
            or not isinstance(receipt.get('scenes'), dict)
            or set(receipt['scenes']) != set(scenes)):
        raise ValueError('N1 requires a complete matching budget-local aggregate SAFE receipt')
    total = I(0)
    weights = {sid: _q(scene['weight']) for sid, scene in scenes.items()}
    if any(w < 0 for w in weights.values()) or sum(weights.values()) != 1:
        raise ValueError('invalid original scenario weights')
    for sid in scenes:
        budget.check()
        local_candidate = {'scenes': {sid: candidate['scenes'][sid]}}
        local = {stage['shared_stage_id']: row['unit']
                 for stage in scenes[sid]['stage_instances']
                 for row in candidate['scenes'][sid] if row['stage_id'] == stage['id']}
        local = {key: local[key] for key in sorted(local)}
        expected_local = _partial_identity(instance, deployment, accuracy, budget,
            scene_id=sid, candidate=local_candidate, local_deployment=local)
        part = receipt['scenes'][sid]
        if (not isinstance(part, dict) or part.get('protocol') != PARTIAL_PROTOCOL
                or part.get('state') != 'SAFE' or part.get('rankable_energy') is not True
                or part.get('identity') != expected_local
                or part.get('scenario_id') != sid or part.get('unweighted') is not True
                or part.get('shared_deployment') != deployment
                or part.get('shared_stage_ids') != shared_deployment_ids(instance)
                or part.get('local_deployment') != local or part.get('violations') != []
                or part.get('receipt_sha256') != _receipt_hash(part)
                or part.get('legality', {}).get('scenes', {}).get(sid) != checked['scenes'][sid]
                or not _formed_before_deadline(part.get('completed_at_elapsed_s'), budget)):
            raise ValueError('N1 seed scene receipt does not match original full input')
        total += _partial_scene_energy(instance, sid, part, budget)*I.rational(weights[sid])
    if (receipt.get('weighted_energy_J') != total.data()
            or receipt.get('safe_upper_bound_J') != str(total.hi)):
        raise ValueError('N1 aggregate energy is inconsistent with saved scene receipts')
    budget.check()
    return checked


def _opened(instance, opened, budget):
    scenes = _scenes(instance)
    if not isinstance(opened, dict) or set(opened) != set(scenes):
        raise ValueError('N1 opened mapping must cover exactly every original scene')
    shared = set(shared_deployment_ids(instance))
    normalized = {}
    for sid, scene in scenes.items():
        budget.check()
        values = opened[sid]
        stages = {stage['id']: stage for stage in scene['stage_instances']}
        if (not isinstance(values, list) or any(not isinstance(v, str) for v in values)
                or len(values) != len(set(values)) or set(values)-set(stages)):
            raise ValueError('N1 opened Stage identities must be unique legal instance ids')
        if any(stages[v]['shared_stage_id'] in shared for v in values):
            raise ValueError('N1 may open only scene-local Stage instances')
        normalized[sid] = sorted(values)
    return normalized


def _seed_options(candidate):
    return {sid: {row['stage_id']: {'unit': row['unit'], 'opp': row['opp'],
                    'start_ms': str(_q(row['start_ms']))}
                  for row in rows} for sid, rows in candidate['scenes'].items()}


def make_n1_condition(instance, shared_deployment, seed_candidate, seed_receipt,
                      open_stage_ids_by_scene, *, budget, accuracy=None):
    """Declare a restricted local domain from this call's verified SAFE seed."""
    budget.check()
    deployment = validate_shared_deployment(instance, shared_deployment)
    candidate, receipt = _json_copy(seed_candidate), _json_copy(seed_receipt)
    requested = _json_copy(_accuracy(accuracy))
    _validate_seed_receipt(instance, deployment, candidate, receipt, requested, budget)
    opened = _opened(instance, open_stage_ids_by_scene, budget)
    out = {'protocol': PROTOCOL, 'source_input_sha256': canonical_hash(instance),
        'shared_deployment': deployment, 'accuracy': requested,
        'seed_candidate': candidate, 'seed_receipt': receipt,
        'seed_candidate_sha256': canonical_hash(candidate),
        'seed_receipt_sha256': receipt['receipt_sha256'],
        'budget_identity': _budget_identity(budget),
        'evaluator_source_sha256': deepcopy(receipt['identity']['source_sha256']),
        'condition_source_sha256': _source_hash(), 'opened_by_scene': opened,
        'seed_options_by_scene': _seed_options(candidate)}
    out['condition_sha256'] = _condition_hash(out)
    budget.check()
    return out


def validate_n1_condition(instance, condition, *, budget, shared_deployment=None):
    """Reject changed inputs, seed evidence, source files or Budget identities."""
    budget.check()
    if (not isinstance(condition, dict) or set(condition) != _FIELDS
            or condition.get('protocol') != PROTOCOL
            or condition.get('condition_sha256') != _condition_hash(condition)):
        raise ValueError('invalid or modified N1 condition')
    out = _json_copy(condition)
    deployment = validate_shared_deployment(instance, out['shared_deployment'])
    if shared_deployment is not None and deployment != validate_shared_deployment(
            instance, shared_deployment):
        raise ValueError('N1 shared deployment condition mismatch')
    if (out['source_input_sha256'] != canonical_hash(instance)
            or out['budget_identity'] != _budget_identity(budget)
            or out['condition_source_sha256'] != _source_hash()
            or out['accuracy'] != _accuracy(out['accuracy'])
            or out['seed_candidate_sha256'] != canonical_hash(out['seed_candidate'])
            or out['seed_receipt_sha256'] != out['seed_receipt'].get('receipt_sha256')):
        raise ValueError('N1 input, Budget, source or seed identity mismatch')
    _validate_seed_receipt(instance, deployment, out['seed_candidate'], out['seed_receipt'],
                           out['accuracy'], budget)
    if (out['evaluator_source_sha256'] != out['seed_receipt']['identity']['source_sha256']
            or out['opened_by_scene'] != _opened(instance, out['opened_by_scene'], budget)
            or out['seed_options_by_scene'] != _seed_options(out['seed_candidate'])):
        raise ValueError('N1 derived conditions do not match seed evidence')
    budget.check()
    return out


def _member(condition, sid, stage_id, unit, opp, start):
    try:
        fixed = condition['seed_options_by_scene'][sid][stage_id]
    except (KeyError, TypeError) as error:
        raise ValueError('unknown N1 scene/Stage identity') from error
    if unit != fixed['unit']:
        return False
    if stage_id in condition['opened_by_scene'][sid]:
        return True
    return opp == fixed['opp'] and _q(start) == _q(fixed['start_ms'])


def filter_n1_options(instance, condition, options, *, budget):
    """Order-preserving intersection with N1; no option or physics is changed."""
    condition = validate_n1_condition(instance, condition, budget=budget)
    counts = {sid: {stage: {'before': 0, 'after': 0}
                   for stage in by_stage}
              for sid, by_stage in condition['seed_options_by_scene'].items()}
    kept, before = [], 0
    for option in options:
        budget.check()
        if not isinstance(option, dict):
            raise ValueError('N1 option must be a dict')
        sid, stage_id = option['scenario_id'], option['stage_instance_id']
        try:
            count = counts[sid][stage_id]
        except (KeyError, TypeError) as error:
            raise ValueError('unknown N1 option scene/Stage identity') from error
        before += 1
        count['before'] += 1
        # expand_options owns original-mode/start legality. This intersection
        # changes neither those fields nor the order and identities of objects.
        if _member(condition, sid, stage_id, option['unit_id'], option['opp_id'], option['start_ms']):
            kept.append(option)
            count['after'] += 1
    budget.check()
    return kept, {'before': before, 'after': len(kept), 'removed': before-len(kept),
                  'by_scene_stage': counts, 'complete': True,
                  'condition_sha256': condition['condition_sha256']}


def check_n1_candidate(instance, condition, candidate, *, budget, scene_id=None):
    """Check original legality and N1 membership, never modify fixed starts."""
    condition = validate_n1_condition(instance, condition, budget=budget)
    scenes = _scenes(instance)
    expected = set(scenes) if scene_id is None else {scene_id}
    if (scene_id is not None and scene_id not in scenes
            or not isinstance(candidate, dict) or set(candidate) != {'scenes'}
            or not isinstance(candidate['scenes'], dict)
            or set(candidate['scenes']) != expected):
        raise ValueError('N1 candidate must contain all original scenes or exactly its explicit scene')
    view = instance if scene_id is None else make_scene_instance(instance, scene_id)
    checked = validate_schedule(view, candidate)
    budget.check()
    if checked['state'] != 'SCHEDULE_VALID_THERMAL_UNCHECKED':
        raise ValueError('original schedule is illegal: '+str(checked['reason']))
    for sid, rows in candidate['scenes'].items():
        for row in rows:
            budget.check()
            if not _member(condition, sid, row['stage_id'], row['unit'], row['opp'], row['start_ms']):
                raise ValueError('candidate lies outside N1 condition: '+sid+'/'+row['stage_id'])
    budget.check()
    return {'state': 'N1_MEMBER_SCHEDULE_VALID_THERMAL_UNCHECKED',
        'condition_sha256': condition['condition_sha256'],
        'scene_ids': sorted(expected), 'legality': checked}
