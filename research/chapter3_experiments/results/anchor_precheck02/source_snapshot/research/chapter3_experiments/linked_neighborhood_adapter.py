"""Linked membership followed by original-input continuous scene evaluation."""
from linked_neighborhood import check_linked_candidate
from scene_adapter import evaluate_partial_scene, _partial_scene_energy
from thermal import Exhausted, _accuracy


PROTOCOL = 'linked-original-input-scene-evaluation-v1'


def evaluate_linked_scene(instance, condition, scene_id, candidate, *, budget, accuracy=None):
    out = {'protocol': PROTOCOL, 'state': 'UNRESOLVED', 'reason': None,
        'condition_sha256': None, 'scenario_id': scene_id, 'member': False,
        'receipt': None, 'rankable_energy': False, 'independently_proven_optimal': False,
        'independently_proven_infeasible': False,
        'scope': 'linked_original_full_scene_evaluation_not_global'}
    try:
        membership = check_linked_candidate(instance, condition, candidate,
                                             budget=budget, scene_id=scene_id)
        requested = _accuracy(condition['accuracy'] if accuracy is None else accuracy)
        if requested != condition['accuracy']:
            raise ValueError('Linked evaluation accuracy must match both SAFE anchors')
        out.update(member=True, condition_sha256=membership['condition_sha256'])
        receipt = evaluate_partial_scene(instance, scene_id, condition['shared_deployment'],
                                         candidate, requested, budget)
        # Preserve already formed evidence before testing a later clock state.
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
        out.update(state='UNRESOLVED', reason='NUMERICAL_ERROR', error_type=type(error).__name__)
    except (KeyError, TypeError, ValueError) as error:
        out.update(state='INVALID_INPUT', reason=str(error), error_type=type(error).__name__)
    return out
