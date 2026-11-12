"""Eight groups of deterministic, manually specified correctness tests.

No random family, solver, physical-energy or thermal evaluation is used.
Run from the repository root with the package's dedicated test runner.
"""

import ast
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
import unittest
from unittest.mock import patch

from . import contract, checker, scheduler, deadlines, bounds
from .fixtures import (
    chain_family, diamond_family, gap_family, separate_scenes_family,
    copies_family, parallel_cpu_family, shared_scene_family,
    reverse_input_order, occurrence, profile, request,
)


def rows_by_id(candidate, scene_id="S"):
    return {row["stage_id"]: row for row in candidate["scenes"][scene_id]}


def derive(parent, axis):
    child = deepcopy(parent)
    child["variant_id"] = axis + "_manual"
    child["derivation"] = {
        "axis": axis, "parent_contract_hash": contract.contract_hash(parent)}
    return child


def absolute_sources(data):
    return {s["id"]: {r["id"]: {
        "source_scene": s["id"], "source_request": r["id"],
        "policy": "absolute"} for r in s["requests"]}
        for s in data["scenarios"]}


def base_receipt(data, beta="1.3"):
    bundle = scheduler.build_references(data)
    receipt = deadlines.make_deadlines(data, bundle["timetables"]["H"],
        beta=beta, reference_topology_id=data["topology_id"])
    return bundle, receipt


class ReferenceTests(unittest.TestCase):
    def assert_contract_rejected(self, data):
        with self.assertRaises(contract.ContractError):
            contract.normalize(data)

    def assert_bad_candidate(self, data, candidate):
        result = checker.check_timetable(data, candidate)
        self.assertEqual(result["state"], "INVALID_SCHEDULE", result)
        self.assertEqual(result["thermal_status"], "NOT_EVALUATED")

    def test_g1_empty_shared_support_intersection(self):
        data = shared_scene_family()
        data["scenarios"][0]["stage_instances"][0]["legal_units"] = ["CPU1"]
        data["scenarios"][1]["stage_instances"][0]["legal_units"] = ["CPU2"]
        self.assert_contract_rejected(data)

    def test_g1_missing_opp_is_not_substituted(self):
        data = chain_family()
        data["stage_profiles"]["s0"]["units"]["CPU1"]["legal_opps"] = ["L", "H"]
        self.assert_contract_rejected(data)

    def test_g1_duplicate_stage_is_rejected(self):
        data = chain_family()
        data["scenarios"][0]["stage_instances"].append(
            deepcopy(data["scenarios"][0]["stage_instances"][0]))
        self.assert_contract_rejected(data)

    def test_g1_missing_stage_is_rejected(self):
        data = chain_family()
        data["scenarios"][0]["stage_instances"].pop()
        self.assert_contract_rejected(data)

    def test_g1_invalid_edge_is_rejected(self):
        data = chain_family()
        data["scenarios"][0]["dependencies"].append(["unknown", "s0"])
        self.assert_contract_rejected(data)

    def test_g1_cycle_is_rejected(self):
        data = chain_family()
        data["scenarios"][0]["dependencies"].append(["s2", "s0"])
        self.assert_contract_rejected(data)

    def test_g1_explicit_release_weight_and_exact_scalars(self):
        original = chain_family()
        for mode in ("release", "weight", "float", "deadline", "context"):
            with self.subTest(mode=mode):
                data = deepcopy(original)
                if mode == "release":
                    del data["scenarios"][0]["requests"][0]["release_ms"]
                elif mode == "weight":
                    del data["scenarios"][0]["weight"]
                elif mode == "float":
                    data["stage_profiles"]["s0"]["units"]["CPU1"]["d_ref_ms"] = 5.0
                elif mode == "context":
                    del data["context"]
                else:
                    data["window_ms"] = "400"
                self.assert_contract_rejected(data)

    def test_g2_permutation_has_identical_canonical_identity_and_timetables(self):
        data = separate_scenes_family()
        reversed_data = reverse_input_order(data)
        self.assertEqual(contract.contract_hash(data), contract.contract_hash(reversed_data))
        first = scheduler.build_references(data)
        second = scheduler.build_references(reversed_data)
        self.assertEqual(first["mapping_record"], second["mapping_record"])
        self.assertEqual(first["timetables"], second["timetables"])

    def test_g2_exclusive_scene_loads_are_not_summed_as_concurrent(self):
        data = separate_scenes_family()
        mapping = scheduler.choose_mapping(data)
        # After a/c: max load is 30, not 60. x on CPU gives 40;
        # x on GPU leaves max 30 even though x itself takes 20 instead of 10.
        self.assertEqual(mapping["mapping"], {"a": "CPU1", "c": "CPU1", "x": "GPU0"})
        self.assertEqual(Fraction(mapping["load_scores_ms"]["x"]), 5)

    def test_g2_request_copies_contribute_to_sorting_load(self):
        data = copies_family()
        mapping = scheduler.choose_mapping(data)
        self.assertEqual(Fraction(mapping["load_scores_ms"]["x"]), 20)
        self.assertEqual(Fraction(mapping["load_scores_ms"]["a"]), 15)
        self.assertEqual(mapping["mapping"]["x"], "CPU1")

    def test_g2_lexicographic_unit_tie_is_reproducible(self):
        mapping = scheduler.choose_mapping(parallel_cpu_family())
        self.assertEqual(mapping["mapping"], {"a": "CPU1", "b": "CPU2"})

    def test_g3_diamond_has_manual_expected_completion(self):
        data = diamond_family()
        timetable = scheduler.build_references(data)["timetables"]["H"]
        rows = rows_by_id(timetable)
        self.assertEqual({key: Fraction(row["start_ms"]) for key, row in rows.items()},
                         {"pre": 0, "left": 5, "right": 5, "join": 15})
        result = checker.check_timetable(data, timetable, required_opp="H")
        self.assertEqual(result["state"], "TIME_STRUCTURAL_VALID")
        self.assertEqual(Fraction(result["completions_ms"]["S"]["r"]), 20)

    def test_g3_shared_unit_cannot_change_across_scenes(self):
        data = shared_scene_family()
        table = scheduler.build_references(data)["timetables"]["H"]
        table["scenes"]["S2"][0]["unit"] = "CPU2"
        self.assert_bad_candidate(data, table)

    def test_g3_shared_unit_cannot_change_across_request_copies(self):
        data = copies_family()
        table = scheduler.build_references(data)["timetables"]["H"]
        for row in table["scenes"]["S"]:
            if row["stage_id"] == "x2":
                row["unit"] = "GPU0"
        self.assert_bad_candidate(data, table)

    def test_g3_s1_projection_reuses_mapping_without_reconstruction(self):
        data = separate_scenes_family()
        bundle = scheduler.build_references(data)
        child = derive(data, "S1")
        child["scenarios"] = [deepcopy(data["scenarios"][0])]
        child["scenarios"][0]["weight"] = "1"
        with patch.object(scheduler, "choose_mapping", side_effect=AssertionError("remap")), \
             patch.object(scheduler, "build_timetable", side_effect=AssertionError("reschedule")):
            projected = scheduler.project_references(data, bundle, child)
        self.assertEqual(projected["mapping_origin_hash"], bundle["mapping_origin_hash"])
        for opp in ("H", "M", "L"):
            self.assertEqual(projected["timetables"][opp]["scenes"],
                             {"S1": bundle["timetables"][opp]["scenes"]["S1"]})

    def test_g3_release_is_respected_and_completion_is_per_request(self):
        data = gap_family()
        table = scheduler.build_references(data)["timetables"]["H"]
        result = checker.check_timetable(data, table)
        self.assertEqual(result["completions_ms"]["S"], {"A": "25", "B": "10"})
        rows_by_id(table)["short"]["start_ms"] = "0"
        self.assert_bad_candidate(data, table)

    def test_g3_s1_rejects_damaged_mapping_origin(self):
        parent = separate_scenes_family()
        bundle = scheduler.build_references(parent)
        child = derive(parent, "S1")
        child["scenarios"] = [deepcopy(parent["scenarios"][0])]
        child["scenarios"][0]["weight"] = "1"
        for field in ("mapping_origin_hash", "record_contract_hash"):
            bad = deepcopy(bundle)
            if field == "mapping_origin_hash":
                bad[field] = "0" * 64
            else:
                bad["mapping_record"]["contract_hash"] = "0" * 64
                bad["mapping_origin_hash"] = contract.content_hash(bad["mapping_record"])
            with self.subTest(field=field), self.assertRaises(contract.ContractError):
                scheduler.project_references(parent, bad, child)
    def test_g4_no_400ms_reference_horizon(self):
        data = chain_family(("405", "5"))
        table = scheduler.build_references(data)["timetables"]["H"]
        result = checker.check_timetable(data, table)
        self.assertEqual(result["state"], "TIME_STRUCTURAL_VALID")
        self.assertEqual(Fraction(result["completions_ms"]["S"]["r"]), 410)

    def test_g4_fractional_finishes_keep_exact_values_and_grid_successor(self):
        data = chain_family(("10", "10"))
        table = scheduler.build_references(data)["timetables"]["M"]
        self.assertEqual(Fraction(rows_by_id(table)["s1"]["start_ms"]), 15)
        result = checker.check_timetable(data, table)
        self.assertEqual(Fraction(result["completions_ms"]["S"]["r"]), Fraction(85, 3))

    def test_g4_earliest_gap_insertion_is_not_append_only(self):
        data = gap_family()
        table = scheduler.build_references(data)["timetables"]["H"]
        rows = rows_by_id(table)
        self.assertEqual(Fraction(rows["tail"]["start_ms"]), 20)
        self.assertEqual(Fraction(rows["short"]["start_ms"]), 5)

    def test_g4_dependency_and_grid_tampering_are_detected(self):
        data = chain_family()
        original = scheduler.build_references(data)["timetables"]["H"]
        for value in ("0", "6"):
            with self.subTest(start=value):
                table = deepcopy(original)
                rows_by_id(table)["s1"]["start_ms"] = value
                self.assert_bad_candidate(data, table)

    def test_g5_shared_cpu_same_opp_overlap_is_legal(self):
        data = parallel_cpu_family()
        table = scheduler.build_references(data)["timetables"]["H"]
        self.assertEqual({Fraction(row["start_ms"]) for row in table["scenes"]["S"]}, {0})
        self.assertEqual(checker.check_timetable(data, table)["state"], "TIME_STRUCTURAL_VALID")

    def test_g5_shared_cpu_different_opp_overlap_is_illegal(self):
        data = parallel_cpu_family()
        table = scheduler.build_references(data)["timetables"]["H"]
        rows_by_id(table)["b"]["opp"] = "M"
        self.assert_bad_candidate(data, table)

    def test_g5_same_unit_overlap_is_illegal(self):
        data = parallel_cpu_family()
        table = scheduler.build_references(data)["timetables"]["H"]
        rows_by_id(table)["b"]["unit"] = "CPU1"
        self.assert_bad_candidate(data, table)

    def test_g5_half_open_intervals_allow_touching(self):
        data = parallel_cpu_family()
        table = {"scenes": {"S": [
            {"stage_id": "a", "unit": "CPU1", "opp": "H", "start_ms": "0"},
            {"stage_id": "b", "unit": "CPU1", "opp": "H", "start_ms": "10"}]}}
        self.assertEqual(checker.check_timetable(data, table)["state"], "TIME_STRUCTURAL_VALID")

    def test_g5_legacy_hold_is_not_silently_auto_low(self):
        data = chain_family()
        data["execution_rules"]["idle_holds_last_opp"] = True
        self.assert_contract_rejected(data)

    def test_g6_hml_uses_same_mapping_and_response_profiles(self):
        data = parallel_cpu_family()
        original = deepcopy(data)
        bundle = scheduler.build_references(data)
        for opp in ("H", "M", "L"):
            self.assertEqual({row["stage_id"]: row["unit"] for row in bundle["timetables"][opp]["scenes"]["S"]},
                             {"a": "CPU1", "b": "CPU2"})
            self.assertEqual({row["opp"] for row in bundle["timetables"][opp]["scenes"]["S"]}, {opp})
        self.assertEqual(data, original)

    def test_g6_insensitive_response_is_not_replaced_by_one_over_f(self):
        data = chain_family(("10",), alpha="0")
        bundle = scheduler.build_references(data)
        for opp in ("H", "M", "L"):
            result = checker.check_timetable(data, bundle["timetables"][opp])
            self.assertEqual(Fraction(result["completions_ms"]["S"]["r"]), 10)

    def test_g6_manual_deadline_thresholds_and_all_betas_without_reschedule(self):
        data = chain_family()
        bundle = scheduler.build_references(data)
        with patch.object(scheduler, "build_references", side_effect=AssertionError("reschedule")), \
             patch.object(scheduler, "build_timetable", side_effect=AssertionError("reschedule")):
            report = deadlines.diagnose(data, bundle, betas=["1", "1.3", "1.6", "2"],
                                        reference_topology_id="chain")
        self.assertEqual(Fraction(report["thresholds"]["M"]), Fraction(19, 12))
        self.assertEqual(Fraction(report["thresholds"]["L"]), 2)
        expected = {"1": (True, False, False), "13/10": (True, False, False),
                    "8/5": (True, True, False), "2": (True, True, True)}
        for beta, statuses in expected.items():
            record = report["by_beta"][beta]
            self.assertEqual(Fraction(record["deadlines"]["requests"]["S"]["r"]["deadline_ms"]),
                             Fraction(beta) * 20)
            for opp, passed in zip(("H", "M", "L"), statuses):
                self.assertEqual(record["by_opp"][opp]["all_on_time"], passed)

    def test_g6_beta_and_reference_topology_have_no_defaults(self):
        data = chain_family()
        h = scheduler.build_references(data)["timetables"]["H"]
        with self.assertRaises(TypeError):
            deadlines.make_deadlines(data, h)
        with self.assertRaises((ValueError, contract.ContractError)):
            deadlines.make_deadlines(data, h, beta="1.3", reference_topology_id="unselected")

    def test_g6_incomplete_reference_cannot_create_deadlines(self):
        data = chain_family()
        h = scheduler.build_references(data)["timetables"]["H"]
        h["scenes"]["S"].pop()
        with self.assertRaises((ValueError, contract.ContractError)):
            deadlines.make_deadlines(data, h, beta="1.3", reference_topology_id="chain")

    def test_g6_bounds_distinguish_global_and_fixed_mapping_scopes(self):
        data = copies_family()
        mapping = scheduler.choose_mapping(data)["mapping"]
        value = bounds.lower_bounds(data, mapping)["S"]
        # Optimistic two-device capacity: (15+10+10)/2 = 17.5 ms.
        # Fixed reference puts all three executions on CPU1: 35 ms.
        self.assertEqual(Fraction(value["subset_capacity_duration_ms"]["CPU1,GPU0"]), Fraction(35, 2))
        self.assertEqual(Fraction(value["scene_completion_lower_bound_ms"]), Fraction(35, 2))
        self.assertEqual(Fraction(value["fixed_mapping_completion_lower_bound_ms"]), 35)
        self.assertEqual(len(value["subset_capacity_duration_ms"]), 15)

    def test_g7_counts_include_copies_without_duplicating_shared_identity(self):
        self.assertEqual(deadlines.counts(copies_family())["S"], {
            "fixed_stage_count": 2, "stage_instance_count": 3,
            "requests": 3, "work_units": "35"})

    def test_g7_s2_real_work_growth_gets_new_base_deadline(self):
        parent = chain_family()
        _, old_receipt = base_receipt(parent)
        child = derive(parent, "S2")
        child["stage_profiles"]["s3"] = profile({"CPU1": "5"}, work="5")
        s = child["scenarios"][0]
        s["stage_instances"].append(occurrence("s3", "r", "s3", ["CPU1"]))
        s["requests"][0]["stage_instance_ids"].append("s3")
        s["dependencies"].append(["s2", "s3"])
        _, receipt = base_receipt(child)
        self.assertEqual(len(s["requests"]), 1)
        self.assertEqual(len(s["stage_instances"]), 4)
        self.assertEqual(sum(Fraction(v["work_units"]) for v in child["stage_profiles"].values()), 25)
        self.assertEqual(Fraction(receipt["requests"]["S"]["r"]["deadline_ms"]), Fraction(65, 2))
        self.assertNotEqual(receipt["deadline_origin_hash"], old_receipt["deadline_origin_hash"])

    def test_g7_s3_preserves_work_deadline_and_exposes_grid_wait(self):
        parent = chain_family(("4",))
        _, old = base_receipt(parent)
        child = derive(parent, "S3")
        child["topology_id"] = "split_manual"
        child["stage_profiles"] = {s: profile({"CPU1": "2"}, work="2") for s in ("a", "b")}
        scene = child["scenarios"][0]
        scene["requests"][0]["stage_instance_ids"] = ["a", "b"]
        scene["stage_instances"] = [occurrence(s, "r", s, ["CPU1"]) for s in ("a", "b")]
        scene["dependencies"] = [["a", "b"]]
        with patch.object(deadlines, "make_deadlines", side_effect=AssertionError("regenerate")):
            inherited = deadlines.inherit_deadlines(parent, old, child, request_sources=absolute_sources(child))
        h = scheduler.build_references(child)["timetables"]["H"]
        compared = deadlines.compare_deadlines(child, h, inherited)
        self.assertEqual(sum(Fraction(p["work_units"]) for p in child["stage_profiles"].values()), 4)
        self.assertEqual(inherited["deadline_origin_hash"], old["deadline_origin_hash"])
        self.assertEqual(Fraction(inherited["requests"]["S"]["r"]["deadline_ms"]), Fraction(26, 5))
        self.assertFalse(compared["all_on_time"])
        self.assertEqual(Fraction(compared["slack_ms"]["S"]["r"]), Fraction(-9, 5))

    def test_g7_s4_changed_topology_does_not_regenerate_deadline(self):
        parent = diamond_family()
        _, old = base_receipt(parent)
        child = derive(parent, "S4")
        child["topology_id"] = "chain_manual"
        child["scenarios"][0]["dependencies"] = [["pre", "left"], ["left", "right"], ["right", "join"]]
        with patch.object(deadlines, "make_deadlines", side_effect=AssertionError("regenerate")):
            receipt = deadlines.inherit_deadlines(parent, old, child, request_sources=absolute_sources(child))
        self.assertEqual(receipt["reference_topology_id"], "diamond")
        self.assertEqual(receipt["deadline_origin_hash"], old["deadline_origin_hash"])
        self.assertEqual(Fraction(receipt["requests"]["S"]["r"]["deadline_ms"]), 26)
        h = scheduler.build_references(child)["timetables"]["H"]
        with self.assertRaises((ValueError, contract.ContractError)):
            deadlines.make_deadlines(child, h, beta="1.3", reference_topology_id="chain_manual")

    def test_g7_s5_work_pressure_does_not_relax_inherited_deadline(self):
        parent = chain_family()
        _, old = base_receipt(parent)
        child = derive(parent, "S5")
        for p in child["stage_profiles"].values():
            p["work_units"] = str(Fraction(p["work_units"]) * Fraction(5, 4))
            p["units"]["CPU1"]["d_ref_ms"] = str(Fraction(p["units"]["CPU1"]["d_ref_ms"]) * Fraction(5, 4))
        with patch.object(deadlines, "make_deadlines", side_effect=AssertionError("regenerate")):
            receipt = deadlines.inherit_deadlines(parent, old, child, request_sources=absolute_sources(child))
        h = scheduler.build_references(child)["timetables"]["H"]
        result = deadlines.compare_deadlines(child, h, receipt)
        self.assertEqual(Fraction(receipt["requests"]["S"]["r"]["deadline_ms"]), 26)
        self.assertFalse(result["all_on_time"])
        self.assertEqual(result["check"]["state"], "TIME_STRUCTURAL_VALID")

    def test_g7_s6_temperature_is_not_used_by_reference(self):
        parent = chain_family()
        parent["context"]["initial_temperature_degC"] = "50"
        bundle, old = base_receipt(parent)
        child = derive(parent, "S6")
        child["context"]["initial_temperature_degC"] = "78"
        new_bundle = scheduler.build_references(child)
        self.assertEqual(new_bundle["timetables"], bundle["timetables"])
        receipt = deadlines.inherit_deadlines(parent, old, child, request_sources=absolute_sources(child))
        self.assertEqual(receipt["requests"], old["requests"])

    def test_g7_s7_release_and_relative_deadline_are_explicit(self):
        parent = chain_family()
        _, old = base_receipt(parent)
        child = derive(parent, "S7")
        s = child["scenarios"][0]
        s["requests"].append(request("r2", "7", ["s0_2", "s1_2", "s2_2"]))
        s["stage_instances"].extend(occurrence(sid + "_2", "r2", sid, ["CPU1"])
                                    for sid in ("s0", "s1", "s2"))
        s["dependencies"].extend([["s0_2", "s1_2"], ["s1_2", "s2_2"]])
        sources = absolute_sources(parent)
        sources["S"]["r2"] = {"source_scene": "S", "source_request": "r", "policy": "same_relative"}
        with patch.object(deadlines, "make_deadlines", side_effect=AssertionError("regenerate")):
            receipt = deadlines.inherit_deadlines(parent, old, child, request_sources=sources)
        self.assertEqual(Fraction(receipt["requests"]["S"]["r"]["deadline_ms"]), 26)
        self.assertEqual(Fraction(receipt["requests"]["S"]["r2"]["deadline_ms"]), 33)
        self.assertEqual(len(child["stage_profiles"]), 3)
        self.assertEqual(len(s["stage_instances"]), 6)
        with self.assertRaises((ValueError, contract.ContractError)):
            deadlines.inherit_deadlines(parent, old, child, request_sources=absolute_sources(parent))
        del s["requests"][1]["release_ms"]
        self.assert_contract_rejected(child)

    def test_g7_existing_request_release_cannot_drift(self):
        parent = chain_family()
        _, old = base_receipt(parent)
        child = derive(parent, "S7")
        child["scenarios"][0]["requests"][0]["release_ms"] = "5"
        with self.assertRaises((ValueError, contract.ContractError)):
            deadlines.inherit_deadlines(parent, old, child, request_sources=absolute_sources(child))

    def test_g7_cannot_delete_original_requests_during_inheritance(self):
        parent = gap_family()
        _, old = base_receipt(parent)
        for axis in ("S3", "S4", "S5", "S6", "S7", "E2"):
            child = derive(parent, axis)
            scene = child["scenarios"][0]
            scene["requests"] = [r for r in scene["requests"] if r["id"] != "B"]
            scene["stage_instances"] = [j for j in scene["stage_instances"] if j["request_id"] != "B"]
            with self.subTest(axis=axis), self.assertRaises(contract.ContractError):
                deadlines.inherit_deadlines(parent, old, child, request_sources=absolute_sources(child))

    def test_g7_only_s1_can_drop_scenes(self):
        parent = separate_scenes_family()
        _, old = base_receipt(parent)
        child = derive(parent, "S7")
        child["scenarios"] = [deepcopy(parent["scenarios"][0])]
        child["scenarios"][0]["weight"] = "1"
        with self.assertRaises(contract.ContractError):
            deadlines.inherit_deadlines(parent, old, child, request_sources=absolute_sources(child))

    def test_g6_receipt_detects_changed_deadline_or_target(self):
        parent = chain_family()
        refs, receipt = base_receipt(parent)
        bad = deepcopy(receipt)
        bad["requests"]["S"]["r"]["deadline_ms"] = "999"
        with self.assertRaises(contract.ContractError):
            deadlines.compare_deadlines(parent, refs["timetables"]["H"], bad)
        other = deepcopy(parent)
        other["variant_id"] = "different_input_identity"
        with self.assertRaises(contract.ContractError):
            deadlines.compare_deadlines(other, refs["timetables"]["H"], receipt)

    def test_g8_recorder_preserves_failed_subtest_detail(self):
        import io
        from .run_checks import RecordedResult

        class DeliberateFailure(unittest.TestCase):
            def runTest(self):
                with self.subTest(case="intentional_recording_probe"):
                    self.assertEqual(1, 2)

        probe = unittest.TextTestRunner(stream=io.StringIO(), resultclass=RecordedResult).run(
            unittest.TestSuite([DeliberateFailure()]))
        self.assertFalse(probe.wasSuccessful())
        self.assertEqual(probe.records[0]["state"], "FAIL")
        self.assertEqual(probe.subtest_records[0]["state"], "FAIL")
        self.assertIn("1 != 2", probe.subtest_records[0]["detail"])

    def test_g8_checker_does_not_call_scheduler_or_duration_helper(self):
        data = chain_family()
        candidate = {"scenes": {"S": [
            {"stage_id": "s0", "unit": "CPU1", "opp": "H", "start_ms": "0"},
            {"stage_id": "s1", "unit": "CPU1", "opp": "H", "start_ms": "5"},
            {"stage_id": "s2", "unit": "CPU1", "opp": "H", "start_ms": "15"}]}}
        with patch.object(scheduler, "choose_mapping", side_effect=AssertionError("planner")), \
             patch.object(scheduler, "build_timetable", side_effect=AssertionError("planner")), \
             patch.object(contract, "duration", side_effect=AssertionError("shared duration")):
            result = checker.check_timetable(data, candidate)
        self.assertEqual(result["state"], "TIME_STRUCTURAL_VALID")
        self.assertEqual(result["energy_status"], "NOT_EVALUATED")
        self.assertEqual(result["thermal_status"], "NOT_EVALUATED")

    def test_g8_checker_detects_missing_and_duplicate_assignments(self):
        data = chain_family()
        table = scheduler.build_references(data)["timetables"]["H"]
        missing = deepcopy(table)
        missing["scenes"]["S"].pop()
        duplicate = deepcopy(table)
        duplicate["scenes"]["S"].append(deepcopy(duplicate["scenes"]["S"][0]))
        self.assert_bad_candidate(data, missing)
        self.assert_bad_candidate(data, duplicate)

    def test_g8_implementation_has_no_solver_thermal_or_random_import(self):
        forbidden = {"subprocess", "scipy", "numpy", "matlab", "random", "thermal", "milp", "heft", "sa"}
        folder = Path(__file__).parent
        for filename in ("contract.py", "checker.py", "scheduler.py", "deadlines.py", "bounds.py"):
            tree = ast.parse((folder / filename).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [entry.name for entry in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                with self.subTest(file=filename, imports=names):
                    self.assertFalse(any(set(name.split(".")) & forbidden for name in names))
                    self.assertFalse(any("chapter3_experiments" in name for name in names))


if __name__ == "__main__":
    unittest.main()
