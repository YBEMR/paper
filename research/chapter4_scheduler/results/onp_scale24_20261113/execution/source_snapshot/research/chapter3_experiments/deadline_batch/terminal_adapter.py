"""Stored-evidence adapter for a bounded linked seed-construction stop.

The existing linked method deliberately does not start its MILP without a
complete SAFE seed.  Exhausting its three existing templates is a method
limitation, not an exception, infeasibility proof, or a new SAFE result.  This
adapter changes only that stop's execution classification.  It never runs a
constructor, model, solver, thermal integrator, repair, or new energy check.

Unknown/thermal-unresolved attempts retain the inherited unresolved status.
Hashes bind ordinary accidental mixing; this is not an adversarial verifier.
"""
from copy import deepcopy
from fractions import Fraction as F
import json
import math
from pathlib import Path
from types import SimpleNamespace


PROTOCOL = 'K162-deadline-linked-no-safe-seed-stored-audit-v1'
NO_SEED_REASON = 'NO_COMPLETE_SAFE_LINKED_SEED'


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _read(path):
    with Path(path).open(encoding='utf-8') as stream:
        return json.load(stream)


def _check_inputs(result, declaration, folder):
    from scene_adapter import canonical_hash
    from thermal import _accuracy
    config = _read(folder/'input_config.json')
    instance = _read(folder/'input_instance.json')
    expected = {'full_input_sha256': declaration['input_sha256'],
                'config_sha256': declaration['config_sha256']}
    _require(canonical_hash(instance) == expected['full_input_sha256']
             and canonical_hash(config) == expected['config_sha256'],
             'STORED_INPUT_IDENTITY_MISMATCH')
    _require(result.get('problem_id') == declaration['problem_id'] == instance['id'],
             'PROBLEM_IDENTITY_MISMATCH')
    identity = result.get('identity') or {}
    _require(all(identity.get(k) == v for k, v in expected.items()),
             'RESULT_INPUT_IDENTITY_MISMATCH')
    accuracy = _accuracy(config['accuracy_targets'])
    _require(identity.get('accuracy_sha256') == canonical_hash(accuracy)
             and identity.get('shared_deployment_sha256') == canonical_hash(result['shared_deployment']),
             'ACCURACY_OR_DEPLOYMENT_IDENTITY_MISMATCH')
    _require(result.get('original_scene_order') == [s['id'] for s in instance['scenarios']],
             'SCENE_ORDER_MISMATCH')
    return config, instance, accuracy


def _check_construction_failure(construction, instance):
    """Only an ordinary exhausted fixed-rule start search is eligible."""
    _require('candidate' not in construction, 'FAILED_CONSTRUCTION_HAS_CANDIDATE')
    details = construction.get('details') or {}
    _require(details.get('reason') == 'NO_START_FOUND_BY_FIXED_RULE',
             'CONSTRUCTION_FAILURE_NOT_RECOGNISED')
    scene = next((s for s in instance['scenarios'] if s['id'] == details.get('scenario')), None)
    _require(scene is not None, 'CONSTRUCTION_FAILURE_SCENE_MISMATCH')
    stage = next((s for s in scene['stage_instances'] if s['id'] == details.get('stage_id')), None)
    _require(stage is not None, 'CONSTRUCTION_FAILURE_STAGE_MISMATCH')
    request = next(r for r in scene['requests'] if r['id'] == stage['request_id'])
    _require(F(details['latest_finish_ms']) == min(F(instance['window_ms']), F(request['deadline_ms']))
             and F(details['earliest_ms']) >= F(request['release_ms'])
             and F(details['duration_ms']) > 0
             and type(details.get('assigned_stage_count')) is int
             and 0 <= details['assigned_stage_count'] < len(scene['stage_instances']),
             'CONSTRUCTION_FAILURE_TIME_OR_COUNT_INVALID')
    unit = construction['shared_deployment'][stage['shared_stage_id']]
    mode = next((m for m in instance['stage_modes'][stage['shared_stage_id']]
                 if m['unit_id'] == unit
                 and m['opp_id'] == construction['domain_opps'][m['domain_id']]), None)
    _require(mode is not None and F(mode['duration_ms']) == F(details['duration_ms']),
             'CONSTRUCTION_FAILURE_MODE_MISMATCH')


def _check_scene_receipt(receipt, candidate, scene, result, instance, accuracy, budget_id, elapsed):
    from scene_adapter import (_partial_identity, _receipt_hash,
                               _local_candidate_deployment, PARTIAL_PROTOCOL)
    sid = scene['id']
    local = _local_candidate_deployment(instance, sid, candidate)
    supplied_budget = receipt.get('identity', {}).get('budget')
    _require(isinstance(supplied_budget, dict)
             and isinstance(supplied_budget.get('token'), str) and bool(supplied_budget['token'])
             and F(supplied_budget['seconds']) == 300
             and F(supplied_budget['start']) >= 0,
             'MISSING_OR_INVALID_RECEIPT_BUDGET')
    if budget_id is not None:
        _require(supplied_budget == budget_id, 'MIXED_SEED_RECEIPT_BUDGETS')
    # Identity calculation only.  A frozen identity avoids allocating a new
    # token or advancing a clock; no trajectory is recomputed here.
    proxy = SimpleNamespace(_scene_adapter_budget_identity=deepcopy(supplied_budget))
    identity = _partial_identity(instance, result['shared_deployment'], accuracy,
        proxy, scene_id=sid, candidate=candidate, local_deployment=local)
    _require(receipt.get('protocol') == PARTIAL_PROTOCOL
             and receipt.get('identity') == identity
             and receipt.get('receipt_sha256') == _receipt_hash(receipt)
             and receipt.get('scenario_id') == sid
             and receipt.get('shared_deployment') == result['shared_deployment']
             and receipt.get('shared_stage_ids') == result['shared_stage_ids']
             and receipt.get('local_deployment') == local
             and receipt.get('unweighted') is True,
             'SEED_SCENE_RECEIPT_IDENTITY_MISMATCH')
    _require(_number(receipt.get('elapsed_s')) and 0 <= receipt['elapsed_s'] <= elapsed < 300
             and not receipt.get('error_type') and not receipt.get('error_details')
             and receipt.get('budget_exhausted') is not True
             and receipt.get('legality', {}).get('state') == 'SCHEDULE_VALID_THERMAL_UNCHECKED',
             'SEED_SCENE_RECEIPT_ERROR_OR_LATE')
    physical = receipt.get('result') or {}
    _require(physical.get('scene_id') == sid and not physical.get('error_type')
             and not physical.get('error_details') and not physical.get('budget_exhausted'),
             'SEED_PHYSICAL_RECEIPT_ERROR')
    if receipt.get('state') == 'SAFE':
        _require(receipt.get('rankable_energy') is True and receipt.get('violations') == []
                 and physical.get('state') == 'SAFE' and physical.get('complete') is True
                 and physical.get('rankable_energy') is True
                 and physical.get('energy_accuracy_met') is True
                 and F(physical['covered_until_s']) == F(instance['window_ms'])/1000
                 and _number(receipt.get('completed_at_elapsed_s'))
                 and 0 <= receipt['completed_at_elapsed_s'] <= elapsed,
                 'INCOMPLETE_OR_LATE_LOCAL_SAFE')
        return supplied_budget, False
    _require(receipt.get('state') == 'THERMAL_VIOLATION'
             and receipt.get('reason') == 'POINT_WITNESS'
             and receipt.get('rankable_energy') is False
             and physical.get('state') == 'THERMAL_VIOLATION'
             and receipt.get('violations') == physical.get('violations')
             and bool(receipt.get('violations')), 'THERMAL_OR_NUMERICAL_UNRESOLVED')
    limits = dict(zip(instance['platform']['node_order'], scene['maximum_temperature_degC']))
    for witness in receipt['violations']:
        lower, upper = map(F, witness['temperature_degC'])
        _require(witness.get('scene_id') == sid and witness.get('node') in limits
                 and lower <= upper and lower > F(limits[witness['node']])
                 and F(witness['limit_degC']) == F(limits[witness['node']])
                 and 0 <= F(witness['time_s']) <= F(instance['window_ms'])/1000
                 and _number(witness.get('formed_at_elapsed_s'))
                 and 0 <= witness['formed_at_elapsed_s'] <= elapsed,
                 'INVALID_OR_LATE_SAVED_POINT_WITNESS')
    return supplied_budget, True


def _check_attempts(result, instance, accuracy, elapsed):
    from initial_schedule import RULE_VERSION
    from schedules import validate_schedule
    attempts = result.get('seed_attempts')
    _require(isinstance(attempts, list) and len(attempts) == 3,
             'THREE_TEMPLATE_EXHAUSTION_NOT_RECORDED')
    domains = instance['platform']['domains']
    ranks = {domain: sorted(v['opps'], key=lambda k: (-F(v['opps'][k]['frequency_GHz']), k))
             for domain, v in domains.items()}
    _require(all(len(v) == 3 for v in ranks.values()), 'THREE_OPP_SCOPE_REQUIRED')
    previous, budget_id, violations = 0., None, 0
    for rank, attempt in enumerate(attempts, 1):
        construction = attempt.get('construction') or {}
        expected_opps = {domain: values[rank-1] for domain, values in ranks.items()}
        _require(construction.get('rule_version') == RULE_VERSION
                 and construction.get('template_rank') == rank
                 and construction.get('domain_opps') == expected_opps
                 and construction.get('thermal_status') == 'NOT_EVALUATED'
                 and construction.get('energy_status') == 'NOT_EVALUATED'
                 and construction.get('exclusion') == 'NONE', 'CONSTRUCTION_TEMPLATE_IDENTITY_MISMATCH')
        stamp = attempt.get('schedule_completed_at_s')
        _require(_number(stamp) and previous <= stamp <= elapsed
                 and attempt.get('state') == 'UNRESOLVED'
                 and attempt.get('aggregation') is None, 'INCOMPLETE_SEED_ATTEMPT_OR_CLOCK')
        previous = stamp
        if construction.get('status') == 'CONSTRUCTION_UNRESOLVED':
            _require(attempt.get('reason') == 'CONSTRUCTION_UNRESOLVED'
                     and attempt.get('scene_evaluations') == {}, 'FAILED_CONSTRUCTION_HAS_EVALUATION')
            _check_construction_failure(construction, instance)
            continue
        _require(construction.get('status') == 'COMPLETE_LEGAL_CANDIDATE',
                 'UNKNOWN_CONSTRUCTION_STATUS')
        candidate = construction.get('candidate')
        _require(validate_schedule(instance, candidate)['state'] == 'SCHEDULE_VALID_THERMAL_UNCHECKED',
                 'STORED_SEED_SCHEDULE_INVALID')
        stages = {s['id']: s for scene in instance['scenarios'] for s in scene['stage_instances']}
        units = {u['id']: u for u in instance['platform']['units']}
        _require(all(row['opp'] == expected_opps[units[row['unit']]['domain_id']]
                     and row['unit'] == construction['shared_deployment'][stages[row['stage_id']]['shared_stage_id']]
                     for rows in candidate['scenes'].values() for row in rows),
                 'COMPLETE_CANDIDATE_TEMPLATE_OR_DEPLOYMENT_MISMATCH')
        evaluations = attempt.get('scene_evaluations')
        _require(isinstance(evaluations, dict) and bool(evaluations)
                 and list(evaluations) == [s['id'] for s in instance['scenarios']][:len(evaluations)],
                 'SEED_SCENE_PREFIX_INVALID')
        failed = False
        for sid, receipt in evaluations.items():
            _require(not failed, 'EVALUATION_AFTER_FAILED_SEED_SCENE')
            scene = next(s for s in instance['scenarios'] if s['id'] == sid)
            local = {'scenes': {sid: candidate['scenes'][sid]}}
            budget_id, failed = _check_scene_receipt(receipt, local, scene, result,
                instance, accuracy, budget_id, elapsed)
            if failed:
                violations += 1
        _require(failed and attempt.get('reason') == 'POINT_WITNESS',
                 'NO_CONCLUSIVE_SEED_FAILURE_OR_AGGREGATION_MISSING')
    return violations


def adapt_no_safe_seed(record, result, declaration, folder):
    """Return a copy; normalise only a fully evidenced pre-native seed stop.

    ``record`` is the unchanged inherited audit_cutoff result.  Existing hard
    errors, unknown identity, numeric rejection and heat-unknown states remain
    blockers.  Missing fields are not silently supplied as success evidence.
    """
    out = deepcopy(record)
    audit = {'protocol': PROTOCOL, 'applied': False,
             'new_safe_evaluation': False, 'new_or_late_U': False,
             'independent_infeasibility_claim': False,
             'scope': 'existing three seed templates exhausted; no search-domain exclusion'}
    out['no_safe_seed_audit'] = audit
    if not isinstance(result, dict) or result.get('reason') != NO_SEED_REASON:
        audit['not_applied_reason'] = 'NOT_THE_LINKED_NO_SAFE_SEED_STOP'
        return out
    try:
        context = deepcopy(record['context'])
        _require(record['execution']['execution_status'] == 'STATUS_UNRESOLVED'
                 and record.get('usable_U_J') is None
                 and context.get('hard_errors') == []
                 and context.get('observed_numerical_rejection') is False
                 and context.get('numerical_checks') == []
                 and context.get('prior_requests_complete') is True
                 and context.get('last_request') == {'state': 'NONE'}
                 and context.get('worker_isolation') == 'NOT_APPLICABLE'
                 and context.get('thermal_unresolved') is False
                 and all(context.get(k) is True for k in ('input_identity_valid',
                      'source_identity_valid', 'current_request_identity_valid')),
                 'INHERITED_ERROR_IDENTITY_OR_UNRESOLVED_CHECK_BLOCKS_ADAPTER')
        _require(result.get('state') == 'UNRESOLVED'
                 and result.get('technical_state') == 'INTERRUPTED_OR_UNRESOLVED'
                 and result.get('stop_stage') == 'fresh_seed_construction'
                 and result.get('budget_exhausted') is False
                 and result.get('search_failure_latched') is False
                 and all(not result.get(k) for k in ('error', 'cleanup_error', 'archive_errors'))
                 and result.get('archive_complete') is not False,
                 'METHOD_STOP_IS_NOT_CLEAN_SEED_EXHAUSTION')
        _require(result.get('matlab_worker_ready') is False
                 and result.get('solver_request_attempts') == 0
                 and result.get('session_total_request_count') == 0
                 and result.get('integer_solver_entered') is False
                 and result.get('event_consumer_detached') is True
                 and result.get('session_closed_by_neighborhood') is False,
                 'NATIVE_ACTIVITY_IN_PRE_NATIVE_SEED_STOP')
        transport = result.get('augmented_transport') or {}
        _require(transport.get('requests') == [] and transport.get('latched_unresolved') is False
                 and transport.get('failure_reasons') == [], 'UNRESOLVED_OR_EXISTING_NATIVE_TRANSPORT')
        folder = Path(folder)
        _require(not any(p.is_file() for p in (folder/'matlab').rglob('*')),
                 'NATIVE_ARTIFACTS_EXIST')
        _require(result.get('phases') == [] and result.get('condition') is None
                 and result.get('committed_safe_snapshot') is None
                 and result.get('global_updates') == []
                 and result.get('rankable_energy') is False
                 and all(result.get(k) is None for k in ('safe_candidate', 'safe_upper_bound_J',
                     'weighted_energy_J', 'aggregation', 'initial_global_safe_upper_bound_J'))
                 and result.get('independently_proven_optimal') is False
                 and result.get('independently_proven_infeasible') is False
                 and result.get('remaining_domain') == 'retained', 'UNEXPECTED_SAFE_PHASE_OR_PROOF')
        timing = result.get('timing') or {}
        elapsed = timing.get('method_elapsed_s')
        _require(timing.get('limit_s') == 300 and _number(elapsed) and 0 <= elapsed < 300
                 and context.get('cutoff_s') == 300
                 and context.get('root_deadline_confirmed') is False, 'ROOT_BUDGET_NOT_VERIFIED')
        _, instance, accuracy = _check_inputs(result, declaration, folder)
        violations = _check_attempts(result, instance, accuracy, elapsed)
        context['completion_verified'] = True
        from execution_status import classify_execution
        execution = classify_execution(result, context)
        _require(execution['execution_status'] == 'NORMAL_COMPLETION'
                 and execution['usable_U_J'] is None
                 and execution['safe_witness_preserved'] is False
                 and execution['independently_proven_infeasible'] is False,
                 'INHERITED_CLASSIFIER_REJECTED_COMPLETION')
        audit.update(applied=True, original_execution_status=record['execution']['execution_status'],
                     method_outcome='NO_COMPLETE_SAFE_SEED_WITHIN_FIXED_THREE_TEMPLATE_RULE',
                     templates_exhausted=3, saved_point_violation_attempts=violations,
                     complete_safe_solution_found=False)
        out.update(context=context, execution=execution, usable_U_J=None)
    except (KeyError, TypeError, ValueError, IndexError, OSError, ZeroDivisionError) as exc:
        audit['not_applied_reason'] = str(exc)
    return out
