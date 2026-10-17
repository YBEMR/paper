"""One-budget, fixed-deployment single-scene candidate/feedback adapter.

The original MILP and its model-view continuous feedback are reused unchanged.
A SAFE model-view candidate is checked again against the original full input by
``evaluate_scene``. Only matching original-input receipts may supply the outer
weighted upper bound. This adapter searches no other deployment, adds no repair,
warm start or independent optimality/infeasibility claim.
"""
from copy import deepcopy
import json
from pathlib import Path
import platform
import sys
import time

from build_observer import BuildObserver
from matlab_bridge import MatlabSession
from milp import build_model, solve_with_feedback
from scene_adapter import (aggregate_scene_receipts, canonical_hash, _identity,
                           _receipt_hash, evaluate_scene, validate_fixed_deployment)
from thermal import Exhausted, _accuracy, _q
from timing import MethodBudget


DEFAULT_BUILDER_OPTIONS = {
    'fix_late_options': True,
    'aggregate_opp_locks': True,
    'relax_auxiliary_integrality': True,
    'strengthen_energy_lower_bounds': True,
    'prefilter_deadlines': True,
}


def _save(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def _reported_bounds(solved):
    """Copy native progress without upgrading it to a certified bound."""
    found = []
    for index, returned in enumerate(solved.get('rounds', []), 1):
        for callback_index, callback in enumerate(returned.get('callbacks', [])):
            values = callback.get('values', {})
            if 'lowerbound' in values:
                found.append({'round': index, 'origin': 'callback',
                              'callback_index': callback_index,
                              'lowerbound_J': values['lowerbound'],
                              'request_wall_seconds': callback.get('request_wall_seconds'),
                              'solver_reported_only': True,
                              'independently_certified': False})
        output = returned.get('output', {})
        if 'lowerbound' in output or returned.get('fval') is not None:
            found.append({'round': index, 'origin': 'final_output',
                          'lowerbound_J': output.get('lowerbound'),
                          'objective_J': returned.get('fval'),
                          'absolute_gap_J': output.get('absolutegap'),
                          'relative_gap': output.get('relativegap'),
                          'exitflag': returned.get('exitflag'),
                          'budget_valid': returned.get('budget_valid'),
                          'solver_reported_only': True,
                          'independently_certified': False})
    return found


def _violations(result, scene_id, scope):
    return [{'scenario_id': scene_id, 'scope': scope, 'witness': deepcopy(item)}
            for item in result.get('violations', [])]


def execute_fixed_deployment(input_loader, workdir, *, fixed_deployment,
                             seconds=60, starts=None, clock=time.monotonic,
                             model_builder=build_model,
                             session_factory=MatlabSession,
                             solve=solve_with_feedback,
                             scene_evaluator=evaluate_scene,
                             aggregator=aggregate_scene_receipts,
                             builder_options=None):
    """Construct and solve all scenes of one complete, supplied deployment.

    ``input_loader(budget)`` returns the original ``(config, instance)``. The
    absolute deadline starts before that read and covers every construction,
    one fresh MATLAB startup, all requests/feedback, both continuous checks and
    aggregation. Scenes follow the original declared order, including zero-
    weight scenes. ``starts`` is an explicit fixture-only domain restriction;
    the original builder enforces that restriction. Injectable dependencies
    exist for deterministic small-domain prechecks, never reference answers.

    Solver-view evidence and original-input scene receipts are separate. If
    the latter cannot finish, the former remains diagnostic evidence but does
    not become a new scene/outer upper bound. A failed candidate never excludes
    its fixed deployment. Returned statuses/bounds remain solver-reported.
    """
    budget = MethodBudget(float(seconds), clock=clock)
    workdir = Path(workdir)
    if workdir.exists():
        raise FileExistsError(f'Invocation directory already exists: {workdir}')
    workdir.mkdir(parents=True, exist_ok=False)
    result = {
        'state': 'UNRESOLVED', 'reason': None, 'problem_id': None,
        'safe_candidate': None, 'safe_upper_bound_J': None,
        'aggregation': None, 'scenes': {}, 'violations': [],
        'rankable_energy': False, 'independently_proven_optimal': False,
        'independently_proven_infeasible': False,
        'certified_lower_bound_J': None, 'remaining_domain': 'retained',
        'deployment_feasibility': 'NOT_DECIDED', 'formal_comparison': False,
        'scope': 'fixed supplied deployment; small-domain end-to-end precheck',
        'global_deployment_search_performed': False,
        'candidate_and_cache_shared_between_calls': False,
        'solver_reported_bounds_aggregated': False,
        'first_safe_time_semantics': (
            'original-input scene receipt after final-returned integer candidate; '
            'not an online incumbent callback time'),
        'matlab_worker_ready': False, 'integer_solver_entered': False,
        'solver_request_attempts': 0,
    }
    instance = config = session = None
    models, observers, receipts, candidates = {}, {}, {}, {}
    active_stage = 'invocation_setup'
    active_scene = None
    constructor_cleanup_s = 0.0
    try:
        with budget.phase('input_read_and_expansion'):
            active_stage = 'input_read_and_expansion'
            loaded_config, loaded_instance = input_loader(budget)
            config, instance = deepcopy(loaded_config), deepcopy(loaded_instance)
        budget.check()
        with budget.phase('identity_and_scope_validation'):
            active_stage = 'identity_and_scope_validation'
            deployment = validate_fixed_deployment(instance, deepcopy(fixed_deployment))
            accuracy = _accuracy(config['accuracy_targets'])
            weights = [_q(scene['weight']) for scene in instance['scenarios']]
            if any(weight < 0 for weight in weights) or sum(weights) != 1:
                raise ValueError('scenario weights must be nonnegative and sum to one')
            flags = dict(DEFAULT_BUILDER_OPTIONS)
            if builder_options is not None:
                if set(builder_options) - set(flags):
                    raise ValueError('unsupported builder option')
                if any(not isinstance(value, bool) for value in builder_options.values()):
                    raise ValueError('builder flags must be booleans')
                flags.update(builder_options)
            result.update(problem_id=instance['id'], fixed_deployment=deepcopy(deployment),
                identity={'full_input_sha256': canonical_hash(instance),
                          'config_sha256': canonical_hash(config),
                          'fixed_deployment_sha256': canonical_hash(deployment),
                          'accuracy_sha256': canonical_hash(accuracy)},
                builder_options=flags, original_scene_order=[s['id'] for s in instance['scenarios']],
                original_scene_weights={s['id']: s['weight'] for s in instance['scenarios']})
            result['scenes'] = {scene['id']: {
                'state': 'UNRESOLVED', 'reason': 'NOT_PROCESSED',
                'model_complete': False, 'solver_result': None,
                'scene_receipt': None, 'safe_candidate': None,
                'safe_upper_bound_J': None, 'first_safe_at_s': None,
                'solver_reported_bounds': [], 'deployment_feasibility': 'NOT_DECIDED',
            } for scene in instance['scenarios']}
        budget.check()
        for index, scene in enumerate(instance['scenarios']):
            active_scene = scene['id']
            record = result['scenes'][active_scene]
            active_stage = 'model_construction'
            observer = BuildObserver(budget, workdir/f'build_scene_{index:03d}.jsonl')
            observers[active_scene] = observer
            with budget.phase('model_construction'):
                model = model_builder(instance, config, starts=starts, budget=budget,
                    progress=observer, fixed_deployment=deployment,
                    fixed_scene_id=active_scene, **flags)
                observer.finish('MODEL_CONSTRUCTED')
                models[active_scene] = model
                record.update(model_complete=True, reason='MODEL_CONSTRUCTED',
                    model_completed_at_s=budget.elapsed,
                    model_summary=model.summary(),
                    preprocessing=deepcopy(getattr(model, 'preprocessing', None)))
            budget.check()

        active_scene = None
        active_stage = 'solver_startup'
        with budget.phase('solver_startup'):
            session = session_factory(workdir/'matlab', total_budget_s=budget.remaining,
                                      budget=budget)
        budget.check()
        result['matlab_worker_ready'] = True
        for scene in instance['scenarios']:
            active_scene = scene['id']
            record = result['scenes'][active_scene]
            model = models[active_scene]
            budget.check()
            active_stage = 'candidate_search'
            record['search_started_at_s'] = budget.elapsed
            solved = solve(model, session, accuracy, budget=budget)
            # Copy all committed evidence before checking the shared deadline.
            record['solver_result'] = solved
            record['search_returned_at_s'] = budget.elapsed
            record['solver_reported_bounds'] = _reported_bounds(solved)
            record['reason'] = solved.get('reason')
            evaluation = solved.get('evaluation') or {}
            result['violations'].extend(_violations(evaluation, active_scene, 'solver_model_view'))
            if solved.get('state') == 'SAFE':
                record['solver_view_safe_evidence'] = {
                    'safe_candidate': deepcopy(solved.get('safe_candidate')),
                    'safe_upper_bound_J': solved.get('safe_upper_bound_J'),
                    'completed_at_elapsed_s': evaluation.get('completed_at_elapsed_s'),
                    'scope': 'model-view diagnostic; not original-input scene receipt or outer U'}
            budget.check()
            if solved.get('state') != 'SAFE' or solved.get('safe_candidate') is None:
                continue
            candidate = deepcopy(solved['safe_candidate'])
            record['attempted_candidate'] = candidate
            active_stage = 'original_input_scene_evaluation'
            with budget.phase('original_input_scene_evaluation'):
                receipt = scene_evaluator(instance, active_scene, deployment,
                                          candidate, accuracy, budget)
            # The original-input adapter owns its in-budget commit timestamp.
            # Preserve a receipt/violation even when transfer happens late.
            record['scene_receipt'] = receipt
            receipts[active_scene], candidates[active_scene] = receipt, candidate
            record.update(state=receipt['state'], reason=receipt.get('reason'))
            identity_valid = (receipt.get('identity') == _identity(
                instance, active_scene, deployment, candidate, accuracy, budget)
                and receipt.get('receipt_sha256') == _receipt_hash(receipt))
            record['original_receipt_identity_valid'] = identity_valid
            if identity_valid:
                result['violations'].extend(_violations(
                    receipt, active_scene, 'original_input_scene_receipt'))
            else:
                record.update(state='UNRESOLVED', reason='ORIGINAL_RECEIPT_IDENTITY_MISMATCH')
            consistent = None
            if identity_valid and receipt.get('state') == 'SAFE' and receipt.get('rankable_energy'):
                before, after = evaluation.get('weighted_energy_J'), receipt.get('energy_J')
                # The model view has objective weight one. Both independent
                # checks cover this same physical candidate and window.
                if before is not None and after is not None:
                    consistent = (max(_q(before[0]), _q(after[0]))
                                  <= min(_q(before[1]), _q(after[1])))
                if consistent is False:
                    record.update(state='UNRESOLVED', reason='INCONSISTENT_SAFE_ENERGY_RECEIPTS')
            elif identity_valid and receipt.get('state') in ('THERMAL_VIOLATION', 'INVALID_SCHEDULE'):
                consistent = False
                record.update(state='UNRESOLVED', reason='INCONSISTENT_SOLVER_VIEW_AND_ORIGINAL_RECEIPT')
            record['consistent_with_solver_view'] = consistent
            if record['state'] == 'SAFE' and receipt.get('rankable_energy'):
                record.update(safe_candidate=candidate,
                    safe_upper_bound_J=receipt['safe_upper_bound_J'],
                    first_safe_at_s=receipt['completed_at_elapsed_s'],
                    deployment_feasibility='SCENE_SAFE_WITNESS')
            budget.check()

        active_scene = None
        if len(receipts) == len(instance['scenarios']) and all(
                record['state'] == 'SAFE' for record in result['scenes'].values()):
            active_stage = 'outer_weighted_aggregation'
            with budget.phase('outer_weighted_aggregation'):
                aggregation = aggregator(instance, deployment, receipts, candidates,
                                         accuracy, budget)
            result['aggregation'] = aggregation
            if aggregation.get('state') == 'SAFE' and aggregation.get('rankable_energy'):
                result.update(state='SAFE', reason='ALL_ORIGINAL_SCENE_RECEIPTS_SAFE',
                    safe_candidate={'scenes': {sid: deepcopy(candidate['scenes'][sid])
                                              for sid, candidate in candidates.items()}},
                    safe_upper_bound_J=aggregation['safe_upper_bound_J'],
                    rankable_energy=True,
                    first_safe_at_s=aggregation['completed_at_elapsed_s'],
                    deployment_feasibility='ALL_SCENES_SAFE_WITNESS')
            else:
                result['reason'] = aggregation.get('reason') or 'AGGREGATION_UNRESOLVED'
            budget.check()
        else:
            result['reason'] = 'NOT_ALL_ORIGINAL_SCENES_HAVE_SAFE_RECEIPTS'
    except Exhausted as error:
        if hasattr(error, 'matlab_cleanup'):
            result['startup_cleanup'] = error.matlab_cleanup
            constructor_cleanup_s = error.matlab_cleanup.get('cleanup_wall_seconds', 0.0)
        result['reason'] = str(error)
    except MemoryError:
        result['reason'] = 'RESOURCE_LIMIT'
    except (KeyError, TypeError, ValueError) as error:
        result.update(reason='INVALID_INPUT_OR_INTERFACE',
                      error=f'{type(error).__name__}: {error}')
    except Exception as error:
        if hasattr(error, 'matlab_cleanup'):
            result['startup_cleanup'] = error.matlab_cleanup
            constructor_cleanup_s = error.matlab_cleanup.get('cleanup_wall_seconds', 0.0)
        result.update(reason=('WALL_TIME_LIMIT' if budget.elapsed-constructor_cleanup_s >= budget.seconds
                              else 'INTERFACE_ERROR'),
                      error=f'{type(error).__name__}: {error}')
    finally:
        stopped = budget.elapsed
        method_elapsed = max(0.0, stopped-constructor_cleanup_s)
        result['stop_stage'], result['stop_scene'] = active_stage, active_scene
        result['budget_exhausted'] = method_elapsed >= budget.seconds
        result['timing'] = budget.summary(stopped)
        result['timing'].update(method_elapsed_s=method_elapsed,
            method_elapsed_excluding_cleanup_s=method_elapsed,
            wall_until_constructor_cleanup_return_s=stopped,
            startup_failure_cleanup_in_method_elapsed_s=constructor_cleanup_s,
            deadline_overshoot_s=max(0.0, method_elapsed-budget.seconds),
            cleanup_s=constructor_cleanup_s)
        if constructor_cleanup_s:
            totals = result['timing']['phases_exclusive_s']
            totals['solver_startup'] = max(0.0, totals.get('solver_startup', 0)-constructor_cleanup_s)
            for frame in result['timing']['phase_records']:
                if frame['phase'] == 'solver_startup':
                    frame['startup_cleanup_inclusive_s'] = constructor_cleanup_s
                    frame['exclusive_s'] = max(0.0, frame['exclusive_s']-constructor_cleanup_s)
            result['timing']['unattributed_s'] = max(0.0, method_elapsed-sum(totals.values()))
        cleanup_started = clock()
        if session is not None:
            try:
                session.close()
            except Exception as error:
                result['cleanup_error'] = f'{type(error).__name__}: {error}'
        result['timing']['cleanup_s'] += clock()-cleanup_started
        result['solver_request_attempts'] = getattr(session, 'counter', 0)
        rounds = [returned for item in result['scenes'].values()
                  for returned in (item.get('solver_result') or {}).get('rounds', [])]
        entries = [returned.get('intlinprog_entered') for returned in rounds]
        result['integer_solver_entered'] = (True if True in entries else
            False if not result['solver_request_attempts'] or
                (entries and all(value is False for value in entries)) else None)
        result['integer_solver_entry_evidence'] = 'returned worker records; null means unconfirmed'

    # Archival only after stop: never solve, evaluate, aggregate, or create U.
    archive_started = clock()
    for scene_id, observer in observers.items():
        record = result['scenes'][scene_id]
        record['construction'] = (observer.snapshot() if observer.finished_at is not None
            else observer.finish('CONSTRUCTION_INTERRUPTED'))
    if config is not None:
        _save(workdir/'input_config.json', config)
    if instance is not None:
        _save(workdir/'input_instance.json', instance)
    result['environment'] = {'python': sys.version, 'platform': platform.platform(),
        'scope': 'single-deployment correctness/precheck; no formal performance comparison'}
    result['counted_energy_source'] = 'matching original-input adapter receipts only'
    result['timing']['postprocess_before_serialization_s'] = clock()-archive_started
    _save(workdir/'result.json', result)
    _save(workdir/'archive_timing.json', {
        'report_wall_s': clock()-archive_started,
        'scope': 'serialization of already committed evidence; no search or energy supplementation',
        'includes_own_file_write': False})
    return result
