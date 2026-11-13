"""Two bounded passes over one fresh-seed fixed-unit invocation.

The first pass keeps the caller's explicit N1 opening and scene cap. The
second pass visits each scene once with every Stage's original OPP/start
domain, using the same seed-fixed units, complete SAFE ledger, worker and
absolute budget. Only its request transport uses exact-row complements.
"""
import time


PROTOCOL = 'fresh-seed-n1-then-all-stage-opp-start-complement-live-scenes-v1'


def execute_staged_fixed_unit_opp_start(input_loader, workdir, *,
        shared_deployment, opened_by_scene, seconds=300, scene_slice_s=60,
        budget=None, clock=time.monotonic, session_factory=None,
        condition_factory=None, second_condition_factory=None,
        n1_scene_evaluator=None, second_scene_evaluator=None,
        augmented_context_factory=None, **kwargs):
    """Search at most two passes; no caller-provided seed or prior evidence.

    ``condition_factory``/``n1_scene_evaluator`` inject first-pass operations;
    ``second_condition_factory``/``second_scene_evaluator`` inject second-pass
    operations under their owned protocol and membership checks. The normal
    lifecycle seams in kwargs retain their meanings. ``recorder_factory`` is
    first-pass only; second-pass admission belongs to AugmentedMethodContext.
    A context subclass may inject a tiny decoder for correctness fixtures,
    while retaining the existing original-row gate and invocation latch.
    """
    entry_started = clock() if budget is None else None
    from timing import MethodBudget
    entry_owns_budget = budget is None
    if entry_owns_budget:
        budget = MethodBudget(float(seconds), clock=clock)
        # Charge even the lazy budget-module import to this invocation.
        budget.start = entry_started
        budget.deadline = entry_started + float(seconds)
    elif not isinstance(budget, MethodBudget):
        raise TypeError('budget must be the caller-owned MethodBudget')
    else:
        clock = budget.clock
    budget.check()
    with budget.phase('staged_adapter_initialisation'):
        import math
        from augmented_method import AugmentedMethodContext, AugmentedSession
        from fixed_unit_neighborhood import (PROTOCOL as FULL_CONDITION_PROTOCOL,
            make_fixed_unit_condition, check_fixed_unit_candidate)
        from fixed_unit_neighborhood_adapter import (
            PROTOCOL as FULL_EVALUATION_PROTOCOL, evaluate_fixed_unit_scene)
        from matlab_bridge import MatlabSession
        from neighborhood import make_n1_condition
        from neighborhood_adapter import evaluate_n1_scene
        from neighborhood_method import execute_n1_neighborhood

        reserved = {'membership_checker', 'evaluation_protocol', 'condition_protocol',
                    '_method_identity', '_second_phase'}
        if set(kwargs) & reserved:
            raise ValueError('Staged method owns both domains and protocol identities')
        if (isinstance(scene_slice_s, bool) or not isinstance(scene_slice_s, (int, float))
                or not math.isfinite(scene_slice_s) or not 0 < scene_slice_s <= 60):
            raise ValueError('Staged scene cap must be finite and in (0, 60] seconds')
        native_factory = MatlabSession if session_factory is None else session_factory
        context_factory = (AugmentedMethodContext if augmented_context_factory is None
                           else augmented_context_factory)
        if not callable(context_factory) or not callable(native_factory):
            raise TypeError('Context and session factories must be callable')
        context = context_factory(session_factory=native_factory)
        if not isinstance(context, AugmentedMethodContext):
            raise TypeError('Second-pass context must retain AugmentedMethodContext admission')

        def all_opened(instance, active_budget):
            opened = {}
            for scene in instance['scenarios']:
                active_budget.check()
                sid = scene['id']
                if sid in opened:
                    raise ValueError('Duplicate scene identity in staged input')
                opened[sid] = []
                for stage in scene['stage_instances']:
                    active_budget.check()
                    opened[sid].append(stage['id'])
            active_budget.check()
            return opened

        labels = {
            'protocol': PROTOCOL, 'name': 'N1',
            'search_scope': 'one fresh seed: explicit N1 then all-Stage original OPP/start on the same fixed units; original full domain retained',
            'initialisation_fallback': 'rejected x0 permits bare current-domain MILP; missing complete SAFE seed stops',
            'inner_solution_source': 'N1_inner_MILP',
            'model_violation_source': 'N1_solver_model_view',
            'original_violation_source': 'N1_original_input_scene_receipt',
            'original_evaluation_phase': 'original_input_n1_scene_evaluation',
            'model_evaluation_phase': 'initial_n1_model_view_evaluation',
            'no_seed_reason': 'NO_COMPLETE_SAFE_STAGED_SEED',
            'bound_scope': 'seed_defined_N1_fixed_shared_deployment_unweighted_scene',
            'environment_scope': 'bounded two-pass correctness/method invocation; not a formal comparison'}
        second_labels = dict(labels, name='all-Stage OPP/start, complement transport',
            inner_solution_source='staged_fixed_unit_complement_inner_MILP',
            model_violation_source='fixed_unit_complement_solver_model_view',
            original_violation_source='fixed_unit_complement_original_input_scene_receipt',
            original_evaluation_phase='original_input_fixed_unit_scene_evaluation',
            model_evaluation_phase='initial_fixed_unit_model_view_evaluation',
            bound_scope='seed_fixed_units_all_stage_opp_start_unweighted_scene')
        second = {
            'condition_factory': (make_fixed_unit_condition if second_condition_factory is None
                                  else second_condition_factory),
            'opened': all_opened, 'membership_checker': check_fixed_unit_candidate,
            'scene_evaluator': (evaluate_fixed_unit_scene if second_scene_evaluator is None
                                else second_scene_evaluator),
            'evaluation_protocol': FULL_EVALUATION_PROTOCOL,
            'condition_protocol': FULL_CONDITION_PROTOCOL,
            'recorder_factory': context.recorder_factory,
            'session_adapter': lambda native: AugmentedSession(native, context),
            'latched': lambda: context.failed, 'identity': second_labels}

    result = execute_n1_neighborhood(input_loader, workdir,
        shared_deployment=shared_deployment, opened_by_scene=opened_by_scene,
        seconds=seconds, scene_slice_s=scene_slice_s, budget=budget, clock=clock,
        session_factory=native_factory,
        condition_factory=make_n1_condition if condition_factory is None else condition_factory,
        n1_scene_evaluator=evaluate_n1_scene if n1_scene_evaluator is None else n1_scene_evaluator,
        _method_identity=labels, _second_phase=second, **kwargs)
    # This tail only copies/serializes already formed transport evidence.
    # It cannot form a new numerical, thermal, energy or bound receipt.
    result['augmented_transport'] = context.summary()
    result['staged_record_contract'] = {
        'condition_and_opened_by_scene': 'first-pass N1 declarations',
        'scenes': 'latest local metadata; may precede the last complete global aggregate',
        'phases': 'per-pass condition, model, initialisation and solver records',
        'committed_safe_snapshot': 'only complete global generation and second-pass warm source'}
    result['staged_budget_boundary'] = {
        'entry_owns_budget': entry_owns_budget,
        'clock_begins_before_adapter_import_and_context': True,
        'identical_budget_forwarded_to_both_passes': True,
        'native_session_factory_calls_expected': 1,
        'tail_summary_scope': 'post-cutoff copying/serialization only; no new evidence'}
    result['timing']['clock_origin'] = 'before staged-entry lazy imports/context and input read; one absolute deadline'
    from pathlib import Path
    from scene_method import _save
    try:
        _save(Path(workdir)/'augmented_transport.json', result['augmented_transport'])
        _save(Path(workdir)/'result.json', result)
    except Exception as error:
        result.setdefault('technical_state_before_archive', result.get('technical_state'))
        result.update(technical_state='FAILED', archive_complete=False)
        result.setdefault('archive_errors', []).append({
            'source': 'staged method post-budget archival',
            'exception_type': type(error).__name__, 'message': str(error)})
    return result
