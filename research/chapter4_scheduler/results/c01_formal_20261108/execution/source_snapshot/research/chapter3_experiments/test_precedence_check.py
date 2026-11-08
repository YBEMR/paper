"""Pure exact algebra checks; no scheduling model, LP, thermal, or native call."""
from copy import deepcopy
from fractions import Fraction as F
from itertools import combinations, product
import unittest

from precedence_check import build_precedence_system


def option(identifier, start, end, **labels):
    return dict(option_id=identifier, start=start, end=end, **labels)


def lhs(row, weights):
    # Independent dot product: no evaluation helper from the module under test.
    return sum((coefficient * weights.get(identifier, F(0))
                for identifier, coefficient in row['coef'].items()), F(0))


def accepts(rows, weights):
    return all(lhs(row, weights) <= row['rhs'] for row in rows)


def nonempty_subsets(values):
    return [part for size in range(1, len(values) + 1)
            for part in combinations(values, size)]


class PrecedenceAlgebraTests(unittest.TestCase):
    def test_complete_cartesian_integer_oracle_matches_direct_end_le_start(self):
        predecessors = [option(f'p{k}', 0, end) for k, end in
                        enumerate((F(0), F(1, 2), F(3, 2)))]
        successors = [option(f's{k}', start, start + F(1, 3)) for k, start in
                      enumerate((F(0), F(1, 2), F(1), F(2)))]
        checked = 0
        for before, after in product(nonempty_subsets(predecessors),
                                     nonempty_subsets(successors)):
            full = build_precedence_system(before, after)
            reduced = build_precedence_system(before, after, simplify=True)
            for chosen_before, chosen_after in product(before, after):
                weights = {chosen_before['option_id']: F(1),
                           chosen_after['option_id']: F(1)}
                direct = chosen_before['end'] <= chosen_after['start']
                with self.subTest(before=chosen_before, after=chosen_after,
                                  before_n=len(before), after_n=len(after)):
                    self.assertEqual(accepts(full['cumulative_rows'], weights), direct)
                    self.assertEqual(accepts(reduced['cumulative_rows'], weights), direct)
                    self.assertEqual(accepts([full['expected_row']] +
                        full['cumulative_rows'], weights), direct)
                checked += 1
        self.assertEqual(checked, 384)

    def test_expected_row_and_every_threshold_have_exact_original_coefficients(self):
        system = build_precedence_system(
            [option('p0', 0, '1/3'), option('p1', 0, '2/3')],
            [option('s0', '1/3', 1), option('s1', 1, 2)])
        self.assertEqual(system['expected_row']['coef'],
            {'p0': F(1, 3), 'p1': F(2, 3), 's0': F(-1, 3), 's1': F(-1)})
        self.assertEqual([row['threshold'] for row in system['cumulative_rows']],
                         [F(1, 3), F(1)])
        self.assertEqual(system['cumulative_rows'][0]['coef'], {'p0': F(-1), 's0': F(1)})
        self.assertEqual(system['cumulative_rows'][1]['coef'],
                         {'p0': F(-1), 'p1': F(-1), 's0': F(1), 's1': F(1)})
        self.assertEqual(system['raw_cumulative_rows'], system['cumulative_rows'])
        self.assertEqual(system['removed_rows'], [])

    def test_fractional_point_passes_expected_time_but_violates_cumulative(self):
        before = [option(f'p{k}', 0, end) for k, end in enumerate((1, 5, 9))]
        after = [option(f's{k}', start, start + 1) for k, start in enumerate((2, 6, 10))]
        system = build_precedence_system(before, after)
        weights = {'p0': F(1, 2), 'p1': F(0), 'p2': F(1, 2),
                   's0': F(0), 's1': F(1), 's2': F(0)}
        self.assertEqual(lhs(system['expected_row'], weights), F(-1))
        self.assertTrue(accepts([system['expected_row']], weights))
        self.assertFalse(accepts(system['cumulative_rows'], weights))
        row = next(row for row in system['cumulative_rows'] if row['threshold'] == 6)
        self.assertEqual(lhs(row, weights), F(1, 2))
        # Every option appears in a legal integer pair; no option prefilter is needed.
        self.assertTrue(all(any(p['end'] <= s['start'] for s in after) for p in before))
        self.assertTrue(all(any(p['end'] <= s['start'] for p in before) for s in after))

    def test_equal_endpoint_and_noninteger_true_end_without_float_rounding(self):
        end = F(10**30 + 1, 3 * 10**30)
        start_values = (F(1, 3), end, end + F(1, 10**40))
        system = build_precedence_system([option('p', 0, end)],
            [option(f's{k}', start, start + 1) for k, start in enumerate(start_values)])
        self.assertEqual(len(system['cumulative_rows']), 3)
        for k, expected in enumerate((False, True, True)):
            with self.subTest(start=start_values[k]):
                self.assertEqual(accepts(system['cumulative_rows'],
                    {'p': F(1), f's{k}': F(1)}), expected)
        # The first row must not include an end that lies strictly after its threshold.
        self.assertNotIn('p', system['cumulative_rows'][0]['coef'])
        self.assertEqual(system['cumulative_rows'][1]['coef']['p'], F(-1))

    def test_legal_waiting_and_arbitrary_time_origin_are_retained(self):
        system = build_precedence_system([option('p', '-7/2', '-1/2')],
                                         [option('s', '11/3', 4)])
        self.assertTrue(accepts(system['cumulative_rows'], {'p': F(1), 's': F(1)}))
        self.assertEqual(len(system['predecessor_options']), 1)
        self.assertEqual(len(system['successor_options']), 1)

    def test_mapping_frequency_and_other_labels_never_prune_or_merge_options(self):
        before = [option('p0', 0, 1, mapping='CPU0', frequency='H'),
                  option('p1', 0, 1, mapping='CPU0', frequency='H')]
        after = [option('s0', 1, 2, mapping='NPU0', frequency='H'),
                 option('s1', 2, 3, mapping='CPU1', frequency='H')]
        original = deepcopy((before, after))
        first = build_precedence_system(before, after)
        changed_before, changed_after = deepcopy((before, after))
        for item in changed_before + changed_after:
            item.update(mapping='anything', frequency='same', domain='opaque')
        second = build_precedence_system(changed_before[::-1], changed_after[::-1])
        self.assertEqual(first['expected_row'], second['expected_row'])
        self.assertEqual(first['raw_cumulative_rows'], second['raw_cumulative_rows'])
        self.assertEqual([o['option_id'] for o in first['predecessor_options']], ['p0', 'p1'])
        self.assertEqual([o['option_id'] for o in first['successor_options']], ['s0', 's1'])
        self.assertEqual((before, after), original)
        first['predecessor_options'][0]['mapping'] = 'changed returned catalog'
        self.assertEqual((before, after), original)

    def test_simplification_only_drops_proven_prefix_tautologies(self):
        before = [option('p0', 0, 1), option('p1', 0, 3)]
        after = [option(f's{k}', start, start + 1) for k, start in enumerate((0, 1, 3, 4))]
        system = build_precedence_system(before, after, simplify=True)
        self.assertEqual([r['threshold'] for r in system['raw_cumulative_rows']],
                         [F(0), F(1), F(3), F(4)])
        self.assertEqual([r['threshold'] for r in system['cumulative_rows']], [F(0), F(1)])
        self.assertEqual([r['row']['threshold'] for r in system['removed_rows']], [F(3), F(4)])
        self.assertTrue(all(r['reason'] == 'predecessor_prefix_is_one'
                            for r in system['removed_rows']))
        # Enumerate fractional simplex points as well: removed rows remain valid.
        after_weights = ((F(1), F(0), F(0), F(0)),
                         (F(1, 4), F(1, 4), F(1, 4), F(1, 4)),
                         (F(0), F(1, 3), F(2, 3), F(0)))
        for p0, sw in product((F(0), F(1, 3), F(1)), after_weights):
            weights = {'p0': p0, 'p1': 1 - p0}
            weights.update({f's{k}': weight for k, weight in enumerate(sw)})
            self.assertTrue(accepts([r['row'] for r in system['removed_rows']], weights))
        self.assertEqual(system['expected_row'],
                         build_precedence_system(before, after)['expected_row'])
        system['cumulative_rows'][0]['coef']['s0'] = F(99)
        self.assertEqual(system['raw_cumulative_rows'][0]['coef']['s0'], F(1))
        system['removed_rows'][0]['row']['coef']['s0'] = F(99)
        self.assertEqual(system['raw_cumulative_rows'][2]['coef']['s0'], F(1))

    def test_empty_predecessor_prefix_is_not_a_tautology(self):
        system = build_precedence_system([option('p', 0, 2)],
                                         [option('s', 0, 1)], simplify=True)
        self.assertEqual(system['cumulative_rows'][0]['coef'], {'s': F(1)})
        self.assertEqual(system['removed_rows'], [])
        self.assertFalse(accepts(system['cumulative_rows'], {'p': F(1), 's': F(1)}))

    def test_equal_successor_thresholds_generate_one_row_including_both_variables(self):
        system = build_precedence_system([option('p', 0, '1/2')],
            [option('s0', 1, 2), option('s1', F(1), 3)])
        self.assertEqual(len(system['raw_cumulative_rows']), 1)
        self.assertEqual(system['raw_cumulative_rows'][0]['coef'],
                         {'p': F(-1), 's0': F(1), 's1': F(1)})
        self.assertEqual(len(system['successor_options']), 2)

    def test_empty_domains_remain_explicit_and_expected_row_is_always_kept(self):
        no_predecessor = build_precedence_system([], [option('s', 0, 1)], simplify=True)
        self.assertEqual(no_predecessor['empty_option_sides'], ('predecessor',))
        self.assertEqual(no_predecessor['cumulative_rows'][0]['coef'], {'s': F(1)})
        self.assertEqual(no_predecessor['removed_rows'], [])
        no_successor = build_precedence_system([option('p', 0, 1)], [], simplify=True)
        self.assertEqual(no_successor['empty_option_sides'], ('successor',))
        self.assertEqual(no_successor['raw_cumulative_rows'], [])
        empty = build_precedence_system([], [], simplify=True)
        self.assertEqual(empty['empty_option_sides'], ('predecessor', 'successor'))
        self.assertEqual(empty['expected_row']['coef'], {})
        self.assertEqual(empty['domain_assumptions']['predecessor_sum'], F(1))
        tautological = build_precedence_system([option('p', 0, 0)],
                                              [option('s', 0, 0)], simplify=True)
        self.assertEqual(tautological['cumulative_rows'], [])
        self.assertEqual(tautological['expected_row']['coef'], {'p': F(0), 's': F(0)})

    def test_reject_inexact_malformed_or_colliding_input_without_mutation(self):
        for value in (True, False, 0.5, float('nan'), float('inf'), None, '1/0', 'bad'):
            with self.subTest(value=repr(value)):
                before = [option('p', 0, 1)]
                after = [option('s', value, 2)]
                with self.assertRaises(ValueError):
                    build_precedence_system(before, after)
        for before, after in (
            ([option('p', 1, 0)], [option('s', 1, 2)]),
            ([option('same', 0, 1)], [option('same', 1, 2)]),
            ([option('p', 0, 1), option('p', 1, 2)], [option('s', 2, 3)]),
            ([option('', 0, 1)], [option('s', 1, 2)]),
            ([option(1, 0, 1)], [option('s', 1, 2)]),
            ([{'option_id': 'p', 'start': 0}], [option('s', 1, 2)]),
            (['not an option mapping'], [option('s', 1, 2)]),
        ):
            original = deepcopy((before, after))
            with self.subTest(before=before, after=after), self.assertRaises(ValueError):
                build_precedence_system(before, after)
            self.assertEqual((before, after), original)
        with self.assertRaises(ValueError):
            build_precedence_system([], [], simplify=1)


if __name__ == '__main__':
    unittest.main()
