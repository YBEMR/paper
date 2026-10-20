"""Fresh-seed N1 search, original-input acceptance, one absolute budget.

This local method fixes every execution unit to this invocation's complete
SAFE constructor seed. Only explicitly named scene-local Stages retain their
original OPP/start choices. It neither deletes those choices from the original
problem nor upgrades neighborhood solver reports to global certificates.
"""
from copy import deepcopy
import math
from pathlib import Path
import platform
import sys
import time

from build_observer import BuildObserver
from control_policy import resolve_idle_policy
from formal_milp import OUTER_ROUND_LIMIT, _checked_thermal_witnesses
from initial_point import _InitialSession, complete_initial_point
from initial_schedule import iter_initial_candidates
from matlab_bridge import MatlabSession, NUMERICAL_CONSISTENCY_UNRESOLVED, cleanup_is_complete
from milp import add_thermal_feedback, build_model, decode, evaluate_model_candidate, _digest
from neighborhood import (PROTOCOL as N1_CONDITION_PROTOCOL, check_n1_candidate,
                          make_n1_condition)
from neighborhood_adapter import PROTOCOL as N1_EVALUATION_PROTOCOL, evaluate_n1_scene
from partial_method import (PartialRecorder, _bound_gaps, _change, _default_bounds,
    _detach_observer, _safe, _solve_scene, _validate_bounds_receipt)
from scene_adapter import (PARTIAL_PROTOCOL, _local_candidate_deployment,
    _partial_identity, _partial_scene_energy, _receipt_hash,
    aggregate_partial_scene_receipts, canonical_hash, evaluate_partial_scene,
    shared_deployment_ids, validate_shared_deployment)
from scene_method import DEFAULT_BUILDER_OPTIONS, _reported_bounds, _save, _violations
from thermal import Exhausted, _accuracy, _q
from timing import MethodBudget


PROTOCOL = 'fresh-seed-n1-live-scenes-v1'


class _NoCompleteSafeSeed(Exception):
    pass


def _constructor_view(instance, deployment, budget):
    """Only constrain the fresh constructor's shared-unit choices; no physics edit."""
    view = deepcopy(instance)
    for shared_id, unit in deployment.items():
        budget.check()
        view['stage_modes'][shared_id] = [mode for mode in view['stage_modes'][shared_id]
                                          if mode['unit_id'] == unit]
    return view


def execute_n1_neighborhood(input_loader, workdir, *, shared_deployment,
        opened_by_scene, seconds=60, starts=None, clock=time.monotonic,
        budget=None, seed_iterator=iter_initial_candidates,
        seed_scene_evaluator=evaluate_partial_scene,
        condition_factory=make_n1_condition, model_builder=build_model,
        initial_completer=complete_initial_point,
        model_evaluator=evaluate_model_candidate,
        n1_scene_evaluator=evaluate_n1_scene,
        aggregator=aggregate_partial_scene_receipts,
        recorder_factory=PartialRecorder, session_factory=MatlabSession,
        feedback_adder=add_thermal_feedback,
        witness_validator=_checked_thermal_witnesses,
        bounds_provider=_default_bounds, checkpoint=None, builder_options=None,
        max_rounds=OUTER_ROUND_LIMIT, close_session=True, scene_slice_s=None,
        on_global_update=None, membership_checker=check_n1_candidate,
        evaluation_protocol=N1_EVALUATION_PROTOCOL,
        condition_protocol=N1_CONDITION_PROTOCOL, _method_identity=None):
    """Build a fresh complete SAFE seed, then search its declared N1 domain.

    Input expansion, at most three original constructor templates, original
    continuous checks, condition construction, physical model/x0 construction,
    worker startup, callback checks, feedback and aggregate updates all use one
    MethodBudget. No seed, candidate, receipt or cache is supplied by callers.
    Injectable operations exist for bounded correctness prechecks.

    Missing/rejected x0 permits bare MILP within the same complete N1 model;
    missing full SAFE seed does not. Existing SAFE/violations survive a later
    expiry; no post-cutoff evaluation or weighted U is manufactured.
    """
    external_budget = budget is not None
    if external_budget:
        if not isinstance(budget, MethodBudget):
            raise TypeError('budget must be the caller-owned MethodBudget')
        clock = budget.clock
    else:
        budget = MethodBudget(float(seconds), clock=clock)
    labels = {
        'protocol': PROTOCOL, 'name': 'N1',
        'search_scope': 'this invocation seed-defined N1 only; original domain retained',
        'initialisation_fallback': 'rejected x0 permits bare N1 MILP; missing complete SAFE seed stops',
        'inner_solution_source': 'N1_inner_MILP',
        'model_violation_source': 'N1_solver_model_view',
        'original_violation_source': 'N1_original_input_scene_receipt',
        'original_evaluation_phase': 'original_input_n1_scene_evaluation',
        'model_evaluation_phase': 'initial_n1_model_view_evaluation',
        'no_seed_reason': 'NO_COMPLETE_SAFE_N1_SEED',
        'bound_scope': 'seed_defined_N1_fixed_shared_deployment_unweighted_scene',
        'environment_scope': 'fresh SAFE seed N1 correctness/method invocation; not a formal comparison'}
    if _method_identity is not None:
        if (not isinstance(_method_identity, dict) or set(_method_identity) != set(labels)
                or any(not isinstance(value, str) or not value for value in _method_identity.values())):
            raise ValueError('Complete method identity required for an adapted lifecycle')
        labels = dict(_method_identity)
    if (not callable(membership_checker) or not isinstance(evaluation_protocol, str)
            or not evaluation_protocol or not isinstance(condition_protocol, str)
            or not condition_protocol):
        raise ValueError('A membership checker and explicit protocol identities are required')
    if type(close_session) is not bool:
        raise ValueError('close_session must be boolean')
    if scene_slice_s is not None:
        if (isinstance(scene_slice_s, bool) or not isinstance(scene_slice_s, (int, float))
                or not math.isfinite(scene_slice_s) or scene_slice_s <= 0):
            raise ValueError('scene_slice_s must be finite and positive')
        scene_slice_s = float(scene_slice_s)
    if on_global_update is not None and not callable(on_global_update):
        raise TypeError('on_global_update must be callable')
    invocation_started = budget.elapsed
    workdir = Path(workdir)
    if workdir.exists():
        raise FileExistsError(f'Invocation directory already exists: {workdir}')
    workdir.mkdir(parents=True, exist_ok=False)
    result = {'protocol': labels['protocol'], 'state': 'UNRESOLVED', 'reason': None,
        'problem_id': None, 'safe_candidate': None, 'safe_upper_bound_J': None,
        'weighted_energy_J': None, 'rankable_energy': False, 'aggregation': None,
        'global_updates': [], 'scenes': {}, 'violations': [], 'seed_attempts': [],
        'initial_global_safe_upper_bound_J': None,
        'initial_global_weighted_energy_J': None, 'safe_solution_source': None,
        'condition': None, 'independently_proven_optimal': False,
        'independently_proven_infeasible': False, 'remaining_domain': 'retained',
        'deployment_feasibility': 'NOT_DECIDED',
        'global_deployment_search_performed': False, 'formal_comparison': False,
        'candidate_and_cache_shared_between_calls': False,
        'solver_reported_bounds_aggregated': False, 'matlab_worker_ready': False,
        'external_budget': external_budget, 'close_session_requested': close_session,
        'scene_slice_s': scene_slice_s, 'worker_reusable': True,
        'search_scope': labels['search_scope'],
        'initialisation_fallback': labels['initialisation_fallback'],
        'scene_budget_policy': 'original scene order, one absolute remaining budget; no reset',
        'inner_MILP_improved_initial_upper_bound': False,
        'strict_improvement_over_initial_certified': False}
    models, observers, initial, receipts, candidates, sources, caches = {}, {}, {}, {}, {}, {}, {}
    config = instance = session = condition = None
    active_stage, active_scene = 'invocation_setup', None
    constructor_cleanup_s = 0.0
    session_counter_at_entry = 0

    def validate_original_receipt(sid, candidate, receipt):
        local = _local_candidate_deployment(instance, sid, candidate)
        expected = _partial_identity(instance, deployment, accuracy, budget,
            scene_id=sid, candidate=candidate, local_deployment=local)
        matches = (receipt.get('protocol') == PARTIAL_PROTOCOL
            and receipt.get('identity') == expected
            and receipt.get('receipt_sha256') == _receipt_hash(receipt)
            and receipt.get('shared_deployment') == deployment
            and receipt.get('shared_stage_ids') == result['shared_stage_ids']
            and receipt.get('local_deployment') == local and receipt.get('unweighted') is True)
        if not matches:
            raise ValueError('Original-input scene receipt identity mismatch')
        return local

    def commit_aggregate(aggregation, sid, source):
        # The aggregation operation owns timestamp/identity checks; transfer
        # its already formed SAFE before any current-clock check.
        result.setdefault('aggregation_attempts', []).append(deepcopy(aggregation))
        if not _safe(aggregation, budget):
            return False
        previous = result['weighted_energy_J']
        if (result['safe_upper_bound_J'] is not None and
                _q(aggregation['safe_upper_bound_J']) >= _q(result['safe_upper_bound_J'])):
            return False
        change = _change(previous, aggregation['weighted_energy_J'])
        update = {'trigger_scene': sid, 'trigger_source': source,
            'scene_sources': deepcopy(sources),
            'weighted_energy_J': deepcopy(aggregation['weighted_energy_J']),
            'safe_upper_bound_J': aggregation['safe_upper_bound_J'],
            'committed_at_s': aggregation['completed_at_elapsed_s'],
            'transferred_at_s': budget.elapsed, **change}
        result['global_updates'].append(update)
        all_initial = all(value == 'initial_constructor' for value in sources.values())
        result.update(state='SAFE', safe_candidate=deepcopy(aggregation['safe_candidate']),
            safe_upper_bound_J=aggregation['safe_upper_bound_J'],
            weighted_energy_J=deepcopy(aggregation['weighted_energy_J']), rankable_energy=True,
            aggregation=deepcopy(aggregation),
            safe_solution_source='initial_constructor' if all_initial else labels['inner_solution_source'],
            deployment_feasibility='ALL_SCENES_SAFE_WITNESS')
        result.setdefault('first_safe_at_s', aggregation['completed_at_elapsed_s'])
        if all_initial and result['initial_global_safe_upper_bound_J'] is None:
            result['initial_global_safe_upper_bound_J'] = aggregation['safe_upper_bound_J']
            result['initial_global_weighted_energy_J'] = deepcopy(aggregation['weighted_energy_J'])
        if on_global_update is not None:
            update['observer_requested_at_s'] = budget.elapsed
            try:
                on_global_update(result, update)
            except Exception as error:
                update['observer_error'] = f'{type(error).__name__}: {error}'
                raise
            update['observer_completed_at_s'] = budget.elapsed
        bounds = result.get('deployment_bounds') or {}
        if budget.elapsed < budget.seconds and all(bounds.get(key) is not None for key in ('L0', 'L_a')):
            gaps = _bound_gaps(result['deployment_bounds'], result['safe_upper_bound_J'])
            result['independent_gaps'] = gaps
            update['independent_gaps'] = deepcopy(gaps)
        result['inner_MILP_improved_initial_upper_bound'] = (
            result['initial_global_safe_upper_bound_J'] is not None and
            _q(result['safe_upper_bound_J']) < _q(result['initial_global_safe_upper_bound_J']))
        result['strict_improvement_over_initial_certified'] = (
            result['initial_global_weighted_energy_J'] is not None and
            _q(result['weighted_energy_J'][1]) < _q(result['initial_global_weighted_energy_J'][0]))
        return True

    def store_scene(sid, candidate, receipt, source):
        record = result['scenes'][sid]
        energy = _partial_scene_energy(instance, sid, receipt, budget).data()
        local = _local_candidate_deployment(instance, sid, candidate)
        before = receipts.get(sid)
        change = _change(before.get('energy_J') if before else None, energy)
        receipts[sid], candidates[sid], sources[sid] = deepcopy(receipt), deepcopy(candidate), source
        record.update(state='SAFE', scene_receipt=deepcopy(receipt),
            safe_candidate=deepcopy(candidate), safe_upper_bound_J=receipt['safe_upper_bound_J'],
            local_deployment=deepcopy(local), best_source=source,
            deployment_feasibility='SCENE_SAFE_WITNESS')
        if record['first_safe_at_s'] is None:
            record['first_safe_at_s'] = receipt['completed_at_elapsed_s']
        record['updates'].append({'source': source, 'energy_J': deepcopy(energy),
            'scene_committed_at_s': receipt['completed_at_elapsed_s'],
            'transferred_at_s': budget.elapsed, **change})

    def remember_view(sid, candidate, evaluation, source):
        result['scenes'][sid]['model_view_evaluations'].append({
            'candidate': deepcopy(candidate), 'evaluation': deepcopy(evaluation),
            'source': source, 'received_at_s': budget.elapsed})
        result['violations'].extend(_violations(evaluation, sid, labels['model_violation_source']))

    def publish_safe(sid, model, candidate, evaluation, source):
        record = result['scenes'][sid]
        expected = {'input_sha256': _digest(model.instance), 'candidate_sha256': _digest(candidate)}
        if not _safe(evaluation, budget) or evaluation.get('evidence_identity') != expected:
            raise ValueError('SAFE model-view receipt identity/timestamp mismatch')
        # A cache hit reuses physical evidence, never bypasses N1 membership.
        membership_checker(instance, condition, candidate, budget=budget, scene_id=sid)
        key = canonical_hash(candidate)
        if key in caches[sid]:
            record['original_receipt_cache_hits'] += 1
            cached = caches[sid][key]
            if cached.get('state') in ('THERMAL_VIOLATION', 'INVALID_SCHEDULE'):
                raise ValueError('SAFE model-view candidate conflicts with cached original receipt')
            validate_original_receipt(sid, candidate, cached)
            energy = _partial_scene_energy(instance, sid, cached, budget).data()
            view_energy = evaluation.get('weighted_energy_J')
            if (view_energy is None or max(_q(view_energy[0]), _q(energy[0]))
                    > min(_q(view_energy[1]), _q(energy[1]))):
                raise ValueError('Cached original-input and model-view SAFE energies disagree')
            return
        with budget.phase(labels['original_evaluation_phase']):
            wrapper = n1_scene_evaluator(instance, condition, sid, candidate,
                                         budget=budget, accuracy=accuracy)
        receipt = wrapper.get('receipt')
        attempt = {'candidate': deepcopy(candidate), 'wrapper': deepcopy(wrapper),
            'receipt': deepcopy(receipt), 'source': source,
            'received_at_s': budget.elapsed, 'accepted_safe': False}
        record['original_scene_evaluations'].append(attempt)
        # Preserve any inner physical violation before checking wrapper status
        # or whether its transfer crossed the absolute deadline.
        if isinstance(receipt, dict):
            result['violations'].extend(_violations(receipt, sid, labels['original_violation_source']))
        if receipt is None:
            if wrapper.get('state') == 'INVALID_INPUT':
                raise ValueError(labels['name']+' candidate membership/adapter rejection: '+str(wrapper.get('reason')))
            return
        if (wrapper.get('protocol') != evaluation_protocol
                or wrapper.get('member') is not True
                or wrapper.get('condition_sha256') != condition['condition_sha256']):
            raise ValueError(labels['name']+' wrapper condition identity mismatch')
        validate_original_receipt(sid, candidate, receipt)
        if receipt.get('state') in ('THERMAL_VIOLATION', 'INVALID_SCHEDULE'):
            caches[sid][key] = deepcopy(receipt)
            raise ValueError('SAFE '+labels['name']+' model-view candidate disagrees with original input')
        if not (wrapper.get('rankable_energy') is True and _safe(receipt, budget)):
            return
        energy = _partial_scene_energy(instance, sid, receipt, budget).data()
        view_energy = evaluation.get('weighted_energy_J')
        if (view_energy is None or max(_q(view_energy[0]), _q(energy[0]))
                > min(_q(view_energy[1]), _q(energy[1]))):
            raise ValueError(labels['name']+' model-view and original-input SAFE energies disagree')
        attempt['accepted_safe'] = True
        caches[sid][key] = deepcopy(receipt)
        previous = receipts.get(sid)
        if previous is not None and _q(receipt['safe_upper_bound_J']) >= _q(previous['safe_upper_bound_J']):
            return
        store_scene(sid, candidate, receipt, source)
        budget.check()
        with budget.phase('outer_weighted_aggregation'):
            aggregation = aggregator(instance, deployment, receipts, candidates, accuracy, budget)
        commit_aggregate(aggregation, sid, source)

    try:
        with budget.phase('input_read_and_expansion'):
            active_stage = 'input_read_and_expansion'
            loaded_config, loaded_instance = input_loader(budget)
            config, instance = deepcopy(loaded_config), deepcopy(loaded_instance)
        budget.check()
        with budget.phase('identity_and_scope_validation'):
            active_stage = 'identity_and_scope_validation'
            deployment = validate_shared_deployment(instance, deepcopy(shared_deployment))
            policy = resolve_idle_policy(instance)
            if resolve_idle_policy(config) != policy:
                raise ValueError('Instance/config control policies must match')
            accuracy = _accuracy(config['accuracy_targets'])
            weights = [_q(scene['weight']) for scene in instance['scenarios']]
            if not weights or any(weight < 0 for weight in weights) or sum(weights) != 1:
                raise ValueError('Scenario weights must be nonnegative and sum to one')
            if isinstance(max_rounds, bool) or not isinstance(max_rounds, int) or not 1 <= max_rounds <= OUTER_ROUND_LIMIT:
                raise ValueError('max_rounds must be in 1..50')
            flags = dict(DEFAULT_BUILDER_OPTIONS)
            if builder_options is not None:
                if (set(builder_options)-(set(flags)|{'cumulative_precedence'})
                        or any(type(value) is not bool for value in builder_options.values())):
                    raise ValueError('Unsupported builder flags')
                flags.update(builder_options)
            # There is no automatic interpretation of main/post names. The
            # condition factory checks the explicit scene/instance IDs.
            declared_opened = deepcopy(opened_by_scene)
            result.update(problem_id=instance['id'], shared_stage_ids=shared_deployment_ids(instance),
                shared_deployment=deepcopy(deployment), control_policy=policy,
                opened_by_scene=declared_opened, builder_options=flags, outer_round_limit=max_rounds,
                identity={'full_input_sha256': canonical_hash(instance),
                    'config_sha256': canonical_hash(config),
                    'shared_deployment_sha256': canonical_hash(deployment),
                    'accuracy_sha256': canonical_hash(accuracy)},
                original_scene_order=[scene['id'] for scene in instance['scenarios']],
                original_scene_weights={scene['id']: scene['weight'] for scene in instance['scenarios']})
            for scene in instance['scenarios']:
                sid = scene['id']; caches[sid] = {}
                result['scenes'][sid] = {'state': 'UNRESOLVED', 'reason': 'NOT_PROCESSED',
                    'model_complete': False, 'initialisation': None, 'solver_result': None,
                    'scene_receipt': None, 'safe_candidate': None, 'safe_upper_bound_J': None,
                    'first_safe_at_s': None, 'updates': [], 'model_view_evaluations': [],
                    'original_scene_evaluations': [], 'original_receipt_cache_hits': 0,
                    'solver_reported_bounds': [], 'deployment_feasibility': 'NOT_DECIDED'}
        with budget.phase('deployment_bound_construction'):
            active_stage = 'deployment_bound_construction'
            if bounds_provider is _default_bounds:
                from partial_bounds import independent_lower_bound
                # Transfer L0 before attempting La. A later interruption must
                # not erase the independent evidence already completed here.
                result['deployment_bounds'] = {
                    'L0': independent_lower_bound(instance, None, budget), 'L_a': None}
                result['deployment_bounds']['L_a'] = independent_lower_bound(
                    instance, deployment, budget)
                raw_bounds = result['deployment_bounds']
            else:
                raw_bounds = bounds_provider(instance, deployment, budget)
            result['deployment_bounds'] = _validate_bounds_receipt(
                raw_bounds, instance, deployment, policy, budget)
        budget.check()
        active_stage = 'fresh_seed_construction'
        with budget.phase('fresh_seed_constructor_view'):
            view = _constructor_view(instance, deployment, budget)
            result['seed_constructor_input_sha256'] = canonical_hash(view)
        iterator = seed_iterator(view, starts=starts, budget=budget, max_attempts=3)
        seed_candidate = seed_aggregate = None
        while True:
            with budget.phase('initial_schedule_construction'):
                try:
                    attempt = next(iterator)
                except StopIteration:
                    break
            attempt_record = {'construction': deepcopy(attempt),
                'schedule_completed_at_s': budget.elapsed, 'scene_evaluations': {},
                'state': 'UNRESOLVED', 'aggregation': None}
            result['seed_attempts'].append(attempt_record)
            if attempt.get('status') != 'COMPLETE_LEGAL_CANDIDATE':
                attempt_record['reason'] = 'CONSTRUCTION_UNRESOLVED'
                budget.check()
                continue
            current = deepcopy(attempt['candidate'])
            trial_receipts, trial_candidates = {}, {}
            for scene in instance['scenarios']:
                active_scene = sid = scene['id']
                local = {'scenes': {sid: deepcopy(current['scenes'][sid])}}
                with budget.phase('initial_original_input_scene_evaluation'):
                    receipt = seed_scene_evaluator(instance, sid, deployment, local, accuracy, budget)
                attempt_record['scene_evaluations'][sid] = deepcopy(receipt)
                result['violations'].extend(_violations(receipt, sid, 'fresh_seed_original_input'))
                validate_original_receipt(sid, local, receipt)
                if not _safe(receipt, budget):
                    attempt_record['reason'] = receipt.get('reason') or receipt.get('state')
                    budget.check()
                    break
                # These local receipts remain visible even if the next scene
                # or aggregate is interrupted. They are not a weighted U.
                trial_receipts[sid], trial_candidates[sid] = deepcopy(receipt), local
                budget.check()
            else:
                with budget.phase('initial_outer_weighted_aggregation'):
                    aggregation = aggregator(instance, deployment, trial_receipts,
                                             trial_candidates, accuracy, budget)
                attempt_record['aggregation'] = deepcopy(aggregation)
                if _safe(aggregation, budget):
                    for sid in trial_receipts:
                        store_scene(sid, trial_candidates[sid], trial_receipts[sid], 'initial_constructor')
                        caches[sid][canonical_hash(trial_candidates[sid])] = deepcopy(trial_receipts[sid])
                    commit_aggregate(aggregation, None, 'initial_constructor')
                    seed_candidate = deepcopy(aggregation['safe_candidate'])
                    seed_aggregate = deepcopy(aggregation)
                    attempt_record.update(state='SAFE', reason='COMPLETE_SAFE_SEED')
                    break
                attempt_record['reason'] = aggregation.get('reason') or aggregation.get('state')
            budget.check()
        if seed_aggregate is None:
            result['reason'] = labels['no_seed_reason']
            result['worker_reusable'] = False
            raise _NoCompleteSafeSeed()
        active_scene = None
        budget.check()
        active_stage = 'neighborhood_condition_construction'
        with budget.phase('neighborhood_condition_construction'):
            condition = condition_factory(instance, deployment, seed_candidate, seed_aggregate,
                declared_opened, budget=budget, accuracy=accuracy)
            if condition.get('protocol') != condition_protocol:
                raise ValueError('Neighborhood condition protocol does not match this lifecycle')
            result['condition'] = deepcopy(condition)
            result['condition_sha256'] = condition['condition_sha256']
        budget.check()
        for index, scene in enumerate(instance['scenarios']):
            active_scene = sid = scene['id']; record = result['scenes'][sid]
            active_stage = 'model_construction'
            observer = BuildObserver(budget, workdir/f'build_scene_{index:03d}.jsonl')
            observers[sid] = observer
            with budget.phase('model_construction'):
                model = model_builder(instance, config, starts=starts, budget=budget, progress=observer,
                    fixed_shared_deployment=deployment, fixed_scene_id=sid,
                    neighborhood_condition=condition, **flags)
                models[sid] = model
                observer.finish('MODEL_CONSTRUCTED')
                record.update(model_complete=True, model_completed_at_s=budget.elapsed,
                    model_summary=model.summary(), preprocessing=deepcopy(getattr(model, 'preprocessing', None)))
            budget.check()
            active_stage = 'initial_point_preparation'
            local = {'scenes': {sid: deepcopy(seed_candidate['scenes'][sid])}}
            with budget.phase(labels['model_evaluation_phase']):
                evaluation = model_evaluator(model, local, accuracy, budget)
            remember_view(sid, local, evaluation, 'initial_constructor')
            completion = {'state': 'INITIAL_POINT_REJECTED', 'x0': None,
                          'reason': 'MODEL_VIEW_SAFE_NOT_CONFIRMED'}
            if _safe(evaluation, budget):
                publish_safe(sid, model, local, evaluation, 'initial_constructor')
                completion = initial_completer(model, local, evaluation, budget)
            elif evaluation.get('state') in ('THERMAL_VIOLATION', 'INVALID_SCHEDULE'):
                raise ValueError('Fresh SAFE seed disagrees with '+labels['name']+' model view')
            initial[sid] = completion
            record['initialisation'] = {
                'candidate': local, 'evaluation': deepcopy(evaluation),
                'completion': deepcopy({key: value for key, value in completion.items() if key != 'x0'}),
                'state': completion.get('state'), 'completed_at_s': budget.elapsed}
            record['initial_checkpoint'] = {'requested': True, 'completed': False}
            with budget.phase('initial_receipt_checkpoint'):
                if checkpoint is None:
                    _save(workdir/f'initial_scene_{index:03d}.json', record['initialisation'])
                else:
                    checkpoint(sid, record['initialisation'], budget)
            record['initial_checkpoint'].update(completed=True, completed_at_s=budget.elapsed)
            budget.check()
        active_scene = None
        active_stage = 'solver_startup'
        with budget.phase('solver_startup'):
            session = session_factory(workdir/'matlab', total_budget_s=budget.remaining, budget=budget)
            session_counter_at_entry = getattr(session, 'counter', 0)
            if (getattr(session, 'closed', False) or getattr(session, 'request_blocked', False)
                    or getattr(session, 'event_consumer', None) is not None):
                raise ValueError('Worker is not idle and reusable')
            if getattr(session, 'budget', budget) is not budget:
                raise ValueError('Worker must use the identical MethodBudget')
        budget.check()
        result['matlab_worker_ready'] = True
        for index, scene in enumerate(instance['scenarios']):
            active_scene = sid = scene['id']; record = result['scenes'][sid]
            budget.check(); active_stage = 'candidate_search'
            folder = workdir/f'scene_{index}'
            folder.mkdir()
            model = models[sid]
            recorder = recorder_factory(model, accuracy, budget, folder,
                model_evaluator=model_evaluator,
                on_evaluation=lambda candidate, evaluation, source, sid=sid:
                    remember_view(sid, candidate, evaluation, source),
                on_safe=lambda candidate, evaluation, source, sid=sid, model=model:
                    publish_safe(sid, model, candidate, evaluation, source),
                witness_validator=witness_validator)
            prepared = initial[sid]
            ready = prepared.get('state') == 'INITIAL_POINT_READY' and prepared.get('x0') is not None
            inner_session = _InitialSession(session, prepared['x0']) if ready else session
            record.update(x0_injected=ready, bare_MILP_fallback=not ready,
                          search_started_at_s=budget.elapsed)
            solved = _solve_scene(model, inner_session, accuracy, budget, recorder,
                feedback_adder=feedback_adder, witness_validator=witness_validator,
                max_rounds=max_rounds, scene_slice_s=scene_slice_s)
            record.update(solver_result=solved, reason=solved['reason'],
                          search_returned_at_s=budget.elapsed)
            record['solver_reported_bounds'] = [dict(item,
                scope=labels['bound_scope'],
                condition_sha256=condition['condition_sha256']) for item in _reported_bounds(solved)]
            result['worker_reusable'] = solved['worker_reusable']
            budget.check()
            if not solved['worker_reusable']:
                result['reason'] = solved['reason']; break
        else:
            result['reason'] = 'SCENE_SEARCH_SEQUENCE_COMPLETE'
    except _NoCompleteSafeSeed:
        pass
    except Exhausted as error:
        result['reason'] = str(error)
        result['worker_reusable'] = False
        if hasattr(error, 'matlab_cleanup'):
            result['startup_cleanup'] = error.matlab_cleanup
            constructor_cleanup_s = error.matlab_cleanup.get('cleanup_wall_seconds', 0.0)
        if hasattr(error, 'matlab_startup_metadata'):
            result['startup_metadata'] = deepcopy(error.matlab_startup_metadata)
    except MemoryError:
        result['reason'] = 'RESOURCE_LIMIT'; result['worker_reusable'] = False
    except Exception as error:
        if hasattr(error, 'matlab_cleanup'):
            result['startup_cleanup'] = error.matlab_cleanup
            constructor_cleanup_s = error.matlab_cleanup.get('cleanup_wall_seconds', 0.0)
        if hasattr(error, 'matlab_startup_metadata'):
            result['startup_metadata'] = deepcopy(error.matlab_startup_metadata)
        result.update(reason='INVALID_INPUT_OR_INTERFACE' if isinstance(error, (KeyError, TypeError, ValueError))
                      else 'INTERFACE_ERROR', error=f'{type(error).__name__}: {error}')
        result['worker_reusable'] = False
    finally:
        stopped = budget.elapsed
        method_elapsed = max(0.0, stopped-constructor_cleanup_s)
        result.update(stop_stage=active_stage, stop_scene=active_scene,
                      budget_exhausted=method_elapsed >= budget.seconds)
        if result['seed_attempts'] and result['seed_attempts'][-1].get('reason') is None:
            result['seed_attempts'][-1]['reason'] = result['reason']
        failed = result['reason'] in ('RESOURCE_LIMIT', 'INVALID_INPUT_OR_INTERFACE',
            'INTERFACE_ERROR', 'SOLVER_INTERFACE_ERROR', NUMERICAL_CONSISTENCY_UNRESOLVED)
        result['technical_state'] = ('FAILED' if failed else 'COMPLETED' if
            result['reason'] == 'SCENE_SEARCH_SEQUENCE_COMPLETE' else 'INTERRUPTED_OR_UNRESOLVED')
        result['timing'] = budget.summary(stopped)
        result['timing'].update(method_elapsed_s=method_elapsed,
            method_elapsed_excluding_cleanup_s=method_elapsed,
            wall_until_constructor_cleanup_return_s=stopped,
            startup_failure_cleanup_in_method_elapsed_s=constructor_cleanup_s,
            deadline_overshoot_s=max(0.0, method_elapsed-budget.seconds), cleanup_s=constructor_cleanup_s,
            invocation_started_at_s=invocation_started, invocation_stopped_at_s=stopped,
            invocation_elapsed_s=max(0.0, method_elapsed-invocation_started))
        if constructor_cleanup_s:
            totals = result['timing']['phases_exclusive_s']
            totals['solver_startup'] = max(0.0, totals.get('solver_startup', 0)-constructor_cleanup_s)
            for frame in result['timing']['phase_records']:
                if frame['phase'] == 'solver_startup':
                    frame['startup_cleanup_inclusive_s'] = constructor_cleanup_s
                    frame['exclusive_s'] = max(0.0, frame['exclusive_s']-constructor_cleanup_s)
            result['timing']['unattributed_s'] = max(0.0, method_elapsed-sum(totals.values()))
        cleanup_started = clock()
        result['session_closed_by_neighborhood'] = False
        if session is not None and close_session:
            session.event_consumer = None
            try:
                session.close(); result['session_closed_by_neighborhood'] = True
            except Exception as error:
                result['cleanup_error'] = f'{type(error).__name__}: {error}'
            cleanup_receipt = getattr(session, 'cleanup', None)
            cleanup_failed = (isinstance(cleanup_receipt, dict)
                              and not cleanup_is_complete(cleanup_receipt))
            forced_closed = (isinstance(cleanup_receipt, dict)
                             and cleanup_receipt.get('cleanup_status') == 'forced_closed')
            if cleanup_failed or forced_closed:
                # close() can finish process cleanup while its stop/closed
                # writes fail. Preserve that in-memory cause even if no
                # closed.json exists; no SAFE or primary search error changes.
                result['session_cleanup'] = deepcopy(cleanup_receipt)
            if cleanup_failed or result.get('cleanup_error'):
                result.setdefault('technical_state_before_cleanup', result.get('technical_state'))
                result['technical_state'] = 'FAILED'
        result['timing']['cleanup_s'] += clock()-cleanup_started
        session_total = getattr(session, 'counter', 0)
        result['session_total_request_count'] = session_total
        result['solver_request_attempts'] = max(0, session_total-session_counter_at_entry)
        result['event_consumer_detached'] = session is None or getattr(session, 'event_consumer', None) is None
        result['worker_reusable'] = (result['worker_reusable'] and budget.remaining > 0
            and result['event_consumer_detached'] and not result['session_closed_by_neighborhood']
            and not getattr(session, 'closed', False) and not getattr(session, 'request_blocked', False))
        rounds = [round_record for scene in result['scenes'].values()
                  for round_record in (scene.get('solver_result') or {}).get('rounds', [])]
        entries = [round_record.get('intlinprog_entered') for round_record in rounds]
        result['raw_native_solver_entry_seen'] = True in entries
        result['in_budget_solver_entry_confirmed'] = any(
            round_record.get('intlinprog_entered') is True and round_record.get('budget_valid') is True
            for round_record in rounds)
        result['integer_solver_entered'] = (True if result['in_budget_solver_entry_confirmed'] else
            False if not result['solver_request_attempts'] or
            (entries and all(value is False for value in entries)) else None)
        result['integer_solver_entry_evidence'] = 'budget-valid returned native records only; late entry separate'
    archive_started = clock()
    archive_errors = []

    def archive_attempt(stage, path, operation):
        # Archival cannot replace a previously formed SAFE/violation or the
        # search failure that preceded it. No retry, alternate output path,
        # candidate evaluation or budget replenishment is performed here.
        try:
            return operation()
        except Exception as error:
            archive_errors.append({
                'source': 'neighborhood_method post-budget archival',
                'stage': stage, 'path': None if path is None else str(path),
                'exception_type': type(error).__name__, 'message': str(error),
                'exception_repr': repr(error), 'errno': getattr(error, 'errno', None),
                'winerror': getattr(error, 'winerror', None),
                'filename': getattr(error, 'filename', None),
                'filename2': getattr(error, 'filename2', None)})
            result.setdefault('technical_state_before_archive', result.get('technical_state'))
            result.update(technical_state='FAILED', archive_complete=False,
                          archive_errors=archive_errors)
            return None

    for sid, observer in observers.items():
        construction = archive_attempt('construction_metadata', None,
            lambda observer=observer: (observer.snapshot() if observer.finished_at is not None
                                      else observer.finish('CONSTRUCTION_INTERRUPTED')))
        if construction is not None:
            result['scenes'][sid]['construction'] = construction
        archive_attempt('construction_observer_detach', None,
                        lambda observer=observer: _detach_observer(observer))
    if config is not None:
        path = workdir/'input_config.json'
        archive_attempt('input_config', path, lambda: _save(path, config))
    if instance is not None:
        path = workdir/'input_instance.json'
        archive_attempt('input_instance', path, lambda: _save(path, instance))
    result['environment'] = {'python': sys.version, 'platform': platform.platform(),
        'scope': labels['environment_scope']}
    result['counted_energy_source'] = 'matching original-input partial aggregates only'
    result['timing']['postprocess_before_serialization_s'] = clock()-archive_started
    path = workdir/'result.json'
    archive_attempt('result', path, lambda: _save(path, result))
    archive_timing = {'report_wall_s': clock()-archive_started,
        'scope': 'serialization only; no new evaluation/aggregation/solver evidence',
        'includes_own_file_write': False}
    if archive_errors:
        archive_timing.update(archive_complete=False, archive_errors=deepcopy(archive_errors))
    path = workdir/'archive_timing.json'
    archive_attempt('archive_timing', path, lambda: _save(path, archive_timing))
    return result
