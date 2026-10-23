"""Fixed-deployment, single-scene evaluation and guarded outer aggregation.

Scene views use objective weight one only to expose an *unweighted* interface.
The original weights are applied once, after every scene (including weight-zero
scenes) has a matching SAFE receipt.  Receipts belong to one shared Budget;
these hashes detect accidental mixing, not adversarially forged evidence.
No search, repair, deployment exclusion or optimum certificate is performed.
"""
from copy import deepcopy
from control_policy import require_legacy_control, resolve_idle_policy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import uuid

from schedules import validate_schedule
from start_domain import explicit_start_sets
from thermal import Budget, Exhausted, I, _accuracy, _energy_accuracy, _q, evaluate_piecewise

PROTOCOL = 'fixed-deployment-unweighted-scene-v1'
PARTIAL_PROTOCOL = 'partial-shared-deployment-unweighted-scene-v1'


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
    require_legacy_control(instance, 'Fixed-deployment scene adapter')
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


def shared_deployment_ids(instance):
    """Return Stage deployment identities occurring in distinct full scenes.

    ``instance`` must be the original, unprojected input. Repeated requests in
    one scene contribute one occurrence; catalog entries unused by scenes do
    not contribute. A genuine one-scene input has an empty shared set.
    """
    try:
        occurrences = {}
        for scene_id, scene in _scenes(instance).items():
            used = {stage['shared_stage_id'] for stage in scene['stage_instances']}
            for shared in used:
                if not isinstance(shared, str) or shared not in instance['stage_modes']:
                    raise ValueError('unknown Stage deployment identity')
                occurrences.setdefault(shared, set()).add(scene_id)
        return sorted(shared for shared, scenes in occurrences.items() if len(scenes) >= 2)
    except (KeyError, TypeError) as error:
        raise ValueError('malformed full input for shared deployment') from error


def validate_shared_deployment(instance, mapping):
    """Validate exactly H's concrete units, leaving scene-local mappings free.

    The source must be the original full input, before make_scene_instance.
    Both declared control policies are supported by this structural interface.
    """
    resolve_idle_policy(instance)
    shared = shared_deployment_ids(instance)
    if not isinstance(mapping, dict) or set(mapping) != set(shared):
        raise ValueError('shared deployment must cover exactly cross-scene Stages')
    units = {unit['id']: unit for unit in instance['platform']['units']}
    if len(units) != len(instance['platform']['units']):
        raise ValueError('duplicate execution unit identities')
    result = {}
    for stage in shared:
        unit = mapping[stage]
        if not isinstance(unit, str) or unit not in units:
            raise ValueError('unknown shared execution unit: '+str(unit))
        if not any(mode['unit_id'] == unit and mode['shared_stage_id'] == stage
                   for mode in instance['stage_modes'][stage]):
            raise ValueError('illegal shared deployment for '+stage)
        result[stage] = unit
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


def _partial_identity(instance, deployment, accuracy, budget, *, scene_id=None,
                      candidate=None, local_deployment=None):
    """Bind fixed conditions separately from a returned local solution."""
    sources = _source_identity()
    policy_source = Path(__file__).with_name('control_policy.py')
    sources[policy_source.name] = hashlib.sha256(policy_source.read_bytes()).hexdigest()
    identity = {'protocol': PARTIAL_PROTOCOL,
        'full_input_sha256': canonical_hash(instance),
        'shared_stage_ids': shared_deployment_ids(instance),
        'shared_deployment_sha256': canonical_hash(deployment),
        'platform_sha256': canonical_hash(instance['platform']),
        'execution_rules_sha256': canonical_hash(instance['execution_rules']),
        'control_policy': resolve_idle_policy(instance),
        'accuracy_sha256': canonical_hash(accuracy),
        'source_sha256': sources, 'budget': _budget_identity(budget)}
    if scene_id is not None:
        scene = _scenes(instance)[scene_id]
        identity.update(scenario_id=scene_id, scenario_sha256=canonical_hash(scene),
                        entry_sha256=canonical_hash(scene['entry']))
    if candidate is not None:
        identity['candidate_sha256'] = canonical_hash(candidate)
    if local_deployment is not None:
        identity['local_deployment_sha256'] = canonical_hash(local_deployment)
    return identity


def _local_candidate_deployment(instance, scene_id, candidate):
    """Read complete candidate identities, without thermal work or search.

    This cheap extraction permits transfer of previously committed matching
    violations after expiry. Full original-input legality is checked before
    any new global upper bound is committed.
    """
    if (not isinstance(candidate, dict) or set(candidate) != {'scenes'}
            or not isinstance(candidate['scenes'], dict)
            or set(candidate['scenes']) != {scene_id}):
        raise ValueError('partial scene candidate must contain exactly its scene')
    stages = {s['id']: s for s in _scenes(instance)[scene_id]['stage_instances']}
    rows = candidate['scenes'][scene_id]
    if not isinstance(rows, list) or len(rows) != len(stages):
        raise ValueError('partial scene candidate must cover every Stage')
    seen, deployment = set(), {}
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {'stage_id','unit','opp','start_ms'}
                or row['stage_id'] not in stages or row['stage_id'] in seen
                or not isinstance(row['unit'], str)):
            raise ValueError('malformed or duplicate local Stage assignment')
        seen.add(row['stage_id'])
        shared = stages[row['stage_id']]['shared_stage_id']
        if shared in deployment and deployment[shared] != row['unit']:
            raise ValueError('local request copies disagree on their deployment')
        deployment[shared] = row['unit']
    if seen != set(stages):
        raise ValueError('incomplete local Stage assignment')
    return {key: deployment[key] for key in sorted(deployment)}


def _partial_failure(out, error):
    if isinstance(error, Exhausted):
        out.update(reason=str(error), budget_exhausted=True)
        state = 'UNRESOLVED'
    elif isinstance(error, MemoryError):
        out['reason'] = 'RESOURCE_LIMIT'
        state = 'UNRESOLVED'
    elif isinstance(error, ArithmeticError):
        out.update(reason='NUMERICAL_ERROR', error_type=type(error).__name__,
                   error_details=str(error))
        state = 'UNRESOLVED'
    else:
        out.update(reason=str(error), error_type=type(error).__name__)
        state = 'INVALID_INPUT'
    out['state'] = 'THERMAL_VIOLATION' if out['violations'] else state


def _finish_partial(out, budget):
    out.update(elapsed_s=budget.elapsed, panels=budget.panels, refinements=budget.refinements)
    out['receipt_sha256'] = _receipt_hash(out)
    return out


def evaluate_partial_scene(instance, scene_id, shared_deployment, candidate,
                           accuracy=None, budget=None):
    """Evaluate a complete local solution under only H's fixed units.

    The original full input is mandatory. Local mappings, all OPPs and starts
    remain decisions of the supplied candidate, with same-scene request-copy
    consistency enforced by the common checker. No failed candidate excludes
    the shared condition or produces an independent lower bound.
    """
    budget = Budget() if budget is None else budget
    out = {'protocol': PARTIAL_PROTOCOL, 'state': 'UNRESOLVED', 'reason': None,
        'scenario_id': scene_id, 'identity': None, 'legality': None, 'result': None,
        'shared_stage_ids': None, 'shared_deployment': None, 'local_deployment': None,
        'violations': [], 'energy_J': None, 'safe_upper_bound_J': None,
        'rankable_energy': False, 'unweighted': True,
        'deployment_feasibility': 'NOT_DECIDED', 'formal_experiment_result': False,
        'independently_proven_optimal': False, 'independently_proven_infeasible': False,
        'certified_lower_bound_J': None}
    try:
        budget.check()
        original, supplied = deepcopy(instance), deepcopy(candidate)
        deployment = validate_shared_deployment(original, shared_deployment)
        requested = _accuracy(accuracy)
        out.update(shared_stage_ids=shared_deployment_ids(original),
                   shared_deployment=deepcopy(deployment))
        view = make_scene_instance(original, scene_id)
        checked = validate_schedule(view, supplied)
        out['legality'] = checked
        if checked['state'] != 'SCHEDULE_VALID_THERMAL_UNCHECKED':
            out.update(state='INVALID_SCHEDULE', reason=checked['reason'])
            out['identity'] = _partial_identity(original, deployment, requested,
                budget, scene_id=scene_id, candidate=supplied)
        else:
            local = {key: checked['shared_deployment'][key]
                     for key in sorted(checked['shared_deployment'])}
            out['local_deployment'] = local
            out['identity'] = _partial_identity(original, deployment, requested,
                budget, scene_id=scene_id, candidate=supplied, local_deployment=local)
            if any(local[key] != unit for key, unit in deployment.items() if key in local):
                out.update(state='INVALID_SCHEDULE', reason='SHARED_DEPLOYMENT_MISMATCH')
            else:
                budget.check()
                scene = view['scenarios'][0]
                physical = evaluate_piecewise(view['platform'], scene['entry']['temperature_degC'],
                    scene['maximum_temperature_degC'], checked['scenes'][scene_id]['segments'],
                    view['window_ms'], requested, budget, scene_id=scene_id)
                # Commit existing inner evidence before an outer expiry check.
                out['result'] = physical
                out['violations'] = deepcopy(physical['violations'])
                budget.check()
                if out['violations']:
                    out.update(state='THERMAL_VIOLATION', reason='POINT_WITNESS')
                elif physical['state'] == 'SAFE':
                    formed = physical.get('completed_at_elapsed_s')
                    if (not physical['complete'] or not physical.get('rankable_energy')
                            or not physical.get('energy_accuracy_met')
                            or _q(physical.get('covered_until_s', '-1')) != _q(view['window_ms'])/1000
                            or isinstance(formed, bool) or not isinstance(formed, (int, float))
                            or not 0 <= formed < budget.seconds):
                        out.update(state='UNRESOLVED', reason='INCOMPLETE_OR_LATE_SCENE_SAFE')
                    else:
                        budget.mark('before_partial_scene_commit')
                        completed_at = budget.elapsed
                        if completed_at >= budget.seconds:
                            raise Exhausted('wall_time_limit')
                        out.update(state='SAFE', reason='COMPLETE_CONTINUOUS_ENCLOSURE',
                            energy_J=deepcopy(physical['energy_J']),
                            safe_upper_bound_J=str(I(*physical['energy_J']).hi), rankable_energy=True,
                            completed_at_elapsed_s=completed_at,
                            deployment_feasibility='SCENE_SAFE_WITNESS')
                else:
                    out.update(state=physical['state'], reason=physical['reason'])
    except (Exhausted, MemoryError, ArithmeticError, KeyError, TypeError, ValueError) as error:
        _partial_failure(out, error)
    return _finish_partial(out, budget)


def _partial_scene_energy(instance, scene_id, receipt, budget):
    result = receipt['result']
    formed = receipt.get('completed_at_elapsed_s')
    inner_formed = result.get('completed_at_elapsed_s')
    if (result['state'] != 'SAFE' or not result['complete'] or not result.get('rankable_energy')
            or result['scene_id'] != scene_id
            or _q(result['covered_until_s']) != _q(instance['window_ms'])/1000
            or result['energy_J'] != receipt['energy_J'] or not result['energy_accuracy_met']
            or str(I(*result['energy_J']).hi) != receipt['safe_upper_bound_J']
            or any(isinstance(t, bool) or not isinstance(t, (int, float))
                   or not 0 <= t < budget.seconds for t in (formed, inner_formed))):
        raise ValueError('inconsistent or late partial SAFE scene receipt')
    return I(*receipt['energy_J'])


def aggregate_partial_scene_receipts(instance, shared_deployment, receipts, candidates,
                                     accuracy=None, budget=None):
    """Publish weighted U only for all matching complete scene SAFE witnesses.

    ``candidates`` maps scene ids to complete one-scene candidates. Missing
    scenes remain unresolved. Existing matching violations survive expiry;
    neither local failure nor an unresolved scene excludes the outer condition.
    """
    budget = Budget() if budget is None else budget
    out = {'protocol': PARTIAL_PROTOCOL, 'state': 'UNRESOLVED', 'reason': None,
        'problem_id': instance.get('id'), 'identity': None,
        'shared_stage_ids': None, 'shared_deployment': None, 'merged_deployment': None,
        'safe_candidate': None, 'legality': None, 'scenes': {}, 'violations': [],
        'receipt_errors': {}, 'weighted_energy_J': None, 'safe_upper_bound_J': None,
        'rankable_energy': False, 'deployment_feasibility': 'NOT_DECIDED',
        'formal_experiment_result': False, 'independently_proven_optimal': False,
        'independently_proven_infeasible': False, 'certified_lower_bound_J': None}
    try:
        original = deepcopy(instance)
        deployment = validate_shared_deployment(original, shared_deployment)
        requested = _accuracy(accuracy)
        scenes = _scenes(original)
        weights = {sid: _q(scene['weight']) for sid, scene in scenes.items()}
        if any(w < 0 for w in weights.values()) or sum(weights.values()) != 1:
            raise ValueError('scenario weights must be nonnegative and sum to one')
        out.update(shared_stage_ids=shared_deployment_ids(original),
                   shared_deployment=deepcopy(deployment))
        if (not isinstance(receipts, dict) or not isinstance(candidates, dict)
                or set(receipts)-set(scenes) or set(candidates)-set(scenes)):
            raise ValueError('partial candidate or receipt has unknown scene identities')
        # Identity-only transfer: no physical reevaluation after expiry.
        for scene_id in scenes:
            receipt, candidate = receipts.get(scene_id), candidates.get(scene_id)
            if receipt is None or candidate is None:
                out['receipt_errors'][scene_id] = 'MISSING_SCENE_RECEIPT_OR_CANDIDATE'
                continue
            try:
                local = _local_candidate_deployment(original, scene_id, candidate)
            except (KeyError, TypeError, ValueError) as error:
                out['receipt_errors'][scene_id] = 'INVALID_LOCAL_CANDIDATE: '+str(error)
                continue
            expected = _partial_identity(original, deployment, requested, budget,
                scene_id=scene_id, candidate=candidate, local_deployment=local)
            if (not isinstance(receipt, dict) or receipt.get('protocol') != PARTIAL_PROTOCOL
                    or receipt.get('identity') != expected
                    or receipt.get('shared_deployment') != deployment
                    or receipt.get('shared_stage_ids') != out['shared_stage_ids']
                    or receipt.get('local_deployment') != local or receipt.get('unweighted') is not True):
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
            out.update(reason='NOT_ALL_RECEIPTS_MATCH')
        elif any(r['state'] != 'SAFE' or not r['rankable_energy'] for r in out['scenes'].values()):
            out.update(reason='NOT_ALL_SCENES_COMPLETE_AND_SAFE')
        else:
            combined = {'scenes': {sid: deepcopy(candidates[sid]['scenes'][sid]) for sid in scenes}}
            checked = validate_schedule(original, combined)
            out['legality'] = checked
            budget.check()
            if checked['state'] != 'SCHEDULE_VALID_THERMAL_UNCHECKED':
                out.update(state='INVALID_SCHEDULE', reason=checked['reason'])
            elif any(checked['shared_deployment'][key] != unit for key, unit in deployment.items()):
                out.update(state='INVALID_SCHEDULE', reason='SHARED_DEPLOYMENT_MISMATCH')
            else:
                total = I(0)
                for sid, receipt in out['scenes'].items():
                    if (receipt['legality']['scenes'][sid] != checked['scenes'][sid]
                            or receipt['local_deployment'] != _local_candidate_deployment(original, sid, candidates[sid])):
                        raise ValueError('local legality does not match original full-input merge')
                    total += _partial_scene_energy(original, sid, receipt, budget)*I.rational(weights[sid])
                    budget.check()
                if not _energy_accuracy(total, requested):
                    out['reason'] = 'WEIGHTED_ENERGY_ERROR_TARGET'
                else:
                    budget.mark('before_partial_aggregate_commit')
                    completed_at = budget.elapsed
                    if completed_at >= budget.seconds:
                        raise Exhausted('wall_time_limit')
                    merged = checked['shared_deployment']
                    identity = _partial_identity(original, deployment, requested, budget,
                        candidate=combined, local_deployment=merged)
                    budget.check()
                    completed_at = budget.elapsed
                    if completed_at >= budget.seconds:
                        raise Exhausted('wall_time_limit')
                    out.update(state='SAFE', reason='ALL_MATCHING_SCENES_COMPLETE_AND_SAFE',
                        identity=identity, weighted_energy_J=total.data(), safe_upper_bound_J=str(total.hi),
                        rankable_energy=True, completed_at_elapsed_s=completed_at,
                        safe_candidate=combined, merged_deployment=deepcopy(merged),
                        deployment_feasibility='ALL_SCENES_SAFE_WITNESS')
    except (Exhausted, MemoryError, ArithmeticError, KeyError, TypeError, ValueError) as error:
        _partial_failure(out, error)
    return _finish_partial(out, budget)
