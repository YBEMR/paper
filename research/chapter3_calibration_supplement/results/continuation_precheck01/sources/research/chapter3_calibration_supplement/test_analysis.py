"""Hand-written diagnostic receipts; no timetable constructors or real roots."""

from copy import deepcopy
from fractions import Fraction
import unittest

from .analysis import BETAS, OPPS, summarize_condition, aggregate_summaries


def manual_evidence(role, responses, *, doubled=False, staggered=False):
    root = "manual-analysis"
    scenes, deadlines, checks = [], {b: {"beta": b, "requests": {}, "deadline_origin_hash": "manual-origin-" + b,
                                        "receipt_hash": "manual-receipt-" + role + b} for b in BETAS}, {}
    for sid in ("M1", "M2"):
        releases = {"A.r1": Fraction(0)}
        if doubled:
            releases["A.r2"] = Fraction(20 if staggered else 0)
        scenes.append({"id": sid, "requests": [{"id": rid, "release_ms": str(release)}
                                                 for rid, release in releases.items()]})
        for beta in BETAS:
            deadlines[beta]["requests"][sid] = {
                rid: {"release_ms": str(release), "relative_deadline_ms": str(Fraction(beta) * 10),
                      "deadline_ms": str(release + Fraction(beta) * 10)} for rid, release in releases.items()}
    for opp in OPPS:
        checks[opp] = {"state": "TIME_STRUCTURAL_VALID", "timetable_hash": "manual-table-" + role + opp,
                       "completions_ms": {s["id"]: {r["id"]: str(Fraction(r["release_ms"]) +
                                                               Fraction(responses.get((opp, r["id"]), responses[opp])))
                                                            for r in s["requests"]} for s in scenes}}
    nodes = ["A.s" + str(i) for i in range(8)]
    if role == "serial":
        edges = [[a, b] for a, b in zip(nodes, nodes[1:])]
    elif role == "branch_multi":
        edges = [[nodes[a], nodes[b]] for a, b in ((0, 1), (0, 2), (1, 3), (2, 3),
                                                  (3, 4), (4, 5), (4, 6), (5, 7), (6, 7))]
    elif role == "layered":
        edges = [[nodes[a], nodes[b]] for a, b in ((0, 3), (0, 4), (1, 4), (1, 5),
                                                  (2, 5), (3, 6), (4, 6), (4, 7), (5, 7))]
    else:
        edges = [[nodes[a], nodes[b]] for a, b in ((0, 1), (0, 2), (1, 3), (2, 3),
                                                  (3, 4), (4, 5), (5, 6), (6, 7))]
    return {"state": "TIME_CALIBRATION_COMPLETE", "beta_selected": None,
            "thermal_status": "NOT_EVALUATED", "energy_status": "NOT_EVALUATED",
            "workload": {"contract_hash": "manual-contract-" + role,
                         "time_contract": {"root_family_id": root, "topology_id": role, "scenarios": scenes},
                         "provenance": {"root_id": root, "scale": 8},
                         "applications": {"A": {"nodes": nodes, "edges": edges}}},
            "reference": {"mapping_origin_hash": "manual-mapping", "checks": checks}, "deadlines": deadlines,
            "metrics": {"deliberately_stale": "must be recomputed from checked completions"}}


def manual_case(axis="S4", new_response="12", old_response="14"):
    call = {"condition_id": "manual-" + axis, "root_id": "manual-analysis", "scale": 8,
            "axis": axis, "parent_id": "manual-base", "rule": "manual-fixture",
            "comparison_ids": ["manual-serial", "manual-layered"] if axis == "S4" else ["manual-sync"]}
    parent = manual_evidence("branch_join", dict.fromkeys(OPPS, old_response))
    comparisons = {call["parent_id"]: parent}
    if axis == "S4":
        evidence = manual_evidence("branch_multi", dict.fromkeys(OPPS, new_response))
        comparisons.update({"manual-serial": manual_evidence("serial", dict.fromkeys(OPPS, old_response)),
                            "manual-layered": manual_evidence("layered", dict.fromkeys(OPPS, old_response))})
    else:
        evidence = manual_evidence("staggered", dict.fromkeys(OPPS, new_response), doubled=True, staggered=True)
        comparisons["manual-sync"] = manual_evidence("synchronous", dict.fromkeys(OPPS, old_response), doubled=True)
    return call, evidence, comparisons


class SummaryTests(unittest.TestCase):
    def test_four_betas_three_opps_and_exact_deadline_boundary(self):
        call, new, old = manual_case(new_response="13")
        result = summarize_condition(call, new, old)
        self.assertEqual(tuple(result["by_beta"]), BETAS)
        self.assertEqual(tuple(result["by_beta"]["1"]), OPPS)
        metrics = result["by_beta"]["13/10"]["H"]["roles"]["branch_multi"]
        self.assertTrue(metrics["family_all_on_time"])
        self.assertEqual(metrics["minimum_eta"], "0")
        self.assertEqual(metrics["request_on_time_rate"], "1")
        self.assertFalse(result["by_beta"]["1"]["H"]["roles"]["branch_multi"]["family_all_on_time"])
        self.assertIsNone(result["beta_selected"])

    def test_s4_pair_improves_and_structure_is_dependency_only(self):
        call, new, old = manual_case()
        result = summarize_condition(call, new, old)
        pair = result["by_beta"]["13/10"]["H"]["paired"]["branch_join"]
        self.assertEqual(pair["family_all_on_time_change"], "improved")
        self.assertEqual(pair["scene_status_changes"], {"improved": 2, "unchanged": 0, "worsened": 0})
        self.assertEqual(pair["request_slack_changes"]["improved"], 2)
        structures = result["structure_by_role"]
        self.assertEqual([structures[r]["applications"]["A"]["longest_path_nodes"]
                          for r in ("serial", "branch_join", "branch_multi", "layered")], [8, 7, 6, 3])

    def test_s7_improvement_uses_response_not_absolute_finish(self):
        call, new, old = manual_case("S7", new_response="12", old_response="18")
        result = summarize_condition(call, new, old)
        row = result["by_beta"]["13/10"]["H"]
        current = row["roles"]["staggered"]["scenes"]["M1"]["requests"]["A.r2"]
        previous = row["roles"]["synchronous"]["scenes"]["M1"]["requests"]["A.r2"]
        self.assertGreater(Fraction(current["finish_ms"]), Fraction(previous["finish_ms"]))
        self.assertEqual(row["paired"]["synchronous"]["family_all_on_time_change"], "improved")
        delta = row["paired"]["synchronous"]["scenes"]["M1"]["requests"]["A.r2"]
        self.assertEqual(delta["response_change_ms"], "-6")
        self.assertEqual(delta["slack_change_ms"], "6")
        self.assertEqual(set(row["paired"]), {"synchronous"})

    def test_both_overdue_can_have_slack_improvement_without_status_gain(self):
        call, new, old = manual_case("S7", new_response="28", old_response="30")
        pair = summarize_condition(call, new, old)["by_beta"]["13/10"]["H"]["paired"]["synchronous"]
        self.assertEqual(pair["family_all_on_time_change"], "unchanged")
        self.assertEqual(pair["request_status_changes"]["unchanged"], 4)
        self.assertEqual(pair["request_slack_changes"]["improved"], 4)

    def test_worsening_and_exact_equality_preserved(self):
        for new_response, expected in (("22", "worsened"), ("12", "unchanged")):
            call, new, old = manual_case(new_response=new_response, old_response="12")
            pair = summarize_condition(call, new, old)["by_beta"]["13/10"]["H"]["paired"]["serial"]
            self.assertEqual(pair["family_all_on_time_change"], expected)

    def test_missing_beta_or_completion_rejected_not_overdue(self):
        call, new, old = manual_case()
        altered = deepcopy(new)
        del altered["deadlines"]["2"]
        with self.assertRaisesRegex(ValueError, "BETA_COVERAGE"):
            summarize_condition(call, altered, old)
        altered = deepcopy(new)
        del altered["reference"]["checks"]["H"]["completions_ms"]["M1"]["A.r1"]
        with self.assertRaisesRegex(ValueError, "REQUEST_COMPLETION_COVERAGE"):
            summarize_condition(call, altered, old)

    def test_relative_deadline_or_origin_drift_rejected(self):
        call, new, old = manual_case("S7")
        altered = deepcopy(new)
        altered["deadlines"]["1"]["requests"]["M1"]["A.r2"]["relative_deadline_ms"] = "11"
        altered["deadlines"]["1"]["requests"]["M1"]["A.r2"]["deadline_ms"] = "31"
        with self.assertRaisesRegex(ValueError, "PAIR_RELATIVE"):
            summarize_condition(call, altered, old)
        altered = deepcopy(new)
        altered["reference"]["mapping_origin_hash"] = "different"
        with self.assertRaisesRegex(ValueError, "MAPPING_ORIGIN"):
            summarize_condition(call, altered, old)

    def test_partial_aggregate_preserves_missing_and_error_states(self):
        call, new, old = manual_case()
        summary = summarize_condition(call, new, old)
        planned = [call] + [{**call, "condition_id": "manual-" + str(i)} for i in range(3)]
        result = aggregate_summaries(planned, [
            {"condition_id": call["condition_id"], "state": "COMPLETE", "summary": summary},
            {"condition_id": "manual-0", "state": "TIMEOUT_OR_LATE"},
            {"condition_id": "manual-1", "state": "FAILED"}])
        self.assertEqual(result["state"], "PARTIAL")
        self.assertEqual(result["usable_conditions"], 1)
        self.assertEqual(result["planned_existing_roots"], 1)
        self.assertEqual(result["condition_status_counts"],
                         {"COMPLETE": 1, "TIMEOUT_OR_LATE": 1, "FAILED": 1, "NOT_RUN": 1})
        metric = result["by_axis"]["S4"]["all_scales"]["by_beta"]["13/10"]["H"]["roles"]["branch_multi"]
        self.assertEqual(metric["conditions"], 1)
        self.assertEqual(metric["family_on_time_rate"], "1")

    def test_complete_without_valid_summary_excluded(self):
        call, new, old = manual_case()
        summary = summarize_condition(call, new, old)
        summary["by_beta"]["13/10"]["H"]["roles"]["branch_multi"]["family_all_on_time"] = False
        result = aggregate_summaries([call], [{"condition_id": call["condition_id"],
                                             "state": "COMPLETE", "summary": summary}])
        self.assertEqual(result["usable_conditions"], 0)
        self.assertEqual(result["condition_status_counts"], {"INCOMPLETE_OR_INVALID_SUMMARY": 1})
        self.assertEqual(result["by_axis"]["S4"]["all_scales"]["by_beta"]["1"]["H"]["roles"], {})

    def test_unknown_duplicate_and_incomplete_inputs_rejected(self):
        call, new, old = manual_case()
        row = {"condition_id": call["condition_id"], "state": "FAILED"}
        with self.assertRaises(ValueError):
            aggregate_summaries([call], [row, row])
        with self.assertRaises(ValueError):
            aggregate_summaries([call], [{"condition_id": "wrong", "state": "FAILED"}])
        new["state"] = "PARTIAL"
        with self.assertRaisesRegex(ValueError, "INCOMPLETE_TIME_EVIDENCE"):
            summarize_condition(call, new, old)

    def test_all_results_available_yields_complete_aggregate_without_beta_choice(self):
        s4, new4, old4 = manual_case()
        s7, new7, old7 = manual_case("S7", "14", "12")
        results = [summarize_condition(s4, new4, old4), summarize_condition(s7, new7, old7)]
        batch = aggregate_summaries([s4, s7], [{"condition_id": r["condition"]["condition_id"],
                                              "state": "COMPLETE", "summary": r} for r in results])
        self.assertEqual(batch["state"], "COMPLETE")
        self.assertEqual(batch["usable_existing_roots"], 1)
        self.assertEqual(batch["usable_conditions"], 2)
        self.assertIsNone(batch["beta_selected"])
        self.assertEqual(batch["by_axis"]["S7"]["all_scales"]["by_beta"]["13/10"]["L"]["paired"]
                         ["synchronous"]["families"]["worsened"], 1)


if __name__ == "__main__":
    unittest.main()
