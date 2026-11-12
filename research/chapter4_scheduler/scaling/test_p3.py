"""Invented lifecycle controls; no real initialization/search/thermal calls."""
from copy import deepcopy
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import uuid

from . import p3
from research.chapter4_scheduler.tests.test_method import artificial_input, complete_mock, FakeClock
from research.chapter4_scheduler.blocking.method import Bindings
from research.chapter4_scheduler.comparison.core import EvaluationJournal, normalize
from timing import MethodBudget
from thermal import Exhausted


class P3Tests(unittest.TestCase):
    def test_scope_and_order(self):
        cases = [{'case_id': name, 'root_id': name[:3], 'stages_per_scene': int(name.split('n')[-1])} for name in p3.CASES]
        self.assertEqual([r['arm'] for r in p3.slots(cases)], ['OFF', 'ON', 'ON', 'OFF', 'OFF', 'ON'])
        with self.assertRaises(ValueError):
            p3.slots(cases + [{'case_id': 'U02__n12'}])
        with self.assertRaises(ValueError):
            p3.dispatch('HEFT', None, None, None, None)

    def exercise(self, arm, timeout=False):
        parent = p3.REPO.parent.resolve()
        directory = parent / ('mock_p3_' + uuid.uuid4().hex)
        directory.mkdir()
        clock = FakeClock()
        budget = MethodBudget(300, clock=clock)
        config, instance, candidate = artificial_input(two_scenes=True)
        roots, flags = [], []
        def loader(b):
            roots.append(b)
            clock.now += 2
            return deepcopy(config), deepcopy(instance)
        def evaluator(i, c, a, b):
            roots.append(b)
            clock.now += 1
            return complete_mock(i, c, a, b)
        journal = EvaluationJournal(evaluator, budget)
        def initializer(i, c, b, assess, **kwargs):
            roots.append(b)
            clock.now += 5
            assess(candidate, 'MOCK_ONLY_INITIAL')
            return {'status': 'MOCK_INITIALIZER_COMPLETED'}
        def packets(i, c, b, **kwargs):
            roots.append(b)
            flags.append(kwargs['allow_blocking_edges'])
            clock.now += 2
            if timeout:
                clock.now = 1300.1
                raise Exhausted('MOCK_ONLY_TIMEOUT')
            return iter(())
        try:
            with patch('heft_method.run_heft', side_effect=AssertionError('REAL_INITIALIZATION_FORBIDDEN')), \
                    patch('thermal.evaluate_candidate', side_effect=AssertionError('REAL_THERMAL_FORBIDDEN')), \
                    patch('research.chapter4_scheduler.blocking.method.candidate_packets', side_effect=packets):
                raw = p3.dispatch(arm, loader, directory / arm, budget, Bindings(initializer, journal))
            self.assertTrue(all(b is budget for b in roots))
            self.assertEqual((budget.start, budget.deadline), (1000.0, 1300.0))
            self.assertEqual(flags, [arm == 'ON'])
            self.assertEqual(raw['blocking_edge_adjustment_enabled'], arm == 'ON')
            result = normalize(raw, journal)
            self.assertTrue(result['has_SAFE_archive'])
            self.assertEqual(result['counts']['evaluation_attempts'], 1)
            self.assertEqual(result['terminal'], 'BUDGET_EXHAUSTED' if timeout else 'SEARCH_COMPLETED')
            self.assertEqual(p3.metrics(raw, arm)['initialization_s'], 6)
            if not timeout:
                self.assertEqual(p3.metrics(raw, arm)['search_s'], 2)
        finally:
            assert directory.resolve().is_relative_to(parent) and directory.name.startswith('mock_p3_')
            shutil.rmtree(directory)

    def test_both_flag_values_preserve_lifecycle_root_and_search_cost(self):
        for arm in ('ON', 'OFF'):
            with self.subTest(arm=arm):
                self.exercise(arm)

    def test_budget_stop_retains_safe_for_both_arms(self):
        for arm in ('ON', 'OFF'):
            with self.subTest(arm=arm):
                self.exercise(arm, timeout=True)


if __name__ == '__main__':
    unittest.main()
