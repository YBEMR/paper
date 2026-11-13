"""Pure fake K191 lifecycle tests: no native process, solver or heat call."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
from scipy import sparse
from scipy.io import savemat


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('k191_runner_under_pure_test', HERE/'run_once.py')
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
checks = runner.bind_lp()
SCRATCH = HERE.parents[2]/'.runtime/k191_runner_pure_tests'


class Clock:
    def __init__(self): self.value = 100.0
    def __call__(self): return self.value
    def advance(self, value): self.value += value


def options(limit=290.0):
    return dict(Algorithm='dual-simplex', Preprocess='none', ConstraintTolerance=1e-9,
        OptimalityTolerance=1e-7, MaxIterations=2049240, Display='off', MaxTime=limit)


def toy_original():
    return dict(c=np.array([1., 2.]), A=sparse.csc_matrix([[-1., 0.]]),
        b=np.array([-.5]), Aeq=sparse.csc_matrix((0, 2)), beq=np.array([]),
        lb=np.array([0., -2.]), ub=np.array([1., 2.]), intcon=np.array([0]),
        x0=np.array([1., .5]))


class PureRunnerTests(unittest.TestCase):
    def setUp(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='fake_', dir=SCRATCH)
        self.folder = Path(self.temp.name)
        self.native_guard = patch.object(runner.subprocess, 'Popen',
            side_effect=AssertionError('NATIVE_PROCESS_FORBIDDEN_IN_PURE_TEST'))
        self.native_popen = self.native_guard.start()

    def tearDown(self):
        self.native_guard.stop()
        self.temp.cleanup()

    def make_worker(self, *, seconds=20, exitflag=1, x=None, options_drift=False,
                    native_error=False, close_failure=False, cleanup_complete=True,
                    constructor_failure=False, loaded_hash_drift=False):
        clock = Clock()
        budget = runner.common.RootBudget(300, clock=clock)
        out = self.folder/'out'
        runner.write_new(out/'declaration.json', {'mock_only': True})
        runner.write_new(out/'launch.claim.json', {
            'declaration_sha256': runner.sha(out/'declaration.json')})
        original = toy_original()
        declaration = {'original_environment': {'mock_only': True},
            'original_native_environment': {'version': 'MOCK', 'release': 'MOCK'}}
        original_key = (runner.OLD/'method/matlab/request_000001.mat').relative_to(runner.REPO).as_posix()
        declaration['original_sources'] = {original_key: {'sha256': 'MOCK_ORIGINAL_PAYLOAD_SHA'}}
        host = {'token_is_appcontainer': False, 'matlab_processes': [],
            'physical_available_bytes': 8*1024**3, 'commit_available_bytes': 8*1024**3,
            'disk_free_bytes': 8*1024**3, 'mock_only': True}
        calls = {'constructors': [], 'submits': [], 'close': 0}
        outer = self

        class FakeLPProcess:
            def __init__(self, bridge, passed_budget, expected_ready):
                outer.assertIs(passed_budget, budget)
                outer.assertEqual(expected_ready, declaration['original_native_environment'])
                calls['constructors'].append(passed_budget)
                self.counter = 0
                self.cleanup = None
                clock.advance(2)
                if constructor_failure:
                    error = RuntimeError('MOCK_CONSTRUCTOR_FAILURE')
                    error.matlab_cleanup = {'mock_only': True, 'complete': True}
                    raise error

            def submit(self, payload, passed_budget):
                outer.assertIs(passed_budget, budget)
                outer.assertEqual(set(payload), set(runner.LP_KEYS))
                outer.assertNotIn('x0', payload)
                outer.assertNotIn('intcon', payload)
                checks.assert_identity(original, payload)
                # In particular do not import K189's fixed integer bounds.
                outer.assertEqual((payload['lb'][0], payload['ub'][0]), (0., 1.))
                self.counter += 1
                outer.assertEqual(self.counter, 1)
                remainder = budget.remaining
                runner.write_new(out/'request.claim.json', {'declared_remaining_s': remainder})
                calls['submits'].append({'budget': passed_budget, 'remaining_s': remainder,
                    'payload': deepcopy(payload)})
                clock.advance(seconds)
                actual = options(max(.01, remainder-.5))
                if options_drift: actual['ConstraintTolerance'] = 1e-8
                vector = [.5, 0.] if x is None else list(x)
                return {'status': 'ERROR' if native_error else 'SOLVED', 'exitflag': exitflag,
                    'x': vector, 'fval': .5 if vector else [], 'options': actual,
                    'linprog_entered': not native_error, 'mock_only': True}

            def close(self):
                calls['close'] += 1
                clock.advance(.5)
                if close_failure: raise RuntimeError('MOCK_CLOSE_FAILURE')
                self.cleanup = {'mock_only': True, 'complete': cleanup_complete}

        bridge = SimpleNamespace(cleanup_is_complete=Mock(side_effect=lambda receipt:
            bool(isinstance(receipt, dict) and receipt.get('mock_only') and receipt.get('complete'))))
        return SimpleNamespace(clock=clock, budget=budget, out=out, original=original,
            declaration=declaration, host=host, calls=calls, process=FakeLPProcess, bridge=bridge,
            loaded_sha='MOCK_DRIFTED_SHA' if loaded_hash_drift else 'MOCK_ORIGINAL_PAYLOAD_SHA')

    def run_worker(self, fixture):
        real_read = runner.read
        def read(path):
            if Path(path).name == 'method_return.json' and Path(path) != fixture.out/'method_return.json':
                return {'result': {'x': [1., .5], 'fval': 2.}}
            return real_read(path)
        with patch.object(runner, 'OUT', fixture.out), \
             patch.object(runner, 'read', side_effect=read), \
             patch.object(runner, 'admission', return_value=fixture.declaration), \
             patch.object(runner, 'bind_lp', return_value=checks), \
             patch.object(runner, 'LPProcess', fixture.process), \
             patch.object(runner.common, 'RootBudget', side_effect=lambda: fixture.budget), \
             patch.object(runner.common, 'context', return_value=fixture.host), \
             patch.object(runner.common, 'bind_bridge', return_value=fixture.bridge), \
             patch.object(runner.common, 'check_python_environment', return_value={'mock_only': True}), \
             patch.object(checks.numeric, 'load_original_mat', return_value=(fixture.original,
                {'mock_only': True, 'sha256': fixture.loaded_sha})):
            status = runner.worker()
        self.assertEqual(self.native_popen.call_count, 0)
        return status, real_read(fixture.out/'method_return.json')

    def test_options_require_exact_scientific_values(self):
        self.assertTrue(runner.verify_options(options(), 291))
        for key, drift in [('Algorithm', 'interior-point'), ('Preprocess', 'basic'),
                           ('ConstraintTolerance', 1e-8), ('OptimalityTolerance', 1e-6),
                           ('MaxIterations', 1), ('Display', 'iter')]:
            actual = options(); actual[key] = drift
            with self.subTest(key=key), self.assertRaises(ValueError):
                runner.verify_options(actual, 291)

    def test_options_time_is_positive_finite_and_within_root_remainder(self):
        for limit in [0, -1, float('nan'), float('inf'), 291.01, None]:
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                runner.verify_options(options(limit), 291)

    def test_load_sent_only_seven_arguments_no_integer_or_initial_point(self):
        payload = checks.make_relaxation(toy_original())
        path = self.folder/'lp.mat'
        savemat(path, payload, oned_as='column')
        checks.assert_identity(toy_original(), runner.load_sent(path))
        for forbidden in ('intcon', 'x0'):
            with self.subTest(forbidden=forbidden):
                savemat(path, dict(payload, **{forbidden: np.array([1.])}), oned_as='column')
                with self.assertRaisesRegex(ValueError, 'Unexpected native argument'):
                    runner.load_sent(path)

    def test_worker_fractional_primal_is_admitted_without_SAFE_or_certified_bound(self):
        fixture = self.make_worker()
        status, report = self.run_worker(fixture)
        self.assertEqual((status, len(fixture.calls['submits']), fixture.calls['close']), (0, 1, 1))
        self.assertIs(fixture.calls['submits'][0]['budget'], fixture.budget)
        self.assertEqual(report['state'], 'LP_OPTIMUM_SOLVER_REPORTED_ONLY')
        self.assertTrue(report['numeric']['accepted'])
        self.assertEqual(report['numeric']['original_integer_distance'], .5)
        self.assertEqual(report['technical_completion'], 'COMPLETE')
        self.assertTrue(report['lifecycle_complete'])
        self.assertEqual(report['request_attempts'], 1)
        self.assertEqual((report['thermal_integrations'], report['new_SAFE_or_U'],
            report['certified_lower_bound'], report['x0_passed'], report['intcon_passed'],
            report['internal_root_LP_reproduction']), (0, False, False, False, False, False))
        self.assertLess(report['method_elapsed_s'], 300)
        self.assertGreater(report['wall_including_cleanup_s'], report['method_elapsed_s'])
        self.assertEqual(fixture.budget.deadline, fixture.budget.start+300)

    def test_worker_late_response_not_admitted_and_not_retried(self):
        fixture = self.make_worker(seconds=301)
        status, report = self.run_worker(fixture)
        self.assertEqual(status, 2)
        self.assertEqual(report['state'], 'LATE_OR_TIMEOUT_UNRESOLVED')
        self.assertIsNone(report['numeric'])
        self.assertIsNone(report['numeric_admission_completed_s'])
        self.assertEqual((len(fixture.calls['submits']), fixture.calls['close']), (1, 1))

    def test_worker_infeasibility_remains_unresolved_despite_archived_witness(self):
        fixture = self.make_worker(exitflag=-2, x=[])
        status, report = self.run_worker(fixture)
        self.assertEqual(status, 0)
        self.assertEqual(report['state'], 'LP_NUMERICAL_INFEASIBILITY_STATUS_UNRESOLVED')
        self.assertIsNone(report['numeric'])
        self.assertEqual(len(fixture.calls['submits']), 1)

    def test_worker_readback_drift_blocks_numeric_admission(self):
        fixture = self.make_worker(options_drift=True)
        status, report = self.run_worker(fixture)
        self.assertEqual(status, 2)
        self.assertEqual(report['state'], 'TECHNICAL_FAILURE')
        self.assertFalse(report['options_match'])
        self.assertIsNone(report['numeric'])
        self.assertEqual(len(fixture.calls['submits']), 1)

    def test_worker_native_options_guard_error_has_no_solver_entry(self):
        fixture = self.make_worker(native_error=True)
        status, report = self.run_worker(fixture)
        self.assertEqual(status, 2)
        self.assertEqual(report['state'], 'TECHNICAL_FAILURE')
        self.assertFalse(report['result']['linprog_entered'])
        self.assertIsNone(report['numeric'])

    def test_worker_nonfinal_cleanup_cannot_be_technical_success(self):
        fixture = self.make_worker(cleanup_complete=False)
        status, report = self.run_worker(fixture)
        self.assertEqual(status, 2)
        self.assertEqual(report['state'], 'LP_OPTIMUM_SOLVER_REPORTED_ONLY')
        self.assertEqual(report['technical_completion'], 'ERROR_OR_UNRESOLVED')
        self.assertFalse(report['lifecycle_complete'])
        self.assertIn('CLEANUP_UNRESOLVED', [entry['type'] for entry in report['errors']])

    def test_worker_close_exception_preserves_raw_and_stops(self):
        fixture = self.make_worker(close_failure=True)
        status, report = self.run_worker(fixture)
        self.assertEqual(status, 2)
        self.assertIsNotNone(report['result'])
        self.assertEqual(report['technical_completion'], 'ERROR_OR_UNRESOLVED')
        self.assertEqual(fixture.calls['close'], 1)

    def test_worker_constructor_failure_never_submits(self):
        fixture = self.make_worker(constructor_failure=True)
        status, report = self.run_worker(fixture)
        self.assertEqual(status, 2)
        self.assertEqual(report['request_attempts'], 0)
        self.assertEqual(len(fixture.calls['submits']), 0)
        self.assertTrue(report['lifecycle_complete'])

    def test_worker_loaded_payload_hash_drift_stops_before_native_start(self):
        fixture = self.make_worker(loaded_hash_drift=True)
        status, report = self.run_worker(fixture)
        self.assertEqual(status, 2)
        self.assertEqual(report['state'], 'TECHNICAL_FAILURE')
        self.assertEqual(report['request_attempts'], 0)
        self.assertEqual(len(fixture.calls['constructors']), 0)
        self.assertEqual(len(fixture.calls['submits']), 0)
        self.assertIsNone(report['result'])

    def test_worker_method_claim_cannot_be_consumed_twice(self):
        fixture = self.make_worker()
        self.run_worker(fixture)
        original_receipt = (fixture.out/'method_return.json').read_bytes()
        with self.assertRaises(FileExistsError):
            self.run_worker(fixture)
        self.assertEqual(len(fixture.calls['submits']), 1)
        self.assertEqual((fixture.out/'method_return.json').read_bytes(), original_receipt)


if __name__ == '__main__':
    unittest.main(verbosity=2)
