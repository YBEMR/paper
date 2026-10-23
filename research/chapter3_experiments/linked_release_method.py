"""K175: one N1 pass, then at most one constraint-guided release per scene.

Original C is retained byte-for-byte in linked_method.py. This distinct entry
selects its second-pass mask only after freezing the same complete SAFE anchor
that is subsequently bound by the original linked condition. No new physical
evaluator or search pass is introduced.
"""
import time


PROTOCOL = 'fresh-seed-n1-then-conditional-release-linked-opp-start-v1'


def execute_linked_conditional_release(input_loader, workdir, *,
        shared_deployment, opened_by_scene, linked_opened_by_scene,
        seconds=300, scene_slice_s=60, budget=None, clock=time.monotonic,
        session_factory=None, condition_factory=None, second_condition_factory=None,
        n1_scene_evaluator=None, second_scene_evaluator=None,
        augmented_context_factory=None, **kwargs):
    """Retain C initialization and safety; release only from this call's S1.

    ``linked_opened_by_scene`` is the original C baseline. The production
    selector may append at most one Stage per scene and never closes an
    originally open Stage. Devices and all unselected closed choices remain
    tied to the original seed and the frozen complete S1, respectively.
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
            make_linked_condition, validate_linked_condition, check_linked_candidate, _opened)
        from linked_release_policy import select_release, validate_selection
        from thermal import _accuracy
        from linked_neighborhood_adapter import (
            PROTOCOL as LINKED_EVALUATION_PROTOCOL, evaluate_linked_scene)
        from matlab_bridge import MatlabSession
        from neighborhood import make_n1_condition
        from neighborhood_adapter import evaluate_n1_scene
        from neighborhood_method import execute_n1_neighborhood
        from scene_adapter import canonical_hash

        # This is a distinct C-derived version, not an additional presolve arm.
        if 'preeliminate_closed_anchors' in kwargs:
            raise ValueError('Conditional release always retains C anchor preelimination')
        from milp import build_model
        original_builder = kwargs.pop('model_builder', build_model)

        def anchor_builder(instance, config, **options):
            active = options.get('neighborhood_condition', {})
            if active.get('protocol') == LINKED_CONDITION_PROTOCOL:
                # Rebuild against the actual remaining closed anchors. Never
                # reuse the old fixed-mask option list or merely append labels.
                options['preeliminate_closed_anchors'] = True
            return original_builder(instance, config, **options)

        kwargs['model_builder'] = anchor_builder

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
        anchor = {'seed': None, 'last_first_pass': None, 'frozen': None,
                  'baseline_condition': None, 'selection': None,
                  'selection_state': 'NOT_ENTERED', 'selection_started_at_s': None,
                  'selection_completed_at_s': None}
        input_state = {'config': None}

        def checked_loader(active_budget):
            config, instance = input_loader(active_budget)
            # Reject an invalid second-domain declaration before constructing
            # or searching the first pass, under the same billed input phase.
            with active_budget.phase('linked_domain_declaration_validation'):
                _opened(instance, declared_linked, active_budget)
                input_state['config'] = deepcopy(config)
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
                    if update['phase_index'] == 0:
                        if anchor['seed'] is not None:
                            raise ValueError('Conditional release expects one complete original seed generation')
                        anchor['seed'] = deepcopy(snapshot)
                    anchor['last_first_pass'] = deepcopy(snapshot)
            # Charge the caller observer in exactly the same root budget.
            if user_observer is not None:
                user_observer(result, update)

        def linked_opened(instance, active_budget):
            # The N1 lifecycle invokes this only after the original worker is
            # idle, both first-pass scene searches settled and root checked.
            if active_budget is not budget:
                raise ValueError('Conditional release must retain the original root Budget')
            with active_budget.phase('linked_release_anchor_and_selection'):
                if (anchor['frozen'] is not None or anchor['selection'] is not None
                        or anchor['last_first_pass'] is None or anchor['seed'] is None):
                    raise ValueError('Release selection needs one unfrozen complete first-pass SAFE generation')
                frozen = deepcopy(anchor['last_first_pass'])
                frozen['candidate_sha256'] = canonical_hash(frozen['safe_candidate'])
                frozen['receipt_sha256'] = frozen['aggregation']['receipt_sha256']
                anchor['frozen'] = frozen
                anchor['selection_state'] = 'FROZEN_BEFORE_SELECTION'
                anchor['selection_started_at_s'] = active_budget.elapsed
                seed = anchor['seed']
                accuracy = _accuracy(input_state['config']['accuracy_targets'])
                factory = (make_linked_condition if second_condition_factory is None
                           else second_condition_factory)
                # Validate the complete SAFE pair before asking the selector.
                # This preserves original unit, input/source and Budget gates.
                baseline = factory(instance, shared_deployment,
                    seed['safe_candidate'], seed['aggregation'], declared_linked,
                    warm_candidate=frozen['safe_candidate'],
                    warm_receipt=frozen['aggregation'], budget=active_budget,
                    accuracy=accuracy)
                baseline = validate_linked_condition(instance, baseline,
                    budget=active_budget, shared_deployment=shared_deployment)
                anchor['baseline_condition'] = deepcopy(baseline)
                baseline_hash = canonical_hash(baseline)
                selected = select_release(instance, baseline, budget=active_budget)
                if canonical_hash(baseline) != baseline_hash:
                    raise ValueError('Release selector modified its frozen baseline condition')
                if (not isinstance(selected, dict)
                        or set(selected) != {'opened_by_scene', 'receipt'}
                        or not isinstance(selected['receipt'], dict)):
                    raise ValueError('Release selector returned an invalid selection receipt')
                validate_selection(instance, baseline, selected, budget=active_budget)
                masks = _opened(instance, selected['opened_by_scene'], active_budget)
                original = baseline['opened_by_scene']
                for sid, values in original.items():
                    if (not set(values) <= set(masks[sid])
                            or len(set(masks[sid])-set(values)) > 1):
                        raise ValueError('Release selection must preserve C and add at most one Stage per scene')
                active_budget.check()
                anchor['selection'] = {'opened_by_scene': deepcopy(masks),
                    'receipt': deepcopy(selected['receipt']),
                    'receipt_sha256': canonical_hash(selected['receipt']),
                    'baseline_condition_sha256': baseline['condition_sha256'],
                    'frozen_candidate_sha256': frozen['candidate_sha256'],
                    'frozen_receipt_sha256': frozen['receipt_sha256']}
                anchor['selection_state'] = 'SELECTED_ONCE'
                anchor['selection_completed_at_s'] = active_budget.elapsed
                return deepcopy(masks)

        def linked_condition(instance, deployment, seed_candidate, seed_receipt,
                             opened, *, budget, accuracy):
            with budget.phase('linked_release_selected_condition'):
                frozen = anchor['frozen']
                selection = anchor['selection']
                baseline = anchor['baseline_condition']
                if (frozen is None or selection is None or baseline is None
                        or anchor['selection_state'] != 'SELECTED_ONCE'):
                    raise ValueError('Release condition requires one already frozen S1/mask selection')
                if (canonical_hash(seed_candidate) != baseline['seed_candidate_sha256']
                        or seed_receipt.get('receipt_sha256') != baseline['seed_receipt_sha256']
                        or canonical_hash(seed_receipt) != canonical_hash(baseline['seed_receipt'])
                        or _accuracy(accuracy) != baseline['accuracy']
                        or opened != selection['opened_by_scene']
                        or canonical_hash(frozen['safe_candidate']) != selection['frozen_candidate_sha256']
                        or frozen['aggregation'].get('receipt_sha256') != selection['frozen_receipt_sha256']):
                    raise ValueError('Release condition and selection must use the identical seed, complete S1 and masks')
                if canonical_hash(selection['receipt']) != selection['receipt_sha256']:
                    raise ValueError('Frozen release receipt changed after selection')
                validate_selection(instance, baseline, {
                    'opened_by_scene': selection['opened_by_scene'],
                    'receipt': selection['receipt']}, budget=budget)
                factory = (make_linked_condition if second_condition_factory is None
                           else second_condition_factory)
                condition = factory(instance, deployment, seed_candidate, seed_receipt, opened,
                    warm_candidate=frozen['safe_candidate'], warm_receipt=frozen['aggregation'],
                    budget=budget, accuracy=accuracy)
                condition = validate_linked_condition(instance, condition,
                    budget=budget, shared_deployment=deployment)
                if (condition['opened_by_scene'] != selection['opened_by_scene']
                        or condition['seed_candidate_sha256'] != baseline['seed_candidate_sha256']
                        or condition['seed_receipt_sha256'] != baseline['seed_receipt_sha256']
                        or condition['warm_candidate_sha256'] != selection['frozen_candidate_sha256']
                        or condition['warm_receipt_sha256'] != selection['frozen_receipt_sha256']):
                    raise ValueError('Release final condition differs from its frozen SAFE selection')
                budget.check()
                selection['final_condition_sha256'] = condition['condition_sha256']
                anchor['selection_state'] = 'FINAL_CONDITION_BOUND'
                return condition

        labels = {
            'protocol': PROTOCOL, 'name': 'N1',
            'search_scope': 'one fresh seed: N1 then a C-superset linked domain selected from its own frozen complete S1; devices fixed',
            'initialisation_fallback': 'rejected x0 permits bare current-domain MILP; missing complete SAFE seed stops',
            'inner_solution_source': 'N1_inner_MILP',
            'model_violation_source': 'N1_solver_model_view',
            'original_violation_source': 'N1_original_input_scene_receipt',
            'original_evaluation_phase': 'original_input_n1_scene_evaluation',
            'model_evaluation_phase': 'initial_n1_model_view_evaluation',
            'no_seed_reason': 'NO_COMPLETE_SAFE_LINKED_SEED',
            'bound_scope': 'seed_defined_N1_fixed_shared_deployment_unweighted_scene',
            'environment_scope': 'bounded linked-neighborhood correctness/method invocation; not a formal comparison'}
        second_labels = dict(labels, name='conditional-release linked OPP/start, warm-closed, complement transport',
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
            phase['name'] = 'linked_conditional_release_opp_start_warm_closed'
    result['augmented_transport'] = context.summary()
    frozen = anchor['frozen']
    result['linked_record_contract'] = {
        'condition_and_opened_by_scene': 'first-pass N1 declarations',
        'baseline_linked_opened_by_scene': declared_linked,
        'linked_opened_by_scene': None if anchor['selection'] is None else deepcopy(anchor['selection']['opened_by_scene']),
        'closed_choice_anchor': 'last complete first-pass SAFE generation, frozen once before phase 2',
        'closed_anchor_candidate_sha256': None if frozen is None else frozen.get('candidate_sha256'),
        'closed_anchor_phase_index': None if frozen is None else frozen.get('phase_index'),
        'closed_anchor_committed_at_s': None if frozen is None else frozen.get('committed_at_s'),
        'units': 'original fresh-seed units across both phases',
        'scenes': 'latest local metadata; may precede the last complete global aggregate',
        'phases': 'per-pass condition, model, initialisation and solver records',
        'committed_safe_snapshot': 'only complete global generation and second-pass warm source'}
    result['linked_record_contract']['closed_anchor_preelimination'] = {
        'enabled': True, 'phase_indices': [2],
        'scope': 'rebuild legal options against remaining closed anchors; original C integer schedules retained'}
    result['conditional_release'] = {
        'selection_state': anchor['selection_state'],
        'selection_started_at_s': anchor['selection_started_at_s'],
        'selection_completed_at_s': anchor['selection_completed_at_s'],
        'selection': deepcopy(anchor['selection']),
        'frozen_first_pass_safe_snapshot': deepcopy(frozen),
        'baseline_condition': deepcopy(anchor['baseline_condition']),
        'maximum_added_stages_per_scene': 1,
        'added_search_passes': 0,
        'policy_changes_physical_evaluation': False}
    result['linked_budget_boundary'] = {
        'entry_owns_budget': entry_owns_budget,
        'clock_begins_before_adapter_import_and_context': True,
        'identical_budget_forwarded_to_both_passes': True,
        'anchor_capture_freeze_selection_validation_and_observer_billed': True,
        'native_session_factory_calls_expected': 1,
        'tail_summary_scope': 'post-cutoff copying/serialization only; no new evidence'}
    result['timing']['clock_origin'] = 'before conditional-release linked-entry lazy imports/context and input read; one absolute deadline'
    from pathlib import Path
    from scene_method import _save
    try:
        _save(Path(workdir)/'augmented_transport.json', result['augmented_transport'])
        _save(Path(workdir)/'result.json', result)
    except Exception as error:
        result.setdefault('technical_state_before_archive', result.get('technical_state'))
        result.update(technical_state='FAILED', archive_complete=False)
        result.setdefault('archive_errors', []).append({
            'source': 'conditional-release linked method post-budget archival',
            'exception_type': type(error).__name__, 'message': str(error)})
    return result
