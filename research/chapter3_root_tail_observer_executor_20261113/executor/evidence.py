"""Formal 600-second scientific evidence classification. No scientific calls."""
from fractions import Fraction
import math
from budget_policy import ResponseDeadline

SECONDS = 600.0
NATIVE_SECONDS = None
RESERVE = 60.0
WATCHDOG = 680.0


class StopWindow(Exception):
    pass


class InsufficientNativeBudget(Exception):
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


def progress(events, objective_reference, cutoff=SECONDS, baseline_bound=None):
    """Native bounds remain solver-reported; the reference is numerical, not exact feasible."""
    valid = [e for e in events if timely(e.get('received_elapsed_s')) and e['received_elapsed_s']<cutoff]
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
    advances = [b for b in checked if baseline_bound is not None and Fraction(b['value_exact_binary64'])>Fraction(baseline_bound)]
    vectors = [dict(event_number=e.get('event_number'), received_elapsed_s=e['received_elapsed_s'],
                    state='AVAILABLE_UNVALIDATED', length=len(e['x']))
               for e in valid if isinstance(e.get('x'), list) and e['x']]
    root_objectives=[dict(event_number=e.get('event_number'),received_elapsed_s=e['received_elapsed_s'],
        value=e['values'].get('fval'),source='rootlp callback fval; native root LP objective, not a returned integer candidate',
        independently_certified=False) for e in roots]
    basis='ROOTLP_CALLBACK_AND_LATER_PHASE' if roots and later else ('ROOTLP_CALLBACK' if roots else ('LATER_PHASE' if later else 'UNKNOWN'))
    return dict(root_lp_entry_observed=bool(roots), root_lp_completion_via_later_phase=bool(later),
                root_lp_completion_observed=bool(roots or later),root_lp_completion_basis=basis,
                root_lp_native_objectives=root_objectives,
                root_lp_semantics_source='https://www.mathworks.com/help/releases/R2023b/optim/ug/intlinprog-output-functions-and-plot-functions.html',
                root_lp_actual_completion='OBSERVED_LATER_PHASE' if later else 'UNKNOWN',
                finite_bounds=bounds, best_consistent_native_bound=max(checked, key=lambda b:b['value']) if checked else None,
                box_lower_bound_exact=baseline_bound,native_bound_exceeds_box_bound=bool(advances),
                independent_lower_bound_certificate=False, callback_vectors=vectors,
                callback_counter_records=[dict(event_number=e.get('event_number'), state=e.get('state'),
                    numfeaspoints=e.get('values', {}).get('numfeaspoints')) for e in valid if e.get('kind') == 'callback'])

