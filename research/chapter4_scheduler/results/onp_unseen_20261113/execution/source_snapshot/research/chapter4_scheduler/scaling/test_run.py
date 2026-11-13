"""Small invented-fixture tests; real HEFT/search/thermal calls prohibited."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch
import uuid

from . import run
from research.chapter4_scheduler.tests.test_method import artificial_input, complete_mock, FakeClock, changed
from research.chapter4_scheduler.blocking.method import Bindings
from research.chapter4_scheduler.comparison.core import EvaluationJournal, normalize
from timing import MethodBudget
from thermal import Exhausted


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.base = run.REPO.parent.resolve()
        self.tmp = self.base / ("mock_scaling_" + uuid.uuid4().hex)
        self.tmp.mkdir()

    def tearDown(self):
        target = self.tmp.resolve()
        if not target.is_relative_to(self.base) or not target.name.startswith("mock_scaling_"):
            raise RuntimeError("UNSAFE_TEST_CLEANUP")
        shutil.rmtree(target)

    def cases(self):
        return [{"case_id": f"{r}__n{n}", "root_id": r, "stages_per_scene": n}
            for r in ("U01", "U02") for n in (6, 12)]

    def exercise(self, arm, interrupted=False):
        clock = FakeClock()
        budget = MethodBudget(300, clock=clock)
        clock.now += 20
        config, instance, candidate = artificial_input(two_scenes=True)
        calls, roots = [], []
        def evaluator(i, c, a, b):
            roots.append(b)
            if calls and interrupted:
                clock.now = 1300.1
                raise Exhausted("MOCK_ONLY_TIMEOUT")
            calls.append(True)
            clock.now += 1
            return complete_mock(i, c, a, b)
        journal = EvaluationJournal(evaluator, budget)
        def loader(b):
            roots.append(b)
            clock.now += 2
            return deepcopy(config), deepcopy(instance)
        def initializer(i, c, b, assess, **kwargs):
            roots.append(b)
            clock.now += 5
            assess(candidate, "MOCK_ONLY_INITIAL")
            assess(changed(candidate, 5) if interrupted else deepcopy(candidate), "MOCK_ONLY_SECOND")
            return {"status": "MOCK_INITIALIZER_COMPLETED"}
        def packets(*args, **kwargs):
            roots.append(args[2])
            clock.now += 2
            return iter(())
        with patch("heft_method.run_heft", side_effect=AssertionError("REAL_HEFT_FORBIDDEN")), \
                patch("thermal.evaluate_candidate", side_effect=AssertionError("REAL_THERMAL_FORBIDDEN")), \
                patch("research.chapter4_scheduler.blocking.method.candidate_packets", side_effect=packets) as generator:
            raw = run.dispatch(arm, loader, self.tmp / arm, budget, Bindings(initializer, journal))
        self.assertTrue(all(b is budget for b in roots))
        self.assertEqual((budget.start, budget.deadline, budget.seconds), (1000.0, 1300.0, 300))
        return raw, normalize(raw, journal), journal, generator

    def test_balanced_eight_slots_without_SA(self):
        slots = run.slots(self.cases())
        self.assertEqual(len(slots), 8)
        self.assertEqual([s["arm"] for s in slots], ["HEFT", "ON", "ON", "HEFT", "ON", "HEFT", "HEFT", "ON"])
        self.assertEqual(len({s["id"] for s in slots}), 8)
        with self.assertRaises(ValueError):
            run.slots(self.cases()[:-1])

    def test_SA_rejected_before_any_call(self):
        with self.assertRaisesRegex(ValueError, "ONLY_HEFT_AND_ON"):
            run.dispatch("SA", None, None, None, None)

    def test_both_arms_preserve_root_and_complete_accounting(self):
        for arm in ("HEFT", "ON"):
            with self.subTest(arm=arm):
                raw, unified, journal, generator = self.exercise(arm)
                self.assertEqual(unified["terminal"], "SEARCH_COMPLETED")
                self.assertEqual(unified["counts"]["evaluation_attempts"], 1)
                self.assertEqual(unified["counts"]["validated_SAFE_receipts"], 1)
                self.assertEqual(unified["counts"]["cache_hits"], 1)
                self.assertEqual(raw["evidence_kind"], "MOCK_ONLY")
                self.assertFalse(raw["usable_as_research_evidence"])
                cost = run.derived_metrics(raw, arm)
                self.assertEqual(cost["initialization_s"], 6)
                self.assertEqual(cost["full_electrothermal_SAFE_evaluations"], 1)
                self.assertEqual(cost["search_s"], 2 if arm == "ON" else 0)
                self.assertEqual(generator.call_count, int(arm == "ON"))

    def test_budget_failure_retains_SAFE_and_interrupted_attempt(self):
        for arm in ("HEFT", "ON"):
            with self.subTest(arm=arm):
                raw, unified, journal, generator = self.exercise(arm, interrupted=True)
                self.assertEqual(unified["terminal"], "BUDGET_EXHAUSTED")
                self.assertTrue(unified["has_SAFE_archive"])
                self.assertEqual(unified["counts"]["evaluation_attempts"], 2)
                self.assertEqual(unified["counts"]["interrupted_attempts"], 1)
                self.assertEqual(unified["counts"]["validated_SAFE_receipts"], 1)
                self.assertFalse(run.derived_metrics(raw, arm)["initialization_complete"])
                self.assertEqual(run.derived_metrics(raw, arm)["search_s"], 0)
                generator.assert_not_called()

    def test_actual_process_failure_keeps_all_eight_planned_rows(self):
        out = self.tmp / "batch"
        out.mkdir()
        cases = self.cases()
        run.save(out / "plan.json", {"cases": cases, "slots": run.slots(cases), "subject_commit": "MOCK_ONLY"})
        fake = subprocess.CompletedProcess([], 1, "MOCK_ONLY", "MOCK_ONLY_FAILURE")
        with patch.object(run, "verify"), patch.object(run.subprocess, "run", return_value=fake) as launch, redirect_stdout(io.StringIO()):
            result = run.batch(out)
        self.assertEqual(result, 1)
        launch.assert_called_once()
        final = run.read(out / "batch_return.json")
        self.assertEqual(len(final["slots"]), 8)
        self.assertEqual(final["slots"][0]["status"], "STOPPED_TECHNICAL")
        self.assertTrue(all(s["status"] == "NOT_RUN_TECHNICAL_STOP" for s in final["slots"][1:]))
        self.assertEqual(final["retry_count"], 0)
        self.assertEqual(len(run.read(out / "summary.json")["rows"]), 8)

    def test_preflight_failure_records_no_call_and_all_pending_slots(self):
        out = self.tmp / "preflight"
        out.mkdir()
        cases = self.cases()
        run.save(out / "plan.json", {"cases": cases, "slots": run.slots(cases), "subject_commit": "MOCK_ONLY"})
        with patch.object(run, "verify", side_effect=[None, ValueError("MOCK_SOURCE_DRIFT"), None]), \
                patch.object(run.subprocess, "run", side_effect=AssertionError("CALL_FORBIDDEN")) as launch, redirect_stdout(io.StringIO()):
            result = run.batch(out)
        self.assertEqual(result, 1)
        launch.assert_not_called()
        final = run.read(out / "batch_return.json")
        self.assertEqual(len(final["slots"]), 8)
        self.assertIn("MOCK_SOURCE_DRIFT", final["stop_reason"])
        first = out / "calls" / final["slots"][0]["slot"]["id"] / "method_preflight_failure.json"
        self.assertFalse(run.read(first)["scientific_call_started"])


if __name__ == "__main__":
    unittest.main()
