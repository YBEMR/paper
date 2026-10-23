"""Inert dispatch/controller tests; no scientific method or subprocess."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'research/chapter3_experiments'))
from timing import MethodBudget
from research.chapter4_scheduler.execution import backends, batch, protocol as p
from research.chapter4_scheduler.tests.test_method import FakeClock


class DispatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recipe = p.make_declaration()['cases'][0]['recipes']['C']

    def test_each_arm_receives_exact_caller_root_and_distinct_rule(self):
        for arm in backends.ARMS:
            with self.subTest(arm=arm):
                clock = FakeClock(); root = MethodBudget(300, clock=clock)
                clock.now += 17
                raw = {'state': 'INERT_TEST_RECORD'}; observed = []
                def inert(loader, directory, **kw):
                    observed.append(kw)
                    self.assertIs(kw['budget'], root)
                    self.assertIs(kw['clock'], root.clock)
                    self.assertEqual(root.elapsed, 17)
                    if arm == 'C':
                        self.assertEqual(kw['preeliminate_closed_anchors'], True)
                        self.assertEqual(kw['linked_opened_by_scene'], self.recipe['kwargs']['linked_opened_by_scene'])
                        with self.assertRaises(RuntimeError):
                            kw['session_factory']()
                    elif arm == 'HEFT':
                        self.assertEqual(kw['method'], 'heft')
                        self.assertIsNone(kw['seed'])
                        self.assertTrue(kw['allow_auto_low'])
                    else:
                        self.assertEqual(kw['variant'], arm.lower())
                        self.assertEqual(kw['bindings'].kind, 'MOCK_ONLY')
                        with self.assertRaises(RuntimeError):
                            kw['bindings'].evaluator()
                    clock.now += 2
                    return raw
                result = backends.dispatch(arm, lambda b: None, Path('INERT'), root,
                    deepcopy(self.recipe), _entries={arm: inert})
                self.assertEqual(len(observed), 1)
                self.assertIs(result['result'], raw)
                self.assertTrue(result['not_scientific'])
                self.assertEqual(root.elapsed, 19)
                self.assertEqual(result['root_deadline'], 1300)

    def test_invalid_arm_or_changed_C_recipe_never_dispatches(self):
        root = MethodBudget(300, clock=FakeClock())
        def forbidden(*a, **k):
            raise AssertionError('BACKEND_MUST_NOT_RUN')
        with self.assertRaises(ValueError):
            backends.dispatch('UNKNOWN', forbidden, Path('INERT'), root, {}, _entries={})
        recipe = deepcopy(self.recipe); recipe['kwargs']['scene_slice_s'] = 150
        with self.assertRaises(ValueError):
            backends.dispatch('C', forbidden, Path('INERT'), root, recipe, _entries={'C': forbidden})


class BatchTests(unittest.TestCase):
    def fixture(self):
        from research.chapter4_scheduler.execution.test_protocol import active_fixture
        return active_fixture()

    @staticmethod
    def process(command, folder, phase, **limits):
        if phase == 'post':
            p.write_new(folder / 'post_return.json', dict(passed=True, not_scientific=True))
        assert command[3] == phase
        return dict(returncode=0, process_closed=True, watchdog_stop=None,
                    launched=True, not_scientific=True)

    def test_simulated_eight_safe_slots_are_never_scientific(self):
        with self.fixture() as (path, d, out):
            report = batch.run(path, _runner=self.process, _audit=lambda *a:
                dict(eligible_for_post=True, normal_no_safe=False, technical_failure=False))
            self.assertTrue(report['passed']); self.assertTrue(report['not_scientific'])
            self.assertEqual(report['research_calls_reserved'], 8)
            self.assertEqual(report['reserved_method_s'], 2400)
            self.assertEqual(report['reserved_post_s'], 480)
            with self.assertRaises(ValueError):
                batch.run(path, _runner=self.process, _audit=lambda *a: {})

    def test_normal_no_safe_advances_without_post_or_infeasibility_claim(self):
        with self.fixture() as (path, d, out):
            report = batch.run(path, _runner=self.process, _audit=lambda *a:
                dict(eligible_for_post=False, normal_no_safe=True, technical_failure=False))
            self.assertTrue(report['passed']); self.assertEqual(report['posts_reserved'], 0)
            self.assertNotIn('infeasible', str(report).lower())

    def test_failed_first_process_consumes_one_without_retry(self):
        with self.fixture() as (path, d, out):
            calls = []
            def bad(*a, **k):
                calls.append(a)
                return dict(returncode=2, process_closed=True, launched=True, watchdog_stop=None)
            report = batch.run(path, _runner=bad, _audit=lambda *a: {})
            self.assertFalse(report['passed']); self.assertEqual(len(calls), 1)
            self.assertEqual(report['research_calls_reserved'], 1)
            self.assertEqual(report['reserved_method_s'], 300)
            self.assertEqual(report['posts_reserved'], 0)

    def test_technical_audit_stops_even_with_safe_result(self):
        with self.fixture() as (path, d, out):
            report = batch.run(path, _runner=self.process, _audit=lambda *a:
                dict(eligible_for_post=True, normal_no_safe=False, technical_failure=True))
            self.assertFalse(report['passed']); self.assertEqual(report['research_calls_reserved'], 1)
            self.assertEqual(report['posts_reserved'], 0)

    def test_failed_post_is_once_only_and_stops_following_methods(self):
        with self.fixture() as (path, d, out):
            def child(command, folder, phase, **kw):
                if phase == 'post':
                    p.write_new(folder / 'post_return.json', dict(passed=False))
                return dict(returncode=0, process_closed=True, launched=True, watchdog_stop=None)
            report = batch.run(path, _runner=child, _audit=lambda *a:
                dict(eligible_for_post=True, normal_no_safe=False, technical_failure=False))
            self.assertFalse(report['passed']); self.assertEqual(report['posts_reserved'], 1)
            self.assertEqual(report['research_calls_reserved'], 1)

    def test_single_fake_service_cannot_start_real_process(self):
        with self.fixture() as (path, d, out):
            with self.assertRaises(ValueError):
                batch.run(path, _audit=lambda *a: {})
            self.assertFalse((out / 'batch.claim.json').exists())


if __name__ == '__main__':
    unittest.main()
