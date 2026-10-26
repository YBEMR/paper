"""Ledger tests consume only synthetic MOCK_PROCESS authorizations."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from .ledger import BUDGETS, Ledger, LedgerError, digest


def authority(name="mock-test"):
    return dict(authorization_id=name, kind="MOCK_PROCESS", scope_sha256="1" * 64,
                source_sha="2" * 40, budgets=deepcopy(BUDGETS))


def context(objective="FULL"):
    return dict(input_sha256="3" * 64, config_sha256="4" * 64,
                accuracy_sha256="5" * 64, objective=objective)


def token():
    return dict(**context(), planning_score_sha256="6" * 64,
                receipt_sha256="7" * 64, candidate_sha256="8" * 64)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="e1-mock-ledger-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.auth = authority()
        self.store = self.path / "authority"
        self.run_dir = self.path / "output"
        self.ledger = Ledger(self.store, self.auth, self.run_dir)
        self.batch = self.ledger.claim_batch({"manifest_sha256": "9" * 64})

    def plan(self, ordinal=1):
        claim = self.ledger.claim_plan(ordinal, 123.0, context())
        self.ledger.consume_launch(claim, "a" * 64, self.path / "worker")
        return claim

    def finish_selected(self):
        self.plan()
        return self.ledger.finish_plan(1, "b" * 64, token())

    def test_batch_claim_is_not_refunded_by_reconstruction(self):
        other = Ledger(self.store, self.auth, self.run_dir)
        with self.assertRaisesRegex(LedgerError, "ALREADY_CONSUMED"):
            other.claim_batch({"manifest_sha256": "9" * 64})

    def test_output_directory_change_cannot_reuse_authorization(self):
        other = Ledger(self.store, self.auth, self.path / "different-output")
        with self.assertRaisesRegex(LedgerError, "ALREADY_CONSUMED"):
            other.claim_batch({"manifest_sha256": "9" * 64})
        with self.assertRaisesRegex(LedgerError, "OUTPUT_DRIFT"):
            other.claim_plan(1, 123, context())

    def test_source_or_scope_change_cannot_reuse_identifier(self):
        for key, value in (("source_sha", "a" * 40), ("scope_sha256", "a" * 64)):
            changed = deepcopy(self.auth)
            changed[key] = value
            other = Ledger(self.store, changed, self.run_dir)
            with self.assertRaisesRegex(LedgerError, "DRIFT"):
                other.claim_plan(1, 123, context())

    def test_mock_authorization_cannot_be_used_as_real_or_reverse(self):
        with self.assertRaisesRegex(LedgerError, "KIND_MISMATCH"):
            Ledger(self.store, self.auth, self.run_dir, kind="REAL_RESEARCH")
        changed = deepcopy(self.auth)
        changed["kind"] = "REAL_RESEARCH"
        with self.assertRaisesRegex(LedgerError, "KIND_MISMATCH"):
            Ledger(self.store, changed, self.run_dir)

    def test_claim_contains_frozen_origin_budget_and_valid_hash(self):
        claim = self.plan()
        self.assertEqual((claim["root_origin"], claim["limit_s"], claim["kind"]),
                         (123.0, 300, "MOCK_PROCESS"))
        unsigned = deepcopy(claim)
        saved = unsigned.pop("claim_sha256")
        self.assertEqual(saved, digest(unsigned))
        self.assertEqual(claim["context_sha256"], digest(context()))

    def test_plan_consumption_survives_no_launch_or_failed_process(self):
        self.ledger.claim_plan(1, 123, context())
        other = Ledger(self.store, self.auth, self.run_dir)
        with self.assertRaisesRegex(LedgerError, "PLAN_ALREADY_CONSUMED"):
            other.claim_plan(1, 999, context())
        with self.assertRaisesRegex(LedgerError, "MISSING_OR_CORRUPT"):
            other.claim_plan(2, 999, context())

    def test_plan_order_requires_previous_post_completion(self):
        self.finish_selected()
        with self.assertRaisesRegex(LedgerError, "MISSING_OR_CORRUPT"):
            self.ledger.claim_plan(2, 999, context())
        claim = self.ledger.claim_post(1, 400, token())
        self.assertEqual(claim["limit_s"], 60)
        with self.assertRaisesRegex(LedgerError, "MISSING_OR_CORRUPT"):
            self.ledger.claim_plan(2, 999, context())
        with self.assertRaisesRegex(LedgerError, "MISSING_OR_CORRUPT"):
            self.ledger.finish_post(1, "c" * 64)
        self.ledger.consume_launch(claim, "c" * 64, self.path / "post-worker")
        self.ledger.finish_post(1, "c" * 64)
        self.ledger.claim_plan(2, 999, context())

    def test_post_unlaunched_normal_deadline_is_recorded_and_can_advance(self):
        self.finish_selected()
        self.ledger.claim_post(1, 400, token())
        proof = {"reason": "ROOT_DEADLINE_BEFORE_SPAWN", "observed_monotonic": 460.0}
        result = self.ledger.finish_post(1, "c" * 64, not_launched_deadline=proof)
        self.assertEqual(result["not_launched_deadline"], proof)
        self.assertFalse((self.ledger.root / "01_post_launch.json").exists())
        self.ledger.claim_plan(2, 500, context())
        with self.assertRaisesRegex(LedgerError, "POST_ALREADY_CONSUMED"):
            self.ledger.claim_post(1, 500, token())

    def test_post_unlaunched_proof_rejects_early_or_malformed_time(self):
        self.finish_selected()
        self.ledger.claim_post(1, 400, token())
        for observed in (459.999, True, float("nan"), float("inf"), "460"):
            proof = {"reason": "ROOT_DEADLINE_BEFORE_SPAWN", "observed_monotonic": observed}
            with self.assertRaisesRegex(LedgerError, "NOT_EXPIRED"):
                self.ledger.finish_post(1, "c" * 64, not_launched_deadline=proof)
        for proof in ({}, {"reason": "OTHER", "observed_monotonic": 460},
                      {"reason": "ROOT_DEADLINE_BEFORE_SPAWN", "observed_monotonic": 460, "x": 1}):
            with self.assertRaisesRegex(LedgerError, "PROOF"):
                self.ledger.finish_post(1, "c" * 64, not_launched_deadline=proof)
        self.assertFalse((self.ledger.root / "01_post_finish.json").exists())

    def test_post_unlaunched_deadline_rejects_launch_and_stop_contradictions(self):
        self.finish_selected()
        claim = self.ledger.claim_post(1, 400, token())
        proof = {"reason": "ROOT_DEADLINE_BEFORE_SPAWN", "observed_monotonic": 460}
        with self.assertRaisesRegex(LedgerError, "CONTRADICTION"):
            self.ledger.finish_post(1, "c" * 64, stop_required=True, not_launched_deadline=proof)
        self.ledger.consume_launch(claim, "c" * 64, self.path / "post-worker")
        with self.assertRaisesRegex(LedgerError, "CONTRADICTION"):
            self.ledger.finish_post(1, "c" * 64, not_launched_deadline=proof)
        self.ledger.finish_post(1, "c" * 64)

    def test_no_selected_candidate_does_not_require_post(self):
        self.plan()
        self.ledger.finish_plan(1, "b" * 64)
        self.ledger.claim_plan(2, 500, context())

    def test_selected_token_is_bound_to_plan_inputs_and_objective(self):
        self.plan()
        changed = token()
        changed["objective"] = "OMIT_TEMP"
        with self.assertRaisesRegex(LedgerError, "PLAN_SCOPE_DRIFT"):
            self.ledger.finish_plan(1, "b" * 64, changed)
        self.ledger.finish_plan(1, "b" * 64, token())

    def test_selected_safe_token_requires_actual_launch_claim(self):
        self.ledger.claim_plan(1, 123, context())
        with self.assertRaisesRegex(LedgerError, "MISSING_OR_CORRUPT"):
            self.ledger.finish_plan(1, "b" * 64, token())

    def test_post_is_bound_to_exact_final_receipt_candidate_and_score(self):
        self.finish_selected()
        for key in token():
            changed = token()
            changed[key] = "OMIT_TEMP" if key == "objective" else "f" * 64
            with self.assertRaisesRegex(LedgerError, "NOT_FINAL_SELECTED"):
                self.ledger.claim_post(1, 500, changed)
        self.ledger.claim_post(1, 500, token())
        with self.assertRaisesRegex(LedgerError, "POST_ALREADY_CONSUMED"):
            self.ledger.claim_post(1, 501, token())

    def test_launch_is_once_and_parent_claim_exact(self):
        claim = self.plan()
        with self.assertRaisesRegex(LedgerError, "LAUNCH_ALREADY_CONSUMED"):
            self.ledger.consume_launch(claim, "a" * 64, self.path / "other-worker")
        changed = deepcopy(claim)
        changed["root_origin"] = 999
        with self.assertRaisesRegex(LedgerError, "PARENT_CLAIM_MISMATCH"):
            self.ledger.consume_launch(changed, "a" * 64, self.path / "worker")

    def test_launch_checks_job_hash_if_frozen_in_context(self):
        ctx = context()
        ctx["job_sha256"] = "a" * 64
        claim = self.ledger.claim_plan(1, 123, ctx)
        with self.assertRaisesRegex(LedgerError, "JOB_HASH_MISMATCH"):
            self.ledger.consume_launch(claim, "b" * 64, self.path / "worker")
        self.ledger.consume_launch(claim, "a" * 64, self.path / "worker")

    def test_persistent_stop_prevents_further_calls_but_allows_archive(self):
        self.plan()
        self.ledger.stop("TECHNICAL_FAILURE")
        self.ledger.finish_plan(1, "b" * 64)
        other = Ledger(self.store, self.auth, self.run_dir)
        with self.assertRaisesRegex(LedgerError, "BATCH_STOPPED"):
            other.claim_plan(2, 500, context())
        self.assertEqual(other.stop("OTHER")["reason"], "TECHNICAL_FAILURE")

    def test_finish_stop_and_duplicate_finish(self):
        self.plan()
        self.ledger.finish_plan(1, "b" * 64, stop_required=True)
        with self.assertRaisesRegex(LedgerError, "ALREADY_RECORDED"):
            self.ledger.finish_plan(1, "b" * 64)
        with self.assertRaisesRegex(LedgerError, "BATCH_STOPPED"):
            self.ledger.claim_plan(2, 500, context())

    def test_abandoned_lock_is_fail_closed(self):
        (self.ledger.root / "mutation.lock").write_bytes(b"crashed writer")
        with self.assertRaisesRegex(LedgerError, "BUSY_OR_ABANDONED"):
            self.ledger.claim_plan(1, 123, context())

    def test_truncated_claim_remains_consumed(self):
        (self.ledger.root / "01_plan_claim.json").write_bytes(b"{")
        with self.assertRaisesRegex(LedgerError, "ALREADY_CONSUMED"):
            self.ledger.claim_plan(1, 123, context())

    def test_concurrent_controllers_only_one_claims_same_slot(self):
        def attempt(unused):
            try:
                Ledger(self.store, self.auth, self.run_dir).claim_plan(1, 123, context())
                return True
            except LedgerError:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            successes = list(pool.map(attempt, range(8)))
        self.assertEqual(sum(successes), 1)

    def test_another_process_cannot_reclaim(self):
        self.ledger.claim_plan(1, 123, context())
        code = """import json,sys
from e1_objective.ledger import Ledger,LedgerError
try:
 Ledger(sys.argv[1],json.loads(sys.argv[2]),sys.argv[3]).claim_plan(1,999,json.loads(sys.argv[4]))
except LedgerError as error:
 print(str(error));sys.exit(23)
sys.exit(24)
"""
        run = subprocess.run([sys.executable, "-B", "-c", code, str(self.store),
                              json.dumps(self.auth), str(self.run_dir), json.dumps(context())],
                             cwd=Path(__file__).resolve().parent.parent,
                             capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 23, run.stderr)
        self.assertIn("PLAN_ALREADY_CONSUMED", run.stdout)

    def test_budget_and_ordinal_validation(self):
        changed = deepcopy(self.auth)
        changed["budgets"]["plan_s"] = 301
        with self.assertRaisesRegex(LedgerError, "BUDGETS"):
            Ledger(self.store, changed, self.run_dir)
        for ordinal in (0, 5, True, "1"):
            with self.assertRaisesRegex(LedgerError, "ORDINAL"):
                self.ledger.claim_plan(ordinal, 123, context())
        for origin in (-1, float("nan"), float("inf"), True):
            with self.assertRaisesRegex(LedgerError, "ROOT_ORIGIN"):
                self.ledger.claim_plan(1, origin, context())


if __name__ == "__main__":
    unittest.main()
