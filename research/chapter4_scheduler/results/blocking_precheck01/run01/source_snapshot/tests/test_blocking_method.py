"""Artificial blocking-method lifecycle checks; never research evidence.

All SAFE-shaped receipts below are invented MOCK_ONLY contracts.  The exact
schedule checker and structural graph code may run; HEFT, optimizers, MATLAB,
thermal integration, and historical workloads must not run.
"""
from copy import deepcopy
from fractions import Fraction as F
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from research.chapter4_scheduler.tests.test_method import (
    RESEARCH, FakeClock, artificial_input, changed, complete_mock)
from research.chapter4_scheduler.tests.test_graph_core import (
    fixture, independent_legality, rows)
from research.chapter4_scheduler.blocking import method
from timing import MethodBudget


def crossing_input():
    """Four invented tasks on a 5 ms grid; no physical energy claim."""
    instance, candidate = fixture([
        {"id": "lead", "unit": "NPU0", "opp": "H", "start": "0",
         "duration_H": "8", "activity_H": "5",
         "duration_L": "18", "activity_L": "1"},
        {"id": "tail", "unit": "NPU0", "opp": "L", "start": "10",
         "duration": "11", "activity_L": "1", "activity_H": "1"},
        {"id": "pa", "unit": "CPU1", "opp": "L", "start": "30",
         "duration": "3", "deadline": "34"},
        {"id": "pb", "unit": "CPU1", "opp": "L", "start": "25",
         "duration": "3", "deadline": "40"},
    ], dependencies=[("lead", "pa"), ("tail", "pb")], window="50")
    instance["id"] = "mock_only_saving_mode_cross_resource"
    instance["platform"]["power_model_temperature_range_degC"] = ["0", "100"]
    for scene in instance["scenarios"]:
        scene["entry"]["temperature_degC"] = ["50"] * 4
        scene["maximum_temperature_degC"] = ["80"] * 4
    config = {"execution_rules": deepcopy(instance["execution_rules"]),
        "platform": deepcopy(instance["platform"]),
        "accuracy_targets": {"temperature_enclosure_width_K": "0.01",
            "energy_absolute_error_J": "2", "energy_relative_error": "1/1000000"}}
    return config, instance, candidate


class BlockingMethodLifecycleTests(unittest.TestCase):
    def setUp(self):
        temporary_root = (RESEARCH.parent / ".runtime").resolve()
        temporary_root.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="blocking-mock-method-", dir=temporary_root)
        self.addCleanup(self.tmp.cleanup)
        self.clock = FakeClock()
        self.config, self.instance, self.candidate = artificial_input()
        self.call_number = 0

    def initialize(self, instance, config, budget, assess, *, allow_auto_low):
        self.assertTrue(allow_auto_low)
        assess(deepcopy(self.candidate), "mock:initial")
        return {"status": "MOCK_INITIALIZER_COMPLETED",
            "local_base_candidate": deepcopy(self.candidate)}

    def evaluator(self, interval=("10", "10")):
        def evaluate(instance, candidate, accuracy, budget):
            self.clock.now += 1
            return complete_mock(instance, candidate, accuracy, budget, interval=interval)
        return Mock(side_effect=evaluate)

    def packet(self, candidate, **metadata):
        return {"state": "COMPLETE_LEGAL_CANDIDATE", "candidate": deepcopy(candidate),
            "nonthermal_energy_J": "1", "evidence_kind": "MOCK_ONLY",
            "additional_reversed_edges": [], **metadata}

    def execute(self, *, initializer=None, evaluator=None, packets=(), loader=None,
                budget=None, clock=None):
        self.call_number += 1
        workdir = Path(self.tmp.name) / ("call_%02d" % self.call_number)
        initializer = self.initialize if initializer is None else initializer
        evaluator = self.evaluator() if evaluator is None else evaluator
        loader = (lambda budget: (deepcopy(self.config), deepcopy(self.instance))) if loader is None else loader
        packet_fn = (method.candidate_packets if packets is None else packets
            if callable(packets) else Mock(return_value=iter(packets)))
        # A real backend call would fail this suite even if the imported alias
        # changed.  Only explicit invented evaluator bindings are permitted.
        with patch.object(method, "candidate_packets", packet_fn), \
                patch("heft_method.run_heft", side_effect=AssertionError("NO_REAL_HEFT")), \
                patch("thermal.evaluate_candidate", side_effect=AssertionError("NO_REAL_THERMAL")):
            result = method.execute_reconstruction(loader, workdir,
                bindings=method.Bindings(initializer, evaluator), seconds=300,
                clock=self.clock if clock is None else clock, budget=budget)
        self.assertEqual(result["evidence_kind"], "MOCK_ONLY")
        self.assertNotEqual(result["state"], "SAFE")
        self.assertFalse(result["usable_as_research_evidence"])
        self.assertFalse(result["independently_proven_optimal"])
        self.assertFalse(result["independently_proven_infeasible"])
        self.assertFalse(result["coverage_complete"])
        self.assertEqual(json.loads((workdir / "result.json").read_text(encoding="utf-8")), result)
        return result, evaluator, packet_fn

    def assert_old_safe(self, result):
        self.assertEqual(result["state"], "MOCK_SAFE")
        self.assertEqual(result["safe_candidate"], self.candidate)
        self.assertEqual(result["safe_upper_bound_J"], "10")

    def test_one_root_covers_loader_initialization_targets_reconstruction_and_assessment(self):
        self.candidate["scenes"]["S0"][0]["opp"] = "H"
        for mode in self.instance["stage_modes"]["x"]:
            if mode["opp_id"] == "H":
                mode["activity_power_W"] = "5"
        roots = {name: [] for name in ("loader", "initializer", "targets", "reconstruct", "assessment")}
        target_impl, reconstruct_impl = method.energy_targets, method.core.reconstruct
        def loader(budget):
            roots["loader"].append(budget)
            self.clock.now += 10
            return deepcopy(self.config), deepcopy(self.instance)
        def initialize(instance, config, budget, assess, *, allow_auto_low):
            roots["initializer"].append(budget)
            self.assertEqual(budget.elapsed, 10)
            self.clock.now += 3
            return self.initialize(instance, config, budget, assess, allow_auto_low=allow_auto_low)
        def targets(instance, candidate, budget):
            roots["targets"].append(budget)
            self.clock.now += 2
            return target_impl(instance, candidate, budget)
        def reconstruct(*args, **kwargs):
            roots["reconstruct"].append(kwargs["budget"])
            self.clock.now += 1
            return reconstruct_impl(*args, **kwargs)
        def evaluate(instance, candidate, accuracy, budget):
            roots["assessment"].append(budget)
            self.clock.now += 1
            e = "10" if candidate == self.candidate else "11"
            return complete_mock(instance, candidate, accuracy, budget, interval=(e, e))
        with patch.object(method, "energy_targets", targets), \
                patch.object(method.core, "reconstruct", reconstruct):
            result, _, _ = self.execute(loader=loader, initializer=initialize,
                evaluator=Mock(side_effect=evaluate), packets=None)
        self.assertTrue(all(roots.values()), roots)
        root = roots["loader"][0]
        self.assertTrue(all(budget is root for budgets in roots.values() for budget in budgets))
        self.assertEqual(result["root_context"]["root_start"], "1000.0")
        self.assertEqual(result["root_context"]["root_deadline"], "1300.0")
        self.assertEqual(result["timing"]["method_elapsed_s"], self.clock.now - 1000)
        self.assertEqual(result["run_terminal"], "SEARCH_COMPLETED")

    def test_unfinished_initializer_keeps_safe_and_never_enters_graph(self):
        for metadata in ({}, {"status": "MOCK_INITIALIZER_INTERRUPTED"}):
            with self.subTest(metadata=metadata):
                def initialize(instance, config, budget, assess, *, allow_auto_low):
                    self.initialize(instance, config, budget, assess, allow_auto_low=allow_auto_low)
                    return metadata
                result, _, packets = self.execute(initializer=initialize)
                self.assert_old_safe(result)
                self.assertEqual(result["reason"], "INITIALIZATION_NOT_COMPLETED")
                self.assertEqual(result["run_terminal"], "UNRESOLVED_STOP")
                packets.assert_not_called()

    def test_initializer_budget_exhaustion_keeps_safe_and_never_enters_graph(self):
        def initialize(instance, config, budget, assess, *, allow_auto_low):
            self.initialize(instance, config, budget, assess, allow_auto_low=allow_auto_low)
            self.clock.now = 1300
            return {"status": "MOCK_INITIALIZER_COMPLETED"}
        result, _, packets = self.execute(initializer=initialize)
        self.assert_old_safe(result)
        self.assertEqual(result["run_terminal"], "BUDGET_EXHAUSTED")
        packets.assert_not_called()

    def test_no_saving_target_keeps_safe_without_reconstruction(self):
        with patch.object(method.core, "reconstruct", side_effect=AssertionError("NO_TARGET_NO_GRAPH")) as graph:
            result, evaluator, _ = self.execute(packets=None)
        self.assert_old_safe(result)
        self.assertEqual(result["run_terminal"], "SEARCH_COMPLETED")
        self.assertEqual(result["reconstruction_attempts"], [])
        self.assertEqual(evaluator.call_count, 1)
        graph.assert_not_called()

    def test_overlap_or_equal_intervals_never_replace_incumbent(self):
        trial = changed(self.candidate, 5)
        for interval in (("8", "19/2"), ("8", "9"), ("11", "11")):
            with self.subTest(interval=interval):
                def evaluate(instance, candidate, accuracy, budget):
                    self.clock.now += 1
                    return complete_mock(instance, candidate, accuracy, budget,
                        interval=("9", "10") if candidate == self.candidate else interval)
                result, _, _ = self.execute(evaluator=Mock(side_effect=evaluate),
                    packets=[self.packet(trial)])
                self.assert_old_safe(result)
                self.assertTrue(result["evaluations"][-1]["accepted_safe"])
                self.assertFalse(result["evaluations"][-1]["incumbent_replaced"])
                self.assertEqual(result["graph_strict_improvements"], 0)

    def test_strict_interval_separation_replaces_incumbent(self):
        trial = changed(self.candidate, 5)
        def evaluate(instance, candidate, accuracy, budget):
            self.clock.now += 1
            return complete_mock(instance, candidate, accuracy, budget,
                interval=("9", "10") if candidate == self.candidate else ("8", "89/10"))
        result, _, _ = self.execute(evaluator=Mock(side_effect=evaluate), packets=[self.packet(trial)])
        self.assertEqual(result["safe_candidate"], trial)
        self.assertEqual(result["safe_upper_bound_J"], "89/10")
        self.assertEqual(result["graph_strict_improvements"], 1)
        self.assertTrue(result["graph_proposals"][-1]["strict_accepted"])

    def test_thermal_unresolved_and_technical_receipts_preserve_old_safe(self):
        trial = changed(self.candidate, 5)
        for state, terminal in (("THERMAL_VIOLATION", "SEARCH_COMPLETED"),
                ("UNRESOLVED", "UNRESOLVED_STOP"), ("NUMERICAL_ERROR", "TECHNICAL_STOP")):
            with self.subTest(state=state):
                def evaluate(instance, candidate, accuracy, budget):
                    self.clock.now += 1
                    receipt = complete_mock(instance, candidate, accuracy, budget)
                    if candidate != self.candidate:
                        receipt.update(state=state, rankable_energy=False,
                            weighted_energy_J=None, safe_upper_bound_J=None)
                        if state == "THERMAL_VIOLATION":
                            receipt["violations"] = [{"scene_id": "S0", "node": "c1",
                                "time_s": "1/100", "temperature_degC": ["81", "82"],
                                "limit_degC": "80", "formed_at_elapsed_s": budget.elapsed}]
                    return receipt
                result, _, _ = self.execute(evaluator=Mock(side_effect=evaluate), packets=[self.packet(trial)])
                self.assert_old_safe(result)
                self.assertEqual(result["run_terminal"], terminal)
                self.assertEqual(result["graph_strict_improvements"], 0)
                self.assertEqual(len(result["violations"]), int(state == "THERMAL_VIOLATION"))

    def test_initializer_and_graph_exceptions_preserve_old_safe(self):
        def initialize(instance, config, budget, assess, *, allow_auto_low):
            self.initialize(instance, config, budget, assess, allow_auto_low=allow_auto_low)
            raise RuntimeError("invented initialization failure")
        result, _, packets = self.execute(initializer=initialize)
        self.assert_old_safe(result)
        self.assertEqual(result["run_terminal"], "TECHNICAL_STOP")
        packets.assert_not_called()
        def packets(*args, **kwargs):
            raise RuntimeError("invented reconstruction failure")
        result, _, _ = self.execute(packets=packets)
        self.assert_old_safe(result)
        self.assertEqual(result["run_terminal"], "TECHNICAL_STOP")

    def test_failure_before_first_safe_has_no_candidate(self):
        initializer = Mock(side_effect=RuntimeError("invented early failure"))
        result, evaluator, packets = self.execute(initializer=initializer)
        self.assertIsNone(result["safe_candidate"])
        self.assertIsNone(result["safe_upper_bound_J"])
        self.assertEqual(result["state"], "UNRESOLVED")
        self.assertEqual(result["run_terminal"], "TECHNICAL_STOP")
        evaluator.assert_not_called()
        packets.assert_not_called()

    def test_timely_initial_receipt_survives_return_after_outer_deadline(self):
        def evaluate(instance, candidate, accuracy, budget):
            self.clock.now = 1300.1
            return complete_mock(instance, candidate, accuracy, budget, formed=299.9)
        result, _, packets = self.execute(evaluator=Mock(side_effect=evaluate))
        self.assert_old_safe(result)
        self.assertEqual(result["first_safe_at_s"], 299.9)
        self.assertEqual(result["run_terminal"], "BUDGET_EXHAUSTED")
        packets.assert_not_called()

    def test_timely_improvement_survives_return_after_outer_deadline(self):
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
        self.assertEqual(result["first_graph_strict_improvement_at_s"], 299.9)
        self.assertTrue(result["graph_proposals"][-1]["strict_accepted"])

    def test_new_safe_at_or_after_cutoff_is_rejected_and_old_safe_kept(self):
        trial = changed(self.candidate, 5)
        for formed in (300.0, 300.1):
            with self.subTest(formed=formed):
                self.clock.now = 1000
                def evaluate(instance, candidate, accuracy, budget):
                    if candidate == self.candidate:
                        self.clock.now += 1
                        return complete_mock(instance, candidate, accuracy, budget)
                    self.clock.now = 1300.2
                    return complete_mock(instance, candidate, accuracy, budget,
                        interval=("8", "8"), formed=formed)
                result, _, _ = self.execute(evaluator=Mock(side_effect=evaluate), packets=[self.packet(trial)])
                self.assert_old_safe(result)
                self.assertEqual(result["run_terminal"], "BUDGET_EXHAUSTED")
                self.assertEqual(result["reason"], "SAFE_FORMED_AFTER_DEADLINE")
                self.assertEqual(result["graph_strict_improvements"], 0)

    def test_malformed_or_future_safe_timestamp_cannot_replace_old_safe(self):
        trial = changed(self.candidate, 5)
        for formed in (True, -1.0, float("nan"), 200.0):
            with self.subTest(formed=formed):
                def evaluate(instance, candidate, accuracy, budget):
                    self.clock.now += 1
                    return complete_mock(instance, candidate, accuracy, budget,
                        interval=("10", "10") if candidate == self.candidate else ("8", "8"),
                        formed=None if candidate == self.candidate else formed)
                result, _, _ = self.execute(evaluator=Mock(side_effect=evaluate), packets=[self.packet(trial)])
                self.assert_old_safe(result)
                self.assertEqual(result["reason"], "INVALID_SAFE_TIMESTAMP")
                self.assertEqual(result["run_terminal"], "TECHNICAL_STOP")

    def test_caller_root_is_not_reset_and_is_used_in_every_stage(self):
        budget = MethodBudget(300, clock=self.clock)
        self.clock.now += 20
        roots = []
        def loader(supplied):
            roots.append(supplied)
            self.assertEqual(supplied.elapsed, 20)
            return deepcopy(self.config), deepcopy(self.instance)
        def initialize(instance, config, supplied, assess, *, allow_auto_low):
            roots.append(supplied)
            return self.initialize(instance, config, supplied, assess, allow_auto_low=allow_auto_low)
        def packets(instance, incumbent, supplied, *, diagnostics):
            roots.append(supplied)
            self.clock.now += 2
            return iter(())
        unused_clock = Mock(side_effect=AssertionError("CALLER_CLOCK_MUST_WIN"))
        result, _, _ = self.execute(loader=loader, initializer=initialize,
            packets=packets, budget=budget, clock=unused_clock)
        self.assertTrue(all(root is budget for root in roots))
        self.assertEqual(result["root_context"]["root_start"], "1000.0")
        self.assertEqual(result["root_context"]["root_deadline"], "1300.0")
        self.assertEqual(result["timing"]["method_elapsed_s"], 23)
        unused_clock.assert_not_called()

    def test_local_duplicate_cache_is_not_shared_between_calls(self):
        def initialize(instance, config, budget, assess, *, allow_auto_low):
            assess(self.candidate, "mock:first")
            assess(deepcopy(self.candidate), "mock:duplicate")
            return {"status": "MOCK_INITIALIZER_COMPLETED"}
        a, ea, _ = self.execute(initializer=initialize)
        b, eb, _ = self.execute(initializer=initialize)
        self.assertEqual(ea.call_count, 1)
        self.assertEqual(eb.call_count, 1)
        self.assertEqual(a["cache_hits"], 1)
        self.assertEqual(b["cache_hits"], 1)
        self.assertNotEqual(a["root_context"]["root_token"], b["root_context"]["root_token"])
        self.assertFalse(a["candidate_or_cache_shared_between_calls"])
        self.assertFalse(b["candidate_or_cache_shared_between_calls"])

    def test_zero_weight_scene_still_requires_complete_full_window_receipt(self):
        self.config, self.instance, self.candidate = artificial_input(two_scenes=True)
        self.instance["scenarios"][0]["weight"] = "1"
        self.instance["scenarios"][1]["weight"] = "0"
        for failure in ("missing", "incomplete", "short_window", "too_hot"):
            with self.subTest(failure=failure):
                def evaluate(instance, candidate, accuracy, budget):
                    self.clock.now += 1
                    receipt = complete_mock(instance, candidate, accuracy, budget)
                    if failure == "missing":
                        del receipt["scenes"]["S1"]
                    elif failure == "incomplete":
                        receipt["scenes"]["S1"]["complete"] = False
                    elif failure == "short_window":
                        receipt["scenes"]["S1"]["covered_until_s"] = "1/20"
                    else:
                        receipt["scenes"]["S1"]["peaks_degC"]["c1"] = ["81", "81"]
                    return receipt
                result, _, packets = self.execute(evaluator=Mock(side_effect=evaluate))
                self.assertIsNone(result["safe_candidate"])
                self.assertEqual(result["run_terminal"], "TECHNICAL_STOP")
                packets.assert_not_called()

    def test_new_sources_are_bound_and_source_drift_keeps_old_safe(self):
        sources = method.source_identity()
        self.assertTrue({"chapter4_scheduler/blocking/method.py",
            "chapter4_scheduler/blocking/core.py", "chapter4_scheduler/blocking/__init__.py"} <= set(sources))
        original_source = method.source_identity
        drifted = [False]
        def source_identity():
            result = original_source()
            if drifted[0]:
                result["chapter4_scheduler/blocking/core.py"] = "0" * 64
            return result
        def initialize(instance, config, budget, assess, *, allow_auto_low):
            result = self.initialize(instance, config, budget, assess, allow_auto_low=allow_auto_low)
            drifted[0] = True
            return result
        with patch.object(method, "source_identity", source_identity):
            result, _, packets = self.execute(initializer=initialize)
        self.assert_old_safe(result)
        self.assertEqual(result["reason"], "CALL_CONTEXT_DRIFT")
        self.assertEqual(result["run_terminal"], "TECHNICAL_STOP")
        packets.assert_not_called()

    def test_input_config_and_root_drift_keep_old_safe(self):
        for target in ("input", "config", "start", "deadline", "seconds"):
            with self.subTest(target=target):
                def initialize(instance, config, budget, assess, *, allow_auto_low):
                    result = self.initialize(instance, config, budget, assess, allow_auto_low=allow_auto_low)
                    if target == "input": instance["id"] = "mutated"
                    elif target == "config": config["accuracy_targets"]["energy_absolute_error_J"] = "999"
                    elif target == "start": budget.start += 1
                    elif target == "deadline": budget.deadline += 1
                    else: budget.seconds += 1
                    return result
                result, _, packets = self.execute(initializer=initialize)
                self.assert_old_safe(result)
                self.assertEqual(result["reason"], "CALL_CONTEXT_DRIFT")
                packets.assert_not_called()

    def test_bad_receipt_hash_cannot_replace_old_safe(self):
        trial = changed(self.candidate, 5)
        for key in ("input_sha256", "candidate_sha256"):
            with self.subTest(key=key):
                def evaluate(instance, candidate, accuracy, budget):
                    self.clock.now += 1
                    receipt = complete_mock(instance, candidate, accuracy, budget)
                    if candidate != self.candidate:
                        receipt["evidence_identity"][key] = "0" * 64
                    return receipt
                result, _, _ = self.execute(evaluator=Mock(side_effect=evaluate), packets=[self.packet(trial)])
                self.assert_old_safe(result)
                self.assertEqual(result["reason"], "RECEIPT_INPUT_OR_CANDIDATE_IDENTITY")

    def test_more_than_one_additional_edge_is_rejected_before_assessment(self):
        trial = changed(self.candidate, 5)
        packet = self.packet(trial, additional_reversed_edges=[["a", "b"], ["c", "d"]])
        result, evaluator, _ = self.execute(packets=[packet])
        self.assert_old_safe(result)
        self.assertEqual(result["reason"], "INVALID_ADDITIONAL_EDGE_SCOPE")
        self.assertEqual(result["run_terminal"], "TECHNICAL_STOP")
        self.assertEqual(evaluator.call_count, 1)

    def test_evaluator_mutation_is_rejected_without_replacing_old_safe(self):
        trial = changed(self.candidate, 5)
        for target in ("input", "candidate", "accuracy"):
            with self.subTest(target=target):
                def evaluate(instance, candidate, accuracy, budget):
                    self.clock.now += 1
                    receipt = complete_mock(instance, candidate, accuracy, budget)
                    if candidate != self.candidate:
                        if target == "input": instance["id"] = "mutated"
                        elif target == "candidate": candidate["scenes"]["S0"][0]["start_ms"] = "10"
                        else: accuracy["energy_absolute_error_J"] = "999"
                    return receipt
                result, _, _ = self.execute(evaluator=Mock(side_effect=evaluate), packets=[self.packet(trial)])
                self.assert_old_safe(result)
                self.assertEqual(result["reason"], "EVALUATOR_ARGUMENT_MUTATION")

    def test_actual_generator_repairs_cross_resource_blocking_in_artificial_fixture(self):
        self.config, self.instance, self.candidate = crossing_input()
        self.assertTrue(independent_legality(self.instance, self.candidate))
        evaluated = []
        def evaluate(instance, candidate, accuracy, budget):
            self.clock.now += 1
            self.assertTrue(independent_legality(instance, candidate))
            rr = rows(candidate)
            repaired = (rr["lead"]["opp"] == "L" and
                F(rr["pa"]["start_ms"]) + 3 <= F(rr["pb"]["start_ms"]))
            # Invented contract rule: only the demonstrated structural repair
            # gets 8 J. This is not integration, a measured benefit, or a SAFE.
            energy = "8" if repaired else "10"
            evaluated.append(deepcopy(candidate))
            return complete_mock(instance, candidate, accuracy, budget, interval=(energy, energy))
        # This call uses the genuine candidate generator, target selector,
        # blocking traces, graph reconstruction, and complete-legality checker.
        result, _, _ = self.execute(evaluator=Mock(side_effect=evaluate), packets=None)
        rr = rows(result["safe_candidate"])
        self.assertEqual(result["state"], "MOCK_SAFE")
        self.assertEqual(result["safe_upper_bound_J"], "8")
        self.assertEqual(result["graph_strict_improvements"], 1)
        self.assertEqual(rr["lead"]["opp"], "L")
        self.assertLessEqual(F(rr["pa"]["start_ms"]) + 3, F(rr["pb"]["start_ms"]))
        self.assertLessEqual(F(rr["pa"]["start_ms"]) + 3, 34)
        self.assertTrue(independent_legality(self.instance, result["safe_candidate"]))
        attempts = result["reconstruction_attempts"]
        base = [a for a in attempts if a["target"]["stage_id"] == "lead"
            and a["target"]["target_opp"] == "L" and a["extra_resource_edge"] is None
            and a["orientation"] == "incumbent" and a["template"] == "earliest"
            and a["opp_overrides"].get("tail") == "L"]
        self.assertTrue(base)
        self.assertTrue(any(a["state"] == "RECONSTRUCTION_REJECTED"
            and any(v["stage_id"] == "pa" for v in a["deadline_violations"])
            for a in base))
        repair = [a for a in attempts if a["extra_resource_edge"] == ["pb", "pa"]
            and a["state"] == "COMPLETE_LEGAL_CANDIDATE"]
        self.assertTrue(repair)
        self.assertTrue(any(p["strict_accepted"] and p["additional_reversed_edges"] == [["pb", "pa"]]
            for p in result["graph_proposals"]))
        self.assertEqual(evaluated[0], self.candidate)
        self.assertTrue(all(candidate != self.candidate for candidate in evaluated[1:]))


if __name__ == "__main__":
    unittest.main()
