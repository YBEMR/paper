"""Synthetic status-consistency and lifecycle checks; no native solver or heat run.

The six groups cover current-request admission, absent/stale admission, ordinary
returns, rejected input, deadline priority, and both feedback/legacy lifecycles.
Fixtures are fabricated interface receipts, never research evidence.
"""
from contextlib import ExitStack
from copy import deepcopy
from functools import partial
import argparse
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from scipy import sparse

import diagnostic_search as legacy
import formal_milp as formal
import initial_point
import matlab_bridge as bridge
from timing import MethodBudget


HERE = Path(__file__).resolve().parent
CONFLICT = bridge.NUMERICAL_CONSISTENCY_CONFLICT
UNRESOLVED = bridge.NUMERICAL_CONSISTENCY_UNRESOLVED


class Clock:
    def __init__(self):
        self.now = 100.

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def solver_fixture():
    return {'c': np.array([2., 1.]), 'A': sparse.csc_matrix([[1., 1.]]),
            'b': np.array([1.]), 'Aeq': sparse.csc_matrix([[1., 1.]]),
            'beq': np.array([1.]), 'lb': np.zeros(2), 'ub': np.ones(2),
            'intcon': np.array([0, 1])}


def native_reply(*, exitflag=-2, x=None):
    return {'status': 'SOLVED', 'exitflag': exitflag,
            'x': [] if x is None else list(x), 'fval': None,
            'output': {'message': 'synthetic fixture only', 'lowerbound': None},
            'intlinprog_entered': True,
            'initial_point': {'provided': True,
                              'solver_acceptance': 'not_independently_observed'}}


def fake_bridge_session(directory, clock):
    directory.mkdir()
    session = object.__new__(bridge.MatlabSession)
    session.closed = False
    session.request_blocked = False
    session.clock, session.started = clock, clock()
    session.deadline = clock()+10
    session.budget, session.counter = None, 0
    session.workdir, session.metadata, session.proc = directory, {}, None
    return session


class SyntheticTest(unittest.TestCase):
    def setUp(self):
        # A regression that starts MATLAB is a test failure, not a study call.
        self.popen = patch.object(bridge.subprocess, 'Popen',
                                 side_effect=AssertionError('native process forbidden'))
        self.popen.start()
        self.addCleanup(self.popen.stop)


class CurrentRequestTests(SyntheticTest):
    """Group 1: the real preparation in this request is the trigger."""
    def test_admitted_x0_infeasible_keeps_native_and_rejects_returned_candidate(self):
        for vector in ([], [1., 0.]):
            with self.subTest(returned_vector=vector), \
                 tempfile.TemporaryDirectory(dir=HERE) as directory:
                clock = Clock()
                session = fake_bridge_session(Path(directory)/'worker', clock)
                reply = native_reply(x=vector)
                with patch.object(bridge, '_read_json_until',
                                  return_value=(deepcopy(reply), {'attempts': 1})):
                    result = session.solve(solver_fixture(), x0=np.array([1., 0.]))
                self.assertEqual((result['status'], result['exitflag']), ('SOLVED', -2))
                self.assertEqual(result['output'], reply['output'])
                self.assertEqual(result['x'], vector)
                self.assertTrue(result['budget_valid'])
                self.assertFalse(result['accepted_for_evaluation'])
                info = result['numerical_consistency']
                self.assertEqual(info['state'], CONFLICT)
                self.assertEqual(info['request_number'], 1)
                self.assertTrue(info['explicit_x0_in_this_request'])
                self.assertTrue(info['python_x0_admission']['accepted_numerically'])
                self.assertFalse(info['independent_certificate'])
                self.assertFalse(info['thermal_safe_claim'])
                self.assertFalse(info['retry_performed'])
                archived = json.loads((session.workdir/'request_000001.python.json').read_text())
                self.assertEqual(archived['numerical_consistency'], info)

    def test_worker_receipt_is_recorded_but_not_invented_as_solver_acceptance(self):
        for native_initial in ({'provided': False}, {}):
            with self.subTest(native_initial=native_initial), \
                 tempfile.TemporaryDirectory(dir=HERE) as directory:
                session = fake_bridge_session(Path(directory)/'worker', Clock())
                reply = native_reply()
                reply['initial_point'] = native_initial
                with patch.object(bridge, '_read_json_until',
                                  return_value=(reply, {'attempts': 1})):
                    result = session.solve(solver_fixture(), x0=np.array([1., 0.]))
                info = result['numerical_consistency']
                self.assertEqual(info['worker_reported_x0_received'], native_initial.get('provided'))
                self.assertEqual(info['worker_solver_x0_acceptance'], 'not_independently_observed')
                self.assertEqual(info['state'], CONFLICT)


class AbsentOrStaleAdmissionTests(SyntheticTest):
    """Group 2: no x0 or stale worker metadata cannot manufacture a conflict."""
    def test_no_x0_does_not_trust_native_admission_metadata(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            session = fake_bridge_session(Path(directory)/'worker', Clock())
            reply = native_reply()
            reply['initial_point']['accepted_numerically'] = True
            with patch.object(bridge, '_read_json_until',
                              return_value=(reply, {'attempts': 1})):
                result = session.solve(solver_fixture())
            self.assertNotIn('numerical_consistency', result)
            self.assertEqual((result['status'], result['exitflag']), ('SOLVED', -2))

    def test_explicit_two_requests_do_not_inherit_first_admission(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            session = fake_bridge_session(Path(directory)/'worker', Clock())
            replies = [(native_reply(), {'attempts': 1}) for _ in range(2)]
            with patch.object(bridge, '_read_json_until', side_effect=replies) as read:
                first = session.solve(solver_fixture(), x0=np.array([1., 0.]))
                # Caller explicitly makes a second independent request. The
                # production guard never initiates this request or a retry.
                second = session.solve(solver_fixture())
            self.assertEqual(read.call_count, 2)
            self.assertEqual(first['numerical_consistency']['request_number'], 1)
            self.assertNotIn('numerical_consistency', second)
            self.assertEqual(second['request_number'], 2)
            stored = json.loads((session.workdir/'request_000002.input.json').read_text())
            self.assertEqual(stored['initial_point'], {'provided': False})

    def test_admission_is_recomputed_for_changed_current_model(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            session = fake_bridge_session(Path(directory)/'worker', Clock())
            with patch.object(bridge, '_read_json_until',
                              return_value=(native_reply(), {'attempts': 1})) as read:
                first = session.solve(solver_fixture(), x0=np.array([1., 0.]))
                changed = solver_fixture()
                changed['ub'] = np.array([0., 1.])
                with self.assertRaises(bridge.InitialPointRejected):
                    session.solve(changed, x0=np.array([1., 0.]))
            self.assertEqual(first['numerical_consistency']['state'], CONFLICT)
            self.assertEqual(read.call_count, 1)
            self.assertFalse((session.workdir/'request_000002.request.json').exists())


class OrdinaryReturnTests(SyntheticTest):
    """Group 3: ordinary feasible or stopped returns retain their old contract."""
    def test_non_infeasible_exit_with_admitted_x0_keeps_normal_candidate(self):
        for exitflag in (1, 2, 0):
            with self.subTest(exitflag=exitflag), \
                 tempfile.TemporaryDirectory(dir=HERE) as directory:
                session = fake_bridge_session(Path(directory)/'worker', Clock())
                reply = native_reply(exitflag=exitflag, x=[1., 0.])
                with patch.object(bridge, '_read_json_until',
                                  return_value=(reply, {'attempts': 1})):
                    result = session.solve(solver_fixture(), x0=np.array([1., 0.]))
                self.assertNotIn('numerical_consistency', result)
                self.assertTrue(result['accepted_for_evaluation'])
                self.assertEqual(result['x'], [1., 0.])

    def test_non_solved_transport_status_does_not_manufacture_infeasibility_conflict(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            session = fake_bridge_session(Path(directory)/'worker', Clock())
            reply = native_reply()
            reply['status'] = 'ERROR'
            with patch.object(bridge, '_read_json_until',
                              return_value=(reply, {'attempts': 1})):
                result = session.solve(solver_fixture(), x0=np.array([1., 0.]))
            self.assertNotIn('numerical_consistency', result)
            self.assertFalse(result['accepted_for_evaluation'])
            self.assertEqual(result['status'], 'ERROR')


class RejectedInputTests(SyntheticTest):
    """Group 4: current-point rejection precedes publication and all status logic."""
    def test_invalid_current_x0_never_publishes_or_calls_reader(self):
        for point in ([.4, .6], [1., 1.], [float('nan'), 0.]):
            with self.subTest(point=point), tempfile.TemporaryDirectory(dir=HERE) as directory:
                session = fake_bridge_session(Path(directory)/'worker', Clock())
                with patch.object(bridge, '_read_json_until') as read:
                    with self.assertRaises(bridge.InitialPointRejected):
                        session.solve(solver_fixture(), x0=np.array(point))
                read.assert_not_called()
                stored = json.loads((session.workdir/'request_000001.initial.json').read_text())
                self.assertFalse(stored['accepted_numerically'])
                self.assertFalse(stored['independent_certificate'])
                self.assertFalse((session.workdir/'request_000001.request.json').exists())
                self.assertFalse((session.workdir/'request_000001.mat').exists())


class DeadlinePriorityTests(SyntheticTest):
    """Group 5: late returns/archives remain budget failure before guard handling."""
    def test_late_response_cannot_be_evaluated_and_keeps_raw_status_in_diagnostic(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            clock = Clock()
            session = fake_bridge_session(Path(directory)/'worker', clock)
            def late(*args, **kwargs):
                clock.advance(11.)
                return native_reply(x=[1., 0.]), {'attempts': 1}
            with patch.object(bridge, '_read_json_until', side_effect=late):
                result = session.solve(solver_fixture(), x0=np.array([1., 0.]))
            self.assertFalse(result['budget_valid'])
            self.assertFalse(result['accepted_for_evaluation'])
            self.assertEqual(result['status'], 'BUDGET_EXHAUSTED_BEFORE_RETURN')
            self.assertEqual(result['x'], [])
            self.assertEqual(result['numerical_consistency']['solver_reported_status'], 'SOLVED')
            self.assertEqual(result['numerical_consistency']['solver_reported_exitflag'], -2)
            self.assertFalse(result['numerical_consistency']['formed_within_request_budget'])

    def test_archive_crossing_deadline_cannot_turn_timely_reply_into_new_evidence(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            clock = Clock()
            session = fake_bridge_session(Path(directory)/'worker', clock)
            original_json = bridge._json
            crossed = []
            def archive(path, value):
                if path.name.endswith('.python.json') and not crossed:
                    crossed.append(True)
                    clock.advance(11.)
                original_json(path, value)
            with patch.object(bridge, '_read_json_until',
                              return_value=(native_reply(x=[1., 0.]), {'attempts': 1})), \
                 patch.object(bridge, '_json', side_effect=archive):
                result = session.solve(solver_fixture(), x0=np.array([1., 0.]))
            self.assertFalse(result['budget_valid'])
            self.assertFalse(result['accepted_for_evaluation'])
            self.assertEqual(result['status'], 'BUDGET_EXHAUSTED_BEFORE_RETURN')
            self.assertEqual(result['numerical_consistency']['solver_reported_status'], 'SOLVED')
            self.assertEqual(result['numerical_consistency']['solver_reported_exitflag'], -2)
            archived = json.loads((session.workdir/'request_000001.python.json').read_text())
            self.assertFalse(archived['budget_valid'])

    def test_already_expired_request_does_not_run_preparation_or_status_guard(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            clock = Clock()
            session = fake_bridge_session(Path(directory)/'worker', clock)
            clock.advance(11.)
            with patch.object(bridge, '_prepare') as prepare, \
                 patch.object(bridge, '_read_json_until') as read:
                result = session.solve(solver_fixture(), x0=np.array([1., 0.]))
            prepare.assert_not_called()
            read.assert_not_called()
            self.assertNotIn('numerical_consistency', result)
            self.assertEqual(result['status'], 'BUDGET_EXHAUSTED')


class TinyModel:
    def __init__(self, budget):
        self.instance = {'id': 'synthetic_status_consistency'}
        self.budget = budget

    def as_solver_dict(self):
        return solver_fixture()


def safe_receipt():
    return {'candidate': {'scenes': {}}, 'evaluation': {
        'state': 'SAFE', 'rankable_energy': True, 'safe_upper_bound_J': '2',
        'weighted_energy_J': ['1.9', '2'], 'completed_at_elapsed_s': .1}}


def initial_preparation():
    receipt = safe_receipt()
    receipt['schedule_completed_at_s'] = .05
    return {'state': 'SAFE_POINT_READY', 'reason': 'INITIAL_POINT_READY',
            'witness': receipt, 'x0': np.array([1., 0.]), 'attempts': [],
            'completion': {'state': 'INITIAL_POINT_READY', 'decoded_roundtrip': True,
                'completed_at_s': .2,
                'numerical_acceptance': {'accepted_numerically': True}}}


class LifecycleTests(SyntheticTest):
    """Group 6: no retry, cut, return-candidate evaluation or loss of existing SAFE."""
    def invoke(self, route, *, existing=None, use_initial=False,
               invalid_budget=False, expire_clock=False, no_x0=False):
        clock = Clock()
        budget = MethodBudget(10, clock=clock)
        model = TinyModel(budget)
        calls, assessments = [], []

        class Recorder:
            def __init__(inner, *args):
                inner.best = deepcopy(existing)
            def poll(inner, prefix):
                pass
            def assess(inner, *args):
                assessments.append(args)
                raise AssertionError('conflicting returned candidate must not be evaluated')
            def summary(inner):
                return {'fixture': True, 'evaluations': [], 'first_safe_receipt_s': None}

        class Session:
            workdir = Path('unused')/'matlab'
            event_consumer = None
            def solve(inner, payload, **kwargs):
                calls.append(kwargs)
                point = kwargs.get('x0')
                # The direct loop fixture explicitly injects a current point;
                # the real initial-witness wrapper injects it in lifecycle tests.
                if not use_initial and not no_x0:
                    point = np.array([1., 0.])
                prepared = bridge._prepare(payload, x0=point)
                reply = native_reply(x=[1., 0.] if not no_x0 else [])
                reply.update(budget_valid=not invalid_budget, accepted_for_evaluation=False)
                info = bridge._initial_point_status_conflict(
                    prepared.get('x0_validation', {'provided': False}), reply,
                    explicit_x0=point is not None, request_number=len(calls),
                    within_budget=not invalid_budget)
                if info is not None:
                    reply['numerical_consistency'] = info
                if expire_clock:
                    clock.advance(11.)
                return reply

        session = Session()
        module = legacy if route == 'legacy' else formal
        diagnostic = (legacy.solve_diagnostic if route == 'legacy' else
                      partial(formal.solve_formal_diagnostic, feedback_kind=route))
        with ExitStack() as stack:
            stack.enter_context(patch.object(module, 'Recorder', Recorder))
            feedback = stack.enter_context(patch.object(module, 'add_thermal_feedback'))
            assignment = stack.enter_context(patch.object(formal, 'add_assignment_feedback'))
            checked = stack.enter_context(patch.object(formal, '_checked_thermal_witnesses'))
            if use_initial:
                stack.enter_context(patch.object(initial_point, 'prepare_initial_witness',
                                               return_value=initial_preparation()))
                output = initial_point.solve_with_initial_witness(
                    model, session, {}, budget, diagnostic_solver=diagnostic)
            else:
                output = diagnostic(model, session, {}, budget)
            feedback.assert_not_called()
            assignment.assert_not_called()
            checked.assert_not_called()
        self.assertEqual(len(calls), 1)
        self.assertEqual(assessments, [])
        self.assertIsNone(session.event_consumer)
        self.assertEqual(output['feedback'], [])
        self.assertEqual(output['remaining_domain'], 'retained')
        self.assertFalse(output['independently_proven_optimal'])
        self.assertFalse(output['independently_proven_infeasible'])
        self.assertEqual(output['rounds'][0]['status'], 'SOLVED')
        self.assertEqual(output['rounds'][0]['exitflag'], -2)
        return output, calls

    def test_both_feedback_variants_and_legacy_stop_before_nonempty_x_decode(self):
        for route in ('conditional', 'assignment', 'legacy'):
            with self.subTest(route=route):
                result, _ = self.invoke(route)
                self.assertEqual(result['state'], 'UNRESOLVED')
                self.assertEqual(result['reason'], UNRESOLVED)
                self.assertEqual(result['numerical_consistency']['state'], CONFLICT)
                self.assertIsNone(result['safe_upper_bound_J'])

    def test_existing_callback_safe_survives_conflicting_final_return(self):
        for route in ('conditional', 'assignment', 'legacy'):
            with self.subTest(route=route):
                receipt = safe_receipt()
                result, _ = self.invoke(route, existing=receipt)
                self.assertEqual(result['state'], 'SAFE')
                self.assertEqual(result['reason'], UNRESOLVED)
                self.assertEqual(result['evaluation'], receipt['evaluation'])
                self.assertEqual(result['safe_upper_bound_J'], '2')

    def test_initial_safe_and_attribution_survive_for_both_feedback_lifecycles(self):
        for route in ('conditional', 'assignment', 'legacy'):
            with self.subTest(route=route):
                result, calls = self.invoke(route, use_initial=True)
                self.assertIn('x0', calls[0])
                self.assertTrue(np.array_equal(calls[0]['x0'], np.array([1., 0.])))
                self.assertEqual(result['state'], 'SAFE')
                self.assertEqual(result['reason'], UNRESOLVED)
                self.assertEqual(result['safe_upper_bound_J'], '2')
                self.assertEqual(result['initial_safe_upper_bound_J'], '2')
                self.assertEqual(result['first_initial_safe_s'], .1)
                self.assertEqual(result['safe_solution_source'], 'initial_constructor')
                self.assertIsNone(result['milp_safe_upper_bound_J'])
                self.assertFalse(result['milp_improved_initial_upper_bound'])
                self.assertFalse(result['strict_energy_improvement_certified'])
                self.assertEqual(result['solver_diagnostic']['reason'], UNRESOLVED)

    def test_invalid_budget_has_priority_and_preserves_seed_without_new_solver_evidence(self):
        for route in ('conditional', 'assignment', 'legacy'):
            with self.subTest(route=route):
                result, _ = self.invoke(route, use_initial=True, invalid_budget=True)
                self.assertEqual(result['reason'], 'SOLVER_RETURN_AFTER_BUDGET')
                self.assertNotIn('numerical_consistency', result)
                self.assertEqual(result['state'], 'SAFE')
                self.assertIsNone(result['milp_safe_upper_bound_J'])
                self.assertFalse(result['rounds'][0]['budget_valid'])

    def test_expired_wall_clock_has_priority_and_preserves_seed(self):
        for route in ('conditional', 'assignment', 'legacy'):
            with self.subTest(route=route):
                result, _ = self.invoke(route, use_initial=True, expire_clock=True)
                self.assertEqual(result['reason'], 'wall_time_limit')
                self.assertNotIn('numerical_consistency', result)
                self.assertEqual(result['state'], 'SAFE')
                self.assertIsNone(result['milp_safe_upper_bound_J'])
                self.assertEqual(result['rounds'][0]['numerical_consistency']['state'], CONFLICT)

    def test_without_current_admission_infeasible_remains_solver_reported(self):
        for route in ('conditional', 'assignment', 'legacy'):
            with self.subTest(route=route):
                result, _ = self.invoke(route, no_x0=True)
                self.assertEqual(result['reason'], 'SOLVER_REPORTED_INFEASIBLE')
                self.assertNotIn('numerical_consistency', result)
                self.assertNotIn('numerical_consistency', result['rounds'][0])


def run(out):
    out.mkdir(parents=True, exist_ok=False)
    sources = [HERE/name for name in ('matlab_bridge.py', 'formal_milp.py',
                                      'diagnostic_search.py', Path(__file__).name)]
    before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    snapshot = out/'source_snapshot'
    snapshot.mkdir()
    for path in sources:
        (snapshot/path.name).write_bytes(path.read_bytes())
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromModule(__import__(__name__))
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    (out/'unit_checks.txt').write_text(stream.getvalue(), encoding='utf-8')
    after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    receipt = {'passed': result.wasSuccessful() and before == after,
               'count': result.testsRun, 'failures': len(result.failures),
               'errors': len(result.errors), 'skipped': len(result.skipped),
               'source_sha256': before, 'source_after_sha256': after,
               'source_unchanged_during_checks': before == after,
               'groups': ['current_request_admission', 'absent_or_stale_admission',
                          'ordinary_solver_return', 'rejected_input',
                          'deadline_priority', 'feedback_and_initial_safe_lifecycles'],
               'native_solver_calls': 0, 'research_calls': 0,
               'thermal_evaluations': 0,
               'scope': 'synthetic interface checks only; no new native infeasibility diagnosis'}
    (out/'checks.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    print(stream.getvalue())
    print(json.dumps({k: receipt[k] for k in ('passed', 'count', 'failures', 'errors')}))
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path)
    args, remaining = parser.parse_known_args()
    if args.out is None:
        unittest.main(argv=[__file__, *remaining])
    else:
        if remaining:
            parser.error('Unexpected arguments: '+' '.join(remaining))
        raise SystemExit(0 if run(args.out)['passed'] else 1)
