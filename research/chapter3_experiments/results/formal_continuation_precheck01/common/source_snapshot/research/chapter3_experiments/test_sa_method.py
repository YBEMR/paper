"""SA rules and deadline lifecycle on synthetic/tiny correctness domains only."""
from copy import deepcopy
from fractions import Fraction as F
import random
import sys
import types
import unittest
from unittest.mock import patch

import sa_method as sa
from thermal import Exhausted


def input_fixture():
    return {
        'window_ms': '30', 'start_grid_ms': '5',
        'stage_modes': {
            'A': [{'unit_id': 'CPU1', 'opp_id': 'H'},
                  {'unit_id': 'CPU1', 'opp_id': 'L'},
                  {'unit_id': 'GPU', 'opp_id': 'Boost'}],
            'B': [{'unit_id': 'CPU1', 'opp_id': 'H'},
                  {'unit_id': 'CPU1', 'opp_id': 'L'}]},
        'scenarios': [
            {'id': 'AB', 'stage_instances': [
                {'id': 'a1', 'shared_stage_id': 'A'},
                {'id': 'b1', 'shared_stage_id': 'B'}]},
            {'id': 'AC', 'stage_instances': [
                {'id': 'a2', 'shared_stage_id': 'A'}]}]}


def plan_fixture():
    return {'mapping': {'A': 'CPU1', 'B': 'CPU1'},
            'opps': {'AB': {'a1': 'H', 'b1': 'H'}, 'AC': {'a2': 'L'}},
            'priorities': {'AB': ['a1', 'b1'], 'AC': ['a2']},
            'delays': {'AB': {'a1': 0, 'b1': 0}, 'AC': {'a2': 0}}}


def receipt(lo='1', hi='1', state='SAFE'):
    return {'state': state, 'rankable_energy': True,
            'weighted_energy_J': [lo, hi], 'safe_upper_bound_J': hi}


class CountingBudget:
    def __init__(self, checks=200):
        self.checks = checks

    def check(self):
        self.checks -= 1
        if self.checks < 0:
            raise Exhausted('synthetic_budget')


class SAMethodTests(unittest.TestCase):
    def test_parameters_are_explicit_and_immutable(self):
        params = sa.algorithm_parameters()
        self.assertEqual(params['initial_temperature_dimensionless'], 0.05)
        self.assertEqual(params['initial_random_batch'], 32)
        self.assertEqual(params['initial_random_zero_wait_probability'], 0.5)
        self.assertIn('self-set', params['parameter_source'])
        params['move_kinds'].append('bad')
        self.assertNotIn('bad', sa.algorithm_parameters()['move_kinds'])

    def test_random_genes_preserve_all_shared_copies_and_legal_opps(self):
        instance = input_fixture()
        for seed in range(20):
            plan = sa._random_plan(instance, random.Random(seed))
            self.assertEqual(set(plan['mapping']), {'A', 'B'})
            for scene in instance['scenarios']:
                sid = scene['id']
                self.assertCountEqual(plan['priorities'][sid],
                                      [st['id'] for st in scene['stage_instances']])
                for st in scene['stage_instances']:
                    key, iid = st['shared_stage_id'], st['id']
                    self.assertIn(plan['opps'][sid][iid],
                        sa._opp_ids(instance, key, plan['mapping'][key]))
                    self.assertTrue(0 <= plan['delays'][sid][iid] <= 4)

    def test_random_initialisation_mixes_zero_and_nonzero_waits(self):
        observed = []
        for seed in range(40):
            plan = sa._random_plan(input_fixture(), random.Random(seed))
            observed.append(all(value == 0 for scene in plan['delays'].values()
                                for value in scene.values()))
        self.assertIn(True, observed)
        self.assertIn(False, observed)
        self.assertEqual(sa.algorithm_parameters()['initial_random_zero_wait_probability'], 0.5)

    def test_neighbours_have_all_four_moves_and_never_mutate_parent(self):
        instance, plan = input_fixture(), plan_fixture()
        original, kinds = deepcopy(plan), set()
        for seed in range(150):
            new, kind = sa._mutate(instance, plan, random.Random(seed))
            kinds.add(kind)
            self.assertEqual(plan, original)
            self.assertNotEqual(new, plan)
            if kind == 'mapping':
                self.assertEqual(new['mapping']['A'], 'GPU')
                self.assertEqual(new['opps']['AB']['a1'], 'Boost')
                self.assertEqual(new['opps']['AC']['a2'], 'Boost')
            if kind == 'delay':
                differences = [new['delays'][sid][iid]-plan['delays'][sid][iid]
                    for sid in plan['delays'] for iid in plan['delays'][sid]]
                self.assertEqual(sorted(differences), [0, 0, 1])
        self.assertEqual(kinds, set(sa.MOVE_KINDS))

    def test_delay_change_is_one_step_and_bounded(self):
        instance, plan = input_fixture(), plan_fixture()
        plan['delays']['AB']['a1'] = 6
        catalog = sa._move_catalog(instance, plan)
        values = next(v for sid, iid, v in catalog['delay'] if iid == 'a1')
        self.assertEqual(values, [5])

    def test_only_complete_rankable_safe_interval_is_a_score(self):
        self.assertEqual(sa._safe_energy(receipt('1', '2')), (F(1), F(2)))
        for state in ('THERMAL_VIOLATION', 'UNRESOLVED', 'INVALID_SCHEDULE'):
            self.assertIsNone(sa._safe_energy(receipt(state=state)))
        bad = receipt()
        bad['rankable_energy'] = False
        self.assertIsNone(sa._safe_energy(bad))
        self.assertIsNone(sa._safe_energy(receipt('2', '1')))
        self.assertIsNone(sa._safe_energy(receipt('-1', '1')))
        bad = receipt('1', '2')
        bad['safe_upper_bound_J'] = '3'
        self.assertIsNone(sa._safe_energy(bad))

    def test_cooling_and_acceptance_are_dimensionless(self):
        self.assertEqual(sa._temperature(0), 0.05)
        self.assertEqual(sa._temperature(20), 0.05*0.95)
        self.assertEqual(sa._temperature(10000000), 0.0001)
        self.assertTrue(sa._accept((F(2), F(2)), (F(1), F(1)), 0, random.Random(7)))
        self.assertFalse(sa._accept((F(1), F(1)), (F(100), F(100)), 0, random.Random(7)))

    def _run(self, assess, *, constructor=None, checks=150, seed=101):
        plan = plan_fixture()
        common = types.ModuleType('heuristic_common')
        common.decode_plan = lambda instance, proposed, budget=None: {'plan': deepcopy(proposed)}
        common.plan_from_candidate = lambda instance, candidate, budget=None: deepcopy(candidate['plan'])
        heft = types.ModuleType('heft_method')
        heft.build_heft_candidate = constructor or (lambda *a, **kw:
            {'candidate': {'plan': deepcopy(plan)}, 'status': 'CONSTRUCTED'})
        with patch.dict(sys.modules, {'heuristic_common': common, 'heft_method': heft}):
            return sa.run_sa(input_fixture(), {}, CountingBudget(checks), assess, seed)

    def test_seed_is_reproducible_and_global_rng_is_untouched(self):
        records = []
        def run():
            events = []
            def assess(candidate, source):
                events.append((deepcopy(candidate), source))
                return receipt()
            out = self._run(assess)
            records.append(events)
            return out
        state = random.getstate()
        left, right = run(), run()
        self.assertEqual(left, right)
        self.assertEqual(records[0], records[1])
        self.assertEqual(random.getstate(), state)
        self.assertEqual(left['state'], 'SAFE')
        self.assertEqual(left['stop_reason'], 'METHOD_BUDGET_EXHAUSTED')
        self.assertEqual(left['initialisation_source'], 'heft')

    def test_failed_initialisation_continues_after_first_random_batch(self):
        out = self._run(lambda *args: receipt(state='UNRESOLVED'),
                        constructor=lambda *a, **kw: {'candidate': None}, checks=240)
        self.assertGreater(out['counters']['random_initialisation_attempts'], 32)
        self.assertGreater(out['counters']['post_batch_random_restarts'], 0)
        self.assertEqual(out['state'], 'UNRESOLVED')
        self.assertIsNone(out['best_evaluated_upper_J'])

    def test_unknown_and_violation_neighbours_cannot_replace_safe_current(self):
        calls = []
        def assess(candidate, source):
            calls.append(source)
            return receipt('2', '2') if len(calls) == 1 else receipt('0', '0', 'THERMAL_VIOLATION')
        out = self._run(assess)
        self.assertEqual(out['current_safe_energy_J'], ['2', '2'])
        self.assertEqual(out['best_evaluated_upper_J'], '2')
        self.assertGreater(out['counters']['rejected_without_safe_objective'], 0)
        self.assertEqual(out['counters'].get('accepted_neighbours', 0), 0)

    def test_template_order_is_fixed_and_does_not_call_heft_optimisation(self):
        ranks = []
        def constructor(*args, **kwargs):
            ranks.append(kwargs['opp_rank'])
            return {'candidate': None}
        out = self._run(lambda *a: receipt(state='UNRESOLVED'), constructor=constructor, checks=14)
        self.assertEqual(ranks, [None, 0, 1, 2])
        self.assertEqual(out['counters']['initial_constructions'], 4)

    def test_invalid_seed_rejected(self):
        with self.assertRaises(ValueError):
            self._run(lambda *a: receipt(), seed=True)

    def test_common_decoder_tiny_shared_fixture_is_legal(self):
        # Structural correctness only: no thermal propagation, solver or Q1 run.
        from inputs import load_config
        from run_milp_precheck import fixtures
        from heuristic_common import decode_plan, plan_from_candidate
        from schedules import validate_schedule
        tiny, starts = fixtures(load_config())['shared_two_scenes']
        tiny['start_domain'] = {'version': 1, 'kind': 'explicit_grid_subset',
                               'by_scene_stage_ms': starts}
        copies, units = sa._indexes(tiny)
        plan = sa._random_plan(tiny, random.Random(9), (copies, units))
        for sid in plan['delays']:
            for iid in plan['delays'][sid]:
                plan['delays'][sid][iid] = 0
        candidate = decode_plan(tiny, plan)
        self.assertIsNotNone(candidate)
        self.assertEqual(validate_schedule(tiny, candidate)['state'],
                         'SCHEDULE_VALID_THERMAL_UNCHECKED')
        again = decode_plan(tiny, plan_from_candidate(tiny, candidate))
        self.assertEqual(candidate, again)

    def test_real_constructor_and_decoder_share_one_budget(self):
        from inputs import load_config
        from run_milp_precheck import fixtures
        from schedules import validate_schedule
        tiny, starts = fixtures(load_config())['shared_two_scenes']
        tiny['start_domain'] = {'version': 1, 'kind': 'explicit_grid_subset',
                               'by_scene_stage_ms': starts}
        seen = []
        def assess(candidate, source):
            self.assertEqual(validate_schedule(tiny, candidate)['state'],
                             'SCHEDULE_VALID_THERMAL_UNCHECKED')
            seen.append(source)
            # Fake receipt tests integration, not any physical SAFE claim.
            return receipt()
        out = sa.run_sa(tiny, {}, CountingBudget(1800), assess, 101)
        self.assertTrue(seen)
        self.assertEqual(seen[0], 'sa_initial_heft')
        self.assertEqual(out['state'], 'SAFE')
        self.assertEqual(out['stop_reason'], 'METHOD_BUDGET_EXHAUSTED')


if __name__ == '__main__':
    unittest.main()
