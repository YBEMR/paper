"""Artificial worker handoff tests, with no real planning or physical result.

All authorization views, input expansion and selected entries are in-memory
test doubles. Files live only under a disposable project .runtime directory;
none of these MOCK_ONLY records is research evidence or an execution grant.
"""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


RESEARCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RESEARCH.parent))
sys.path.insert(0, str(RESEARCH / "chapter3_experiments"))
from research.chapter4_scheduler.execution import worker, backends
from research.chapter4_scheduler.tests.test_method import artificial_input, complete_mock


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class WorkerTests(unittest.TestCase):
    def setUp(self):
        runtime = (RESEARCH.parent / ".runtime").resolve()
        runtime.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="ch4-worker-mock-", dir=runtime)
        self.assertTrue(Path(self.tmp.name).resolve().is_relative_to(runtime))
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.declaration_path = self.folder / "declaration.json"
        self.clock = Clock()
        self.config, self.instance, self.candidate = artificial_input()
        self.instance["id"] = "MOCK_ONLY_WORKER_FIXTURE"
        self.raw_config = deepcopy(self.config)
        self.common = {"case_id": self.instance["id"],
            "input_sha256": worker.protocol.canonical(self.instance),
            "config_sha256": worker.protocol.canonical(self.config),
            "raw_config_sha256": worker.protocol.canonical(self.raw_config)}
        self.declaration = {"protocol": "MOCK_ONLY_NOT_AN_AUTHORIZATION",
            "budgets": {"method_s": 300, "post_s": 60},
            "source_sha256": {"MOCK_ONLY": "not-a-production-source"},
            "environment": {"scope": "mock"}}
        self.write(self.declaration_path, self.declaration)
        self.sequence = 0
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.authority = self.stack.enter_context(patch.object(worker.protocol, "load_active"))
        self.verify = self.stack.enter_context(patch.object(worker.protocol, "verify_files", return_value=True))
        self.stack.enter_context(patch.object(worker, "_environment", return_value={"scope": "MOCK_ONLY"}))
        self.stack.enter_context(patch.object(worker, "_emit"))
        self.stack.enter_context(patch.object(worker.time, "monotonic", self.clock))
        clock = self.clock

        class FakeBudget:
            def __init__(self, seconds):
                self.seconds, self.clock = seconds, clock
                self.start = clock()
                self.deadline = self.start + seconds

            @property
            def elapsed(self):
                return self.clock() - self.start

            def check(self):
                if self.clock() >= self.deadline:
                    raise RuntimeError("MOCK_ONLY budget expiry")

            @contextmanager
            def phase(self, name):
                self.check()
                yield

        self.stack.enter_context(patch("timing.MethodBudget", FakeBudget))
        self.fresh = self.stack.enter_context(patch("p0_batch.run_p0.fresh_input",
            side_effect=lambda case, active: (deepcopy(self.raw_config), deepcopy(self.config), deepcopy(self.instance))))
        self.dispatch = self.stack.enter_context(patch.object(backends, "dispatch"))
        self.heat = self.stack.enter_context(patch("thermal.evaluate_candidate",
            side_effect=AssertionError("NO_REAL_THERMAL_EVALUATION")))
        self.stack.enter_context(patch("thermal.evaluate_piecewise",
            side_effect=AssertionError("NO_REAL_THERMAL_KERNEL")))
        self.stack.enter_context(patch("heft_method.run_heft",
            side_effect=AssertionError("NO_REAL_HEFT")))
        self.stack.enter_context(patch("subprocess.Popen",
            side_effect=AssertionError("NO_PROCESS_OR_NATIVE_SOLVER")))
        self.stack.enter_context(patch("socket.create_connection",
            side_effect=AssertionError("NO_NETWORK")))

    @staticmethod
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def read(path):
        return json.loads(path.read_text(encoding="utf-8"))

    def slot(self, arm="HEFT"):
        self.sequence += 1
        sid = "MOCK_ONLY_" + arm + "_" + str(self.sequence)
        slot = {"slot_id": sid, "case_id": self.instance["id"], "arm": arm,
            "ordinal": self.sequence, "method_seconds": 300, "post_seconds_max": 60}
        case = {"common": deepcopy(self.common), "recipes": {arm: {"MOCK_ONLY": True}}}
        self.authority.return_value = (deepcopy(self.declaration), slot, case)
        out = self.folder / "calls" / sid
        self.write(out / "slot.claim.json", {"scope": "MOCK_ONLY_NOT_AUTHORIZED"})
        return slot, case, out

    def fake_method(self, *, drift=False, twice=False):
        raw = {"state": "MOCK_ONLY", "safe_candidate": None,
               "usable_as_research_evidence": False, "scope": "worker contract test"}
        observed = {}

        def fake_dispatch(arm, loader, path, budget, recipe):
            observed.update(arm=arm, path=path, budget=budget, recipe=recipe,
                root=(budget.start, budget.deadline, budget.seconds, budget.clock))
            config, instance = loader(budget)
            self.assertEqual(config, self.config)
            self.assertEqual(instance, self.instance)
            if twice:
                loader(budget)
            if arm == "C":
                token = {"MOCK_ONLY_actual_root": "one-test-root-token"}
                budget._scene_adapter_budget_identity = deepcopy(token)
                raw["condition"] = {"budget_identity": deepcopy(token)}
                raw["aggregation"] = {"identity": {"budget": deepcopy(token)}}
            if drift:
                budget.deadline += 1
            return {"result": raw, "not_scientific": True,
                "root_start": observed["root"][0], "root_deadline": observed["root"][1],
                "selected_imports_elapsed_s": 0.0, "arm": arm,
                "budget_unchanged": not drift}

        self.dispatch.side_effect = fake_dispatch
        return raw, observed

    def test_unauthorized_method_stops_before_backend_or_input(self):
        slot, _, out = self.slot()
        self.authority.side_effect = ValueError("MOCK_ONLY missing authorization")
        with self.assertRaises(ValueError):
            worker.run_method(self.declaration_path, slot["slot_id"], out)
        self.dispatch.assert_not_called()
        self.fresh.assert_not_called()
        self.assertFalse((out / "worker_started.json").exists())

    def test_wrong_folder_stops_before_backend_or_input(self):
        slot, _, _ = self.slot()
        with self.assertRaises(ValueError):
            worker.run_method(self.declaration_path, slot["slot_id"], self.folder / "wrong")
        self.dispatch.assert_not_called()
        self.fresh.assert_not_called()

    def test_duplicate_method_stops_before_backend(self):
        slot, _, out = self.slot()
        self.write(out / "worker_started.json", {"scope": "prior mock claim"})
        with self.assertRaises(FileExistsError):
            worker.run_method(self.declaration_path, slot["slot_id"], out)
        self.dispatch.assert_not_called()
        self.fresh.assert_not_called()

    def test_all_four_arms_keep_raw_root_input_and_mock_status(self):
        for arm in ("C", "HEFT", "SINGLE", "PAIR"):
            with self.subTest(arm=arm):
                self.dispatch.reset_mock()
                self.fresh.reset_mock()
                slot, case, out = self.slot(arm)
                raw, observed = self.fake_method()
                code = worker.run_method(self.declaration_path, slot["slot_id"], out)
                self.assertEqual(code, 0)
                self.assertEqual(self.read(out / "result.json"), raw)
                self.assertEqual(self.read(out / "wrapper_raw_result.json"), raw)
                identity = self.read(out / "worker_identity.json")
                returned = self.read(out / "worker_return.json")
                self.assertTrue(identity["not_scientific"])
                self.assertTrue(returned["not_scientific"])
                self.assertTrue(identity["input_verified"])
                self.assertTrue(identity["source_verified"])
                self.assertTrue(identity["environment_verified"])
                self.assertEqual(identity["fresh_input_calls"], 1)
                self.assertEqual(identity["root_start_s"], 1000.0)
                self.assertEqual(identity["root_deadline_s"], 1300.0)
                self.assertEqual(identity["common"], self.common)
                self.assertEqual(identity["source_sha256"], self.declaration["source_sha256"])
                self.assertEqual(observed["recipe"], case["recipes"][arm])
                self.assertEqual(identity["input_sha256"], self.common["input_sha256"])
                if arm == "C":
                    self.assertEqual(identity["budget_identity"],
                                     observed["budget"]._scene_adapter_budget_identity)
                self.assertFalse(identity["native_started"])
                self.fresh.assert_called_once()
                self.heat.assert_not_called()

    def test_budget_drift_retains_raw_and_returns_failure(self):
        slot, _, out = self.slot("PAIR")
        raw, _ = self.fake_method(drift=True)
        code = worker.run_method(self.declaration_path, slot["slot_id"], out)
        self.assertEqual(code, 2)
        self.assertEqual(self.read(out / "result.json"), raw)
        self.assertEqual(self.read(out / "wrapper_raw_result.json"), raw)
        returned = self.read(out / "worker_return.json")
        self.assertFalse(returned["passed"])
        self.assertTrue(returned["original_result_saved"])
        self.assertTrue(returned["not_scientific"])
        self.assertIn("Backend changed the root budget", returned["errors"][0]["message"])

    def test_fresh_input_cannot_be_loaded_twice(self):
        slot, _, out = self.slot()
        self.fake_method(twice=True)
        self.assertEqual(worker.run_method(self.declaration_path, slot["slot_id"], out), 2)
        self.fresh.assert_called_once()
        returned = self.read(out / "worker_return.json")
        self.assertIn("loaded once", returned["errors"][0]["message"])

    def test_changed_input_hash_stops_method_before_raw_return(self):
        slot, _, out = self.slot()
        self.fake_method()
        changed = deepcopy(self.instance)
        changed["id"] = "MOCK_ONLY_CHANGED_INPUT"
        self.fresh.side_effect = lambda case, active: (deepcopy(self.raw_config), deepcopy(self.config), changed)
        self.assertEqual(worker.run_method(self.declaration_path, slot["slot_id"], out), 2)
        self.assertFalse((out / "result.json").exists())
        self.assertFalse(self.read(out / "worker_identity.json")["input_verified"])
        self.heat.assert_not_called()

    def post_fixture(self, *, eligible=True):
        slot, _, out = self.slot()
        # This shape is not a physical receipt and must never reach evaluation.
        result = {"state": "MOCK_ONLY", "safe_candidate": deepcopy(self.candidate),
                  "safe_upper_bound_J": "10", "usable_as_research_evidence": False}
        self.write(out / "result.json", result)
        self.write(out / "wrapper_raw_result.json", result)
        self.write(out / "input_instance.json", self.instance)
        self.write(out / "input_config.json", self.config)
        audit = {"scope": "MOCK_ONLY_PRECONDITION_TEST", "eligible_for_post": eligible,
            "admitted_interval": ["10", "10"],
            "candidate_sha256": worker.protocol.canonical(self.candidate),
            "result_sha256": worker.protocol.sha(out / "result.json"),
            "raw_result_sha256": worker.protocol.sha(out / "wrapper_raw_result.json"),
            "input_sha256": self.common["input_sha256"],
            "config_sha256": self.common["config_sha256"],
            "declaration_sha256": worker.protocol.sha(self.declaration_path)}
        self.write(out / "audit.json", audit)
        return slot, out, audit

    def test_post_missing_eligibility_never_calls_evaluator(self):
        slot, out, _ = self.post_fixture(eligible=False)
        with self.assertRaises(ValueError):
            worker.run_post(self.declaration_path, slot["slot_id"], out)
        self.heat.assert_not_called()
        self.assertFalse((out / "postcheck.claim.json").exists())

    def test_duplicate_post_never_calls_evaluator(self):
        slot, out, _ = self.post_fixture()
        self.write(out / "postcheck.claim.json", {"scope": "prior mock claim"})
        with self.assertRaises(FileExistsError):
            worker.run_post(self.declaration_path, slot["slot_id"], out)
        self.heat.assert_not_called()

    def test_wrong_post_hashes_never_call_evaluator_or_replace_U(self):
        fields = ("result_sha256", "raw_result_sha256", "input_sha256", "config_sha256",
                  "declaration_sha256", "candidate_sha256")
        for field in fields:
            with self.subTest(field=field):
                slot, out, audit = self.post_fixture()
                audit[field] = "0" * 64
                self.write(out / "audit.json", audit)
                before = worker.protocol.sha(out / "result.json")
                code = worker.run_post(self.declaration_path, slot["slot_id"], out)
                self.assertEqual(code, 2)
                self.heat.assert_not_called()
                returned = self.read(out / "post_return.json")
                self.assertEqual(returned["evaluation_calls"], 0)
                self.assertFalse(returned["passed"])
                self.assertFalse(returned["new_U"])
                self.assertEqual(worker.protocol.sha(out / "result.json"), before)
                self.assertFalse((out / "postcheck.json").exists())

    def test_mismatched_raw_result_never_calls_post_evaluator(self):
        slot, out, audit = self.post_fixture()
        raw = self.read(out / "wrapper_raw_result.json")
        raw["safe_upper_bound_J"] = "9"
        self.write(out / "wrapper_raw_result.json", raw)
        audit["raw_result_sha256"] = worker.protocol.sha(out / "wrapper_raw_result.json")
        self.write(out / "audit.json", audit)
        self.assertEqual(worker.run_post(self.declaration_path, slot["slot_id"], out), 2)
        self.heat.assert_not_called()

    def test_normal_complete_mock_post_checks_once_and_never_replaces_U(self):
        # All numeric/thermal values here are invented contract payloads. The
        # real receipt checker runs; the physical evaluator remains a mock.
        slot, out, _ = self.post_fixture()
        before = {name: worker.protocol.sha(out / name)
                  for name in ("result.json", "wrapper_raw_result.json")}
        budgets = []

        def evaluate(instance, candidate, accuracy, budget):
            budgets.append(budget)
            self.assertEqual(instance, self.instance)
            self.assertEqual(candidate, self.candidate)
            self.assertEqual(accuracy, self.config["accuracy_targets"])
            self.assertEqual((budget.start, budget.deadline, budget.seconds), (1000.0, 1060.0, 60))
            self.clock.now += 1
            return complete_mock(instance, candidate, accuracy, budget, interval=("10", "10"))

        self.heat.side_effect = evaluate
        from h02_pair_preflight.receipts import safe_receipt
        with patch("h02_pair_preflight.receipts.safe_receipt", wraps=safe_receipt) as checker:
            self.assertEqual(worker.run_post(self.declaration_path, slot["slot_id"], out), 0)
        self.heat.assert_called_once()
        checker.assert_called_once()
        self.assertEqual(len(budgets), 1)
        receipt = self.read(out / "postcheck.json")
        returned = self.read(out / "post_return.json")
        self.assertEqual(receipt["evidence_kind"], "MOCK_ONLY")
        self.assertTrue(returned["passed"])
        self.assertTrue(returned["energy_reproduced"])
        self.assertEqual(returned["evaluation_calls"], 1)
        self.assertEqual(returned["evaluation_elapsed_s"], 1)
        self.assertFalse(returned["new_U"])
        self.assertTrue(returned["no_search_or_repair"])
        self.assertEqual(returned["original_U_J"], "10")
        for name, expected in before.items():
            self.assertEqual(worker.protocol.sha(out / name), expected)
        with self.assertRaises(FileExistsError):
            worker.run_post(self.declaration_path, slot["slot_id"], out)
        self.heat.assert_called_once()

    def test_late_or_disjoint_mock_post_stops_without_retry_or_U_change(self):
        for failure in ("late", "disjoint"):
            with self.subTest(failure=failure):
                self.clock.now = 1000.0
                self.heat.reset_mock()
                slot, out, _ = self.post_fixture()
                before = {name: worker.protocol.sha(out / name)
                          for name in ("result.json", "wrapper_raw_result.json")}

                def evaluate(instance, candidate, accuracy, budget):
                    self.clock.now = 1060.1 if failure == "late" else 1001.0
                    energy = "10" if failure == "late" else "9"
                    return complete_mock(instance, candidate, accuracy, budget,
                                         interval=(energy, energy))

                self.heat.side_effect = evaluate
                self.assertEqual(worker.run_post(self.declaration_path, slot["slot_id"], out), 2)
                self.heat.assert_called_once()
                returned = self.read(out / "post_return.json")
                self.assertFalse(returned["passed"])
                self.assertEqual(returned["evaluation_calls"], 1)
                self.assertFalse(returned["new_U"])
                self.assertTrue(returned["errors"])
                for name, expected in before.items():
                    self.assertEqual(worker.protocol.sha(out / name), expected)
                with self.assertRaises(FileExistsError):
                    worker.run_post(self.declaration_path, slot["slot_id"], out)
                self.heat.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
