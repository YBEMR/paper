"""N1 identity/domain checks using explicitly mocked physical receipts.

No solver, thermal propagation or research input/result is executed. Existing
small-case constructors only supply original legal identity fixtures; their
fabricated SAFE energies test receipt lifecycle, not physical safety.
"""
from copy import deepcopy
from fractions import Fraction
import json
import unittest
from unittest.mock import patch

from inputs import expand_options, load_config
import neighborhood as n1
import scene_adapter as adapter
from schedules import validate_schedule
from test_partial_deployment import small_case, matching_receipts
from thermal import Budget, Exhausted


def mock_condition_fixture(*, budget=None, accuracy=None):
    """Return make_n1_condition kwargs; SAFE physics is explicitly fabricated."""
    instance, mapping, candidates = small_case()
    budget = Budget(seconds=600) if budget is None else budget
    seed = {'scenes': {sid: deepcopy(candidate['scenes'][sid])
                       for sid, candidate in candidates.items()}}
    receipts = matching_receipts(instance, mapping, candidates, budget, accuracy)
    receipt = adapter.aggregate_partial_scene_receipts(
        instance, mapping, receipts, candidates, accuracy=accuracy, budget=budget)
    opened = {sid: [row['stage_id'] for row in rows if 'A.pre' not in row['stage_id']]
              for sid, rows in seed['scenes'].items()}
    return {'instance': instance, 'shared_deployment': mapping,
            'seed_candidate': seed, 'seed_receipt': receipt,
            'open_stage_ids_by_scene': opened, 'budget': budget, 'accuracy': accuracy}


class N1ConditionTests(unittest.TestCase):
    def setUp(self):
        fixture = mock_condition_fixture()
        self.instance = fixture['instance']; self.mapping = fixture['shared_deployment']
        self.budget = fixture['budget']; self.seed = fixture['seed_candidate']
        self.receipt = fixture['seed_receipt']; self.opened = fixture['open_stage_ids_by_scene']
        self.assertEqual(self.receipt['state'], 'SAFE')  # mocked energy only
        self.condition = self.make()

    def make(self, **overrides):
        args = dict(instance=self.instance, shared_deployment=self.mapping,
            seed_candidate=self.seed, seed_receipt=self.receipt,
            open_stage_ids_by_scene=self.opened, budget=self.budget)
        args.update(overrides)
        return n1.make_n1_condition(**args)

    def reseal(self, condition):
        condition['condition_sha256'] = n1._condition_hash(condition)
        return condition

    def test_json_roundtrip_and_original_input_seed_receipt_unchanged(self):
        before = deepcopy((self.instance, self.mapping, self.seed, self.receipt))
        result = n1.validate_n1_condition(self.instance, json.loads(json.dumps(self.condition)),
                                        budget=self.budget, shared_deployment=self.mapping)
        self.assertEqual(result, self.condition)
        self.assertEqual(before, (self.instance, self.mapping, self.seed, self.receipt))
        self.assertIsNot(result, self.condition)

    def test_seed_is_member_without_thermal_reevaluation(self):
        with patch.object(adapter, 'evaluate_piecewise', side_effect=AssertionError('no heat')):
            result = n1.check_n1_candidate(self.instance, self.condition, self.seed, budget=self.budget)
        self.assertEqual(result['state'], 'N1_MEMBER_SCHEDULE_VALID_THERMAL_UNCHECKED')
        self.assertEqual(set(result['scene_ids']), set(self.seed['scenes']))

    def test_filter_matches_independent_fixed_unit_closed_stage_predicate(self):
        options = expand_options(self.instance, load_config(), budget=self.budget)
        original = deepcopy(options)
        expected = []
        seed = {(sid, row['stage_id']): row for sid, rows in self.seed['scenes'].items() for row in rows}
        for option in options:
            sid, stage_id = option['scenario_id'], option['stage_instance_id']
            row = seed[sid, stage_id]
            if (option['unit_id'] == row['unit'] and
                    (stage_id in self.opened[sid] or
                     option['opp_id'] == row['opp'] and Fraction(option['start_ms']) == Fraction(row['start_ms']))):
                expected.append(option)
        kept, stats = n1.filter_n1_options(self.instance, self.condition, options, budget=self.budget)
        self.assertEqual(kept, expected)
        self.assertEqual(options, original)
        self.assertTrue(all(any(item is source for source in options) for item in kept))
        self.assertEqual(stats['before'], len(options))
        self.assertEqual(stats['after'], len(expected))
        self.assertEqual(stats['removed'], len(options)-len(expected))
        self.assertIs(stats['complete'], True)

    def test_option_scene_subset_preserves_all_original_legal_modes_and_starts(self):
        sid = next(iter(self.seed['scenes']))
        options = [o for o in expand_options(self.instance, load_config()) if o['scenario_id'] == sid]
        kept, stats = n1.filter_n1_options(self.instance, self.condition, options, budget=self.budget)
        local = self.opened[sid][0]
        fixed_unit = next(r['unit'] for r in self.seed['scenes'][sid] if r['stage_id'] == local)
        expected = [o for o in options if o['stage_instance_id'] == local and o['unit_id'] == fixed_unit]
        self.assertEqual([o for o in kept if o['stage_instance_id'] == local], expected)
        self.assertEqual(stats['before'], len(options))

    def test_empty_open_lists_are_valid_fully_fixed_condition(self):
        condition = self.make(open_stage_ids_by_scene={sid: [] for sid in self.opened})
        kept, _ = n1.filter_n1_options(self.instance, condition,
                                     expand_options(self.instance, load_config()), budget=self.budget)
        self.assertEqual(len(kept), sum(map(len, self.seed['scenes'].values())))

    def test_missing_unknown_duplicate_and_shared_open_id_rejected(self):
        sid = next(iter(self.opened))
        cases = [{}, dict(self.opened, nonexistent=[])]
        value = self.opened[sid][0]
        duplicate = deepcopy(self.opened); duplicate[sid] = [value, value]; cases.append(duplicate)
        unknown = deepcopy(self.opened); unknown[sid] = ['not-a-stage']; cases.append(unknown)
        shared = deepcopy(self.opened)
        shared[sid] = [r['stage_id'] for r in self.seed['scenes'][sid] if 'A.pre' in r['stage_id']]
        cases.append(shared)
        for opened in cases:
            with self.subTest(opened=opened), self.assertRaises(ValueError):
                self.make(open_stage_ids_by_scene=opened)

    def test_new_budget_or_changed_physics_input_cannot_reuse_condition(self):
        with self.assertRaises(ValueError):
            n1.validate_n1_condition(self.instance, self.condition, budget=Budget(seconds=600))
        changed = deepcopy(self.instance); changed['platform']['external_common_power_W'] = '999'
        with self.assertRaises(ValueError):
            n1.validate_n1_condition(changed, self.condition, budget=self.budget)

    def test_modified_condition_and_resealed_derived_payload_are_rejected(self):
        changed = deepcopy(self.condition); changed['opened_by_scene'] = {}
        with self.assertRaises(ValueError):
            n1.validate_n1_condition(self.instance, changed, budget=self.budget)
        changed = deepcopy(self.condition)
        sid = next(iter(changed['seed_options_by_scene']))
        stage = next(iter(changed['seed_options_by_scene'][sid]))
        changed['seed_options_by_scene'][sid][stage]['start_ms'] = '999'
        with self.assertRaises(ValueError):
            n1.validate_n1_condition(self.instance, self.reseal(changed), budget=self.budget)

    def test_safe_string_without_full_receipt_and_wrong_payload_hash_rejected(self):
        for receipt in ({'state': 'SAFE'}, dict(self.receipt, receipt_sha256='not-valid')):
            with self.subTest(receipt=receipt), self.assertRaises(ValueError):
                self.make(seed_receipt=receipt)

    def test_wrong_source_and_late_aggregate_or_inner_receipt_rejected(self):
        bad_source = deepcopy(self.receipt)
        bad_source['identity']['source_sha256']['schedules.py'] = 'changed'
        bad_source['receipt_sha256'] = adapter._receipt_hash(bad_source)
        late = deepcopy(self.receipt); late['completed_at_elapsed_s'] = self.budget.seconds
        late['receipt_sha256'] = adapter._receipt_hash(late)
        bad_inner = deepcopy(self.receipt)
        sid = next(iter(bad_inner['scenes']))
        bad_inner['scenes'][sid]['result']['completed_at_elapsed_s'] = self.budget.seconds
        bad_inner['scenes'][sid]['receipt_sha256'] = adapter._receipt_hash(bad_inner['scenes'][sid])
        bad_inner['receipt_sha256'] = adapter._receipt_hash(bad_inner)
        for receipt in (bad_source, late, bad_inner):
            with self.subTest(reason=receipt.get('completed_at_elapsed_s')), self.assertRaises(ValueError):
                self.make(seed_receipt=receipt)

    def test_original_legal_device_change_is_outside_N1(self):
        sid = next(iter(self.seed['scenes']))
        candidate = {'scenes': {sid: deepcopy(self.seed['scenes'][sid])}}
        row = next(r for r in candidate['scenes'][sid] if r['stage_id'] in self.opened[sid])
        row.update(unit='CPU1', start_ms='20')
        checked = validate_schedule(adapter.make_scene_instance(self.instance, sid), candidate)
        self.assertEqual(checked['state'], 'SCHEDULE_VALID_THERMAL_UNCHECKED')
        with self.assertRaisesRegex(ValueError, 'outside N1'):
            n1.check_n1_candidate(self.instance, self.condition, candidate, budget=self.budget, scene_id=sid)

    def test_closed_start_not_propagated_and_equal_fraction_start_is_accepted(self):
        sid = next(iter(self.seed['scenes']))
        candidate = {'scenes': {sid: deepcopy(self.seed['scenes'][sid])}}
        row = next(r for r in candidate['scenes'][sid] if r['stage_id'] not in self.opened[sid])
        row['start_ms'] = '0/7'
        n1.check_n1_candidate(self.instance, self.condition, candidate, budget=self.budget, scene_id=sid)
        row['start_ms'] = '20'
        before = deepcopy(candidate)
        with self.assertRaisesRegex(ValueError, 'outside N1'):
            n1.check_n1_candidate(self.instance, self.condition, candidate, budget=self.budget, scene_id=sid)
        self.assertEqual(candidate, before)

    def test_incomplete_or_implicit_scene_projection_is_rejected(self):
        sid = next(iter(self.seed['scenes']))
        projected = {'scenes': {sid: deepcopy(self.seed['scenes'][sid])}}
        with self.assertRaises(ValueError):
            n1.check_n1_candidate(self.instance, self.condition, projected, budget=self.budget)
        projected['scenes'][sid].pop()
        with self.assertRaises(ValueError):
            n1.check_n1_candidate(self.instance, self.condition, projected, budget=self.budget, scene_id=sid)

    def test_interrupt_never_returns_partial_successful_filter_stats(self):
        options = expand_options(self.instance, load_config())
        original_check = self.budget.check
        checks = 0
        def interrupted():
            nonlocal checks
            checks += 1
            if checks == 2:
                raise Exhausted('mock_interrupted_N1_filter')
            original_check()
        with patch.object(self.budget, 'check', side_effect=interrupted), self.assertRaises(Exhausted):
            n1.filter_n1_options(self.instance, self.condition, options, budget=self.budget)


if __name__ == '__main__':
    unittest.main()
