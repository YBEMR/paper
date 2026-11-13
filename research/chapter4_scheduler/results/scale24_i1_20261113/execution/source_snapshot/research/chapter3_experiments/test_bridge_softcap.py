"""Mock transport checks for optional native-only intlinprog MaxTime caps.

No worker, solver, model builder, or thermal evaluator is executed. Request
files and artificial clocks exercise the real Python transport lifecycle.
Run with unittest, for example: python -m unittest test_bridge_softcap.
"""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from scipy.io import loadmat

import matlab_bridge as bridge


HERE = Path(__file__).resolve().parent
MODEL = {'c': [1.], 'Aeq': [[1.]], 'beq': [1.], 'lb': [0.],
         'ub': [1.], 'intcon': [0]}


class Clock:
    def __init__(self):
        self.now = 0.

    def __call__(self):
        return self.now


def fake_session(folder, clock, deadline=10.):
    folder.mkdir()
    session = object.__new__(bridge.MatlabSession)
    session.workdir, session.clock = folder, clock
    session.started, session.deadline = clock(), deadline
    session.budget = SimpleNamespace(deadline=deadline)
    session.closed, session.request_blocked = False, False
    session.counter, session.metadata = 0, {}
    session.proc = SimpleNamespace(poll=lambda: None)
    return session


def reply(*, x=None, exitflag=0):
    return {'status': 'SOLVED', 'x': [1.] if x is None else x,
            'fval': 1., 'exitflag': exitflag,
            'output': {'message': 'fabricated MaxTime return; no solver run'}}


class BridgeSoftCapTests(unittest.TestCase):
    def setUp(self):
        # Refuse accidental native process creation, including future edits.
        self.spawn = patch.object(bridge.subprocess, 'Popen',
                                  side_effect=AssertionError('native process forbidden'))
        self.spawn.start()
        self.addCleanup(self.spawn.stop)
        runtime = HERE.parents[1]/'.runtime'/'bridge_softcap_unit'
        runtime.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=runtime)
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.clock = Clock()
        self.session = fake_session(self.folder/'worker', self.clock)

    def test_no_cap_and_explicit_none_preserve_legacy_publication_and_deadline(self):
        deadlines = []

        def receive(path, deadline, *args, **kwargs):
            deadlines.append(deadline)
            return reply(exitflag=1), {'attempts': 1}

        with patch.object(bridge, '_read_json_until', side_effect=receive):
            first = self.session.solve(MODEL)
            second = self.session.solve(MODEL, solver_max_time_s=None)
        self.assertTrue(first['accepted_for_evaluation'])
        self.assertTrue(second['accepted_for_evaluation'])
        self.assertEqual(deadlines, [10., 10.])
        for index in (1, 2):
            prefix = self.session.workdir/f'request_{index:06d}'
            for suffix in ('.request.json', '.input.json'):
                document = json.loads(prefix.with_suffix(suffix).read_text())
                self.assertFalse(any(key.startswith('solver_max_time') for key in document))
            payload = loadmat(prefix.with_suffix('.mat'))
            self.assertNotIn('solver_max_time_s', payload)
            self.assertNotIn('solver_max_time_s_declared', payload)

    def test_tiny_cap_transfers_without_shortening_response_or_evidence_cutoff(self):
        deadlines = []

        def receive(path, deadline, *args, **kwargs):
            deadlines.append(deadline)
            self.clock.now = 2.  # long after the .001 s native cap, before global deadline
            return reply(), {'attempts': 1}

        with patch.object(bridge, '_read_json_until', side_effect=receive):
            result = self.session.solve(MODEL, solver_max_time_s=.001)
        self.assertEqual(deadlines, [10.])
        self.assertTrue(result['budget_valid'])
        self.assertTrue(result['accepted_for_evaluation'])
        prefix = self.session.workdir/'request_000001'
        request = json.loads(prefix.with_suffix('.request.json').read_text())
        inputs = json.loads(prefix.with_suffix('.input.json').read_text())
        payload = loadmat(prefix.with_suffix('.mat'))
        self.assertEqual(request['remaining_s'], 10.)
        self.assertEqual(request['solver_max_time_s_declared'], .001)
        self.assertEqual(request['solver_max_time_s'], .001)
        self.assertEqual(inputs['absolute_deadline'], 10.)
        self.assertEqual(inputs['solver_max_time_s_declared'], .001)
        self.assertEqual(float(payload['remaining_s'].item()), 10.)
        self.assertEqual(float(payload['solver_max_time_s_declared'].item()), .001)
        self.assertEqual(float(payload['solver_max_time_s'].item()), .001)

    def test_cap_allocation_cannot_exceed_global_remainder(self):
        with patch.object(bridge, '_read_json_until',
                          return_value=(reply(), {'attempts': 1})):
            self.session.solve(MODEL, solver_max_time_s=60)
        request = json.loads((self.session.workdir/'request_000001.request.json').read_text())
        self.assertEqual(request['remaining_s'], 10.)
        self.assertEqual(request['solver_max_time_s_declared'], 60.)
        self.assertEqual(request['solver_max_time_s'], 10.)

    def test_serialization_consumption_updates_request_allocation_not_deadline(self):
        original_save = bridge.savemat
        deadlines = []

        def slow_save(*args, **kwargs):
            original_save(*args, **kwargs)
            self.clock.now = 8.

        def receive(path, deadline, *args, **kwargs):
            deadlines.append(deadline)
            return reply(), {'attempts': 1}

        with patch.object(bridge, 'savemat', side_effect=slow_save), \
                patch.object(bridge, '_read_json_until', side_effect=receive):
            result = self.session.solve(MODEL, solver_max_time_s=7.)
        request = json.loads((self.session.workdir/'request_000001.request.json').read_text())
        self.assertEqual(request['remaining_s'], 2.)
        self.assertEqual(request['solver_max_time_s_declared'], 7.)
        self.assertEqual(request['solver_max_time_s'], 2.)
        self.assertEqual(deadlines, [10.])
        self.assertTrue(result['accepted_for_evaluation'])

    def test_invalid_caps_rejected_before_prepare_publication_or_counter_increment(self):
        for cap in (0, -1, float('inf'), float('-inf'), float('nan'),
                    True, False, np.bool_(True), 1+0j, '1', [], np.array([1.])):
            with self.subTest(cap=repr(cap)), \
                    patch.object(bridge, '_prepare') as prepare, \
                    patch.object(bridge, '_read_json_until') as receive:
                with self.assertRaisesRegex(ValueError, 'solver_max_time_s'):
                    self.session.solve(MODEL, solver_max_time_s=cap)
                prepare.assert_not_called()
                receive.assert_not_called()
                self.assertEqual(self.session.counter, 0)
                self.assertEqual(list(self.session.workdir.iterdir()), [])

    def test_positive_integer_and_numpy_real_caps_are_accepted(self):
        for cap in (1, np.float64(.001), np.int64(2)):
            with self.subTest(cap=repr(cap)), patch.object(
                    bridge, '_read_json_until', return_value=(reply(), {'attempts': 1})):
                result = self.session.solve(MODEL, solver_max_time_s=cap)
                self.assertTrue(result['budget_valid'])

    def test_normal_soft_stop_allows_next_request_and_does_not_inherit_cap(self):
        with patch.object(bridge, '_read_json_until',
                          side_effect=[(reply(x=[]), {'attempts': 1}),
                                       (reply(exitflag=1), {'attempts': 1})]):
            first = self.session.solve(MODEL, solver_max_time_s=.001)
            self.clock.now = 4.
            second = self.session.solve(MODEL)
        self.assertEqual(first['status'], 'SOLVED')
        self.assertEqual(first['exitflag'], 0)
        self.assertFalse(first['accepted_for_evaluation'])
        self.assertFalse(self.session.request_blocked)
        self.assertEqual(second['request_number'], 2)
        self.assertTrue(second['accepted_for_evaluation'])
        self.assertFalse(list(self.session.workdir.glob('*.cancel')))
        request = json.loads((self.session.workdir/'request_000002.request.json').read_text())
        self.assertNotIn('solver_max_time_s', request)
        self.assertEqual(request['remaining_s'], 6.)

    def test_event_consumer_can_still_cancel_current_request(self):
        consumed = []

        def consume(prefix):
            consumed.append(prefix.name)
            prefix.with_suffix('.cancel').write_text('credible violation\n', encoding='ascii')

        def receive(path, deadline, *args, **kwargs):
            self.assertEqual(deadline, 10.)
            self.clock.now = 2.
            kwargs['on_poll']()
            return reply(), {'attempts': 1}

        self.session.event_consumer = consume
        with patch.object(bridge, '_read_json_until', side_effect=receive):
            result = self.session.solve(MODEL, solver_max_time_s=.001)
        self.assertEqual(consumed, ['request_000001'])
        self.assertTrue(result['accepted_for_evaluation'])
        self.assertFalse(self.session.request_blocked)
        self.assertTrue((self.session.workdir/'request_000001.cancel').exists())

    def test_true_total_deadline_timeout_still_blocks_subsequent_request(self):
        def expire(path, deadline, *args, **kwargs):
            self.assertEqual(deadline, 10.)
            self.clock.now = 10.
            raise bridge.PublicationTimeout(path, {'attempts': 1})

        with patch.object(bridge, '_read_json_until', side_effect=expire), \
                patch.object(self.session, 'close') as close:
            result = self.session.solve(MODEL, solver_max_time_s=.001)
            close.assert_not_called()  # method-bound cleanup is caller-owned
        self.assertEqual(result['status'], 'BUDGET_EXHAUSTED')
        self.assertFalse(result['accepted_for_evaluation'])
        self.assertTrue(self.session.request_blocked)
        self.assertTrue((self.session.workdir/'request_000001.cancel').exists())
        with self.assertRaises(RuntimeError):
            self.session.solve(MODEL, solver_max_time_s=.001)

    def test_legacy_remaining_s_keeps_its_shorter_case_deadline(self):
        deadlines = []

        def receive(path, deadline, *args, **kwargs):
            deadlines.append(deadline)
            return reply(), {'attempts': 1}

        with patch.object(bridge, '_read_json_until', side_effect=receive):
            self.session.solve(MODEL, remaining_s=3., solver_max_time_s=.001)
        self.assertEqual(deadlines, [3.])
        request = json.loads((self.session.workdir/'request_000001.request.json').read_text())
        self.assertEqual(request['remaining_s'], 3.)
        self.assertEqual(self.session.deadline, 10.)

    def test_native_allocation_fields_are_preserved_without_claiming_stop_reason(self):
        native = reply()
        native.update({'solver_max_time_s_declared': .001,
                       'solver_max_time_s_allocated': .001,
                       'solver_max_time_s_used': .0007,
                       'solver_max_time_s_scope': 'native_MaxTime_only_not_response_or_evidence_deadline'})
        with patch.object(bridge, '_read_json_until',
                          return_value=(deepcopy(native), {'attempts': 1})):
            result = self.session.solve(MODEL, solver_max_time_s=.001)
        for name in ('solver_max_time_s_declared', 'solver_max_time_s_allocated',
                     'solver_max_time_s_used', 'solver_max_time_s_scope'):
            self.assertEqual(result[name], native[name])
        self.assertNotIn('soft_cap_reached', result)
        self.assertEqual(result['exitflag'], 0)

    def test_late_archive_cannot_use_soft_cap_to_extend_global_evidence_time(self):
        original_json = bridge._json

        def archive(path, value):
            original_json(path, value)
            if path.name.endswith('.python.json'):
                self.clock.now = 10.

        with patch.object(bridge, '_read_json_until',
                          return_value=(reply(), {'attempts': 1})), \
                patch.object(bridge, '_json', side_effect=archive):
            result = self.session.solve(MODEL, solver_max_time_s=.001)
        self.assertEqual(result['status'], 'BUDGET_EXHAUSTED_BEFORE_RETURN')
        self.assertFalse(result['accepted_for_evaluation'])
        self.assertEqual(result['x'], [])


if __name__ == '__main__':
    unittest.main()
