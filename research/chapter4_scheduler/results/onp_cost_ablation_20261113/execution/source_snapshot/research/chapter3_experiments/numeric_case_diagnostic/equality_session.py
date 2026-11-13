"""Budgeted exact-row representation for fresh formal MILP requests.

Only ``solve`` is wrapped. The original native session, options, callback
consumer, Recorder/Model physical checks, returned receipt and late semantics
are retained. No historical matrix, initial point or candidate is read.
"""
from contextlib import nullcontext
import json
from pathlib import Path

import numpy as np
from scipy import sparse
from scipy.io import loadmat

from . import exact_equalities


NATIVE_ARRAYS = ('c', 'A', 'b', 'Aeq', 'beq', 'lb', 'ub', 'intcon')


def _save(path, value, *, immutable=False):
    path = Path(path)
    content = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    if immutable:
        with path.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(content)
    else:
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_text(content, encoding='utf-8')
        temporary.replace(path)


def _same_array(left, right):
    left, right = np.asarray(left), np.asarray(right)
    return left.shape == right.shape and left.dtype == right.dtype and left.tobytes() == right.tobytes()


def _same_sparse(left, right):
    return (sparse.issparse(left) and sparse.issparse(right)
            and left.format == right.format and left.shape == right.shape
            and all(_same_array(getattr(left, key), getattr(right, key))
                    for key in ('data', 'indices', 'indptr')))


def _sent_identity(path, expected, supplied_x0):
    keys = NATIVE_ARRAYS + ('x0',)
    actual = loadmat(path, variable_names=list(keys))
    if ('x0' in actual) != supplied_x0:
        raise ValueError('Native x0 presence differs from this request')
    checks = {}
    for key in NATIVE_ARRAYS + (('x0',) if supplied_x0 else ()):
        value = actual[key] if key in ('A', 'Aeq') else actual[key].reshape(-1)
        equal = _same_sparse(value, expected[key]) if key in ('A', 'Aeq') else _same_array(value, expected[key])
        if not equal:
            raise ValueError('Native transformed payload differs: ' + key)
        checks[key] = True
    return {'state': 'MATCHED_EXPECTED_TRANSFORMATION', 'arrays': checks,
            'native_x0_provided': supplied_x0}


def _normalise(model, x0, bridge):
    original_native = bridge._prepare(model, x0=x0)
    # The proof helper has a mandatory copy-only x0 field. An absent x0 uses
    # a labelled placeholder solely for the algebraic certificate; it is
    # removed from the model sent to the backend and never supplied as x0.
    original = {key: value.copy() for key, value in original_native.items() if key in NATIVE_ARRAYS}
    original['intcon'] = original_native['intcon'].astype(np.int64) - 1
    original['x0'] = (original_native['x0'].copy() if x0 is not None
                      else np.zeros(len(original['c']), dtype=np.float64))
    represented, certificate = exact_equalities.transform(original)
    represented.pop('x0')
    if 'metadata' in model:
        represented['metadata'] = model['metadata']
    expected_native = bridge._prepare(represented, x0=x0)
    return original_native, represented, expected_native, certificate


def attach(session, *, numeric_bridge=None):
    """Wrap a newly created/guarded session in place; return that same object."""
    if getattr(session, '_exact_equalities_attached', False):
        raise ValueError('Exact-equality adapter cannot be attached twice')
    if numeric_bridge is None:
        import matlab_bridge as numeric_bridge
    backend_solve = session.solve

    def solve(model, remaining_s=None, budget=None, x0=None, solver_max_time_s=None):
        root = budget if budget is not None else getattr(session, 'budget', None)
        if root is None:
            raise ValueError('Equality representation requires the original method budget')
        clock = session.clock
        entered = clock()
        deadline = min(float(root.deadline), float(session.deadline))
        if getattr(session, 'budget', None) is not None:
            deadline = min(deadline, float(session.budget.deadline))
        if remaining_s is not None:
            if not np.isfinite(remaining_s) or remaining_s <= 0:
                # Preserve the existing backend's own invalid/expired contract.
                return backend_solve(model, remaining_s=remaining_s, budget=budget,
                                     x0=x0, solver_max_time_s=solver_max_time_s)
            deadline = min(deadline, entered + float(remaining_s))
        root.check()
        request_number = session.counter + 1
        prefix = session.workdir / f'request_{request_number:06d}'
        receipt_path = prefix.with_suffix('.equality_admission.json')
        receipt = {'request_number': request_number, 'representation': 'exact_opposite_rows_to_equalities_v1',
                   'started_at_monotonic': entered, 'absolute_deadline': deadline,
                   'x0_supplied_to_native': x0 is not None,
                   'proof_x0_field': 'this_request_x0' if x0 is not None else 'zero_copy_placeholder_never_sent',
                   'callback_scope': 'Unchanged Recorder.poll on original Model: logical/schedule and complete physical evaluation; no extra callback row-admission algorithm.',
                   'native_return_unmodified': True, 'thermal_or_optimality_claim': False,
                   'actual_transport': {'state': 'NOT_CHECKED_YET'},
                   'final_original_rows': {'state': 'NOT_CHECKED_YET'}}
        phase = getattr(root, 'phase', lambda _: nullcontext())
        try:
            with phase('exact_equality_conversion_and_certificate'):
                original_native, represented, expected_native, certificate = _normalise(model, x0, numeric_bridge)
                certificate['request_initial_point_scope'] = receipt['proof_x0_field']
                _save(prefix.with_suffix('.equality_certificate.json'), certificate, immutable=True)
                receipt.update(original_inequalities=int(original_native['A'].shape[0]),
                    original_equalities=int(original_native['Aeq'].shape[0]),
                    transformed_inequalities=int(expected_native['A'].shape[0]),
                    transformed_equalities=int(expected_native['Aeq'].shape[0]),
                    exact_pairs_moved=certificate['exact_pairs_moved'],
                    certificate_checks=certificate['checks'], state='REPRESENTATION_READY')
                _save(receipt_path, receipt)
            root.check()
        except BaseException as error:
            receipt.update(state='CONVERSION_FAILED_OR_EXPIRED', error_type=type(error).__name__,
                           error=str(error), completed_at_monotonic=clock())
            _save(receipt_path, receipt)
            raise
        # Conversion consumes the existing request allowance, never replenishes it.
        native_remaining = None if remaining_s is None else max(0.0, deadline - clock())
        returned = backend_solve(represented, remaining_s=native_remaining, budget=budget,
                                 x0=x0, solver_max_time_s=solver_max_time_s)
        receipt['backend_returned_at_monotonic'] = clock()
        receipt['native_status'] = returned.get('status')
        receipt['native_budget_valid'] = returned.get('budget_valid')
        # Formal appends the unchanged native receipt, then checks its deadline.
        # Never lose that round through an adapter-only post-return expiry.
        if not returned.get('budget_valid') or clock() >= deadline:
            receipt.update(state='NATIVE_RETURN_LATE_OR_BUDGET_EXHAUSTED',
                actual_transport={'state': 'DEFERRED_TO_READONLY_ARCHIVE_AUDIT'},
                final_original_rows={'state': 'NOT_CHECKED_LATE_OR_EXPIRED'})
            _save(receipt_path, receipt)
            return returned
        try:
            with phase('exact_equality_transport_identity'):
                if session.counter != request_number:
                    raise ValueError('Native request number changed unexpectedly')
                receipt['actual_transport'] = _sent_identity(prefix.with_suffix('.mat'), expected_native, x0 is not None)
                receipt['actual_transport']['completed_at_monotonic'] = clock()
            if clock() < deadline and returned.get('x') and returned.get('accepted_for_evaluation'):
                with phase('exact_equality_final_original_row_admission'):
                    _, original_check = numeric_bridge._check_initial_point(original_native, returned['x'])
                    receipt['final_original_rows'] = dict(original_check,
                        state='ORIGINAL_ROWS_NUMERICALLY_ADMITTED', completed_at_monotonic=clock(),
                        original_inequalities=int(original_native['A'].shape[0]),
                        original_equalities=int(original_native['Aeq'].shape[0]),
                        scope='Current original numerical rows/bounds/integer tolerance; not a thermal certificate')
            elif not returned.get('x'):
                receipt['final_original_rows'] = {'state': 'NO_NATIVE_FINAL_VECTOR'}
            else:
                receipt['final_original_rows'] = {'state': 'NOT_CHECKED_EXPIRED_OR_NOT_ACCEPTED'}
            receipt.update(state='NATIVE_RECEIPT_PRESERVED', completed_at_monotonic=clock(),
                           adapter_checks_completed_within_deadline=clock() < deadline)
        except BaseException as error:
            if clock() >= deadline and type(error).__name__ in ('Exhausted', 'TimeoutError'):
                receipt.update(state='POSTRETURN_CHECK_EXPIRED_NATIVE_RECEIPT_PRESERVED',
                               completed_at_monotonic=clock())
            else:
                receipt.update(state='ORIGINAL_NUMERICAL_OR_TRANSPORT_REJECTION',
                               error_type=type(error).__name__, error=str(error),
                               completed_at_monotonic=clock())
                if hasattr(error, 'diagnostics'):
                    receipt['rejection_diagnostics'] = error.diagnostics
                _save(receipt_path, receipt)
                raise
        _save(receipt_path, receipt)
        return returned

    session.solve = solve
    session._exact_equalities_attached = True
    return session
