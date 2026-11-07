"""Move exact opposite saved inequality pairs to Aeq, without changing the domain.

No tolerance, solver, model builder or thermal evaluator is used. Binary64
numbers are treated as their exact values. Positive-width affine intervals,
conditional big-M rows and empty rows are retained as inequalities.
"""
from collections import defaultdict
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import time

import numpy as np
from scipy import sparse


KEYS = ('c', 'A', 'b', 'Aeq', 'beq', 'lb', 'ub', 'intcon', 'x0')
UNCHANGED = ('c', 'lb', 'ub', 'intcon', 'x0')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _array_same(left, right):
    left, right = np.asarray(left), np.asarray(right)
    return left.shape == right.shape and left.dtype == right.dtype and left.tobytes() == right.tobytes()


def _matrix_same(left, right):
    left, right = left.tocsr(), right.tocsr()
    return (left.shape == right.shape and left.dtype == right.dtype
            and _array_same(left.data, right.data)
            and _array_same(left.indices, right.indices)
            and _array_same(left.indptr, right.indptr))


def _digest(payload):
    result = {}
    for key in KEYS:
        value = payload[key]
        h = hashlib.sha256()
        if sparse.issparse(value):
            h.update((str(value.shape) + str(value.dtype) + value.format).encode('ascii'))
            for array in (value.data, value.indices, value.indptr):
                h.update((str(array.shape) + str(array.dtype)).encode('ascii'))
                h.update(array.tobytes())
        else:
            value = np.asarray(value)
            h.update((str(value.shape) + str(value.dtype)).encode('ascii'))
            h.update(value.tobytes())
        result[key] = h.hexdigest()
    return result


def _validate(payload):
    _require(set(payload) == set(KEYS), 'Unexpected payload fields')
    n = np.asarray(payload['c']).size
    _require(n > 0, 'Empty variable set')
    for key, rhs in (('A', 'b'), ('Aeq', 'beq')):
        value = payload[key]
        _require(sparse.issparse(value) and value.format in ('csr', 'csc'), 'Canonical CSR/CSC required')
        _require(value.has_canonical_format and value.dtype == np.float64, 'Canonical binary64 matrix required')
        _require(value.shape[1] == n and np.isfinite(value.data).all(), 'Invalid matrix shape or values')
        _require(np.asarray(payload[rhs]).dtype == np.float64 and np.asarray(payload[rhs]).ndim == 1,
                 'One-dimensional binary64 right-hand side required')
        _require(len(payload[rhs]) == value.shape[0] and np.isfinite(payload[rhs]).all(), 'Invalid right-hand side')
    for key in ('lb', 'ub', 'x0'):
        _require(np.asarray(payload[key]).size == n, 'Variable count changed: ' + key)


def _row(a, i):
    part = slice(a.indptr[i], a.indptr[i+1])
    indices, values = a.indices[part], a.data[part]
    nonzero = values != 0
    return indices[nonzero], values[nonzero]


def _exact_pair(a, b, i, j):
    ix, av = _row(a, i); jx, bv = _row(a, j)
    return (len(ix) > 0 and np.array_equal(ix, jx)
            and np.array_equal(av, -bv) and b[i] == -b[j])


def _ranges(indices):
    result = []
    for i in indices:
        if result and result[-1][1] == i:
            result[-1][1] += 1
        else:
            result.append([i, i+1])
    return result


def verify_equivalence(original, derived, certificate):
    """Reject any omitted/duplicated row or any change beyond proved equality pairs."""
    _validate(original); _validate(derived)
    a = original['A'].tocsr(); b = original['b']
    m, n = a.shape
    _require(certificate.get('proof_rule') == 'exact_opposite_nonempty_rows_and_exact_opposite_rhs', 'Unknown proof rule')
    _require(certificate['source_array_sha256'] == _digest(original), 'Source array identity mismatch')
    _require(certificate['derived_array_sha256'] == _digest(derived), 'Derived array identity mismatch')
    _require(all(_array_same(original[k], derived[k]) for k in UNCHANGED), 'Variable, objective or initial point drift')
    _require(derived['A'].shape[1] == n and derived['Aeq'].shape[1] == n, 'Variable dimension changed')
    _require(derived['A'].format == original['A'].format and derived['Aeq'].format == original['Aeq'].format,
             'Sparse storage format changed')
    kept = []
    for start, stop in certificate['retained_le_row_ranges']:
        _require(type(start) is int and type(stop) is int and 0 <= start < stop <= m, 'Invalid retained row range')
        kept.extend(range(start, stop))
    _require(kept == sorted(set(kept)), 'Retained rows must be unique and ordered')
    pairs = certificate['original_le_pair_to_new_eq']
    old_eq = original['Aeq'].shape[0]
    _require(certificate['original_Aeq_rows'] == old_eq, 'Original equality count changed')
    _require(derived['A'].shape[0] == len(kept) and derived['Aeq'].shape[0] == old_eq+len(pairs), 'Output row counts mismatch')
    covered = list(kept)
    for offset, triple in enumerate(pairs):
        _require(len(triple) == 3 and all(type(v) is int for v in triple), 'Invalid pair mapping')
        i, j, k = triple
        _require(0 <= i < j < m and k == old_eq+offset, 'Pair order or output equality index mismatch')
        _require(_exact_pair(a, b, i, j), 'Pair is not an exact nonempty equality: ' + str((i, j)))
        _require(_matrix_same(derived['Aeq'].getrow(k), a.getrow(i)), 'New equality coefficients changed')
        _require(_array_same(derived['beq'][k:k+1], b[i:i+1]), 'New equality RHS changed')
        covered.extend((i, j))
    _require(sorted(covered) == list(range(m)), 'Original inequality row omitted or consumed more than once')
    _require(_matrix_same(derived['A'], a[kept, :]), 'Retained inequality coefficients changed')
    _require(_array_same(derived['b'], b[kept]), 'Retained inequality RHS changed')
    _require(_matrix_same(derived['Aeq'][:old_eq, :], original['Aeq']), 'Original equality coefficients changed')
    _require(_array_same(derived['beq'][:old_eq], original['beq']), 'Original equality RHS changed')
    return {'all_pairs_exact_without_tolerance': True, 'all_original_rows_covered_once': True,
            'retained_inequalities_bitwise_preserved': True, 'original_equalities_bitwise_preserved': True,
            'new_equalities_are_original_upper_rows': True, 'all_variables_bounds_intcon_x0_objective_unchanged': True,
            'returned_vector_uses_original_coordinates': True}


def transform(original):
    """Return a new payload and deterministic row-by-row equivalence certificate."""
    _validate(original)
    source_hash = _digest(original)
    a = original['A'].tocsr(copy=True); b = original['b']
    available = defaultdict(list)
    pairs, used = [], set()
    empty_rows = 0
    for i in range(a.shape[0]):
        indices, values = _row(a, i)
        if not len(indices):
            empty_rows += 1
            continue
        indices = tuple(int(j) for j in indices)
        key = (indices, tuple(float(v) for v in values), float(b[i]))
        opposite = (indices, tuple(float(-v) for v in values), float(-b[i]))
        if available.get(opposite):
            j = available[opposite].pop()
            _require(_exact_pair(a, b, j, i), 'Internal exact pairing failure')
            pairs.append((j, i)); used.update((j, i))
        else:
            available[key].append(i)
    kept = [i for i in range(a.shape[0]) if i not in used]
    old_eq = original['Aeq'].shape[0]
    new_eq_rows = [i for i, _ in pairs]
    derived = {key: value.copy() for key, value in original.items()}
    derived['A'] = a[kept, :].asformat(original['A'].format)
    derived['b'] = b[kept].copy()
    derived['Aeq'] = sparse.vstack((original['Aeq'], a[new_eq_rows, :]), format=original['Aeq'].format)
    derived['beq'] = np.concatenate((original['beq'], b[new_eq_rows]))
    certificate = {
        'proof_rule': 'exact_opposite_nonempty_rows_and_exact_opposite_rhs',
        'mathematical_identity': '(a*x<=b and -a*x<=-b) iff a*x=b; all saved binary64 coefficients interpreted exactly.',
        'pair_selection': 'Ascending original rows; latest unmatched exact opposite row; each original row consumed at most once.',
        'source_array_sha256': source_hash, 'derived_array_sha256': _digest(derived),
        'original_Aeq_rows': old_eq,
        'original_le_pair_to_new_eq': [[i, j, old_eq+k] for k, (i, j) in enumerate(pairs)],
        'retained_le_row_ranges': _ranges(kept),
        'original_inequalities': a.shape[0], 'derived_inequalities': len(kept),
        'derived_equalities': derived['Aeq'].shape[0], 'exact_pairs_moved': len(pairs),
        'empty_rows_retained': empty_rows, 'variable_count': a.shape[1],
        'no_approximate_pairing': True, 'no_variable_or_option_removed': True,
        'solver_calls': 0, 'model_builds': 0, 'thermal_evaluations': 0,
        'status': 'ALGEBRAICALLY_EQUIVALENT_REPRESENTATION_CANDIDATE_NOT_SOLVER_VALIDATED',
    }
    certificate['checks'] = verify_equivalence(original, derived, certificate)
    _require(_digest(original) == source_hash, 'Original arrays were mutated')
    return derived, certificate


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('original_mat', type=Path)
    parser.add_argument('new_output_json', type=Path)
    args = parser.parse_args()
    _require(not args.new_output_json.exists(), 'Refuse to overwrite a result')
    started = time.monotonic()
    repo = Path(__file__).resolve().parents[3]
    core_path = repo/'research/chapter3_experiments/results/fixed_integer_native03/source_snapshot/core.py'
    spec = importlib.util.spec_from_file_location('frozen_array_loader', core_path)
    core = importlib.util.module_from_spec(spec); spec.loader.exec_module(core)
    original, receipt = core.load_original_mat(args.original_mat)
    _, certificate = transform(original)
    certificate.update(original_mat=receipt, elapsed_s=time.monotonic()-started,
                       script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    args.new_output_json.parent.mkdir(parents=True, exist_ok=True)
    with args.new_output_json.open('x', encoding='utf-8', newline='\n') as output:
        json.dump(certificate, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write('\n')
    print(json.dumps({key: certificate[key] for key in ('status', 'exact_pairs_moved', 'derived_inequalities',
                                                       'derived_equalities', 'elapsed_s')}, ensure_ascii=False))
