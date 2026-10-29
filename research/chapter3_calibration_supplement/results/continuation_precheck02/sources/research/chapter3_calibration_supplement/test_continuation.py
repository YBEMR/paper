"""Read-only real archive identities plus manual/mock continuation tests."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import continuation as c, protocol as p, runtime as r, test_runtime as lifecycle


class ContinuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prior = c.prior_evidence()

    def test_actual_remaining_list_is_exact_not_run_suffix(self):
        old, batch, calls, binding, history = self.prior
        self.assertEqual(calls, old["calls"][3:])
        self.assertEqual(len(calls), 25)
        self.assertEqual(sum(x["axis"] == "S4" for x in calls), 13)
        self.assertEqual(sum(x["axis"] == "S7" for x in calls), 12)
        self.assertEqual(calls[0]["condition_id"], "C12__S4_branch_multi_v1")
        self.assertEqual(binding["retained_conditions"], c.RETAINED)
        self.assertEqual(len(history), 83)

    def test_partition_rejects_failed_claimed_and_preexisting_directory(self):
        old, batch, *_ = self.prior
        for bad in ("FAILED", "CLAIMED", "COMPLETE", "TIMEOUT_OR_LATE"):
            rows = deepcopy(batch["rows"])
            rows[3]["state"] = bad
            with self.subTest(state=bad), self.assertRaises(ValueError):
                c.partition_calls(old["calls"], rows, [])
        with self.assertRaisesRegex(ValueError, "ALREADY_HAS_DIRECTORY"):
            c.partition_calls(old["calls"], batch["rows"], [old["calls"][3]["condition_id"]])

    def test_partition_rejects_missing_duplicate_and_reordered_rows(self):
        old, batch, *_ = self.prior
        rows = batch["rows"]
        for bad in (rows[:-1], [rows[0]] + rows[:-1], rows[:3] + list(reversed(rows[3:]))):
            with self.subTest(length=len(bad)), self.assertRaises(ValueError):
                c.partition_calls(old["calls"], bad, [])

    def test_new_plan_preserves_scientific_rules_and_new_budget_is_closed(self):
        inv = p.inventory()
        plan = c.build_plan(inv, {"manual": "source"}, prior=self.prior)
        original = p.build_plan(inv, {"manual": "source"})
        for key in ("betas", "formal_beta", "new_root_sampling", "reference_mapping", "window_policy", "comparison_policy", "stop_rules", "excluded"):
            self.assertEqual(plan[key], original[key])
        self.assertEqual(plan["limits"], c.LIMITS)
        self.assertFalse(plan["execution_authorized"])
        self.assertEqual(plan["limits"]["family_timetables"], 75)

    def test_old_approval_scope_or_hash_cannot_authorize_remaining_batch(self):
        plan = c.build_plan(p.inventory(), {"manual": "source"}, prior=self.prior)
        new = p.approval_template("new-hash", plan=plan)
        with self.assertRaises(ValueError):
            p.validate_approval(new, "new-hash", plan=plan)
        new.update(approved=True, user_authorization="MANUAL TEST ONLY")
        self.assertTrue(p.validate_approval(new, "new-hash", plan=plan))
        old = p.approval_template("new-hash")
        old.update(approved=True, user_authorization="MANUAL TEST ONLY")
        with self.assertRaises(ValueError):
            p.validate_approval(old, "new-hash", plan=plan)
        with self.assertRaises(ValueError):
            p.validate_approval({**new, "plan_sha256": "old-hash"}, "new-hash", plan=plan)

    def test_tampered_prior_archive_is_rejected_without_writing_old_files(self):
        original = p.sha
        def bad(path):
            return "wrong" if Path(path) == c.PRIOR / "batch_result.json" else original(path)
        with patch.object(p, "sha", side_effect=bad), self.assertRaises(ValueError):
            c.prior_evidence()

    def test_remaining_freeze_roundtrip_and_domain_tampering(self):
        with tempfile.TemporaryDirectory(dir=p.PACKAGE / "results") as temp:
            base = Path(temp)
            checks = base / "manual-checks.json"
            p.write_json(checks, {"state": "PASS", "source_files": p.sources(),
                                 "supplement_conditions_executed": 0, "formal_algorithm_calls": 0, "thermal_integrations": 0})
            frozen = base / "freeze"
            record = c.freeze(frozen, checks)
            plan, _, _ = p.check_frozen(frozen, full_archive_check=True)
            self.assertEqual(record["conditions"], 25)
            self.assertFalse(p.read_json(frozen / "approval_template.json")["approved"])
            self.assertFalse((frozen / "execution_claim.json").exists())
            p.write_json(frozen / "plan.json", {**plan, "calls": self.prior[0]["calls"]})
            with self.assertRaises(ValueError):
                p.check_frozen(frozen)

    def test_mock_25_calls_use_1620_clock_and_cloned_freeze_cannot_reconsume(self):
        with tempfile.TemporaryDirectory(dir=p.PACKAGE / "results") as temp:
            shared = str(Path(temp) / "shared-consumption.json")
            code, result, calls = lifecycle.RuntimeTests()._fake_batch(temp, call_count=25, first_index=3,
                plan_overrides={"scope": c.SCOPE, "limits": c.LIMITS, "consumption_claim_path": shared})
            claim = p.read_json(shared)
            self.assertAlmostEqual(claim["deadline_monotonic"] - claim["started_monotonic"], 1620)
            self.assertEqual(result["rows"][0]["condition_id"], "manual-3")
            self.assertEqual(result["limits"], c.LIMITS)
        self.assertEqual((code, len(calls), result["completed_conditions"]), (0, 25, 25))

    def test_mock_failure_stops_remaining_batch_without_old_replays(self):
        with tempfile.TemporaryDirectory(dir=p.PACKAGE / "results") as temp:
            code, result, calls = lifecycle.RuntimeTests()._fake_batch(temp, call_count=25, first_index=3,
                fail_index=1, plan_overrides={"scope": c.SCOPE, "limits": c.LIMITS,
                                              "consumption_claim_path": str(Path(temp) / "claim.json")})
        self.assertEqual((code, calls), (2, [0, 1]))
        self.assertEqual(result["completed_conditions"], 1)
        self.assertEqual(sum(x["state"] == "NOT_RUN" for x in result["rows"]), 23)

    def test_combined_partial_summary_has_two_execution_accounts(self):
        old, batch, calls, *_ = self.prior
        new = {"state": "STOPPED_EXCEPTION", "elapsed_s": 2.0, "consumed_conditions": 0,
               "completed_conditions": 0, "rows": [{"condition_id": x["condition_id"], "state": "NOT_RUN"} for x in calls]}
        result = c.combine_rows(old["calls"], batch, calls, new)
        self.assertEqual(result["usable_conditions"], 3)
        self.assertEqual(result["planned_conditions"], 28)
        self.assertEqual(result["condition_status_counts"], {"COMPLETE": 3, "NOT_RUN": 25})
        self.assertFalse(result["single_execution_claim"])
        self.assertEqual(result["execution_accounts"]["continuation"]["consumed_conditions"], 0)
        self.assertEqual(result["condition_origin"][c.RETAINED[0]], "original")

    def test_combination_rejects_duplicate_missing_or_replayed_old_item(self):
        old, batch, calls, *_ = self.prior
        rows = [{"condition_id": x["condition_id"], "state": "NOT_RUN"} for x in calls]
        for bad in (rows[:-1], [rows[0]] + rows[:-1], [batch["rows"][0]] + rows[1:]):
            with self.subTest(length=len(bad)), self.assertRaises(ValueError):
                c.combine_rows(old["calls"], batch, calls, {"rows": bad})

    def test_combined_reader_binds_plan_claim_payload_and_exit_status(self):
        from .test_condition import manual_case
        from .condition import evaluate_supplement
        from .analysis import summarize_condition
        call, parent, comparisons = manual_case("S4")
        evidence = evaluate_supplement(call, parent, comparisons)
        summary = summarize_condition(call, evidence, {call["parent_id"]: parent, **comparisons})
        calls = [call] + [{**call, "condition_id": f"manual-pending-{i}"} for i in range(1, 25)]
        old_plan, old_batch, *_ = self.prior
        combined_old = {"calls": old_plan["calls"][:3] + calls}
        with tempfile.TemporaryDirectory(dir=p.PACKAGE / "results") as temp:
            base = Path(temp); out = base / "out"; out.mkdir(); frozen = base / "freeze"; frozen.mkdir()
            shared = base / "shared.json"
            plan = {"calls": calls, "limits": c.LIMITS, "scope": c.SCOPE,
                    "source_files": {"manual": "fixture"}, "consumption_claim_path": str(shared)}
            p.write_json(out / "plan.json", plan)
            record = {"plan_sha256": p.sha(out / "plan.json")}
            approval = p.approval_template(record["plan_sha256"], plan=plan)
            approval.update(approved=True, user_authorization="MANUAL TEST ONLY")
            p.write_json(out / "approval.json", approval)
            claim = {"output": str(out), "plan_sha256": record["plan_sha256"], "approval_sha256": p.sha(out / "approval.json")}
            p.write_json(shared, claim); p.write_json(frozen / "execution_claim.json", claim)
            directory = out / call["condition_id"]; directory.mkdir()
            p.write_json(directory / "call_claim.json", {"token": "manual-token"})
            r.write_gzip(directory / "evidence.json.gz", evidence)
            r.write_gzip(directory / "generated_workload.json.gz", evidence["workload"])
            p.write_json(directory / "summary.json", summary)
            receipt = {"state": "COMPLETE", "condition": call, "elapsed_s": .01, "token": "manual-token",
                       "counters": {**r.ZERO, "timetable_constructions": 3}, "source_files": plan["source_files"],
                       "beta_selected": None, "thermal_status": "NOT_EVALUATED", "energy_status": "NOT_EVALUATED",
                       "evidence_sha256": p.sha(directory / "evidence.json.gz"),
                       "workload_sha256": p.sha(directory / "generated_workload.json.gz"),
                       "summary_sha256": p.sha(directory / "summary.json")}
            p.write_json(directory / "result.json", receipt)
            rows = [{"condition_id": call["condition_id"], "state": "COMPLETE", "summary": summary,
                     "returncode": 0, "elapsed_s": .02, "result_sha256": p.sha(directory / "result.json")}]
            rows += [{"condition_id": x["condition_id"], "state": "NOT_RUN"} for x in calls[1:]]
            batch = {"state": "STOPPED_EXCEPTION", "rows": rows, "limits": c.LIMITS, "planned_conditions": 25,
                     "plan_sha256": record["plan_sha256"], "elapsed_s": .03, "consumed_conditions": 1, "completed_conditions": 1}
            p.write_json(out / "batch_result.json", batch)
            with patch.object(c, "check_frozen", return_value=(plan, {}, record)), \
                 patch.object(c, "prior_evidence", return_value=(combined_old, old_batch)):
                result = c.combined_summary(frozen, out, exit_code=2)
                self.assertEqual(result["usable_conditions"], 4)
                for path in (out / "plan.json", shared, directory / "summary.json", directory / "call_claim.json"):
                    before = path.read_bytes()
                    try:
                        path.write_text('{}', encoding='utf-8')
                        with self.subTest(path=path.name), self.assertRaises((ValueError, KeyError)):
                            c.combined_summary(frozen, out, exit_code=2)
                    finally:
                        path.write_bytes(before)
                p.write_json(out / "batch_result.json", {**batch, "state": "COMPLETE"})
                with self.assertRaisesRegex(ValueError, "ZERO_EXIT_CODE"):
                    c.combined_summary(frozen, out, exit_code=2)


if __name__ == '__main__':
    unittest.main()
