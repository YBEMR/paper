"""K133 diagnostic payload adapter; no optimizer, model builder or physics.

Keep every original coordinate.  Only labelled, single-joint physical rows
replace +M*w by -M*v, with v+w=1.  A nonrepresentable binary64 b-M rejects
the entire adapter.  Numerical admission always includes the original rows.
All integer indices accepted and returned here are Python zero based.
"""
from __future__ import annotations

from fractions import Fraction
import math

import numpy as np
from scipy import sparse


CONSTRAINT_TOLERANCE = 1e-9
INTEGER_TOLERANCE = 1e-6
PHYSICAL_PREFIXES = ('thermal_propagation/', 'complete_energy/')


def _vector(value, name, length=None, allow_infinity=False):
    if np.iscomplexobj(value):
        raise ValueError(f'{name} must be real')
    result = np.asarray(value, dtype=np.float64)
    if result.ndim > 2 or (result.ndim == 2 and min(result.shape) != 1
                           and result.size != 0):
        raise ValueError(f'{name} must be a vector')
    result = result.reshape(-1).copy()
    if length is not None and len(result) != length:
        raise ValueError(f'{name} length must equal {length}')
    bad = np.isnan(result) if allow_infinity else ~np.isfinite(result)
    if bad.any():
        raise ValueError(f'{name} contains unsupported nonfinite values')
    return result


def _matrix(value, name, n):
    if np.iscomplexobj(value):
        raise ValueError(f'{name} must be real')
    result = sparse.csr_matrix(value, dtype=np.float64, copy=True)
    if result.shape[1] != n or not np.isfinite(result.data).all():
        raise ValueError(f'{name} has invalid dimensions or coefficients')
    # Duplicate entries would require an additional floating addition. Refuse
    # them rather than treating its rounded result as the archived row.
    if not result.has_canonical_format:
        raise ValueError(f'{name} must have canonical sparse entries')
    result.eliminate_zeros()
    return result


def _canonical(payload):
    c = _vector(payload['c'], 'c')
    n = len(c)
    if not n:
        raise ValueError('empty original payload')
    a = _matrix(payload['A'], 'A', n)
    aeq = _matrix(payload['Aeq'], 'Aeq', n)
    b = _vector(payload['b'], 'b', a.shape[0])
    beq = _vector(payload['beq'], 'beq', aeq.shape[0])
    lb = _vector(payload['lb'], 'lb', n, True)
    ub = _vector(payload['ub'], 'ub', n, True)
    if np.any(lb > ub):
        raise ValueError('inconsistent variable bounds')
    indices = _vector(payload['intcon'], 'intcon')
    if ((indices != np.floor(indices)).any() or (indices < 0).any()
            or (indices >= n).any() or len(np.unique(indices)) != len(indices)):
        raise ValueError('intcon must contain unique zero-based integer indices')
    return {'c': c, 'A': a, 'b': b, 'Aeq': aeq, 'beq': beq,
            'lb': lb, 'ub': ub, 'intcon': indices.astype(np.int64)}


def _exact_float(value, description):
    try:
        rounded = float(value)
    except OverflowError as exc:
        raise ValueError(f'{description} is not exactly representable as binary64') from exc
    if not math.isfinite(rounded) or Fraction.from_float(rounded) != value:
        raise ValueError(f'{description} is not exactly representable as binary64')
    return rounded


def build_augmented_payload(original: dict, labels: dict) -> tuple[dict, dict]:
    """Return independent arrays and a JSON-serializable column/row mapping.

    Labels must already have been matched to the archived arrays by the
    caller. Length/name checks here do not replace that provenance check.
    Any unsupported physical row rejects the whole expression, without a
    fallback, rounding, scaling, dropped row, or mutation of ``original``.
    """
    old = _canonical(original)
    a, n = old['A'], len(old['c'])
    names, tags = labels['names'], labels['row_tags']
    if (len(names) != n or len(tags) != a.shape[0]
            or not all(isinstance(v, str) for v in [*names, *tags])
            or len(set(names)) != n):
        raise ValueError('labels have invalid lengths, types or duplicate variable names')
    joint = np.array([name.startswith('w:') for name in names], dtype=bool)
    physical = np.array([tag.startswith(PHYSICAL_PREFIXES) for tag in tags], dtype=bool)
    rows = np.flatnonzero(physical)
    if not len(rows):
        raise ValueError('no labelled physical rows to augment')
    rhs = old['b'].copy()
    used, row_gates, row_coefficients = set(), [], []
    for i in rows:
        start, end = a.indptr[i:i + 2]
        columns = a.indices[start:end]
        positions = np.flatnonzero(joint[columns])
        if len(positions) != 1:
            raise ValueError(f'physical row {i} must have exactly one joint gate')
        position = start + int(positions[0])
        gate, coefficient = int(a.indices[position]), float(a.data[position])
        if coefficient <= 0:
            raise ValueError(f'physical row {i} must have a positive M gate coefficient')
        if old['lb'][gate] != 0 or old['ub'][gate] != 1:
            raise ValueError(f'joint gate {gate} must have original bounds [0,1]')
        if gate in old['intcon']:
            raise ValueError(f'joint gate {gate} must remain continuous')
        exact = (Fraction.from_float(float(old['b'][i]))
                 - Fraction.from_float(coefficient))
        rhs[i] = _exact_float(exact, f'physical row {i} b-M')
        used.add(gate)
        row_gates.append(gate)
        row_coefficients.append(coefficient)
    gates = sorted(used)
    count = len(gates)
    new_columns = list(range(n, n + count))
    lookup = dict(zip(gates, new_columns))
    coo = a.tocoo()
    columns, data = coo.col.copy(), coo.data.copy()
    selected = physical[coo.row] & joint[coo.col]
    columns[selected] = [lookup[int(j)] for j in columns[selected]]
    data[selected] *= -1
    transformed = sparse.coo_matrix((data, (coo.row, columns)),
                                    shape=(a.shape[0], n + count)).tocsr()
    link_index = np.arange(count)
    links = sparse.coo_matrix((np.ones(2 * count),
                               (np.r_[link_index, link_index],
                                np.r_[gates, new_columns])),
                              shape=(count, n + count)).tocsr()
    original_eq_rows = old['Aeq'].shape[0]
    aeq_prefix = sparse.hstack([old['Aeq'],
                               sparse.csr_matrix((original_eq_rows, count))],
                              format='csr')
    augmented = {
        'c': np.r_[old['c'], np.zeros(count)],
        'A': transformed, 'b': rhs,
        'Aeq': sparse.vstack([aeq_prefix, links], format='csr'),
        'beq': np.r_[old['beq'], np.ones(count)],
        'lb': np.r_[old['lb'], np.zeros(count)],
        'ub': np.r_[old['ub'], np.ones(count)],
        'intcon': old['intcon'].copy(),
    }
    meta = {
        'scheme': 'K132_single_joint_physical_alias_v_equals_1_minus_w',
        'intcon_convention': 'Python_zero_based_unchanged',
        'original_n': n, 'augmented_n': n + count,
        'original_inequality_rows': int(a.shape[0]),
        'original_eq_rows': int(original_eq_rows),
        'new_variables': count, 'new_link_equalities': count,
        'gate_columns': gates, 'new_columns': new_columns,
        'physical_rows': rows.tolist(),
        'physical_gate_columns': row_gates,
        'physical_gate_coefficients': row_coefficients,
        'physical_rows_rewritten': int(len(rows)),
        'nonphysical_rows_unchanged': int(a.shape[0] - len(rows)),
        'exact_rhs_rows': int(len(rows)),
        'maximum_physical_gate_coefficient': max(row_coefficients),
        'original_Aeq_preserved_as_prefix': True,
        'original_prefix_repaired': False,
        'thermal_safe_claim': False, 'independent_certificate': False,
    }
    return augmented, meta


def append_complements(original_x, meta: dict) -> np.ndarray:
    """Keep the original prefix and append exactly representable 1-w values."""
    x = _vector(original_x, 'original_x', meta['original_n'])
    complements = [_exact_float(Fraction(1) - Fraction.from_float(float(x[j])),
                                f'complement of gate {j}')
                   for j in meta['gate_columns']]
    return np.r_[x, complements]


def _residual_report(payload, x, constraint_tolerance, integer_tolerance):
    with np.errstate(over='ignore', invalid='ignore'):
        inequality = np.asarray(payload['A'] @ x).reshape(-1) - payload['b']
        equality = np.asarray(payload['Aeq'] @ x).reshape(-1) - payload['beq']
        lower = payload['lb'] - x
        upper = x - payload['ub']
        integer = np.abs(x[payload['intcon']] - np.rint(x[payload['intcon']]))
        objective = float(payload['c'] @ x)
    finite = (np.isfinite(inequality).all() and np.isfinite(equality).all()
              and math.isfinite(objective) and not np.isnan(lower).any()
              and not np.isnan(upper).any())
    report = {
        'finite_residuals_and_objective': bool(finite),
        'inequality_violation': float(max(0., np.max(inequality, initial=0.))),
        'equality_violation': float(np.max(np.abs(equality), initial=0.)),
        'lower_bound_violation': float(max(0., np.max(lower, initial=0.))),
        'upper_bound_violation': float(max(0., np.max(upper, initial=0.))),
        'integer_violation': float(np.max(integer, initial=0.)),
        'objective': objective,
    }
    report['accepted'] = bool(finite and all(report[k] <= constraint_tolerance for k in
        ('inequality_violation', 'equality_violation',
         'lower_bound_violation', 'upper_bound_violation'))
        and report['integer_violation'] <= integer_tolerance)
    for key, value in list(report.items()):
        if isinstance(value, float) and not math.isfinite(value):
            report[key] = None
    return report


def validate_projected_vector(vector, original: dict, augmented: dict, meta: dict,
                              *, constraint_tolerance=CONSTRAINT_TOLERANCE,
                              integer_tolerance=INTEGER_TOLERANCE):
    """Gate every final/callback vector before returning its original prefix.

    A rejection returns ``(None, report)``. It is a numerical-path failure,
    not a decision about an independently established physical SAFE receipt.
    This routine never rounds integer coordinates or repairs a link.
    """
    if (constraint_tolerance != CONSTRAINT_TOLERANCE
            or integer_tolerance != INTEGER_TOLERANCE):
        raise ValueError('K133 requires unchanged 1e-9/1e-6 tolerances')
    report = {'accepted': False, 'reasons': [],
              'constraint_tolerance': constraint_tolerance,
              'integer_tolerance': integer_tolerance,
              'thermal_safe_claim': False, 'independent_certificate': False,
              'rounding_or_repair_performed': False}
    try:
        x = _vector(vector, 'augmented vector', meta['augmented_n'])
    except (TypeError, ValueError) as exc:
        report['reasons'].append(str(exc))
        return None, report
    old, new = _canonical(original), _canonical(augmented)
    n = meta['original_n']
    if len(old['c']) != n or len(new['c']) != meta['augmented_n']:
        raise ValueError('payload dimensions disagree with augmentation metadata')
    original_report = _residual_report(old, x[:n], constraint_tolerance, integer_tolerance)
    augmented_report = _residual_report(new, x, constraint_tolerance, integer_tolerance)
    links = x[np.asarray(meta['gate_columns'], dtype=int)] + x[n:] - 1
    link_max = float(np.max(np.abs(links), initial=0.))
    report.update(original=original_report, augmented=augmented_report,
                  link_max_abs_residual=link_max,
                  link_accepted=bool(math.isfinite(link_max)
                                     and link_max <= constraint_tolerance),
                  length=len(x))
    for key, value in [('original', original_report['accepted']),
                       ('augmented', augmented_report['accepted']),
                       ('link', report['link_accepted'])]:
        if not value:
            report['reasons'].append(f'{key} numerical admission failed')
    if (original_report['objective'] is not None
            and augmented_report['objective'] is not None):
        difference = abs(original_report['objective'] - augmented_report['objective'])
        report['objective_difference'] = difference
        report['objective_consistent'] = bool(difference <= constraint_tolerance * max(
            1., abs(original_report['objective'])))
    else:
        report['objective_difference'] = None
        report['objective_consistent'] = False
    if not report['objective_consistent']:
        report['reasons'].append('original/augmented objective mismatch')
    report['accepted'] = not report['reasons']
    return (x[:n].copy() if report['accepted'] else None), report
