"""Fresh fixed-unit search with every Stage's legal OPP/start retained.

This is a separate protocol, not an expansion or relabeling of historical N1.
Shared deployment is supplied explicitly; every remaining unit is selected by
this invocation's fresh complete SAFE seed. No candidate or thermal cache is
accepted from another invocation.
"""
from fixed_unit_neighborhood import (PROTOCOL as CONDITION_PROTOCOL,
    make_fixed_unit_condition, check_fixed_unit_candidate)
from fixed_unit_neighborhood_adapter import (PROTOCOL as EVALUATION_PROTOCOL,
                                             evaluate_fixed_unit_scene)
from neighborhood_method import execute_n1_neighborhood


PROTOCOL = 'fresh-seed-fixed-unit-all-stage-opp-start-live-scenes-v1'


def execute_fixed_unit_opp_start(input_loader, workdir, *, shared_deployment,
        condition_factory=make_fixed_unit_condition,
        scene_evaluator=evaluate_fixed_unit_scene, **kwargs):
    """Reuse the budget lifecycle with the independently checked new domain.

    All opened Stage identities are derived from the freshly loaded original
    input inside the same MethodBudget. The caller cannot pass an opening
    subset, replace membership semantics or override the declared scope.
    Other lifecycle arguments keep their existing meanings, including the
    dependency-injection seams used only for correctness prechecks.
    """
    reserved = {'opened_by_scene', 'membership_checker', 'evaluation_protocol',
                'condition_protocol', '_method_identity', 'n1_scene_evaluator'}
    if set(kwargs) & reserved:
        raise ValueError('Fixed-unit method owns its all-Stage domain and protocol identities')
    opened = {}

    def billed_loader(budget):
        config, instance = input_loader(budget)
        for scene in instance['scenarios']:
            budget.check()
            sid = scene['id']
            if sid in opened:
                raise ValueError('Duplicate scene identity in fixed-unit input')
            opened[sid] = []
            for stage in scene['stage_instances']:
                budget.check()
                opened[sid].append(stage['id'])
        budget.check()
        return config, instance

    labels = {
        'protocol': PROTOCOL, 'name': 'fixed-unit all-Stage OPP/start',
        'search_scope': 'this invocation seed-fixed execution units, every Stage original OPP/start; original full domain retained',
        'initialisation_fallback': 'rejected x0 permits bare fixed-unit MILP; missing complete SAFE seed stops',
        'inner_solution_source': 'fixed_unit_inner_MILP',
        'model_violation_source': 'fixed_unit_solver_model_view',
        'original_violation_source': 'fixed_unit_original_input_scene_receipt',
        'original_evaluation_phase': 'original_input_fixed_unit_scene_evaluation',
        'model_evaluation_phase': 'initial_fixed_unit_model_view_evaluation',
        'no_seed_reason': 'NO_COMPLETE_SAFE_FIXED_UNIT_SEED',
        'bound_scope': 'seed_fixed_units_all_stage_opp_start_unweighted_scene',
        'environment_scope': 'fresh SAFE seed fixed-unit all-Stage OPP/start correctness/method invocation; not a formal comparison'}
    return execute_n1_neighborhood(billed_loader, workdir,
        shared_deployment=shared_deployment, opened_by_scene=opened,
        condition_factory=condition_factory, n1_scene_evaluator=scene_evaluator,
        membership_checker=check_fixed_unit_candidate,
        evaluation_protocol=EVALUATION_PROTOCOL, condition_protocol=CONDITION_PROTOCOL,
        _method_identity=labels, **kwargs)
