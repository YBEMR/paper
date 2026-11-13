"""Isolated metadata/claim checks; all authorization payloads are TEST_ONLY.

The disposable fake repository lives under .runtime and is removed at
test exit.  No production declaration, claim, input, planner, or evaluator is
used.  Dummy source files are hashed/copied as bytes and never imported.
"""
from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


RESEARCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RESEARCH.parent))
from research.chapter4_scheduler.execution import protocol


REAL_TEMP = RESEARCH.parent / ".runtime"


class PureProtocolTests(unittest.TestCase):
    def setUp(self):
        REAL_TEMP.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="TEST_ONLY_protocol_", dir=REAL_TEMP)
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "fake_repo"
        self.science = self.repo / "research/chapter3_experiments"
        self.package = self.repo / "research/chapter4_scheduler"
        self.here = self.package / "execution"
        self.proposal = self.science / "results/linked_ablation_preparation01/preparation02/proposal.json"
        self.here.mkdir(parents=True)
        self.output = self.package / "results/TEST_ONLY_batch"
        self.source = self.repo / "TEST_ONLY_source.py"
        self.source.write_text("# TEST_ONLY bytes; never execute\n", encoding="utf-8")
        self.archive = self.repo / "TEST_ONLY_archive.txt"
        self.archive.write_text("TEST_ONLY protected artifact\n", encoding="utf-8")
        for rel in (
                "research/chapter3_experiments/linked_ablation_execution/audit.py",
                "research/chapter3_experiments/linked_ablation_execution/registry.py",
                "research/chapter3_experiments/linked_ablation_execution/supervise.py",
                "research/chapter3_experiments/h02_pair_preflight/receipts.py",
                "research/chapter3_experiments/h02_pair_preflight/common.py"):
            path = self.repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# TEST_ONLY source fixture\n", encoding="utf-8")
        self.old = {
            "cases": [{
                "common": {"case_id": case, "input_sha256": "0" * 64,
                    "config_sha256": "1" * 64,
                    "historical_seed_reference": "TEST_ONLY_must_be_removed"},
                "recipes": {"C": {"kwargs": {"seconds": 300,
                    "TEST_ONLY_recipe": case}}},
            } for case in ("base__R1", "base__R3")],
            "source_sha256": {"TEST_ONLY_source.py": protocol.sha(self.source)},
            "archive_readonly_sha256": {"TEST_ONLY_archive.txt": protocol.sha(self.archive)},
            "solver_options": {"TEST_ONLY_options": "unchanged"},
        }
        protocol.write_new(self.proposal, self.old)
        self.constants = patch.multiple(protocol, REPO=self.repo, SCIENCE=self.science,
            PACKAGE=self.package, HERE=self.here, PROPOSAL=self.proposal)
        self.constants.start()
        self.addCleanup(self.constants.stop)
        self.environment = patch.object(protocol, "environment", return_value={
            "evidence_kind": "TEST_ONLY", "license_check": "NO_PROBE"})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def frozen(self):
        declaration = protocol.freeze(self.output)
        return declaration, self.output / "declaration.json"

    def activate_fake(self, *, expired=False, batch_hash=None, with_batch=True):
        """Exercise software predicates only; this is not human authorization."""
        declaration, path = self.frozen()
        gate = self.repo / "TEST_ONLY_gate.json"
        protocol.write_new(gate, {"passed": True, "evidence_kind": "TEST_ONLY",
            "protocol": "K181-guarded-execution-precheck-v1",
            "source_sha256": deepcopy(declaration["source_sha256"]),
            "new_research_calls": 0})
        auth = {
            "origin": "direct human budget confirmation",
            "confirmation": "TEST_ONLY invented payload; not an actual authorization",
            "declaration_sha256": protocol.sha(path),
            "budgets": deepcopy(protocol.BUDGETS),
            "authorized": True, "execution_enabled": True,
            "precheck_sha256": {gate.relative_to(self.repo).as_posix(): protocol.sha(gate)},
            "evidence_kind": "TEST_ONLY",
        }
        protocol.write_new(self.output / "authorization.json", auth)
        started = datetime.now(timezone.utc)
        if expired:
            started -= timedelta(seconds=protocol.BUDGETS["calendar_s"] + 1)
        deadline = started + timedelta(seconds=protocol.BUDGETS["calendar_s"])
        if with_batch:
            protocol.write_new(self.output / "batch.claim.json", {
                "declaration_sha256": protocol.sha(path) if batch_hash is None else batch_hash,
                "started_utc": started.isoformat(), "deadline_utc": deadline.isoformat(),
                "evidence_kind": "TEST_ONLY", "not_scientific": False, "no_retry": True,
            })
        return declaration, path

    def rewrite(self, path, value):
        Path(path).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def test_pending_has_exact_eight_slots_and_remains_disabled(self):
        d = protocol.make_declaration()
        self.assertFalse(d["authorized"])
        self.assertFalse(d["execution_enabled"])
        self.assertEqual(d["research_calls_consumed"], 0)
        self.assertEqual(len(d["slots"]), 8)
        self.assertEqual([(s["case_id"], s["arm"]) for s in d["slots"]], protocol.ORDER)
        self.assertEqual(sum(s["method_seconds"] for s in d["slots"]), 2400)
        self.assertEqual(sum(s["post_seconds_max"] for s in d["slots"]), 480)
        self.assertTrue(protocol.validate(d))
        self.assertTrue(protocol.verify_files(d))
        for case in d["cases"]:
            self.assertNotIn("historical_seed_reference", case["common"])
        with self.assertRaises(ValueError):
            protocol.validate(d, require_active=True)

    def test_freeze_only_writes_pending_binding_and_byte_snapshots(self):
        d, path = self.frozen()
        binding = protocol.read(self.output / "declaration_binding.json")
        self.assertEqual(binding["declaration_sha256"], protocol.sha(path))
        self.assertFalse(binding["authorized"])
        self.assertEqual(binding["research_calls_consumed"], 0)
        self.assertFalse((self.output / "authorization.json").exists())
        self.assertFalse((self.output / "batch.claim.json").exists())
        self.assertFalse((self.output / "calls").exists())
        for rel, expected in d["source_sha256"].items():
            self.assertEqual(protocol.sha(self.output / "source_snapshot" / rel), expected)
        with self.assertRaises(FileExistsError):
            protocol.freeze(self.output)

    def test_pending_cannot_claim_or_load_a_method(self):
        d, path = self.frozen()
        slot = d["slots"][0]["slot_id"]
        for operation in (protocol.claim_slot, protocol.load_active):
            with self.subTest(operation=operation.__name__):
                with self.assertRaises((OSError, ValueError)):
                    operation(path, slot)
        self.assertFalse((self.output / "calls").exists())

    def test_declaration_budget_order_recipe_and_self_approval_drift_rejected(self):
        d = protocol.make_declaration()
        variants = []
        x = deepcopy(d); x["budgets"]["method_total_s"] += 300; variants.append(x)
        x = deepcopy(d); x["slots"][0], x["slots"][1] = x["slots"][1], x["slots"][0]; variants.append(x)
        x = deepcopy(d); x["cases"][0]["recipes"]["C"]["kwargs"]["seconds"] = 301; variants.append(x)
        x = deepcopy(d); x["authorized"] = x["execution_enabled"] = True; variants.append(x)
        for i, value in enumerate(variants):
            with self.subTest(drift=i):
                with self.assertRaises(ValueError):
                    protocol.validate(value)

    def test_source_dependency_and_archive_drift_fail_verification(self):
        d = protocol.make_declaration()
        for path in (self.source, self.proposal, self.archive):
            with self.subTest(path=path.name):
                before = path.read_bytes()
                path.write_bytes(before + b"\nTEST_ONLY changed")
                self.assertFalse(protocol.verify_files(d))
                path.write_bytes(before)
                self.assertTrue(protocol.verify_files(d))

    def test_authorization_must_bind_exact_declaration(self):
        d, path = self.activate_fake()
        auth_path = self.output / "authorization.json"
        auth = protocol.read(auth_path)
        auth["declaration_sha256"] = "f" * 64
        self.rewrite(auth_path, auth)
        with self.assertRaises(ValueError):
            protocol.claim_slot(path, d["slots"][0]["slot_id"])
        self.assertFalse((self.output / "calls").exists())

    def test_failed_precheck_cannot_consume_a_slot(self):
        d, path = self.activate_fake()
        gate = self.repo / "TEST_ONLY_gate.json"
        self.rewrite(gate, {"passed": False, "evidence_kind": "TEST_ONLY"})
        auth_path = self.output / "authorization.json"
        auth = protocol.read(auth_path)
        auth["precheck_sha256"][gate.relative_to(self.repo).as_posix()] = protocol.sha(gate)
        self.rewrite(auth_path, auth)
        with self.assertRaises(ValueError):
            protocol.claim_slot(path, d["slots"][0]["slot_id"])
        self.assertFalse((self.output / "calls").exists())

    def test_only_next_slot_can_be_reserved_and_consumption_has_no_retry(self):
        d, path = self.activate_fake()
        first, second = d["slots"][:2]
        with self.assertRaises((OSError, ValueError)):
            protocol.claim_slot(path, second["slot_id"])
        self.assertFalse((self.output / "calls" / second["slot_id"]).exists())
        folder = protocol.claim_slot(path, first["slot_id"])
        claim = protocol.read(folder / "slot.claim.json")
        self.assertEqual(claim["reserved_method_s"], 300)
        self.assertEqual(claim["slot"], first)
        self.assertTrue(claim["no_retry"])
        with self.assertRaises(FileExistsError):
            protocol.claim_slot(path, first["slot_id"])
        self.assertEqual(protocol.read(folder / "slot.claim.json"), claim)

    def test_earlier_fault_and_batch_terminal_stop_advancement(self):
        d, path = self.activate_fake()
        first, second = d["slots"][:2]
        folder = protocol.claim_slot(path, first["slot_id"])
        protocol.write_new(folder / "terminal.json", {"continue_allowed": False,
            "reason": "TEST_ONLY_TECHNICAL_FAULT"})
        with self.assertRaises(ValueError):
            protocol.claim_slot(path, second["slot_id"])
        protocol.write_new(self.output / "batch_terminal.json", {"state": "TEST_ONLY_STOP"})
        with self.assertRaises(ValueError):
            protocol.load_active(path, first["slot_id"])

    def test_active_slot_returns_exact_declared_case_then_terminal_blocks_reentry(self):
        d, path = self.activate_fake()
        first = d["slots"][0]
        folder = protocol.claim_slot(path, first["slot_id"])
        current, slot, case = protocol.load_active(path, first["slot_id"])
        self.assertEqual(current, d)
        self.assertEqual(slot, first)
        self.assertEqual(case["common"]["case_id"], first["case_id"])
        protocol.write_new(folder / "terminal.json", {"continue_allowed": True,
            "evidence_kind": "TEST_ONLY"})
        with self.assertRaises(ValueError):
            protocol.load_active(path, first["slot_id"])

    def test_expired_batch_cannot_reserve_a_new_slot(self):
        d, path = self.activate_fake(expired=True)
        with self.assertRaises(ValueError):
            protocol.claim_slot(path, d["slots"][0]["slot_id"])
        self.assertFalse((self.output / "calls").exists())

    def test_batch_claim_must_bind_same_subject_before_consumption(self):
        d, path = self.activate_fake(batch_hash="e" * 64)
        with self.assertRaises(ValueError):
            protocol.claim_slot(path, d["slots"][0]["slot_id"])
        self.assertFalse((self.output / "calls").exists())

    def test_simulation_batch_cannot_activate_a_real_worker(self):
        d, path = self.activate_fake()
        slot = d["slots"][0]["slot_id"]
        protocol.claim_slot(path, slot)
        batch_path = self.output / "batch.claim.json"
        batch = protocol.read(batch_path)
        batch["not_scientific"] = True
        self.rewrite(batch_path, batch)
        with self.assertRaises(ValueError):
            protocol.load_active(path, slot)


@contextmanager
def active_fixture():
    """Yield (path, declaration, output) for an injected, MOCK_ONLY batch test.

    The controller must supply inert runner AND audit services. It creates its
    own simulated batch claim; load_active then rejects real-worker activation.
    Every source, gate, archive, and authorization here belongs to an isolated
    disposable fake repository, never to the production execution namespace.
    """
    owner = PureProtocolTests("test_pending_has_exact_eight_slots_and_remains_disabled")
    owner.setUp()
    try:
        declaration, path = owner.activate_fake(with_batch=False)
        yield path, declaration, owner.output
    finally:
        owner.doCleanups()


if __name__ == "__main__":
    unittest.main(verbosity=2)
