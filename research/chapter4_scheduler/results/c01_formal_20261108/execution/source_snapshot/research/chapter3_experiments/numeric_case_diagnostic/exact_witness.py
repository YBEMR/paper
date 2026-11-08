"""Exact arithmetic audit of saved binary64 MILP rows; no solver or physics.

Keep the archived x0's selected choices and control states. For each active
opposite affine row pair, set its unique +1 target to the midpoint of the
exact rational interval implied by those two archived rows. Process pairs in
their saved topological order. Then verify *every* original row, bound and
integer condition with Fraction arithmetic. This is a matrix feasibility
witness, not a new schedule, thermal evaluation, optimizer or repair of data.
"""
from fractions import Fraction as Q
import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from scipy.io import loadmat


def audit(matrix_path, limit_seconds=120):
    started = time.monotonic()
    def check_time():
        if time.monotonic()-started > limit_seconds:
            raise TimeoutError('Saved-matrix exact audit exceeded its bound')
    source_bytes = matrix_path.read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    del source_bytes
    data = loadmat(matrix_path)
    a = data['A'].tocsr(); b = data['b'].ravel()
    ae = data['Aeq'].tocsr(); be = data['beq'].ravel()
    original = data['x0'].ravel()
    lo, hi = data['lb'].ravel(), data['ub'].ravel()
    intcon = data['intcon'].ravel().astype(int)-1
    assert a.shape[1] == len(original) == len(lo) == len(hi)
    assert np.isfinite(a.data).all() and np.isfinite(b).all()
    assert np.isfinite(lo).all() and np.isfinite(hi).all()
    assert np.isfinite(original).all()
    cache = {}
    def q(value):
        value = float(value)
        if value not in cache:
            cache[value] = Q.from_float(value)
        return cache[value]
    x = [q(v) for v in original]
    original_q = list(x)
    def row_parts(i):
        sl = slice(a.indptr[i], a.indptr[i+1])
        return a.indices[sl], a.data[sl]
    def dot(indices, values, vector, skip=None):
        total = Q(0)
        for j, value in zip(indices, values):
            if j == skip or not vector[j]:
                continue
            if value == 1:
                total += vector[j]
            elif value == -1:
                total -= vector[j]
            else:
                total += q(value)*vector[j]
        return total
    all_pairs = []
    active_pairs = []
    min_width = None
    for i in range(a.shape[0]-1):
        if i % 128 == 0: check_time()
        ix, av = row_parts(i); jx, bv = row_parts(i+1)
        if len(ix) != len(jx) or not np.array_equal(ix, jx):
            continue
        difference = av+bv
        nz = np.flatnonzero(difference)
        if len(nz) != 1 or difference[nz[0]] <= 0:
            continue
        k = int(nz[0]); gate = int(ix[k])
        # Every non-gate coefficient is bit-for-bit opposite. Check the gate
        # sum exactly as well: no binary64 subtraction is used for the width.
        if not (lo[gate] == 0 and hi[gate] == 1 and x[gate] in (0, 1)):
            continue
        width = q(b[i])+q(b[i+1])-q(av[k])-q(bv[k])
        assert width >= 0, ('empty_archived_pair', i, str(width))
        min_width = width if min_width is None else min(min_width, width)
        all_pairs.append((i, gate))
        if x[gate] != 1:
            continue
        targets = [int(j) for j, value in zip(ix, av) if value == 1 and j != gate]
        assert len(targets) == 1, ('not_unique_affine_target', i, targets)
        target = targets[0]
        assert bv[np.flatnonzero(jx == target)[0]] == -1
        upper = q(b[i])-dot(ix, av, x, skip=target)
        lower = dot(jx, bv, x, skip=target)-q(b[i+1])
        assert lower <= upper, ('empty_substituted_pair', i, str(lower-upper))
        x[target] = (lower+upper)/2
        active_pairs.append((i, gate, target))
    assert len({target for _, _, target in active_pairs}) == len(active_pairs)
    inequality_failures = []
    original_positive = []
    for i in range(a.shape[0]):
        if i % 64 == 0: check_time()
        ix, av = row_parts(i)
        residue = dot(ix, av, x)-q(b[i])
        if residue > 0:
            inequality_failures.append({'row_zero_based': i, 'residual_exact': str(residue),
                                        'residual_float': float(residue)})
        old_residue = dot(ix, av, original_q)-q(b[i])
        if old_residue > 0:
            original_positive.append((float(old_residue), i))
    equality_failures = []
    for i in range(ae.shape[0]):
        check_time()
        row = ae.getrow(i)
        residue = dot(row.indices, row.data, x)-q(be[i])
        if residue:
            equality_failures.append({'row_zero_based': i, 'residual_exact': str(residue)})
    bound_failures = [i for i, v in enumerate(x) if not q(lo[i]) <= v <= q(hi[i])]
    integer_failures = [int(i) for i in intcon if x[i].denominator != 1]
    changed = {i for i, (v, old) in enumerate(zip(x, original_q)) if v != old}
    targets = {t for _, _, t in active_pairs}
    assert changed <= targets
    assert not changed.intersection(set(intcon))
    witness_hash = hashlib.sha256()
    for value in x:
        witness_hash.update(str(value).encode('ascii')+b'\n')
    checks = {'every_inequality_exact': not inequality_failures,
              'every_equality_exact': not equality_failures,
              'every_bound_exact': not bound_failures,
              'every_integer_exact': not integer_failures,
              'only_affine_auxiliary_targets_changed': changed <= targets,
              'all_integer_choices_unchanged': not changed.intersection(set(intcon))}
    return {'state': 'EXACT_MATRIX_FEASIBILITY_WITNESS' if all(checks.values()) else 'WITNESS_CONSTRUCTION_INCOMPLETE',
            'source_matrix': matrix_path.as_posix(), 'source_sha256': source_hash,
            'algorithm': 'Saved active opposite affine pairs, unique +1 target midpoint, saved order; exact binary64-as-rational arithmetic.',
            'variables': a.shape[1], 'inequalities': a.shape[0], 'equalities': ae.shape[0],
            'integer_variables': len(intcon), 'all_opposite_affine_pairs': len(all_pairs),
            'active_affine_pairs': len(active_pairs), 'changed_auxiliary_variables': len(changed),
            'smallest_pair_width_exact': str(min_width), 'smallest_pair_width_float': float(min_width),
            'maximum_auxiliary_change': max(float(abs(v-o)) for v, o in zip(x, original_q)),
            'original_exact_positive_residual_count': len(original_positive),
            'original_maximum_exact_residual_float': max(original_positive, default=(0, None))[0],
            'original_worst_row_zero_based': max(original_positive, default=(0, None))[1],
            'checks': checks, 'inequality_failures': inequality_failures[:20],
            'inequality_failure_count': len(inequality_failures),
            'equality_failures': equality_failures[:20], 'bound_failures': bound_failures[:20],
            'integer_failures': integer_failures[:20],
            'witness_canonical_fraction_lines_sha256': witness_hash.hexdigest(),
            'maximum_denominator_bits': max(v.denominator.bit_length() for v in x),
            'elapsed_s': time.monotonic()-started,
            'scope': 'Feasibility of the archived binary64 numerical MILP, not mathematical optimality or an additional physical SAFE certificate.',
            'scientific_calls': 0, 'solver_calls': 0, 'model_builds': 0, 'thermal_evaluations': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('matrix', type=Path)
    parser.add_argument('new_output', type=Path)
    args = parser.parse_args()
    assert not args.new_output.exists()
    result = audit(args.matrix)
    args.new_output.parent.mkdir(parents=True, exist_ok=True)
    with args.new_output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({k: result[k] for k in ['state', 'checks', 'inequality_failure_count', 'elapsed_s']}, ensure_ascii=False))
