"""K129 fixed-unit conditions, exact small projections and receipt boundaries.

SAFE fixture energies are explicitly fabricated. Structural models omit
physics. No native solver, research optimization or real heat propagation is
performed. An archived K127 source supplies the default-array reference.
"""
from copy import deepcopy
from fractions import Fraction as F
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import fixed_unit_neighborhood as fixed
import fixed_unit_neighborhood_adapter as wrapper
import milp
import neighborhood as n1
import scene_adapter as adapter
from control_policy import with_auto_low_idle
from inputs import expand_options, load_config
from run_milp_precheck import candidate_key, independent_check, select_fixture
from schedules import validate_schedule
from test_auto_milp import row_accepts, structure_vector
from test_neighborhood_milp import (assert_solver_bytes_equal, base_input,
    expected_option_keys, mocked_physical, option_key, oracle_candidates)
from thermal import Budget, Exhausted


HERE = Path(__file__).resolve().parent
RECORDS = {'scope': 'mock SAFE receipt identities and exact small structural projection; '
                    'no physical SAFE claim or native/research solve'}


def fixture():
    base = base_input()
    ab, ac = [scene['id'] for scene in base['scenarios']]
    case, starts = select_fixture(base, 'fixed_unit_all_open',
        {ab: ['A.pre', 'B.pre'], ac: ['A.pre']}, {'A.pre': [0, 20], 'B.pre': [0, 20]})
    case['start_domain'] = {'version': 1, 'kind': 'explicit_grid_subset',
                            'by_scene_stage_ms': starts}
    case = with_auto_low_idle(case)
    seed, opened = {'scenes': {}}, {}
    for scene in case['scenarios']:
        sid = scene['id']
        seed['scenes'][sid] = [{'stage_id': stage['id'],
            'unit': 'CPU1' if stage['shared_stage_id'] == 'A.pre' else 'CPU2',
            'opp': 'H', 'start_ms': '0'} for stage in scene['stage_instances']]
        opened[sid] = [stage['id'] for stage in scene['stage_instances']]
    return case, {'A.pre': 'CPU1'}, seed, opened


def condition_for(case, mapping, seed, opened, budget):
    candidates = {sid: {'scenes': {sid: deepcopy(rows)}} for sid, rows in seed['scenes'].items()}
    with patch.object(adapter, 'evaluate_piecewise', side_effect=mocked_physical):
        receipts = {sid: adapter.evaluate_partial_scene(case, sid, mapping, candidate, budget=budget)
                    for sid, candidate in candidates.items()}
    receipt = adapter.aggregate_partial_scene_receipts(case, mapping, receipts, candidates, budget=budget)
    if receipt['state'] != 'SAFE':
        raise AssertionError('fabricated receipt fixture failed: ' + repr(receipt))
    return fixed.make_fixed_unit_condition(case, mapping, seed, receipt, opened, budget=budget)


def build(case, mapping, condition=None, *, budget=None, **extra):
    return milp.build_model(case, with_auto_low_idle(load_config()),
        budget=Budget(seconds=600) if budget is None else budget,
        include_physics=False, fixed_shared_deployment=mapping,
        neighborhood_condition=condition, **extra)


class FixedUnitConditionTests(unittest.TestCase):
    def setUp(self):
        self.case, self.mapping, self.seed, self.opened = fixture()
        self.budget = Budget(seconds=600)
        self.condition = condition_for(self.case, self.mapping, self.seed, self.opened, self.budget)

    def test_independent_protocol_json_roundtrip_and_source_dependencies(self):
        before = deepcopy((self.case, self.seed, self.condition))
        actual = fixed.validate_fixed_unit_condition(self.case,
            json.loads(json.dumps(self.condition)), budget=self.budget, shared_deployment=self.mapping)
        self.assertEqual(actual, self.condition)
        self.assertNotEqual(actual['protocol'], n1.PROTOCOL)
        self.assertEqual(set(actual['condition_dependency_sha256']), {'neighborhood.py'})
        self.assertNotEqual(actual['condition_source_sha256'], n1._source_hash())
        self.assertEqual(before, (self.case, self.seed, self.condition))

    def test_shared_unit_same_but_scene_opps_and_starts_may_differ(self):
        candidate = deepcopy(self.seed)
        ab, ac = list(candidate['scenes'])
        for row in candidate['scenes'][ab]:
            row['opp'] = 'M'  # Same CPU domain within AB, independent from AC.
        candidate['scenes'][ac][0].update(opp='L', start_ms='20')
        with patch.object(adapter, 'evaluate_piecewise', side_effect=AssertionError('no heat')):
            out = fixed.check_fixed_unit_candidate(self.case, self.condition, candidate, budget=self.budget)
        self.assertEqual(out['state'], 'FIXED_UNIT_MEMBER_SCHEDULE_VALID_THERMAL_UNCHECKED')
        self.assertEqual(out['legality']['shared_deployment']['A.pre'], 'CPU1')
        self.assertNotEqual(candidate['scenes'][ab][0]['opp'], candidate['scenes'][ac][0]['opp'])

    def test_wrong_shared_or_local_unit_rejected_without_repair(self):
        ab = self.case['scenarios'][0]['id']
        changed = deepcopy(self.seed)
        local = next(row for row in changed['scenes'][ab] if 'B.pre' in row['stage_id'])
        local.update(unit='CPU1', start_ms='20')
        self.assertEqual(validate_schedule(self.case, changed)['state'], 'SCHEDULE_VALID_THERMAL_UNCHECKED')
        before = deepcopy(changed)
        with self.assertRaisesRegex(ValueError, 'outside fixed-unit'):
            fixed.check_fixed_unit_candidate(self.case, self.condition, changed, budget=self.budget)
        self.assertEqual(changed, before)
        with self.assertRaisesRegex(ValueError, 'shared deployment condition mismatch'):
            fixed.validate_fixed_unit_condition(self.case, self.condition, budget=self.budget,
                                                shared_deployment={'A.pre': 'CPU2'})

    def test_opened_requires_every_scene_and_exactly_all_stages(self):
        sid = next(iter(self.opened))
        wrong = [{}, {**self.opened, 'unknown': []}]
        for value in ([], self.opened[sid][:-1], self.opened[sid] + [self.opened[sid][0]], ['unknown']):
            item = deepcopy(self.opened); item[sid] = value; wrong.append(item)
        for opened in wrong:
            with self.subTest(opened=opened), self.assertRaises(ValueError):
                fixed.make_fixed_unit_condition(self.case, self.mapping, self.seed,
                    self.condition['seed_receipt'], opened, budget=self.budget)

    def test_old_n1_still_rejects_shared_open_and_both_protocols_reject_each_other(self):
        with self.assertRaisesRegex(ValueError, 'only scene-local'):
            n1.make_n1_condition(self.case, self.mapping, self.seed,
                self.condition['seed_receipt'], self.opened, budget=self.budget)
        with self.assertRaises(ValueError):
            n1.validate_n1_condition(self.case, self.condition, budget=self.budget)
        opened = {sid: [stage for stage in stages if 'A.pre' not in stage]
                  for sid, stages in self.opened.items()}
        old = n1.make_n1_condition(self.case, self.mapping, self.seed,
            self.condition['seed_receipt'], opened, budget=self.budget)
        with self.assertRaises(ValueError):
            fixed.validate_fixed_unit_condition(self.case, old, budget=self.budget)

    def test_budget_dependency_hash_and_resealed_payload_cannot_be_substituted(self):
        with self.assertRaises(ValueError):
            fixed.validate_fixed_unit_condition(self.case, self.condition, budget=Budget(seconds=600))
        for key in ('condition_source_sha256', 'condition_dependency_sha256', 'seed_options_by_scene'):
            altered = deepcopy(self.condition)
            altered[key] = 'changed' if key == 'condition_source_sha256' else {}
            altered['condition_sha256'] = n1._condition_hash(altered)
            with self.subTest(key=key), self.assertRaises(ValueError):
                fixed.validate_fixed_unit_condition(self.case, altered, budget=self.budget)

    def test_filter_keeps_original_option_objects_for_every_seed_unit_only(self):
        options = expand_options(self.case, load_config(), budget=self.budget)
        before = deepcopy(options)
        units = {(sid, row['stage_id']): row['unit']
                 for sid, rows in self.seed['scenes'].items() for row in rows}
        expected = [o for o in options if o['unit_id'] == units[o['scenario_id'], o['stage_instance_id']]]
        kept, stats = fixed.filter_fixed_unit_options(self.case, self.condition, options, budget=self.budget)
        self.assertEqual(kept, expected)
        self.assertEqual(options, before)
        self.assertTrue(all(any(o is original for original in options) for o in kept))
        self.assertEqual(stats['after'], len(expected))
        self.assertTrue(stats['complete'])

    def test_incomplete_scene_and_interrupted_filter_cannot_return_success(self):
        sid = next(iter(self.seed['scenes']))
        local = {'scenes': {sid: deepcopy(self.seed['scenes'][sid])}}
        with self.assertRaises(ValueError):
            fixed.check_fixed_unit_candidate(self.case, self.condition, local, budget=self.budget)
        fixed.check_fixed_unit_candidate(self.case, self.condition, local,
                                        budget=self.budget, scene_id=sid)
        with patch.object(self.budget, 'check', side_effect=Exhausted('mock_expiry')):
            with self.assertRaises(Exhausted):
                fixed.filter_fixed_unit_options(self.case, self.condition, [], budget=self.budget)


class FixedUnitMilpTests(unittest.TestCase):
    def test_exact_small_cartesian_projection_and_original_domain_subset(self):
        case, mapping, seed, opened = fixture(); budget = Budget(seconds=600)
        condition = condition_for(case, mapping, seed, opened, budget)
        model = build(case, mapping, condition, budget=budget)
        self.assertEqual({option_key(o) for o in model.options}, expected_option_keys(case, seed, opened))
        candidates = list(oracle_candidates(case, seed, opened))
        expected = {candidate_key(c) for c in candidates if independent_check(case, c)['valid']}
        actual = {candidate_key(c) for c in candidates if row_accepts(model, structure_vector(model, c))}
        self.assertEqual(actual, expected)
        self.assertTrue(actual)
        self.assertLess(len(actual), len(candidates))  # includes incompatible CPU OPP overlaps
        original_options = expand_options(case, load_config())
        self.assertLess(len(model.options), len(original_options))
        self.assertTrue({option_key(o) for o in model.options} <= {option_key(o) for o in original_options})
        self.assertTrue(any(F(o['end_ms']).denominator != 1 for o in model.options))
        RECORDS['cartesian'] = {'assignments': len(candidates), 'legal': len(expected),
            'projection_equal': actual == expected, 'all_stages_open': True,
            'original_domain_subset': True, 'physical_models': 0}

    def test_per_scene_projection_preserves_all_seed_unit_opps_starts_and_nodes(self):
        case, mapping, seed, opened = fixture(); budget = Budget(seconds=600)
        condition = condition_for(case, mapping, seed, opened, budget)
        for scene in case['scenarios']:
            sid = scene['id']
            model = build(case, mapping, condition, budget=budget, fixed_scene_id=sid)
            self.assertEqual({option_key(o) for o in model.options},
                             {key for key in expected_option_keys(case, seed, opened) if key[0] == sid})
            self.assertEqual(model.instance['platform'], case['platform'])
            self.assertEqual(model.instance['scenarios'][0]['weight'], '1')
            for stage in scene['stage_instances']:
                self.assertEqual({o['opp_id'] for o in model.options if o['stage_instance_id'] == stage['id']},
                                 {'L', 'M', 'H'})

    def test_current_default_and_explicit_none_match_archived_k127_arrays(self):
        case, mapping, _, _ = fixture()
        snapshot = HERE / 'results/night_k127_run02/source_snapshot/research/chapter3_experiments/milp.py'
        source = snapshot.read_text(encoding='utf-8')
        namespace = {'__name__': '_k129_archived_milp', '__file__': str(HERE / 'milp.py')}
        exec(compile(source, str(snapshot), 'exec'), namespace)
        config = with_auto_low_idle(load_config())
        before = namespace['build_model'](case, config, include_physics=False,
            budget=Budget(seconds=600), fixed_shared_deployment=mapping)
        current = build(case, mapping)
        explicit = milp.build_model(case, config, include_physics=False,
            budget=Budget(seconds=600), fixed_shared_deployment=mapping, neighborhood_condition=None)
        for other in (current, explicit):
            assert_solver_bytes_equal(self, before, other)
            self.assertEqual(before.summary(), other.summary())
            for field in ('names', 'rows', 'options', 'shared', 'scenes', 'formulation'):
                self.assertEqual(getattr(before, field), getattr(other, field), field)
        RECORDS['default_reference'] = {'snapshot': str(snapshot.relative_to(HERE)),
            'all_eight_solver_arrays_equal': True, 'old_N1_source_unchanged': True}

    def test_unknown_protocol_and_missing_shared_condition_rejected_before_model(self):
        case, mapping, seed, opened = fixture(); budget = Budget(seconds=600)
        condition = condition_for(case, mapping, seed, opened, budget)
        config = with_auto_low_idle(load_config())
        with patch.object(milp, 'Model') as constructor:
            with self.assertRaises(ValueError):
                milp.build_model(case, config, budget=budget, neighborhood_condition=condition)
            wrong = deepcopy(condition); wrong['protocol'] = 'unknown'
            with self.assertRaises(ValueError):
                build(case, mapping, wrong, budget=budget)
        constructor.assert_not_called()


class FixedUnitAdapterTests(unittest.TestCase):
    def setUp(self):
        self.case, mapping, self.seed, opened = fixture(); self.budget = Budget(seconds=600)
        self.condition = condition_for(self.case, mapping, self.seed, opened, self.budget)
        self.sid = self.case['scenarios'][0]['id']
        self.local = {'scenes': {self.sid: deepcopy(self.seed['scenes'][self.sid])}}
        self.receipt = deepcopy(self.condition['seed_receipt']['scenes'][self.sid])

    def evaluate(self, **extra):
        return wrapper.evaluate_fixed_unit_scene(self.case, self.condition, self.sid,
                                                 self.local, budget=self.budget, **extra)

    def test_delegates_original_full_input_and_returns_identical_raw_receipt(self):
        before = deepcopy(self.receipt)
        with patch.object(wrapper, 'evaluate_partial_scene', return_value=self.receipt) as call:
            out = self.evaluate()
        self.assertIs(call.call_args.args[0], self.case)
        self.assertEqual(len(call.call_args.args[0]['scenarios']), 2)
        self.assertIs(out['receipt'], self.receipt)
        self.assertEqual(before, self.receipt)
        self.assertEqual(out['state'], 'SAFE')
        self.assertTrue(out['rankable_energy'])
        self.assertNotIn('weighted_energy_J', out)
        self.assertNotIn('safe_upper_bound_J', out)

    def test_unit_escape_rejected_before_original_evaluation(self):
        row = next(r for r in self.local['scenes'][self.sid] if 'B.pre' in r['stage_id'])
        row.update(unit='CPU1', start_ms='20')
        with patch.object(wrapper, 'evaluate_partial_scene') as call:
            out = self.evaluate()
        call.assert_not_called()
        self.assertEqual(out['state'], 'INVALID_INPUT')
        self.assertIsNone(out['receipt'])

    def test_committed_safe_and_violation_survive_expiry_during_return(self):
        for state in ('SAFE', 'THERMAL_VIOLATION'):
            with self.subTest(state=state):
                receipt = self.receipt if state == 'SAFE' else {
                    'state': state, 'reason': 'EXPLICIT_MOCK_POINT', 'violations': [{'node': 'CPU1'}]}
                original = self.budget.check
                def committed(*args):
                    self.budget.check = lambda: (_ for _ in ()).throw(Exhausted('after_inner_return'))
                    return receipt
                try:
                    with patch.object(wrapper, 'evaluate_partial_scene', side_effect=committed):
                        out = self.evaluate()
                finally:
                    self.budget.check = original
                self.assertIs(out['receipt'], receipt)
                self.assertEqual(out['state'], state)
                self.assertEqual(out['rankable_energy'], state == 'SAFE')

    def test_late_safe_and_unknown_are_retained_but_not_ranked(self):
        late = deepcopy(self.receipt); late['completed_at_elapsed_s'] = self.budget.seconds + 1
        unknown = {'state': 'UNRESOLVED', 'reason': 'EXPLICIT_MOCK_UNKNOWN'}
        for receipt in (late, unknown):
            with patch.object(wrapper, 'evaluate_partial_scene', return_value=receipt):
                out = self.evaluate()
            self.assertIs(out['receipt'], receipt)
            self.assertEqual(out['state'], 'UNRESOLVED')
            self.assertFalse(out['rankable_energy'])

    def test_accuracy_change_and_expired_budget_stop_before_original_evaluation(self):
        with patch.object(wrapper, 'evaluate_partial_scene') as call:
            changed = self.evaluate(accuracy={'energy_absolute_error_J': '0.1'})
            self.assertEqual(changed['state'], 'INVALID_INPUT')
            self.budget.check = lambda: (_ for _ in ()).throw(Exhausted('expired'))
            expired = self.evaluate()
        call.assert_not_called()
        self.assertEqual(expired['state'], 'UNRESOLVED')


if __name__ == '__main__':
    unittest.main()
