"""Shared-clock/search-slice checks using K113 mock fixtures and real polling.

No model construction, thermal propagation, MATLAB or optimizer is used.
All SAFE/violation values below are synthetic control-flow receipts.
"""
from copy import deepcopy
import gc
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import weakref

from initial_point import _InitialSession
from partial_bounds import get_deployment_bounds
import partial_method as method
from test_partial_method import Harness, Clock, candidate, fixture_for_units, REPO
from timing import MethodBudget


class SimpleRecorder:
    def __init__(self, evaluations=None, best=None):
        self.pending = None
        self.best = best
        self.evaluations = list(evaluations or [])
    def begin_request(self):
        self.pending = None
    def poll(self, prefix):
        pass
    def assess(self, vector, source):
        evaluation = self.evaluations.pop(0)
        if evaluation.get('state') == 'SAFE':
            self.best = {'candidate': {}, 'evaluation': evaluation}
        return {}, evaluation
    def summary(self):
        return {'mock': True}


def solve_fixture(*, slice_s=10, export_cost=2, replies=None, failure=False,
                  evaluations=None, seconds=900, x0=False, best=None):
    clock = Clock(); budget = MethodBudget(seconds, clock=clock)
    calls = []; sequence = list(replies or [
        {'cost': 3, 'x': [1], 'exitflag': 0}, {'cost': 2, 'x': [], 'exitflag': 0}])
    def export():
        clock.tick(export_cost)
        return {'mock_matrix': True}
    model = SimpleNamespace(as_solver_dict=export)
    class Session:
        event_consumer = None
        workdir = Path('unused_mock_matlab')
        closed = request_blocked = False
        def solve(self, payload, **kwargs):
            calls.append(kwargs)
            if failure:
                raise RuntimeError('MOCK_UNSETTLED_WORKER')
            item = sequence.pop(0); clock.tick(item['cost'])
            return {'status': 'SOLVED', 'budget_valid': budget.remaining > 0,
                'x': item['x'], 'exitflag': item['exitflag'],
                'accepted_for_evaluation': bool(item['x']) and budget.remaining > 0}
    raw = Session(); session = _InitialSession(raw, [0]) if x0 else raw
    recorder = SimpleRecorder(evaluations or [{'state': 'THERMAL_VIOLATION'}], best)
    def feedback(*args):
        clock.tick(1)
        return {'rows_added': 1}
    result = method._solve_scene(model, session, {}, budget, recorder,
        feedback_adder=feedback, witness_validator=lambda *args: [True],
        max_rounds=50, scene_slice_s=slice_s)
    return result, calls, budget, raw


class PartialSliceLoopTests(unittest.TestCase):
    def test_fixed_slice_counts_export_and_feedback_and_does_not_reset_x0(self):
        result, calls, budget, raw = solve_fixture(x0=True)
        self.assertEqual(result['reason'], 'SCENE_SLICE_COMPLETE', result)
        self.assertEqual([call['solver_max_time_s'] for call in calls], [8, 2])
        self.assertEqual(len(result['feedback']), 1)
        self.assertIn('x0', calls[0]); self.assertNotIn('x0', calls[1])
        self.assertTrue(all(call['remaining_s'] > call['solver_max_time_s'] for call in calls))
        self.assertTrue(all(call['budget'] is budget for call in calls))
        self.assertEqual(budget.deadline, 900)
        self.assertEqual(budget.elapsed, 10)
        self.assertTrue(result['request_settled'])
        self.assertTrue(result['worker_reusable'])
        self.assertIsNone(raw.event_consumer)

    def test_export_consuming_slice_cannot_submit_native_request(self):
        result, calls, budget, _ = solve_fixture(export_cost=11)
        self.assertEqual(result['reason'], 'SCENE_SLICE_COMPLETE')
        self.assertEqual(calls, [])
        self.assertEqual(budget.remaining, 889)
        self.assertTrue(result['worker_reusable'])

    def test_violation_return_at_slice_end_is_retained_without_useless_feedback(self):
        result, calls, budget, _ = solve_fixture(
            replies=[{'cost': 8, 'x': [1], 'exitflag': -1}])
        self.assertEqual(result['reason'], 'SCENE_SLICE_COMPLETE')
        self.assertEqual(result['evaluation']['state'], 'THERMAL_VIOLATION')
        self.assertEqual(result['feedback'], [])
        self.assertEqual(len(calls), 1)
        self.assertEqual(budget.elapsed, 10)
        self.assertTrue(result['request_settled'])
        self.assertTrue(result['worker_reusable'])

    def test_unsliced_default_keeps_old_solve_arguments(self):
        safe = {'state': 'SAFE', 'rankable_energy': True,
                'safe_upper_bound_J': '2', 'completed_at_elapsed_s': 1}
        result, calls, _, _ = solve_fixture(slice_s=None,
            replies=[{'cost': 1, 'x': [1], 'exitflag': 1}], evaluations=[safe])
        self.assertEqual(result['state'], 'SAFE')
        self.assertEqual(result['reason'], 'SAFE_ENGINEERING_CONVERGENCE')
        self.assertNotIn('solver_max_time_s', calls[0])
        self.assertNotIn('scene_slice_s', result)

    def test_unsettled_worker_keeps_previous_safe_but_cannot_be_reused(self):
        best = {'candidate': {}, 'evaluation': {'safe_upper_bound_J': '2'}}
        result, calls, _, raw = solve_fixture(failure=True, best=best)
        self.assertEqual(result['state'], 'SAFE')
        self.assertEqual(result['safe_upper_bound_J'], '2')
        self.assertEqual(result['reason'], 'INTERFACE_ERROR')
        self.assertFalse(result['request_settled'])
        self.assertFalse(result['worker_reusable'])
        self.assertEqual(len(calls), 1)
        self.assertIsNone(raw.event_consumer)

    def test_global_expiry_is_not_a_normal_slice_yield(self):
        result, calls, budget, _ = solve_fixture(seconds=5,
            replies=[{'cost': 4, 'x': [], 'exitflag': 0}])
        self.assertEqual(result['reason'], 'wall_time_limit')
        self.assertFalse(result['request_settled'])
        self.assertFalse(result['worker_reusable'])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['solver_max_time_s'], 3)
        self.assertEqual(budget.deadline, 5)


class PartialSharedContextTests(unittest.TestCase):
    def setUp(self):
        self.home = (REPO/'.runtime/partial_slice_unit').resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='unit_', dir=self.home)
        self.path = Path(self.temp.name).resolve(); self.path.relative_to(self.home)
    def tearDown(self):
        self.path.relative_to(self.home)
        self.temp.cleanup()

    def run_harness(self, h, path, *, budget, session_factory=None, **kwargs):
        return method.execute_shared_deployment(h.loader, path,
            shared_deployment={'A.pre': 'CPU1'}, clock=h.clock, budget=budget,
            close_session=False, model_builder=h.builder,
            session_factory=session_factory or h.session_factory,
            initial_preparer=h.initial, model_evaluator=h.evaluator,
            scene_evaluator=h.scene_evaluator, aggregator=h.aggregator,
            recorder_factory=h.recorder, feedback_adder=h.feedback, **kwargs)

    def test_shared_budget_lazy_single_worker_request_deltas_and_live_observer(self):
        h = Harness(); budget = MethodBudget(900, clock=h.clock)
        h.clock.tick(7)
        _, instance = fixture_for_units()
        bounds = get_deployment_bounds(instance, {'A.pre': 'CPU1'}, budget)
        singleton = []; seen = []; native_options = []
        def factory(path, **kwargs):
            self.assertIs(kwargs['budget'], budget)
            if not singleton:
                session = h.session_factory(path, **kwargs)
                original = session.solve
                def solve(payload, **options):
                    native_options.append(options.copy())
                    return original(payload, **options)
                session.solve = solve
                singleton.append(session)
            return singleton[0]
        def observer(result, update):
            self.assertEqual(result['state'], 'SAFE')
            self.assertEqual(result['aggregation']['safe_upper_bound_J'], update['safe_upper_bound_J'])
            self.assertIsNotNone(result['initial_global_safe_upper_bound_J'])
            seen.append((result['safe_upper_bound_J'], len(h.sessions), h.inside, budget.elapsed))
        first = self.run_harness(h, self.path/'a0', budget=budget,
            session_factory=factory, scene_slice_s=60, on_global_update=observer, bounds_receipt=bounds)
        second = self.run_harness(h, self.path/'a1', budget=budget,
            session_factory=factory, scene_slice_s=60, on_global_update=observer, bounds_receipt=bounds)
        self.assertEqual(first['state'], 'SAFE', first)
        self.assertEqual(second['state'], 'SAFE', second)
        self.assertEqual(len(h.sessions), 1)
        self.assertEqual(first['solver_request_attempts'], 2)
        self.assertEqual(second['solver_request_attempts'], 2)
        self.assertEqual(second['session_total_request_count'], 4)
        self.assertFalse(any(item[0] == 'closed' for item in h.trace))
        self.assertEqual(seen[0][1], 0, 'initial U must be observable before lazy worker startup')
        self.assertTrue(any(item[2] for item in seen), 'callback U must be observable before solve returns')
        self.assertEqual(len(set(h.budgets)), 1)
        self.assertTrue(all(item['budget'] is budget for item in native_options))
        self.assertTrue(all(0 < item['solver_max_time_s'] <= 60 < item['remaining_s']
                            for item in native_options))
        self.assertEqual(budget.deadline, 900)
        for result in (first, second):
            self.assertEqual(result['timing']['limit_s'], 900)
            self.assertTrue(result['worker_reusable'])
            self.assertTrue(result['event_consumer_detached'])
            self.assertFalse(result['session_closed_by_partial'])
            self.assertEqual(result['timing']['cleanup_s'], 0)
            self.assertNotIn('models', result)

    def test_slice_poll_cancels_but_still_admits_timely_global_budget_callback(self):
        h = Harness(); budget = MethodBudget(900, clock=h.clock)
        config, instance = fixture_for_units()
        sid = instance['scenarios'][0]['id']
        model = h.builder(instance, config, budget=budget, fixed_scene_id=sid,
                          fixed_shared_deployment={'A.pre': 'CPU1'})
        evaluations, safes = [], []
        recorder = method.PartialRecorder(model, config['accuracy_targets'], budget, self.path,
            model_evaluator=h.evaluator, decoder=lambda m, x: candidate(m, x[0]),
            on_evaluation=lambda c, e, s: evaluations.append(e),
            on_safe=lambda c, e, s: safes.append(e))
        recorder.slice_end = h.clock()+1
        h.clock.tick(1)
        prefix = self.path/'request_000001'
        Path(str(prefix)+'.event_000001.json').write_text(
            json.dumps({'kind': 'incumbent', 'x': [1], 'values': {}}), encoding='utf-8')
        recorder.poll(prefix)
        self.assertTrue(prefix.with_suffix('.cancel').exists())
        self.assertEqual(recorder.cancel_requests[0]['reason'], 'SCENE_SLICE_END')
        self.assertEqual(len(evaluations), 1)
        self.assertEqual(len(safes), 1)
        self.assertLess(safes[0]['completed_at_elapsed_s'], budget.seconds)
        self.assertIsNotNone(recorder.best)
        self.assertEqual(budget.deadline, 900)

    def test_supplied_bound_scope_input_condition_and_time_are_checked(self):
        for name in ('scope', 'input', 'deployment', 'time'):
            with self.subTest(mutation=name):
                h = Harness(); budget = MethodBudget(900, clock=h.clock)
                _, instance = fixture_for_units()
                bounds = deepcopy(get_deployment_bounds(instance, {'A.pre': 'CPU1'}, budget))
                if name == 'scope': bounds['L0']['scope'] = 'fixed_shared_deployment'
                if name == 'input': bounds['L0']['input_sha256'] = 'wrong'
                if name == 'deployment': bounds['L_a']['shared_deployment'] = {'A.pre': 'CPU2'}
                if name == 'time': bounds['L_a']['formed_at_s'] = 901
                result = self.run_harness(h, self.path/name, budget=budget, bounds_receipt=bounds)
                self.assertEqual(result['reason'], 'INVALID_INPUT_OR_INTERFACE', result)
                self.assertFalse(h.models)
                self.assertFalse(h.sessions)
                self.assertIsNone(result['safe_upper_bound_J'])

    def test_observer_exception_retains_committed_a_safe_and_stops_before_worker(self):
        h = Harness(); budget = MethodBudget(900, clock=h.clock)
        seen = []
        def observer(result, update):
            seen.append(update['safe_upper_bound_J'])
            raise RuntimeError('MOCK_OBSERVER_FAILURE')
        result = self.run_harness(h, self.path/'observer_error', budget=budget,
                                  scene_slice_s=60, on_global_update=observer)
        self.assertEqual(result['state'], 'SAFE')
        self.assertTrue(seen)
        self.assertEqual(result['reason'], 'INTERFACE_ERROR')
        self.assertFalse(result['worker_reusable'])
        self.assertFalse(h.sessions)
        self.assertIn('observer_error', result['global_updates'][-1])

    def test_invalid_slice_is_rejected_before_input_or_directory_creation(self):
        for index, value in enumerate((0, -1, float('inf'), float('nan'), True, '60')):
            h = Harness(); budget = MethodBudget(900, clock=h.clock)
            out = self.path/('invalid_'+str(index))
            with self.assertRaises(ValueError):
                self.run_harness(h, out, budget=budget, scene_slice_s=value)
            self.assertIsNone(h.primary_budget)
            self.assertFalse(out.exists())

    def test_recorder_detaches_model_and_captured_callbacks_without_cyclic_gc(self):
        clock = Clock(); budget = MethodBudget(900, clock=clock)
        class Model:
            instance = {'id': 'fixture_recorder_release'}
            def as_solver_dict(self):
                clock.tick(2)
                return {'mock_matrix': True}
        def invoke():
            model = Model()
            # Real Model/BuildObserver also retain one another. The method
            # detaches this edge only after storing construction observations.
            observer = SimpleNamespace(model=model)
            model.progress = observer
            def evaluate(*args, captured=model):
                return captured
            def on_evaluation(*args, captured=model):
                return captured
            def on_safe(*args, captured=model):
                return captured
            def decoder(*args, captured=model):
                return captured
            def validator(*args, captured=model):
                return captured
            refs = [weakref.ref(callback) for callback in
                    (evaluate, on_evaluation, on_safe, decoder, validator)]
            model_ref = weakref.ref(model)
            recorder = method.PartialRecorder(model, {}, budget, self.path,
                model_evaluator=evaluate, on_evaluation=on_evaluation,
                on_safe=on_safe, decoder=decoder, witness_validator=validator)
            # Keep an actual best receipt to check release cannot erase the
            # already formed result while dropping search-only references.
            recorder.best = {'candidate': {'scenes': {}}, 'evaluation': {
                'state': 'SAFE', 'safe_upper_bound_J': '2'}}
            recorder.evaluations = [{'scope': 'synthetic receipt, no physics'}]
            session = SimpleNamespace(event_consumer=None, closed=False, request_blocked=False)
            result = method._solve_scene(model, session, {}, budget, recorder,
                feedback_adder=lambda *args: {'rows_added': 0},
                witness_validator=validator, max_rounds=50, scene_slice_s=1)
            method._detach_observer(observer)
            return model_ref, refs, result, recorder, observer
        was_enabled = gc.isenabled()
        gc.disable()
        try:
            model_ref, callback_refs, result, recorder, observer = invoke()
            self.assertIsNone(model_ref(), 'model must not wait for cyclic GC')
            self.assertIsNone(observer.model)
            self.assertTrue(all(reference() is None for reference in callback_refs))
            for name in ('model', 'model_evaluator', 'on_safe', 'on_evaluation',
                         'evaluator', 'decoder', 'witness_validator'):
                self.assertIsNone(getattr(recorder, name))
            self.assertEqual(result['state'], 'SAFE')
            self.assertEqual(result['safe_upper_bound_J'], '2')
            self.assertEqual(result['diagnostic']['evaluations'],
                             [{'scope': 'synthetic receipt, no physics'}])
        finally:
            if was_enabled:
                gc.enable()


if __name__ == '__main__':
    unittest.main()
