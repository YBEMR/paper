"""Manual positive and adversarial checks; no calibration input construction."""

from copy import deepcopy
from fractions import Fraction
import unittest
from unittest.mock import patch

from research.chapter3_deadline_reference.contract import ContractError, content_hash, exact
from research.chapter3_deadline_reference.checker import check_timetable
from research.chapter3_deadline_reference.deadlines import inherit_deadlines
from research.chapter3_deadline_reference.scheduler import build_timetable
from research.chapter3_workload_calibration.generator import stamp, request_sources, validate_transform
from research.chapter3_workload_calibration.topology import validate_graph, TopologyError
from .fixtures import manual_bundle, manual_evidence
from .transforms import (branch_multi, structure_metrics, derive_branch_multi,
                         derive_staggered, validate_adjustment, validated_base_h)


class TransformChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = manual_evidence()

    def test_branch_two_and_four_exact_edges(self):
        self.assertEqual(branch_multi(["a", "b"])["edges"], [["a", "b"]])
        got = branch_multi(["a", "b", "c", "d"])
        self.assertEqual(got["edges"], [["a", "b"], ["a", "c"], ["b", "d"], ["c", "d"]])
        self.assertEqual(got["required_outputs"], ["d"])
        self.assertEqual(got["structure"]["partial_order_width"], 2)

    def test_multiple_modules_edges_paths_and_parallel_pairs(self):
        for count in (8, 16, 32, 64):
            with self.subTest(count=count):
                nodes = [f"n{i:02d}" for i in range(count)]
                got = branch_multi(nodes)
                self.assertEqual(len(got["edges"]), 5 * (count // 4) - 1)
                self.assertEqual(got["structure"]["longest_path_nodes"], 3 * (count // 4))
                for at in range(4, count, 4):
                    self.assertIn([nodes[at - 1], nodes[at]], got["edges"])
                metrics = structure_metrics(nodes, got["edges"], {n: "1" for n in nodes})
                self.assertEqual(exact(metrics["weighted_critical_path_ms"]), 3 * count // 4)
                self.assertEqual(len(metrics["incomparable_pairs"]), count // 4)

    def test_unsupported_size_duplicate_or_invalid_nodes(self):
        for nodes in ([], ["a"], ["a", "b", "c"], list("abcde"), list("abcdef"), ["a", "a"], ["", "a"]):
            with self.subTest(nodes=nodes), self.assertRaises(ContractError):
                branch_multi(nodes)

    def test_bad_graph_cycle_missing_node_or_output_rejected(self):
        nodes = list("abcd")
        original = branch_multi(nodes)
        for edges, outputs in ((original["edges"] + [["d", "a"]], ["d"]),
                               (original["edges"] + [["d", "x"]], ["x"]),
                               (original["edges"], ["b"])):
            with self.subTest(edges=edges, outputs=outputs), self.assertRaises(TopologyError):
                validate_graph(nodes, edges, outputs, max_indegree=3, max_outdegree=3,
                               layers=None, require_nonchain=False, forbidden_edges=None)

    def test_weighted_critical_path_exact_formula(self):
        nodes = [f"n{i}" for i in range(8)]
        weights = {n: str(i + 1) for i, n in enumerate(nodes)}
        multi = structure_metrics(nodes, branch_multi(nodes)["edges"], weights)
        serial = structure_metrics(nodes, [[a, b] for a, b in zip(nodes, nodes[1:])], weights)
        self.assertEqual(exact(serial["weighted_critical_path_ms"]), 36)
        self.assertEqual(exact(multi["weighted_critical_path_ms"]), 28)
        self.assertEqual(exact(serial["weighted_critical_path_ms"]) - exact(multi["weighted_critical_path_ms"]), 2 + 6)

    def test_serial_tail_multi_and_hand_layered_have_distinct_paths(self):
        nodes = [f"n{i}" for i in range(8)]
        weights = {n: "1" for n in nodes}
        serial = [[a, b] for a, b in zip(nodes, nodes[1:])]
        tail = [["n0", "n1"], ["n0", "n2"], ["n1", "n3"], ["n2", "n3"]] + serial[3:]
        multi = branch_multi(nodes)["edges"]
        layers = [nodes[:3], nodes[3:6], nodes[6:]]
        layered = [[a, b] for left, right in zip(layers, layers[1:]) for a in left for b in right]
        metrics = [structure_metrics(nodes, graph, weights) for graph in (serial, tail, multi, layered)]
        self.assertEqual([m["longest_path_nodes"] for m in metrics], [8, 7, 6, 3])
        self.assertEqual([len(m["incomparable_pairs"]) for m in metrics], [0, 1, 2, 7])
        self.assertTrue(all([a, b] in metrics[3]["incomparable_pairs"]
                            for a, b in (("n0", "n1"), ("n0", "n2"), ("n1", "n2"))))

    def test_s4_only_graph_changes_and_shared_instances_match(self):
        child = derive_branch_multi(self.base["workload"])
        self.assertTrue(validate_adjustment(self.base, child))
        self.assertEqual(child["physical_profiles"], self.base["workload"]["physical_profiles"])
        self.assertEqual(child["time_contract"]["stage_profiles"], self.base["workload"]["time_contract"]["stage_profiles"])
        self.assertEqual(child["time_contract"]["scenarios"][0]["dependencies"],
                         child["time_contract"]["scenarios"][1]["dependencies"])

    def test_s4_small_exception_matches_old_base(self):
        base = manual_evidence(large_nodes=4, small_nodes=2)
        child = derive_branch_multi(base["workload"])
        self.assertTrue(validate_adjustment(base, child))
        for before, after in zip(base["workload"]["time_contract"]["scenarios"], child["time_contract"]["scenarios"]):
            self.assertEqual(before["dependencies"], after["dependencies"])

    def test_s4_rejects_unchanged_hash_relabel_and_mutated_fields(self):
        for field in ("context", "physical_platform", "profile_traces", "weight", "edge"):
            child = derive_branch_multi(self.base["workload"])
            if field == "context":
                child["time_contract"]["context"]["extra"] = True
            elif field == "physical_platform":
                child[field]["external_common_power_W"] = "1"
            elif field == "profile_traces":
                child[field][next(iter(child[field]))]["extra"] = True
            elif field == "weight":
                child["time_contract"]["scenarios"][0]["weight"] = "1/3"
                child["time_contract"]["scenarios"][1]["weight"] = "2/3"
            else:
                child["time_contract"]["scenarios"][0]["dependencies"].append(["L1.s0002.r1", "L1.s0003.r1"])
            stamp(child)
            with self.subTest(field=field), self.assertRaises(ContractError):
                validate_adjustment(self.base, child)

    def test_derived_parent_and_wrong_application_metadata_rejected(self):
        child = derive_branch_multi(self.base["workload"])
        with self.assertRaises(ContractError):
            derive_branch_multi(child)
        wrong = deepcopy(self.base["workload"])
        wrong["applications"]["L1"]["edges"].append(["L1.s0002", "L1.s0003"])
        stamp(wrong)
        with self.assertRaises(ContractError):
            derive_branch_multi(wrong)

    def test_stagger_shifts_both_applications_and_preserves_work(self):
        child = derive_staggered(self.base)
        self.assertTrue(validate_adjustment(self.base, child))
        base = self.base["workload"]
        self.assertEqual(child["time_contract"]["stage_profiles"], base["time_contract"]["stage_profiles"])
        for original, scene in zip(base["time_contract"]["scenarios"], child["time_contract"]["scenarios"]):
            shift = exact(child["transform"]["scene_shifts_ms"][scene["id"]])
            requests = {r["id"]: r for r in scene["requests"]}
            for r in original["requests"]:
                self.assertEqual(requests[r["id"]], r)
                self.assertEqual(exact(requests[r["id"][:-1] + "2"]["release_ms"]) - exact(r["release_ms"]), shift)
            def work(s):
                return sum((exact(base["time_contract"]["stage_profiles"][i["shared_stage_id"]]["work_units"])
                            for i in s["stage_instances"]), Fraction(0))
            self.assertEqual(work(scene), 2 * work(original))

    def test_stagger_does_not_replan_base_h(self):
        with patch("research.chapter3_deadline_reference.scheduler.build_timetable", side_effect=AssertionError("replan")), \
             patch("research.chapter3_deadline_reference.scheduler.choose_mapping", side_effect=AssertionError("remap")):
            child = derive_staggered(self.base)
            self.assertTrue(validate_adjustment(self.base, child))

    def test_half_makespan_rounding_and_per_scene_offsets(self):
        from .transforms import _stagger_metadata
        check = {"completions_ms": {"x": {"a": "80"}, "y": {"a": "8001/100"}, "z": {"a": "83"}},
                 "timetable_hash": "manual"}
        got = _stagger_metadata(self.base["workload"], check)
        self.assertEqual(got["scene_shifts_ms"], {"x": "40", "y": "45", "z": "45"})

    def test_delta_less_than_small_release_has_no_round_barrier(self):
        base = manual_evidence(large_nodes=4, small_nodes=2, offsets=("200",))
        child = derive_staggered(base)
        self.assertTrue(validate_adjustment(base, child))
        scene = child["time_contract"]["scenarios"][0]
        reqs = {r["id"]: r for r in scene["requests"]}
        self.assertLess(exact(reqs["L1.r2"]["release_ms"]), exact(reqs["S1.r1"]["release_ms"]))
        self.assertTrue(all(a.endswith(b[-3:]) for a, b in scene["dependencies"]))

    def test_h_table_check_mapping_and_deadline_provenance_mutations_rejected(self):
        for kind in ("M_table", "check", "mapping", "deadline", "origin"):
            wrong = deepcopy(self.base)
            if kind == "M_table":
                wrong["reference"]["timetables"]["H"] = wrong["reference"]["timetables"]["M"]
            elif kind == "check":
                wrong["reference"]["checks"]["H"]["completions_ms"]["M1"]["L1.r1"] = "999"
            elif kind == "mapping":
                wrong["reference"]["mapping_origin_hash"] = "0" * 64
            elif kind == "deadline":
                wrong["deadlines"]["1"]["requests"]["M1"]["L1.r1"]["deadline_ms"] = "999"
            else:
                receipt = wrong["deadlines"]["1"]
                receipt["origin"]["h_timetable_hash"] = "0" * 64
                receipt["deadline_origin_hash"] = content_hash(receipt["origin"])
                receipt["receipt_hash"] = content_hash({k: v for k, v in receipt.items() if k != "receipt_hash"})
            with self.subTest(kind=kind), self.assertRaises(ContractError):
                derive_staggered(wrong)

    def test_stagger_mutations_rejected_and_old_sync_validator_stays_strict(self):
        good = derive_staggered(self.base)
        with self.assertRaises(ContractError):
            validate_transform(self.base["workload"], good)
        for kind in ("shift", "metadata", "extra_edge", "first_release", "profile"):
            child = deepcopy(good)
            scene = child["time_contract"]["scenarios"][0]
            reqs = {r["id"]: r for r in scene["requests"]}
            if kind == "shift":
                reqs["S1.r2"]["release_ms"] = str(exact(reqs["S1.r2"]["release_ms"]) + 5)
            elif kind == "metadata":
                child["transform"]["fraction"] = "1/3"
            elif kind == "extra_edge":
                scene["dependencies"].append(["L1.s0008.r1", "L1.s0001.r2"])
            elif kind == "first_release":
                reqs["L1.r1"]["release_ms"] = "5"
            else:
                sid = next(iter(child["time_contract"]["stage_profiles"]))
                child["time_contract"]["stage_profiles"][sid]["work_units"] = "99"
                child["physical_profiles"][sid]["work_units"] = "99"
            stamp(child)
            with self.subTest(kind=kind), self.assertRaises(ContractError):
                validate_adjustment(self.base, child)

    def test_all_betas_inherit_without_new_deadline_fit(self):
        for child in (derive_branch_multi(self.base["workload"]), derive_staggered(self.base)):
            base = self.base["workload"]
            for key, receipt in self.base["deadlines"].items():
                new = inherit_deadlines(base["time_contract"], receipt, child["time_contract"],
                                        request_sources=request_sources(base, child))
                self.assertEqual(new["deadline_origin_hash"], receipt["deadline_origin_hash"])
                for sid, rows in receipt["requests"].items():
                    for rid, row in rows.items():
                        self.assertEqual(new["requests"][sid][rid], row)
                        if child["transform"]["axis"] == "S7":
                            copied = new["requests"][sid][rid[:-1] + "2"]
                            self.assertEqual(copied["relative_deadline_ms"], row["relative_deadline_ms"])
                            self.assertEqual(exact(copied["deadline_ms"]) - exact(row["deadline_ms"]),
                                             exact(child["transform"]["scene_shifts_ms"][sid]))

    def test_manual_derived_hml_checked_with_original_mapping(self):
        mapping = self.base["reference"]["mapping_record"]["mapping"]
        for child in (derive_branch_multi(self.base["workload"]), derive_staggered(self.base)):
            for opp in ("H", "M", "L"):
                table = build_timetable(child["time_contract"], mapping, opp)
                checked = check_timetable(child["time_contract"], table, required_opp=opp)
                self.assertEqual(checked["state"], "TIME_STRUCTURAL_VALID")
                self.assertEqual(checked["shared_deployment"], mapping)


if __name__ == "__main__":
    unittest.main()
