"""Outer orchestration tests: mocked physics and worker, real receipt identities."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from control_policy import with_auto_low_idle
from inputs import build_instance, load_config
import scene_adapter as adapter
from shared_search import execute_shared_search, ordered_conditions
from test_partial_method import Clock, small_input
from timing import MethodBudget

REPO = Path(__file__).resolve().parents[2]
RECORDS = {'scope': 'mock orchestration and exact input algebra; no physical conclusions'}


class OuterHarness:
    def __init__(self, **options):
        self.options = options
        self.clock = Clock()
        self.trace, self.sessions, self.budget_ids = [], [], []
        self.calls = 0

    def loader(self, budget):
        self.budget_ids.append(id(budget)); self.clock.tick()
        self.config, self.instance = small_input()
        return self.config, self.instance

    def session(self, folder, **kwargs):
        harness = self
        self.budget_ids.append(id(kwargs['budget']))
        class Session:
            counter = 0
            request_blocked = False
            event_consumer = None
            def close(self):
                harness.trace.append('closed'); harness.clock.tick()
        session = Session()
        self.sessions.append(session); self.trace.append('worker_started')
        return session

    def executor(self, loader, folder, *, shared_deployment, budget, close_session,
                 scene_slice_s, session_factory, on_global_update, bounds_receipt, **kwargs):
        self.calls += 1
        self.budget_ids.append(id(budget))
        assert close_session is False and scene_slice_s == 60
        assert bounds_receipt['L_a']['shared_deployment'] == shared_deployment
        config, instance = loader(budget)
        assert instance == self.instance
        path = Path(folder); path.mkdir()
        result = {'state': 'UNRESOLVED', 'reason': 'SEARCH_SLICE_ENDED', 'scenes': {},
                  'shared_deployment': deepcopy(shared_deployment), 'violations': [],
                  'initial_global_safe_upper_bound_J': None}
        unit = shared_deployment['A.pre']

        def publish(opp, source, value):
            receipts, candidates = {}, {}
            accuracy = adapter._accuracy(config['accuracy_targets'])
            def physical(platform, entry, limits, segments, window, accuracy, given, *, scene_id):
                assert given is budget
                return {'scene_id': scene_id, 'state': 'SAFE', 'complete': True,
                    'rankable_energy': True, 'violations': [], 'energy_J': [str(value), str(value)],
                    'energy_accuracy_met': True, 'covered_until_s': '2/5',
                    'completed_at_elapsed_s': budget.elapsed}
            for scene in instance['scenarios']:
                sid = scene['id']
                proposal = {'scenes': {sid: [{'stage_id': scene['stage_instances'][0]['id'],
                    'unit': unit, 'opp': opp, 'start_ms': '0'}]}}
                with patch.object(adapter, 'evaluate_piecewise', side_effect=physical):
                    receipts[sid] = adapter.evaluate_partial_scene(instance, sid, shared_deployment,
                                                                   proposal, accuracy, budget)
                candidates[sid] = proposal
            aggregation = adapter.aggregate_partial_scene_receipts(instance, shared_deployment,
                receipts, candidates, accuracy, budget)
            assert aggregation['state'] == 'SAFE', aggregation
            result.update(state='SAFE', aggregation=aggregation)
            update = {'scene_sources': {sid: source for sid in receipts},
                      'weighted_energy_J': aggregation['weighted_energy_J'],
                      'safe_upper_bound_J': aggregation['safe_upper_bound_J']}
            self.trace.append(('aggregate', unit, source))
            self.clock.tick()
            if self.options.get('late_first') and self.calls == 1:
                self.clock.tick(100)
            if self.options.get('wrong_identity') and self.calls == 2:
                result['shared_deployment'] = {'A.pre': 'CPU1'}
            on_global_update(result, update)

        if not self.options.get('no_initial'):
            publish('H', 'initial_constructor', 10 if unit == 'CPU1' else 8)
        session = session_factory(path/'matlab', total_budget_s=budget.remaining, budget=budget)
        session.counter += 2
        self.trace.append(('solver', unit))
        if self.options.get('inner') and unit == 'CPU1':
            publish('L', 'round1:callback', 6 if not self.options.get('weak_inner') else 9)
        if self.options.get('technical'):
            result.update(reason='INTERFACE_ERROR', error='MOCK_AFTER_SAFE')
        if self.options.get('blocked'):
            session.request_blocked = True
        if self.options.get('expire_return'):
            result['violations'] = [{'reason': 'MOCK_COMMITTED_VIOLATION'}]
            self.clock.tick(100)
        (path/'result.json').write_text(json.dumps(result), encoding='utf-8')
        self.clock.tick()
        return result

    def run(self, folder, **kwargs):
        return execute_shared_search(self.loader, folder, clock=self.clock,
            session_factory=self.session, condition_executor=self.executor, seconds=60, **kwargs)


class SharedSearchTests(unittest.TestCase):
    def setUp(self):
        home = REPO/'.runtime/shared_search_unit'; home.mkdir(parents=True, exist_ok=True)
        self.home = home.resolve()
        self.temp = tempfile.TemporaryDirectory(prefix='unit_', dir=home)
        self.path = Path(self.temp.name).resolve(); self.path.relative_to(self.home)
    def tearDown(self):
        self.path.relative_to(self.home); self.temp.cleanup()

    def test_original_sixteen_group_order_and_all_CPU_labels(self):
        config = with_auto_low_idle(load_config())
        instance = with_auto_low_idle(build_instance(config, 'base__R1'))
        rows, ordering = ordered_conditions(instance, MethodBudget(60))
        self.assertEqual(len(rows), 16)
        self.assertEqual(ordering['group_order'], ['NPU0', 'GPU0', 'CPU1', 'CPU2'])
        self.assertEqual([r['shared_deployment']['A.main'] for r in rows[:4]], ordering['group_order'])
        self.assertEqual(len({tuple(sorted(r['shared_deployment'].items())) for r in rows}), 16)
        self.assertTrue(all(r['state'] == 'UNVISITED' for r in rows))
        self.assertFalse(ordering['domain_pruning'])
        RECORDS['original_static_order'] = {'ordering': ordering,
            'conditions': [r['shared_deployment'] for r in rows]}

    def test_one_budget_worker_and_initial_before_startup(self):
        h = OuterHarness(inner=True); result = h.run(self.path/'run')
        self.assertEqual(result['reason'], 'FIRST_PASS_COMPLETED_REMAINING_DOMAIN_UNRESOLVED')
        self.assertEqual(len(h.sessions), 1)
        self.assertEqual(len(set(h.budget_ids)), 1)
        self.assertLess(h.trace.index(('aggregate', 'CPU1', 'initial_constructor')), h.trace.index('worker_started'))
        self.assertEqual(h.trace.count('closed'), 1)
        self.assertEqual(result['visited_condition_count'], 2)
        self.assertEqual(result['solver_request_attempts'], 4)
        self.assertEqual(result['safe_upper_bound_J'], '6')
        self.assertEqual(result['best_initial_upper_bound_J'], '8')
        self.assertTrue(result['strict_improvement_over_best_initial_certified'])
        self.assertFalse(result['independently_proven_optimal'])
        self.assertEqual(result['remaining_domain'], 'retained')
        RECORDS['outer_lifecycle'] = result

    def test_new_condition_initial_improvement_not_inner_credit(self):
        h = OuterHarness(inner=True, weak_inner=True); result = h.run(self.path/'run')
        last = result['global_updates'][-1]
        self.assertEqual(last['source'], 'initial_constructor')
        self.assertTrue(last['condition_changed'])
        self.assertEqual(result['safe_upper_bound_J'], result['best_initial_upper_bound_J'])
        self.assertFalse(result['strict_improvement_over_best_initial_certified'])

    def test_no_initial_can_find_SAFE_without_creating_a_baseline(self):
        h = OuterHarness(no_initial=True, inner=True); result = h.run(self.path/'run')
        self.assertEqual(result['state'], 'SAFE')
        self.assertIsNone(result['best_initial_upper_bound_J'])
        self.assertFalse(result['strict_improvement_over_best_initial_certified'])
        self.assertEqual(result['global_updates'][0]['source'], 'inner_MILP')

    def test_cross_condition_identity_error_keeps_prior_safe(self):
        h = OuterHarness(wrong_identity=True); result = h.run(self.path/'run')
        self.assertEqual(result['reason'], 'INTERFACE_ERROR')
        self.assertEqual(result['safe_upper_bound_J'], '10')
        self.assertEqual(result['best_shared_deployment'], {'A.pre': 'CPU1'})

    def test_safe_does_not_hide_technical_error_and_stops(self):
        h = OuterHarness(technical=True); result = h.run(self.path/'run')
        self.assertEqual(result['state'], 'SAFE')
        self.assertEqual(result['reason'], 'CONDITION_TECHNICAL_FAILURE')
        self.assertEqual(result['visited_condition_count'], 1)
        self.assertEqual(result['conditions'][1]['state'], 'UNVISITED')

    def test_unwound_guard_stops_without_new_worker(self):
        h = OuterHarness(blocked=True); result = h.run(self.path/'run')
        self.assertEqual(result['reason'], 'NATIVE_REQUEST_NOT_UNWOUND')
        self.assertEqual(h.calls, 1)
        self.assertEqual(len(h.sessions), 1)

    def test_committed_safe_and_violation_survive_expired_return(self):
        h = OuterHarness(expire_return=True); result = h.run(self.path/'run')
        self.assertEqual(result['safe_upper_bound_J'], '10')
        self.assertEqual(result['reason'], 'GLOBAL_BUDGET_EXHAUSTED')
        self.assertEqual(len(result['violations']), 1)
        self.assertEqual(result['visited_condition_count'], 1)

    def test_late_transfer_does_not_publish_search_U(self):
        h = OuterHarness(late_first=True); result = h.run(self.path/'run')
        self.assertIsNone(result['safe_upper_bound_J'])
        self.assertFalse(result['rankable_energy'])
        self.assertTrue(result['late_existing_aggregate_transfers'])
        self.assertEqual(result['best_initial_upper_bound_J'], '10')
        self.assertFalse(result['strict_improvement_over_best_initial_certified'])

    def test_directory_and_timing_override_rejected(self):
        folder = self.path/'existing'; folder.mkdir()
        with self.assertRaises(FileExistsError): OuterHarness().run(folder)
        with self.assertRaises(ValueError):
            OuterHarness().run(self.path/'override', condition_options={'seconds': 900})
        with self.assertRaises(ValueError):
            OuterHarness().run(self.path/'bad_slice', scene_slice_s=0)

