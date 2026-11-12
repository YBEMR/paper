"""Fixed-unit lifecycle correctness, not a scheduling performance experiment.

Mock tests reuse the existing N1 transport harness with the real new condition
and original-input adapter. One integration test uses real small-domain
continuous physics/models and echoes only this call's freshly admitted x0.
No native solver or original-scale research call is started.
"""
from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4
import unittest
from unittest.mock import patch

import numpy as np

import fixed_unit_method
import fixed_unit_neighborhood as condition_api
import fixed_unit_neighborhood_adapter as fixed_adapter
import matlab_bridge
import milp
import neighborhood_method
import scene_adapter
from control_policy import with_auto_low_idle
from inputs import load_config
from test_neighborhood_method import Harness
from test_partial_deployment import small_case


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RECORDS = {'scope': 'fixed-unit lifecycle correctness only; fake optimizer, no research call'}


class FixedHarness(Harness):
    def condition_factory(self, *args, **kwargs):
        budget = kwargs['budget']
        self.budgets.append(id(budget)); self.clock.tick()
        assert self.aggregate_values, 'A complete fresh SAFE seed must precede the condition'
        self.trace.append(('condition', self.clock.now))
        self.condition = condition_api.make_fixed_unit_condition(*args, **kwargs)
        return self.condition

    def scene_evaluator(self, instance, condition, sid, proposal, *, budget, accuracy=None):
        self.budgets.append(id(budget)); self.clock.tick()
        self.assert_original(instance)
        if self.options.get('expire_original_recheck') and self._local_opp(proposal, sid) != 'H':
            self.clock.tick(100)
        with patch.object(scene_adapter, 'evaluate_piecewise', side_effect=self.physical):
            wrapper = fixed_adapter.evaluate_fixed_unit_scene(
                instance, condition, sid, proposal, budget=budget, accuracy=accuracy)
        self.trace.append(('fixed_unit_original', sid, wrapper['state'], self.inside))
        return wrapper

    def run(self, directory, **extra):
        return fixed_unit_method.execute_fixed_unit_opp_start(self.loader, directory,
            shared_deployment={'A.pre': 'CPU1'}, seconds=60, clock=self.clock,
            seed_iterator=self.seed_iterator, seed_scene_evaluator=self.seed_scene_evaluator,
            condition_factory=self.condition_factory, model_builder=self.builder,
            initial_completer=self.completer, model_evaluator=self.evaluator,
            scene_evaluator=self.scene_evaluator, aggregator=self.aggregator,
            recorder_factory=self.recorder, session_factory=self.session_factory,
            feedback_adder=self.feedback, **extra)


class FixedUnitMethodTests(unittest.TestCase):
    def setUp(self):
        # Inherit workspace permissions rather than tempfile's Windows ACL
        # behavior. Retain ignored artifacts; never recursively delete them.
        root = REPO/'.runtime/fixed_unit_method_correctness'
        root.mkdir(parents=True, exist_ok=True)
        self.path = root/('case_'+uuid4().hex)
        self.path.mkdir()

    def test_all_stage_opening_is_derived_once_inside_same_fresh_budget(self):
        h = FixedHarness()
        result = h.run(self.path/'call')
        self.assertEqual(result['state'], 'SAFE', result.get('error'))
        self.assertEqual(result['protocol'], fixed_unit_method.PROTOCOL)
        self.assertEqual(h.condition['protocol'], condition_api.PROTOCOL)
        self.assertEqual(len(set(h.budgets)), 1)
        self.assertEqual(len(h.seed_views), 1)
        self.assertEqual(h.instance, h.input_before)
        for scene in h.instance['scenarios']:
            self.assertEqual(set(result['opened_by_scene'][scene['id']]),
                             {stage['id'] for stage in scene['stage_instances']})
        order = [item[0] for item in h.trace]
        self.assertLess(order.index('aggregate'), order.index('condition'))
        self.assertLess(order.index('condition'), order.index('model'))
        self.assertEqual(len(h.sessions), 1)
        RECORDS['same_budget_mock'] = {'result': result, 'trace': h.trace}

    def test_shared_A_opp_is_open_but_unit_is_fixed(self):
        h = FixedHarness(closed_opp_escape=True)
        result = h.run(self.path/'call')
        self.assertEqual(result['state'], 'SAFE', result.get('error'))
        self.assertEqual(result['reason'], 'SCENE_SEARCH_SEQUENCE_COMPLETE', result.get('error'))
        self.assertLess(float(result['safe_upper_bound_J']), 10)
        for rows in result['safe_candidate']['scenes'].values():
            a = next(row for row in rows if 'A.pre' in row['stage_id'])
            self.assertEqual((a['unit'], a['opp']), ('CPU1', 'M'))
        self.assertEqual(result['shared_deployment'], {'A.pre': 'CPU1'})

    def test_outside_seed_unit_is_not_accepted_or_globally_excluded(self):
        h = FixedHarness(outside_n1=True)
        result = h.run(self.path/'call')
        self.assertEqual(result['state'], 'SAFE')
        self.assertEqual(float(result['safe_upper_bound_J']), 10)
        self.assertNotEqual(result['reason'], 'SCENE_SEARCH_SEQUENCE_COMPLETE')
        self.assertFalse(result['independently_proven_infeasible'])

    def test_missing_complete_safe_seed_stops_before_condition_and_models(self):
        for option in ('no_safe_seed', 'no_seed_candidate'):
            with self.subTest(option=option):
                h = FixedHarness(**{option: True})
                result = h.run(self.path/option)
                self.assertEqual(result['reason'], 'NO_COMPLETE_SAFE_FIXED_UNIT_SEED')
                self.assertIsNone(result['safe_upper_bound_J'])
                self.assertIsNone(h.condition)
                self.assertFalse(h.models)
                self.assertFalse(h.sessions)
                self.assertFalse(result['independently_proven_infeasible'])

    def test_rejected_x0_keeps_safe_seed_and_permits_same_domain_bare_search(self):
        h = FixedHarness(reject_x0=True)
        result = h.run(self.path/'call')
        self.assertEqual(result['state'], 'SAFE', result.get('error'))
        self.assertTrue(h.requests)
        self.assertTrue(all(item[3] is None for item in h.trace if item[0] == 'request'))
        self.assertTrue(all(scene['bare_MILP_fallback'] for scene in result['scenes'].values()))
        self.assertIsNotNone(result['initial_global_safe_upper_bound_J'])

    def test_formed_violation_survives_deadline_without_late_feedback(self):
        h = FixedHarness(violation=True, expire_after_callback=True)
        result = h.run(self.path/'call')
        self.assertEqual(result['state'], 'SAFE')
        self.assertEqual(float(result['safe_upper_bound_J']), 10)
        self.assertTrue(result['violations'])
        self.assertTrue(result['budget_exhausted'])
        self.assertFalse(any(item[0] == 'feedback' for item in h.trace))

    def test_late_original_recheck_does_not_create_an_improved_upper_bound(self):
        h = FixedHarness(expire_original_recheck=True)
        result = h.run(self.path/'call')
        self.assertEqual(result['state'], 'SAFE')
        self.assertEqual(float(result['safe_upper_bound_J']), 10)
        self.assertEqual(len(h.aggregate_values), 1)

    def test_formed_complete_safe_aggregate_survives_late_transfer(self):
        h = FixedHarness(late_aggregate_transfer=True)
        result = h.run(self.path/'call')
        self.assertEqual(result['state'], 'SAFE', result.get('error'))
        self.assertLess(float(result['safe_upper_bound_J']), 10)
        self.assertTrue(result['budget_exhausted'])

    def test_reported_bound_and_infeasibility_keep_conditional_scope(self):
        h = FixedHarness(reported_infeasible=True)
        result = h.run(self.path/'call')
        self.assertEqual(result['state'], 'SAFE')
        self.assertFalse(result['independently_proven_optimal'])
        self.assertFalse(result['independently_proven_infeasible'])
        self.assertFalse(result['solver_reported_bounds_aggregated'])
        self.assertFalse(result['global_deployment_search_performed'])
        for scene in result['scenes'].values():
            for bound in scene['solver_reported_bounds']:
                self.assertEqual(bound['scope'], 'seed_fixed_units_all_stage_opp_start_unweighted_scene')
                self.assertTrue(bound['solver_reported_only'])
                self.assertFalse(bound['independently_certified'])
        self.assertIn('original full domain retained', result['search_scope'])

    def test_wrapper_does_not_accept_a_subset_or_protocol_only_relabel(self):
        loader = lambda budget: (_ for _ in ()).throw(AssertionError('must not load'))
        for override in ({'opened_by_scene': {}}, {'membership_checker': lambda *args: None},
                         {'condition_protocol': 'arbitrary'}, {'_method_identity': {}}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                fixed_unit_method.execute_fixed_unit_opp_start(loader, self.path/'invalid',
                    shared_deployment={'A.pre': 'CPU1'}, **override)

    def test_old_N1_default_protocol_and_closed_A_behavior_remain(self):
        old = Harness(closed_opp_escape=True)
        result = old.run(self.path/'old')
        self.assertEqual(result['protocol'], neighborhood_method.PROTOCOL)
        self.assertEqual(result['search_scope'],
                         'this invocation seed-defined N1 only; original domain retained')
        self.assertEqual(result['state'], 'SAFE')
        self.assertEqual(float(result['safe_upper_bound_J']), 10)
        self.assertNotEqual(result['reason'], 'SCENE_SEARCH_SEQUENCE_COMPLETE')

    def test_real_small_physics_and_echo_transport_use_fresh_all_stage_domain(self):
        config = with_auto_low_idle(load_config())
        instance, shared, _ = small_case()
        before = scene_adapter.canonical_hash(instance)
        models, sessions, requests = [], [], []

        def loader(budget):
            budget.check()
            return deepcopy(config), deepcopy(instance)

        def builder(original, cfg, **kwargs):
            model = milp.build_model(original, cfg, **kwargs)
            models.append(model)
            return model

        def save(path, value):
            Path(path).write_text(json.dumps(value, default=str), encoding='utf-8')

        class EchoSession:
            def __init__(self, folder, *, total_budget_s, budget):
                self.workdir = Path(folder); self.workdir.mkdir()
                self.budget = budget; self.counter = 0
                self.event_consumer = None; self.closed = False; self.request_blocked = False
                sessions.append(self)

            def solve(self, payload, *, remaining_s, budget, x0=None, **kwargs):
                budget.check()
                assert budget is self.budget and x0 is not None
                accepted = matlab_bridge._prepare(payload, x0=x0)
                assert accepted['x0_validation']['accepted_numerically'] is True
                vector = np.asarray(x0).reshape(-1).tolist()
                self.counter += 1
                requests.append({'same_budget': budget is self.budget,
                    'dimension': len(vector), 'mock_native': True,
                    'x0_validation': accepted['x0_validation']})
                prefix = self.workdir/('request_%03d'%self.counter)
                for seq, event in enumerate(({'kind': 'solver_entered'},
                        {'kind': 'incumbent', 'x': vector, 'values': {}}), 1):
                    save(Path(str(prefix)+'.event_%06d.json'%seq), event)
                    if self.event_consumer:
                        self.event_consumer(prefix)
                return {'status': 'SOLVED', 'x': vector, 'exitflag': 1,
                    'budget_valid': budget.remaining > 0,
                    'accepted_for_evaluation': budget.remaining > 0,
                    'intlinprog_entered': False, 'output': {}, 'callbacks': [],
                    'precheck_transport': 'echo of this call fresh admitted x0, no native solver'}

            def close(self):
                self.event_consumer = None; self.closed = True

        result = fixed_unit_method.execute_fixed_unit_opp_start(loader, self.path/'physical',
            shared_deployment=shared, seconds=180, model_builder=builder, session_factory=EchoSession)
        self.assertEqual(result['state'], 'SAFE', result.get('error', result.get('reason')))
        self.assertEqual(result['reason'], 'SCENE_SEARCH_SEQUENCE_COMPLETE', result.get('error'))
        self.assertEqual(result['protocol'], fixed_unit_method.PROTOCOL)
        self.assertEqual(result['condition']['protocol'], condition_api.PROTOCOL)
        self.assertEqual(result['weighted_energy_J'], result['initial_global_weighted_energy_J'])
        self.assertFalse(result['strict_improvement_over_initial_certified'])
        self.assertFalse(result['independently_proven_optimal'])
        self.assertFalse(result['independently_proven_infeasible'])
        self.assertEqual(len(models), 2)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(len(requests), 2)
        self.assertTrue(sessions[0].closed)
        for model in models:
            a_opps = {option['opp_id'] for option in model.options
                      if option['shared_stage_id'] == 'A.pre'}
            self.assertEqual(a_opps, {'L', 'M', 'H'})
        self.assertEqual(scene_adapter.canonical_hash(instance), before)
        RECORDS['real_small_physical_echo'] = {'input': instance, 'config': config,
            'result': result, 'requests': requests,
            'model_summaries': [model.summary() for model in models],
            'native_calls': 0, 'research_calls': 0}


if __name__ == '__main__':
    unittest.main(verbosity=2)
