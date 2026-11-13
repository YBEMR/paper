"""D281 offline binary64 transport contract. No native backend or solve entry point.

The fake backend tests serialization semantics only. It cannot establish solver
acceptance, numerical feasibility, SAFE, or performance. Integer base is explicit.
"""
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import math
import numpy as np
from scipy import sparse


class ContractError(ValueError):
    pass


def vector(value, length, name, bounds=False):
    a = np.asarray(value)
    if a.dtype.kind != 'f' or a.dtype.itemsize != 8:
        raise ContractError(name + ': binary64 required, no implicit cast')
    if a.ndim > 2 or (a.ndim == 2 and min(a.shape, default=0) > 1):
        raise ContractError(name + ': vector required')
    a = np.array(a.reshape(-1), dtype='<f8', copy=True)
    if len(a) != length or np.isnan(a).any() or (not bounds and not np.isfinite(a).all()):
        raise ContractError(name + ': length/nonfinite')
    return a


def triplets(value, n, name):
    if not sparse.issparse(value) or value.shape[1] != n:
        raise ContractError(name + ': sparse shape required')
    coo = value.tocoo(copy=True)
    data = vector(coo.data, coo.nnz, name)
    order = np.lexsort((coo.col, coo.row))
    row = np.array(coo.row[order], dtype='<i8')
    col = np.array(coo.col[order], dtype='<i8')
    data = data[order]
    if len(row) > 1 and np.any((row[1:] == row[:-1]) & (col[1:] == col[:-1])):
        raise ContractError(name + ': duplicate coordinates; summation prohibited')
    if (data == 0).any():
        raise ContractError(name + ': explicit sparse zero requires separate audited policy')
    return (value.shape, row, col, data)


def integer_indices(value, n, base):
    if type(base) is not int or base not in (0, 1):
        raise ContractError('intcon base must be explicitly 0 or 1')
    a = np.asarray(value)
    if a.dtype.kind not in 'if' or a.dtype.kind == 'b':
        raise ContractError('integer indices must be numeric, not boolean')
    a = a.reshape(-1)
    if not np.isfinite(a).all() or np.any(a != np.floor(a)):
        raise ContractError('nonintegral intcon')
    if np.any(a < base) or np.any(a >= n + base):
        raise ContractError('out of range intcon')
    a = a.astype('<i8') - base
    if len(np.unique(a)) != len(a):
        raise ContractError('duplicate intcon')
    # Order of variable columns is never changed. Normalize only the index set.
    return np.sort(a)


@dataclass
class MatrixPacket:
    n: int
    A: tuple
    Aeq: tuple
    c: np.ndarray
    b: np.ndarray
    beq: np.ndarray
    lb: np.ndarray
    ub: np.ndarray
    intcon: np.ndarray
    x0: np.ndarray
    column_ids: tuple
    sense: str = 'min'
    objective_constant: float = 0.0

    @classmethod
    def read(cls, arrays, *, intcon_base, sense, objective_constant, column_ids):
        n = np.asarray(arrays['c']).size
        if sense != 'min' or type(objective_constant) is not float or objective_constant.hex() != '0x0.0p+0':
            raise ContractError('frozen objective is min c*x + positive zero')
        if tuple(column_ids) != tuple(range(n)):
            raise ContractError('original ordered column IDs required')
        A = triplets(arrays['A'], n, 'A')
        E = triplets(arrays['Aeq'], n, 'Aeq')
        v = {k: vector(arrays[k], size, k, k in ('lb', 'ub'))
             for k, size in [('c', n), ('b', A[0][0]), ('beq', E[0][0]),
                             ('lb', n), ('ub', n), ('x0', n)]}
        if np.any(np.isposinf(v['lb'])) or np.any(np.isneginf(v['ub'])) or np.any(v['lb'] > v['ub']):
            raise ContractError('invalid bounds')
        return cls(n, A, E, **v, intcon=integer_indices(arrays['intcon'], n, intcon_base),
                   column_ids=tuple(column_ids), sense=sense, objective_constant=objective_constant)

    def hashes(self):
        result = {}
        for name in ('c', 'b', 'beq', 'lb', 'ub', 'intcon', 'x0'):
            result[name] = hashlib.sha256(getattr(self, name).tobytes()).hexdigest()
        for name in ('A', 'Aeq'):
            shape, row, col, data = getattr(self, name)
            result[name] = hashlib.sha256(np.asarray(shape, dtype='<i8').tobytes()
                                          + row.tobytes() + col.tobytes() + data.tobytes()).hexdigest()
        result['metadata'] = hashlib.sha256(repr((self.n, self.column_ids, self.sense,
                                                self.objective_constant.hex())).encode()).hexdigest()
        return result

    def assert_same(self, readback):
        if self.hashes() != readback.hashes():
            raise ContractError('binary64/column/domain/objective/start readback drift')


class FakeBackend:
    """Deep-copy transport only: not a solver, no native acceptance claim."""
    def load_and_readback(self, packet):
        import copy
        return copy.deepcopy(packet)


def native_quota(elapsed):
    if not math.isfinite(elapsed) or elapsed < 0:
        raise ContractError('invalid monotonic elapsed time')
    quota = math.floor(min(540, max(0, 600 - elapsed - 10 - 50)))
    return quota if quota >= 30 else 0


def license_gate(*, installed, entitlement, max_variables, max_rows, n, m):
    """Metadata gate only. Passing does not enable any execution in D281."""
    if installed is not True or entitlement not in ('verified_full', 'verified_open_source'):
        return False
    return all(limit is None or (type(limit) is int and limit >= size)
               for limit, size in [(max_variables, n), (max_rows, m)])


def interval(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2 or any(type(x) is not str for x in value):
        raise ContractError('exact interval endpoints must be decimal/rational strings')
    low, high = map(Fraction, value)
    if low > high:
        raise ContractError('reversed interval')
    return low, high


def classify_mock(receipt):
    """Control specification, NOT an evidence verifier. All inputs are mock only.

    Real code must derive these flags from hash-bound numeric/vector/schedule/SAFE
    verifiers and native events. This function is not an authorization endpoint.
    """
    if receipt.get('mode') != 'SIMULATION_ONLY':
        raise ContractError('real receipts prohibited')
    for field in ('source_identity', 'matrix_identity', 'cleanup_ok'):
        if receipt.get(field) is not True:
            return 'INTEGRITY_STOP'
    if receipt.get('native_calls') != 1:
        return 'INTEGRITY_STOP'
    times = [receipt.get(k) for k in ('native_received_s', 'evidence_sealed_s')]
    if any(type(t) not in (int, float) or not math.isfinite(t) or t < 0 for t in times):
        return 'INTEGRITY_STOP'
    if times[1] < times[0]:
        return 'INTEGRITY_STOP'
    if times[0] > 550 or times[1] > 600:
        return 'LATE_UNCREDITED'
    if receipt.get('bound_conflict') is True:
        return 'BOUND_CONFLICT_STOP'
    if receipt.get('has_native_vector') is not True:
        return 'NO_NATIVE_CANDIDATE'
    if any(receipt.get(k) is not True for k in ('old_matrix_admitted', 'new_matrix_admitted', 'schedule_legal')):
        return 'CANDIDATE_REJECTED'
    if receipt.get('full_safe_AB') is not True or receipt.get('full_safe_AC') is not True:
        return 'SAFE_NOT_ESTABLISHED'
    if receipt.get('different_schedule') is not True:
        return 'COMMON_SCHEDULE_SAFE_ONLY'
    old = interval(receipt.get('initial_energy'))
    new = interval(receipt.get('candidate_energy'))
    return 'STRICT_IMPROVEMENT' if new[1] < old[0] else 'SAFE_WITHOUT_STRICT_IMPROVEMENT'


def native_execution(*args, **kwargs):
    raise ContractError('D281 has no native backend: environment/license unresolved; independent future approval required')
