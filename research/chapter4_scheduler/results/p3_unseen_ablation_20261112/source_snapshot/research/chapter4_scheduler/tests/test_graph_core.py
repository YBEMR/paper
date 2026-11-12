"""Independent, small artificial checks of graph reconstruction only.

No optimizer, MATLAB, temperature propagation, or research candidate is used.
The Cartesian checks below enumerate starts in tiny artificial fixtures; they
do not establish any result for P0/P1/P2 or a thermal safety conclusion.
"""
from copy import deepcopy
from fractions import Fraction as F
from itertools import product
from pathlib import Path
import sys
import unittest


RESEARCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RESEARCH / "chapter3_experiments"))
sys.path.insert(0, str(RESEARCH.parent))

from research.chapter4_scheduler.graph_core import reconstruct, related_pairs


def fixture(specs, *, dependencies=(), window="100", second_scene=False):
    """Construct an exact expanded-schema artificial input, never a SAFE."""
    nodes = ["c1", "c2", "g", "n"]
    units = [("CPU1", "CPU", "c1"), ("CPU2", "CPU", "c2"),
             ("GPU0", "GPU", "g"), ("NPU0", "NPU", "n")]
    platform = {"node_order": nodes, "units": [], "domains": {},
                "external_common_power_W": "1/2",
                "external_common_heat_distribution": ["0"] * 4,
                "reference_temperature_degC": "30"}
    for unit, domain, node in units:
        platform["units"].append({"id": unit, "domain_id": domain,
            "power_group_id": domain, "thermal_node_id": node,
            "device_class": domain})
    for domain in ("CPU", "GPU", "NPU"):
        members = [unit for unit, group, _ in units if group == domain]
        dist = [F(1, len(members)) if any(group == domain and node == n
                for _, group, node in units) else F(0) for n in nodes]
        platform["domains"][domain] = {
            "unit_ids": members, "opps": {
                "L": {"frequency_GHz": "1", "voltage_V": "1"},
                "H": {"frequency_GHz": "2", "voltage_V": "3/2"}},
            "baseline_W": {"L": "1", "H": "3"},
            "local_temperature_slope_W_per_K": {"L": "0", "H": "0"},
            "baseline_heat_distribution": [str(v) for v in dist]}
    rules = {name: False for name in ("preemption", "migration", "in_stage_opp_change")}
    rules.update(switch_only_when_domain_empty=True,
        interval_convention="[start,end)", idle_holds_last_opp=False,
        idle_policy="auto_low_immediate_v1", idle_delay_ms="0")
    for name in ("extra_transfer_time_ms", "extra_switch_time_ms", "extra_handoff_time_ms",
                 "extra_transfer_energy_J", "extra_switch_energy_J", "extra_handoff_energy_J"):
        rules[name] = "0"
    instance = {"schema_version": "chapter3-input-v0.1", "id": "fixture_graph_core",
        "window_ms": str(window), "start_grid_ms": "5", "platform": platform,
        "execution_rules": rules, "stage_modes": {}, "scenarios": []}
    candidate = {"scenes": {}}
    for scene_index in range(2 if second_scene else 1):
        sid = "S" + str(scene_index)
        scene = {"id": sid, "weight": "1/2" if second_scene else "1",
            "stage_instances": [], "requests": [],
            "dependencies": [list(edge) for edge in dependencies],
            "entry": {"temperature_degC": ["30"] * 4,
                      "domain_opp": {d: "L" for d in platform["domains"]},
                      "unfinished_work": []}}
        rows = []
        for supplied in specs:
            spec = dict(supplied)
            stage, unit = spec["id"], spec.get("unit", "CPU1")
            shared, request = stage, "r_" + stage
            scene["stage_instances"].append({"id": stage, "shared_stage_id": shared,
                                             "request_id": request})
            scene["requests"].append({"id": request, "release_ms": str(spec.get("release", "0")),
                "deadline_ms": str(spec.get("deadline", window)), "stage_instance_ids": [stage]})
            if shared not in instance["stage_modes"]:
                modes = []
                for u, domain, node in units:
                    for opp, frequency, voltage in (("L", "1", "1"), ("H", "2", "3/2")):
                        modes.append({"shared_stage_id": shared, "unit_id": u,
                            "domain_id": domain, "thermal_node_id": node,
                            "power_group_id": domain, "opp_id": opp,
                            "frequency_GHz": frequency, "voltage_V": voltage,
                            "duration_ms": str(spec.get("duration_" + opp, spec.get("duration", "5"))),
                            "activity_power_W": str(spec.get("activity_" + opp, "1"))})
                instance["stage_modes"][shared] = modes
            rows.append({"stage_id": stage, "unit": unit,
                         "opp": spec.get("opp", "L"), "start_ms": str(spec.get("start", "0"))})
        instance["scenarios"].append(scene)
        candidate["scenes"][sid] = rows
    return instance, candidate


def rows(candidate, scene="S0"):
    return {row["stage_id"]: row for row in candidate["scenes"][scene]}


def selected_mode(instance, row):
    return next(mode for mode in instance["stage_modes"][row["stage_id"]]
                if (mode["unit_id"], mode["opp_id"]) == (row["unit"], row["opp"]))


def independent_legality(instance, candidate):
    """Tiny exact task/resource oracle, independent of graph/schedule code."""
    fixed = {}
    for scene in instance["scenarios"]:
        rr = rows(candidate, scene["id"])
        requests = {r["id"]: r for r in scene["requests"]}
        times = {}
        for stage in scene["stage_instances"]:
            row = rr[stage["id"]]
            mode = selected_mode(instance, row)
            req = requests[stage["request_id"]]
            start = F(row["start_ms"])
            end = start + F(mode["duration_ms"])
            if (start < F(req["release_ms"]) or start < 0 or
                    (start / F(instance["start_grid_ms"])).denominator != 1 or
                    end > min(F(req["deadline_ms"]), F(instance["window_ms"]))):
                return False
            explicit = instance.get("start_domain", {}).get("by_scene_stage_ms")
            if explicit is not None and start not in map(F, explicit[scene["id"]][stage["id"]]):
                return False
            shared = stage["shared_stage_id"]
            if shared in fixed and fixed[shared] != row["unit"]:
                return False
            fixed[shared] = row["unit"]
            times[stage["id"]] = (start, end, row, mode)
        if any(times[a][1] > times[b][0] for a, b in scene["dependencies"]):
            return False
        entries = list(times.values())
        for i, a in enumerate(entries):
            for b in entries[i + 1:]:
                if max(a[0], b[0]) < min(a[1], b[1]):
                    if a[2]["unit"] == b[2]["unit"]:
                        return False
                    if a[3]["domain_id"] == b[3]["domain_id"] and a[2]["opp"] != b[2]["opp"]:
                        return False
    return True


class BudgetExpired(Exception):
    pass


class Budget:
    def __init__(self, allowed=0):
        self.allowed, self.calls = allowed, 0

    def check(self):
        self.calls += 1
        if self.calls > self.allowed:
            raise BudgetExpired("artificial budget expiry")


class GraphCoreTests(unittest.TestCase):
    def accepted(self, result, instance):
        self.assertEqual(result["state"], "COMPLETE_LEGAL_CANDIDATE", result)
        self.assertIsNotNone(result["candidate"])
        self.assertTrue(independent_legality(instance, result["candidate"]), result)
        self.assertNotIn("safe_upper_bound_J", result)
        self.assertNotEqual(result.get("state"), "SAFE")
        return rows(result["candidate"])

    def rejected(self, operation):
        try:
            result = operation()
        except (ValueError, TypeError, KeyError):
            return
        self.assertEqual(result["state"], "RECONSTRUCTION_REJECTED", result)
        self.assertIsNone(result.get("candidate"))

    def test_same_domain_same_opp_keeps_two_cores_parallel(self):
        instance, initial = fixture([{"id": "a", "unit": "CPU1", "duration": "10"},
                                     {"id": "b", "unit": "CPU2", "duration": "10"}])
        out = reconstruct(instance, initial, "S0", ["a", "b"], {"a": "H", "b": "H"})
        actual = self.accepted(out, instance)
        self.assertEqual(F(actual["a"]["start_ms"]), 0)
        self.assertEqual(F(actual["b"]["start_ms"]), 0)

    def test_new_different_opp_conflicts_include_unselected_third_party(self):
        instance, initial = fixture([{"id": "a", "unit": "CPU1", "duration": "10"},
            {"id": "b", "unit": "CPU2", "duration": "10"},
            {"id": "c", "unit": "CPU2", "start": "10", "duration": "10"}])
        out = reconstruct(instance, initial, "S0", ["a"], {"a": "H"})
        actual = self.accepted(out, instance)
        self.assertEqual(F(actual["b"]["start_ms"]), 10)
        self.assertEqual(F(actual["c"]["start_ms"]), 20)

    def test_removed_domain_conflict_releases_parallelism(self):
        instance, initial = fixture([{"id": "a", "unit": "CPU1", "opp": "H", "duration": "10"},
            {"id": "b", "unit": "CPU2", "start": "10", "duration": "10"}])
        out = reconstruct(instance, initial, "S0", ["a"], {"a": "L"})
        actual = self.accepted(out, instance)
        self.assertEqual(F(actual["a"]["start_ms"]), 0)
        self.assertEqual(F(actual["b"]["start_ms"]), 0)

    def test_same_device_selected_pair_reverse(self):
        instance, initial = fixture([{"id": "a", "start": "0"}, {"id": "b", "start": "10"}])
        out = reconstruct(instance, initial, "S0", ["a", "b"], {}, orientation="reverse")
        actual = self.accepted(out, instance)
        self.assertEqual(F(actual["b"]["start_ms"]), 0)
        self.assertEqual(F(actual["a"]["start_ms"]), 5)

    def test_reverse_conflicts_with_dependency_rejects_cycle(self):
        instance, initial = fixture([{"id": "a"}, {"id": "b", "start": "5"}],
                                    dependencies=[("a", "b")])
        self.rejected(lambda: reconstruct(instance, initial, "S0", ["a", "b"], {},
                                            orientation="reverse"))

    def test_noninteger_finish_and_release_round_to_next_start_only(self):
        instance, initial = fixture([{"id": "a", "unit": "CPU1", "duration": "7/2",
            "release": "1", "start": "5"},
            {"id": "b", "unit": "NPU0", "duration": "1", "start": "10"}],
            dependencies=[("a", "b")])
        out = reconstruct(instance, initial, "S0", ["a"], {})
        actual = self.accepted(out, instance)
        self.assertEqual(F(actual["a"]["start_ms"]), 5)
        self.assertEqual(F(actual["b"]["start_ms"]), 10)
        self.assertEqual(F(actual["a"]["start_ms"]) + F(selected_mode(instance, actual["a"])["duration_ms"]), F("17/2"))

    def test_exact_deadline_boundary_accepted_slower_mode_rejected(self):
        instance, initial = fixture([{"id": "a", "opp": "H", "duration_L": "6", "duration_H": "5",
                                     "deadline": "5"}])
        self.accepted(reconstruct(instance, initial, "S0", ["a"], {}), instance)
        self.rejected(lambda: reconstruct(instance, initial, "S0", ["a"], {"a": "L"}))

    def test_window_boundary_is_not_relaxed(self):
        instance, initial = fixture([{"id": "a", "opp": "H", "duration_L": "11", "duration_H": "5",
                                     "deadline": "10"}], window="10")
        self.rejected(lambda: reconstruct(instance, initial, "S0", ["a"], {"a": "L"}))

    def test_explicit_domain_uses_next_member_and_does_not_fall_back(self):
        instance, initial = fixture([{"id": "a", "duration": "6", "start": "0"},
            {"id": "b", "unit": "NPU0", "start": "15"}], dependencies=[("a", "b")])
        instance["start_domain"] = {"version": 1, "kind": "explicit_grid_subset",
            "by_scene_stage_ms": {"S0": {"a": ["0"], "b": ["5", "15"]}}}
        actual = self.accepted(reconstruct(instance, initial, "S0", ["a"], {}), instance)
        self.assertEqual(F(actual["b"]["start_ms"]), 15)
        empty = deepcopy(instance)
        empty["start_domain"]["by_scene_stage_ms"]["S0"]["b"] = []
        self.rejected(lambda: reconstruct(empty, initial, "S0", ["a"], {}))

    def test_explicit_domain_exhaustion_after_mode_change(self):
        instance, initial = fixture([{"id": "a", "opp": "H", "duration_L": "11", "duration_H": "5"},
            {"id": "b", "unit": "NPU0", "start": "10"}], dependencies=[("a", "b")])
        instance["start_domain"] = {"version": 1, "kind": "explicit_grid_subset",
            "by_scene_stage_ms": {"S0": {"a": ["0"], "b": ["5", "10"]}}}
        self.rejected(lambda: reconstruct(instance, initial, "S0", ["a"], {"a": "L"}))

    def test_preserve_keeps_unselected_nondescendant_floor_only(self):
        instance, initial = fixture([{"id": "a", "duration": "5"},
            {"id": "b", "unit": "NPU0", "start": "30"},
            {"id": "c", "unit": "GPU0", "start": "40"}], dependencies=[("a", "b")])
        out = reconstruct(instance, initial, "S0", ["a"], {}, template="preserve")
        actual = self.accepted(out, instance)
        self.assertEqual(F(actual["b"]["start_ms"]), 5)
        self.assertEqual(F(actual["c"]["start_ms"]), 40)

    def test_other_scene_mapping_and_inputs_are_unchanged(self):
        instance, initial = fixture([{"id": "a"}, {"id": "b", "unit": "NPU0", "start": "10"}],
                                    second_scene=True)
        before_instance, before_initial = deepcopy(instance), deepcopy(initial)
        out = reconstruct(instance, initial, "S0", ["a"], {"a": "H"})
        self.accepted(out, instance)
        self.assertEqual(out["candidate"]["scenes"]["S1"], initial["scenes"]["S1"])
        for sid in initial["scenes"]:
            self.assertEqual({key: row["unit"] for key, row in rows(out["candidate"], sid).items()},
                             {key: row["unit"] for key, row in rows(initial, sid).items()})
        self.assertEqual(instance, before_instance)
        self.assertEqual(initial, before_initial)

    def test_cross_scene_device_mismatch_is_not_silently_repaired(self):
        instance, initial = fixture([{"id": "a"}], second_scene=True)
        initial["scenes"]["S1"][0]["unit"] = "CPU2"
        self.rejected(lambda: reconstruct(instance, initial, "S0", ["a"], {"a": "H"}))

    def test_shared_domain_base_not_charged_once_per_core(self):
        instance, initial = fixture([{"id": "a", "unit": "CPU1", "opp": "H", "duration": "10"},
            {"id": "b", "unit": "CPU2", "opp": "H", "duration": "10"}])
        out = reconstruct(instance, initial, "S0", ["a", "b"], {})
        self.accepted(out, instance)
        # CPU 3W*10ms + 1W*90ms; GPU/NPU each 1W*100ms;
        # external .5W*100ms; two activities 1W*10ms each.
        self.assertEqual(F(out["nonthermal_energy_J"]), F("39/100"))

    def test_nonthermal_energy_is_weighted_over_all_scenes(self):
        instance, initial = fixture([{"id": "a", "duration": "10"}], second_scene=True)
        out = reconstruct(instance, initial, "S0", ["a"], {"a": "H"})
        self.accepted(out, instance)
        # Base .35 J each scene; activity .01 J each; S0 CPU-H adds .02 J.
        self.assertEqual(F(out["nonthermal_energy_J"]), F("37/100"))

    def test_invalid_opp_device_rows_and_duplicate_options_rejected(self):
        instance, initial = fixture([{"id": "a"}])
        self.rejected(lambda: reconstruct(instance, initial, "S0", ["a"], {"a": "UNKNOWN"}))
        self.rejected(lambda: reconstruct(instance, initial, "S0", ["a", "a"], {}))
        self.rejected(lambda: reconstruct(instance, initial, "S0", ["a"], {"not_selected": "L"}))
        self.rejected(lambda: reconstruct(instance, initial, "S0", ["a"], {"a": ("CPU2", "H")}))
        duplicate = deepcopy(instance)
        duplicate["stage_modes"]["a"].append(deepcopy(duplicate["stage_modes"]["a"][0]))
        self.rejected(lambda: reconstruct(duplicate, initial, "S0", ["a"], {}))
        bad = deepcopy(initial)
        bad["scenes"]["S0"][0]["unit"] = "MISSING_UNIT"
        self.rejected(lambda: reconstruct(instance, bad, "S0", ["a"], {}))

    def test_related_pairs_use_resources_not_accelerator_type(self):
        instance, initial = fixture([{"id": "a", "unit": "CPU1"},
            {"id": "b", "unit": "CPU2"},
            {"id": "c", "unit": "NPU0"}, {"id": "d", "unit": "NPU0", "start": "5"}])
        pairs = related_pairs(instance, initial)
        keys = [(item["scene_id"], frozenset(item["stage_ids"])) for item in pairs]
        self.assertIn(("S0", frozenset(("a", "b"))), keys)
        self.assertIn(("S0", frozenset(("c", "d"))), keys)
        self.assertNotIn(("S0", frozenset(("a", "c"))), keys)
        self.assertEqual(len(keys), len(set(keys)))

    def test_budget_expiry_propagates_without_candidate(self):
        instance, initial = fixture([{"id": "a"}])
        for operation in (lambda b: related_pairs(instance, initial, budget=b),
                          lambda b: reconstruct(instance, initial, "S0", ["a"], {}, budget=b)):
            with self.assertRaises(BudgetExpired):
                operation(Budget(0))

    def test_nonthermal_score_rejects_nonunit_scene_weight_sum(self):
        instance, initial = fixture([{"id": "a"}], second_scene=True)
        instance["scenarios"][0]["weight"] = "1"
        self.rejected(lambda: reconstruct(instance, initial, "S0", ["a"], {}))

    def test_fixed_skeleton_earliest_by_independent_cartesian_enumeration(self):
        # Enumerate only starts for artificial two-Stage schedules. Modes and
        # precedence/order are fixed. This is an independent finite oracle.
        for duration in ("1", "7/2", "6", "10"):
            with self.subTest(duration=duration):
                instance, initial = fixture([{"id": "a", "duration": duration,
                    "release": "1", "start": "5", "deadline": "20"},
                    {"id": "b", "unit": "NPU0", "duration": "1", "start": "15", "deadline": "20"}],
                    dependencies=[("a", "b")], window="20")
                out = reconstruct(instance, initial, "S0", ["a"], {})
                actual = self.accepted(out, instance)
                actual_starts = {stage: F(row["start_ms"]) for stage, row in actual.items()}
                feasible = []
                for a, b in product(range(0, 21, 5), repeat=2):
                    candidate = deepcopy(initial)
                    values = rows(candidate)
                    values["a"]["start_ms"], values["b"]["start_ms"] = str(a), str(b)
                    if independent_legality(instance, candidate):
                        feasible.append({"a": F(a), "b": F(b)})
                self.assertTrue(feasible)
                for other in feasible:
                    self.assertTrue(all(actual_starts[key] <= other[key] for key in actual_starts),
                                    (actual_starts, other))


if __name__ == "__main__":
    unittest.main(verbosity=2)
