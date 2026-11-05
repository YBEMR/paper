"""Certified, solver-free AUTO_LOW OR projection and exact inequality cleanup.

All integer indices here are ZERO BASED.  This module never performs tolerance
admission or thermal evaluation.  A lifted candidate MUST pass the unchanged
full original numerical/logic/SAFE checks before acceptance by the caller.
"""
from collections.abc import Mapping
import hashlib
import json

import numpy as np
from scipy import sparse


POLICY = 'auto_low_immediate_v1'
SCHEMA = 'certified_auto_low_or_and_exact_rows_v1'
BASE_KEYS = frozenset(('c', 'A', 'b', 'Aeq', 'beq', 'lb', 'ub', 'intcon'))
CERT_KEYS = frozenset(('schema', 'policy', 'source_identity', 'derived_identity',
    'original_counts', 'kept_columns', 'removed_or_blocks', 'kept_inequality_rows',
    'removed_or_rows', 'duplicate_rows', 'true_empty_rows', 'statistics',
    'certificate_sha256'))


class CertifiedProjectionError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise CertifiedProjectionError(message)


def _tick(check):
    if check is not None:
        check()


def _vector(value, name, length=None, integer=False):
    _require(isinstance(value, np.ndarray), name + ': ndarray required')
    _require(value.ndim == 1, name + ': one dimensional required')
    _require(value.dtype == (np.dtype('int64') if integer else np.dtype('float64')),
             name + ': exact int64/binary64 dtype required')
    _require(length is None or len(value) == length, name + ': length mismatch')
    _require(np.isfinite(value).all(), name + ': finite values required')
    return value


def _validate(payload, check=None):
    _tick(check)
    _require(isinstance(payload, Mapping), 'Payload must be a mapping')
    _require(set(payload) in (BASE_KEYS, BASE_KEYS | {'x0'}), 'Unexpected payload fields')
    c = _vector(payload['c'], 'c')
    n = len(c)
    for key, rhs in (('A', 'b'), ('Aeq', 'beq')):
        value = payload[key]
        _require(sparse.isspmatrix_csc(value), key + ': CSC matrix required')
        _require(value.dtype == np.dtype('float64'), key + ': binary64 required')
        _require(value.shape[1] == n, key + ': column count mismatch')
        # Do not rely on SciPy's cached canonical/sorted flags: callers can
        # mutate sparse index buffers without invalidating those flags.
        ip, ix, values = value.indptr, value.indices, value.data
        _require(ip.ndim == ix.ndim == values.ndim == 1 and
                 ip.dtype.kind == ix.dtype.kind == 'i', key + ': invalid sparse arrays')
        _require(len(ip) == n + 1 and len(ip) > 0 and ip[0] == 0 and
                 ip[-1] == len(ix) == len(values) and np.all(ip[1:] >= ip[:-1]),
                 key + ': invalid sparse column pointers')
        _require(np.all((ix >= 0) & (ix < value.shape[0])), key + ': sparse row index out of range')
        if len(ix) > 1:
            # Adjacent row indices must increase except at column boundaries.
            # Empty columns may repeat a boundary; assigning False is idempotent.
            nonincreasing = ix[1:] <= ix[:-1]
            boundaries = ip[1:-1]
            boundaries = boundaries[(boundaries > 0) & (boundaries < len(ix))]
            nonincreasing[boundaries - 1] = False
            _require(not np.any(nonincreasing), key + ': unsorted/duplicate sparse row index')
        _tick(check)
        _require(value.has_canonical_format and value.has_sorted_indices,
                 key + ': canonical sorted storage required')
        _require(np.isfinite(value.data).all(), key + ': finite coefficients required')
        _require(not np.any(value.data == 0), key + ': explicit zeros unsupported')
        _vector(payload[rhs], rhs, value.shape[0])
        _tick(check)
    lb = _vector(payload['lb'], 'lb', n)
    ub = _vector(payload['ub'], 'ub', n)
    _require(np.all(lb <= ub), 'Inconsistent bounds')
    integers = _vector(payload['intcon'], 'intcon', integer=True)
    _require(np.all((integers >= 0) & (integers < n)), 'Integer index out of range')
    _require(len(set(map(int, integers))) == len(integers), 'Duplicate integer index')
    if 'x0' in payload:
        _vector(payload['x0'], 'x0', n)
    return n


def _array_digest(a):
    h = hashlib.sha256()
    h.update((str(a.shape) + '|' + a.dtype.str + '|').encode('ascii'))
    h.update(a.tobytes(order='C'))
    return h.hexdigest()


def identity(payload, *, check=None):
    """Exact stored-array identity, including shape/dtype/index storage."""
    _validate(payload, check)
    result = {}
    for key in sorted(payload):
        value = payload[key]
        if sparse.issparse(value):
            h = hashlib.sha256((str(value.shape) + '|' + value.format + '|' + value.dtype.str).encode('ascii'))
            for array in (value.data, value.indices, value.indptr):
                h.update(_array_digest(array).encode('ascii'))
            result[key] = h.hexdigest()
        else:
            result[key] = _array_digest(value)
        _tick(check)
    return result


def _row(a, row):
    part = slice(a.indptr[row], a.indptr[row + 1])
    return a.indices[part], a.data[part]


def _row_key(a, b, row):
    indices, values = _row(a, row)
    return (indices.astype('<i8', copy=False).tobytes(),
            values.tobytes(), b[row:row+1].tobytes())


def _block(payload, rows, j, integer_set):
    """Return a full column-occurrence proof, or None; no tolerance is used."""
    c, lb, ub = payload['c'], payload['lb'], payload['ub']
    a, e, b = payload['A'], payload['Aeq'], payload['b']
    if j in integer_set or c[j] != 0 or lb[j] != 0 or ub[j] not in (0, 1):
        return None
    if e.indptr[j + 1] != e.indptr[j]:
        return None
    occurrences = a.indices[a.indptr[j]:a.indptr[j + 1]]
    if not len(occurrences):
        return None
    lower, upper = [], []
    for row_id in occurrences:
        row_id = int(row_id)
        indices, values = _row(rows, row_id)
        own = values[indices == j]
        if len(own) != 1 or b[row_id] != 0:
            return None
        others = [(int(k), float(v)) for k, v in zip(indices, values) if k != j]
        if any(k not in integer_set for k, _ in others):
            return None
        if own[0] == -1 and len(others) == 1 and others[0][1] == 1:
            lower.append((row_id, others[0][0]))
        elif own[0] == 1 and all(v == -1 for _, v in others):
            upper.append((row_id, [k for k, _ in others]))
        else:
            return None
    if len(upper) != 1:
        return None
    ys = upper[0][1]
    if sorted(y for _, y in lower) != ys or len(set(ys)) != len(ys):
        return None
    if ub[j] != int(bool(ys)) or any(lb[y] != 0 or ub[y] != 1 for y in ys):
        return None
    return {'column': int(j), 'ys': ys,
            'lower_rows': [r for r, _ in lower], 'upper_row': upper[0][0]}


def _json_hash(value):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=True, allow_nan=False).encode('ascii')
    except (TypeError, ValueError, OverflowError) as error:
        raise CertifiedProjectionError('Certificate must contain finite JSON values') from error
    return hashlib.sha256(raw).hexdigest()


def _integer_list(value, name, limit, *, sorted_unique=True):
    _require(type(value) is list and all(type(x) is int for x in value), name + ': integer list required')
    _require(all(0 <= x < limit for x in value), name + ': index out of range')
    if sorted_unique:
        _require(value == sorted(set(value)), name + ': sorted unique indices required')
    return value


def _certificate_sanity(cert):
    _require(type(cert) is dict and set(cert) == CERT_KEYS, 'Unexpected certificate fields')
    _require(cert['schema'] == SCHEMA and cert['policy'] == POLICY, 'Unsupported certificate schema/policy')
    unsealed = {k:v for k,v in cert.items() if k != 'certificate_sha256'}
    _require(type(cert['certificate_sha256']) is str and _json_hash(unsealed) == cert['certificate_sha256'],
             'Certificate identity mismatch')
    counts = cert['original_counts']
    _require(type(counts) is dict and set(counts) == {'variables','inequalities','equalities','integers'},
             'Unexpected original counts')
    _require(all(type(x) is int and x >= 0 for x in counts.values()), 'Invalid original counts')
    n, m = counts['variables'], counts['inequalities']
    keep = _integer_list(cert['kept_columns'], 'kept_columns', n)
    _require(type(cert['removed_or_blocks']) is list, 'OR blocks must be a list')
    removed, block_rows = [], []
    for block in cert['removed_or_blocks']:
        _require(type(block) is dict and set(block) == {'column','ys','lower_rows','upper_row'},
                 'Unexpected OR block fields')
        _require(type(block['column']) is int and 0 <= block['column'] < n, 'Invalid OR column')
        _require(type(block['upper_row']) is int and 0 <= block['upper_row'] < m, 'Invalid OR upper row')
        _integer_list(block['ys'], 'OR ys', n)
        _integer_list(block['lower_rows'], 'OR lower rows', m)
        _require(len(block['ys']) == len(block['lower_rows']), 'OR row count mismatch')
        _require(all(y in keep for y in block['ys']), 'OR inputs must be retained')
        removed.append(block['column'])
        block_rows.extend(block['lower_rows'] + [block['upper_row']])
    _require(removed == sorted(set(removed)), 'OR columns must be sorted and unique')
    _require(sorted(keep + removed) == list(range(n)), 'Column partition is incomplete or overlapping')
    _require(len(block_rows) == len(set(block_rows)), 'OR rows overlap')
    _integer_list(cert['removed_or_rows'], 'removed_or_rows', m)
    _require(cert['removed_or_rows'] == sorted(block_rows), 'OR row coverage mismatch')
    retained = _integer_list(cert['kept_inequality_rows'], 'kept_inequality_rows', m)
    empty = _integer_list(cert['true_empty_rows'], 'true_empty_rows', m)
    _require(type(cert['duplicate_rows']) is list, 'Duplicate rows must be a list')
    duplicate_indices = []
    for item in cert['duplicate_rows']:
        _require(type(item) is dict and set(item) == {'row','representative'}, 'Invalid duplicate row record')
        row, representative = item['row'], item['representative']
        _require(type(row) is int and type(representative) is int and 0 <= representative < row < m,
                 'Invalid duplicate indices')
        _require(representative in retained, 'Duplicate representative must be retained')
        duplicate_indices.append(row)
    _require(duplicate_indices == sorted(set(duplicate_indices)), 'Duplicate indices not sorted/unique')
    _require(sorted(retained + block_rows + empty + duplicate_indices) == list(range(m)),
             'Inequality coverage is incomplete or overlapping')
    expected = _statistics(n, m, counts['equalities'], removed, block_rows,
                           duplicate_indices, empty, keep, retained)
    _require(type(cert['statistics']) is dict and
             all(type(v) is int for v in cert['statistics'].values()) and
             cert['statistics'] == expected, 'Statistics mismatch')
    return n, keep


def _statistics(n, m, me, removed, or_rows, duplicates, empty, keep, retained):
    return {'removed_variables': len(removed), 'removed_or_inequalities': len(or_rows),
            'duplicate_inequalities': len(duplicates), 'true_empty_inequalities': len(empty),
            'total_removed_inequalities': m - len(retained),
            'retained_variables': len(keep), 'retained_inequalities': len(retained),
            'retained_equalities': me}


def _derive(payload, kept_columns, kept_rows):
    mapping = np.full(len(payload['c']), -1, dtype=np.int64)
    mapping[kept_columns] = np.arange(len(kept_columns), dtype=np.int64)
    result = {key: payload[key][kept_columns].copy() for key in ('c','lb','ub')}
    result.update(A=payload['A'][kept_rows, :][:, kept_columns].tocsc(copy=True),
                  b=payload['b'][kept_rows].copy(),
                  Aeq=payload['Aeq'][:, kept_columns].tocsc(copy=True),
                  beq=payload['beq'].copy(), intcon=mapping[payload['intcon']].copy())
    if 'x0' in payload:
        result['x0'] = payload['x0'][kept_columns].copy()
    return result


def transform(original, *, policy, check=None):
    """Copy and reduce certified OR blocks, then exact inequality duplicates.

    The returned JSON certificate is sealed but not signed. Call verify against
    the immutable original before relying on it; hashes are not authorization.
    """
    _require(policy == POLICY, 'Explicit AUTO_LOW policy required')
    n = _validate(original, check)
    source_identity = identity(original, check=check)
    rows = original['A'].tocsr(copy=True)
    integers = set(map(int, original['intcon']))
    blocks = []
    for j in range(n):
        if j % 64 == 0:
            _tick(check)
        block = _block(original, rows, j, integers)
        if block is not None:
            blocks.append(block)
    removed = [b['column'] for b in blocks]
    or_rows = sorted(r for b in blocks for r in b['lower_rows'] + [b['upper_row']])
    _require(len(or_rows) == len(set(or_rows)), 'OR blocks unexpectedly overlap')
    removed_set, or_set = set(removed), set(or_rows)
    keep = [i for i in range(n) if i not in removed_set]
    retained, duplicates, empty, seen = [], [], [], {}
    for row in range(rows.shape[0]):
        if row % 128 == 0:
            _tick(check)
        if row in or_set:
            continue
        indices, values = _row(rows, row)
        _require(not any(int(i) in removed_set for i in indices), 'Removed column used outside OR block')
        if not len(indices) and original['b'][row] >= 0:
            empty.append(row)
            continue
        # Retained rows have no removed-column support. Comparing original
        # indices is exactly equivalent to comparing their injective reindexing.
        key = _row_key(rows, original['b'], row)
        if key in seen:
            duplicates.append({'row': row, 'representative': seen[key]})
        else:
            seen[key] = row
            retained.append(row)
    reduced = _derive(original, keep, retained)
    _tick(check)
    cert = {'schema': SCHEMA, 'policy': policy, 'source_identity': source_identity,
            'derived_identity': identity(reduced, check=check),
            'original_counts': {'variables': n, 'inequalities': rows.shape[0],
                                'equalities': original['Aeq'].shape[0], 'integers': len(integers)},
            'kept_columns': keep, 'removed_or_blocks': blocks,
            'kept_inequality_rows': retained, 'removed_or_rows': or_rows,
            'duplicate_rows': duplicates, 'true_empty_rows': empty,
            'statistics': _statistics(n, rows.shape[0], original['Aeq'].shape[0],
                removed, or_rows, duplicates, empty, keep, retained)}
    cert['certificate_sha256'] = _json_hash(cert)
    verify(original, reduced, cert, policy=policy, check=check)
    return reduced, cert


def verify(original, reduced, certificate, *, policy, check=None):
    """Validate each proof and unchanged array slice without calling transform."""
    _require(policy == POLICY, 'Explicit AUTO_LOW policy required')
    n = _validate(original, check)
    _validate(reduced, check)
    n_cert, keep = _certificate_sanity(certificate)
    _require(n == n_cert and certificate['policy'] == policy, 'Original dimension/policy mismatch')
    counts = {'variables': n, 'inequalities': original['A'].shape[0],
              'equalities': original['Aeq'].shape[0], 'integers': len(original['intcon'])}
    _require(certificate['original_counts'] == counts, 'Original counts mismatch')
    _require(identity(original, check=check) == certificate['source_identity'], 'Original arrays changed')
    _require(identity(reduced, check=check) == certificate['derived_identity'], 'Reduced arrays changed')
    rows = original['A'].tocsr(copy=True)
    integers = set(map(int, original['intcon']))
    for index, block in enumerate(certificate['removed_or_blocks']):
        if index % 64 == 0:
            _tick(check)
        _require(_block(original, rows, block['column'], integers) == block,
                 'OR certificate does not match all original column occurrences')
    for index, pair in enumerate(certificate['duplicate_rows']):
        if index % 128 == 0:
            _tick(check)
        _require(_row_key(rows, original['b'], pair['row']) ==
                 _row_key(rows, original['b'], pair['representative']), 'Duplicate is not bit-exact')
    for row in certificate['true_empty_rows']:
        _require(rows.indptr[row] == rows.indptr[row+1] and original['b'][row] >= 0,
                 'Empty-row proof is false')
    expected = _derive(original, keep, certificate['kept_inequality_rows'])
    _require(identity(expected, check=check) == identity(reduced, check=check),
             'Reduced arrays do not equal untouched original slices')
    _tick(check)
    return {'verified': True, 'schema': SCHEMA,
            'certificate_sha256': certificate['certificate_sha256'],
            'all_original_inequalities_accounted_once': True,
            'all_original_equalities_retained': True,
            'original_integer_columns_retained': True,
            'objective_and_retained_coefficients_bitwise_preserved': True,
            'exact_real_projection_equivalence': True,
            'floating_tolerance_equivalence_claim': False,
            'candidate_admission_performed': False, 'thermal_safe_claim': False}


def project(full_vector, certificate):
    """Project without numerical repair; this is NOT an admission check."""
    n, keep = _certificate_sanity(certificate)
    full = _vector(full_vector, 'full_vector', n)
    return full[keep].copy()


def lift(reduced_vector, certificate):
    """Recover original coordinates; original numerical/SAFE admission is mandatory.

    Retained coordinates are copied bit-for-bit. J=max(0,y) defines only removed
    auxiliaries and never clips a retained y, including a slightly negative y.
    """
    n, keep = _certificate_sanity(certificate)
    reduced = _vector(reduced_vector, 'reduced_vector', len(keep))
    full = np.empty(n, dtype=np.float64)
    full[keep] = reduced
    for block in certificate['removed_or_blocks']:
        full[block['column']] = max([0.0] + [float(full[y]) for y in block['ys']])
    return full
