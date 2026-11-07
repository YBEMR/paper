"""Optional cumulative-row integration checks on small correctness fixtures.

All constructed models use include_physics=False. The independent exact
one-edge oracle is the K120 module; complete scheduling enumeration reuses
the existing small-fixture Cartesian oracle. No solve or heat evaluation.
"""
from copy import deepcopy
from fractions import Fraction as F
from itertools import product
import inspect
import unittest
from unittest.mock import patch

import numpy as np

from inputs import load_config
import milp
from precedence_check import build_precedence_system
from run_milp_precheck import (fixtures, independent_assignments,
                              independent_check)
from run_scene_precheck import row_acceptance
from thermal import Budget, Exhausted


RECORDS = {}


def row_accepts(rows, selected):
    return all(sum((F(coefficient)*selected.get(y, F(0))
                    for y, coefficient in row['coef'].items()), F(0))
               <= F(row['rhs']) for row in rows)


class InterruptBudget(Budget):
    def __init__(self):
        super().__init__(seconds=600)
        self.fail_after = None
        self.armed_checks = 0

    def arm(self, fail_after):
        self.fail_after = fail_after
        self.armed_checks = 0

    def check(self):
        super().check()
        if self.fail_after is not None:
            self.armed_checks += 1
            if self.armed_checks >= self.fail_after:
                raise Exhausted('fixture_cumulative_generation_interruption')


class RowCollector:
    """No model construction: expose only the append contract of the helper."""
    def __init__(self, budget=None):
        self.budget = budget if budget is not None else Budget(seconds=600)
        self.rows = []

    def le(self, coefficients, rhs, tag):
        self.budget.check()
        self.rows.append({'coef': dict(coefficients), 'rhs': rhs, 'tag': tag})


class CumulativePrecedenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config()
        cls.fixture_map = fixtures(cls.config)
        cls.instance, cls.starts = deepcopy(cls.fixture_map['chain_fractional'])
        cls.omitted = cls.build(cls.instance, cls.starts)
        cls.current = cls.build(cls.instance, cls.starts, cumulative_precedence=False)
        cls.strengthened = cls.build(cls.instance, cls.starts, cumulative_precedence=True)

    @classmethod
    def build(cls, instance, starts, **kwargs):
        return milp.build_model(instance, cls.config, starts=starts,
            include_physics=False, budget=kwargs.pop('budget', Budget(seconds=600)),
            **kwargs)

    def assert_solver_bytes_equal(self, left, right, rows=None):
        before, after = left.as_solver_dict(), right.as_solver_dict()
        if rows is not None:
            after['A'] = after['A'][:rows]
            after['b'] = after['b'][:rows]
        for key in ('c', 'b', 'beq', 'lb', 'ub', 'intcon'):
            with self.subTest(export=key):
                self.assertEqual(before[key].shape, after[key].shape)
                self.assertEqual(before[key].dtype, after[key].dtype)
                self.assertEqual(before[key].tobytes(), after[key].tobytes())
        for key in ('A', 'Aeq'):
            with self.subTest(export=key):
                a, b = before[key].tocsr(), after[key].tocsr()
                self.assertEqual(a.shape, b.shape)
                for part in ('data', 'indices', 'indptr'):
                    self.assertEqual(getattr(a, part).tobytes(), getattr(b, part).tobytes())

    def test_default_false_has_identical_rows_exports_and_summary(self):
        self.assertIs(inspect.signature(milp.build_model).parameters[
            'cumulative_precedence'].default, False)
        for field in ('names', 'rows', 'options', 'option_vars', 'shared', 'scenes',
                      'c', 'lb', 'ub', 'bounds', 'integer', 'logical_binary', 'formulation'):
            self.assertEqual(getattr(self.omitted, field), getattr(self.current, field), field)
        self.assert_solver_bytes_equal(self.omitted, self.current)
        self.assertEqual(self.omitted.summary(), self.current.summary())
        self.assertNotIn('cumulative_precedence', self.current.formulation)
        self.assertNotIn('cumulative_precedence', self.current.summary())
        self.assertFalse(hasattr(self.current, 'cumulative_precedence_stats'))

    def test_switch_rejects_non_bool_before_model_construction(self):
        with patch.object(milp, 'Model') as constructor:
            for value in (0, 1, None, 'false', np.bool_(False), 0.0, []):
                with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                    self.build(self.instance, self.starts, cumulative_precedence=value)
            constructor.assert_not_called()

    def test_true_only_appends_zero_error_integer_rows_and_transparent_statistics(self):
        before, after = self.current, self.strengthened
        original_count = len(before.rows)
        self.assertEqual(after.rows[:original_count], before.rows)
        for field in ('names', 'options', 'option_vars', 'shared', 'scenes', 'c',
                      'lb', 'ub', 'bounds', 'integer', 'logical_binary',
                      'deadline_fixed_options', 'energy_bound_certificates', 'instance'):
            self.assertEqual(getattr(before, field), getattr(after, field), field)
        self.assert_solver_bytes_equal(before, after, rows=original_count)
        added = after.rows[original_count:]
        self.assertTrue(added)
        for row in added:
            self.assertEqual(row['tag'], 'dependency_cumulative')
            self.assertEqual(set(row['coef'].values())-{-1.0, 1.0}, set())
            self.assertEqual(row['rhs'], 0.0)
            self.assertEqual(F(row['rounding_allowance']), 0)
            self.assertTrue(all(F(value) == 0 for value in row['rhs_interval']))
        stats = after.cumulative_precedence_stats
        self.assertTrue(stats['complete'])
        self.assertEqual(stats['rows_added'], len(added))
        self.assertEqual(stats['nonzeros_added'], sum(len(r['coef']) for r in added))
        self.assertEqual(stats['raw_rows'], stats['rows_added'] +
                         stats['removed_tautology_rows'] + stats['removed_duplicate_rows'])
        self.assertEqual(stats['options_removed'], 0)
        self.assertEqual(stats['variables_added'], 0)
        self.assertEqual(after.row_nonzeros-before.row_nonzeros, stats['nonzeros_added'])
        summary = after.summary()
        self.assertEqual(summary['cumulative_precedence'], stats)
        summary['cumulative_precedence']['edges'].clear()
        self.assertTrue(stats['edges'])
        self.assertEqual(after.coefficients.calls, 0)
        self.assertEqual(milp._digest(self.instance), milp._digest(after.instance))

    def test_all_production_rows_match_independent_k120_oracle_with_real_indices(self):
        model = self.strengthened
        for edge in model.cumulative_precedence_stats['edges']:
            choices = model.scenes[edge['scene_id']]['stage_options']
            def oracle_options(stage):
                return [{'option_id': f'y:{y}', 'start': F(o['start_ms'])/1000,
                         'end': F(o['end_ms'])/1000} for o, y in choices[stage]]
            oracle = build_precedence_system(oracle_options(edge['predecessor_stage_id']),
                oracle_options(edge['successor_stage_id']), simplify=True)
            self.assertEqual(edge['raw_rows'], len(oracle['raw_cumulative_rows']))
            self.assertEqual(edge['raw_nonzeros'], sum(len(row['coef'])
                             for row in oracle['raw_cumulative_rows']))
            self.assertEqual(edge['rows_added'], len(oracle['cumulative_rows']))
            for actual, expected in zip(edge['rows'], oracle['cumulative_rows']):
                self.assertEqual(F(actual['threshold_s']), expected['threshold'])
                self.assertEqual(model.rows[actual['row_index']]['coef'],
                    {int(identifier.split(':')[1]): coefficient
                     for identifier, coefficient in expected['coef'].items()})
            self.assertEqual([F(row['threshold_s']) for row in edge['removed_rows']],
                [row['row']['threshold'] for row in oracle['removed_rows']])

    def test_complete_small_fixture_integer_schedule_projection_matches_old_and_oracle(self):
        checked, legal, rejected, legal_waiting = 0, 0, 0, False
        for candidate in independent_assignments(self.instance, self.starts):
            expected = independent_check(self.instance, candidate)
            self.assertEqual(row_acceptance(self.current, candidate), expected['valid'])
            self.assertEqual(row_acceptance(self.strengthened, candidate), expected['valid'])
            checked += 1
            if expected['valid']:
                legal += 1
                for scene in self.instance['scenarios']:
                    rows = expected['scenes'][scene['id']]['rows']
                    legal_waiting |= any(rows[a]['end'] < rows[b]['start']
                                         for a, b in scene['dependencies'])
            else:
                rejected += 1
        self.assertGreater(checked, 0)
        self.assertGreater(legal, 0)
        self.assertGreater(rejected, 0)
        self.assertTrue(legal_waiting)
        self.assertTrue(any(F(o['end_ms']).denominator > 1 for o in self.strengthened.options))
        RECORDS['chain_fractional_integer_projection'] = {
            'checked': checked, 'legal': legal, 'rejected': rejected,
            'legal_waiting': legal_waiting,
            'scope': 'existing two-Stage correctness fixture only; no thermal or research run'}

    def test_exact_noninteger_end_inclusive_threshold_and_waiting_without_rounding(self):
        end = F(10**30+1, 3*10**30)
        stages = {'p': [({}, 17), ({}, 23)], 's': [({}, 41), ({}, 43), ({}, 47)]}
        starts = {17: F(0), 23: F(0), 41: F(1, 3), 43: end, 47: end+1}
        ends = {17: end, 23: end+F(1, 10**40),
                41: F(2), 43: F(2), 47: end+2}
        model = RowCollector()
        stats = milp.add_cumulative_precedence(model, 'scene', stages, starts, ends,
                                              dependencies=[('p', 's')])
        self.assertEqual(model.rows[0]['coef'], {41: 1})
        self.assertEqual(model.rows[1]['coef'], {17: -1, 41: 1, 43: 1})
        self.assertEqual(stats['removed_tautology_rows'], 1)
        for predecessor, successor in product((17, 23), (41, 43, 47)):
            with self.subTest(predecessor=predecessor, successor=successor):
                self.assertEqual(row_accepts(model.rows, {predecessor: F(1), successor: F(1)}),
                                 ends[predecessor] <= starts[successor])
        self.assertTrue(row_accepts(model.rows, {23: F(1), 47: F(1)}))

    def test_repeated_option_ids_and_labels_across_scenes_keep_real_y_columns_separate(self):
        instance, starts = deepcopy((self.instance, self.starts))
        original = instance['scenarios'][0]
        original['weight'] = '1/2'
        other = deepcopy(original)
        other['id'] += '_copy'
        instance['scenarios'].append(other)
        starts[other['id']] = deepcopy(starts[original['id']])
        model = self.build(instance, starts, cumulative_precedence=True)
        catalogs = {sid: {y for _, y in meta['options']} for sid, meta in model.scenes.items()}
        identifiers = [[o['option_id'] for o, _ in model.scenes[sid]['options']]
                       for sid in (original['id'], other['id'])]
        self.assertEqual(identifiers[0], identifiers[1])
        self.assertFalse(catalogs[original['id']] & catalogs[other['id']])
        self.assertEqual(len(model.cumulative_precedence_stats['edges']), 2)
        for edge in model.cumulative_precedence_stats['edges']:
            self.assertTrue(edge['rows'])
            for record in edge['rows']:
                self.assertLessEqual(set(model.rows[record['row_index']]['coef']),
                                     catalogs[edge['scene_id']])
        # Labels are never read by the generator, even if they all coincide.
        collectors = [RowCollector(), RowCollector()]
        stage_options = {'p': [({'option_id': 'same', 'opp_id': 'H', 'unit_id': 'CPU1'}, 11),
                               ({'option_id': 'same', 'opp_id': 'H', 'unit_id': 'CPU1'}, 13)],
                         's': [({'option_id': 'same', 'opp_id': 'H', 'unit_id': 'CPU1'}, 19)]}
        changed = deepcopy(stage_options)
        for choices in changed.values():
            for option, _ in choices:
                option.update(option_id='different', opp_id='L', unit_id='NPU0')
        for collector, catalog in zip(collectors, (stage_options, changed)):
            milp.add_cumulative_precedence(collector, 'labels', catalog,
                {11: F(0), 13: F(0), 19: F(1)}, {11: F(0), 13: F(2), 19: F(2)},
                dependencies=[('p', 's')])
        self.assertEqual(collectors[0].rows, collectors[1].rows)
        self.assertEqual(collectors[0].rows[0]['coef'], {11: -1, 19: 1})

    def test_empty_option_sets_preserve_onehot_contradiction_and_empty_prefix_rows(self):
        sid = self.instance['scenarios'][0]['id']
        before, after = self.instance['scenarios'][0]['dependencies'][0]
        for empty_stage in (before, after):
            starts = deepcopy(self.starts)
            starts[sid][empty_stage] = []
            model = self.build(self.instance, starts, cumulative_precedence=True)
            self.assertTrue(any(row['tag'] == 'stage_unique/lower' and
                not row['coef'] and row['rhs'] == -1 for row in model.rows))
            edge = model.cumulative_precedence_stats['edges'][0]
            if empty_stage == before:
                self.assertTrue(edge['empty_predecessor_option_set'])
                self.assertGreater(edge['rows_added'], 0)
                self.assertEqual(edge['empty_predecessor_prefix_rows_added'], edge['rows_added'])
                for record in edge['rows']:
                    self.assertEqual(set(model.rows[record['row_index']]['coef'].values()), {1.0})
            else:
                self.assertTrue(edge['empty_successor_option_set'])
                self.assertEqual(edge['raw_rows'], 0)
                self.assertEqual(edge['rows_added'], 0)

    def test_enabled_zero_edge_model_records_zero_added_rows(self):
        instance, starts = self.fixture_map['one_stage_energy']
        model = self.build(instance, starts, cumulative_precedence=True)
        stats = model.cumulative_precedence_stats
        self.assertTrue(stats['complete'])
        self.assertEqual(stats['edges'], [])
        self.assertEqual(stats['rows_added'], 0)
        self.assertEqual(stats['nonzeros_added'], 0)
        self.assertEqual(model.coefficients.calls, 0)

    def test_budget_interrupts_inside_coefficient_generation_before_row_append(self):
        budget = InterruptBudget()
        model = RowCollector(budget)
        budget.arm(10)
        with self.assertRaises(Exhausted):
            milp.add_cumulative_precedence(model, 'scene',
                {'p': [({}, 11), ({}, 13)], 's': [({}, 19)]},
                {11: F(0), 13: F(0), 19: F(1)},
                {11: F(0), 13: F(2), 19: F(2)}, dependencies=[('p', 's')])
        self.assertEqual(budget.armed_checks, 10)
        self.assertFalse(model.cumulative_precedence_stats['complete'])
        self.assertEqual(model.cumulative_precedence_stats['raw_rows'], 1)
        self.assertEqual(model.cumulative_precedence_stats['rows_added'], 0)
        self.assertEqual(model.rows, [])

    def test_build_budget_expiry_propagates_without_returning_solver_ready_model(self):
        budget, observed = InterruptBudget(), []
        instance, starts = deepcopy((self.instance, self.starts))
        first = instance['scenarios'][0]
        first['weight'] = '1/2'
        second = deepcopy(first)
        second['id'] += '_interrupted_copy'
        instance['scenarios'].append(second)
        starts[second['id']] = deepcopy(starts[first['id']])
        add = milp.add_cumulative_precedence
        def finish_first_scene_then_expire(model, *args, **kwargs):
            observed.append(model)
            result = add(model, *args, **kwargs)
            budget.arm(1)
            return result
        with patch.object(milp, 'add_cumulative_precedence',
                          side_effect=finish_first_scene_then_expire), self.assertRaises(Exhausted):
            self.build(instance, starts, budget=budget, cumulative_precedence=True)
        self.assertEqual(len(observed), 1)
        stats = observed[0].cumulative_precedence_stats
        self.assertEqual(len(stats['edges']), 1)
        self.assertGreater(stats['rows_added'], 0)
        self.assertFalse(stats['complete'])
        self.assertIs(observed[0].budget, budget)


if __name__ == '__main__':
    unittest.main()
