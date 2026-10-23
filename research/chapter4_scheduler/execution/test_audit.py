"""Invented archive-format fixtures only; no search or thermal propagation.

Positive records imitate the REAL format to test parsing; they are not physical
SAFE evidence. They exist only in disposable workspace directories and are
never eligible for a real protocol/declaration or a research claim.
"""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from research.chapter4_scheduler.execution import audit
from research.chapter4_scheduler.tests.test_method import artificial_input, complete_mock


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        scratch = (audit.REPO / ".runtime").resolve()
        scratch.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="ch4-archive-audit-fixture-", dir=scratch)
        Path(self.temporary.name).resolve().relative_to(scratch)
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.config, self.instance, self.candidate = artificial_input()
        source = Path(audit.__file__).resolve()
        manifest = {source.relative_to(audit.REPO).as_posix(): audit.legacy.sha(source)}
        self.identity = {"input_verified": True, "source_verified": True,
            "environment_verified": True, "scientific_call_started": True,
            "not_scientific": False, "fresh_input_calls": 1,
            "input_sha256": audit.legacy.canonical(self.instance),
            "config_sha256": audit.legacy.canonical(self.config),
            "source_sha256": manifest, "root_start_s": 1000.0,
            "root_deadline_s": 1300.0, "root_limit_s": 300,
            "declaration_sha256": "1" * 64}
        self.native = {"folder": str(self.folder)}

    def receipt(self, candidate=None):
        r = complete_mock(self.instance, candidate or self.candidate,
            self.config["accuracy_targets"], SimpleNamespace(elapsed=10.0), interval=("10", "10"))
        # Only ordinary-format fixtures can exercise the positive parser. The
        # outer test file explicitly retains their synthetic provenance.
        r.pop("evidence_kind")
        return r

    def heft(self, *, safe=True):
        r = {"method": "heft", "seed": None, "state": "SAFE" if safe else "UNRESOLVED",
            "problem_id": self.instance["id"], "reason": "DECLARED_SEARCH_COMPLETED",
            "budget_exhausted": False, "timing": {"limit_s": 300, "method_elapsed_s": 11.0},
            "safe_candidate": deepcopy(self.candidate) if safe else None,
            "safe_upper_bound_J": "10" if safe else None,
            "input_sha256": audit.legacy.canonical(self.instance)}
        if safe:
            r["evaluation"] = self.receipt()
        return r

    def graph(self, *, variant="pair", safe=True):
        r = self.heft(safe=safe)
        r.update(method="related_opp_order_graph", variant=variant,
            rule_version=audit.GRAPH_RULE, evidence_kind="REAL_CORE",
            run_terminal="SEARCH_COMPLETED", usable_as_research_evidence=safe,
            graph_strict_improvements=0, graph_proposals=[], evaluations=[], events=[],
            first_graph_strict_improvement_at_s=None)
        sources = {name.removeprefix("research/"): value for name, value in self.identity["source_sha256"].items()}
        context = {"input_sha256": audit.legacy.canonical(self.instance),
            "config_sha256": audit.legacy.canonical(self.config),
            "accuracy_sha256": audit.legacy.canonical(self.config["accuracy_targets"]),
            "root_start": "1000.0", "root_deadline": "1300.0", "root_seconds": 300,
            "root_token": "invented-fixture-token", "source_sha256": sources}
        r.update(root_context=deepcopy(context), sources_sha256=sources)
        if safe:
            r.update(safe_context=deepcopy(context), initial_safe_snapshot={
                "candidate": deepcopy(self.candidate), "receipt": self.receipt(),
                "context": deepcopy(context)})
        return r

    def c(self):
        """Point-valued partial aggregate exercising the unchanged old helpers."""
        direct = self.receipt()
        common = {"input_sha256": self.identity["input_sha256"],
            "config_sha256": self.identity["config_sha256"],
            "shared_deployment": {"x": "NPU0", "y": "NPU0"},
            "first_opened_by_scene": {"S0": ["x"]},
            "second_opened_by_scene": {"S0": ["y"]},
            "control_policy": "auto_low_immediate_v1"}
        bid = {"token": "invented-own-budget", "start": "1000.0", "seconds": "300.0",
            "panel_limit": 100000, "refinement_limit": 20000}
        self.identity.update(common=common, budget_identity=bid)
        ident = {"full_input_sha256": common["input_sha256"],
            "candidate_sha256": audit.legacy.canonical(self.candidate), "budget": bid,
            "source_sha256": {}, "accuracy_sha256": audit.legacy.canonical(self.config["accuracy_targets"]),
            "control_policy": common["control_policy"],
            "platform_sha256": audit.legacy.canonical(self.instance["platform"]),
            "execution_rules_sha256": audit.legacy.canonical(self.instance["execution_rules"]),
            "shared_deployment_sha256": audit.legacy.canonical(common["shared_deployment"])}
        scenes = {}
        for s in self.instance["scenarios"]:
            sid = s["id"]
            physical = deepcopy(direct["scenes"][sid])
            physical["trace"] = [{"time_s": physical["covered_until_s"]}]
            si = dict(ident, candidate_sha256=audit.legacy.canonical({"scenes": {sid: self.candidate["scenes"][sid]}}),
                scenario_sha256=audit.legacy.canonical(s), entry_sha256=audit.legacy.canonical(s["entry"]))
            scenes[sid] = {"state": "SAFE", "rankable_energy": True, "scenario_id": sid,
                "identity": si, "result": physical, "completed_at_elapsed_s": 9.0,
                "legality": direct["legality"], "energy_J": ["10", "10"], "safe_upper_bound_J": "10"}
            scenes[sid]["receipt_sha256"] = audit.legacy.receipt_hash(scenes[sid])
        aggregate = {"state": "SAFE", "rankable_energy": True,
            "safe_candidate": deepcopy(self.candidate), "safe_upper_bound_J": "10",
            "weighted_energy_J": ["10", "10"], "identity": ident,
            "problem_id": self.instance["id"], "legality": direct["legality"],
            "completed_at_elapsed_s": 10.0, "scenes": scenes}
        aggregate["receipt_sha256"] = audit.legacy.receipt_hash(aggregate)
        condition = {"source_input_sha256": common["input_sha256"],
            "shared_deployment": common["shared_deployment"],
            "opened_by_scene": common["first_opened_by_scene"],
            "seed_candidate": deepcopy(self.candidate), "seed_receipt": deepcopy(aggregate),
            "seed_candidate_sha256": audit.legacy.canonical(self.candidate),
            "seed_receipt_sha256": aggregate["receipt_sha256"],
            "seed_options_by_scene": {"S0": {}}, "budget_identity": deepcopy(bid)}
        condition["condition_sha256"] = audit.legacy.canonical(condition)
        r = {"protocol": audit.C_PROTOCOL, "state": "SAFE", "reason": "SCENE_SEARCH_SEQUENCE_COMPLETE",
            "rankable_energy": True,
            "problem_id": self.instance["id"], "scene_slice_s": 60,
            "safe_candidate": deepcopy(self.candidate), "safe_upper_bound_J": "10",
            "weighted_energy_J": ["10", "10"], "aggregation": aggregate,
            "condition": condition, "search_failure_latched": False, "budget_exhausted": False,
            "timing": {"limit_s": 300, "method_elapsed_s": 11.0}, "matlab_worker_ready": True,
            "phases": [{"phase_index": 1, "condition": deepcopy(condition), "scenes": {}}],
            "global_updates": [{"safe_upper_bound_J": "10", "weighted_energy_J": ["10", "10"]}]}
        r["committed_safe_snapshot"] = {k: deepcopy(r[k]) for k in
            ("safe_candidate", "safe_upper_bound_J", "weighted_energy_J", "aggregation")}
        closure = {"returncode": 0, "cleanup_status": "graceful_closed", "force_requested": False,
            "observed_tree_identity_count": 1, "observed_tree_verified_terminated": True,
            "observed_tree_capture_complete": True, "process_tree_verification": {
                "identities": [{"pid": 1, "create_time": 1.0, "state": "EXITED"}],
                "capture_complete": True, "verified_terminated": True}}
        native = self.folder / "method" / "matlab"
        native.mkdir(parents=True)
        self.write(native / "closed.json", closure)
        self.native.update(native_started=True, closure=deepcopy(closure))
        return r

    @staticmethod
    def write(path, value):
        Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    def materialize(self, result):
        for name, value in (("result.json", result), ("wrapper_raw_result.json", result),
                            ("input_instance.json", self.instance), ("input_config.json", self.config)):
            self.write(self.folder / name, value)
        self.identity["result_sha256"] = audit.legacy.sha(self.folder / "result.json")
        self.identity["raw_result_sha256"] = audit.legacy.sha(self.folder / "wrapper_raw_result.json")

    def check(self, arm, result, *, save=True):
        if save:
            self.materialize(result)
        before = deepcopy(result)
        out = audit.admit_result(arm, result, self.instance, self.config,
            identity=self.identity, native_evidence=self.native)
        self.assertEqual(result, before)
        return out

    def test_complete_heft_admitted_without_requiring_graph_usable_flag(self):
        out = self.check("HEFT", self.heft())
        self.assertTrue(out["eligible_for_post"], out)
        self.assertEqual(out["admitted_interval"], ["10", "10"])

    def test_complete_graph_and_single_use_direct_full_receipt(self):
        for arm, variant in (("PAIR", "pair"), ("SINGLE", "single")):
            with self.subTest(arm=arm):
                out = self.check(arm, self.graph(variant=variant))
                self.assertTrue(out["eligible_for_post"], out)

    def test_original_C_aggregate_source_root_and_current_native_closure(self):
        out = self.check("C", self.c())
        self.assertTrue(out["eligible_for_post"], out)

    def test_C_without_actual_closed_file_is_not_admitted(self):
        r = self.c()
        (self.folder / "method/matlab/closed.json").unlink()
        out = self.check("C", r)
        self.assertTrue(out["technical_failure"])
        self.assertIn("C_CURRENT_CLOSED_FILE_REQUIRED", out["errors"])

    def test_C_root_token_from_another_call_is_rejected(self):
        r = self.c()
        self.identity["budget_identity"] = dict(self.identity["budget_identity"], token="different-call")
        out = self.check("C", r)
        self.assertTrue(out["technical_failure"])
        self.assertIn("C_METHOD_ROOT_NOT_CALLER_ROOT", out["errors"])

    def test_C_missing_safe_seed_before_native_start_is_normal_no_witness(self):
        r = self.c()
        native = self.folder / "method" / "matlab"
        (native / "closed.json").unlink()
        native.rmdir(); native.parent.rmdir()
        self.native.update(native_started=False, closure=None)
        r.update(state="UNRESOLVED", reason="NO_COMPLETE_SAFE_LINKED_SEED",
            rankable_energy=False, matlab_worker_ready=False, safe_candidate=None,
            safe_upper_bound_J=None, weighted_energy_J=None, aggregation=None,
            condition=None, phases=[], global_updates=[], committed_safe_snapshot=None,
            seed_attempts=[{"state": "UNRESOLVED", "reason": "NO_COMPLETE_LEGAL_CONSTRUCTOR"}])
        out = self.check("C", r)
        self.assertTrue(out["normal_no_safe"], out)
        self.assertFalse(out["technical_failure"])

    def remove_native(self, result):
        native = self.folder / "method" / "matlab"
        (native / "closed.json").unlink()
        native.rmdir(); native.parent.rmdir()
        self.native.update(native_started=False, closure=None)
        result.update(matlab_worker_ready=False, session_total_request_count=0,
            solver_request_attempts=0, phases=[], scenes={})

    def constructor_only_no_safe(self):
        r = self.c()
        self.remove_native(r)
        r.update(state="UNRESOLVED", reason="NO_COMPLETE_SAFE_LINKED_SEED", rankable_energy=False,
            safe_candidate=None, safe_upper_bound_J=None, weighted_energy_J=None,
            aggregation=None, condition=None, global_updates=[], committed_safe_snapshot=None,
            seed_attempts=[{"construction": {"status": "CONSTRUCTION_UNRESOLVED"},
                "state": "UNRESOLVED", "reason": "CONSTRUCTION_UNRESOLVED",
                "scene_evaluations": {}, "aggregation": None} for _ in range(3)])
        self.identity["budget_identity"] = None
        return r

    def test_constructor_only_no_safe_allows_not_yet_created_scene_budget_token(self):
        r = self.constructor_only_no_safe()
        out = self.check("C", r)
        self.assertTrue(out["normal_no_safe"], out)
        self.assertFalse(out["technical_failure"])
        self.assertIs(out["initialization_complete"], False)

    def test_constructor_only_token_exception_does_not_allow_a_scene_evaluation(self):
        r = self.constructor_only_no_safe()
        r["seed_attempts"][0]["scene_evaluations"] = {"S0": {"state": "UNRESOLVED"}}
        out = self.check("C", r)
        self.assertTrue(out["technical_failure"])
        self.assertIn("C_CALLER_BUDGET_IDENTITY_REQUIRED", out["errors"])

    def test_constructor_only_token_exception_keeps_strict_worker_clock_check(self):
        r = self.constructor_only_no_safe()
        self.identity["root_start_s"] = 1001.0
        out = self.check("C", r)
        self.assertTrue(out["technical_failure"])
        self.assertIn("WORKER_ROOT_IDENTITY", out["errors"])

    def test_C_SAFE_with_missing_root_token_is_still_rejected(self):
        r = self.c()
        self.identity["budget_identity"] = None
        out = self.check("C", r)
        self.assertTrue(out["technical_failure"])
        self.assertIn("C_CALLER_BUDGET_IDENTITY_REQUIRED", out["errors"])

    def test_C_SAFE_committed_before_condition_at_normal_cutoff_can_post(self):
        r = self.c()
        self.remove_native(r)
        r.update(condition=None, reason="wall_time_limit", budget_exhausted=True)
        r["timing"]["method_elapsed_s"] = 300.1
        out = self.check("C", r)
        self.assertTrue(out["eligible_for_post"], out)
        self.assertEqual(out["classification"], "NORMAL_TIME_LIMIT")
        self.assertIs(out["initialization_complete"], False)

    def test_C_condition_exception_requires_real_cutoff_and_no_native(self):
        r = self.c()
        self.remove_native(r)
        r["condition"] = None
        out = self.check("C", r)
        self.assertTrue(out["technical_failure"])
        self.assertIn("C_SAFE_WITHOUT_CONDITION", out["errors"])

    def test_C_precondition_cutoff_does_not_admit_missing_complete_snapshot(self):
        r = self.c()
        self.remove_native(r)
        r.update(condition=None, reason="wall_time_limit", budget_exhausted=True,
            committed_safe_snapshot=None)
        r["timing"]["method_elapsed_s"] = 300.1
        out = self.check("C", r)
        self.assertTrue(out["technical_failure"])
        self.assertIn("C_SNAPSHOT_AGGREGATE_MISMATCH", out["errors"])

    def test_C_normal_cancelled_last_request_preserves_earlier_safe(self):
        r = self.c()
        r.update(reason="wall_time_limit", budget_exhausted=True)
        r["timing"]["method_elapsed_s"] = 300.1
        r["phases"][0]["scenes"] = {"S0": {"solver_result": {"rounds": [{
            "status": "BUDGET_EXHAUSTED", "budget_valid": False, "request_number": 1}]}}}
        native = self.folder / "method" / "matlab"
        self.write(native / "request_000001.python.json", {"request_number": 1,
            "status": "BUDGET_EXHAUSTED", "budget_valid": False,
            "accepted_for_evaluation": False, "x": [], "publication_read": {"transient_read_errors": {}}})
        self.write(native / "request_000001.input.json", {"request_number": 1,
            "method_deadline_bound": True, "absolute_deadline": "1300"})
        out = self.check("C", r)
        self.assertTrue(out["eligible_for_post"], out)
        self.assertEqual(out["classification"], "NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST")

    def test_graph_mock_or_explicit_ineligible_flags_cannot_post(self):
        for key, value in (("state", "MOCK_SAFE"), ("evidence_kind", "MOCK_ONLY"),
                           ("usable_as_research_evidence", False)):
            with self.subTest(key=key):
                r = self.graph(); r[key] = value
                out = self.check("PAIR", r)
                self.assertFalse(out["eligible_for_post"])
                self.assertTrue(out["technical_failure"])

    def initialization_cutoff_graph(self):
        r = self.graph()
        r.update(initial_safe_snapshot=None, initialization=None,
            run_terminal="BUDGET_EXHAUSTED", reason="METHOD_BUDGET_EXHAUSTED", budget_exhausted=True)
        r["timing"]["method_elapsed_s"] = 300.1
        r["evaluations"] = [{"source": "heft:eft", "phase": "initialization",
            "candidate": deepcopy(r["safe_candidate"]), "receipt": deepcopy(r["evaluation"]),
            "candidate_sha256": audit.legacy.canonical(r["safe_candidate"]),
            "accepted_safe": True, "context": deepcopy(r["root_context"])}]
        r["events"] = [{"phase": "initialization", "at_s": 10.0}]
        return r

    def test_graph_initialization_cutoff_preserves_complete_HEFT_SAFE(self):
        out = self.check("PAIR", self.initialization_cutoff_graph())
        self.assertTrue(out["eligible_for_post"], out)
        self.assertIs(out["initialization_complete"], False)
        self.assertEqual(out["classification"], "NORMAL_TIME_LIMIT")

    def test_graph_missing_initial_freeze_is_not_allowed_after_normal_completion(self):
        r = self.initialization_cutoff_graph()
        r.update(run_terminal="SEARCH_COMPLETED", reason="NO_FURTHER_DECLARED_IMPROVEMENT", budget_exhausted=False)
        r["timing"]["method_elapsed_s"] = 11.0
        out = self.check("PAIR", r)
        self.assertTrue(out["technical_failure"])

    def test_graph_missing_initial_freeze_cannot_hide_refinement_or_graph_proposals(self):
        for mutation in ("evaluation_phase", "evaluation_source", "event_phase", "proposal", "strict_count"):
            with self.subTest(mutation=mutation):
                r = self.initialization_cutoff_graph()
                if mutation == "evaluation_phase": r["evaluations"][0]["phase"] = "refinement"
                elif mutation == "evaluation_source": r["evaluations"][0]["source"] = "graph:pair"
                elif mutation == "event_phase": r["events"][0]["phase"] = "refinement"
                elif mutation == "proposal": r["graph_proposals"] = [{"strict_accepted": False}]
                else: r["graph_strict_improvements"] = 1
                out = self.check("PAIR", r)
                self.assertTrue(out["technical_failure"])

    def test_graph_initialization_cutoff_requires_bound_SAFE_observation(self):
        r = self.initialization_cutoff_graph()
        r["evaluations"][0]["candidate_sha256"] = "0" * 64
        out = self.check("PAIR", r)
        self.assertTrue(out["technical_failure"])
        self.assertIn("GRAPH_INITIALIZATION_SAFE_OBSERVATION_NOT_BOUND", out["errors"])

    def test_normal_no_witness_is_not_global_infeasibility_or_technical_failure(self):
        for arm in ("HEFT", "PAIR"):
            with self.subTest(arm=arm):
                r = self.heft(safe=False) if arm == "HEFT" else self.graph(safe=False)
                if arm == "PAIR":
                    r.update(run_terminal="UNRESOLVED_STOP", reason="NO_COMPLETE_SAFE_HEFT_INITIALIZATION")
                out = self.check(arm, r)
                self.assertTrue(out["normal_no_safe"], out)
                self.assertFalse(out["technical_failure"])
                self.assertFalse(out["independently_proven_infeasible"])

    def test_normal_cutoff_preserves_timely_SAFE_but_technical_error_does_not_post(self):
        r = self.heft(); r.update(reason="wall_time_limit", budget_exhausted=True)
        r["timing"]["method_elapsed_s"] = 300.1
        self.assertTrue(self.check("HEFT", r)["eligible_for_post"])
        r["evaluation"]["error_type"] = "ArithmeticError"
        out = self.check("HEFT", r)
        self.assertTrue(out["technical_failure"])
        self.assertFalse(out["eligible_for_post"])
        self.assertEqual(out["reported_U_J"], "10")

    def test_late_SAFE_receipt_is_rejected(self):
        r = self.heft(); r["evaluation"]["completed_at_elapsed_s"] = 300.0
        out = self.check("HEFT", r)
        self.assertTrue(out["technical_failure"])

    def test_missing_zero_weight_scene_and_wrong_top_U_are_rejected(self):
        self.config, self.instance, self.candidate = artificial_input(two_scenes=True)
        self.instance["scenarios"][0]["weight"] = "1"
        self.instance["scenarios"][1]["weight"] = "0"
        self.identity.update(input_sha256=audit.legacy.canonical(self.instance),
            config_sha256=audit.legacy.canonical(self.config))
        r = self.heft(); del r["evaluation"]["scenes"]["S1"]
        self.assertTrue(self.check("HEFT", r)["technical_failure"])
        r = self.heft(); r["safe_upper_bound_J"] = "9"
        self.assertTrue(self.check("HEFT", r)["technical_failure"])

    def test_current_byte_file_tampering_cannot_be_hidden_by_semantic_snapshot(self):
        r = self.heft(); self.materialize(r)
        path = self.folder / "result.json"
        path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
        out = self.check("HEFT", r, save=False)
        self.assertTrue(out["technical_failure"])
        self.assertIn("CURRENT_RESULT_FILE_BINDING:result.json", out["errors"])

    def test_graph_source_and_root_context_must_match_worker_origin(self):
        r = self.graph(); r["safe_context"]["root_start"] = "999.0"
        out = self.check("PAIR", r)
        self.assertTrue(out["technical_failure"])
        self.assertIn("GRAPH_SAFE_ROOT_OR_INPUT_CONTEXT", out["errors"])

    def test_wrong_arm_or_missing_worker_identity_fails_closed(self):
        r = self.heft()
        self.assertTrue(self.check("pair", r)["technical_failure"])
        self.materialize(r)
        out = audit.admit_result("HEFT", r, self.instance, self.config,
            native_evidence=self.native)
        self.assertTrue(out["technical_failure"])
        self.assertIn("WORKER_IDENTITY_REQUIRED", out["errors"])


if __name__ == "__main__":
    unittest.main()
