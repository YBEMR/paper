"""K190 pure LP payload/return checks. This module has no solver entry."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
FIXED_CORE = REPO / 'research/chapter3_experiments/results/fixed_integer_native03/source_snapshot/core.py'
spec = importlib.util.spec_from_file_location('k190_frozen_numeric_reader', FIXED_CORE)
numeric = importlib.util.module_from_spec(spec)
spec.loader.exec_module(numeric)
LP_KEYS = ('c', 'A', 'b', 'Aeq', 'beq', 'lb', 'ub')


def make_relaxation(original):
    """Omit integrality only; do not copy K189's tightened bounds."""
    payload = {key: original[key].copy() for key in LP_KEYS}
    assert_identity(original, payload)
    return payload


def assert_identity(original, payload):
    if set(payload) != set(LP_KEYS):
        raise ValueError('LP must contain exactly the seven original numerical arguments')
    for key in LP_KEYS:
        same = (numeric._same_matrix(original[key], payload[key]) if key in ('A', 'Aeq')
                else numeric._same_array(original[key], payload[key]))
        if not same:
            raise ValueError('Original LP argument drift: ' + key)
    return dict(passed=True, seven_arguments_bitwise_preserved=True,
        integrality_only_omitted=True, original_integer_columns=len(original['intcon']),
        original_bounds_not_K189_fixed_bounds=True, x0_passed_to_solver=False,
        no_scaling_or_elimination=True)


def check_vector(original, payload, vector, fval=None, *, require_objective=True):
    """Original row/bound tolerances; integrality is measured but never required."""
    assert_identity(original, payload)
    out = dict(accepted=False, reasons=[], physical_safety_claim=False,
        new_safe_or_U=False, independent_lower_bound=False, integer_check_is_diagnostic_only=True,
        rounding_or_repair_performed=False, constraint_tolerance=1e-9)
    try:
        x = numeric._vector(vector, 'LP vector', len(original['c']))
    except (ValueError, TypeError, OverflowError) as error:
        out['reasons'].append(str(error))
        return out
    rows = original['A'] @ x - original['b']
    eq = original['Aeq'] @ x - original['beq']
    obj = float(original['c'] @ x)
    out.update(inequality_violation=float(np.max(rows, initial=0.)),
        equality_violation=float(np.max(np.abs(eq), initial=0.)),
        lower_bound_violation=float(np.max(original['lb']-x, initial=0.)),
        upper_bound_violation=float(np.max(x-original['ub'], initial=0.)),
        original_integer_distance=float(np.max(np.abs(x[original['intcon']]-np.rint(x[original['intcon']])), initial=0.)),
        objective=obj if np.isfinite(obj) else None)
    if not (np.isfinite(rows).all() and np.isfinite(eq).all() and np.isfinite(obj)):
        out['reasons'].append('NONFINITE_RESIDUAL_OR_OBJECTIVE')
    if any(out[key] > 1e-9 for key in ('inequality_violation','equality_violation',
                                      'lower_bound_violation','upper_bound_violation')):
        out['reasons'].append('ORIGINAL_ROW_OR_BOUND_VIOLATION')
    consistent = not require_objective
    if fval is not None:
        try:
            reported = numeric._vector(fval, 'fval', 1)[0]
            error = abs(float(reported)-obj)
            consistent = bool(np.isfinite(error) and error <= 1e-9*max(1.,abs(obj)))
            out['objective_absolute_difference'] = error if np.isfinite(error) else None
        except (ValueError, TypeError, OverflowError):
            consistent = False
    if not consistent:
        out['reasons'].append('OBJECTIVE_MISSING_OR_INCONSISTENT')
    out['accepted'] = not out['reasons']
    return out


def interpret(exitflag, accepted, *, in_budget, options_match=True):
    if not in_budget:
        return 'LATE_OR_TIMEOUT_UNRESOLVED'
    if not options_match:
        return 'OPTIONS_DRIFT_STOP'
    if exitflag == -2:
        return 'LP_NUMERICAL_INFEASIBILITY_STATUS_UNRESOLVED'
    if exitflag == -3:
        return 'LP_UNBOUNDED_STATUS_UNRESOLVED'
    if accepted and exitflag == 1:
        return 'LP_OPTIMUM_SOLVER_REPORTED_ONLY'
    if accepted:
        return 'LP_PRIMAL_ADMITTED_OPTIMALITY_UNRESOLVED'
    return 'LP_NO_ADMITTED_VECTOR_UNRESOLVED'
