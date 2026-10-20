"""Fixed-unit linked OPP/start domain with warm-fixed closed Stage choices.

The original budget-local complete SAFE seed fixes devices. A separate,
complete SAFE anchor from the same invocation fixes only closed OPP/start
choices. Open Stage choices retain their original legal modes and starts.
No scheduling repair, physical evaluation or global proof is performed here.
"""
from copy import deepcopy
import hashlib
from pathlib import Path

import neighborhood as n1
from scene_adapter import (canonical_hash, _budget_identity, _scenes,
    make_scene_instance, validate_shared_deployment)
from schedules import validate_schedule
from thermal import _accuracy, _q


PROTOCOL = 'fixed-unit-linked-opp-start-warm-closed-v1'
_FIELDS = n1._FIELDS | {'condition_dependency_sha256', 'warm_candidate',
    'warm_receipt', 'warm_candidate_sha256', 'warm_receipt_sha256',
    'warm_options_by_scene'}


def _source_hash():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _dependency_hashes():
    return {'neighborhood.py': hashlib.sha256(Path(n1.__file__).read_bytes()).hexdigest()}


def _opened(instance, opened, budget):
    scenes = _scenes(instance)
    if not isinstance(opened, dict) or set(opened) != set(scenes):
        raise ValueError('Linked opened mapping must cover exactly every original scene')
    normalized = {}
    for sid, scene in scenes.items():
        budget.check()
        values = opened[sid]
        expected = {stage['id'] for stage in scene['stage_instances']}
        if (not isinstance(values, list) or any(not isinstance(v, str) for v in values)
                or len(values) != len(set(values)) or not values
                or not set(values) < expected):
            raise ValueError('Linked domain must open a nonempty proper subset of each scene')
        normalized[sid] = sorted(values)
    return normalized


def _same_units(seed, warm):
    if (set(seed) != set(warm) or any(set(seed[s]) != set(warm[s]) for s in seed)
            or any(seed[s][t]['unit'] != warm[s][t]['unit']
                   for s in seed for t in seed[s])):
        raise ValueError('Linked warm anchor may not change any original-seed unit')


def make_linked_condition(instance, shared_deployment, seed_candidate, seed_receipt,
                          opened_by_scene, *, warm_candidate, warm_receipt,
                          budget, accuracy=None):
    """Bind seed-fixed units and last complete SAFE warm-fixed closed choices."""
    budget.check()
    deployment = validate_shared_deployment(instance, shared_deployment)
    seed, receipt = n1._json_copy(seed_candidate), n1._json_copy(seed_receipt)
    warm, warm_part = n1._json_copy(warm_candidate), n1._json_copy(warm_receipt)
    requested = n1._json_copy(_accuracy(accuracy))
    n1._validate_seed_receipt(instance, deployment, seed, receipt, requested, budget)
    n1._validate_seed_receipt(instance, deployment, warm, warm_part, requested, budget)
    seed_options, warm_options = n1._seed_options(seed), n1._seed_options(warm)
    _same_units(seed_options, warm_options)
    out = {'protocol': PROTOCOL, 'source_input_sha256': canonical_hash(instance),
        'shared_deployment': deployment, 'accuracy': requested,
        'seed_candidate': seed, 'seed_receipt': receipt,
        'seed_candidate_sha256': canonical_hash(seed),
        'seed_receipt_sha256': receipt['receipt_sha256'],
        'budget_identity': _budget_identity(budget),
        'evaluator_source_sha256': deepcopy(receipt['identity']['source_sha256']),
        'condition_source_sha256': _source_hash(),
        'condition_dependency_sha256': _dependency_hashes(),
        'opened_by_scene': _opened(instance, opened_by_scene, budget),
        'seed_options_by_scene': seed_options, 'warm_candidate': warm,
        'warm_receipt': warm_part, 'warm_candidate_sha256': canonical_hash(warm),
        'warm_receipt_sha256': warm_part['receipt_sha256'],
        'warm_options_by_scene': warm_options}
    out['condition_sha256'] = n1._condition_hash(out)
    budget.check()
    return out


def validate_linked_condition(instance, condition, *, budget, shared_deployment=None):
    """Recheck both complete SAFE generations, sources, original input and Budget."""
    budget.check()
    if (not isinstance(condition, dict) or set(condition) != _FIELDS
            or condition.get('protocol') != PROTOCOL
            or condition.get('condition_sha256') != n1._condition_hash(condition)):
        raise ValueError('invalid or modified linked condition')
    out = n1._json_copy(condition)
    deployment = validate_shared_deployment(instance, out['shared_deployment'])
    if shared_deployment is not None and deployment != validate_shared_deployment(
            instance, shared_deployment):
        raise ValueError('Linked shared deployment condition mismatch')
    if (out['source_input_sha256'] != canonical_hash(instance)
            or out['budget_identity'] != _budget_identity(budget)
            or out['condition_source_sha256'] != _source_hash()
            or out['condition_dependency_sha256'] != _dependency_hashes()
            or out['accuracy'] != _accuracy(out['accuracy'])
            or out['seed_candidate_sha256'] != canonical_hash(out['seed_candidate'])
            or out['seed_receipt_sha256'] != out['seed_receipt'].get('receipt_sha256')
            or out['warm_candidate_sha256'] != canonical_hash(out['warm_candidate'])
            or out['warm_receipt_sha256'] != out['warm_receipt'].get('receipt_sha256')):
        raise ValueError('Linked input, Budget, source or SAFE anchor identity mismatch')
    for candidate, receipt in ((out['seed_candidate'], out['seed_receipt']),
                                (out['warm_candidate'], out['warm_receipt'])):
        n1._validate_seed_receipt(instance, deployment, candidate, receipt,
                                  out['accuracy'], budget)
        if out['evaluator_source_sha256'] != receipt['identity']['source_sha256']:
            raise ValueError('Linked evaluator sources do not match both SAFE anchors')
    if (out['opened_by_scene'] != _opened(instance, out['opened_by_scene'], budget)
            or out['seed_options_by_scene'] != n1._seed_options(out['seed_candidate'])
            or out['warm_options_by_scene'] != n1._seed_options(out['warm_candidate'])):
        raise ValueError('Linked derived conditions do not match saved SAFE anchors')
    _same_units(out['seed_options_by_scene'], out['warm_options_by_scene'])
    budget.check()
    return out


def _member(condition, sid, stage_id, unit, opp, start):
    try:
        seed = condition['seed_options_by_scene'][sid][stage_id]
        warm = condition['warm_options_by_scene'][sid][stage_id]
    except (KeyError, TypeError) as error:
        raise ValueError('unknown linked scene/Stage identity') from error
    if unit != seed['unit']:
        return False
    return (stage_id in condition['opened_by_scene'][sid]
            or (opp == warm['opp'] and _q(start) == _q(warm['start_ms'])))


def filter_linked_options(instance, condition, options, *, budget):
    """Order-preserving intersection; closed starts are exact rational values."""
    condition = validate_linked_condition(instance, condition, budget=budget)
    counts = {sid: {stage: {'before': 0, 'after': 0} for stage in by_stage}
              for sid, by_stage in condition['seed_options_by_scene'].items()}
    kept, before = [], 0
    for option in options:
        budget.check()
        if not isinstance(option, dict):
            raise ValueError('Linked option must be a dict')
        sid, stage_id = option['scenario_id'], option['stage_instance_id']
        try:
            count = counts[sid][stage_id]
        except (KeyError, TypeError) as error:
            raise ValueError('unknown linked option scene/Stage identity') from error
        before += 1
        count['before'] += 1
        if _member(condition, sid, stage_id, option['unit_id'], option['opp_id'], option['start_ms']):
            kept.append(option)
            count['after'] += 1
    budget.check()
    return kept, {'before': before, 'after': len(kept), 'removed': before-len(kept),
                  'by_scene_stage': counts, 'complete': True,
                  'condition_sha256': condition['condition_sha256']}


def check_linked_candidate(instance, condition, candidate, *, budget, scene_id=None):
    """Check original legality, fixed units and warm-fixed closed OPP/start."""
    condition = validate_linked_condition(instance, condition, budget=budget)
    scenes = _scenes(instance)
    expected = set(scenes) if scene_id is None else {scene_id}
    if (scene_id is not None and scene_id not in scenes
            or not isinstance(candidate, dict) or set(candidate) != {'scenes'}
            or not isinstance(candidate['scenes'], dict)
            or set(candidate['scenes']) != expected):
        raise ValueError('Linked candidate must contain all scenes or exactly its explicit scene')
    view = instance if scene_id is None else make_scene_instance(instance, scene_id)
    checked = validate_schedule(view, candidate)
    budget.check()
    if checked['state'] != 'SCHEDULE_VALID_THERMAL_UNCHECKED':
        raise ValueError('original schedule is illegal: '+str(checked['reason']))
    for sid, rows in candidate['scenes'].items():
        for row in rows:
            budget.check()
            if not _member(condition, sid, row['stage_id'], row['unit'], row['opp'], row['start_ms']):
                raise ValueError('candidate lies outside linked condition: '+sid+'/'+row['stage_id'])
    budget.check()
    return {'state': 'LINKED_MEMBER_SCHEDULE_VALID_THERMAL_UNCHECKED',
        'condition_sha256': condition['condition_sha256'],
        'scene_ids': sorted(expected), 'legality': checked}
