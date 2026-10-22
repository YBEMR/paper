"""K165: inspect archived numbers only; never build, solve, repair or integrate.

Run with the existing project Python.  The output is exclusively created: an
existing report is not replaced.  Fraction checks refer to the exact binary64
numbers stored in these MAT files, not unrounded physical/model coefficients.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import math
from pathlib import Path
import subprocess
import sys
from fractions import Fraction
from unittest.mock import patch

import numpy as np
import scipy
from scipy import sparse
from scipy.io import loadmat


OUT = Path(__file__).resolve().parent
REPO = OUT.parents[4]
SCIENCE = REPO / 'research/chapter3_experiments'
ARCHIVE = SCIENCE / 'results/deadline_resume01/calls/beta_1.0__R2/whole_milp'
MAT = ARCHIVE / 'matlab'
REPORT = OUT / 'payload_audit_final.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stats(values):
    a = np.asarray(values).reshape(-1)
    nz = np.abs(a[a != 0])
    return {'count': int(a.size), 'nan_count': int(np.isnan(a).sum()),
            'inf_count': int(np.isinf(a).sum()),
            'min': float(a.min()) if a.size else None,
            'max': float(a.max()) if a.size else None,
            'nonzero_count': int(nz.size),
            'min_abs_nonzero': float(nz.min()) if nz.size else None,
            'max_abs': float(np.abs(a).max()) if a.size else None}


def q(value):
    return Fraction.from_float(float(value))


def fraction_json(value):
    return {'numerator': str(value.numerator),
            'denominator': str(value.denominator), 'float': float(value)}


def main():
    if REPORT.exists():
        raise FileExistsError('Refusing to overwrite existing audit report')
    originals = [MAT / name for name in (
        'request_000001.mat', 'request_000001.native.mat',
        'request_000001.initial.json', 'request_000001.input.json',
        'request_000001.python.json')]
    originals += [SCIENCE / 'matlab_bridge.py', SCIENCE / 'solve_model.m']
    before = {str(p.relative_to(REPO)).replace('\\', '/'): sha(p)
              for p in originals}
    counters = {'process_launch': 0, 'scipy_milp': 0, 'scipy_linprog': 0,
                'matlab_session': 0, 'payload_prepare': 0}

    def deny(name):
        def blocked(*args, **kwargs):
            counters[name] += 1
            raise RuntimeError('Forbidden in read-only audit: ' + name)
        return blocked

    sys.path.insert(0, str(SCIENCE))
    bridge = importlib.import_module('matlab_bridge')
    # Only its pure arithmetic admission helper is called.  Native process,
    # optimization, payload preparation and MATLAB session entry are blocked.
    with patch.object(subprocess, 'Popen', deny('process_launch')), \
         patch('scipy.optimize.milp', deny('scipy_milp')), \
         patch('scipy.optimize.linprog', deny('scipy_linprog')), \
         patch.object(bridge.MatlabSession, '__init__', deny('matlab_session')), \
         patch.object(bridge, '_prepare', deny('payload_prepare')):
        raw = loadmat(MAT / 'request_000001.mat')
        # Selectively load numbers: the saved opaque MATLAB options object is
        # unsupported by this SciPy reader and is not required for this audit.
        native = loadmat(MAT / 'request_000001.native.mat',
                         variable_names=['initialPoint', 'x', 'fval', 'exitflag',
                                         'output', 'c', 'A', 'b', 'Aeq', 'beq',
                                         'lb', 'ub', 'intcon'])
        payload = {k: np.asarray(raw[k]).reshape(-1)
                   for k in ('c', 'b', 'beq', 'lb', 'ub', 'intcon')}
        payload.update(A=raw['A'], Aeq=raw['Aeq'])
        x = np.asarray(raw['x0']).reshape(-1)
        native_x = np.asarray(native['initialPoint']).reshape(-1)
        _, actual_check = bridge._check_initial_point(payload, x)
        _, native_check = bridge._check_initial_point(payload, native_x)
        archived_check = json.loads((MAT / 'request_000001.initial.json')
                                   .read_text(encoding='utf-8-sig'))
        A, b, c = payload['A'], payload['b'], payload['c']
        csr = A.tocsr()
        n = len(x)
        dot = np.asarray(A @ x).reshape(-1)
        residual = dot - b
        k = np.diff(csr.indptr)
        absproducts = np.asarray(abs(A) @ abs(x)).reshape(-1)
        magnitude = absproducts + abs(b)
        u = 2.0 ** -53
        steps = 2 * k + 4
        gamma = steps * u / (1 - steps * u)
        # Standard gamma_n arithmetic-error margin, doubled conservatively.
        # The denominator also covers rounding in the nonnegative magnitude
        # sum. This audits arithmetic at this archived vector, not solver internals.
        error = np.nextafter(2 * gamma * magnitude / (1 - gamma), np.inf)
        upper = residual + error
        ranked = np.lexsort((np.arange(len(residual)), -residual))[:16]
        risky = np.lexsort((np.arange(len(upper)), -upper))[:16]
        selected = sorted(set(map(int, np.r_[ranked, risky])))
        exact_rows = []
        tolerance = q(1e-9)
        for row in selected:
            start, stop = csr.indptr[row:row + 2]
            indices = csr.indices[start:stop]
            coeff = csr.data[start:stop]
            terms = [q(a) * q(x[j]) for a, j in zip(coeff, indices)]
            exact = sum(terms, Fraction()) - q(b[row])
            active = [(int(j), float(a), float(x[j]), float(a * x[j]))
                      for j, a in zip(indices, coeff) if x[j] != 0]
            active.sort(key=lambda v: (-abs(v[3]), v[0]))
            exact_rows.append({
                'row_1based': row + 1, 'nnz': int(stop - start),
                'float_residual': float(residual[row]),
                'exact_binary64_residual': fraction_json(exact),
                'exact_residual_le_declared_tolerance': exact <= tolerance,
                'difference_exact_minus_float': float(exact - q(residual[row])),
                'row_l1_norm': math.fsum(map(abs, coeff)),
                'rhs': float(b[row]), 'sum_abs_products': float(absproducts[row]),
                'computed_arithmetic_margin': float(error[row]),
                'nonzero_x_column_count': len(active),
                'largest_active_terms': [
                    {'column_1based': j + 1, 'coefficient': a, 'x0': v, 'product': p}
                    for j, a, v, p in active[:8]],
                'semantic_row_category': 'not_archived; no model reconstructed'})
        # Directly inspect the archived opposite-row pairs around the largest
        # ordinary residual. No row generation or change of the point occurs.
        paired_rows = []
        for plus, minus, target in ((21694, 21695, 10672),
                                    (21696, 21697, 10673),
                                    (21698, 21699, 10674),
                                    (21700, 21701, 10675)):
            rows = []
            for row in (plus, minus):
                begin, end = csr.indptr[row:row + 2]
                rows.append({int(j): q(a) for j, a in
                             zip(csr.indices[begin:end], csr.data[begin:end])})
            first, second = rows
            if first.get(target) != 1 or second.get(target) != -1:
                raise AssertionError('Expected archived target signs differ')
            other_first = sum((a * q(x[j]) for j, a in first.items() if j != target), Fraction())
            other_second = sum((a * q(x[j]) for j, a in second.items() if j != target), Fraction())
            lower, upper_exact = other_second - q(b[minus]), q(b[plus]) - other_first
            combined = {j: first.get(j, Fraction()) + second.get(j, Fraction())
                        for j in set(first) | set(second)}
            combined = {j: a for j, a in combined.items() if a}
            paired_rows.append({
                'row_pair_1based': [plus + 1, minus + 1],
                'target_column_1based': target + 1,
                'other_columns_held_at': 'Unchanged archived x0, not a new candidate',
                'target_x0': float(x[target]),
                'lower_exact_binary64': fraction_json(lower),
                'upper_exact_binary64': fraction_json(upper_exact),
                'interval_width_exact_binary64': fraction_json(upper_exact - lower),
                'target_exact_minus_lower': fraction_json(q(x[target]) - lower),
                'upper_minus_target_exact': fraction_json(upper_exact - q(x[target])),
                'combined_nonzero_terms': [{'column_1based': j + 1,
                    'coefficient_exact': fraction_json(a), 'x0': float(x[j])}
                    for j, a in sorted(combined.items())],
                'interpretation': 'Near equality band in stored conditional rows; possible numerical sensitivity only, not a demonstrated cause'})
        canonical = A.copy()
        original_nnz = int(canonical.nnz)
        canonical.sum_duplicates()
        indices = payload['intcon']
        valid_index = np.isfinite(indices).all() and np.equal(indices, np.rint(indices)).all()
        valid_index = bool(valid_index and ((indices >= 1) & (indices <= n)).all())
        integer_idx = indices.astype(np.int64) - 1
        product_values = csr.data * x[csr.indices]
        report = {
            'protocol': 'K165-archived-payload-readonly-v1',
            'scope': 'Existing numeric arrays only; no model, solve, repair, LP, thermal integration or candidate creation',
            'environment': {'python': sys.version, 'platform': sys.platform,
                            'numpy': np.__version__, 'scipy': scipy.__version__,
                            'longdouble_mantissa_bits': int(np.finfo(np.longdouble).nmant)},
            'dimensions': {'variables': n, 'inequality_rows': A.shape[0],
                           'equality_rows': payload['Aeq'].shape[0],
                           'integer_columns': len(indices),
                           'all_vector_and_matrix_dimensions_match': bool(
                               A.shape[1] == n == len(c) == len(payload['lb']) == len(payload['ub'])
                               and len(b) == A.shape[0]
                               and payload['Aeq'].shape[1] == n
                               and len(payload['beq']) == payload['Aeq'].shape[0])},
            'numeric_fields': {name: stats(values) for name, values in
                               {**{key: payload[key] for key in ('c', 'b', 'beq', 'lb', 'ub', 'intcon')},
                                'x0': x, 'A_nonzeros': A.data,
                                'Aeq_nonzeros': payload['Aeq'].data,
                                'A_coefficient_times_x0': product_values}.items()},
            'sparse_storage': {'format': A.format, 'nnz': original_nnz,
                               'has_sorted_indices': bool(A.has_sorted_indices),
                               'has_canonical_format': bool(A.has_canonical_format),
                               'explicit_zero_count': int((A.data == 0).sum()),
                               'duplicates_removed_on_copy': original_nnz - int(canonical.nnz),
                               'maximum_row_nnz': int(k.max(initial=0))},
            'integer_indices': {'valid_one_based_integral_range': valid_index,
                                'unique_count': int(np.unique(indices).size),
                                'maximum_x0_distance_from_integer': float(np.abs(
                                    x[integer_idx] - np.rint(x[integer_idx])).max(initial=0))},
            'archived_python_admission': archived_check,
            'recomputed_actual_python_helper': actual_check,
            'admission_matches_archived': actual_check == archived_check,
            'native_initial_point': {'same_length': len(native_x) == n,
                                     'array_equal': bool(np.array_equal(x, native_x)),
                                     'bitwise_equal': bool(x.tobytes() == native_x.tobytes()),
                                     'maximum_absolute_difference': float(np.abs(x - native_x).max(initial=0)),
                                     'recomputed_against_archived_payload': native_check},
            'ordinary_residual': {'maximum_signed': float(residual.max()),
                                  'row_1based': int(np.argmax(residual)) + 1,
                                  'rows_above_constraint_tolerance': int((residual > 1e-9).sum()),
                                  'objective': float(c @ x)},
            'roundoff_audit_all_inequalities': {
                'scope': 'IEEE binary64 finite normal arithmetic audit at archived x0, not independent MILP proof',
                'unit_roundoff': u, 'operation_count_bound_per_row': '2*nnz+4',
                'formula': '2*gamma_n*(computed(sum|a*x|)+|b|)/(1-gamma_n), nextafter upward',
                'maximum_magnitude_sum': float(magnitude.max()),
                'maximum_arithmetic_margin': float(error.max()),
                'maximum_residual_plus_margin': float(upper.max()),
                'rows_whose_upper_margin_exceeds_1e_9': int((upper > 1e-9).sum()),
                'minimum_margin_to_1e_9_after_error': float((1e-9 - upper).min()),
                'all_products_normal_or_zero': bool(((product_values == 0) |
                    (np.abs(product_values) >= np.finfo(float).tiny)).all())},
            'fraction_checks': {'selection': '16 greatest signed residuals union 16 greatest residual-plus-margin; ties by row',
                                'selected_count': len(selected), 'rows': exact_rows,
                                'all_selected_rows_within_declared_tolerance': all(
                                    r['exact_residual_le_declared_tolerance'] for r in exact_rows)},
            'adjacent_opposite_row_pairs': paired_rows,
            'native_archive_limit': {
                'input_matrix_keys_found': [key for key in ('c', 'A', 'b', 'Aeq', 'beq', 'lb', 'ub', 'intcon') if key in native],
                'native_initial_point_found': 'initialPoint' in native,
                'native_exitflag': int(np.asarray(native['exitflag']).reshape(-1)[0]),
                'native_returned_x_length': int(np.asarray(native['x']).size),
                'matrix_identity_not_independently_observable': True,
                'source_path': 'research/chapter3_experiments/solve_model.m:' + str(next(
                    i for i, line in enumerate((SCIENCE / 'solve_model.m').read_text(encoding='utf-8-sig').splitlines(), 1)
                    if '= intlinprog(p.c' in line)),
                'source_observation': 'intlinprog is passed p.A/p.b/p.Aeq/p.beq/p.lb/p.ub directly; native archive saves initialPoint but not input matrices',
                'scipy_selective_read_reason': 'Saved MATLAB opts contains unsupported opaque objects; numeric selected fields are readable'},
            'interpretation': [
                'No malformed dimensions, NaN/Inf, invalid integer indices or sparse duplicate entries found in the archived payload.',
                'Archived x0 and native initialPoint agree exactly; actual Python numerical admission reproduces the saved record.',
                'All-row arithmetic margin plus exact selected-row checks give no evidence that floating summation hid a >1e-9 violation of this archived system.',
                'Coefficient ranges are descriptive scales, not a condition number or proof of ill-conditioning.',
                'This does not certify the solver internal transformed system, exact original physical coefficients, thermal safety, optimality or infeasibility; status conflict remains unresolved.'],
        }
    after = {str(p.relative_to(REPO)).replace('\\', '/'): sha(p) for p in originals}
    report['original_inputs_before_sha256'] = before
    report['original_inputs_after_sha256'] = after
    report['original_inputs_unchanged'] = before == after
    report['guard'] = {'blocked_entry_attempt_counts': counters,
                       'all_blocked_entry_attempts_zero': all(v == 0 for v in counters.values()),
                       'new_research_calls': 0,
                       'scientific_modules_used': ['matlab_bridge._check_initial_point (pure arithmetic only)'],
                       'model_builder_thermal_or_candidate_functions_imported_or_called': False}
    report['audit_script_sha256'] = sha(Path(__file__))
    with REPORT.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps({'report': str(REPORT),
                      'original_inputs_unchanged': report['original_inputs_unchanged'],
                      'guard_zero': report['guard']['all_blocked_entry_attempts_zero'],
                      'admission_matches': report['admission_matches_archived'],
                      'exact_rows': len(selected),
                      'max_residual_plus_roundoff_margin': float(upper.max())}, ensure_ascii=False))


if __name__ == '__main__':
    main()
