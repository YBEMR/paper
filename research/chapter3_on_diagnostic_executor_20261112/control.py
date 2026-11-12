"""One-shot ON diagnostic policy. Standard library only; no scientific calls."""
from fractions import Fraction
import math

SECONDS = 300.0
NATIVE_SECONDS = 240.0
RESERVE = 10.0
WATCHDOG = 380.0


class StopWindow(Exception):
    pass


def timely(elapsed):
    return isinstance(elapsed, (int, float)) and not isinstance(elapsed, bool) and 0 <= elapsed < SECONDS


def full_safe(evaluation, scene_count):
    return bool(evaluation and evaluation.get('state') == 'SAFE'
                and evaluation.get('rankable_energy') is True
                and timely(evaluation.get('completed_at_elapsed_s'))
                and len(evaluation.get('scenes', {})) == scene_count
                and all(s.get('complete') is True and s.get('state') == 'SAFE'
                        for s in evaluation['scenes'].values()))


def progress(events, objective_reference):
    """Native bounds remain solver-reported; the reference is numerical, not exact feasible."""
    valid = [e for e in events if timely(e.get('received_elapsed_s'))]
    roots = [e for e in valid if e.get('values', {}).get('phase') == 'rootlp']
    later = [e for e in valid if e.get('values', {}).get('phase') in ('heuristics', 'cutgen', 'branching')]
    bounds = []
    for e in valid:
        b = e.get('values', {}).get('lowerbound')
        if not isinstance(b, (int, float)) or isinstance(b, bool) or not math.isfinite(b):
            continue
        q = Fraction.from_float(float(b))
        consistency = 'UNKNOWN' if objective_reference is None else (
            'CONSISTENT_WITH_NUMERICAL_REFERENCE' if q <= Fraction(objective_reference) else 'CONFLICT')
        bounds.append(dict(value=b, value_exact_binary64=str(q), received_elapsed_s=e['received_elapsed_s'],
                           event_number=e.get('event_number'), consistency=consistency,
                           independently_certified=False))
    checked = [b for b in bounds if b['consistency'] == 'CONSISTENT_WITH_NUMERICAL_REFERENCE']
    vectors = [dict(event_number=e.get('event_number'), received_elapsed_s=e['received_elapsed_s'],
                    state='AVAILABLE_UNVALIDATED', length=len(e['x']))
               for e in valid if isinstance(e.get('x'), list) and e['x']]
    return dict(root_lp_entry_observed=bool(roots), root_lp_completion_via_later_phase=bool(later),
                root_lp_actual_completion='OBSERVED_LATER_PHASE' if later else 'UNKNOWN',
                finite_bounds=bounds, best_consistent_native_bound=max(checked, key=lambda b:b['value']) if checked else None,
                independent_lower_bound_certificate=False, callback_vectors=vectors,
                callback_counter_records=[dict(event_number=e.get('event_number'), state=e.get('state'),
                    numfeaspoints=e.get('values', {}).get('numfeaspoints')) for e in valid if e.get('kind') == 'callback'])


def execute(runtime):
    """Called only after a durable one-use claim. Tests inject a non-scientific runtime.

    The runtime is responsible for persistent raw receipts and absolute-time guards.
    There is exactly one solve call site and no iteration, retry, fallback or OFF arm.
    """
    result = dict(arm='ON', native_request_attempts=0, physical_evaluation_attempts=0,
                  initial_evaluation=None, returned_evaluation=None, candidate=None,
                  returned_vector_validation=None, same_initial=None, strict_energy_improvement=None,
                  error=None, terminal_state=None, cleanup=None, identity=None,
                  native=None, model_builds=0, formal_ABC_runs=0, retries=0)
    try:
        runtime.check()
        runtime.prepare()
        runtime.check()
        result['physical_evaluation_attempts'] += 1
        result['initial_evaluation'] = runtime.evaluate_initial()
        runtime.check()
        if not full_safe(result['initial_evaluation'], runtime.scene_count):
            result['terminal_state'] = 'INITIAL_SAFE_NOT_ESTABLISHED_NO_CALL'
        else:
            runtime.start_native()
            runtime.check()
            if runtime.remaining < NATIVE_SECONDS + RESERVE:
                result['terminal_state'] = 'INSUFFICIENT_FIXED_CAP_RESERVE_NO_CALL'
            else:
                result['native_request_attempts'] = 1
                native = runtime.solve(NATIVE_SECONDS)
                result['native'] = native
                # Identity must be checked regardless of vector, exitflag, or ordinary timeout.
                result['identity'] = runtime.inspect_identity(native)
                if result['identity']['state'] == 'INVALID':
                    result['terminal_state'] = 'INVALID_INPUT_OR_NATIVE_SETTINGS'
                elif (native.get('status') == 'SOLVED' and native.get('budget_valid') is True
                      and native.get('accepted_for_evaluation') is True and native.get('x')):
                    runtime.check()
                    validation = runtime.validate_returned(native['x'])
                    result['returned_vector_validation'] = validation
                    runtime.check()
                    if validation['state'] == 'ADMITTED':
                        result['candidate'] = validation['candidate']
                        result['same_initial'] = validation['same_initial']
                        result['physical_evaluation_attempts'] += 1
                        result['returned_evaluation'] = runtime.evaluate_returned(validation['candidate'])
                        if full_safe(result['returned_evaluation'], runtime.scene_count):
                            initial_interval = result['initial_evaluation']['weighted_energy_J']
                            returned_interval = result['returned_evaluation']['weighted_energy_J']
                            result['strict_energy_improvement'] = Fraction(returned_interval[1]) < Fraction(initial_interval[0])
                            result['terminal_state'] = 'RETURNED_COMPLETE_SAFE'
                        else:
                            result['terminal_state'] = 'RETURNED_PHYSICAL_SAFE_NOT_ESTABLISHED'
                    else:
                        result['terminal_state'] = 'RETURNED_VECTOR_REJECTED'
                elif native.get('status') == 'SOLVED' and native.get('exitflag') == 0:
                    result['terminal_state'] = 'ORDINARY_NATIVE_LIMIT_NO_ACCEPTED_VECTOR'
                elif str(native.get('status', '')).startswith('BUDGET_EXHAUSTED'):
                    result['terminal_state'] = 'DIAGNOSTIC_WINDOW_EXHAUSTED'
                elif native.get('status') == 'SOLVED' and native.get('exitflag') == -2:
                    result['terminal_state'] = 'NATIVE_INFEASIBILITY_REPORT_NOT_EXACT_PROOF'
                else:
                    result['terminal_state'] = 'OTHER_NATIVE_STATUS'
    except StopWindow:
        result['terminal_state'] = 'DIAGNOSTIC_WINDOW_EXHAUSTED'
    except Exception as error:
        result['terminal_state'] = 'EXECUTION_ERROR'
        result['error'] = dict(type=type(error).__name__, message=str(error))
    finally:
        result['method_elapsed_s'] = runtime.elapsed
        try:
            result['cleanup'] = runtime.close()
        except Exception as error:
            result['cleanup'] = dict(complete=False, error=repr(error))
        # Read-only integrity checks after cutoff may invalidate; they never create new solver/SAFE evidence.
        try:
            result['identity_after'] = runtime.verify_after()
        except Exception as error:
            result['identity_after'] = dict(state='INVALID', error=repr(error))
        result['total_elapsed_s'] = runtime.elapsed
    result['progress'] = progress(runtime.events, runtime.objective_reference)
    result['returned_complete_SAFE'] = full_safe(result['returned_evaluation'], runtime.scene_count)
    result['new_complete_SAFE'] = result['returned_complete_SAFE'] and result['same_initial'] is False
    after_identity = result['identity_after'].get('native_identity_after')
    if after_identity is not None:
        result['identity_before_cleanup'] = result['identity']
        if (result['identity'] or {}).get('state') != 'INVALID':
            result['identity'] = after_identity
    identity_ok = (result['identity'] or {}).get('state') == 'VERIFIED'
    after_ok = result['identity_after'].get('state') == 'VERIFIED'
    cleanup_ok = result['cleanup'].get('complete') is True
    native_status = (result['native'] or {}).get('status', '')
    status_ok = native_status == 'SOLVED' or native_status.startswith('BUDGET_EXHAUSTED')
    result['evidence_integrity'] = 'VERIFIED' if identity_ok and after_ok and cleanup_ok and result['error'] is None and status_ok else 'NOT_ESTABLISHED'
    p = result['progress']
    result['progress_observed'] = bool(p['root_lp_completion_via_later_phase']
        or p['best_consistent_native_bound'] is not None or result['new_complete_SAFE'])
    result['progress_usable'] = result['progress_observed'] and result['evidence_integrity'] == 'VERIFIED'
    result['bound_scope'] = 'Solver-reported, checked against admitted numerical MILP objective; not an independently certified valid bound.'
    result['next_action'] = 'STOP_NO_RETRY_NO_AUTOMATIC_ABC'
    return result
