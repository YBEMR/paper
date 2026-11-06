"""Isolated live enhanced-HEFT initialization; original science is not edited.

The original lifecycle constructs the full model and starts MATLAB before this
hook. HEFT, its archive, x0 completion and subsequent MILP share that same root.
The only cross-stage input is this invocation's selected SAFE candidate/receipt.
"""
from contextlib import contextmanager
from copy import deepcopy
from fractions import Fraction as F
import math
from pathlib import Path


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


@contextmanager
def install_initializer(instance, config, output, *, origin, deadline, audit_context=None):
    """Temporarily replace only prepare_initial_witness in this dedicated worker.

    instance/config are the freshly hash-verified frozen inputs, not candidate
    files. output must not exist. audit_context receives serializable evidence;
    it never receives the budget object, a callable, a cache, or an x0 vector.
    """
    import initial_point as initial
    from heuristic_runner import execute_heuristic
    from thermal import Exhausted
    from research.chapter3_experiments.natural_full_entry import receipt_failure
    from research.chapter3_method_entry_executor.common import inspect_safe_receipt

    require(type(origin) in (int, float) and math.isfinite(origin)
            and deadline == origin + 600, 'ONE_600_SECOND_ROOT_REQUIRED')
    output = Path(output).resolve()
    require(not output.exists(), 'NEW_HEFT_OUTPUT_REQUIRED')
    context = {} if audit_context is None else audit_context
    require(isinstance(context, dict) and not context, 'EMPTY_AUDIT_CONTEXT_REQUIRED')
    frozen_config = deepcopy(config)
    input_digest = initial._digest(instance)
    config_digest = initial._digest(frozen_config)
    accuracy_digest = initial._digest(frozen_config['accuracy_targets'])
    original_prepare = initial.prepare_initial_witness
    original_complete = initial.complete_initial_point
    original_evaluate = initial.evaluate_model_candidate
    context.update(variant='live-enhanced-heft-initialized-milp', called=False,
        sequence='original full model -> original MATLAB ready -> full live enhanced HEFT -> x0 -> original MILP loop',
        origin=origin, deadline=deadline, seconds=600, input_digest=input_digest,
        config_digest=config_digest, accuracy_digest=accuracy_digest,
        output=str(output), historical_candidate_input=False, cache_transferred_to_milp=False,
        hook_restored=False)

    def prepare(model, accuracy, budget, starts=None, max_attempts=3):
        require(context['called'] is False, 'LIVE_HEFT_INITIALIZER_IS_SINGLE_USE')
        context['called'] = True
        result = dict(state='UNRESOLVED', witness=None, x0=None, attempts=[], completion=None,
            reason='NO_SAFE_LIVE_HEFT_WITNESS', remaining_domain='retained',
            independently_proven_infeasible=False, initializer='live_enhanced_heft',
            historical_candidate_input=False, cache_transferred_to_milp=False)

        def check_identity(received_budget):
            require(received_budget is budget and model.budget is budget, 'SHARED_BUDGET_OBJECT_REQUIRED')
            require(budget.start == origin and budget.deadline == deadline and budget.seconds == 600,
                    'ROOT_CLOCK_DRIFT')
            require(initial._digest(model.instance) == input_digest
                    and initial._digest(frozen_config) == config_digest
                    and initial._digest(accuracy) == accuracy_digest, 'FROZEN_INPUT_OR_ACCURACY_DRIFT')

        def preserve_formed_safe():
            safe = context.get('formed_heft_safe') or {}
            if result['witness'] is None and safe.get('preserved'):
                result['witness'] = dict(candidate=deepcopy(safe['candidate']),
                    evaluation=deepcopy(safe['evaluation']), source='live_enhanced_heft')
                context['heft_safe_receipt'] = deepcopy(safe)
                context['heft_safe_formed_at_s'] = safe['formed_at_s']

        try:
            require(starts is None, 'REDUCED_START_DOMAIN_FORBIDDEN')
            check_identity(budget)
            context.update(root_budget_object_id=id(budget), root_start=budget.start,
                           root_deadline=budget.deadline, hook_entered_at_s=budget.elapsed)
            budget.check()

            def loader(received_budget):
                check_identity(received_budget)
                received_budget.check()
                return frozen_config, model.instance

            def evaluator(received_instance, candidate, received_accuracy, received_budget):
                check_identity(received_budget)
                require(received_instance is model.instance and initial._digest(received_accuracy) == accuracy_digest,
                        'HEFT_EVALUATOR_IDENTITY_DRIFT')
                received_budget.check()
                # Use the actual full model and the unchanged original identity-
                # binding evaluator; no proxy, cached receipt, or later relabeling.
                evaluation = original_evaluate(model, candidate, received_accuracy, received_budget)
                failure = receipt_failure(evaluation)
                if failure:
                    context['evaluation_technical_failure'] = deepcopy(evaluation)
                    raise RuntimeError('HEFT_FULL_EVALUATION_TECHNICAL_FAILURE:' + failure)
                # Evaluation-only evidence is NOT an admission commit. If HEFT's later
                # charged candidate archive fails, preserve_formed_safe cannot promote it.
                # Only the returned charged recorder result can supply a witness.
                safe = inspect_safe_receipt(model.instance, dict(safe_candidate=candidate,
                    evaluation=evaluation, safe_upper_bound_J=evaluation.get('safe_upper_bound_J')), 600)
                previous = context.get('formed_heft_evaluation_evidence') or {}
                if safe['preserved'] and (not previous.get('preserved') or F(safe['U_J']) < F(previous['U_J'])):
                    context['formed_heft_evaluation_evidence'] = deepcopy(safe)
                return evaluation

            context['heft_started_at_s'] = budget.elapsed
            context['heft_remaining_before_s'] = budget.remaining
            with budget.phase('online_heft_including_archive'):
                heft = execute_heuristic(loader, output, method='heft', seconds=600,
                    budget=budget, allow_auto_low=True, evaluator=evaluator)
            context.update(heft_returned_at_s=budget.elapsed, heft_remaining_after_s=budget.remaining,
                heft_total_including_archive_s=budget.elapsed-context['heft_started_at_s'],
                heft_raw=deepcopy(heft))
            safe = inspect_safe_receipt(model.instance, heft, 600)
            context['heft_safe_receipt'] = deepcopy(safe)
            if safe['preserved']:
                result['witness'] = dict(candidate=deepcopy(safe['candidate']),
                    evaluation=deepcopy(safe['evaluation']), source='live_enhanced_heft')
                context['heft_safe_formed_at_s'] = safe['formed_at_s']
            failure = receipt_failure(heft)
            if failure or context.get('evaluation_technical_failure'):
                preserve_formed_safe()
                result.update(state='SAFE_POINT_REJECTED' if result['witness'] else 'UNRESOLVED',
                    reason=heft.get('reason') or 'INITIALISATION_ERROR', technical_state='TECHNICAL_FAILURE',
                    error=str(failure or 'HEFT_FULL_EVALUATION_TECHNICAL_FAILURE'))
            elif budget.remaining <= 0 or heft.get('budget_exhausted') is True:
                result.update(state='SAFE_POINT_UNRESOLVED' if result['witness'] else 'UNRESOLVED',
                              reason='wall_time_limit')
            else:
                require(heft.get('reason') == 'DECLARED_SEARCH_COMPLETED'
                        and (heft.get('search') or {}).get('status') in
                            ('BOUNDED_SEARCH_COMPLETED', 'NO_SAFE_CONSTRUCTED_WITNESS'),
                        'FULL_ENHANCED_HEFT_DID_NOT_COMPLETE')
                context['full_enhanced_heft_completed'] = True
                if result['witness']:
                    check_identity(budget)
                    budget.check()
                    completion = original_complete(model, result['witness']['candidate'],
                                                   result['witness']['evaluation'], budget)
                    result['x0'] = completion.pop('x0')
                    result['completion'] = completion
                    result.update(state='SAFE_POINT_READY' if result['x0'] is not None else 'SAFE_POINT_REJECTED',
                                  reason=completion['state'])
        except Exhausted as error:
            preserve_formed_safe()
            result.update(state='SAFE_POINT_UNRESOLVED' if result['witness'] else 'UNRESOLVED',
                          reason=str(error))
        except Exception as error:
            preserve_formed_safe()
            result.update(state='SAFE_POINT_REJECTED' if result['witness'] else 'UNRESOLVED',
                reason='INITIALISATION_ERROR', technical_state='TECHNICAL_FAILURE',
                error=type(error).__name__ + ': ' + str(error))
        result['completed_at_s'] = budget.elapsed
        public = {key: deepcopy(value) for key, value in result.items() if key != 'x0'}
        context.update(initialisation=public, hook_returned_at_s=budget.elapsed,
                       remaining_at_hook_return_s=budget.remaining,
                       x0_ready=result['state'] == 'SAFE_POINT_READY')
        return result

    initial.prepare_initial_witness = prepare
    try:
        yield context
    finally:
        initial.prepare_initial_witness = original_prepare
        context['hook_restored'] = True
