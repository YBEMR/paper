"""One supplied shared deployment, live scene progress, one absolute budget.

All scene seeds are checked against the original input before inner searches.
Callbacks and final candidates use the same independent model-view evaluator;
timely SAFE candidates are immediately checked by the partial-scene adapter.
Only a matching all-scene aggregate supplies global U. No outer deployment
search, extra solver time, repair, or independent optimality claim is added.
"""
from copy import deepcopy
import math
from pathlib import Path
import platform
import sys
import time

from build_observer import BuildObserver
from control_policy import resolve_idle_policy
from diagnostic_search import Recorder
from formal_milp import _checked_thermal_witnesses, OUTER_ROUND_LIMIT
from initial_point import _InitialSession, prepare_initial_witness
from matlab_bridge import (MatlabSession, NUMERICAL_CONSISTENCY_CONFLICT,
                           NUMERICAL_CONSISTENCY_UNRESOLVED)
from milp import (add_thermal_feedback, build_model, decode,
                  evaluate_model_candidate, _digest)
from scene_adapter import (PARTIAL_PROTOCOL, _local_candidate_deployment,
    _partial_identity, _partial_scene_energy, _receipt_hash,
    aggregate_partial_scene_receipts, canonical_hash, evaluate_partial_scene,
    shared_deployment_ids, validate_shared_deployment)
from scene_method import DEFAULT_BUILDER_OPTIONS, _save, _reported_bounds, _violations
from thermal import Exhausted, _accuracy, _q
from timing import MethodBudget


PROTOCOL = 'one-shared-deployment-live-scenes-v1'


def _timely(receipt, budget):
    stamp = receipt.get('completed_at_elapsed_s')
    return (isinstance(stamp, (int, float)) and not isinstance(stamp, bool)
            and math.isfinite(stamp) and 0 <= stamp < budget.seconds)


def _safe(receipt, budget):
    return (receipt.get('state') == 'SAFE' and receipt.get('rankable_energy') is True
            and receipt.get('safe_upper_bound_J') is not None and _timely(receipt, budget))


def _change(before, after):
    """A smaller rigorous upper bound and separated intervals are distinct."""
    return {'upper_bound_improved': before is not None and _q(after[1]) < _q(before[1]),
            'strict_energy_improvement_certified': (
                before is not None and _q(after[1]) < _q(before[0]))}


def _bound_gaps(bounds, upper):
    """Keep original-domain and fixed-condition independent gaps separate."""
    result = {}
    for key in ('L0', 'L_a'):
        receipt = bounds[key]
        lower, high = _q(receipt['lower_bound_J']), _q(upper)
        gap = high-lower
        result[key] = {'lower_bound_J': str(lower), 'safe_upper_bound_J': str(high),
            'absolute_gap_J': str(gap), 'relative_gap': str(gap/high) if high > 0 else None,
            'scope': receipt['scope'], 'consistent': gap >= 0,
            'solver_reported': False, 'independently_proven_optimal': False}
    return result


def _validate_bounds_receipt(bounds, instance, deployment, policy, budget):
    """Bind supplied current-invocation bounds without recomputing them."""
    if not isinstance(bounds, dict) or set(bounds) != {'L0', 'L_a'}:
        raise ValueError('Supplied bounds must contain exactly L0 and L_a')
    for key, scope, fixed in (('L0', 'original_full_domain', None),
                              ('L_a', 'fixed_shared_deployment', deployment)):
        receipt = bounds[key]
        stamp = receipt.get('formed_at_s') if isinstance(receipt, dict) else None
        if (not isinstance(receipt, dict) or receipt.get('scope') != scope
                or receipt.get('input_sha256') != canonical_hash(instance)
                or receipt.get('control_policy') != policy
                or receipt.get('shared_stage_ids') != shared_deployment_ids(instance)
                or receipt.get('shared_deployment') != fixed
                or receipt.get('shared_deployment_sha256') != (None if fixed is None else canonical_hash(fixed))
                or receipt.get('solver_reported') is not False
                or receipt.get('used_as_new_MILP_row') is not False
                or isinstance(stamp, bool) or not isinstance(stamp, (int, float))
                or not math.isfinite(stamp) or not 0 <= stamp < budget.seconds
                or stamp > budget.elapsed):
            raise ValueError('Supplied '+key+' does not match current input/condition/budget time')
        _q(receipt['lower_bound_J'])
    return deepcopy(bounds)


class PartialRecorder(Recorder):
    """Keep Recorder's decode/cache logic; publish SAFE and queue live feedback.

    ``on_evaluation`` and ``on_safe`` receive (candidate, evaluation, source).
    A trusted callback violation writes only the current request's cancel file.
    Feedback and subsequent solve requests belong to the outer loop, after a
    normal response has confirmed the current request ended within budget.
    """
    def __init__(self, model, accuracy, budget, folder, *, model_evaluator,
                 on_evaluation, on_safe, witness_validator=_checked_thermal_witnesses,
                 decoder=decode):
        self.model_evaluator = model_evaluator
        self.on_evaluation, self.on_safe = on_evaluation, on_safe
        self.witness_validator = witness_validator
        self.current_source = self.current_prefix = None
        self._assessment_evaluated = False
        self.pending = None
        self.cancel_requests = []
        self._cancelled_prefixes = set()
        self.slice_end = None
        super().__init__(model, accuracy, budget, folder,
                         decoder=decoder, evaluator=self._evaluate)

    def begin_request(self):
        self.pending = None

    def assess(self, vector, source):
        previous = self.current_source
        previous_evaluated = self._assessment_evaluated
        self.current_source = source
        self._assessment_evaluated = False
        try:
            candidate, evaluation = super().assess(vector, source)
            # Recorder reuses complete model-view receipts across rounds. A
            # repeated violating callback must still cancel this new request;
            # its physical receipt is reused, never recomputed.
            if (not self._assessment_evaluated and evaluation is not None
                    and evaluation.get('state') == 'THERMAL_VIOLATION'):
                self._queue_violation(candidate, evaluation)
            return candidate, evaluation
        finally:
            self.current_source = previous
            self._assessment_evaluated = previous_evaluated

    def poll(self, prefix):
        previous = self.current_prefix
        self.current_prefix = Path(prefix)
        try:
            self._cancel_slice_if_due(self.current_prefix)
            returned = super().poll(prefix)
            self._cancel_slice_if_due(self.current_prefix)
            return returned
        finally:
            self.current_prefix = previous

    def _cancel_slice_if_due(self, prefix):
        if (self.slice_end is None or self.budget.clock() < self.slice_end
                or self.budget.remaining <= 0 or str(prefix) in self._cancelled_prefixes):
            return
        stamp = self.budget.elapsed
        prefix.with_suffix('.cancel').write_text('scene search slice complete\n', encoding='ascii')
        self._cancelled_prefixes.add(str(prefix))
        self.cancel_requests.append({'request_prefix': str(prefix),
            'requested_at_s': stamp, 'published_at_s': self.budget.elapsed,
            'reason': 'SCENE_SLICE_END', 'cooperative_only': True})

    def _evaluate(self, model, candidate, accuracy, budget):
        self._assessment_evaluated = True
        evaluation = self.model_evaluator(model, candidate, accuracy, budget)
        source = self.current_source
        # Commit diagnostic evidence before another check or disk publication.
        self.on_evaluation(candidate, evaluation, source)
        if _safe(evaluation, budget):
            self.on_safe(candidate, evaluation, source)
        elif evaluation.get('state') == 'THERMAL_VIOLATION':
            self._queue_violation(candidate, evaluation)
        return evaluation

    def _queue_violation(self, candidate, evaluation):
        budget = self.budget
        try:
            witnesses = self.witness_validator(self.model, candidate, evaluation)
        except Exhausted:
            witnesses = []  # The already formed violation remains recorded.
        if witnesses and self.pending is None:
            self.pending = {'candidate': deepcopy(candidate),
                'evaluation': deepcopy(evaluation), 'source': self.current_source,
                'queued_at_s': budget.elapsed}
        prefix = self.current_prefix
        if witnesses and prefix is not None and str(prefix) not in self._cancelled_prefixes:
            stamp = budget.elapsed
            budget.check()
            prefix.with_suffix('.cancel').write_text('certified thermal feedback\n', encoding='ascii')
            self._cancelled_prefixes.add(str(prefix))
            self.cancel_requests.append({'request_prefix': str(prefix),
                'requested_at_s': stamp, 'published_at_s': budget.elapsed,
                'reason': 'CERTIFIED_CALLBACK_THERMAL_VIOLATION',
                'cooperative_only': True})

    def summary(self):
        result = super().summary()
        result.update(cancel_requests=deepcopy(self.cancel_requests),
                      pending_thermal_feedback=deepcopy(self.pending),
                      slice_end_monotonic=self.slice_end)
        return result

    def release(self):
        """Detach search objects after receipts have been copied into results.

        In particular Recorder.evaluator is this instance's bound _evaluate
        method. Breaking that cycle releases the large model without waiting
        for cyclic GC. Replace lists/dicts rather than mutating containers
        already referenced by the archived diagnostic summary.
        """
        for name in ('model', 'model_evaluator', 'on_safe', 'on_evaluation',
                     'evaluator', 'decoder', 'witness_validator', 'budget'):
            setattr(self, name, None)
        self.best = self.pending = None
        self.cache, self.next_event = {}, {}
        self.evaluations, self.decode_records, self.progress = [], [], []


def _solve_scene(model, session, accuracy, budget, recorder, *,
                 feedback_adder, witness_validator, max_rounds, scene_slice_s=None):
    """Same conditional-feedback mechanism, plus live publications/cancel."""
    result = {'state': 'UNRESOLVED', 'reason': None, 'safe_candidate': None,
        'safe_upper_bound_J': None, 'evaluation': None, 'rounds': [], 'feedback': [],
        'remaining_domain': 'retained', 'independently_proven_optimal': False,
        'independently_proven_infeasible': False}
    slice_start = budget.elapsed
    slice_end = (None if scene_slice_s is None else
                 min(budget.deadline, budget.clock()+scene_slice_s))
    recorder.slice_end = slice_end
    if slice_end is not None:
        result.update(scene_slice_s=scene_slice_s, slice_started_at_s=slice_start,
                      slice_end_at_s=slice_end-budget.start)
    request_settled = True
    session.event_consumer = recorder.poll
    try:
        for iteration in range(max_rounds):
            budget.check()
            if slice_end is not None and budget.clock() >= slice_end:
                result['reason'] = 'SCENE_SLICE_COMPLETE'; break
            recorder.begin_request()
            with budget.phase('matrix_export'):
                payload = model.as_solver_dict()
            budget.check()
            if slice_end is not None and budget.clock() >= slice_end:
                result['reason'] = 'SCENE_SLICE_COMPLETE'; break
            options = {'remaining_s': budget.remaining, 'budget': budget}
            if slice_end is not None:
                options['solver_max_time_s'] = min(slice_end-budget.clock(), budget.remaining)
                if options['solver_max_time_s'] <= 0:
                    result['reason'] = 'SCENE_SLICE_COMPLETE'; break
            with budget.phase('solver_transport_and_solve'):
                request_settled = False
                returned = session.solve(payload, **options)
            result['rounds'].append(returned)
            request_settled = returned.get('status') == 'SOLVED' and returned.get('budget_valid') is True
            budget.check()
            if not returned.get('budget_valid'):
                result['reason'] = 'SOLVER_RETURN_AFTER_BUDGET'; break
            if (returned.get('numerical_consistency') or {}).get('state') == NUMERICAL_CONSISTENCY_CONFLICT:
                result.update(reason=NUMERICAL_CONSISTENCY_UNRESOLVED,
                              numerical_consistency=returned['numerical_consistency'])
                break
            if returned.get('status') != 'SOLVED':
                result['reason'] = 'SOLVER_INTERFACE_ERROR'; break
            evaluation = candidate = None
            if returned.get('x'):
                if not returned.get('accepted_for_evaluation'):
                    result['reason'] = 'SOLVER_INTERFACE_ERROR'; break
                candidate, evaluation = recorder.assess(returned['x'], f'round{iteration+1}:final')
                result['evaluation'] = evaluation
            # A pending callback witness survives a normal cancelled response
            # without x. Never enqueue another request while one is active.
            pending = recorder.pending
            if pending is not None:
                candidate, evaluation = pending['candidate'], pending['evaluation']
            elif evaluation is None:
                result['reason'] = ('SCENE_SLICE_COMPLETE' if slice_end is not None
                                    and budget.clock() >= slice_end else
                                    'SOLVER_REPORTED_INFEASIBLE' if returned.get('exitflag') == -2
                                    else 'NO_INTEGER_CANDIDATE')
                break
            elif _safe(evaluation, budget):
                result['reason'] = ('SAFE_ENGINEERING_CONVERGENCE' if returned.get('exitflag') == 1
                                    else 'SAFE_RETURNED_INCUMBENT')
                break
            if evaluation.get('state') != 'THERMAL_VIOLATION':
                result['reason'] = 'EVALUATION_UNRESOLVED'; break
            budget.check()
            if slice_end is not None and budget.clock() >= slice_end:
                result['reason'] = 'SCENE_SLICE_COMPLETE'; break
            with budget.phase('thermal_feedback'):
                witnesses = witness_validator(model, candidate, evaluation)
                feedback = (feedback_adder(model, candidate, evaluation) if witnesses else
                            {'state': 'NO_VALID_EXCLUSION', 'rows_added': 0})
            feedback.update(completed_at_elapsed_s=budget.elapsed,
                            within_budget=budget.elapsed < budget.seconds)
            result.setdefault('feedback' if feedback['within_budget'] else
                              'late_feedback_diagnostics', []).append(feedback)
            budget.check()
            if not feedback.get('rows_added'):
                result['reason'] = 'FEEDBACK_UNRESOLVED'; break
        else:
            result['reason'] = 'OUTER_ROUND_LIMIT'
    except Exhausted as error:
        result['reason'] = str(error)
    except MemoryError:
        result['reason'] = 'RESOURCE_LIMIT'
    except Exception as error:
        result.update(reason='INTERFACE_ERROR', error=f'{type(error).__name__}: {error}')
    finally:
        session.event_consumer = None
        try:
            result['diagnostic'] = recorder.summary()
            if recorder.best is not None:
                result.update(state='SAFE', safe_candidate=recorder.best['candidate'],
                    evaluation=recorder.best['evaluation'],
                    safe_upper_bound_J=recorder.best['evaluation']['safe_upper_bound_J'])
            result['elapsed_s'] = budget.elapsed
            result['request_settled'] = request_settled
            result['worker_reusable'] = (request_settled and budget.remaining > 0
                and not getattr(session, 'closed', False) and not getattr(session, 'request_blocked', False)
                and result['reason'] not in ('INTERFACE_ERROR', 'RESOURCE_LIMIT', 'SOLVER_INTERFACE_ERROR',
                                             NUMERICAL_CONSISTENCY_UNRESOLVED))
        finally:
            release = getattr(recorder, 'release', None)
            if callable(release):
                release()
            else:
                # Small injected recorders can omit the production release
                # method; detach the same callback slots when present.
                for name in ('model', 'model_evaluator', 'on_safe', 'on_evaluation',
                             'evaluator', 'decoder', 'witness_validator'):
                    if hasattr(recorder, name):
                        setattr(recorder, name, None)
    return result


def _default_bounds(instance, deployment, budget):
    from partial_bounds import get_deployment_bounds
    return get_deployment_bounds(instance, deployment, budget=budget)


def _detach_observer(observer):
    """Break the model/progress-observer cycle after its final snapshot."""
    model = getattr(observer, 'model', None)
    if model is not None and getattr(model, 'progress', None) is observer:
        model.progress = None
    observer.model = None


def execute_shared_deployment(input_loader, workdir, *, shared_deployment,
        seconds=60, starts=None, clock=time.monotonic, model_builder=build_model,
        session_factory=MatlabSession, initial_preparer=prepare_initial_witness,
        model_evaluator=evaluate_model_candidate, scene_evaluator=evaluate_partial_scene,
        aggregator=aggregate_partial_scene_receipts, recorder_factory=PartialRecorder,
        feedback_adder=add_thermal_feedback, witness_validator=_checked_thermal_witnesses,
        bounds_provider=_default_bounds, checkpoint=None, builder_options=None,
        max_rounds=OUTER_ROUND_LIMIT, budget=None, close_session=True,
        scene_slice_s=None, on_global_update=None, bounds_receipt=None):
    """Search one fixed H=a; no invocation or solver budget is replenished.

    All declared scenes are built and initialized in input order. An unavailable
    or numerically rejected x0 does not delete the model's choices: a complete
    model may then enter bare MILP. This is a regular invocation fallback, not
    a new heuristic. Only this invocation's admitted x0 is passed, once/scene.
    ``checkpoint(scene_id, public_initialisation, budget)`` is observation only.
    Injectable dependencies are for correctness fixtures, never old witnesses.
    An optional existing MethodBudget owns all identities and deadlines. A
    shared session_factory may return the outer caller's single worker; then
    close_session=False leaves its lifetime with that caller. Search slices
    have soft native caps and never change the global evidence deadline.
    on_global_update(result, update) transfers an already committed aggregate.
    """
    external_budget = budget is not None
    if external_budget:
        if not isinstance(budget, MethodBudget):
            raise TypeError('budget must be the caller-owned MethodBudget')
        clock = budget.clock
    else:
        budget = MethodBudget(float(seconds), clock=clock)
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
    result = {'protocol': PROTOCOL, 'state': 'UNRESOLVED', 'reason': None,
        'problem_id': None, 'safe_candidate': None, 'safe_upper_bound_J': None,
        'weighted_energy_J': None, 'rankable_energy': False, 'aggregation': None,
        'global_updates': [], 'scenes': {}, 'violations': [],
        'initial_global_safe_upper_bound_J': None,
        'initial_global_weighted_energy_J': None, 'safe_solution_source': None,
        'independently_proven_optimal': False, 'independently_proven_infeasible': False,
        'remaining_domain': 'retained', 'deployment_feasibility': 'NOT_DECIDED',
        'global_deployment_search_performed': False, 'formal_comparison': False,
        'candidate_and_cache_shared_between_calls': False,
        'solver_reported_bounds_aggregated': False, 'matlab_worker_ready': False,
        'external_budget': external_budget, 'close_session_requested': close_session,
        'scene_slice_s': scene_slice_s, 'worker_reusable': True,
        'initialisation_fallback': 'complete model with missing/rejected x0 may enter bare MILP; '
            'no new heuristic, repair or domain exclusion; expiry/resources/errors still stop',
        'scene_budget_policy': 'original scene order, one shared remaining budget; no quota reset'}
    models, observers, initial, receipts, candidates, sources, caches = {}, {}, {}, {}, {}, {}, {}
    config = instance = session = None
    active_stage, active_scene = 'invocation_setup', None
    constructor_cleanup_s = 0.0
    session_counter_at_entry = 0

    def remember_view(sid, candidate, evaluation, source):
        result['scenes'][sid]['model_view_evaluations'].append({
            'candidate': deepcopy(candidate), 'evaluation': deepcopy(evaluation),
            'source': source, 'received_at_s': budget.elapsed})
        result['violations'].extend(_violations(evaluation, sid, 'solver_model_view'))

    def publish_safe(sid, model, candidate, evaluation, source):
        record = result['scenes'][sid]
        expected_view = {'input_sha256': _digest(model.instance),
                         'candidate_sha256': _digest(candidate)}
        if not _safe(evaluation, budget) or evaluation.get('evidence_identity') != expected_view:
            raise ValueError('SAFE model-view receipt identity/timestamp mismatch')
        key = canonical_hash(candidate)
        if key in caches[sid]:
            record['original_receipt_cache_hits'] += 1
            return
        with budget.phase('original_input_scene_evaluation'):
            receipt = scene_evaluator(instance, sid, deployment, candidate, accuracy, budget)
        attempt = {'candidate': deepcopy(candidate), 'receipt': deepcopy(receipt),
                   'source': source, 'received_at_s': budget.elapsed,
                   'accepted_safe': False}
        record['original_scene_evaluations'].append(attempt)
        # Identity checking transfers existing evidence; it does not create U.
        local = _local_candidate_deployment(instance, sid, candidate)
        expected = _partial_identity(instance, deployment, accuracy, budget,
            scene_id=sid, candidate=candidate, local_deployment=local)
        matches = (receipt.get('protocol') == PARTIAL_PROTOCOL
            and receipt.get('identity') == expected
            and receipt.get('receipt_sha256') == _receipt_hash(receipt)
            and receipt.get('shared_deployment') == deployment
            and receipt.get('shared_stage_ids') == result['shared_stage_ids']
            and receipt.get('local_deployment') == local and receipt.get('unweighted') is True)
        attempt['identity_valid'] = matches
        if not matches:
            raise ValueError('Original-input partial receipt identity mismatch')
        result['violations'].extend(_violations(receipt, sid, 'original_input_scene_receipt'))
        if receipt.get('state') in ('THERMAL_VIOLATION', 'INVALID_SCHEDULE'):
            caches[sid][key] = deepcopy(receipt)
            raise ValueError('SAFE model-view candidate disagrees with original input')
        if not _safe(receipt, budget):
            return  # Unknown/late results cannot replace an earlier SAFE.
        energy = _partial_scene_energy(instance, sid, receipt, budget).data()
        before_view = evaluation.get('weighted_energy_J')
        if (before_view is None or max(_q(before_view[0]), _q(energy[0]))
                > min(_q(before_view[1]), _q(energy[1]))):
            raise ValueError('Model-view and original-input SAFE energies disagree')
        attempt['accepted_safe'] = True
        caches[sid][key] = deepcopy(receipt)
        previous = receipts.get(sid)
        if previous is not None and _q(receipt['safe_upper_bound_J']) >= _q(previous['safe_upper_bound_J']):
            return
        change = _change(previous.get('energy_J') if previous else None, energy)
        receipts[sid], candidates[sid], sources[sid] = deepcopy(receipt), deepcopy(candidate), source
        record.update(state='SAFE', scene_receipt=deepcopy(receipt), safe_candidate=deepcopy(candidate),
            safe_upper_bound_J=receipt['safe_upper_bound_J'], local_deployment=deepcopy(local),
            best_source=source, deployment_feasibility='SCENE_SAFE_WITNESS')
        if record['first_safe_at_s'] is None:
            record['first_safe_at_s'] = receipt['completed_at_elapsed_s']
        record['updates'].append({'source': source, 'energy_J': deepcopy(energy),
            'scene_committed_at_s': receipt['completed_at_elapsed_s'],
            'transferred_at_s': budget.elapsed, **change})
        # Existing scene evidence is now committed, before a possible expiry.
        budget.check()
        if len(receipts) != len(instance['scenarios']):
            return
        with budget.phase('outer_weighted_aggregation'):
            aggregation = aggregator(instance, deployment, receipts, candidates, accuracy, budget)
        result.setdefault('aggregation_attempts', []).append(deepcopy(aggregation))
        if not _safe(aggregation, budget):
            return
        previous_energy = result['weighted_energy_J']
        if (result['safe_upper_bound_J'] is not None and
                _q(aggregation['safe_upper_bound_J']) >= _q(result['safe_upper_bound_J'])):
            return
        change = _change(previous_energy, aggregation['weighted_energy_J'])
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
            safe_solution_source='initial_constructor' if all_initial else 'inner_MILP',
            deployment_feasibility='ALL_SCENES_SAFE_WITNESS')
        if 'first_safe_at_s' not in result:
            result['first_safe_at_s'] = aggregation['completed_at_elapsed_s']
        if all_initial and result['initial_global_safe_upper_bound_J'] is None:
            result['initial_global_safe_upper_bound_J'] = aggregation['safe_upper_bound_J']
            result['initial_global_weighted_energy_J'] = deepcopy(aggregation['weighted_energy_J'])
        if on_global_update is not None:
            # Observation of a formed aggregate is allowed even if transferring
            # that receipt crosses the method cutoff. The callback may not
            # evaluate, solve, or invent a later commit timestamp.
            update['observer_requested_at_s'] = budget.elapsed
            try:
                on_global_update(result, update)
            except Exception as error:
                update['observer_error'] = f'{type(error).__name__}: {error}'
                raise
            update['observer_completed_at_s'] = budget.elapsed
        gaps = _bound_gaps(result['deployment_bounds'], result['safe_upper_bound_J'])
        if budget.elapsed < budget.seconds:
            result['independent_gaps'] = gaps
            update['independent_gaps'] = deepcopy(gaps)
        result['inner_MILP_improved_initial_upper_bound'] = (
            result['initial_global_safe_upper_bound_J'] is not None and
            _q(result['safe_upper_bound_J']) < _q(result['initial_global_safe_upper_bound_J']))
        result['strict_improvement_over_initial_certified'] = (
            result['initial_global_weighted_energy_J'] is not None and
            _q(result['weighted_energy_J'][1]) < _q(result['initial_global_weighted_energy_J'][0]))

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
            if any(w < 0 for w in weights) or sum(weights) != 1:
                raise ValueError('Scenario weights must be nonnegative and sum to one')
            if isinstance(max_rounds, bool) or not isinstance(max_rounds, int) or not 1 <= max_rounds <= OUTER_ROUND_LIMIT:
                raise ValueError('max_rounds must be in 1..50')
            flags = dict(DEFAULT_BUILDER_OPTIONS)
            if builder_options is not None:
                allowed = set(flags) | {'cumulative_precedence'}
                if set(builder_options)-allowed or any(type(v) is not bool for v in builder_options.values()):
                    raise ValueError('Unsupported builder flags')
                flags.update(builder_options)
            result.update(problem_id=instance['id'], shared_stage_ids=shared_deployment_ids(instance),
                shared_deployment=deepcopy(deployment), control_policy=policy,
                builder_options=flags, outer_round_limit=max_rounds,
                identity={'full_input_sha256': canonical_hash(instance),
                    'config_sha256': canonical_hash(config), 'shared_deployment_sha256': canonical_hash(deployment),
                    'accuracy_sha256': canonical_hash(accuracy)},
                original_scene_order=[s['id'] for s in instance['scenarios']],
                original_scene_weights={s['id']: s['weight'] for s in instance['scenarios']})
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
            if bounds_receipt is not None:
                result['deployment_bounds'] = _validate_bounds_receipt(
                    bounds_receipt, instance, deployment, policy, budget)
                result['bounds_source'] = 'supplied current-invocation receipts'
            elif bounds_provider is _default_bounds:
                from partial_bounds import independent_lower_bound
                result['deployment_bounds'] = {
                    'L0': independent_lower_bound(instance, None, budget), 'L_a': None}
                result['deployment_bounds']['L_a'] = independent_lower_bound(instance, deployment, budget)
            else:
                result['deployment_bounds'] = bounds_provider(instance, deployment, budget)
        budget.check()
        for index, scene in enumerate(instance['scenarios']):
            active_scene = sid = scene['id']; record = result['scenes'][sid]
            active_stage = 'model_construction'
            observer = BuildObserver(budget, workdir/f'build_scene_{index:03d}.jsonl')
            observers[sid] = observer
            with budget.phase('model_construction'):
                model = model_builder(instance, config, starts=starts, budget=budget, progress=observer,
                    fixed_shared_deployment=deployment, fixed_scene_id=sid, **flags)
                models[sid] = model
                observer.finish('MODEL_CONSTRUCTED')
                record.update(model_complete=True, model_completed_at_s=budget.elapsed,
                    model_summary=model.summary(), preprocessing=deepcopy(getattr(model, 'preprocessing', None)))
            budget.check()
        for index, scene in enumerate(instance['scenarios']):
            active_scene = sid = scene['id']; record = result['scenes'][sid]
            active_stage = 'initialisation'
            record['initialisation_started_at_s'] = budget.elapsed
            local_starts = None if starts is None else {sid: deepcopy(starts[sid])}
            prepared = initial_preparer(models[sid], accuracy, budget, local_starts, 3)
            initial[sid] = prepared
            record['initialisation'] = deepcopy({k: v for k, v in prepared.items() if k != 'x0'})
            record['initialisation_returned_at_s'] = budget.elapsed
            witness = prepared.get('witness')
            for attempt in prepared.get('attempts', []):
                if attempt.get('evaluation') is not None:
                    remember_view(sid, attempt.get('candidate'), attempt['evaluation'], 'initial_constructor')
            if witness is not None:
                publish_safe(sid, models[sid], witness['candidate'], witness['evaluation'], 'initial_constructor')
            record['initial_checkpoint'] = {'requested': True, 'completed': False}
            with budget.phase('initial_receipt_checkpoint'):
                if checkpoint is None:
                    _save(workdir/f'initial_scene_{index:03d}.json', record['initialisation'])
                else:
                    checkpoint(sid, record['initialisation'], budget)
            record['initial_checkpoint'].update(completed=True, completed_at_s=budget.elapsed)
            budget.check()
            if prepared.get('reason') not in ('NO_SAFE_INITIAL_WITNESS', 'INITIAL_POINT_READY', 'INITIAL_POINT_REJECTED'):
                raise ValueError('Initialisation stopped: '+str(prepared.get('reason')))
        active_scene = None
        active_stage = 'solver_startup'
        with budget.phase('solver_startup'):
            session = session_factory(workdir/'matlab', total_budget_s=budget.remaining, budget=budget)
            session_counter_at_entry = getattr(session, 'counter', 0)
            if (getattr(session, 'closed', False) or getattr(session, 'request_blocked', False)
                    or getattr(session, 'event_consumer', None) is not None):
                raise ValueError('Shared worker is not idle and reusable')
            if getattr(session, 'budget', budget) is not budget:
                raise ValueError('Shared worker must use the identical MethodBudget')
        budget.check()
        result['matlab_worker_ready'] = True
        for scene in instance['scenarios']:
            active_scene = sid = scene['id']; record = result['scenes'][sid]
            budget.check()
            active_stage = 'candidate_search'
            folder = workdir/('scene_'+str(result['original_scene_order'].index(sid)))
            folder.mkdir()
            model = models[sid]
            recorder = recorder_factory(model, accuracy, budget, folder,
                model_evaluator=model_evaluator,
                on_evaluation=lambda c, e, s, sid=sid: remember_view(sid, c, e, s),
                on_safe=lambda c, e, s, sid=sid, model=model: publish_safe(sid, model, c, e, s),
                witness_validator=witness_validator)
            prepared = initial[sid]
            ready = prepared.get('state') == 'SAFE_POINT_READY' and prepared.get('x0') is not None
            inner_session = _InitialSession(session, prepared['x0']) if ready else session
            record.update(x0_injected=ready, bare_MILP_fallback=not ready,
                          search_started_at_s=budget.elapsed)
            solved = _solve_scene(model, inner_session, accuracy, budget, recorder,
                feedback_adder=feedback_adder, witness_validator=witness_validator,
                max_rounds=max_rounds, scene_slice_s=scene_slice_s)
            record.update(solver_result=solved, reason=solved['reason'],
                          search_returned_at_s=budget.elapsed, solver_reported_bounds=_reported_bounds(solved))
            result['worker_reusable'] = solved['worker_reusable']
            budget.check()
            if not solved['worker_reusable']:
                result['reason'] = solved['reason']; break
            if solved['reason'] in ('INTERFACE_ERROR', 'RESOURCE_LIMIT', 'SOLVER_INTERFACE_ERROR',
                                     NUMERICAL_CONSISTENCY_UNRESOLVED):
                result['reason'] = solved['reason']; break
        else:
            result['reason'] = 'SCENE_SEARCH_SEQUENCE_COMPLETE'
    except Exhausted as error:
        result['reason'] = str(error)
        result['worker_reusable'] = False
        if hasattr(error, 'matlab_cleanup'):
            result['startup_cleanup'] = error.matlab_cleanup
            constructor_cleanup_s = error.matlab_cleanup.get('cleanup_wall_seconds', 0.0)
    except MemoryError:
        result['reason'] = 'RESOURCE_LIMIT'
        result['worker_reusable'] = False
    except Exception as error:
        if hasattr(error, 'matlab_cleanup'):
            result['startup_cleanup'] = error.matlab_cleanup
            constructor_cleanup_s = error.matlab_cleanup.get('cleanup_wall_seconds', 0.0)
        result.update(reason='INVALID_INPUT_OR_INTERFACE' if isinstance(error, (KeyError, TypeError, ValueError))
                      else 'INTERFACE_ERROR', error=f'{type(error).__name__}: {error}')
        result['worker_reusable'] = False
    finally:
        stopped = budget.elapsed
        method_elapsed = max(0.0, stopped-constructor_cleanup_s)
        result.update(stop_stage=active_stage, stop_scene=active_scene,
                      budget_exhausted=method_elapsed >= budget.seconds)
        result['timing'] = budget.summary(stopped)
        result['timing'].update(method_elapsed_s=method_elapsed,
            method_elapsed_excluding_cleanup_s=method_elapsed,
            wall_until_constructor_cleanup_return_s=stopped,
            startup_failure_cleanup_in_method_elapsed_s=constructor_cleanup_s,
            deadline_overshoot_s=max(0.0, method_elapsed-budget.seconds), cleanup_s=constructor_cleanup_s)
        result['timing'].update(invocation_started_at_s=invocation_started,
            invocation_stopped_at_s=stopped,
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
        result['session_closed_by_partial'] = False
        if session is not None and close_session:
            session.event_consumer = None
            try:
                session.close()
                result['session_closed_by_partial'] = True
            except Exception as error:
                result['cleanup_error'] = f'{type(error).__name__}: {error}'
        result['timing']['cleanup_s'] += clock()-cleanup_started
        session_total = getattr(session, 'counter', 0)
        result['session_total_request_count'] = session_total
        result['solver_request_attempts'] = max(0, session_total-session_counter_at_entry)
        result['event_consumer_detached'] = session is None or getattr(session, 'event_consumer', None) is None
        result['worker_reusable'] = (result['worker_reusable'] and budget.remaining > 0
            and result['event_consumer_detached'] and not result['session_closed_by_partial']
            and not getattr(session, 'closed', False) and not getattr(session, 'request_blocked', False))
        rounds = [r for scene in result['scenes'].values()
                  for r in (scene.get('solver_result') or {}).get('rounds', [])]
        entries = [r.get('intlinprog_entered') for r in rounds]
        result['raw_native_solver_entry_seen'] = True in entries
        result['in_budget_solver_entry_confirmed'] = any(
            r.get('intlinprog_entered') is True and r.get('budget_valid') is True for r in rounds)
        result['integer_solver_entered'] = (True if result['in_budget_solver_entry_confirmed'] else
            False if not result['solver_request_attempts'] or
            (entries and all(v is False for v in entries)) else None)
        result['integer_solver_entry_evidence'] = 'budget-valid returned native records only; late entry separate'
    # Archive existing evidence only. No post-deadline aggregation or new U.
    archive_started = clock()
    for sid, observer in observers.items():
        try:
            result['scenes'][sid]['construction'] = (observer.snapshot() if observer.finished_at is not None
                                                   else observer.finish('CONSTRUCTION_INTERRUPTED'))
        finally:
            _detach_observer(observer)
    if config is not None:
        _save(workdir/'input_config.json', config)
    if instance is not None:
        _save(workdir/'input_instance.json', instance)
    result['environment'] = {'python': sys.version, 'platform': platform.platform(),
                            'scope': 'one supplied shared deployment, not a formal comparison'}
    result['counted_energy_source'] = 'matching original-input partial adapter aggregates only'
    result['timing']['postprocess_before_serialization_s'] = clock()-archive_started
    _save(workdir/'result.json', result)
    _save(workdir/'archive_timing.json', {'report_wall_s': clock()-archive_started,
        'scope': 'serialization only; no new evaluation/aggregation/solver evidence', 'includes_own_file_write': False})
    return result
