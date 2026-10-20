"""K139 exact linked-domain projection and budget-local receipt checks.

Mock SAFE energies certify only identity/control flow. Structural models omit
physics. All Cartesian choices are derived independently from the original
mode/start domain; no optimizer, native worker or research instance is solved.
"""
from copy import deepcopy
from fractions import Fraction as F
from itertools import product
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import linked_neighborhood as linked
import linked_neighborhood_adapter as wrapper
import fixed_unit_neighborhood as fixed
import milp
import neighborhood as n1
import scene_adapter as adapter
from control_policy import with_auto_low_idle
from inputs import expand_options, load_config
from run_milp_precheck import candidate_key, independent_check, select_fixture
from schedules import validate_schedule
from test_auto_milp import row_accepts, structure_vector
from test_neighborhood_milp import (assert_solver_bytes_equal, base_input,
    condition_for as old_condition_for, fixture as old_fixture,
    mocked_physical, option_key)
from thermal import Budget, Exhausted


RECORDS = {'scope': 'K139 mock-receipt and exact small structural projection',
           'native_calls': 0, 'research_calls': 0, 'original_scale_models': 0,
           'structural': {}, 'mock': {}}


def fixture():
    base = base_input()
    selected, starts = {}, {'A.pre': [0, 20]}
    for scene in base['scenarios']:
        local = 'B' if scene['id'].startswith('AB') else 'C'
        selected[scene['id']] = ['A.pre']+[local+'.'+p for p in ('pre', 'main', 'post')]
        starts.update({local+'.pre': [0, 20], local+'.main': [20, 25],
                       local+'.post': [60, 85]})
    case, by_stage = select_fixture(base, 'linked_warm_closed', selected, starts)
    case['start_domain'] = {'version': 1, 'kind': 'explicit_grid_subset',
                            'by_scene_stage_ms': by_stage}
    case = with_auto_low_idle(case)
    seed, opened = {'scenes': {}}, {}
    for scene in case['scenarios']:
        sid = scene['id']; rows = []; opened[sid] = []
        for stage in scene['stage_instances']:
            shared = stage['shared_stage_id']
            if shared == 'A.pre':
                unit, start = 'CPU1', '0'; opened[sid].append(stage['id'])
            elif shared.endswith('.pre'):
                unit, start = 'CPU2', '0'; opened[sid].append(stage['id'])
            elif shared.endswith('.main'):
                unit, start = ('NPU0' if shared.startswith('B.') else 'GPU0'), '20'
            else:
                unit, start = 'CPU1', '85'
            rows.append({'stage_id': stage['id'], 'unit': unit, 'opp': 'H', 'start_ms': start})
        seed['scenes'][sid] = rows
    warm = deepcopy(seed)
    for rows in warm['scenes'].values():
        for row in rows:
            if '.main' in row['stage_id'] or '.post' in row['stage_id']:
                row['opp'] = 'M'
            if '.post' in row['stage_id']:
                row['start_ms'] = '255/3'  # exact 85, never a rounded representation
    return case, {'A.pre': 'CPU1'}, seed, warm, opened


def aggregate(case, mapping, candidate, budget, accuracy=None):
    parts = {sid: {'scenes': {sid: deepcopy(rows)}}
             for sid, rows in candidate['scenes'].items()}
    with patch.object(adapter, 'evaluate_piecewise', side_effect=mocked_physical):
        receipts = {sid: adapter.evaluate_partial_scene(case, sid, mapping, part,
                        accuracy, budget) for sid, part in parts.items()}
    result = adapter.aggregate_partial_scene_receipts(case, mapping, receipts,
                                                       parts, accuracy, budget)
    if result['state'] != 'SAFE':
        raise AssertionError('Mock matching receipt fixture is structurally invalid: '+repr(result))
    return result


def condition_for(case, mapping, seed, warm, opened, budget):
    first = aggregate(case, mapping, seed, budget)
    latest = aggregate(case, mapping, warm, budget)
    return linked.make_linked_condition(case, mapping, seed, first, opened,
        warm_candidate=warm, warm_receipt=latest, budget=budget)


def oracle_dimensions(case, seed, warm, opened):
    """Independent Cartesian intersection, without any production membership code."""
    dimensions = []
    for scene in case['scenarios']:
        sid = scene['id']
        initial = {r['stage_id']: r for r in seed['scenes'][sid]}
        anchor = {r['stage_id']: r for r in warm['scenes'][sid]}
        requests = {r['id']: r for r in scene['requests']}
        for stage in scene['stage_instances']:
            choices = []
            for mode in case['stage_modes'][stage['shared_stage_id']]:
                if mode['unit_id'] != initial[stage['id']]['unit']:
                    continue
                for value in case['start_domain']['by_scene_stage_ms'][sid][stage['id']]:
                    when, end = F(value), F(value)+F(mode['duration_ms'])
                    if when < F(requests[stage['request_id']]['release_ms']) or end > F(case['window_ms']):
                        continue
                    fixed = anchor[stage['id']]
                    if stage['id'] not in opened[sid] and (
                            mode['opp_id'] != fixed['opp'] or when != F(fixed['start_ms'])):
                        continue
                    choices.append((sid, {'stage_id': stage['id'], 'unit': mode['unit_id'],
                        'opp': mode['opp_id'], 'start_ms': str(when)}, end))
            dimensions.append(choices)
    return dimensions


def oracle_candidates(case, seed, warm, opened):
    for values in product(*oracle_dimensions(case, seed, warm, opened)):
        candidate = {'scenes': {s['id']: [] for s in case['scenarios']}}
        for sid, row, _ in values:
            candidate['scenes'][sid].append(deepcopy(row))
        yield candidate


def build(case, mapping, condition, budget, **extra):
    return milp.build_model(case, with_auto_low_idle(load_config()), budget=budget,
        include_physics=False, fixed_shared_deployment=mapping,
        neighborhood_condition=condition, **extra)


class LinkedConditionTests(unittest.TestCase):
    def setUp(self):
        self.case, self.mapping, self.seed, self.warm, self.opened = fixture()
        self.budget = Budget(seconds=600)
        self.condition = condition_for(self.case, self.mapping, self.seed,
                                      self.warm, self.opened, self.budget)

    def test_roundtrip_separate_original_units_and_latest_closed_anchor(self):
        before = deepcopy((self.case, self.seed, self.warm, self.condition))
        loaded = linked.validate_linked_condition(self.case,
            json.loads(json.dumps(self.condition)), budget=self.budget,
            shared_deployment=self.mapping)
        self.assertEqual(loaded, self.condition)
        self.assertNotEqual(loaded['protocol'], n1.PROTOCOL)
        for sid, rows in loaded['warm_options_by_scene'].items():
            for stage, row in rows.items():
                self.assertEqual(row['unit'], loaded['seed_options_by_scene'][sid][stage]['unit'])
                if stage not in self.opened[sid]:
                    self.assertEqual(row['opp'], 'M')
                    self.assertEqual(loaded['seed_options_by_scene'][sid][stage]['opp'], 'H')
        self.assertEqual(before, (self.case, self.seed, self.warm, self.condition))

    def test_warm_member_seed_outside_and_exact_closed_start_not_repaired(self):
        accepted = linked.check_linked_candidate(self.case, self.condition,
                                                  self.warm, budget=self.budget)
        self.assertIn('THERMAL_UNCHECKED', accepted['state'])
        before = deepcopy(self.seed)
        with self.assertRaises(ValueError):
            linked.check_linked_candidate(self.case, self.condition, self.seed, budget=self.budget)
        self.assertEqual(self.seed, before)
        changed = deepcopy(self.warm)
        sid = next(iter(changed['scenes']))
        post = next(r for r in changed['scenes'][sid] if '.post' in r['stage_id'])
        post['start_ms'] = '60'
        self.assertNotEqual(validate_schedule(self.case, changed)['state'],
                            'SCHEDULE_VALID_THERMAL_UNCHECKED')
        with self.assertRaises(ValueError):
            linked.check_linked_candidate(self.case, self.condition, changed, budget=self.budget)
        self.assertEqual(post['start_ms'], '60')

    def test_warm_changed_local_unit_even_with_matching_receipt_is_rejected(self):
        warm = deepcopy(self.warm)
        for rows in warm['scenes'].values():
            next(r for r in rows if '.post' in r['stage_id'])['unit'] = 'CPU2'
        # A complete valid warm receipt is insufficient if its unit assignment
        # differs from this invocation's original fixed-unit declaration.
        receipt = aggregate(self.case, self.mapping, warm, self.budget)
        with self.assertRaises(ValueError):
            linked.make_linked_condition(self.case, self.mapping, self.seed,
                self.condition['seed_receipt'], self.opened, warm_candidate=warm,
                warm_receipt=receipt, budget=self.budget)

    def test_invalid_scope_empty_all_open_missing_duplicate_or_unknown_rejected(self):
        sid = next(iter(self.opened)); wrong = [{}, {**self.opened, 'unknown': []}]
        all_ids = [r['stage_id'] for r in self.seed['scenes'][sid]]
        for value in ([], all_ids, self.opened[sid]+[self.opened[sid][0]], ['unknown']):
            item = deepcopy(self.opened); item[sid] = value; wrong.append(item)
        for opened in wrong:
            with self.subTest(opened=opened), self.assertRaises(ValueError):
                linked.make_linked_condition(self.case, self.mapping, self.seed,
                    self.condition['seed_receipt'], opened, warm_candidate=self.warm,
                    warm_receipt=self.condition['warm_receipt'], budget=self.budget)

    def test_budget_source_receipt_anchor_and_scope_mutations_rejected(self):
        with self.assertRaises(ValueError):
            linked.validate_linked_condition(self.case, self.condition, budget=Budget(seconds=600))
        for field in ('condition_source_sha256', 'condition_dependency_sha256',
                      'warm_options_by_scene', 'seed_options_by_scene'):
            changed = deepcopy(self.condition)
            changed[field] = 'changed' if field.endswith('source_sha256') else {}
            changed['condition_sha256'] = n1._condition_hash(changed)
            with self.subTest(field=field), self.assertRaises(ValueError):
                linked.validate_linked_condition(self.case, changed, budget=self.budget)
        for field in ('warm_candidate', 'warm_receipt', 'opened_by_scene'):
            changed = deepcopy(self.condition); changed[field] = {}
            with self.subTest(field=field), self.assertRaises(ValueError):
                linked.validate_linked_condition(self.case, changed, budget=self.budget)
        changed = deepcopy(self.case); changed['id'] += '_changed'
        with self.assertRaises(ValueError):
            linked.validate_linked_condition(changed, self.condition, budget=self.budget)

    def test_incomplete_or_future_warm_and_changed_accuracy_rejected(self):
        incomplete = deepcopy(self.condition['warm_receipt']); incomplete['state'] = 'UNRESOLVED'
        late = deepcopy(self.condition['warm_receipt'])
        late['completed_at_elapsed_s'] = self.budget.seconds
        for receipt in (incomplete, late, self.condition['seed_receipt']):
            with self.subTest(receipt=receipt['state']), self.assertRaises(ValueError):
                linked.make_linked_condition(self.case, self.mapping, self.seed,
                    self.condition['seed_receipt'], self.opened, warm_candidate=self.warm,
                    warm_receipt=receipt, budget=self.budget)
        with self.assertRaises(ValueError):
            linked.make_linked_condition(self.case, self.mapping, self.seed,
                self.condition['seed_receipt'], self.opened, warm_candidate=self.warm,
                warm_receipt=self.condition['warm_receipt'], budget=self.budget,
                accuracy={'energy_absolute_error_J': '1/1000000000000'})
        with patch.object(self.budget, 'check', side_effect=Exhausted('mock_expired')):
            with self.assertRaises(Exhausted):
                linked.filter_linked_options(self.case, self.condition, [], budget=self.budget)

    def test_shared_A_scene_OPP_independent_and_local_closed_choice_preserved(self):
        candidate = deepcopy(self.warm)
        ab, ac = list(candidate['scenes'])
        for row in candidate['scenes'][ab]:
            if row['stage_id'] in self.opened[ab]:
                row['opp'] = 'M'
        next(r for r in candidate['scenes'][ac] if 'A.pre' in r['stage_id'])['start_ms'] = '20'
        result = linked.check_linked_candidate(self.case, self.condition, candidate, budget=self.budget)
        self.assertEqual(result['legality']['shared_deployment']['A.pre'], 'CPU1')
        a = [next(r for r in rows if 'A.pre' in r['stage_id']) for rows in candidate['scenes'].values()]
        self.assertEqual({r['opp'] for r in a}, {'H', 'M'})
        self.assertEqual({r['start_ms'] for r in a}, {'0', '20'})

    def test_adapter_delegates_full_original_input_and_rejects_closed_reset(self):
        sid = next(iter(self.warm['scenes']))
        candidate = {'scenes': {sid: deepcopy(self.warm['scenes'][sid])}}
        receipt = self.condition['warm_receipt']['scenes'][sid]
        with patch.object(wrapper, 'evaluate_partial_scene', return_value=receipt) as call:
            result = wrapper.evaluate_linked_scene(self.case, self.condition, sid, candidate,
                                                    budget=self.budget)
        self.assertIs(call.call_args.args[0], self.case)
        self.assertIs(result['receipt'], receipt)
        self.assertTrue(result['rankable_energy'])
        candidate['scenes'][sid] = deepcopy(self.seed['scenes'][sid])
        with patch.object(wrapper, 'evaluate_partial_scene') as call:
            result = wrapper.evaluate_linked_scene(self.case, self.condition, sid, candidate,
                                                    budget=self.budget)
        call.assert_not_called()
        self.assertEqual(result['state'], 'INVALID_INPUT')
        self.assertIsNone(result['receipt'])


class LinkedProjectionTests(unittest.TestCase):
    def test_exact_cartesian_projection_matches_original_legality_and_filtered_options(self):
        case, mapping, seed, warm, opened = fixture(); budget = Budget(seconds=600)
        condition = condition_for(case, mapping, seed, warm, opened, budget)
        model = build(case, mapping, condition, budget)
        dimensions = oracle_dimensions(case, seed, warm, opened)
        expected_options = {(sid, row['stage_id'], row['unit'], row['opp'], F(row['start_ms']), end)
                            for dimension in dimensions for sid, row, end in dimension}
        self.assertEqual({option_key(o) for o in model.options}, expected_options)
        originals = expand_options(case, load_config(), budget=budget)
        before = deepcopy(originals)
        filtered, stats = linked.filter_linked_options(case, condition, originals, budget=budget)
        self.assertEqual({option_key(o) for o in filtered}, expected_options)
        self.assertTrue(all(any(o is original for original in originals) for o in filtered))
        self.assertEqual(originals, before); self.assertTrue(stats['complete'])
        candidates = list(oracle_candidates(case, seed, warm, opened))
        expected = {candidate_key(c) for c in candidates if independent_check(case, c)['valid']}
        actual = {candidate_key(c) for c in candidates if row_accepts(model, structure_vector(model, c))}
        self.assertEqual(actual, expected); self.assertTrue(actual)
        self.assertLess(len(actual), len(candidates))
        reasons = {independent_check(case, c).get('reason') for c in candidates}
        self.assertIn('dependency', reasons); self.assertIn('busy_domain_conflict', reasons)
        self.assertTrue(any(F(o['end_ms']).denominator != 1 for o in model.options))
        self.assertTrue(independent_check(case, warm)['valid'])  # same-frequency CPU overlap
        RECORDS['structural']['cartesian'] = {'assignments': len(candidates), 'legal': len(expected),
            'projection_equal': actual == expected, 'option_projection_equal': True,
            'rejection_reasons': sorted(r for r in reasons if r), 'physical_models': 0,
            'closed_anchor_differs_from_original_seed': True}

    def test_per_scene_model_retains_full_platform_and_warm_closed_exact_values(self):
        case, mapping, seed, warm, opened = fixture(); budget = Budget(seconds=600)
        condition = condition_for(case, mapping, seed, warm, opened, budget)
        for scene in case['scenarios']:
            sid = scene['id']; model = build(case, mapping, condition, budget, fixed_scene_id=sid)
            self.assertEqual(model.instance['platform'], case['platform'])
            self.assertEqual(model.instance['execution_rules'], case['execution_rules'])
            self.assertEqual(model.instance['scenarios'][0]['weight'], '1')
            for row in warm['scenes'][sid]:
                options = [o for o in model.options if o['stage_instance_id'] == row['stage_id']]
                self.assertEqual({o['unit_id'] for o in options}, {row['unit']})
                if row['stage_id'] not in opened[sid]:
                    self.assertEqual({(o['opp_id'], F(o['start_ms'])) for o in options},
                                     {(row['opp'], F(row['start_ms']))})
                else:
                    self.assertEqual({o['opp_id'] for o in options}, {'L', 'M', 'H'})

    def test_fractional_deadline_boundary_is_exact_and_not_rounded(self):
        case, mapping, seed, warm, opened = fixture()
        # A.pre remains open; its exact M duration is 34/3 ms. Restrict the
        # corresponding request to that boundary, leaving a feasible H seed.
        target = case['scenarios'][0]
        stage = next(s for s in target['stage_instances'] if s['shared_stage_id'] == 'A.pre')
        mode = next(m for m in case['stage_modes']['A.pre']
                    if m['unit_id'] == 'CPU1' and m['opp_id'] == 'M')
        deadline = F(mode['duration_ms'])
        next(r for r in target['requests'] if r['id'] == stage['request_id'])['deadline_ms'] = str(deadline)
        budget = Budget(seconds=600); condition = condition_for(case, mapping, seed, warm, opened, budget)
        model = build(case, mapping, condition, budget)
        good = deepcopy(warm); bad = deepcopy(warm)
        next(r for r in good['scenes'][target['id']] if r['stage_id'] == stage['id'])['opp'] = 'M'
        # Match concurrent local CPU frequency to avoid making this a domain
        # conflict test instead of the intended exact deadline test.
        next(r for r in good['scenes'][target['id']] if '.pre' in r['stage_id'] and r['stage_id'] != stage['id'])['opp'] = 'M'
        bad = deepcopy(good)
        next(r for r in bad['scenes'][target['id']] if r['stage_id'] == stage['id'])['opp'] = 'L'
        self.assertTrue(independent_check(case, good)['valid'])
        self.assertEqual(independent_check(case, bad)['reason'], 'deadline')
        self.assertTrue(row_accepts(model, structure_vector(model, good)))
        self.assertFalse(row_accepts(model, structure_vector(model, bad)))
        RECORDS['structural']['deadline'] = {'deadline_ms': str(deadline),
            'exact_boundary_accepted': True, 'longer_L_rejected': True}

    def test_three_old_dispatch_paths_match_frozen_k138_solver_arrays(self):
        case, mapping, seed, old_opened = old_fixture()
        budget = Budget(seconds=600)
        old = old_condition_for(case, mapping, seed, old_opened, budget)
        all_opened = {sid: [r['stage_id'] for r in rows] for sid, rows in seed['scenes'].items()}
        full = fixed.make_fixed_unit_condition(case, mapping, seed, old['seed_receipt'],
                                               all_opened, budget=budget)
        here = Path(__file__).resolve().parent
        snapshot = here/'results/staged_quality_pair01/source_snapshot/research/chapter3_experiments/milp.py'
        namespace = {'__name__': '_k139_frozen_k138_milp', '__file__': str(here/'milp.py')}
        exec(compile(snapshot.read_text(encoding='utf-8'), str(snapshot), 'exec'), namespace)
        config = with_auto_low_idle(load_config()); checks = []
        for name, condition in (('default', None), ('N1', old), ('all_stage', full)):
            kwargs = dict(budget=budget, include_physics=False,
                          fixed_shared_deployment=mapping, neighborhood_condition=condition)
            previous = namespace['build_model'](case, config, **kwargs)
            current = milp.build_model(case, config, **kwargs)
            assert_solver_bytes_equal(self, previous, current)
            for field in ('rows', 'options', 'names', 'scenes', 'formulation'):
                self.assertEqual(getattr(previous, field), getattr(current, field), (name, field))
            self.assertEqual(previous.summary(), current.summary(), name)
            checks.append({'path': name, 'all_eight_solver_arrays_equal': True,
                           'rows_options_names_scenes_formulation_summary_equal': True})
        RECORDS['structural']['old_dispatch_regression'] = {'source_snapshot': str(snapshot.relative_to(here)),
            'checks': checks, 'physical_models': 0}


if __name__ == '__main__':
    unittest.main(verbosity=2)
