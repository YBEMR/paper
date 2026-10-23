"""N1 membership guard followed by the original full-input scene evaluator.

No search, repair, candidate cache or aggregation is performed. The physical
receipt is returned unchanged, so existing original-input aggregation remains
the only route to a weighted U. A retained local SAFE is not global optimality.
"""
from thermal import Exhausted, _accuracy
from neighborhood import check_n1_candidate
from scene_adapter import evaluate_partial_scene, _partial_scene_energy


PROTOCOL = 'n1-original-input-scene-evaluation-v1'


def evaluate_n1_scene(instance, condition, scene_id, candidate, *, budget,
                      accuracy=None):
    """Evaluate a complete member scene; never rewrite fixed choices.

    The supplied Budget must be the one bound to the seed. Completed inner
    evidence is transferred before any outer deadline decision. This wrapper
    produces no new global energy upper bound and does not alter the receipt.
    """
    out = {'protocol': PROTOCOL, 'state': 'UNRESOLVED', 'reason': None,
           'condition_sha256': None, 'scenario_id': scene_id,
           'member': False, 'receipt': None, 'rankable_energy': False,
           'independently_proven_optimal': False,
           'independently_proven_infeasible': False,
           'scope': 'local_condition_original_full_scene_evaluation_not_global'}
    try:
        membership = check_n1_candidate(instance, condition, candidate,
                                         budget=budget, scene_id=scene_id)
        requested = _accuracy(condition['accuracy'] if accuracy is None else accuracy)
        if requested != condition['accuracy']:
            raise ValueError('N1 evaluation accuracy must match the seed condition')
        out.update(member=True, condition_sha256=membership['condition_sha256'])
        receipt = evaluate_partial_scene(instance, scene_id,
            condition['shared_deployment'], candidate, requested, budget)
        # Do not check the current clock here: an already committed violation
        # or SAFE receipt must survive a deadline crossed during return.
        out['receipt'] = receipt
        out.update(state=receipt['state'], reason=receipt['reason'])
        if receipt['state'] == 'SAFE':
            try:
                _partial_scene_energy(instance, scene_id, receipt, budget)
            except (KeyError, TypeError, ValueError, ArithmeticError):
                out.update(state='UNRESOLVED', reason='INCONSISTENT_OR_LATE_SAFE_RECEIPT')
            else:
                out['rankable_energy'] = True
    except Exhausted as error:
        out.update(state='UNRESOLVED', reason=str(error), budget_exhausted=True)
    except MemoryError:
        out.update(state='UNRESOLVED', reason='RESOURCE_LIMIT')
    except ArithmeticError as error:
        out.update(state='UNRESOLVED', reason='NUMERICAL_ERROR',
                   error_type=type(error).__name__)
    except (KeyError, TypeError, ValueError) as error:
        out.update(state='INVALID_INPUT', reason=str(error),
                   error_type=type(error).__name__)
    return out
