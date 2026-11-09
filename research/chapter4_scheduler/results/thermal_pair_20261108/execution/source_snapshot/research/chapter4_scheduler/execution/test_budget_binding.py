"""Caller-root compatibility checks with artificial inputs and fake receipts.

No real HEFT, graph search, lower-bound calculation, thermal propagation,
optimizer, subprocess, or historical experiment is executed by these tests.
"""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


RESEARCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RESEARCH / "chapter3_experiments"))
sys.path.insert(0, str(RESEARCH.parent))

import heuristic_runner
from research.chapter4_scheduler import method
from research.chapter4_scheduler.tests.test_method import (
    FakeClock, artificial_input, complete_mock,
)
from thermal import Exhausted
from timing import MethodBudget


class CallerRootBindingTests(unittest.TestCase):
    """Only lifecycle behavior; production entry functions use mock backends."""

    def setUp(self):
        runtime = RESEARCH.parent / ".runtime"
        runtime.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="ch4-caller-root-mock-", dir=runtime)
        self.addCleanup(self.tmp.cleanup)
        self.clock = FakeClock()
        self.config, self.instance, self.candidate = artificial_input()
        self.observed = []
        self.sequence = 0

    def invoke(self, arm, *, budget=None, supplied=False, seconds=300,
               clock=None, input_cost=7, graph_cost=2, evaluator=None):
        """A selected-arm import cost is simulated by the caller before entry."""
        self.sequence += 1
        workdir = Path(self.tmp.name) / (arm + "_" + str(self.sequence))
        root_clock = self.clock

        def loader(active):
            self.observed.append(("loader", active, active.elapsed))
            root_clock.now += input_cost
            return deepcopy(self.config), deepcopy(self.instance)

        def evaluate(instance, candidate, accuracy, active):
            self.observed.append(("evaluation", active, active.elapsed))
            root_clock.now += 3
            return complete_mock(instance, candidate, accuracy, active)

        physical = Mock(side_effect=evaluate if evaluator is None else evaluator)

        def search(instance, config, active, assess, **kwargs):
            self.observed.append(("search", active, active.elapsed))
            assess(deepcopy(self.candidate), "MOCK_ONLY:initializer")
            return {"status": "MOCK_ONLY_COMPLETED",
                    "local_base_candidate": deepcopy(self.candidate)}

        def packets(instance, incumbent, active, *, variant):
            self.observed.append(("graph", active, active.elapsed))
            root_clock.now += graph_cost
            return iter(())

        packet_mock = Mock(side_effect=packets)
        options = {"seconds": seconds, "clock": root_clock if clock is None else clock}
        if supplied:
            options["budget"] = budget
        with patch("heft_method.run_heft", side_effect=AssertionError("NO_REAL_HEFT")), \
                patch("thermal.evaluate_candidate", side_effect=AssertionError("NO_REAL_HEAT")), \
                patch("thermal.evaluate_piecewise", side_effect=AssertionError("NO_REAL_HEAT_KERNEL")), \
                patch.object(heuristic_runner, "independent_lower_bound", return_value={"lower_bound_J": "0"}), \
                patch("partial_bounds.independent_lower_bound", return_value={"lower_bound_J": "0"}), \
                patch.object(method, "candidate_packets", packet_mock):
            if arm == "heft":
                result = heuristic_runner.execute_heuristic(loader, workdir,
                    method="heft", evaluator=physical, search=search,
                    allow_auto_low=True, **options)
            elif arm == "graph":
                result = method.execute_reconstruction(loader, workdir,
                    bindings=method.Bindings(search, physical, kind="MOCK_ONLY"),
                    variant="pair", **options)
            else:
                raise AssertionError("unknown fixture arm")
        return result, physical, packet_mock

    def assert_root(self, result, root, *, elapsed):
        self.assertTrue(self.observed)
        self.assertTrue(all(active is root for _, active, _ in self.observed))
        self.assertEqual(root.start, 1000.0)
        self.assertEqual(root.deadline, 1300.0)
        self.assertEqual(result["timing"]["limit_s"], 300)
        self.assertEqual(result["timing"]["method_elapsed_s"], elapsed)

    def test_heft_inherits_worker_import_time_without_new_budget(self):
        root = MethodBudget(300, clock=self.clock)
        self.clock.now += 23  # Selected-arm imports and identity work are billed.
        with patch.object(MethodBudget, "__init__", side_effect=AssertionError("NEW_ROOT_FORBIDDEN")):
            result, evaluator, packets = self.invoke("heft", budget=root, supplied=True,
                clock=Mock(side_effect=AssertionError("FOREIGN_CLOCK_FORBIDDEN")))
        self.assert_root(result, root, elapsed=33)
        self.assertEqual([(kind, at) for kind, _, at in self.observed],
                         [("loader", 23), ("search", 30), ("evaluation", 30)])
        self.assertEqual(result["state"], "SAFE")  # Synthetic receipt, not research SAFE.
        evaluator.assert_called_once()
        packets.assert_not_called()

    def test_graph_inherits_worker_import_time_without_new_budget(self):
        root = MethodBudget(300, clock=self.clock)
        self.clock.now += 23
        with patch.object(MethodBudget, "__init__", side_effect=AssertionError("NEW_ROOT_FORBIDDEN")):
            result, evaluator, packets = self.invoke("graph", budget=root, supplied=True,
                clock=Mock(side_effect=AssertionError("FOREIGN_CLOCK_FORBIDDEN")))
        self.assert_root(result, root, elapsed=35)
        self.assertEqual(result["root_context"]["root_start"], "1000.0")
        self.assertEqual(result["root_context"]["root_deadline"], "1300.0")
        self.assertEqual(result["state"], "MOCK_SAFE")
        self.assertFalse(result["usable_as_research_evidence"])
        evaluator.assert_called_once()
        packets.assert_called_once()

    def test_both_entries_reject_wrong_root_type_before_input(self):
        for arm in ("heft", "graph"):
            with self.subTest(arm=arm):
                self.observed.clear()
                with self.assertRaises((TypeError, ValueError)):
                    self.invoke(arm, supplied=True, budget=object())
                self.assertEqual(self.observed, [])

    def test_both_entries_reject_root_seconds_mismatch_before_input(self):
        for arm in ("heft", "graph"):
            with self.subTest(arm=arm):
                self.observed.clear()
                root = MethodBudget(300, clock=self.clock)
                with self.assertRaises((TypeError, ValueError)):
                    self.invoke(arm, supplied=True, budget=root, seconds=299)
                self.assertEqual(self.observed, [])
                self.assertEqual(root.seconds, 300)
                self.assertEqual(root.deadline - root.start, 300)

    def test_expired_caller_root_never_loads_input_or_resets_deadline(self):
        for arm in ("heft", "graph"):
            with self.subTest(arm=arm):
                self.clock.now = 1000.0
                self.observed.clear()
                root = MethodBudget(300, clock=self.clock)
                self.clock.now = 1300.0
                try:
                    result, evaluator, packets = self.invoke(arm, supplied=True, budget=root)
                except Exhausted:
                    pass  # An entry may reject expiry before its result lifecycle starts.
                else:
                    self.assertTrue(result["budget_exhausted"])
                    self.assertIsNone(result["safe_candidate"])
                    evaluator.assert_not_called()
                    packets.assert_not_called()
                self.assertEqual(self.observed, [])
                self.assertEqual(root.start, 1000.0)
                self.assertEqual(root.deadline, 1300.0)

    def test_legacy_heft_default_still_owns_one_fresh_root(self):
        result, evaluator, _ = self.invoke("heft")
        root = self.observed[0][1]
        self.assert_root(result, root, elapsed=10)
        self.assertEqual(self.observed[0][2], 0)
        self.assertEqual(result["state"], "SAFE")
        evaluator.assert_called_once()

    def test_graph_default_still_owns_one_fresh_root(self):
        result, evaluator, packets = self.invoke("graph")
        root = self.observed[0][1]
        self.assert_root(result, root, elapsed=12)
        self.assertEqual(self.observed[0][2], 0)
        self.assertEqual(result["state"], "MOCK_SAFE")
        self.assertFalse(result["usable_as_research_evidence"])
        evaluator.assert_called_once()
        packets.assert_called_once()

    def test_complete_predeadline_evidence_survives_caller_expiry(self):
        for arm in ("heft", "graph"):
            with self.subTest(arm=arm):
                self.clock.now = 1000.0
                self.observed.clear()
                root = MethodBudget(300, clock=self.clock)
                self.clock.now = 1296.0

                def evaluate(instance, candidate, accuracy, active):
                    self.assertIs(active, root)
                    self.clock.now = 1299.0
                    receipt = complete_mock(instance, candidate, accuracy, active)
                    self.clock.now = 1301.0  # Only return/transfer crosses the cutoff.
                    return receipt

                result, evaluator, packets = self.invoke(arm, supplied=True, budget=root,
                    input_cost=0, evaluator=evaluate)
                self.assertEqual(result["safe_candidate"], self.candidate)
                self.assertTrue(result["budget_exhausted"])
                self.assertEqual(result["timing"]["method_elapsed_s"], 301)
                self.assertEqual(result["evaluation"]["completed_at_elapsed_s"], 299)
                self.assertEqual(root.deadline, 1300.0)
                evaluator.assert_called_once()
                packets.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
