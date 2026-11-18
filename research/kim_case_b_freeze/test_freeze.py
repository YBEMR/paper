"""Static checks of the paired input and the response ledger. No evaluator."""
import csv
import json
import unittest
from collections import Counter
from fractions import Fraction
from itertools import permutations, product
from pathlib import Path

HERE = Path(__file__).resolve().parent
FPS = (20, 25, 30)
LAYER_COUNTS = (54, 24, 35, 179)
SCENES = {"sc0": [0], "sc1": [0, 1, 2], "sc2": [1, 2, 3], "sc3": [3]}


def check_chain(stages, total_layers):
    start = 0
    for resource, first, last in stages:
        if resource not in {"DLA0", "DLA1", "GPU"}:
            raise ValueError("unknown accelerator")
        if type(first) is not int or type(last) is not int or first != start or last < first:
            raise ValueError("invalid inclusive interval")
        start = last + 1
    if start != total_layers:
        raise ValueError("incomplete network")


def count_residents(mapping, cap):
    engines = Counter(resource for chain in mapping.values()
                     for resource, first, last in chain if resource in {"DLA0", "DLA1"})
    if sum(engines.values()) > cap:
        raise ValueError("global resident DLA limit exceeded")
    return engines


class FreezeChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((HERE / "input.json").read_text(encoding="utf-8-sig"))
        cls.maps = {name: row["stages"] for name, row in cls.data["deployments"].items()}
        with (HERE / "stages.csv").open(encoding="utf-8-sig", newline="") as stream:
            cls.ledger = list(csv.DictReader(stream))

    def test_frozen_source_and_networks(self):
        self.assertEqual(self.data["metadata"]["base_commit"],
                         "5004ed72b95e1d32cf6e7b2c1c3a716ce6759af8")
        self.assertEqual(self.data["metadata"]["public_config_commit"],
                         "50fda15ce3b82b38f46adddc04c47b58042cef71")
        apps = self.data["applications"]
        self.assertEqual([a["id"] for a in apps], list(range(4)))
        self.assertEqual([a["network"] for a in apps], ["YOLOv2", "YOLOv2tiny", "YOLOv3tiny", "YOLOv3"])
        self.assertEqual(tuple(a["layers"] for a in apps), LAYER_COUNTS)
        self.assertEqual([a["cpu_core"] for a in apps], [f"CPU{i}" for i in range(4)])
        p = self.data["platform"]
        self.assertEqual((p["precision"], p["batch"], p["input_hw"]), ("FP16", 1, [256, 256]))

    def test_exact_cuts_and_fixed_partners(self):
        self.assertEqual(set(self.maps), {"A", "C"})
        self.assertEqual(self.maps["A"]["0"], [["DLA0", 0, 29], ["GPU", 30, 53]])
        self.assertEqual(self.maps["C"]["0"], [["DLA0", 0, 29], ["DLA1", 30, 40], ["GPU", 41, 53]])
        partners = {
            "1": [["DLA0", 0, 16], ["GPU", 17, 23]],
            "2": [["DLA1", 0, 16], ["GPU", 17, 34]],
            "3": [["GPU", 0, 178]],
        }
        for mapping in self.maps.values():
            self.assertEqual(set(mapping), {"0", "1", "2", "3"})
            self.assertEqual({k: mapping[k] for k in partners}, partners)
            for i, count in enumerate(LAYER_COUNTS):
                check_chain(mapping[str(i)], count)

    def test_bad_intervals_are_rejected(self):
        for wrong in ([["DLA0",0,29],["GPU",29,53]], [["DLA0",0,28],["GPU",30,53]],
                      [["DLA2",0,53]], [["DLA0",0,52]], [["GPU",0,54]]):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                check_chain(wrong, 54)

    def test_global_residency_across_inactive_apps(self):
        cap = self.data["stage_encoding"]["resident_dla_engine_cap"]
        self.assertEqual(cap, 4)
        for label, expected in (("A", {"DLA0": 2, "DLA1": 1}), ("C", {"DLA0": 2, "DLA1": 2})):
            counts = count_residents(self.maps[label], cap)
            self.assertEqual(counts, expected)
            self.assertEqual(sum(counts.values()), self.data["deployments"][label]["resident_dla_engines"])
        five = dict(self.maps["C"], **{"3": [["DLA0",0,3], ["GPU",4,178]]})
        with self.assertRaisesRegex(ValueError, "global"):
            count_residents(five, cap)

    def test_state_graph(self):
        fsm = self.data["fsm"]
        self.assertEqual(fsm["active_apps"], SCENES)
        self.assertCountEqual([tuple(edge) for edge in fsm["edges"]], permutations(SCENES, 2))
        self.assertEqual(fsm["trace"], list(SCENES))
        self.assertEqual(fsm["segment_duration_periods"], [1, 1, 1, 1])
        for src, target in zip(fsm["trace"], fsm["trace"][1:]):
            self.assertIn([src, target], fsm["edges"])

    def test_paired_requests_and_deadlines(self):
        w = self.data["workload"]
        self.assertEqual(tuple(w["fps"]), FPS)
        expected = [(f"sc{i}", a, i, i+1) for i in range(4) for a in SCENES[f"sc{i}"]]
        actual = [(r["scene"], r["app"], r["release_period"], r["deadline_period"]) for r in w["requests"]]
        self.assertCountEqual(actual, expected)
        self.assertEqual(len({r["id"] for r in w["requests"]}), 8)
        for app in range(4):
            jobs = sorted((r for r in w["requests"] if r["app"] == app), key=lambda r:r["release_period"])
            self.assertEqual([r["image_rank"] for r in jobs], [1,2])
        for fps, full_ms in zip(FPS, [250, 200, Fraction(500,3)]):
            self.assertEqual(Fraction(1000, fps) * w["window_periods"], full_ms)
        self.assertEqual(w["tail_periods"], 1)
        self.assertEqual(max(r["deadline_period"] for r in w["requests"]) + w["tail_periods"], w["window_periods"])
        for deployment in self.data["deployments"].values():
            self.assertEqual(set(deployment), {"case", "stages", "resident_dla_engines"})

    def test_frequency_and_two_resource_one_node_model(self):
        self.assertEqual(self.data["frequency_mhz"], {
            "CPU": [1190.4,1651.2,2265.6], "GPU": [675.75,1032.75,1377], "DLA": [550.4,896,1395.2]})
        clock = self.data["clock_policy"]
        self.assertEqual(clock["maxn_mode_id"], 0)
        self.assertEqual(clock["axis_order"], ["CPU", "GPU", "DLA"])
        self.assertCountEqual([tuple(p) for p in clock["constant_opp_levels"]], product("LMH", repeat=3))
        self.assertEqual(clock["domain_members"]["DLA"], ["DLA0", "DLA1"])
        thermal = self.data["thermal"]
        self.assertEqual(thermal["nodes"], ["CPU","GPU","DLA"])
        self.assertEqual(thermal["heat_mapping"], {"CPU":"CPU","GPU":"GPU","DLA0":"DLA","DLA1":"DLA"})
        self.assertCountEqual(self.data["execution_policy"]["accelerators"]["resources"], ["GPU","DLA0","DLA1"])

    def test_stage_and_handoff_table_covers_input(self):
        for label, mapping in self.maps.items():
            for app, intervals in mapping.items():
                rows = sorted((r for r in self.ledger if label in r["deployments"] and r["app"] == f"app{app}"),
                              key=lambda r: int(r["ordinal"]))
                core = f"CPU{app}"
                devices = [core] + [resource for resource, first, last in intervals] + [core]
                labels = ["CPU / pre"] + [f"{first}-{last}" for resource, first, last in intervals] + ["CPU / post"]
                expected = []
                for i, (dev, scope) in enumerate(zip(devices, labels)):
                    expected.append(("STAGE", dev, scope))
                    if i + 1 < len(devices):
                        expected.append(("EDGE", dev+">"+devices[i+1], scope+">"+labels[i+1]))
                actual = [(r["row_type"], r["execution_or_transfer"], r["inclusive_layers_or_interface"]) for r in rows]
                self.assertEqual(actual, expected)
                self.assertEqual([int(r["ordinal"]) for r in rows], list(range(1, len(expected)+1)))
        for row in self.ledger:
            self.assertIn(row["deployments"], ("A","C","AC"))
            self.assertIn(row["app"], {"app0","app1","app2","app3"})
            for field in ("ref_ACET_ms","ref_WCET_ms","active_increment_node_vector_W"):
                self.assertEqual(row[field], "UNKNOWN")

    def test_numerical_admission_remains_blocked(self):
        self.assertTrue(self.data["missing_numeric"])
        self.assertTrue(all(v is None for v in self.data["missing_numeric"].values()))
        for key in ("initial_reference_degC","ambient_degC","safety_limits_degC","capacity_J_per_K",
                    "conductance_W_per_K","temperature_power_slopes_W_per_K"):
            self.assertIsNone(self.data["thermal"][key])
        self.assertEqual(self.data["admission"], {"structure":"FROZEN","deadline":"UNPROVED",
            "power":"UNPROVED","thermal":"UNPROVED","energy":"BLOCKED","allow_value_experiments":False})


if __name__ == "__main__":
    unittest.main()
