"""One fixed nominal delivery reserve inside the original 600-second root.

Install before the exact-equality wrapper: its conversion is then charged
before this wrapper computes a native-only duration cap. Neither the response
deadline nor the scientific acceptance cutoff is shortened or extended.
"""
import json
import math
from pathlib import Path


METHOD_SECONDS = 600
RESERVE_SECONDS = 30
PROTOCOL = 'native-duration-cap-nominal-delivery-reserve-30-v1'


class DeliveryReserveUnavailable(RuntimeError):
    """No new native request may use the reserved delivery allowance."""


def _finite(value, label):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError('Nonfinite or invalid ' + label)
    return float(value)


def _save(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def attach(session):
    """Wrap the same session without changing its callback or returned receipt."""
    if getattr(session, '_delivery_reserve_attached', False):
        raise ValueError('Delivery-reserve adapter cannot be attached twice')
    if getattr(session, '_exact_equalities_attached', False):
        raise ValueError('Install reserve adapter before equality conversion wrapper')
    backend_solve = session.solve

    def solve(model, remaining_s=None, budget=None, x0=None, solver_max_time_s=None):
        if solver_max_time_s is not None:
            raise ValueError('External solver cap forbidden by fixed delivery policy')
        root = budget if budget is not None else getattr(session, 'budget', None)
        if root is None:
            raise ValueError('Original method budget required')
        if _finite(root.seconds, 'method seconds') != METHOD_SECONDS:
            raise ValueError('Delivery policy requires the declared 600-second root')
        root.check()
        entered = _finite(session.clock(), 'clock')
        deadline = min(_finite(root.deadline, 'root deadline'),
                       _finite(session.deadline, 'session deadline'))
        if getattr(session, 'budget', None) is not None:
            deadline = min(deadline, _finite(session.budget.deadline, 'session budget deadline'))
        if remaining_s is not None:
            remaining = _finite(remaining_s, 'remaining seconds')
            if remaining < 0:
                raise ValueError('Negative remaining seconds')
            deadline = min(deadline, entered + remaining)
        available = max(0.0, deadline - entered)
        cap = available - RESERVE_SECONDS
        prospective = session.counter + 1
        path = session.workdir / f'request_{prospective:06d}.delivery_reserve.json'
        receipt = dict(protocol=PROTOCOL, prospective_request_number=prospective,
            root_method_seconds=METHOD_SECONDS, nominal_reserve_seconds=RESERVE_SECONDS,
            allocation_at_monotonic=entered, root_absolute_deadline=float(root.deadline),
            effective_response_deadline=deadline, available_at_allocation_s=available,
            native_duration_cap_s=max(0.0, cap),
            response_deadline_changed=False, native_return_unmodified=True,
            native_request_submitted_by_adapter=False,
            scope='Duration cap only; subsequent transport/preparation overhead can consume part of the nominal reserve. No guaranteed hard native stop time.')
        if cap <= 0:
            receipt.update(state='NO_NATIVE_REQUEST_DELIVERY_RESERVE_UNAVAILABLE',
                           native_backend_called=False, native_request_number_consumed=False)
            _save(path, receipt)
            raise DeliveryReserveUnavailable('Remaining method allowance is at most the fixed 30-second delivery reserve')
        receipt.update(state='NATIVE_DURATION_CAP_ALLOCATED', native_backend_called='AFTER_THIS_RECEIPT')
        _save(path, receipt)
        root.check()
        # Keep original response/acceptance deadline and all original inputs.
        # The backend owns request counting, publications and result receipts.
        return backend_solve(model, remaining_s=remaining_s, budget=budget,
                             x0=x0, solver_max_time_s=cap)

    session.solve = solve
    session._delivery_reserve_attached = True
    return session
