"""K124 N1 encoding checks on named, small correctness fixtures only.

The synthetic SAFE receipts below test the existing receipt identity contract;
their physical evaluator is mocked and they are never thermal evidence.
Every model uses include_physics=False. Cartesian membership, exact execution
ends and resource legality are checked independently from N1's own filter.
No optimizer, MATLAB worker, research case or real thermal propagation runs.
"""
from copy import deepcopy
from fractions import Fraction as F
from itertools import product
import inspect
import unittest
from unittest.mock import patch

import milp
import neighborhood
import scene_adapter as adapter
from control_policy import with_auto_low_idle
from inputs import build_instance, load_config
from run_milp_precheck import (candidate_key, independent_check, select_fixture)
from test_auto_milp import structure_vector, row_accepts
from thermal import Budget, Exhausted


RECORDS = {'scope': 'N1 small structural models and mocked receipt identities only; '
                    'no physical SAFE evidence, solver or research run'}
_BASE = None


def base_input():
    global _BASE
    if _BASE is None:
        _BASE = build_instance(load_config(), 'base__R1')
    return _BASE


def fixture(kind='npu'):
    """Preserve the platform, physics and legal modes; trim test tasks/starts."""
    base = base_input()
    ab, ac = [scene['id'] for scene in base['scenarios']]
    if kind == 'cpu':
        selected = {ab: ['A.pre', 'B.main', 'B.post'], ac: ['A.pre']}
        starts = {'A.pre': [0, 5], 'B.main': [0, 5], 'B.post': [135, 140]}
    else:
        selected = {ab: ['A.pre', 'B.main', 'B.post'],
                    ac: ['A.pre', 'C.main', 'C.post']}
        starts = {'A.pre': [0, 5], 'B.main': [20, 25], 'B.post': [60, 85],
                  'C.main': [20, 25], 'C.post': [60, 85]}
    case, by_stage = select_fixture(base, 'n1_encoding_'+kind, selected, starts)
    case['start_domain'] = {'version': 1, 'kind': 'explicit_grid_subset',
                            'by_scene_stage_ms': by_stage}
    case = with_auto_low_idle(case)
    seed = {'scenes': {}}
    opened = {}
    for scene in case['scenarios']:
        sid = scene['id']
        rows = []
        opened[sid] = []
        for stage in scene['stage_instances']:
            shared = stage['shared_stage_id']
            if shared == 'A.pre':
                unit, start = 'CPU1', '0'
            elif shared == 'B.main':
                unit, start = ('CPU2', '0') if kind == 'cpu' else ('NPU0', '20')
                opened[sid].append(stage['id'])
            elif shared == 'B.post':
                unit, start = 'CPU1', '135' if kind == 'cpu' else '60'
                opened[sid].append(stage['id'])
            elif shared == 'C.main':
                unit, start = 'GPU0', '20'
            else:
                unit, start = 'CPU1', '85'
            rows.append({'stage_id': stage['id'], 'unit': unit,
                         'opp': 'H', 'start_ms': start})
        seed['scenes'][sid] = rows
    return case, {'A.pre': 'CPU1'}, seed, opened


def mocked_physical(platform, entry, limits, segments, window, accuracy, budget, *, scene_id):
    """Fabricated interface energy: this routine performs no physics."""
    return {'scene_id': scene_id, 'state': 'SAFE', 'reason': 'MOCK_IDENTITY_ONLY',
        'complete': True, 'rankable_energy': True, 'violations': [],
        'energy_J': ['1', '1'], 'energy_accuracy_met': True,
        'covered_until_s': str(F(window)/1000),
        'completed_at_elapsed_s': budget.elapsed}


def condition_for(case, mapping, seed, opened, budget):
    candidates = {sid: {'scenes': {sid: deepcopy(rows)}}
                  for sid, rows in seed['scenes'].items()}
    with patch.object(adapter, 'evaluate_piecewise', side_effect=mocked_physical):
        receipts = {sid: adapter.evaluate_partial_scene(
            case, sid, mapping, candidate, budget=budget)
            for sid, candidate in candidates.items()}
    receipt = adapter.aggregate_partial_scene_receipts(
        case, mapping, receipts, candidates, budget=budget)
    if receipt['state'] != 'SAFE':
        raise AssertionError('Synthetic receipt identity fixture failed: '+repr(receipt))
    return neighborhood.make_n1_condition(case, mapping, seed, receipt, opened, budget=budget)


def build(case, mapping, condition=None, *, budget=None, **extra):
    config = with_auto_low_idle(load_config())
    budget = budget if budget is not None else Budget(seconds=600)
    return milp.build_model(case, config, budget=budget, include_physics=False,
        fixed_shared_deployment=mapping, neighborhood_condition=condition, **extra)


def oracle_choices(case, seed, opened):
    """N1 Cartesian dimensions, without calling any N1 filtering/check helper."""
    dimensions = []
    for scene in case['scenarios']:
        sid = scene['id']
        seeds = {row['stage_id']: row for row in seed['scenes'][sid]}
        requests = {request['id']: request for request in scene['requests']}
        for stage in scene['stage_instances']:
            locked = seeds[stage['id']]
            choices = []
            for mode in case['stage_modes'][stage['shared_stage_id']]:
                if mode['unit_id'] != locked['unit']:
                    continue
                for value in case['start_domain']['by_scene_stage_ms'][sid][stage['id']]:
                    start = F(value)
                    if start < F(requests[stage['request_id']]['release_ms']):
                        continue
                    if start+F(mode['duration_ms']) > F(case['window_ms']):
                        continue
                    if stage['id'] not in opened[sid] and (
                        mode['opp_id'] != locked['opp'] or start != F(locked['start_ms'])):
                        continue
                    choices.append((sid, {'stage_id': stage['id'], 'unit': mode['unit_id'],
                        'opp': mode['opp_id'], 'start_ms': str(start)},
                        start+F(mode['duration_ms'])))
            dimensions.append(choices)
    return dimensions


def oracle_candidates(case, seed, opened):
    for selected in product(*oracle_choices(case, seed, opened)):
        candidate = {'scenes': {scene['id']: [] for scene in case['scenarios']}}
        for sid, row, _ in selected:
            candidate['scenes'][sid].append(deepcopy(row))
        yield candidate


def option_key(option):
    return (option['scenario_id'], option['stage_instance_id'], option['unit_id'],
            option['opp_id'], F(option['start_ms']), F(option['end_ms']))


def expected_option_keys(case, seed, opened):
    return {(sid, row['stage_id'], row['unit'], row['opp'], F(row['start_ms']), end)
            for dimension in oracle_choices(case, seed, opened)
            for sid, row, end in dimension}


def assert_solver_bytes_equal(test, left, right):
    a, b = left.as_solver_dict(), right.as_solver_dict()
    for name in ('c', 'b', 'beq', 'lb', 'ub', 'intcon'):
        test.assertEqual(a[name].dtype, b[name].dtype, name)
        test.assertEqual(a[name].shape, b[name].shape, name)
        test.assertEqual(a[name].tobytes(), b[name].tobytes(), name)
    for name in ('A', 'Aeq'):
        one, two = a[name].tocsr(), b[name].tocsr()
        test.assertEqual(one.shape, two.shape, name)
        for part in ('data', 'indices', 'indptr'):
            test.assertEqual(getattr(one, part).tobytes(), getattr(two, part).tobytes(),
                             name+'.'+part)


class N1MilpEncodingTests(unittest.TestCase):
    def test_default_none_is_omitted_byte_identity(self):
        case, mapping, _, _ = fixture('cpu')
        config = with_auto_low_idle(load_config())
        self.assertIsNone(inspect.signature(milp.build_model).parameters[
            'neighborhood_condition'].default)
        omitted = milp.build_model(case, config, include_physics=False,
            budget=Budget(seconds=600), fixed_shared_deployment=mapping)
        explicit = build(case, mapping)
        for field in ('names', 'rows', 'options', 'option_vars', 'shared', 'scenes',
                      'c', 'lb', 'ub', 'bounds', 'integer', 'logical_binary', 'formulation'):
            self.assertEqual(getattr(omitted, field), getattr(explicit, field), field)
        assert_solver_bytes_equal(self, omitted, explicit)
        self.assertEqual(omitted.summary(), explicit.summary())

    def test_condition_requires_shared_deployment_before_model_construction(self):
        case, mapping, seed, opened = fixture()
        budget = Budget(seconds=600)
        condition = condition_for(case, mapping, seed, opened, budget)
        config = with_auto_low_idle(load_config())
        with patch.object(milp, 'Model') as constructor:
            with self.assertRaises(ValueError):
                milp.build_model(case, config, neighborhood_condition=condition,
                    include_physics=False, budget=budget)
            constructor.assert_not_called()

    def test_exact_option_projection_fixes_all_units_and_closed_stage_choices(self):
        case, mapping, seed, opened = fixture()
        original = deepcopy(case)
        budget = Budget(seconds=600)
        condition = condition_for(case, mapping, seed, opened, budget)
        model = build(case, mapping, condition, budget=budget)
        self.assertEqual({option_key(o) for o in model.options},
                         expected_option_keys(case, seed, opened))
        self.assertEqual(case, original)
        self.assertEqual(model.instance['platform'], original['platform'])
        self.assertEqual(len(model.instance['platform']['node_order']), 4)
        self.assertEqual(model.instance['execution_rules'], original['execution_rules'])
        self.assertEqual(model.coefficients.calls, 0)
        for sid, rows in seed['scenes'].items():
            for row in rows:
                options = [o for o in model.options if o['scenario_id'] == sid
                           and o['stage_instance_id'] == row['stage_id']]
                self.assertEqual({o['unit_id'] for o in options}, {row['unit']})
                if row['stage_id'] in opened[sid]:
                    self.assertEqual({o['opp_id'] for o in options}, {'L', 'M', 'H'})
                else:
                    self.assertEqual({(o['opp_id'], F(o['start_ms'])) for o in options},
                                     {(row['opp'], F(row['start_ms']))})

    def test_complete_small_cartesian_projection_matches_independent_legality(self):
        case, mapping, seed, opened = fixture()
        budget = Budget(seconds=600)
        condition = condition_for(case, mapping, seed, opened, budget)
        model = build(case, mapping, condition, budget=budget)
        candidates = list(oracle_candidates(case, seed, opened))
        expected = {candidate_key(c) for c in candidates if independent_check(case, c)['valid']}
        actual = {candidate_key(c) for c in candidates if row_accepts(model, structure_vector(model, c))}
        self.assertEqual(actual, expected)
        self.assertTrue(expected)
        self.assertIn(candidate_key(seed), actual)
        self.assertEqual(neighborhood.check_n1_candidate(case, condition, seed, budget=budget)['state'],
                         'N1_MEMBER_SCHEDULE_VALID_THERMAL_UNCHECKED')
        self.assertLess(len(expected), len(candidates))
        self.assertTrue(any(F(o['end_ms']).denominator != 1 for o in model.options))
        RECORDS['cartesian'] = {'assignments': len(candidates), 'legal': len(expected),
            'projection_equal': actual == expected, 'physical_models': 0}

    def test_single_scene_projection_preserves_all_local_members_and_full_input(self):
        case, mapping, seed, opened = fixture()
        original = deepcopy(case)
        budget = Budget(seconds=600)
        condition = condition_for(case, mapping, seed, opened, budget)
        candidates = list(oracle_candidates(case, seed, opened))
        full_legal = [c for c in candidates if independent_check(case, c)['valid']]
        for scene in case['scenarios']:
            sid = scene['id']
            model = build(case, mapping, condition, budget=budget, fixed_scene_id=sid)
            self.assertEqual(set(model.scenes), {sid})
            self.assertEqual(model.instance['scenarios'][0]['weight'], '1')
            self.assertEqual({option_key(o) for o in model.options},
                             {o for o in expected_option_keys(case, seed, opened) if o[0] == sid})
            expected = {candidate_key({'scenes': {sid: c['scenes'][sid]}}) for c in full_legal}
            actual = {candidate_key({'scenes': {sid: c['scenes'][sid]}}) for c in candidates
                      if row_accepts(model, structure_vector(model, {'scenes': {sid: c['scenes'][sid]}}))}
            self.assertEqual(actual, expected)
        self.assertEqual(case, original)

    def test_same_frequency_cpu_parallel_allowed_but_mixed_frequency_rejected(self):
        case, mapping, seed, opened = fixture('cpu')
        budget = Budget(seconds=600)
        model = build(case, mapping, condition_for(case, mapping, seed, opened, budget), budget=budget)
        self.assertTrue(independent_check(case, seed)['valid'])
        self.assertTrue(row_accepts(model, structure_vector(model, seed)))
        conflicting = deepcopy(seed)
        ab = case['scenarios'][0]['id']
        main = next(row for row in conflicting['scenes'][ab] if row['stage_id'] in opened[ab]
                    and '.main' in row['stage_id'])
        main['opp'] = 'M'
        own = independent_check(case, conflicting)
        self.assertFalse(own['valid'])
        self.assertEqual(own['reason'], 'busy_domain_conflict')
        # Both devices remain fixed, and the M main still precedes its post.
        # It is the CPU domain's overlap with the fixed H A.pre that fails.
        vector = structure_vector(model, conflicting)
        self.assertFalse(row_accepts(model, vector))
        from run_milp_precheck import exact_row_residuals
        tags = {row['tag'] for row, residual in zip(model.rows, exact_row_residuals(model, vector))
                if residual > 0}
        self.assertTrue(any('opp' in tag or 'lock' in tag for tag in tags), tags)

    def test_fractional_finish_and_exact_deadline_are_not_rounded(self):
        case, mapping, seed, opened = fixture()
        ab = case['scenarios'][0]['id']
        scene = case['scenarios'][0]
        post = next(stage for stage in scene['stage_instances'] if stage['shared_stage_id'] == 'B.post')
        request = next(request for request in scene['requests'] if request['id'] == post['request_id'])
        request['deadline_ms'] = '66'
        budget = Budget(seconds=600)
        model = build(case, mapping, condition_for(case, mapping, seed, opened, budget), budget=budget)
        self.assertTrue(row_accepts(model, structure_vector(model, seed)))
        altered = deepcopy(seed)
        row = next(row for row in altered['scenes'][ab] if row['stage_id'] == post['id'])
        row['opp'] = 'M'
        mode = next(mode for mode in case['stage_modes']['B.post']
                    if mode['unit_id'] == 'CPU1' and mode['opp_id'] == 'M')
        exact_end = F(row['start_ms'])+F(mode['duration_ms'])
        self.assertGreater(exact_end, F(66))
        self.assertLess(exact_end, F(67))
        self.assertEqual(independent_check(case, altered)['reason'], 'deadline')
        self.assertFalse(row_accepts(model, structure_vector(model, altered)))
        self.assertTrue(any(F(o['end_ms']) == exact_end for o in model.options))

    def test_events_are_built_only_from_retained_option_ends_and_starts(self):
        case, mapping, seed, opened = fixture()
        budget = Budget(seconds=600)
        condition = condition_for(case, mapping, seed, opened, budget)
        with patch.object(neighborhood, 'filter_n1_options', wraps=neighborhood.filter_n1_options) as filtered:
            model = build(case, mapping, condition, budget=budget)
        self.assertEqual(filtered.call_count, 1)
        for sid, meta in model.scenes.items():
            options = [o for o in model.options if o['scenario_id'] == sid]
            expected = {F(0), F(case['window_ms'])/1000}
            expected.update(F(o[key])/1000 for o in options for key in ('start_ms', 'end_ms'))
            self.assertEqual(set(meta['events']), expected)
        self.assertNotIn(F(5, 1000), model.scenes[case['scenarios'][1]['id']]['events'])

    def test_closed_start_and_frequency_cannot_be_silently_propagated(self):
        case, mapping, seed, opened = fixture()
        budget = Budget(seconds=600)
        condition = condition_for(case, mapping, seed, opened, budget)
        before = deepcopy(condition)
        for kind in ('start', 'opp', 'unit'):
            changed = deepcopy(seed)
            sid = case['scenarios'][1]['id']
            row = next(row for row in changed['scenes'][sid] if '.main' in row['stage_id'])
            if kind == 'start':
                row['start_ms'] = '25'
            elif kind == 'opp':
                row['opp'] = 'M'
            else:
                row['unit'] = 'CPU2'
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                neighborhood.check_n1_candidate(case, condition, changed, budget=budget)
        self.assertEqual(condition, before)

    def test_budget_interruption_returns_no_partial_solver_model(self):
        case, mapping, seed, opened = fixture()
        budget = Budget(seconds=600)
        condition = condition_for(case, mapping, seed, opened, budget)
        before = deepcopy(case)
        real_filter = neighborhood.filter_n1_options
        def interrupt(instance, given, options, *, budget):
            real_filter(instance, given, options, budget=budget)
            raise Exhausted('fixture_interrupt_after_condition_filter')
        with patch.object(neighborhood, 'filter_n1_options', side_effect=interrupt):
            with self.assertRaises(Exhausted):
                build(case, mapping, condition, budget=budget)
        self.assertEqual(case, before)

    def test_empty_fixture_projection_stays_contradictory_without_fallback(self):
        case, mapping, seed, opened = fixture()
        budget = Budget(seconds=600)
        condition = condition_for(case, mapping, seed, opened, budget)
        starts = deepcopy(case['start_domain']['by_scene_stage_ms'])
        ab = case['scenarios'][0]['id']
        stage = next(stage['id'] for stage in case['scenarios'][0]['stage_instances']
                     if stage['shared_stage_id'] == 'B.post')
        # This extra empty restriction is named-fixture-only, not a change to
        # the declared N1 condition or a newly admissible SAFE seed.
        starts[ab][stage] = []
        model = build(case, mapping, condition, budget=budget, starts=starts)
        self.assertFalse(any(o['scenario_id'] == ab and o['stage_instance_id'] == stage
                             for o in model.options))
        self.assertTrue(model.preprocessing['empty_stage_option_sets'])
        self.assertTrue(any(not row['coef'] and row['rhs'] < 0 for row in model.rows))
        RECORDS['empty_projection'] = {'scope': 'extra empty named-fixture start subset only',
            'no_fallback': True, 'original_problem_infeasibility_proven': False}

    def test_production_explicit_trim_argument_remains_forbidden(self):
        case, mapping, seed, opened = fixture()
        case['id'] = 'not_a_fixture_n1_interface'
        budget = Budget(seconds=600)
        condition = condition_for(case, mapping, seed, opened, budget)
        with self.assertRaises(ValueError):
            build(case, mapping, condition, budget=budget,
                  starts=case['start_domain']['by_scene_stage_ms'])


if __name__ == '__main__':
    unittest.main()
