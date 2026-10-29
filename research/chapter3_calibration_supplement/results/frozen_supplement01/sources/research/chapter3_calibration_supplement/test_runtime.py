"""Pure approval/lifecycle tests. Child processes and scientific work are fakes."""

from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch, Mock

from . import protocol as p, runtime as r


class ProtocolTests(unittest.TestCase):
    def test_frozen_inventory_uses_exact_old_twenty_roots(self):
        inv = p.inventory()
        plan = p.build_plan(inv, {"manual.py": "fixture"})
        self.assertEqual(len(plan["calls"]), 28)
        self.assertEqual(len({x["root_id"] for x in plan["calls"]}), 20)
        self.assertEqual(plan["betas"], ["1", "1.3", "1.6", "2"])
        self.assertIsNone(plan["formal_beta"])
        self.assertFalse(plan["execution_authorized"])
        self.assertEqual(plan["limits"]["condition_seconds"], 60)
        self.assertEqual(plan["limits"]["batch_seconds"], 1800)

    def test_approval_template_rejected_and_scope_budget_identity_bound(self):
        good = p.approval_template("fixture-hash")
        with self.assertRaises(ValueError):
            p.validate_approval(good, "fixture-hash")
        good.update(approved=True, user_authorization="MANUAL TEST ONLY")
        self.assertTrue(p.validate_approval(good, "fixture-hash"))
        for field, value in (("scope", "other"), ("plan_sha256", "wrong"),
                             ("single_use", False), ("user_authorization", ""),
                             ("limits", {**p.LIMITS, "condition_seconds": 61})):
            bad = deepcopy(good)
            bad[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                p.validate_approval(bad, "fixture-hash")

    def test_output_must_be_new_and_in_independent_package(self):
        with self.assertRaises(ValueError):
            p.result_path(p.REPO / "research/chapter3_experiments/results/forbidden")
        with self.assertRaises(ValueError):
            p.result_path(p.PACKAGE / "results", fresh=True)

    def test_unapproved_execute_has_no_process_claim_or_output(self):
        with tempfile.TemporaryDirectory(dir=p.PACKAGE / "results") as temp:
            base = Path(temp)
            approval = base / "approval.json"
            p.write_json(approval, p.approval_template("fixture"))
            frozen = base / "freeze"
            frozen.mkdir()
            with patch.object(r, "check_frozen", return_value=({}, {}, {"plan_sha256": "fixture"})), \
                 patch.object(r.subprocess, "Popen", side_effect=AssertionError("must not launch")):
                with self.assertRaises(ValueError):
                    r.execute(frozen, base / "out", approval)
            self.assertFalse((frozen / "execution_claim.json").exists())
            self.assertFalse((base / "out").exists())

    def test_freeze_roundtrip_is_closed_and_plan_drift_rejected(self):
        with tempfile.TemporaryDirectory(dir=p.PACKAGE / "results") as temp:
            base = Path(temp)
            checks = base / "manual-checks.json"
            p.write_json(checks, {"state": "PASS", "source_files": p.sources(),
                                 "supplement_conditions_executed": 0,
                                 "formal_algorithm_calls": 0, "thermal_integrations": 0})
            frozen = base / "freeze"
            record = p.freeze(frozen, checks)
            self.assertEqual(record["state"], "FROZEN_NOT_AUTHORIZED")
            plan, inv, _ = p.check_frozen(frozen, full_archive_check=True)
            self.assertEqual(len(inv["calls"]), 28)
            self.assertFalse(p.read_json(frozen / "approval_template.json")["approved"])
            self.assertFalse((frozen / "execution_claim.json").exists())
            p.write_json(frozen / "plan.json", {**plan, "formal_beta": "1.3"})
            with self.assertRaises(ValueError):
                p.check_frozen(frozen)


class RuntimeTests(unittest.TestCase):
    def test_acceptance_timeout_missing_and_scope_states(self):
        complete = {"state": "COMPLETE", "elapsed_s": 59.0, "denied_imports": [], "denied_events": []}
        cases = [(0, complete, 59.5, "COMPLETE"), (0, complete, 60.1, "TIMEOUT_OR_LATE"),
                 (0, {**complete, "elapsed_s": 61}, 59, "TIMEOUT_OR_LATE"),
                 (1, complete, 59, "FAILED"), (0, None, 59, "FAILED"),
                 (0, {**complete, "denied_imports": ["thermal"]}, 59, "SCOPE_FAILURE")]
        for code, receipt, elapsed, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(r.decide_call_state(code, receipt, elapsed, 60), expected)

    def test_worker_direct_command_needs_batch_and_slot(self):
        with tempfile.TemporaryDirectory(dir=p.PACKAGE / "results") as temp:
            base = Path(temp)
            fake_plan = {"calls": [{"condition_id": "manual"}]}
            with patch.object(r, "check_frozen", return_value=(fake_plan, {}, {"plan_sha256": "fixture"})):
                with self.assertRaises(FileNotFoundError):
                    r.validate_worker_context(base, base, 0, "token")
                p.write_json(base / "approval.json", p.approval_template("fixture"))
                with self.assertRaises(ValueError):
                    r.validate_worker_context(base, base, 0, "token")

    def test_invalid_elapsed_or_limit_is_rejected(self):
        complete = {"state": "COMPLETE", "elapsed_s": 1.0}
        for bad in (float("nan"), float("inf"), -1.0, "1", True, None):
            with self.subTest(value=bad):
                self.assertEqual(r.decide_call_state(0, complete, bad, 60), "INVALID_CLOCK")
                self.assertEqual(r.decide_call_state(0, complete, 1, bad), "INVALID_CLOCK")
                self.assertEqual(r.decide_call_state(0, {**complete, "elapsed_s": bad}, 1, 60), "INVALID_CLOCK")

    def test_worker_claim_bound_to_budget_and_slot_token(self):
        with tempfile.TemporaryDirectory(dir=p.PACKAGE / "results") as temp:
            base = Path(temp)
            call = {"condition_id": "manual"}
            plan = {"calls": [call]}
            approval = p.approval_template("fixture")
            approval.update(approved=True, user_authorization="MANUAL TEST ONLY")
            p.write_json(base / "approval.json", approval)
            batch = {"output": str(base.resolve()), "plan_sha256": "fixture",
                     "approval_sha256": p.sha(base / "approval.json"),
                     "started_monotonic": 10.0, "deadline_monotonic": 1810.0}
            p.write_json(base / "execution_claim.json", batch)
            directory = base / "manual"
            directory.mkdir()
            claim = {"index": 0, "call": call, "token": "token", "plan_sha256": "fixture",
                     "started_monotonic": 100.0, "deadline_monotonic": 160.0}
            p.write_json(directory / "call_claim.json", claim)
            with patch.object(r, "check_frozen", return_value=(plan, {}, {"plan_sha256": "fixture"})), \
                 patch.object(r.time, "perf_counter", return_value=110.0):
                self.assertEqual(r.validate_worker_context(base, base, 0, "token")[2], call)
                with self.assertRaises(ValueError):
                    r.validate_worker_context(base, base, 0, "wrong")
                p.write_json(directory / "call_claim.json", {**claim, "deadline_monotonic": 161.0})
                with self.assertRaises(ValueError):
                    r.validate_worker_context(base, base, 0, "token")

    def test_timeout_kills_only_current_mock_child_once(self):
        with tempfile.TemporaryDirectory() as temp:
            proc = Mock()
            proc.wait.side_effect = [subprocess.TimeoutExpired("manual", 1), 0]
            proc.poll.return_value = None
            with patch.object(r.subprocess, "Popen", return_value=proc) as spawn:
                self.assertEqual(r.launch_worker(["manual"], Path(temp) / "log", r.time.perf_counter()+1), -1)
            self.assertEqual(spawn.call_count, 1)
            proc.kill.assert_called_once()

    def test_manual_worker_output_acceptance_and_duplicate_rejection(self):
        from .test_condition import manual_case
        call, parent, comparisons = manual_case("S7")
        old = {call["parent_id"]: parent, **comparisons}
        with tempfile.TemporaryDirectory(dir=p.PACKAGE / "results") as temp:
            directory = Path(temp) / "manual-worker"
            directory.mkdir()
            started = r.time.perf_counter()
            context = ({}, {}, call, directory, started, started + 60)
            with patch.object(r, "validate_worker_context", return_value=context), \
                 patch.object(r, "load_evidence", side_effect=lambda inv, name: deepcopy(old[name])), \
                 patch.object(r.subprocess, "Popen", side_effect=AssertionError("no process")):
                self.assertEqual(r.worker(Path(temp), Path(temp), 0, "manual-token"), 0)
                first_bytes = (directory / "result.json").read_bytes()
                receipt, summary = r.accept_receipt(directory, call, {"token": "manual-token"}, p.sources())
                self.assertEqual(receipt["counters"], {**r.ZERO, "timetable_constructions": 3})
                self.assertEqual(summary["state"], "SUPPLEMENT_CONDITION_SUMMARY_COMPLETE")
                self.assertEqual(r.worker(Path(temp), Path(temp), 0, "manual-token"), 2)
                self.assertEqual((directory / "result.json").read_bytes(), first_bytes)
                self.assertTrue((directory / "worker_rejection.json").is_file())
                with self.assertRaises(ValueError):
                    r.accept_receipt(directory, call, {"token": "wrong-token"}, p.sources())
                (directory / "summary.json").write_text("{}", encoding="utf-8")
                with self.assertRaises(ValueError):
                    r.accept_receipt(directory, call, {"token": "manual-token"}, p.sources())

    def _fake_batch(self, temp, *, fail_index=None, corrupt_index=None, throw_index=None):
        base = Path(temp)
        frozen = base / "freeze"
        frozen.mkdir()
        calls = [{"condition_id": f"manual-{n}", "axis": "S4", "root_id": f"manual-{n}", "scale": 24}
                 for n in range(28)]
        plan = {"calls": calls, "source_files": {"manual": "fixture"}}
        record = {"plan_sha256": "fixture", "protected_files": {"old": "unchanged"}}
        p.write_json(frozen / "plan.json", plan)
        approval = p.approval_template("fixture")
        approval.update(approved=True, user_authorization="MANUAL TEST ONLY")
        p.write_json(base / "approval.json", approval)
        launched = []

        def launch(args, logfile, deadline):
            directory = Path(logfile).parent
            index = len(launched)
            launched.append(index)
            if index == throw_index:
                raise OSError("injected launch failure")
            receipt = {"state": "FAILED" if index == fail_index else "COMPLETE",
                       "elapsed_s": 0.01, "counters": {**r.ZERO, "timetable_constructions": 3},
                       "denied_imports": [], "denied_events": []}
            if index == corrupt_index:
                (directory / "result.json").write_text("{broken", encoding="utf-8")
            else:
                p.write_json(directory / "result.json", receipt)
            return 0

        def accept(directory, call, claim, source_map):
            return p.read_json(directory / "result.json"), {"manual_summary": True}

        with ExitStack() as stack:
            stack.enter_context(patch.object(r, "check_frozen", return_value=(plan, {}, record)))
            stack.enter_context(patch.object(r, "protected", return_value=record["protected_files"]))
            stack.enter_context(patch.object(r, "sources", return_value=plan["source_files"]))
            stack.enter_context(patch.object(r, "launch_worker", side_effect=launch))
            stack.enter_context(patch.object(r, "accept_receipt", side_effect=accept))
            stack.enter_context(patch("research.chapter3_calibration_supplement.analysis.aggregate_summaries",
                                     return_value={"manual_simulation": True}))
            code = r.execute(frozen, base / "out", base / "approval.json")
            with self.assertRaises(FileExistsError):
                r.execute(frozen, base / "another-output", base / "approval.json")
        return code, p.read_json(base / "out/batch_result.json"), launched

    def test_mock_28_slots_complete_once_without_scientific_calls(self):
        with tempfile.TemporaryDirectory(dir=p.PACKAGE / "results") as temp:
            code, receipt, launches = self._fake_batch(temp)
        self.assertEqual(code, 0)
        self.assertEqual(len(launches), 28)
        self.assertEqual(receipt["completed_conditions"], 28)
        self.assertEqual(receipt["state"], "COMPLETE")

    def test_first_failure_stops_and_marks_remainder_not_run(self):
        with tempfile.TemporaryDirectory(dir=p.PACKAGE / "results") as temp:
            code, receipt, launches = self._fake_batch(temp, fail_index=1)
        self.assertEqual(code, 2)
        self.assertEqual(launches, [0, 1])
        self.assertEqual(receipt["completed_conditions"], 1)
        self.assertEqual(receipt["consumed_conditions"], 2)
        self.assertEqual(sum(row["state"] == "NOT_RUN" for row in receipt["rows"]), 26)

    def test_malformed_receipt_is_terminal_not_silent_exit(self):
        with tempfile.TemporaryDirectory(dir=p.PACKAGE / "results") as temp:
            code, receipt, launches = self._fake_batch(temp, corrupt_index=0)
        self.assertEqual(code, 2)
        self.assertEqual(launches, [0])
        self.assertEqual(receipt["state"], "STOPPED_EXCEPTION")
        self.assertEqual(receipt["rows"][0]["state"], "FAILED")
        self.assertEqual(sum(row["state"] == "NOT_RUN" for row in receipt["rows"]), 27)

    def test_launch_exception_is_consumed_and_not_retried(self):
        with tempfile.TemporaryDirectory(dir=p.PACKAGE / "results") as temp:
            code, receipt, launches = self._fake_batch(temp, throw_index=0)
        self.assertEqual(code, 2)
        self.assertEqual(launches, [0])
        self.assertEqual(receipt["consumed_conditions"], 1)
        self.assertEqual(receipt["rows"][0]["state"], "FAILED")


if __name__ == "__main__":
    unittest.main()
