"""Budget-local fixed-unit domain with every Stage's OPP/start open.

This is a separate protocol from N1. Its complete SAFE seed fixes every
execution unit, including shared deployment A. Each scene independently
retains all original legal OPP/start choices. No thermal evaluation, candidate
construction, timing repair, or global optimality claim is performed here.
"""
from copy import deepcopy
import hashlib
from pathlib import Path

import neighborhood as n1
from scene_adapter import (canonical_hash, _budget_identity, _scenes,
    make_scene_instance, validate_shared_deployment)
from schedules import validate_schedule
from thermal import _accuracy


PROTOCOL = 'fixed-unit-all-stage-opp-start-v1'
_FIELDS = n1._FIELDS | {'condition_dependency_sha256'}


def _source_hash():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _dependency_hashes():
    return {'neighborhood.py': hashlib.sha256(Path(n1.__file__).read_bytes()).hexdigest()}


def _opened(instance, opened, budget):
    scenes = _scenes(instance)
    if not isinstance(opened, dict) or set(opened) != set(scenes):
        raise ValueError('Fixed-unit opened mapping must cover exactly every original scene')
    normalized = {}
    for sid, scene in scenes.items():
        budget.check()
        values = opened[sid]
        expected = {stage['id'] for stage in scene['stage_instances']}
        if (not isinstance(values, list) or any(not isinstance(v, str) for v in values)
                or len(values) != len(set(values)) or set(values) != expected):
            raise ValueError('Fixed-unit domain must open exactly every Stage instance in each scene')
        normalized[sid] = sorted(values)
    return normalized


def make_fixed_unit_condition(instance, shared_deployment, seed_candidate, seed_receipt,
                              opened_by_scene, *, budget, accuracy=None):
    """Declare all original OPPs/starts on this invocation's SAFE seed units."""
    budget.check()
    deployment = validate_shared_deployment(instance, shared_deployment)
    candidate, receipt = n1._json_copy(seed_candidate), n1._json_copy(seed_receipt)
    requested = n1._json_copy(_accuracy(accuracy))
    n1._validate_seed_receipt(instance, deployment, candidate, receipt, requested, budget)
    out = {'protocol': PROTOCOL, 'source_input_sha256': canonical_hash(instance),
        'shared_deployment': deployment, 'accuracy': requested,
        'seed_candidate': candidate, 'seed_receipt': receipt,
        'seed_candidate_sha256': canonical_hash(candidate),
        'seed_receipt_sha256': receipt['receipt_sha256'],
        'budget_identity': _budget_identity(budget),
        'evaluator_source_sha256': deepcopy(receipt['identity']['source_sha256']),
        'condition_source_sha256': _source_hash(),
        'condition_dependency_sha256': _dependency_hashes(),
        'opened_by_scene': _opened(instance, opened_by_scene, budget),
        'seed_options_by_scene': n1._seed_options(candidate)}
    out['condition_sha256'] = n1._condition_hash(out)
    budget.check()
    return out


def validate_fixed_unit_condition(instance, condition, *, budget, shared_deployment=None):
    """Bind original input, complete SAFE seed, source dependencies and Budget."""
    budget.check()
    if (not isinstance(condition, dict) or set(condition) != _FIELDS
            or condition.get('protocol') != PROTOCOL
            or condition.get('condition_sha256') != n1._condition_hash(condition)):
        raise ValueError('invalid or modified fixed-unit condition')
    out = n1._json_copy(condition)
    deployment = validate_shared_deployment(instance, out['shared_deployment'])
    if shared_deployment is not None and deployment != validate_shared_deployment(
            instance, shared_deployment):
        raise ValueError('Fixed-unit shared deployment condition mismatch')
    if (out['source_input_sha256'] != canonical_hash(instance)
            or out['budget_identity'] != _budget_identity(budget)
            or out['condition_source_sha256'] != _source_hash()
            or out['condition_dependency_sha256'] != _dependency_hashes()
            or out['accuracy'] != _accuracy(out['accuracy'])
            or out['seed_candidate_sha256'] != canonical_hash(out['seed_candidate'])
            or out['seed_receipt_sha256'] != out['seed_receipt'].get('receipt_sha256')):
        raise ValueError('Fixed-unit input, Budget, source or seed identity mismatch')
    n1._validate_seed_receipt(instance, deployment, out['seed_candidate'], out['seed_receipt'],
                               out['accuracy'], budget)
    if (out['evaluator_source_sha256'] != out['seed_receipt']['identity']['source_sha256']
            or out['opened_by_scene'] != _opened(instance, out['opened_by_scene'], budget)
            or out['seed_options_by_scene'] != n1._seed_options(out['seed_candidate'])):
        raise ValueError('Fixed-unit derived conditions do not match seed evidence')
    budget.check()
    return out


def filter_fixed_unit_options(instance, condition, options, *, budget):
    """Keep the original ordered options iff their unit equals the seed unit."""
    condition = validate_fixed_unit_condition(instance, condition, budget=budget)
    counts = {sid: {stage: {'before': 0, 'after': 0} for stage in by_stage}
              for sid, by_stage in condition['seed_options_by_scene'].items()}
    kept, before = [], 0
    for option in options:
        budget.check()
        if not isinstance(option, dict):
            raise ValueError('Fixed-unit option must be a dict')
        sid, stage_id = option['scenario_id'], option['stage_instance_id']
        try:
            count = counts[sid][stage_id]
        except (KeyError, TypeError) as error:
            raise ValueError('unknown fixed-unit option scene/Stage identity') from error
        before += 1
        count['before'] += 1
        if n1._member(condition, sid, stage_id, option['unit_id'], option['opp_id'], option['start_ms']):
            kept.append(option)
            count['after'] += 1
    budget.check()
    return kept, {'before': before, 'after': len(kept), 'removed': before - len(kept),
                  'by_scene_stage': counts, 'complete': True,
                  'condition_sha256': condition['condition_sha256']}


def check_fixed_unit_candidate(instance, condition, candidate, *, budget, scene_id=None):
    """Check original legality and fixed units; never synchronize scene OPPs."""
    condition = validate_fixed_unit_condition(instance, condition, budget=budget)
    scenes = _scenes(instance)
    expected = set(scenes) if scene_id is None else {scene_id}
    if (scene_id is not None and scene_id not in scenes
            or not isinstance(candidate, dict) or set(candidate) != {'scenes'}
            or not isinstance(candidate['scenes'], dict)
            or set(candidate['scenes']) != expected):
        raise ValueError('Fixed-unit candidate must contain all scenes or exactly its explicit scene')
    view = instance if scene_id is None else make_scene_instance(instance, scene_id)
    checked = validate_schedule(view, candidate)
    budget.check()
    if checked['state'] != 'SCHEDULE_VALID_THERMAL_UNCHECKED':
        raise ValueError('original schedule is illegal: ' + str(checked['reason']))
    for sid, rows in candidate['scenes'].items():
        for row in rows:
            budget.check()
            if not n1._member(condition, sid, row['stage_id'], row['unit'], row['opp'], row['start_ms']):
                raise ValueError('candidate lies outside fixed-unit condition: ' + sid + '/' + row['stage_id'])
    budget.check()
    return {'state': 'FIXED_UNIT_MEMBER_SCHEDULE_VALID_THERMAL_UNCHECKED',
        'condition_sha256': condition['condition_sha256'], 'scene_ids': sorted(expected), 'legality': checked}
