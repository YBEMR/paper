"""Synthetic lifecycle checks; no HEFT, optimizer, or thermal propagation.

The real wall-clock owner and exact legality checker are used.  Every initializer
and physical receipt below is explicitly MOCK_ONLY and cannot be research data.
"""
from copy import deepcopy
from fractions import Fraction as F
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


RESEARCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RESEARCH / "chapter3_experiments"))
sys.path.insert(0, str(RESEARCH.parent))

from research.chapter4_scheduler import method
from research.chapter4_scheduler.tests.test_graph_core import fixture
from h02_pair_preflight.tests.fixtures import mock_safe_receipt
from schedules import validate_schedule


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def artificial_input(*, two_scenes=False):
    instance, candidate = fixture([
        {"id": "x", "unit": "NPU0", "start": "0"},
        {"id": "y", "unit": "NPU0", "start": "20"},
    ], second_scene=two_scenes)
    instance["id"] = "pure_lifecycle_fixture"
    instance["platform"]["power_model_temperature_range_degC"] = ["0", "100"]
    for scene in instance["scenarios"]:
        scene["entry"]["temperature_degC"] = ["50"] * 4
        scene["maximum_temperature_degC"] = ["80"] * 4
    config = {"execution_rules": deepcopy(instance["execution_rules"]),
        "platform": deepcopy(instance["platform"]),
        "accuracy_targets": {"temperature_enclosure_width_K": "0.01",
            "energy_absolute_error_J": "2", "energy_relative_error": "1/1000000"}}
    return config, instance, candidate


def changed(candidate, start):
    out = deepcopy(candidate)
    for rows in out["scenes"].values():
        next(row for row in rows if row["stage_id"] == "x")["start_ms"] = str(start)
    return out


def complete_mock(instance, candidate, accuracy, budget, *, interval=("10", "10"), formed=None):
    lo, hi = map(F, interval)
    receipt = mock_safe_receipt(instance, candidate, accuracy,
        energy=str((lo + hi) / 2), formed=budget.elapsed if formed is None else formed)
    receipt["legality"] = validate_schedule(instance, candidate)
    for scene in receipt["scenes"].values():
        scene["energy_J"] = [str(lo), str(hi)]
    receipt["weighted_energy_J"] = [str(lo), str(hi)]
    receipt["safe_upper_bound_J"] = str(hi)
    return receipt


class MethodLifecycleTests(unittest.TestCase):
    def setUp(self):
        temporary_root = (RESEARCH.parent / ".runtime").resolve()
        temporary_root.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="chapter4-mock-method-", dir=temporary_root)
        self.assertTrue(Path(self.tmp.name).resolve().is_relative_to(temporary_root))
        self.addCleanup(self.tmp.cleanup)
        self.clock = FakeClock()
        self.config, self.instance, self.candidate = artificial_input()
        self.run_count = 0

    def evaluator(self, interval=("10", "10")):
        def evaluate(instance, candidate, accuracy, budget):
            self.clock.now += 1
            return complete_mock(instance, candidate, accuracy, budget, interval=interval)
        return Mock(side_effect=evaluate)

    def initialize(self, instance, config, budget, assess, *, allow_auto_low):
        self.assertTrue(allow_auto_low)
        assess(deepcopy(self.candidate), "mock:initial")
        return {"status": "MOCK_INITIALIZER_COMPLETED", "local_base_candidate": deepcopy(self.candidate)}

    def execute(self, *, initializer=None, evaluator=None, packets=(), variant="pair", kind="MOCK_ONLY", loader=None):
        self.run_count += 1
        workdir = Path(self.tmp.name) / ("call_%02d" % self.run_count)
        evaluator = self.evaluator() if evaluator is None else evaluator
        initializer = self.initialize if initializer is None else initializer
        if loader is None:
            loader = lambda budget: (deepcopy(self.config), deepcopy(self.instance))
        packet_fn = packets if callable(packets) else Mock(return_value=iter(packets))
        # These sentinels forbid accidental physical/search calls, even if a
        # lifecycle implementation later imports one of the original aliases.
        with patch.object(method, "candidate_packets", packet_fn), \
                patch("heft_method.run_heft", side_effect=AssertionError("NO_REAL_HEFT")), \
                patch("thermal.evaluate_candidate", side_effect=AssertionError("NO_REAL_THERMAL")):
            result = method.execute_reconstruction(loader, workdir,
                bindings=method.Bindings(initializer, evaluator, kind=kind),
                seconds=300, clock=self.clock, variant=variant)
        self.assertEqual(result["evidence_kind"], kind)
        self.assertFalse(result["usable_as_research_evidence"])
        self.assertFalse(result["independently_proven_optimal"])
        self.assertFalse(result["independently_proven_infeasible"])
        self.assertEqual(json.loads((workdir / "result.json").read_text(encoding="utf-8")), result)
        return result, evaluator, packet_fn

    def packet(self, candidate):
        return {"candidate": deepcopy(candidate), "state": "COMPLETE_LEGAL_CANDIDATE",
            "nonthermal_energy_J": "1", "evidence_kind": "MOCK_ONLY"}

    def test_one_root_includes_loader_heft_graph_and_evaluation(self):
        budgets = []
        def loader(budget):
            budgets.append(budget); self.clock.now += 10
            return deepcopy(self.config), deepcopy(self.instance)
        def init(instance, config, budget, assess, *, allow_auto_low):
            budgets.append(budget)
            self.assertEqual(budget.elapsed, 10)
            return self.initialize(instance, config, budget, assess, allow_auto_low=allow_auto_low)
        def packets(instance, incumbent, budget, *, variant):
            budgets.append(budget); self.clock.now += 2
            return iter(())
        result, _, _ = self.execute(initializer=init, loader=loader, packets=packets)
        self.assertTrue(all(b is budgets[0] for b in budgets))
        self.assertEqual(result["root_context"]["root_start"], "1000.0")
        self.assertEqual(result["root_context"]["root_deadline"], "1300.0")
        self.assertEqual(result["timing"]["limit_s"], 300)
        self.assertEqual(result["timing"]["method_elapsed_s"], 13)
        self.assertEqual(result["state"], "MOCK_SAFE")
        self.assertEqual(result["run_terminal"], "SEARCH_COMPLETED")

    def test_initializer_budget_exhaustion_does_not_enter_graph(self):
        def init(instance, config, budget, assess, *, allow_auto_low):
            self.initialize(instance, config, budget, assess, allow_auto_low=allow_auto_low)
            self.clock.now = 1300.0
            return {"status": "MOCK_BUDGET_EXHAUSTED"}
        result, _, packet_fn = self.execute(initializer=init)
        self.assertEqual(result["run_terminal"], "BUDGET_EXHAUSTED")
        self.assertEqual(result["state"], "MOCK_SAFE")
        packet_fn.assert_not_called()

    def test_initializer_best_is_selected_instead_of_last_local_base(self):
        later = changed(self.candidate, 5)
        def evaluate(instance, candidate, accuracy, budget):
            self.clock.now += 1
            energy = "11" if candidate == later else "10"
            return complete_mock(instance, candidate, accuracy, budget, interval=(energy, energy))
        def init(instance, config, budget, assess, *, allow_auto_low):
            assess(self.candidate, "mock:better-first")
            assess(later, "mock:worse-last")
            return {"local_base_candidate": deepcopy(later)}
        result, _, _ = self.execute(initializer=init, evaluator=Mock(side_effect=evaluate))
        self.assertEqual(result["safe_candidate"], self.candidate)
        self.assertEqual(result["initial_safe_snapshot"]["candidate"], self.candidate)
        self.assertEqual(result["initialization"]["local_base_candidate"], later)

    def test_refinement_overlapping_interval_cannot_replace_incumbent(self):
        trial = changed(self.candidate, 5)
        def evaluate(instance, candidate, accuracy, budget):
            self.clock.now += 1
            interval = ("9", "10") if candidate == self.candidate else ("8", "19/2")
            return complete_mock(instance, candidate, accuracy, budget, interval=interval)
        result, _, _ = self.execute(evaluator=Mock(side_effect=evaluate), packets=[self.packet(trial)])
        self.assertEqual(result["safe_candidate"], self.candidate)
        self.assertEqual(result["safe_upper_bound_J"], "10")
        self.assertEqual(result["graph_strict_improvements"], 0)
        self.assertTrue(result["evaluations"][-1]["accepted_safe"])
        self.assertFalse(result["evaluations"][-1]["incumbent_replaced"])

    def test_refinement_strict_interval_separation_replaces_incumbent(self):
        trial = changed(self.candidate, 5)
        def evaluate(instance, candidate, accuracy, budget):
            self.clock.now += 1
            return complete_mock(instance, candidate, accuracy, budget,
                interval=("9", "10") if candidate == self.candidate else ("8", "89/10"))
        def packets(instance, incumbent, budget, *, variant):
            return iter([self.packet(trial)])
        result, _, _ = self.execute(evaluator=Mock(side_effect=evaluate), packets=packets, variant="single")
        self.assertEqual(result["safe_candidate"], trial)
        self.assertEqual(result["graph_strict_improvements"], 1)
        self.assertEqual(result["safe_upper_bound_J"], "89/10")

    def test_missing_zero_weight_scene_rejects_fake_safe(self):
        self.config, self.instance, self.candidate = artificial_input(two_scenes=True)
        self.instance["scenarios"][0]["weight"] = "1"
        self.instance["scenarios"][1]["weight"] = "0"
        def evaluate(instance, candidate, accuracy, budget):
            self.clock.now += 1
            r = complete_mock(instance, candidate, accuracy, budget)
            del r["scenes"]["S1"]
            return r
        result, _, packet_fn = self.execute(evaluator=Mock(side_effect=evaluate))
        self.assertEqual(result["run_terminal"], "TECHNICAL_STOP")
        self.assertIsNone(result["safe_candidate"])
        packet_fn.assert_not_called()

    def test_incomplete_scene_and_bare_fake_safe_are_rejected(self):
        for kind in ("incomplete", "bare", "short_window"):
            with self.subTest(kind=kind):
                def evaluate(instance, candidate, accuracy, budget):
                    self.clock.now += 1
                    r = complete_mock(instance, candidate, accuracy, budget)
                    if kind == "incomplete": r["scenes"]["S0"]["complete"] = False
                    elif kind == "short_window": r["scenes"]["S0"]["covered_until_s"] = "1/20"
                    else: r = {"state": "SAFE", "rankable_energy": True,
                        "weighted_energy_J": ["1", "1"], "safe_upper_bound_J": "1",
                        "completed_at_elapsed_s": budget.elapsed}
                    return r
                result, _, _ = self.execute(evaluator=Mock(side_effect=evaluate))
                self.assertIsNone(result["safe_candidate"])
                self.assertEqual(result["run_terminal"], "TECHNICAL_STOP")

    def test_initializer_exception_keeps_previously_complete_safe(self):
        def init(instance, config, budget, assess, *, allow_auto_low):
            assess(self.candidate, "mock:committed-before-error")
            raise RuntimeError("synthetic initialization failure")
        result, _, _ = self.execute(initializer=init)
        self.assertEqual(result["state"], "MOCK_SAFE")
        self.assertEqual(result["safe_candidate"], self.candidate)
        self.assertEqual(result["run_terminal"], "TECHNICAL_STOP")

    def test_initializer_exception_before_safe_has_no_output(self):
        initializer = Mock(side_effect=RuntimeError("synthetic early failure"))
        result, evaluator, packets = self.execute(initializer=initializer)
        self.assertEqual(result["state"], "UNRESOLVED")
        self.assertEqual(result["run_terminal"], "TECHNICAL_STOP")
        self.assertIsNone(result["safe_candidate"])
        evaluator.assert_not_called(); packets.assert_not_called()

    def test_refinement_exception_keeps_previous_complete_safe(self):
        def packets(*args, **kwargs):
            raise RuntimeError("synthetic graph failure")
        result, _, _ = self.execute(packets=packets)
        self.assertEqual(result["state"], "MOCK_SAFE")
        self.assertEqual(result["safe_candidate"], self.candidate)
        self.assertEqual(result["run_terminal"], "TECHNICAL_STOP")

    def test_timely_safe_with_late_return_is_committed_without_new_budget(self):
        def evaluate(instance, candidate, accuracy, budget):
            self.clock.now = 1300.1
            return complete_mock(instance, candidate, accuracy, budget, formed=299.9)
        result, _, packet_fn = self.execute(evaluator=Mock(side_effect=evaluate))
        self.assertEqual(result["state"], "MOCK_SAFE")
        self.assertEqual(result["first_safe_at_s"], 299.9)
        self.assertEqual(result["run_terminal"], "BUDGET_EXHAUSTED")
        packet_fn.assert_not_called()

    def test_timely_joint_improvement_survives_outer_expiry_and_is_counted(self):
        trial = changed(self.candidate, 5)
        def evaluate(instance, candidate, accuracy, budget):
            if candidate == self.candidate:
                self.clock.now += 1
                return complete_mock(instance, candidate, accuracy, budget)
            self.clock.now = 1300.1
            return complete_mock(instance, candidate, accuracy, budget,
                interval=("8", "8"), formed=299.9)
        result, _, _ = self.execute(evaluator=Mock(side_effect=evaluate), packets=[self.packet(trial)])
        self.assertEqual(result["safe_candidate"], trial)
        self.assertEqual(result["run_terminal"], "BUDGET_EXHAUSTED")
        self.assertEqual(result["graph_strict_improvements"], 1)
        self.assertTrue(result["graph_proposals"][-1]["strict_accepted"])

    def test_deadline_or_invalid_safe_timestamp_cannot_form_new_U(self):
        for formed in (300.0, True, -1.0):
            with self.subTest(formed=formed):
                def evaluate(instance, candidate, accuracy, budget):
                    self.clock.now = 1300.0
                    return complete_mock(instance, candidate, accuracy, budget, formed=formed)
                result, _, _ = self.execute(evaluator=Mock(side_effect=evaluate))
                self.assertIsNone(result["safe_candidate"])
                self.assertIsNone(result["safe_upper_bound_J"])

    def test_nonfinite_safe_timestamp_is_rejected_and_failure_is_archived(self):
        def evaluate(instance, candidate, accuracy, budget):
            self.clock.now += 1
            return complete_mock(instance, candidate, accuracy, budget, formed=float("nan"))
        result, _, _ = self.execute(evaluator=Mock(side_effect=evaluate))
        self.assertEqual(result["run_terminal"], "TECHNICAL_STOP")
        self.assertIsNone(result["safe_candidate"])
        self.assertIsNone(result["safe_upper_bound_J"])

    def test_future_but_interior_timestamp_is_not_accepted(self):
        def evaluate(instance, candidate, accuracy, budget):
            self.clock.now += 1
            return complete_mock(instance, candidate, accuracy, budget, formed=200.0)
        result, _, _ = self.execute(evaluator=Mock(side_effect=evaluate))
        self.assertEqual(result["reason"], "INVALID_SAFE_TIMESTAMP")
        self.assertEqual(result["run_terminal"], "TECHNICAL_STOP")
        self.assertIsNone(result["safe_candidate"])

    def test_source_context_drift_after_initial_safe_is_detected(self):
        original = method.source_identity
        changed_flag = [False]
        def source():
            out = original()
            if changed_flag[0]: out["synthetic_source_drift.py"] = "0" * 64
            return out
        def init(instance, config, budget, assess, *, allow_auto_low):
            assess(self.candidate, "mock:before-source-drift")
            changed_flag[0] = True
            return {"status": "MOCK_SOURCE_DRIFT"}
        with patch.object(method, "source_identity", source):
            result, _, packet_fn = self.execute(initializer=init)
        self.assertEqual(result["reason"], "CALL_CONTEXT_DRIFT")
        self.assertEqual(result["safe_candidate"], self.candidate)
        packet_fn.assert_not_called()

    def test_budget_interior_violation_survives_late_outer_return(self):
        trial = changed(self.candidate, 5)
        witness = {"scene_id": "S0", "node": "c1", "time_s": "1/100",
            "temperature_degC": ["81", "82"], "limit_degC": "80",
            "formed_at_elapsed_s": 299.9}
        def evaluate(instance, candidate, accuracy, budget):
            if candidate == self.candidate:
                self.clock.now += 1
                return complete_mock(instance, candidate, accuracy, budget)
            self.clock.now = 1300.1
            receipt = complete_mock(instance, candidate, accuracy, budget)
            receipt.update(state="THERMAL_VIOLATION", violations=[deepcopy(witness)],
                rankable_energy=False, weighted_energy_J=None, safe_upper_bound_J=None)
            return receipt
        result, _, _ = self.execute(evaluator=Mock(side_effect=evaluate), packets=[self.packet(trial)])
        self.assertEqual(result["safe_candidate"], self.candidate)
        self.assertEqual(result["violations"], [witness])
        self.assertEqual(result["run_terminal"], "BUDGET_EXHAUSTED")

    def test_evaluator_cannot_mutate_input_candidate_or_accuracy(self):
        for target in ("input", "candidate", "accuracy"):
            with self.subTest(target=target):
                def evaluate(instance, candidate, accuracy, budget):
                    self.clock.now += 1
                    r = complete_mock(instance, candidate, accuracy, budget)
                    if target == "input": instance["id"] = "mutated"
                    elif target == "candidate": candidate["scenes"]["S0"][0]["start_ms"] = "5"
                    else: accuracy["energy_absolute_error_J"] = "999"
                    return r
                result, _, _ = self.execute(evaluator=Mock(side_effect=evaluate))
                self.assertEqual(result["reason"], "EVALUATOR_ARGUMENT_MUTATION")
                self.assertIsNone(result["safe_candidate"])

    def test_initializer_input_config_or_budget_drift_stops_after_safe(self):
        for target in ("input", "accuracy", "budget_start", "budget_deadline", "budget_seconds"):
            with self.subTest(target=target):
                def init(instance, config, budget, assess, *, allow_auto_low):
                    assess(self.candidate, "mock:before-drift")
                    if target == "input": instance["id"] = "changed_after_safe"
                    elif target == "accuracy": config["accuracy_targets"]["energy_absolute_error_J"] = "9"
                    elif target == "budget_start": budget.start += 1
                    elif target == "budget_deadline": budget.deadline += 1
                    else: budget.seconds += 1
                    return {"status": "MOCK_DRIFT"}
                result, _, packet_fn = self.execute(initializer=init)
                self.assertEqual(result["reason"], "CALL_CONTEXT_DRIFT")
                self.assertEqual(result["state"], "MOCK_SAFE")
                self.assertEqual(result["safe_candidate"], self.candidate)
                packet_fn.assert_not_called()

    def test_receipt_input_or_candidate_identity_mismatch_is_rejected(self):
        for field in ("input_sha256", "candidate_sha256"):
            with self.subTest(field=field):
                def evaluate(instance, candidate, accuracy, budget):
                    self.clock.now += 1
                    r = complete_mock(instance, candidate, accuracy, budget)
                    r["evidence_identity"][field] = "0" * 64
                    return r
                result, _, _ = self.execute(evaluator=Mock(side_effect=evaluate))
                self.assertEqual(result["run_terminal"], "TECHNICAL_STOP")
                self.assertIsNone(result["safe_candidate"])

    def test_refinement_cannot_change_frozen_specific_deployment(self):
        trial = deepcopy(self.candidate)
        trial["scenes"]["S0"][0]["unit"] = "GPU0"
        result, evaluator, _ = self.execute(packets=[self.packet(trial)])
        self.assertEqual(result["reason"], "FIXED_DEPLOYMENT_DRIFT")
        self.assertEqual(result["safe_candidate"], self.candidate)
        self.assertEqual(evaluator.call_count, 1)

    def test_call_local_cache_and_cross_call_isolation(self):
        def init(instance, config, budget, assess, *, allow_auto_low):
            assess(self.candidate, "mock:first")
            assess(deepcopy(self.candidate), "mock:duplicate")
            return {"status": "MOCK_CACHE_CHECK"}
        a, ea, _ = self.execute(initializer=init)
        b, eb, _ = self.execute(initializer=init)
        self.assertEqual(ea.call_count, 1)
        self.assertEqual(eb.call_count, 1)
        self.assertEqual(a["cache_hits"], 1)
        self.assertEqual(b["cache_hits"], 1)
        self.assertNotEqual(a["root_context"]["root_token"], b["root_context"]["root_token"])
        self.assertFalse(a["candidate_or_cache_shared_between_calls"])

    def test_same_call_safe_snapshot_is_not_aliased_to_initializer_objects(self):
        original = deepcopy(self.candidate)
        def init(instance, config, budget, assess, *, allow_auto_low):
            trial = deepcopy(original)
            assess(trial, "mock:snapshot")
            trial["scenes"]["S0"][0]["start_ms"] = "5"
            return {"local_base_candidate": trial}
        result, _, _ = self.execute(initializer=init)
        self.assertEqual(result["safe_candidate"], original)
        self.assertNotEqual(result["initialization"]["local_base_candidate"], original)

    def test_forged_real_backend_kind_is_rejected_without_calls(self):
        initializer, evaluator = Mock(), Mock()
        result, _, packets = self.execute(initializer=initializer, evaluator=evaluator, kind="REAL_CORE")
        self.assertEqual(result["run_terminal"], "TECHNICAL_STOP")
        initializer.assert_not_called(); evaluator.assert_not_called(); packets.assert_not_called()

    def test_existing_workdir_is_rejected_before_initialization(self):
        initializer, evaluator = Mock(), Mock()
        folder = Path(self.tmp.name) / "already_exists"
        folder.mkdir()
        with self.assertRaises(FileExistsError):
            method.execute_reconstruction(lambda budget: (self.config, self.instance), folder,
                bindings=method.Bindings(initializer, evaluator), clock=self.clock)
        initializer.assert_not_called(); evaluator.assert_not_called()

    def test_malformed_timestamp_is_technical_even_when_root_has_expired(self):
        trial = changed(self.candidate, 5)
        def evaluate(instance, candidate, accuracy, budget):
            if candidate == self.candidate:
                self.clock.now += 1
                return complete_mock(instance, candidate, accuracy, budget)
            self.clock.now = 1300.1
            return complete_mock(instance, candidate, accuracy, budget, formed=float("nan"))
        result, _, _ = self.execute(evaluator=Mock(side_effect=evaluate), packets=[self.packet(trial)])
        self.assertEqual(result["run_terminal"], "TECHNICAL_STOP")
        self.assertEqual(result["reason"], "INVALID_SAFE_TIMESTAMP")
        self.assertEqual(result["safe_candidate"], self.candidate)
        self.assertIn("invalid_nonfinite_float", result["evaluations"][-1]["receipt"]["completed_at_elapsed_s"])

    def test_evaluator_first_checkpoint_expiry_preserves_previous_safe(self):
        trial = changed(self.candidate, 5)
        def evaluate(instance, candidate, accuracy, budget):
            if candidate == self.candidate:
                self.clock.now += 1
                return complete_mock(instance, candidate, accuracy, budget)
            self.clock.now = 1300.1
            return {"state": "UNRESOLVED", "reason": "wall_time_limit",
                "budget_exhausted": True, "violations": []}
        result, _, _ = self.execute(evaluator=Mock(side_effect=evaluate), packets=[self.packet(trial)])
        self.assertEqual(result["run_terminal"], "BUDGET_EXHAUSTED")
        self.assertEqual(result["safe_candidate"], self.candidate)
        self.assertEqual(result["graph_strict_improvements"], 0)

    def test_wrong_candidate_or_future_violation_is_not_a_usable_witness(self):
        trial = changed(self.candidate, 5)
        for fault in ("candidate", "future"):
            with self.subTest(fault=fault):
                self.clock.now = 1000.0
                def evaluate(instance, candidate, accuracy, budget):
                    self.clock.now += 1
                    receipt = complete_mock(instance, candidate, accuracy, budget)
                    if candidate == self.candidate:
                        return receipt
                    witness = {"scene_id": "S0", "node": "c1", "time_s": "1/100",
                        "temperature_degC": ["81", "82"], "limit_degC": "80",
                        "formed_at_elapsed_s": budget.elapsed if fault == "candidate" else 200.0}
                    receipt.update(state="THERMAL_VIOLATION", violations=[witness],
                        rankable_energy=False, weighted_energy_J=None, safe_upper_bound_J=None)
                    if fault == "candidate":
                        receipt["evidence_identity"]["candidate_sha256"] = "bad"
                    return receipt
                result, _, _ = self.execute(evaluator=Mock(side_effect=evaluate), packets=[self.packet(trial)])
                self.assertEqual(result["run_terminal"], "TECHNICAL_STOP")
                self.assertFalse(result["violations"])
                self.assertEqual(result["safe_candidate"], self.candidate)

    def test_archived_original_input_survives_initializer_mutation(self):
        def init(instance, config, budget, assess, *, allow_auto_low):
            assess(self.candidate, "mock:before-drift")
            instance["id"] = "mutated"
            return {"status": "MOCK_DRIFT"}
        result, _, _ = self.execute(initializer=init)
        folder = Path(self.tmp.name) / ("call_%02d" % self.run_count)
        stored = json.loads((folder / "input_instance.json").read_text(encoding="utf-8"))
        self.assertEqual(stored, self.instance)
        self.assertEqual(method.digest(stored), result["root_context"]["input_sha256"])

    def test_artificial_joint_move_crosses_single_move_energy_barrier(self):
        # Invented contract energies: LL=10, one H=11, HH=9. This is a pure
        # mechanism fixture, not a prediction from any physical/thermal model.
        def evaluate(instance, candidate, accuracy, budget):
            self.clock.now += 1
            highs = sum(r["opp"] == "H" for r in candidate["scenes"]["S0"])
            e = "9" if highs == 2 else "11" if highs == 1 else "10"
            return complete_mock(instance, candidate, accuracy, budget, interval=(e, e))
        actual_packets = method.candidate_packets
        single, _, _ = self.execute(evaluator=Mock(side_effect=evaluate),
            packets=actual_packets, variant="single")
        self.clock.now = 1000.0
        pair, _, _ = self.execute(evaluator=Mock(side_effect=evaluate),
            packets=actual_packets, variant="pair")
        self.assertEqual(single["safe_upper_bound_J"], "10")
        self.assertEqual(single["graph_strict_improvements"], 0)
        self.assertEqual(pair["safe_upper_bound_J"], "9")
        self.assertEqual(pair["graph_strict_improvements"], 1)
        self.assertEqual(pair["state"], "MOCK_SAFE")


if __name__ == "__main__":
    unittest.main()
