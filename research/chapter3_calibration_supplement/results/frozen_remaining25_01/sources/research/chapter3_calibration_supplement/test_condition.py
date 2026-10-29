"""Hand-authored supplemental condition fixtures; never read or run C roots."""

from copy import deepcopy
from fractions import Fraction
import unittest
from unittest.mock import patch

from research.chapter3_deadline_reference.contract import ContractError
from research.chapter3_calibration_adjustment.fixtures import manual_evidence
from research.chapter3_workload_calibration.generator import stamp, transform
from research.chapter3_workload_calibration.evaluation import evaluate_condition
from .condition import evaluate_supplement, BETAS, BETA_KEYS, EMPTY_COUNTERS


def _manual_topology(parent, topology):
    """Explicit 8/4-node graphs; no random generator or new physical profiles."""
    bundle = deepcopy(parent)
    data = bundle["time_contract"]
    data.update(variant_id="manual-s4-" + topology, topology_id=topology,
                derivation={"axis": "S4", "parent_contract_hash": parent["contract_hash"]})
    bundle["transform"] = {"axis": "S4", "parent_bundle_hash": parent["bundle_hash"]}
    layers = {8: [[0, 1, 2], [3, 4, 5], [6, 7]], 4: [[0, 1], [2, 3]]}
    edges = {8: [(0, 3), (0, 4), (1, 4), (1, 5), (2, 5),
                 (3, 6), (4, 6), (4, 7), (5, 7)],
             4: [(0, 2), (0, 3), (1, 2), (1, 3)]}
    for spec in bundle["applications"].values():
        nodes = spec["nodes"]
        graph = ([[a, b] for a, b in zip(nodes, nodes[1:])] if topology == "serial"
                 else [[nodes[a], nodes[b]] for a, b in edges[len(nodes)]])
        outputs = [nodes[-1]] if topology == "serial" else [nodes[i] for i in layers[len(nodes)][-1]]
        spec.update(edges=sorted(graph), required_outputs=outputs,
                    trace={"manual_fixed_edges": True, "random_generation": False})
    for scene in data["scenarios"]:
        scene["dependencies"] = sorted([[a + ".r1", b + ".r1"] for req in scene["requests"]
                                        for a, b in bundle["applications"][req["id"][:-3]]["edges"]])
    return stamp(bundle)


def manual_case(axis):
    parent = manual_evidence()
    root = parent["workload"]["provenance"]["root_id"]
    scale = parent["workload"]["provenance"]["scale"]
    parent_id = f"{root}__base_{scale}"
    parent["call"] = {"condition_id": parent_id}
    rule = "branch_multi_v1" if axis == "S4" else "staggered_half_base_H_v1"
    ids = [root + "__S4_serial", root + "__S4_layered"] if axis == "S4" else [root + "__S7"]
    call = {"condition_id": root + "__" + axis + "_" + rule, "root_id": root,
            "scale": scale, "axis": axis, "rule": rule, "parent_id": parent_id,
            "comparison_ids": ids}
    if axis == "S4":
        bundles = [_manual_topology(parent["workload"], topology) for topology in ("serial", "layered")]
    else:
        bundles = [transform(parent["workload"], "S7", value=2,
                             settings={"s7_release_rule": "synchronous_same_application"})]
    comparisons = {}
    for name, bundle in zip(ids, bundles):
        evidence = evaluate_condition(bundle, {"betas": list(BETAS)}, parent=parent,
                                       progress=lambda *args: None)
        evidence["call"] = {"condition_id": name}
        comparisons[name] = evidence
    return call, parent, comparisons


class ConditionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {axis: manual_case(axis) for axis in ("S4", "S7")}

    def run_case(self, axis):
        call, parent, comparisons = deepcopy(self.cases[axis])
        before = deepcopy((parent, comparisons))
        phases = []
        with patch("research.chapter3_workload_calibration.evaluation.choose_mapping",
                   side_effect=AssertionError("must inherit mapping")):
            result = evaluate_supplement(call, parent, comparisons,
                                         progress=lambda p, c: phases.append((p, deepcopy(c))))
        self.assertEqual((parent, comparisons), before)
        self.assertEqual(result["counters"], {**EMPTY_COUNTERS, "timetable_constructions": 3})
        self.assertEqual(set(result["window_receipts"]), set(BETA_KEYS))
        self.assertEqual(result["state"], "TIME_CALIBRATION_COMPLETE")
        self.assertIsNone(result["beta_selected"])
        self.assertEqual(result["thermal_status"], "NOT_EVALUATED")
        self.assertEqual(result["energy_status"], "NOT_EVALUATED")
        self.assertEqual(phases[-1][0], "SUPPLEMENT_COMPLETE")
        return call, parent, result

    def test_s4_exactly_three_new_tables_and_shared_four_beta_windows(self):
        call, parent, result = self.run_case("S4")
        self.assertEqual(result["workload"]["time_contract"]["topology_id"], "branch_multi_v1")
        self.assertEqual(result["reference"]["mapping_origin_hash"], parent["reference"]["mapping_origin_hash"])
        for beta in BETA_KEYS:
            self.assertEqual(result["deadlines"][beta]["requests"], parent["deadlines"][beta]["requests"])
            receipt = result["window_receipts"][beta]
            self.assertEqual(set(receipt["members"]), {"serial", "branch_multi", "layered"})
            self.assertEqual({m["window_ms"] for m in receipt["members"].values()}, {receipt["window_ms"]})

    def test_s7_keeps_original_requests_and_new_relative_deadlines(self):
        call, parent, result = self.run_case("S7")
        shifts = result["workload"]["transform"]["scene_shifts_ms"]
        self.assertEqual(shifts, {"M1": "35", "M2": "30"})
        for beta in BETA_KEYS:
            for scene, requests in parent["deadlines"][beta]["requests"].items():
                for rid, old in requests.items():
                    rows = result["deadlines"][beta]["requests"][scene]
                    self.assertEqual(rows[rid], old)
                    copied = rows[rid[:-1] + "2"]
                    self.assertEqual(copied["relative_deadline_ms"], old["relative_deadline_ms"])
                    self.assertEqual(Fraction(copied["deadline_ms"]) - Fraction(old["deadline_ms"]),
                                     Fraction(shifts[scene]))
            self.assertEqual(set(result["window_receipts"][beta]["members"]),
                             {"single", "synchronous", "staggered"})

    def test_deadline_misses_are_results_not_constructor_failure(self):
        _, _, result = self.run_case("S7")
        self.assertFalse(result["metrics"]["1"]["L"]["all_on_time"])
        self.assertTrue(any(not row["on_time"] for row in result["metrics"]["1"]["L"]["requests"]))

    def test_call_and_parent_identity_fail_before_construction(self):
        for field, replacement in (("root_id", "wrong-root"), ("scale", 24), ("rule", "wrong"),
                                    ("parent_id", "other-base")):
            call, parent, comparisons = deepcopy(self.cases["S4"])
            call[field] = replacement
            with self.subTest(field=field), patch(
                    "research.chapter3_calibration_supplement.condition.evaluate_condition",
                    side_effect=AssertionError("no construction allowed")), self.assertRaises(ContractError):
                evaluate_supplement(call, parent, comparisons, progress=lambda *args: None)

    def test_missing_or_misidentified_comparison_rejected(self):
        for alteration in ("missing", "identity", "topology"):
            call, parent, comparisons = deepcopy(self.cases["S4"])
            first = call["comparison_ids"][0]
            if alteration == "missing":
                del comparisons[first]
            elif alteration == "identity":
                comparisons[first]["call"]["condition_id"] = "different"
            else:
                comparisons[first] = deepcopy(comparisons[call["comparison_ids"][1]])
                comparisons[first]["call"]["condition_id"] = first
            with self.subTest(alteration=alteration), patch(
                    "research.chapter3_calibration_supplement.condition.evaluate_condition",
                    side_effect=AssertionError("no construction allowed")), self.assertRaises(ContractError):
                evaluate_supplement(call, parent, comparisons, progress=lambda *args: None)

    def test_four_betas_and_original_h_required(self):
        for alteration in ("missing_beta", "wrong_h_check"):
            call, parent, comparisons = deepcopy(self.cases["S7"])
            if alteration == "missing_beta":
                del parent["deadlines"]["8/5"]
            else:
                parent["reference"]["checks"]["H"]["completions_ms"]["M1"]["L1.r1"] = "99999"
            with self.subTest(alteration=alteration), patch(
                    "research.chapter3_calibration_supplement.condition.evaluate_condition",
                    side_effect=AssertionError("no construction allowed")), self.assertRaises(ContractError):
                evaluate_supplement(call, parent, comparisons, progress=lambda *args: None)

    def test_checkpoint_timeout_does_not_construct_or_return_complete(self):
        call, parent, comparisons = deepcopy(self.cases["S7"])
        seen = []

        def stop(phase, counters):
            seen.append(phase)
            if phase == "SUPPLEMENT_TRANSFORM_VALIDATED":
                raise TimeoutError("manual-budget-expired")

        with patch("research.chapter3_calibration_supplement.condition.evaluate_condition",
                   side_effect=AssertionError("no construction after timeout")), self.assertRaises(TimeoutError):
            evaluate_supplement(call, parent, comparisons, progress=stop)
        self.assertNotIn("SUPPLEMENT_COMPLETE", seen)


if __name__ == "__main__":
    unittest.main()
