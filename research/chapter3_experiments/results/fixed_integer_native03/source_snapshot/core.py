"""Pure archived-payload checks for the K188 fixed-actual-intcon diagnostic.

This module never imports a model builder, optimizer, decoder or heat evaluator.
MATLAB's saved intcon is converted from one based exactly once at load time.
The only permitted transformation fixes those original coordinates to the
archived x0 values, which must already be exactly binary. No vector is repaired.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from scipy import sparse
from scipy.io import loadmat


CONSTRAINT_TOLERANCE = 1e-9
INTEGER_TOLERANCE = 1e-6
OBJECTIVE_TOLERANCE = 1e-9
KEYS = ('c', 'A', 'b', 'Aeq', 'beq', 'lb', 'ub', 'intcon', 'x0')


def _sha_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _vector(value, name, length=None, *, allow_infinity=False):
    if np.iscomplexobj(value):
        raise ValueError(name + ' must be real')
    result = np.asarray(value, dtype=np.float64)
    if result.ndim > 2 or (result.ndim == 2 and result.size
                          and min(result.shape) != 1):
        raise ValueError(name + ' must be a vector')
    result = result.reshape(-1).copy()
    if length is not None and len(result) != length:
        raise ValueError(name + ' has the wrong length')
    if (np.isnan(result) if allow_infinity else ~np.isfinite(result)).any():
        raise ValueError(name + ' has nonfinite values')
    return result


def _matrix(value, name, columns):
    if np.iscomplexobj(value):
        raise ValueError(name + ' must be real')
    if sparse.issparse(value):
        result = value.copy()
        if result.format not in ('csr', 'csc'):
            raise ValueError(name + ' must use CSR or CSC storage')
    else:
        array = np.asarray(value)
        if array.ndim != 2:
            raise ValueError(name + ' must be two dimensional')
        result = sparse.csc_matrix(array, dtype=np.float64)
    if result.shape[1] != columns or not np.isfinite(result.data).all():
        raise ValueError(name + ' has invalid shape or coefficients')
    if not result.has_canonical_format:
        raise ValueError(name + ' must have canonical sparse entries')
    return result


def _integer_indices(value, columns, *, one_based):
    raw = _vector(value, 'intcon')
    low, high = (1, columns) if one_based else (0, columns - 1)
    if ((raw != np.floor(raw)).any() or (raw < low).any()
            or (raw > high).any() or len(np.unique(raw)) != len(raw)):
        raise ValueError('Invalid, duplicate or out-of-range intcon')
    return raw.astype(np.int64) - (1 if one_based else 0)


def _payload(value, *, intcon_one_based=False):
    missing = set(KEYS) - set(value)
    if missing:
        raise ValueError('Missing payload fields: ' + ','.join(sorted(missing)))
    objective = _vector(value['c'], 'c')
    columns = len(objective)
    if not columns:
        raise ValueError('Empty payload')
    a = _matrix(value['A'], 'A', columns)
    aeq = _matrix(value['Aeq'], 'Aeq', columns)
    result = dict(c=objective, A=a, Aeq=aeq,
        b=_vector(value['b'], 'b', a.shape[0]),
        beq=_vector(value['beq'], 'beq', aeq.shape[0]),
        lb=_vector(value['lb'], 'lb', columns, allow_infinity=True),
        ub=_vector(value['ub'], 'ub', columns, allow_infinity=True),
        x0=_vector(value['x0'], 'x0', columns),
        intcon=_integer_indices(value['intcon'], columns,
                                one_based=intcon_one_based))
    if (result['lb'] > result['ub']).any():
        raise ValueError('Inconsistent bounds')
    indices = result['intcon']
    if not len(indices):
        raise ValueError('This diagnostic requires actual integer coordinates')
    initial = result['x0'][indices]
    if not np.all((initial == 0) | (initial == 1)):
        raise ValueError('Original x0 integer coordinates must be exactly 0 or 1')
    if ((initial < result['lb'][indices]).any()
            or (initial > result['ub'][indices]).any()):
        raise ValueError('Original x0 integer values are outside original bounds')
    return result


def load_original_mat(path):
    """Return (payload, receipt); payload intcon is strictly Python zero based.

    Only the saved numerical arrays are read. The original MAT is hashed before
    and after reading; a concurrent modification rejects this load.
    """
    path = Path(path)
    before = _sha_file(path)
    raw = loadmat(path, variable_names=list(KEYS), struct_as_record=False)
    original = _payload(raw, intcon_one_based=True)
    after = _sha_file(path)
    if before != after:
        raise ValueError('Original MAT changed during read')
    return original, dict(path=str(path.resolve()), sha256=before,
        source_unchanged=True, columns=len(original['c']),
        inequality_rows=original['A'].shape[0],
        equality_rows=original['Aeq'].shape[0],
        integer_columns=len(original['intcon']),
        original_intcon_convention='MATLAB_one_based',
        returned_intcon_convention='Python_zero_based',
        conversion_count=1, new_model_built=False,
        rounding_or_repair_performed=False)


def _same_array(left, right):
    left, right = np.asarray(left), np.asarray(right)
    return (left.shape == right.shape and left.dtype == right.dtype
            and left.tobytes() == right.tobytes())


def _same_matrix(left, right):
    return (sparse.issparse(left) and sparse.issparse(right)
        and left.format == right.format and left.shape == right.shape
        and _same_array(left.data, right.data)
        and _same_array(left.indices, right.indices)
        and _same_array(left.indptr, right.indptr))


def assert_only_fixed_integer_bounds_changed(original, fixed):
    """Reject any payload drift except lb/ub fixed at the actual intcon.

    The comparison is bitwise for every original coefficient, sparse storage,
    initial-vector value and unaffected bound. Index lists use zero bases.
    """
    if set(original) != set(KEYS) or set(fixed) != set(KEYS):
        raise ValueError('Unexpected payload field inventory')
    normalized = _payload(original)
    indices = normalized['intcon']
    for key in ('c', 'b', 'beq', 'intcon', 'x0'):
        if not _same_array(original[key], fixed[key]):
            raise ValueError('Disallowed payload change: ' + key)
    for key in ('A', 'Aeq'):
        if not _same_matrix(original[key], fixed[key]):
            raise ValueError('Disallowed payload change: ' + key)
    expected_low, expected_high = original['lb'].copy(), original['ub'].copy()
    expected_low[indices] = original['x0'][indices]
    expected_high[indices] = original['x0'][indices]
    for key, expected in (('lb', expected_low), ('ub', expected_high)):
        if not _same_array(expected, fixed[key]):
            raise ValueError('Disallowed fixed-bound change: ' + key)
    _payload(fixed)
    return dict(passed=True, only_actual_intcon_bounds_fixed=True,
        fixed_columns=len(indices), original_columns=len(normalized['c']),
        coefficient_objective_x0_and_other_bounds_identical=True,
        index_convention='Python_zero_based',
        rounding_or_repair_performed=False)


def fix_actual_intcon(original):
    """Return independent (fixed_payload, receipt), changing no objective/row."""
    # Canonicalization validates the caller but is not a source of new rows.
    normalized = _payload(original)
    for key in ('c', 'b', 'beq', 'lb', 'ub', 'intcon', 'x0'):
        if not _same_array(normalized[key], original[key]):
            raise ValueError('Original payload must be the normalized loaded form')
    fixed = {key: value.copy() for key, value in original.items()}
    indices = normalized['intcon']
    fixed['lb'][indices] = original['x0'][indices]
    fixed['ub'][indices] = original['x0'][indices]
    return fixed, assert_only_fixed_integer_bounds_changed(original, fixed)


def _max_positive(values):
    return float(max(0., np.max(values, initial=0.)))


def _residuals(payload, vector):
    inequality = np.asarray(payload['A'] @ vector).reshape(-1) - payload['b']
    equality = np.asarray(payload['Aeq'] @ vector).reshape(-1) - payload['beq']
    objective = float(payload['c'] @ vector)
    finite = (np.isfinite(inequality).all() and np.isfinite(equality).all()
              and np.isfinite(objective))
    integer = payload['intcon']
    # Nearest integers are used to MEASURE distance only; vector is untouched.
    distance = np.abs(vector[integer] - np.rint(vector[integer]))
    report = dict(finite_residuals_and_objective=bool(finite),
        inequality_violation=_max_positive(inequality),
        equality_violation=float(np.max(np.abs(equality), initial=0.)),
        lower_bound_violation=_max_positive(payload['lb'] - vector),
        upper_bound_violation=_max_positive(vector - payload['ub']),
        integer_violation=float(np.max(distance, initial=0.)),
        objective=objective if np.isfinite(objective) else None,
        inequality_rows_above_tolerance_0based=[int(i) for i in
            np.flatnonzero(inequality > CONSTRAINT_TOLERANCE)[:16]],
        equality_rows_above_tolerance_0based=[int(i) for i in
            np.flatnonzero(np.abs(equality) > CONSTRAINT_TOLERANCE)[:16]])
    report['accepted'] = bool(finite and all(report[key] <= CONSTRAINT_TOLERANCE
        for key in ('inequality_violation', 'equality_violation',
                    'lower_bound_violation', 'upper_bound_violation'))
        and report['integer_violation'] <= INTEGER_TOLERANCE)
    return report


def verify_vector(vector, original, fixed, objective=None, *, require_objective=True):
    """Check a returned full vector in both original and fixed coordinates.

    No integer rounding, clipping, repair, decoding, heat calculation or new
    SAFE/U is performed. A small nonzero integer deviation is only measured
    against the original tolerances; fixed bounds are also independently tested.
    """
    assert_only_fixed_integer_bounds_changed(original, fixed)
    report = dict(accepted=False, reasons=[], original=None, fixed=None,
        constraint_tolerance=CONSTRAINT_TOLERANCE,
        integer_tolerance=INTEGER_TOLERANCE,
        objective_tolerance_rule='1e-9 * max(1, abs(original c dot x))',
        rounding_or_repair_performed=False, full_vector_required=True,
        physical_safety_claim=False, independent_certificate=False,
        new_safe_or_upper_bound=False)
    try:
        proposed = _vector(vector, 'returned vector', len(original['c']))
    except (ValueError, TypeError, OverflowError) as error:
        report['reasons'].append('INVALID_VECTOR: ' + str(error))
        return report
    report['vector_sha256'] = hashlib.sha256(proposed.tobytes()).hexdigest()
    report['vector_equals_original_x0_bitwise'] = _same_array(proposed, original['x0'])
    report['original'] = _residuals(original, proposed)
    report['fixed'] = _residuals(fixed, proposed)
    for key in ('original', 'fixed'):
        if not report[key]['accepted']:
            report['reasons'].append(key.upper() + '_NUMERICAL_REJECTION')
    calculated = report['original']['objective']
    objective_record = dict(required=bool(require_objective), provided=objective is not None,
        accepted=not require_objective, original_c_dot_x=calculated,
        fval=None, absolute_difference=None, tolerance=None)
    if objective is not None:
        try:
            supplied = _vector(objective, 'fval', 1)
            if calculated is None:
                raise ValueError('Nonfinite original objective')
            tolerance = OBJECTIVE_TOLERANCE * max(1., abs(calculated))
            difference = abs(float(supplied[0]) - calculated)
            objective_record.update(fval=float(supplied[0]),
                absolute_difference=difference, tolerance=tolerance,
                accepted=bool(difference <= tolerance))
        except (ValueError, TypeError, OverflowError) as error:
            objective_record.update(accepted=False, error=str(error))
    if not objective_record['accepted']:
        report['reasons'].append('OBJECTIVE_MISSING_OR_INCONSISTENT')
    report['objective_check'] = objective_record
    report['accepted'] = not report['reasons']
    return report
