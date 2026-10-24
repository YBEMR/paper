"""Independent artificial graph and finite-start checks for blocking repair.

All inputs below are small invented schedules.  Existing fixture construction
and its independent resource oracle are reused unchanged.  The Cartesian
oracle enumerates only these tiny grids, never a research problem.  No HEFT,
optimizer, native process, physical evaluator or thermal integration is used.
"""
from copy import deepcopy
from fractions import Fraction as F
from itertools import product
import unittest

from research.chapter4_scheduler.tests.test_graph_core import (
    fixture, rows, selected_mode, independent_legality, Budget, BudgetExpired)
from research.chapter4_scheduler.blocking.core import reconstruct, blocking_edges


def artificial(specs, *, dependencies=(), window="12", second_scene=False):
    instance, candidate = fixture(specs, dependencies=dependencies,
        window=window, second_scene=second_scene)
    instance["id"] = "artificial_cross_resource_blocking"
    instance["start_grid_ms"] = "1"
    return instance, candidate


def crossing_fixture(*, second_scene=False):
    # Old legal order: b->a on NPU and v->u on CPU.  Changing both NPU
    # durations and reversing only their order makes u miss its deadline.
    return artificial([
        {"id": "a", "unit": "NPU0", "opp": "H", "duration_H": "2",
         "duration_L": "3", "start": "2"},
        {"id": "b", "unit": "NPU0", "opp": "H", "duration_H": "2",
         "duration_L": "6", "start": "0"},
        {"id": "u", "unit": "CPU1", "duration": "1", "start": "4", "deadline": "8"},
        {"id": "v", "unit": "CPU1", "duration": "1", "start": "2"}],
        dependencies=[("a", "u"), ("b", "v")], second_scene=second_scene)


def action(instance, candidate, **kwargs):
    return reconstruct(instance, candidate, "S0", ["a", "b"],
        {"a": "L", "b": "L"}, orientation="reverse", **kwargs)


def finite_oracle(instance, candidate, fixed_orders):
    """Independent exact grid oracle, including all resource and task rules.

    The fixture has at most four tasks and a 12 ms domain, so enumerating
    all start combinations is bounded. No graph implementation is consulted.
    """
    scene = instance["scenarios"][0]
    entries = rows(candidate)
    ids = sorted(entries)
    requests = {r["id"]: r for r in scene["requests"]}
    request_for = {s["id"]: requests[s["request_id"]] for s in scene["stage_instances"]}
    modes = {iid: selected_mode(instance, entries[iid]) for iid in ids}
    durations = {iid: F(modes[iid]["duration_ms"]) for iid in ids}
    choices = range(0, int(F(instance["window_ms"])) + 1)
    feasible = []
    for starts in product(choices, repeat=len(ids)):
        times = dict(zip(ids, map(F, starts)))
        ends = {iid: times[iid] + durations[iid] for iid in ids}
        if any(times[iid] < F(request_for[iid]["release_ms"]) or
               ends[iid] > min(F(request_for[iid]["deadline_ms"]), F(instance["window_ms"]))
               for iid in ids):
            continue
        if any(ends[a] > times[b] for a, b in scene["dependencies"] + list(fixed_orders)):
            continue
        conflict = False
        for index, left in enumerate(ids):
            for right in ids[index + 1:]:
                overlap = max(times[left], times[right]) < min(ends[left], ends[right])
                if overlap and (entries[left]["unit"] == entries[right]["unit"] or
                    modes[left]["domain_id"] == modes[right]["domain_id"] and
                    entries[left]["opp"] != entries[right]["opp"]):
                    conflict = True
        if not conflict:
            feasible.append(times)
    return feasible


class BlockingCoreTests(unittest.TestCase):
    def accepted(self, packet, instance):
        self.assertEqual(packet["state"], "COMPLETE_LEGAL_CANDIDATE", packet)
        self.assertTrue(independent_legality(instance, packet["candidate"]))
        self.assertEqual(packet.get("deadline_violations"), [])
        self.assertNotIn("safe_upper_bound_J", packet)
        self.assertNotEqual(packet.get("thermal_status"), "SAFE")
        return rows(packet["candidate"])

    def rejected(self, packet, reason=None):
        self.assertEqual(packet["state"], "RECONSTRUCTION_REJECTED", packet)
        self.assertIsNone(packet.get("candidate"))
        if reason is not None:
            self.assertEqual(packet.get("reason"), reason, packet)

    def test_cross_resource_extra_edge_is_required_by_independent_grid_oracle(self):
        instance, incumbent = crossing_fixture()
        self.assertTrue(independent_legality(instance, incumbent))
        changed = deepcopy(incumbent)
        for iid in ("a", "b"):
            rows(changed)[iid]["opp"] = "L"
        original_order = finite_oracle(instance, changed, [("a", "b"), ("v", "u")])
        repaired_order = finite_oracle(instance, changed, [("a", "b"), ("u", "v")])
        self.assertEqual(original_order, [])
        self.assertTrue(repaired_order)
        base = action(instance, incumbent)
        self.rejected(base, "SKELETON_DEADLINE_OR_WINDOW_EXCEEDED")
        self.assertEqual(F(base["end_ms"]["u"]), 11)
        self.assertEqual(blocking_edges(base), [("v", "u")])
        repaired = action(instance, incumbent, extra_resource_edge=("v", "u"))
        result = self.accepted(repaired, instance)
        expected = {"a": F(0), "b": F(3), "u": F(3), "v": F(9)}
        self.assertEqual({iid: F(row["start_ms"]) for iid, row in result.items()}, expected)
        self.assertTrue(all(all(expected[iid] <= other[iid] for iid in expected)
            for other in repaired_order))
        self.assertEqual(repaired["additional_reversed_edges"], [["v", "u"]])

    def test_no_extra_preserves_original_resource_direction_and_all_diagnostics(self):
        instance, incumbent = crossing_fixture()
        packet = action(instance, incumbent)
        self.rejected(packet)
        self.assertEqual(packet["additional_reversed_edges"], [])
        self.assertEqual(packet["critical_predecessors"]["u"], "v")
        violation = next(v for v in packet["deadline_violations"] if v["stage_id"] == "u")
        self.assertEqual(F(violation["deadline_ms"]), 8)
        self.assertEqual(F(violation["end_ms"]), 11)
        self.assertEqual(F(violation["lateness_ms"]), 3)
        trace = next(t for t in packet["blocking_traces"] if t["stage_id"] == "u")
        self.assertEqual(trace["chain"], ["a", "b", "v", "u"])

    def test_all_late_requests_are_recorded_not_first_failure_only(self):
        instance, incumbent = crossing_fixture()
        extra_i, extra_c = artificial([{"id": "z", "unit": "GPU0", "duration": "1",
            "start": "2", "deadline": "5"}])
        instance["stage_modes"]["z"] = extra_i["stage_modes"]["z"]
        for key in ("stage_instances", "requests"):
            instance["scenarios"][0][key].extend(extra_i["scenarios"][0][key])
        instance["scenarios"][0]["dependencies"].append(["b", "z"])
        incumbent["scenes"]["S0"].extend(extra_c["scenes"]["S0"])
        self.assertTrue(independent_legality(instance, incumbent))
        packet = action(instance, incumbent)
        self.assertEqual({v["stage_id"] for v in packet["deadline_violations"]}, {"u", "z"})
        self.assertEqual({t["stage_id"] for t in packet["blocking_traces"]}, {"u", "z"})
        self.assertEqual(set(packet["end_ms"]), {"a", "b", "u", "v", "z"})

    def test_one_extra_edge_does_not_recursively_repair_remaining_deadline(self):
        instance, incumbent = crossing_fixture()
        for mode in instance["stage_modes"]["a"]:
            if mode["opp_id"] == "L":
                mode["duration_ms"] = "10"
        packet = action(instance, incumbent, extra_resource_edge=("v", "u"))
        self.rejected(packet)
        self.assertEqual(packet["additional_reversed_edges"], [["v", "u"]])
        self.assertIn("u", {v["stage_id"] for v in packet["deadline_violations"]})

    def test_main_pair_resource_edge_is_not_an_extra_edge(self):
        instance, incumbent = crossing_fixture()
        packet = action(instance, incumbent)
        self.assertNotIn(("a", "b"), blocking_edges(packet))
        self.rejected(action(instance, incumbent, extra_resource_edge=("a", "b")),
            "EXTRA_EDGE_NOT_CERTIFIED_BLOCKING")

    def test_extra_edge_must_use_original_certified_direction(self):
        instance, incumbent = crossing_fixture()
        self.rejected(action(instance, incumbent, extra_resource_edge=("u", "v")),
            "EXTRA_EDGE_NOT_CERTIFIED_BLOCKING")

    def test_arbitrary_unrelated_extra_edge_is_rejected(self):
        instance, incumbent = crossing_fixture()
        self.rejected(action(instance, incumbent, extra_resource_edge=("a", "u")),
            "EXTRA_EDGE_NOT_CERTIFIED_BLOCKING")

    def test_extra_shape_rejects_multiple_edges_or_non_stage_scalars(self):
        instance, incumbent = crossing_fixture()
        for extra in ([], "v,u", ("v",), ("v", "u", "a"), ("v", 1),
                      (("v", "u"), ("a", "b")), ("v", "v")):
            with self.subTest(extra=extra):
                self.rejected(action(instance, incumbent, extra_resource_edge=extra),
                    "INVALID_EXTRA_RESOURCE_EDGE")

    def test_task_plus_resource_same_edge_cannot_be_reversed(self):
        instance, incumbent = artificial([
            {"id": "a", "unit": "NPU0", "opp": "H", "duration_H": "2", "duration_L": "6"},
            {"id": "b", "unit": "NPU0", "duration": "2", "start": "2", "deadline": "5"}],
            dependencies=[("a", "b")])
        packet = reconstruct(instance, incumbent, "S0", ["a"], {"a": "L"})
        self.rejected(packet)
        edge = next(e for e in packet["edges"] if e["from"] == "a" and e["to"] == "b")
        self.assertEqual(set(edge["reasons"]), {"same_unit", "task_dependency"})
        self.assertEqual(blocking_edges(packet), [])
        self.rejected(reconstruct(instance, incumbent, "S0", ["a"], {"a": "L"},
            extra_resource_edge=("a", "b")), "EXTRA_EDGE_NOT_CERTIFIED_BLOCKING")

    def test_main_reversal_cycle_is_not_reclassified_as_deadline_repair(self):
        instance, incumbent = artificial([
            {"id": "a", "unit": "NPU0", "duration": "2"},
            {"id": "b", "unit": "NPU0", "duration": "2", "start": "2"}],
            dependencies=[("a", "b")])
        packet = reconstruct(instance, incumbent, "S0", ["a", "b"], {}, orientation="reverse")
        self.rejected(packet, "SKELETON_DIRECTED_CYCLE")
        self.assertEqual(blocking_edges(packet), [])
        self.rejected(reconstruct(instance, incumbent, "S0", ["a", "b"], {},
            orientation="reverse", extra_resource_edge=("a", "b")),
            "EXTRA_EDGE_NOT_CERTIFIED_BLOCKING")

    def test_equal_max_predecessors_choose_lexical_identity_stably(self):
        instance, incumbent = artificial([
            {"id": "x", "unit": "GPU0", "duration": "3"},
            {"id": "y", "unit": "CPU1", "duration": "3"},
            {"id": "z", "unit": "NPU0", "opp": "H", "duration_H": "1",
             "duration_L": "2", "start": "3", "deadline": "4"}],
            dependencies=[("y", "z"), ("x", "z")])
        first = reconstruct(instance, incumbent, "S0", ["z"], {"z": "L"})
        modified = deepcopy(instance)
        modified["scenarios"][0]["dependencies"].reverse()
        modified["scenarios"][0]["stage_instances"].reverse()
        second = reconstruct(modified, incumbent, "S0", ["z"], {"z": "L"})
        self.assertEqual(first["critical_predecessors"]["z"], "x")
        self.assertEqual(first["blocking_traces"], second["blocking_traces"])
        self.assertEqual(first["blocking_traces"][0]["chain"], ["x", "z"])

    def test_release_dominating_predecessor_stops_trace_including_tie(self):
        for release, deadline in (("5", "9"), ("2", "6")):
            instance, incumbent = artificial([
                {"id": "a", "unit": "GPU0", "duration": "2"},
                {"id": "x", "unit": "CPU1", "opp": "H", "duration_H": "2",
                 "duration_L": "5", "release": release, "start": release},
                {"id": "y", "unit": "CPU1", "duration": "1",
                 "start": str(F(release) + 2), "deadline": deadline}],
                dependencies=[("a", "x")])
            packet = reconstruct(instance, incumbent, "S0", ["x"], {"x": "L"})
            self.rejected(packet)
            trace = next(t for t in packet["blocking_traces"] if t["stage_id"] == "y")
            self.assertEqual(trace["chain"], ["x", "y"])
            self.assertEqual(trace["stop_stage_id"], "x")
            self.assertEqual(trace["stop_reason"], "RELEASE_OR_FLOOR")
            self.assertIsNone(packet["critical_predecessors"]["x"])

    def test_preserved_start_floor_stops_trace_at_unselected_stage(self):
        instance, incumbent = artificial([
            {"id": "a", "unit": "GPU0", "duration": "2"},
            {"id": "x", "unit": "CPU1", "duration": "5", "start": "5"},
            {"id": "y", "unit": "CPU1", "opp": "H", "duration_H": "1",
             "duration_L": "3", "start": "10", "deadline": "12"}],
            dependencies=[("a", "x")], window="20")
        preserved = reconstruct(instance, incumbent, "S0", ["y"], {"y": "L"}, template="preserve")
        self.rejected(preserved)
        trace = next(t for t in preserved["blocking_traces"] if t["stage_id"] == "y")
        self.assertEqual(trace["chain"], ["x", "y"])
        self.assertEqual(trace["stop_reason"], "RELEASE_OR_FLOOR")
        self.assertIsNone(preserved["critical_predecessors"]["x"])
        self.accepted(reconstruct(instance, incumbent, "S0", ["y"], {"y": "L"}), instance)

    def test_explicit_start_subset_and_noninteger_finish_are_preserved(self):
        instance, incumbent = artificial([
            {"id": "a", "unit": "CPU1", "opp": "H", "duration_H": "1", "duration_L": "5/2"},
            {"id": "b", "unit": "NPU0", "duration": "1", "start": "2", "deadline": "5"}],
            dependencies=[("a", "b")], window="6")
        instance["start_domain"] = {"version": 1, "kind": "explicit_grid_subset",
            "by_scene_stage_ms": {"S0": {"a": ["0"], "b": ["1", "2", "4"]}}}
        packet = reconstruct(instance, incumbent, "S0", ["a"], {"a": "L"})
        actual = self.accepted(packet, instance)
        self.assertEqual(F(packet["end_ms"]["a"]), F("5/2"))
        self.assertEqual(F(actual["b"]["start_ms"]), 4)
        self.assertEqual(F(packet["end_ms"]["b"]), 5)
        self.assertEqual(blocking_edges(packet), [])

    def test_explicit_start_exhaustion_does_not_grant_extra_edge(self):
        instance, incumbent = artificial([
            {"id": "a", "unit": "CPU1", "opp": "H", "duration_H": "1", "duration_L": "5"},
            {"id": "b", "unit": "NPU0", "duration": "1", "start": "2"},
            {"id": "z", "unit": "GPU0", "duration": "1", "start": "2", "deadline": "4"}],
            dependencies=[("a", "b"), ("a", "z")])
        instance["start_domain"] = {"version": 1, "kind": "explicit_grid_subset",
            "by_scene_stage_ms": {"S0": {"a": ["0"], "b": ["2"], "z": ["2", "5"]}}}
        packet = reconstruct(instance, incumbent, "S0", ["a"], {"a": "L"})
        self.rejected(packet, "NO_LEGAL_START_IN_SKELETON")
        self.assertTrue(packet["unavailable_starts"])
        self.assertIn("z", {v["stage_id"] for v in packet["deadline_violations"]})
        self.assertEqual(blocking_edges(packet), [])
        self.rejected(reconstruct(instance, incumbent, "S0", ["a"], {"a": "L"},
            extra_resource_edge=("a", "z")), "EXTRA_EDGE_NOT_CERTIFIED_BLOCKING")

    def test_third_party_shared_domain_conflict_is_rebuilt(self):
        instance, incumbent = artificial([
            {"id": "a", "unit": "CPU1", "duration": "2"},
            {"id": "b", "unit": "CPU2", "duration": "2"},
            {"id": "c", "unit": "CPU2", "duration": "2", "start": "2"}])
        actual = self.accepted(reconstruct(instance, incumbent, "S0", ["a"], {"a": "H"}), instance)
        self.assertEqual(F(actual["a"]["start_ms"]), 0)
        self.assertEqual(F(actual["b"]["start_ms"]), 2)
        self.assertEqual(F(actual["c"]["start_ms"]), 4)

    def test_same_frequency_two_cores_remain_concurrent(self):
        instance, incumbent = artificial([
            {"id": "a", "unit": "CPU1", "duration": "2"},
            {"id": "b", "unit": "CPU2", "duration": "2"}])
        packet = reconstruct(instance, incumbent, "S0", ["a", "b"], {"a": "H", "b": "H"})
        actual = self.accepted(packet, instance)
        self.assertEqual([F(actual[k]["start_ms"]) for k in ("a", "b")], [0, 0])
        self.assertFalse(any({e["from"], e["to"]} == {"a", "b"} for e in packet["edges"]))

    def test_zero_weight_scene_still_requires_legality_and_other_scene_is_unchanged(self):
        instance, incumbent = crossing_fixture(second_scene=True)
        instance["scenarios"][0]["weight"] = "0"
        instance["scenarios"][1]["weight"] = "1"
        self.rejected(action(instance, incumbent))
        packet = action(instance, incumbent, extra_resource_edge=("v", "u"))
        self.accepted(packet, instance)
        self.assertEqual(packet["candidate"]["scenes"]["S1"], incumbent["scenes"]["S1"])
        for sid in ("S0", "S1"):
            self.assertEqual({k: v["unit"] for k, v in rows(packet["candidate"], sid).items()},
                {k: v["unit"] for k, v in rows(incumbent, sid).items()})

    def test_cross_scene_shared_unit_mismatch_is_not_repaired(self):
        instance, incumbent = crossing_fixture(second_scene=True)
        rows(incumbent, "S1")["a"]["unit"] = "GPU0"
        self.rejected(action(instance, incumbent))

    def test_original_inputs_unchanged_on_success_and_failure(self):
        instance, incumbent = crossing_fixture()
        before = deepcopy((instance, incumbent))
        action(instance, incumbent)
        action(instance, incumbent, extra_resource_edge=("v", "u"))
        action(instance, incumbent, extra_resource_edge=("u", "v"))
        self.assertEqual((instance, incumbent), before)

    def test_budget_expiry_is_never_reclassified_or_swallowed(self):
        instance, incumbent = crossing_fixture()
        for extra in (None, ("v", "u")):
            with self.subTest(extra=extra), self.assertRaises(BudgetExpired):
                action(instance, incumbent, extra_resource_edge=extra, budget=Budget(0))

    def test_successful_base_does_not_allow_unmotivated_extra_flip(self):
        instance, incumbent = artificial([
            {"id": "a", "duration": "1"}, {"id": "b", "start": "1", "duration": "1"}])
        packet = reconstruct(instance, incumbent, "S0", ["a"], {})
        self.accepted(packet, instance)
        self.assertEqual(blocking_edges(packet), [])
        self.rejected(reconstruct(instance, incumbent, "S0", ["a"], {},
            extra_resource_edge=("a", "b")), "EXTRA_EDGE_NOT_CERTIFIED_BLOCKING")


if __name__ == "__main__":
    unittest.main(verbosity=2)
