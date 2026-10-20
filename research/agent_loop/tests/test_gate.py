"""TEST_ONLY fixtures: local temporary Git repos, no research/solver imports.

Run: python -m unittest discover -s research/agent_loop/tests -v
E2E trace: python research/agent_loop/tests/test_gate.py --e2e
"""
from __future__ import annotations

import base64
import copy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gate import Gate, GateDenied, canonical_json, sha256, signature_message, strict_json
from git_store import CASConflict, GitLedgerStore

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
except ImportError:
    Ed25519PrivateKey = None


class Fixture:
    def __init__(self):
        if Ed25519PrivateKey is None:
            raise RuntimeError("cryptography required; no fake verification")
        self.base = Path(os.environ.get("AGENT_LOOP_TEST_TMP", str(Path(__file__).resolve().parents[3] / ".runtime" / "agent_loop_tests"))).resolve()
        self.base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="TEST_ONLY-", dir=self.base)
        self.root = Path(self.temp.name)
        self.repo = self.root / "subject"
        self.remote = self.root / "remote.git"
        self.repo.mkdir()
        self.git("init", "--quiet", "-b", "main")
        self.git("config", "user.name", "TEST_ONLY fixture")
        self.git("config", "user.email", "TEST_ONLY@invalid")
        subprocess.run(["git", "init", "--bare", "--quiet", str(self.remote)], check=True, capture_output=True)
        self.namespace = "TEST_ONLY-" + uuid.uuid4().hex
        self.key = Ed25519PrivateKey.generate()  # memory only; never exported to disk
        public = self.key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.now = datetime(2026, 10, 20, tzinfo=timezone.utc)
        self.config = {"schema_version": 1, "mode": "TEST_ONLY", "enabled": True, "ALLOW_REAL_EXPERIMENTS": False,
                       "repository": {"remote_url": str(self.remote), "ledger_ref": "refs/heads/TEST_ONLY/" + self.namespace},
                       "review_source": {"source_id": "TEST_ONLY-independent", "key_id": "TEST_ONLY-key",
                                         "public_key_ed25519_base64": base64.b64encode(public).decode(), "github_login": "TEST_ONLY"},
                       "limits": {"max_rounds": 3, "max_calls": 4, "per_call_budget_seconds": 5,
                                  "total_budget_seconds": 20, "wall_clock_limit_seconds": 60,
                                  "deadline_utc": "2026-10-21T00:00:00Z", "max_consecutive_failures": 2,
                                  "max_consecutive_no_improvement": 2},
                       "allowed_scope": ["TEST_ONLY-output"],
                       "test_only": {"namespace": self.namespace, "temporary_root": str(self.root)}}
        self.config_path = self.repo / "config.json"
        self.config_path.write_bytes(canonical_json(self.config))
        self.config_hash = sha256(self.config_path.read_bytes())
        self.env = {"AGENT_LOOP_TRUSTED_CONFIG_SHA256": self.config_hash, "AGENT_LOOP_TEST_TMP": str(self.base)}
        self.manifest_path = "round/manifest.json"
        self.files = {"round/next_proposal.md": b"TEST_ONLY inert proposal; no research task.\n",
                      "round/report.md": b"TEST_ONLY infrastructure report, not research evidence.\n",
                      "fixture_source.txt": b"TEST_ONLY inert fixture source\n",
                      "fixture_evidence.txt": b"TEST_ONLY synthetic fixture bytes\n"}
        for path, data in self.files.items():
            self.write(path, data)
        self.action = {"action_id": "TEST_ONLY-noop", "action_kind": "REAL_EXPERIMENT",
                       "allowed_scope": ["TEST_ONLY-output"], "max_calls": 2, "per_call_budget_seconds": 5,
                       "total_budget_seconds": 10, "wall_clock_limit_seconds": 30}
        self.manifest = {"schema_version": 1, "mode": "TEST_ONLY", "repository": str(self.remote),
                         "config_sha256": self.config_hash, "round_id": "TEST_ONLY-round-1",
                         "proposal_path": "round/next_proposal.md", "proposal_sha256": sha256(self.files["round/next_proposal.md"]),
                         "report_md_path": "round/report.md", "report_md_sha256": sha256(self.files["round/report.md"]),
                         "evidence_class": "TEST_ONLY", "source_files": {"fixture_source.txt": sha256(self.files["fixture_source.txt"])},
                         "evidence_files": {"fixture_evidence.txt": sha256(self.files["fixture_evidence.txt"])}, "proposed_action": self.action}
        self.write(self.manifest_path, canonical_json(self.manifest))
        self.commit = self.commit_all()
        review_dir = "TEST_ONLY-reviews/TEST_ONLY-round-1"
        self.review_report = review_dir + "/review.md"
        self.write(self.review_report, b"TEST_ONLY independent-review fixture; never a real approval.\n")
        self.approval = self.repo / review_dir / "review.json"
        self.review = {"schema_version": 1, "mode": "TEST_ONLY", "repository": str(self.remote),
                       "config_sha256": self.config_hash, "approval_id": "TEST_ONLY-approval-1",
                       "round_id": self.manifest["round_id"], "subject_commit_sha": self.commit,
                       "manifest_path": self.manifest_path, "manifest_sha256": sha256(canonical_json(self.manifest)),
                       "proposal_sha256": self.manifest["proposal_sha256"], "report_md_sha256": self.manifest["report_md_sha256"],
                       "evidence_class": "TEST_ONLY", "decision": "APPROVE_ONE_STEP", "approved_action": self.action["action_id"],
                       "action_kind": self.action["action_kind"], "allowed_scope": self.action["allowed_scope"],
                       **{field: self.action[field] for field in Gate.BUDGET_FIELDS},
                       "expiration": "2026-10-20T01:00:00Z",
                       "review_report_path": self.review_report,
                       "review_report_sha256": sha256((self.repo / self.review_report).read_bytes()),
                       "review_identity": {"source_id": "TEST_ONLY-independent", "key_id": "TEST_ONLY-key",
                                           "reviewer_id": "TEST_ONLY-reviewer", "github_login": "TEST_ONLY"}}
        self.sign()
        self.gates = []

    def git(self, *args):
        result = subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True)
        return result.stdout.decode().strip()

    def write(self, path, data):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def commit_all(self):
        # Fixture repository only; never the shared workspace Git database.
        self.git("add", "--all")
        self.git("commit", "--quiet", "-m", "TEST_ONLY inert fixture")
        return self.git("rev-parse", "HEAD")

    def sign(self):
        self.review["signature"] = {"algorithm": "Ed25519", "value_base64": base64.b64encode(self.key.sign(signature_message(self.review))).decode()}
        self.approval.write_bytes(canonical_json(self.review))

    def gate(self, **kwargs):
        gate = Gate(self.repo, self.config_path, mode="TEST_ONLY", environ=self.env, now=lambda: self.now, **kwargs)
        self.gates.append(gate)
        return gate

    def claim(self, gate):
        return gate.claim(self.approval, requested_action=self.action["action_id"], requested_scope=["TEST_ONLY-output/result.json"])

    def permit(self, gate, claim, budget=5):
        return gate.issue_permit(claim, requested_action=self.action["action_id"], requested_scope=["TEST_ONLY-output/result.json"], budget_seconds=budget)

    def close(self):
        for gate in self.gates:
            gate.close()
        self.temp.cleanup()

    def new_round(self, index):
        self.manifest["round_id"] = "TEST_ONLY-round-" + str(index)
        self.write(self.manifest_path, canonical_json(self.manifest))
        self.commit = self.commit_all()
        self.review.update(round_id=self.manifest["round_id"], approval_id="TEST_ONLY-approval-" + str(index),
                           subject_commit_sha=self.commit, manifest_sha256=sha256(canonical_json(self.manifest)))
        self.sign()


@unittest.skipIf(Ed25519PrivateKey is None, "cryptography missing; production gate rejects verification")
class GateTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()

    def tearDown(self):
        self.f.close()

    def test_normal_signed_subject_claim_permit_and_finish(self):
        gate = self.f.gate()
        claim = self.f.claim(gate)
        self.assertEqual("TEST_ONLY", self.f.permit(gate, claim)["mode"])
        self.f.permit(gate, claim)
        gate.finish(claim, outcome="IMPROVED")
        state = gate.store.read().ledger
        self.assertEqual((1, 2, 10), (state["rounds_consumed"], state["calls_reserved"], state["budget_reserved_seconds"]))
        self.assertIsNone(state["active_claim_id"])
        self.assertEqual("COMPLETED", state["claims"][claim]["status"])

    def test_duplicate_trigger_and_crash_running_remain_blocked(self):
        gate = self.f.gate()
        claim = self.f.claim(gate)
        with self.assertRaisesRegex(GateDenied, "RUNNING"):
            self.f.claim(self.f.gate())
        gate.finish(claim, outcome="IMPROVED")
        with self.assertRaisesRegex(GateDenied, "consumed"):
            self.f.claim(self.f.gate())

    def test_simultaneous_initial_cas_only_one_claim(self):
        gates = [self.f.gate(), self.f.gate()]
        barrier = threading.Barrier(2)
        for gate in gates:
            original = gate.store.compare_and_swap
            def contested(head, state, original=original):
                barrier.wait(timeout=20)
                return original(head, state)
            gate.store.compare_and_swap = contested
        def attempt(gate):
            try:
                return self.f.claim(gate)
            except GateDenied:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, gates))
        self.assertEqual(1, sum(value is not None for value in results))
        self.assertEqual(1, gates[0].store.read().ledger["rounds_consumed"])

    def test_simultaneous_existing_head_cas_only_one_permit(self):
        first, second = self.f.gate(), self.f.gate()
        claim = self.f.claim(first)
        barrier = threading.Barrier(2)
        for gate in (first, second):
            original = gate.store.compare_and_swap
            def contested(head, state, original=original):
                barrier.wait(timeout=20)
                return original(head, state)
            gate.store.compare_and_swap = contested
        def attempt(gate):
            try:
                return self.f.permit(gate, claim)
            except GateDenied:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, (first, second)))
        self.assertEqual(1, sum(value is not None for value in results))
        self.assertEqual(1, first.store.read().ledger["claims"][claim]["calls_issued"])

    def test_stop_is_permanent(self):
        gate = self.f.gate()
        claim = self.f.claim(gate)
        gate.stop("TEST_ONLY stop")
        with self.assertRaisesRegex(GateDenied, "STOP"):
            self.f.permit(gate, claim)
        with self.assertRaises(GateDenied):
            gate.finish(claim, outcome="IMPROVED")

    def test_signed_revise_and_stop_are_recorded_without_execution(self):
        for decision in ("REVISE", "STOP"):
            with self.subTest(decision=decision):
                f = Fixture()
                try:
                    f.review["decision"] = decision
                    f.sign()
                    gate = f.gate()
                    with self.assertRaisesRegex(GateDenied, decision):
                        f.claim(gate)
                    state = gate.store.read().ledger
                    self.assertEqual(decision, state["stop"]["decision"])
                    self.assertEqual(0, state["rounds_consumed"])
                finally:
                    f.close()

    def test_missing_approval_and_required_fields(self):
        gate = self.f.gate()
        missing = self.f.approval.with_name("missing.json")
        with self.assertRaises((GateDenied, FileNotFoundError)):
            gate.claim(missing, requested_action="TEST_ONLY-noop", requested_scope=["TEST_ONLY-output"])
        original = copy.deepcopy(self.f.review)
        for field in Gate.REVIEW_FIELDS:
            with self.subTest(field=field):
                value = copy.deepcopy(original)
                del value[field]
                self.f.approval.write_bytes(canonical_json(value))
                with self.assertRaises(GateDenied):
                    self.f.claim(gate)

    def test_wrong_subject_proposal_report_manifest_and_config(self):
        gate = self.f.gate()
        original = copy.deepcopy(self.f.review)
        for field in ("subject_commit_sha", "proposal_sha256", "report_md_sha256", "manifest_sha256", "config_sha256", "review_report_sha256"):
            with self.subTest(field=field):
                self.f.review = copy.deepcopy(original)
                self.f.review[field] = "0" * (40 if field == "subject_commit_sha" else 64)
                self.f.sign()
                with self.assertRaises(GateDenied):
                    self.f.claim(gate)

    def test_modified_source_evidence_proposal_and_review_report(self):
        gate = self.f.gate()
        for path in (*self.f.files, self.f.review_report):
            with self.subTest(path=path):
                target = self.f.repo / path
                old = target.read_bytes()
                target.write_bytes(b"TEST_ONLY changed after review\n")
                with self.assertRaises(GateDenied):
                    self.f.claim(gate)
                target.write_bytes(old)

    def test_subject_tree_is_not_commit(self):
        self.f.review["subject_commit_sha"] = self.f.git("rev-parse", "HEAD^{tree}")
        self.f.sign()
        with self.assertRaisesRegex(GateDenied, "commit"):
            self.f.claim(self.f.gate())

    def test_expiration_and_wall_clock_limit(self):
        gate = self.f.gate()
        self.f.now += timedelta(hours=2)
        with self.assertRaisesRegex(GateDenied, "expired"):
            self.f.claim(gate)
        self.f.now -= timedelta(hours=2)
        claim = self.f.claim(gate)
        self.f.now += timedelta(seconds=30)
        with self.assertRaisesRegex(GateDenied, "expired"):
            self.f.permit(gate, claim)

    def test_scope_action_budget_and_call_exhaustion(self):
        gate = self.f.gate()
        with self.assertRaises(GateDenied):
            gate.claim(self.f.approval, requested_action="different", requested_scope=["TEST_ONLY-output"])
        with self.assertRaises(GateDenied):
            gate.claim(self.f.approval, requested_action="TEST_ONLY-noop", requested_scope=["elsewhere"])
        claim = self.f.claim(gate)
        with self.assertRaises(GateDenied):
            self.f.permit(gate, claim, 6)
        self.f.permit(gate, claim)
        self.f.permit(gate, claim)
        with self.assertRaises(GateDenied):
            self.f.permit(gate, claim)

    def test_signed_review_cannot_increase_proposal_budget(self):
        self.f.review["max_calls"] = 3
        self.f.sign()
        with self.assertRaisesRegex(GateDenied, "differs from proposal"):
            self.f.claim(self.f.gate())

    def test_invalid_signature_and_unconfigured_source(self):
        self.f.review["signature"]["value_base64"] = base64.b64encode(b"0" * 64).decode()
        self.f.approval.write_bytes(canonical_json(self.f.review))
        with self.assertRaisesRegex(GateDenied, "signature"):
            self.f.claim(self.f.gate())
        self.f.review["review_identity"]["source_id"] = "other-source"
        self.f.sign()
        with self.assertRaisesRegex(GateDenied, "identity"):
            self.f.claim(self.f.gate())

    def test_test_only_never_enters_real_gate_even_with_enabled_switch(self):
        with self.assertRaisesRegex(GateDenied, "mode mismatch"):
            Gate(self.f.repo, self.f.config_path, mode="real", environ=self.f.env)
        # Even deliberate config relabeling cannot relabel a signed test review.
        config = copy.deepcopy(self.f.config)
        config.update(mode="REAL", test_only=None, ALLOW_REAL_EXPERIMENTS=True)
        config["activation"] = {"real_runner_installed": True, "external_review_identity_verified": True,
                                "external_review_writeback_verified": True}  # isolated configuration fixture only
        config["repository"]["ledger_ref"] = "refs/heads/codex/agent-loop-ledger"
        self.f.config_path.write_bytes(canonical_json(config))
        env = dict(self.f.env, AGENT_LOOP_TRUSTED_CONFIG_SHA256=sha256(self.f.config_path.read_bytes()))
        gate = Gate(self.f.repo, self.f.config_path, mode="real", environ=env)
        self.f.gates.append(gate)
        with self.assertRaisesRegex(GateDenied, "domain"):
            self.f.claim(gate)

    def test_disabled_null_limits_config_anchor_and_config_changed(self):
        for field in ("max_calls", "per_call_budget_seconds", "total_budget_seconds", "wall_clock_limit_seconds",
                      "max_rounds", "max_consecutive_failures", "max_consecutive_no_improvement"):
            with self.subTest(field=field):
                config = copy.deepcopy(self.f.config)
                config["limits"][field] = None
                self.f.config_path.write_bytes(canonical_json(config))
                env = dict(self.f.env, AGENT_LOOP_TRUSTED_CONFIG_SHA256=sha256(self.f.config_path.read_bytes()))
                gate = Gate(self.f.repo, self.f.config_path, mode="TEST_ONLY", environ=env)
                self.f.gates.append(gate)
                with self.assertRaises(GateDenied):
                    self.f.claim(gate)
        self.f.config_path.write_bytes(canonical_json(self.f.config))
        with self.assertRaises(GateDenied):
            Gate(self.f.repo, self.f.config_path, mode="TEST_ONLY", environ={})
        gate = self.f.gate()
        self.f.config_path.write_bytes(b"{}")
        with self.assertRaisesRegex(GateDenied, "configuration changed"):
            self.f.claim(gate)

    def test_expiration_during_cas_consumes_but_returns_no_permit(self):
        gate = self.f.gate()
        claim = self.f.claim(gate)
        original = gate.store.compare_and_swap
        def delayed(head, ledger):
            result = original(head, ledger)
            self.f.now += timedelta(seconds=30)
            return result
        gate.store.compare_and_swap = delayed
        with self.assertRaisesRegex(GateDenied, "deadline passed during CAS"):
            self.f.permit(gate, claim)
        self.assertEqual(1, gate.store.read().ledger["claims"][claim]["calls_issued"])

    def test_artifact_change_after_claim_denies_permit(self):
        gate = self.f.gate()
        claim = self.f.claim(gate)
        self.f.write("fixture_source.txt", b"TEST_ONLY post-claim tamper")
        with self.assertRaises(GateDenied):
            self.f.permit(gate, claim)

    def test_strict_json_rejects_duplicates_nan_and_boolean_budget(self):
        for raw in (b'{"a":1,"a":2}', b'{"n":NaN}'):
            with self.assertRaises(GateDenied):
                strict_json(raw)
        self.f.review["max_calls"] = True
        self.f.sign()
        with self.assertRaises(GateDenied):
            self.f.claim(self.f.gate())

    def test_history_rollback_and_empty_ledger_are_rejected(self):
        gate = self.f.gate()
        claim = self.f.claim(gate)
        snap = gate.store.read()
        malicious = copy.deepcopy(snap.ledger)
        malicious["sequence"] += 1
        malicious["previous_state_sha256"] = sha256(canonical_json(snap.ledger))
        malicious["calls_reserved"] = 0
        gate.store.compare_and_swap(snap.head, malicious)
        with self.assertRaises(GateDenied):
            self.f.permit(gate, claim)

    def test_existing_empty_ledger_is_not_initialized_as_fresh(self):
        gate = self.f.gate()
        gate.store.compare_and_swap(None, {})
        with self.assertRaises(GateDenied):
            self.f.claim(gate)

    def test_cumulative_quotas_no_refund_and_failure_threshold(self):
        gate = self.f.gate()
        for index in (1, 2):
            if index > 1:
                self.f.new_round(index)
            claim = self.f.claim(gate)
            gate.finish(claim, outcome="IMPROVED")
        self.f.new_round(3)
        with self.assertRaisesRegex(GateDenied, "cumulative"):
            self.f.claim(gate)
        self.assertEqual(4, gate.store.read().ledger["calls_reserved"])

    def test_failure_threshold_sets_permanent_stop(self):
        gate = self.f.gate()
        for index in (1, 2):
            if index > 1:
                self.f.new_round(index)
            claim = self.f.claim(gate)
            gate.finish(claim, outcome="FAILURE")
        state = gate.store.read().ledger
        self.assertEqual(2, state["consecutive_failures"])
        self.assertEqual("STOP", state["stop"]["decision"])
        with self.assertRaises(GateDenied):
            self.f.claim(gate)

    def test_analysis_has_zero_research_calls_and_no_permits(self):
        self.f.action.update(action_kind="ANALYSIS_ONLY", max_calls=0, per_call_budget_seconds=0, total_budget_seconds=0)
        self.f.manifest["proposed_action"] = self.f.action
        self.f.write(self.f.manifest_path, canonical_json(self.f.manifest))
        self.f.commit = self.f.commit_all()
        self.f.review.update(action_kind="ANALYSIS_ONLY", max_calls=0, per_call_budget_seconds=0, total_budget_seconds=0,
                             subject_commit_sha=self.f.commit, manifest_sha256=sha256(canonical_json(self.f.manifest)))
        self.f.sign()
        gate = self.f.gate()
        claim = self.f.claim(gate)
        with self.assertRaisesRegex(GateDenied, "no research-call"):
            self.f.permit(gate, claim)
        self.assertEqual(0, gate.store.read().ledger["calls_reserved"])

    def test_artifact_change_during_cas_returns_no_permit(self):
        gate = self.f.gate()
        claim = self.f.claim(gate)
        original = gate.store.compare_and_swap
        def drift(head, ledger):
            result = original(head, ledger)
            self.f.write("fixture_evidence.txt", b"TEST_ONLY drift during CAS")
            return result
        gate.store.compare_and_swap = drift
        with self.assertRaisesRegex(GateDenied, "artifact digest"):
            self.f.permit(gate, claim)
        self.assertEqual(1, gate.store.read().ledger["claims"][claim]["calls_issued"])

    def test_forged_ledger_claim_cannot_replace_independent_signature(self):
        gate = self.f.gate()
        fake_review = copy.deepcopy(self.f.review)
        fake_review["signature"]["value_base64"] = base64.b64encode(b"0" * 64).decode()
        state = gate._initial_state()
        state.update(sequence=1, rounds_consumed=1, calls_reserved=2, budget_reserved_seconds=10, active_claim_id="forged")
        state.update(run_started_utc="2026-10-20T00:00:00Z", run_deadline_utc="2026-10-20T00:01:00Z")
        state["consumed_rounds"][fake_review["round_id"]] = fake_review["approval_id"]
        state["consumed_approvals"][fake_review["approval_id"]] = fake_review["round_id"]
        state["claims"]["forged"] = {"status": "RUNNING", "review": fake_review,
                                     "review_sha256": sha256(canonical_json(fake_review)), "calls_issued": 0,
                                     "budget_charged_seconds": 0, "permits": [], "deadline_utc": "2026-10-20T00:00:30Z"}
        gate.store.compare_and_swap(None, state)
        with self.assertRaisesRegex(GateDenied, "signature"):
            self.f.permit(gate, "forged")

    def test_disabled_and_production_activation_are_enforced(self):
        config = copy.deepcopy(self.f.config)
        config["enabled"] = False
        self.f.config_path.write_bytes(canonical_json(config))
        env = dict(self.f.env, AGENT_LOOP_TRUSTED_CONFIG_SHA256=sha256(self.f.config_path.read_bytes()))
        gate = Gate(self.f.repo, self.f.config_path, mode="TEST_ONLY", environ=env)
        self.f.gates.append(gate)
        with self.assertRaisesRegex(GateDenied, "disabled"):
            self.f.claim(gate)
        config.update(enabled=True, mode="REAL", test_only=None)
        config["repository"]["ledger_ref"] = "refs/heads/codex/agent-loop-ledger"
        config["activation"] = {"real_runner_installed": False, "external_review_identity_verified": False,
                                "external_review_writeback_verified": False}
        self.f.config_path.write_bytes(canonical_json(config))
        env["AGENT_LOOP_TRUSTED_CONFIG_SHA256"] = sha256(self.f.config_path.read_bytes())
        gate = Gate(self.f.repo, self.f.config_path, mode="REAL", environ=env)
        self.f.gates.append(gate)
        with self.assertRaisesRegex(GateDenied, "activation"):
            self.f.claim(gate)

    def test_global_wall_clock_cannot_restart_in_new_round_or_process(self):
        gate = self.f.gate()
        claim = self.f.claim(gate)
        gate.finish(claim, outcome="IMPROVED")
        first_deadline = gate.store.read().ledger["run_deadline_utc"]
        self.f.now += timedelta(seconds=40)
        self.f.new_round(2)
        second_gate = self.f.gate()
        second_claim = self.f.claim(second_gate)
        state = second_gate.store.read().ledger
        self.assertEqual(first_deadline, state["run_deadline_utc"])
        self.assertEqual(first_deadline, state["claims"][second_claim]["deadline_utc"])
        self.f.now += timedelta(seconds=20)
        with self.assertRaisesRegex(GateDenied, "global wall-clock"):
            self.f.permit(second_gate, second_claim)


def e2e_trace():
    f = Fixture()
    try:
        gate = f.gate()
        events = [{"event": "TEST_ONLY_SUBJECT_COMMITTED", "subject_commit_sha": f.commit,
                   "object_type": "commit", "repository_type": "isolated_local_fixture", "research_calls_executed": 0},
                  {"event": "TEST_ONLY_SIGNED_REVIEW", "mode": "TEST_ONLY", "decision": f.review["decision"],
                   "subject_commit_sha": f.commit, "manifest_sha256": f.review["manifest_sha256"],
                   "proposal_sha256": f.review["proposal_sha256"], "real_experiments_executed": 0}]
        claim = f.claim(gate)
        events.append({"event": "REMOTE_CAS_CLAIM", "claim_id": claim, "status": "RUNNING"})
        permit = f.permit(gate, claim)
        events.append({"event": "TEST_ONLY_PERMIT_CHARGED", "permit_id": permit["permit_id"], "budget_seconds": permit["budget_seconds"],
                       "executed": False})
        gate.finish(claim, outcome="IMPROVED")
        events.append({"event": "EXPLICIT_FINISH", "status": "COMPLETED", "research_improvement_claimed": False})
        try:
            f.claim(gate)
            raise AssertionError("duplicate unexpectedly admitted")
        except GateDenied as exc:
            events.append({"event": "DUPLICATE_REJECTED", "reason": str(exc)})
        gate.stop("TEST_ONLY explicit safety-stop demonstration")
        events.append({"event": "REMOTE_STOP_COMMITTED", "decision": "STOP"})
        f.new_round(2)
        events.append({"event": "NEW_UNCONSUMED_TEST_ONLY_REVIEW", "approval_id": f.review["approval_id"],
                       "round_id": f.review["round_id"], "subject_commit_sha": f.commit,
                       "manifest_sha256": f.review["manifest_sha256"], "decision": f.review["decision"]})
        try:
            f.claim(gate)
            raise AssertionError("new approval bypassed STOP")
        except GateDenied as exc:
            if "STOP" not in str(exc):
                raise AssertionError("new approval rejected for a reason other than STOP") from exc
            events.append({"event": "NEW_APPROVAL_REJECTED_BY_STOP", "approval_id": f.review["approval_id"], "reason": str(exc)})
        ledger = gate.store.read().ledger
        events.append({"event": "FINAL_LEDGER", "rounds_consumed": ledger["rounds_consumed"], "calls_reserved": ledger["calls_reserved"],
                       "budget_reserved_seconds": ledger["budget_reserved_seconds"], "calls_issued": ledger["claims"][claim]["calls_issued"],
                       "active_claim_id": ledger["active_claim_id"], "stop": ledger["stop"]["decision"],
                       "run_started_utc": ledger["run_started_utc"], "run_deadline_utc": ledger["run_deadline_utc"],
                       "new_approval_consumed": f.review["approval_id"] in ledger["consumed_approvals"],
                       "remote_head": gate.store.remote_head(), "research_calls_executed": 0})
        failures = [{"phase": "initial_sandbox_attempt", "result": "ENVIRONMENT_BLOCKED",
                     "reason": "Windows sandbox denied strict path handle lookup and MSYS local Git transport named object creation.",
                     "resolution": "Use byte/stat validation with non-strict path normalization; isolated TEST_ONLY local Git tests run under auto-reviewed escalation."}]
        print(json.dumps({"schema_version": 1, "evidence_class": "TEST_ONLY", "failure_history": failures, "events": events}, ensure_ascii=False, indent=2))
    finally:
        f.close()


if __name__ == "__main__":
    if "--e2e" in sys.argv:
        e2e_trace()
    else:
        unittest.main()
