"""Handwritten numerical fixtures and fake native backend only."""
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from scipy import sparse
from scipy.io import savemat

from research.chapter3_experiments import matlab_bridge
from research.chapter3_experiments.numeric_case_diagnostic import equality_session as adapter


class Exhausted(Exception):
    pass


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


class Budget:
    def __init__(self, clock):
        self.clock = clock
        self.deadline = 100.0
        self.phases = []

    def check(self):
        if self.clock() >= self.deadline:
            raise Exhausted('test deadline')

    @contextmanager
    def phase(self, name):
        self.check()
        self.phases.append(name)
        yield


class FakeSession:
    def __init__(self, folder):
        self.clock = Clock()
        self.budget = Budget(self.clock)
        self.deadline = self.budget.deadline
        self.workdir = Path(folder)
        self.counter = 0
        self.calls = []
        self.event_consumer = lambda prefix: None
        self.vector = [1.0, 0.0]
        self.finish_at = 1.0
        self.drift = False
        self.last_returned = None

    def solve(self, model, remaining_s=None, budget=None, x0=None, solver_max_time_s=None):
        self.counter += 1
        prefix = self.workdir / f'request_{self.counter:06d}'
        self.calls.append({'model': model, 'x0': x0, 'remaining_s': remaining_s,
                           'budget': budget, 'solver_max_time_s': solver_max_time_s})
        payload = matlab_bridge._prepare(model, x0=x0)
        if self.drift:
            payload['lb'] = payload['lb'].copy()
            payload['lb'][0] += 0.01
        savemat(prefix.with_suffix('.mat'), payload, oned_as='column')
        self.event_consumer(prefix)
        self.clock.value = self.finish_at
        timely = self.clock() < self.deadline
        returned = {'status': 'SOLVED' if timely else 'BUDGET_EXHAUSTED',
                    'budget_valid': timely, 'accepted_for_evaluation': timely,
                    'x': list(self.vector) if timely else [], 'fval': 1.0,
                    'exitflag': 1 if timely else None, 'request_number': self.counter}
        prefix.with_suffix('.python.json').write_text(json.dumps(returned), encoding='utf-8')
        self.last_returned = returned
        return returned


def fixture(extra=False):
    rows = [[1., 1.], [-1., -1.], [1., 0.]]
    rhs = [1., -1., 1.]
    if extra:
        rows.append([1., 0.]); rhs.append(0.)
    return {'c': np.array([1., 1.]), 'A': sparse.csc_matrix(rows),
            'b': np.array(rhs), 'Aeq': sparse.csc_matrix((0, 2)), 'beq': np.array([]),
            'lb': np.array([0., 0.]), 'ub': np.array([1., 1.]), 'intcon': np.array([0]),
            'metadata': {'fixture': 'handwritten, not a research model'}}


class EqualitySessionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='eqtest_', dir=Path(__file__).resolve().parent)
        self.path = Path(self.folder.name).resolve()
        self.assertEqual(self.path.parent, Path(__file__).resolve().parent)
        self.addCleanup(self.folder.cleanup)
        self.session = FakeSession(self.path)
        adapter.attach(self.session, numeric_bridge=matlab_bridge)

    def receipt(self, number=1):
        return json.loads((self.path / f'request_{number:06d}.equality_admission.json').read_text(encoding='utf-8'))

    def assert_native_untouched(self, result, number=1):
        self.assertIs(result, self.session.last_returned)
        saved = json.loads((self.path / f'request_{number:06d}.python.json').read_text(encoding='utf-8'))
        self.assertEqual(result, saved)

    def test_first_x0_exact_representation_and_callback_identity(self):
        consumer = self.session.event_consumer
        point = np.array([1., 0.])
        result = self.session.solve(fixture(), budget=self.session.budget, remaining_s=100, x0=point)
        self.assert_native_untouched(result)
        self.assertIs(self.session.event_consumer, consumer)
        call = self.session.calls[0]
        self.assertIs(call['x0'], point)
        self.assertNotIn('x0', call['model'])
        self.assertEqual(call['model']['A'].shape, (1, 2))
        self.assertEqual(call['model']['Aeq'].shape, (1, 2))
        self.assertEqual(self.receipt()['final_original_rows']['original_inequalities'], 3)

    def test_followup_without_x0_retains_new_feedback_row(self):
        self.session.solve(fixture(), budget=self.session.budget, x0=np.array([1., 0.]))
        self.session.vector = [0., 1.]
        result = self.session.solve(fixture(extra=True), budget=self.session.budget)
        self.assert_native_untouched(result, 2)
        self.assertIsNone(self.session.calls[1]['x0'])
        self.assertNotIn('x0', self.session.calls[1]['model'])
        self.assertEqual(self.session.calls[1]['model']['A'].shape[0], 2)
        self.assertEqual(self.receipt(2)['final_original_rows']['original_inequalities'], 4)
        self.assertEqual(self.receipt(2)['proof_x0_field'], 'zero_copy_placeholder_never_sent')

    def test_late_backend_return_keeps_native_receipt_and_skips_final_checks(self):
        self.session.finish_at = 100.0
        with patch.object(adapter, '_sent_identity', side_effect=AssertionError('late identity call')):
            result = self.session.solve(fixture(), budget=self.session.budget)
        self.assert_native_untouched(result)
        self.assertEqual(self.receipt()['final_original_rows']['state'], 'NOT_CHECKED_LATE_OR_EXPIRED')

    def test_postreturn_expiry_does_not_drop_native_round(self):
        original_check = adapter._sent_identity
        def expire_after_identity(*args):
            result = original_check(*args)
            self.session.clock.value = 100.0
            return result
        with patch.object(adapter, '_sent_identity', side_effect=expire_after_identity):
            result = self.session.solve(fixture(), budget=self.session.budget)
        self.assert_native_untouched(result)
        self.assertFalse(self.receipt()['adapter_checks_completed_within_deadline'])

    def test_deadline_exception_after_native_return_preserves_round(self):
        def expiry(*_):
            self.session.clock.value = 100.0
            raise Exhausted('expired while checking')
        with patch.object(adapter, '_sent_identity', side_effect=expiry):
            result = self.session.solve(fixture(), budget=self.session.budget)
        self.assert_native_untouched(result)
        self.assertEqual(self.receipt()['state'], 'POSTRETURN_CHECK_EXPIRED_NATIVE_RECEIPT_PRESERVED')

    def test_actual_transport_drift_is_a_technical_failure(self):
        self.session.drift = True
        with self.assertRaisesRegex(ValueError, 'differs: lb'):
            self.session.solve(fixture(), budget=self.session.budget)
        self.assertEqual(self.receipt()['state'], 'ORIGINAL_NUMERICAL_OR_TRANSPORT_REJECTION')

    def test_original_row_violation_is_rejected_without_rounding(self):
        self.session.vector = [1., 1.]
        with self.assertRaises(matlab_bridge.InitialPointRejected):
            self.session.solve(fixture(), budget=self.session.budget)
        receipt = self.receipt()
        self.assertEqual(receipt['rejection_diagnostics']['inequality_violation'], 1.0)
        self.assertFalse(receipt['rejection_diagnostics']['rounding_or_repair_performed'])

    def test_conversion_consumes_existing_root_before_any_native_call(self):
        original_transform = adapter.exact_equalities.transform
        def expire(*args):
            result = original_transform(*args)
            self.session.clock.value = 100.0
            return result
        with patch.object(adapter.exact_equalities, 'transform', side_effect=expire):
            with self.assertRaises(Exhausted):
                self.session.solve(fixture(), budget=self.session.budget)
        self.assertEqual(self.session.counter, 0)


if __name__ == '__main__':
    unittest.main()
