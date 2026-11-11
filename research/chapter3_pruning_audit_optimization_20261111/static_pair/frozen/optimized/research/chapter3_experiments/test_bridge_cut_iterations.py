"""Optional CutMaxIterations transport checks; no MATLAB or optimization.

A single tiny finite numerical matrix is reused for both settings. The tests
publish actual bridge MAT/JSON files and supply fabricated native replies.
They do not construct a scheduling model or evaluate a thermal trajectory.
"""
from fractions import Fraction
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from scipy import sparse
from scipy.io import loadmat

from initial_point import _InitialSession
import matlab_bridge as bridge
from test_bridge_softcap import Clock, fake_session, reply


HERE = Path(__file__).resolve().parent
MODEL = {'c': np.array([2., 1.]), 'A': sparse.csr_matrix([[1., -1.]]),
         'b': np.array([1.]), 'Aeq': sparse.csr_matrix([[1., 1.]]),
         'beq': np.array([1.]), 'lb': np.zeros(2), 'ub': np.ones(2),
         'intcon': np.array([0, 1])}
X0 = np.array([1., 0.])


def native_reply(limit=None):
    result = reply(x=[1., 0.], exitflag=1)
    result['fval'] = 2.
    if limit is not None:
        result.update(cut_max_iterations_declared=limit,
            cut_max_iterations_actual_effective=limit,
            options={'CutMaxIterations': limit, 'CutGeneration': 'basic',
                     'LPPreprocess': 'none', 'IntegerPreprocess': 'none'})
    return result


def dense(value):
    return value.toarray() if sparse.issparse(value) else np.asarray(value)


class BridgeCutIterationTests(unittest.TestCase):
    def setUp(self):
        self.no_native = patch.object(bridge.subprocess, 'Popen',
            side_effect=AssertionError('Unmocked native process creation is forbidden'))
        self.no_native.start(); self.addCleanup(self.no_native.stop)
        home = HERE.parents[1]/'.runtime/bridge_cut_iterations_unit'
        home.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix='unit_', dir=home)
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.clock = Clock()

    def test_only_mathematical_integers_in_supported_range_are_accepted(self):
        for value in (1, 10, 50, 10.0, np.int64(10), np.float64(1.0), Fraction(10, 1)):
            with self.subTest(value=value):
                normalized = bridge._cut_iteration_limit(value)
                self.assertIs(type(normalized), int)
                self.assertEqual(normalized, int(value))
        self.assertIsNone(bridge._cut_iteration_limit(None))

    def test_invalid_constructor_option_is_rejected_before_workdir_or_spawn(self):
        invalid = (True, False, np.bool_(True), float('nan'), float('inf'),
                   -float('inf'), 1.5, np.float64(10.1), 0, 51, -1, '10', 1+0j,
                   [10], np.array(10), 10**1000, Fraction(10**100+1, 10**100))
        for index, value in enumerate(invalid):
            with self.subTest(value=repr(value)):
                target = self.folder/('invalid_'+str(index))
                with self.assertRaisesRegex(ValueError, 'cut_max_iterations'):
                    bridge.MatlabSession(target, clock=self.clock, cut_max_iterations=value)
                self.assertFalse(target.exists())

    def test_constructor_records_normalized_declaration_without_real_process(self):
        process = SimpleNamespace(pid=12345, wait=lambda timeout=None: 0, poll=lambda: 0)
        with patch.object(bridge.subprocess, 'Popen', return_value=process), \
             patch.object(bridge, '_read_json_until', return_value=(
                 {'status': 'READY', 'release': '2023b'}, {'attempts': 1})):
            session = bridge.MatlabSession(self.folder/'constructor', total_budget_s=10,
                clock=self.clock, cut_max_iterations=np.float64(10))
        try:
            self.assertIs(type(session.cut_max_iterations), int)
            self.assertEqual(session.cut_max_iterations, 10)
            self.assertEqual(session.metadata['cut_max_iterations_declared'], 10)
            archived = json.loads((session.workdir/'session.json').read_text())
            self.assertEqual(archived['cut_max_iterations_declared'], 10)
            self.assertEqual(archived['engineering_compatibility']['LPPreprocess'], 'none')
            self.assertEqual(session.deadline, 10)
        finally:
            session.close()

    def test_absent_and_none_declaration_leave_legacy_publications_unchanged(self):
        sessions = [fake_session(self.folder/'legacy_absent', self.clock),
                    fake_session(self.folder/'legacy_none', self.clock)]
        sessions[1].cut_max_iterations = None
        documents = []
        for session in sessions:
            with patch.object(bridge, '_read_json_until', return_value=(native_reply(), {'attempts': 1})):
                result = session.solve(MODEL, x0=X0)
            self.assertTrue(result['accepted_for_evaluation'])
            self.assertNotIn('cut_max_iterations_actual_effective', result)
            prefix = session.workdir/'request_000001'
            request = json.loads(prefix.with_suffix('.request.json').read_text())
            inputs = json.loads(prefix.with_suffix('.input.json').read_text())
            payload = loadmat(prefix.with_suffix('.mat'))
            for document in (request, inputs, payload):
                self.assertFalse(any(key.startswith('cut_max_iterations') for key in document))
            documents.append((request, inputs))
        self.assertEqual(documents[0], documents[1])

    def test_10_and_1_export_identical_model_x0_and_global_deadline(self):
        exports, request_docs, input_docs, deadlines = [], [], [], []
        for limit in (10, 1):
            session = fake_session(self.folder/('cut_'+str(limit)), self.clock)
            session.cut_max_iterations = limit
            def receive(path, deadline, *args, limit=limit, **kwargs):
                deadlines.append(deadline)
                return native_reply(limit), {'attempts': 1}
            with patch.object(bridge, '_read_json_until', side_effect=receive):
                result = session.solve(MODEL, x0=X0, solver_max_time_s=.5)
            self.assertTrue(result['accepted_for_evaluation'])
            self.assertEqual(result['cut_max_iterations_actual_effective'], limit)
            prefix = session.workdir/'request_000001'
            payload = loadmat(prefix.with_suffix('.mat'))
            self.assertEqual(payload['cut_max_iterations'].item(), limit)
            exports.append(payload)
            request = json.loads(prefix.with_suffix('.request.json').read_text())
            declared = request.pop('cut_max_iterations')
            self.assertIs(type(declared), int)
            self.assertEqual(declared, limit)
            request_docs.append(request)
            inputs = json.loads(prefix.with_suffix('.input.json').read_text())
            self.assertEqual(inputs.pop('cut_max_iterations_declared'), limit)
            input_docs.append(inputs)
        self.assertEqual(deadlines, [10., 10.])
        self.assertEqual(request_docs[0], request_docs[1])
        self.assertEqual(input_docs[0], input_docs[1])
        for field in ('c', 'A', 'b', 'Aeq', 'beq', 'lb', 'ub', 'intcon', 'x0',
                      'remaining_s', 'solver_max_time_s', 'solver_max_time_s_declared'):
            self.assertTrue(np.array_equal(dense(exports[0][field]), dense(exports[1][field])), field)
        first_keys = {key for key in exports[0] if not key.startswith('__')}
        second_keys = {key for key in exports[1] if not key.startswith('__')}
        self.assertEqual(first_keys, second_keys)

    def test_same_session_multi_round_setting_and_initial_session_x0_once(self):
        session = fake_session(self.folder/'rounds', self.clock)
        session.cut_max_iterations = 1
        wrapped = _InitialSession(session, X0)
        deadlines = []
        def receive(path, deadline, *args, **kwargs):
            deadlines.append(deadline)
            return native_reply(1), {'attempts': 1}
        with patch.object(bridge, '_read_json_until', side_effect=receive):
            for _ in range(3):
                result = wrapped.solve(MODEL, remaining_s=10, budget=session.budget,
                                       solver_max_time_s=.5)
                self.assertEqual(result['cut_max_iterations_actual_effective'], 1)
        self.assertEqual(session.counter, 3)
        self.assertEqual(deadlines, [10., 10., 10.])
        self.assertFalse(session.request_blocked)
        for number in range(1, 4):
            prefix = session.workdir/f'request_{number:06d}'
            request = json.loads(prefix.with_suffix('.request.json').read_text())
            payload = loadmat(prefix.with_suffix('.mat'))
            self.assertEqual(request['cut_max_iterations'], 1)
            self.assertEqual(payload['cut_max_iterations'].item(), 1)
            self.assertEqual('x0' in payload, number == 1)

    def test_native_actual_effective_value_is_preserved_not_fabricated(self):
        session = fake_session(self.folder/'native_fields', self.clock)
        session.cut_max_iterations = 1
        with patch.object(bridge, '_read_json_until', return_value=(native_reply(1), {'attempts': 1})):
            result = session.solve(MODEL)
        self.assertEqual(result['cut_max_iterations_declared'], 1)
        self.assertEqual(result['cut_max_iterations_actual_effective'], 1)
        self.assertEqual(result['options']['CutGeneration'], 'basic')
        self.assertEqual(result['options']['LPPreprocess'], 'none')
        with patch.object(bridge, '_read_json_until', return_value=(native_reply(), {'attempts': 1})):
            absent = session.solve(MODEL)
        self.assertNotIn('cut_max_iterations_actual_effective', absent)

    def test_invalid_mutated_session_setting_cannot_publish_or_increment_request(self):
        session = fake_session(self.folder/'mutated', self.clock)
        session.cut_max_iterations = 1.5
        with self.assertRaisesRegex(ValueError, 'cut_max_iterations'):
            session.solve(MODEL)
        self.assertEqual(session.counter, 0)
        self.assertEqual(list(session.workdir.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
