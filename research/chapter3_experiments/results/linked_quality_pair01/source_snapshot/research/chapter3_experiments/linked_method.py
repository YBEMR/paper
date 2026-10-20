"""Two bounded passes: original N1, then one explicit warm-closed linked block."""
import time


PROTOCOL = 'fresh-seed-n1-then-linked-opp-start-warm-closed-complement-live-scenes-v1'


def execute_linked_fixed_unit_opp_start(input_loader, workdir, *,
        shared_deployment, opened_by_scene, linked_opened_by_scene,
        seconds=300, scene_slice_s=60, budget=None, clock=time.monotonic,
        session_factory=None, condition_factory=None, second_condition_factory=None,
        n1_scene_evaluator=None, second_scene_evaluator=None,
        augmented_context_factory=None, **kwargs):
    """Use one fresh seed, one root deadline and the original settled worker.

    ``opened_by_scene`` is the original first-pass N1 declaration. The distinct
    ``linked_opened_by_scene`` is a nonempty proper subset in every scene; it
    may include shared Stage OPP/start choices, while all device choices remain
    fixed. Closed OPP/start choices come from the final complete first-pass
    SAFE generation, never latest local receipts or the initial seed.
    """
    entry_started = clock() if budget is None else None
    from timing import MethodBudget
    entry_owns_budget = budget is None
    if entry_owns_budget:
        budget = MethodBudget(float(seconds), clock=clock)
        budget.start = entry_started
        budget.deadline = entry_started + float(seconds)
    elif not isinstance(budget, MethodBudget):
        raise TypeError('budget must be the caller-owned MethodBudget')
    else:
        clock = budget.clock
    budget.check()
    with budget.phase('linked_adapter_initialisation'):
        from copy import deepcopy
        import math
        from augmented_method import AugmentedMethodContext, AugmentedSession
        from linked_neighborhood import (PROTOCOL as LINKED_CONDITION_PROTOCOL,
            make_linked_condition, check_linked_candidate, _opened)
        from linked_neighborhood_adapter import (
            PROTOCOL as LINKED_EVALUATION_PROTOCOL, evaluate_linked_scene)
        from matlab_bridge import MatlabSession
        from neighborhood import make_n1_condition
        from neighborhood_adapter import evaluate_n1_scene
        from neighborhood_method import execute_n1_neighborhood
        from scene_adapter import canonical_hash

        reserved = {'membership_checker', 'evaluation_protocol', 'condition_protocol',
                    '_method_identity', '_second_phase'}
        if set(kwargs) & reserved:
            raise ValueError('Linked method owns both domains and protocol identities')
        if (isinstance(scene_slice_s, bool) or not isinstance(scene_slice_s, (int, float))
                or not math.isfinite(scene_slice_s) or not 0 < scene_slice_s <= 60):
            raise ValueError('Linked scene cap must be finite and in (0, 60] seconds')
        native_factory = MatlabSession if session_factory is None else session_factory
        context_factory = (AugmentedMethodContext if augmented_context_factory is None
                           else augmented_context_factory)
        if not callable(context_factory) or not callable(native_factory):
            raise TypeError('Context and session factories must be callable')
        context = context_factory(session_factory=native_factory)
        if not isinstance(context, AugmentedMethodContext):
            raise TypeError('Second-pass context must retain AugmentedMethodContext admission')
        user_observer = kwargs.pop('on_global_update', None)
        if user_observer is not None and not callable(user_observer):
            raise TypeError('on_global_update must be callable')
        declared_linked = deepcopy(linked_opened_by_scene)
        anchor = {'last_first_pass': None, 'frozen': None}

        def checked_loader(active_budget):
            config, instance = input_loader(active_budget)
            # Reject an invalid second-domain declaration before constructing
            # or searching the first pass, under the same billed input phase.
            with active_budget.phase('linked_domain_declaration_validation'):
                _opened(instance, declared_linked, active_budget)
            return config, instance

        def committed_observer(result, update):
            # commit_aggregate publishes the matching complete generation
            # atomically before this hook. Local scene.latest is never used.
            if update.get('phase_index') in (0, 1) and anchor['frozen'] is None:
                with budget.phase('linked_complete_anchor_capture'):
                    snapshot = result.get('committed_safe_snapshot')
                    if (not isinstance(snapshot, dict)
                            or snapshot.get('phase_index') != update['phase_index']
                            or snapshot.get('safe_upper_bound_J') != update.get('safe_upper_bound_J')
                            or snapshot.get('safe_candidate') != result.get('safe_candidate')
                            or snapshot.get('aggregation') != result.get('aggregation')):
                        raise ValueError('Linked anchor requires the matching complete SAFE ledger')
                    anchor['last_first_pass'] = deepcopy(snapshot)
            # Charge the caller observer in exactly the same root budget.
            if user_observer is not None:
                user_observer(result, update)

        def linked_opened(instance, active_budget):
            return _opened(instance, declared_linked, active_budget)

        def linked_condition(instance, deployment, seed_candidate, seed_receipt,
                             opened, *, budget, accuracy):
            with budget.phase('linked_warm_anchor_freeze'):
                if anchor['frozen'] is not None or anchor['last_first_pass'] is None:
                    raise ValueError('Linked phase requires one unambiguous first-pass complete SAFE anchor')
                frozen = deepcopy(anchor['last_first_pass'])
                frozen['candidate_sha256'] = canonical_hash(frozen['safe_candidate'])
                anchor['frozen'] = frozen
            factory = make_linked_condition if second_condition_factory is None else second_condition_factory
            return factory(instance, deployment, seed_candidate, seed_receipt, opened,
                warm_candidate=frozen['safe_candidate'], warm_receipt=frozen['aggregation'],
                budget=budget, accuracy=accuracy)

        labels = {
            'protocol': PROTOCOL, 'name': 'N1',
            'search_scope': 'one fresh seed: explicit N1 then one linked OPP/start subset with warm-closed choices; original full domain retained',
            'initialisation_fallback': 'rejected x0 permits bare current-domain MILP; missing complete SAFE seed stops',
            'inner_solution_source': 'N1_inner_MILP',
            'model_violation_source': 'N1_solver_model_view',
            'original_violation_source': 'N1_original_input_scene_receipt',
            'original_evaluation_phase': 'original_input_n1_scene_evaluation',
            'model_evaluation_phase': 'initial_n1_model_view_evaluation',
            'no_seed_reason': 'NO_COMPLETE_SAFE_LINKED_SEED',
            'bound_scope': 'seed_defined_N1_fixed_shared_deployment_unweighted_scene',
            'environment_scope': 'bounded linked-neighborhood correctness/method invocation; not a formal comparison'}
        second_labels = dict(labels, name='linked OPP/start, warm-closed, complement transport',
            inner_solution_source='linked_warm_closed_complement_inner_MILP',
            model_violation_source='linked_complement_solver_model_view',
            original_violation_source='linked_complement_original_input_scene_receipt',
            original_evaluation_phase='original_input_linked_scene_evaluation',
            model_evaluation_phase='initial_linked_model_view_evaluation',
            bound_scope='seed_fixed_units_linked_opp_start_warm_closed_unweighted_scene')
        second = {
            'condition_factory': linked_condition, 'opened': linked_opened,
            'membership_checker': check_linked_candidate,
            'scene_evaluator': (evaluate_linked_scene if second_scene_evaluator is None
                                else second_scene_evaluator),
            'evaluation_protocol': LINKED_EVALUATION_PROTOCOL,
            'condition_protocol': LINKED_CONDITION_PROTOCOL,
            'recorder_factory': context.recorder_factory,
            'session_adapter': lambda native: AugmentedSession(native, context),
            'latched': lambda: context.failed, 'identity': second_labels}

    result = execute_n1_neighborhood(checked_loader, workdir,
        shared_deployment=shared_deployment, opened_by_scene=opened_by_scene,
        seconds=seconds, scene_slice_s=scene_slice_s, budget=budget, clock=clock,
        session_factory=native_factory,
        condition_factory=make_n1_condition if condition_factory is None else condition_factory,
        n1_scene_evaluator=evaluate_n1_scene if n1_scene_evaluator is None else n1_scene_evaluator,
        on_global_update=committed_observer,
        _method_identity=labels, _second_phase=second, **kwargs)
    # Archival metadata only: no new receipt, bound or physical work after cutoff.
    for phase in result.get('phases', []):
        if phase.get('phase_index') == 2:
            phase['lifecycle_label'] = phase.get('name')
            phase['name'] = 'linked_opp_start_warm_closed'
    result['augmented_transport'] = context.summary()
    frozen = anchor['frozen']
    result['linked_record_contract'] = {
        'condition_and_opened_by_scene': 'first-pass N1 declarations',
        'linked_opened_by_scene': declared_linked,
        'closed_choice_anchor': 'last complete first-pass SAFE generation, frozen once before phase 2',
        'closed_anchor_candidate_sha256': None if frozen is None else frozen.get('candidate_sha256'),
        'closed_anchor_phase_index': None if frozen is None else frozen.get('phase_index'),
        'closed_anchor_committed_at_s': None if frozen is None else frozen.get('committed_at_s'),
        'units': 'original fresh-seed units across both phases',
        'scenes': 'latest local metadata; may precede the last complete global aggregate',
        'phases': 'per-pass condition, model, initialisation and solver records',
        'committed_safe_snapshot': 'only complete global generation and second-pass warm source'}
    result['linked_budget_boundary'] = {
        'entry_owns_budget': entry_owns_budget,
        'clock_begins_before_adapter_import_and_context': True,
        'identical_budget_forwarded_to_both_passes': True,
        'anchor_capture_freeze_and_observer_billed': True,
        'native_session_factory_calls_expected': 1,
        'tail_summary_scope': 'post-cutoff copying/serialization only; no new evidence'}
    result['timing']['clock_origin'] = 'before linked-entry lazy imports/context and input read; one absolute deadline'
    from pathlib import Path
    from scene_method import _save
    try:
        _save(Path(workdir)/'augmented_transport.json', result['augmented_transport'])
        _save(Path(workdir)/'result.json', result)
    except Exception as error:
        result.setdefault('technical_state_before_archive', result.get('technical_state'))
        result.update(technical_state='FAILED', archive_complete=False)
        result.setdefault('archive_errors', []).append({
            'source': 'linked method post-budget archival',
            'exception_type': type(error).__name__, 'message': str(error)})
    return result
