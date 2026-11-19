"""Regression and structural tests; no expanded deployment value experiment."""
from copy import deepcopy
import unittest

import numpy as np

import adapter
from scene_events import split_workload, replay_sequence, time_scene as historical_time_scene


class CandidateAdapterTests(unittest.TestCase):
    def test_coverage_cap_and_historical_anchors(self):
        proof = adapter.certificates()
        self.assertEqual(len(proof["individual"]), 8)
        self.assertEqual(len(proof["combinations"]), 16)
        self.assertEqual(len(adapter.combinations()), 12)
        self.assertEqual(sum(not r["admitted"] for r in proof["combinations"]), 4)
        for row in proof["combinations"]:
            self.assertEqual(row["admitted"], row["resident_dla_stages"] <= 4)
        for name in ("A", "C"):
            self.assertEqual(adapter.FROZEN_EXT["deployments"][name]["stages"],
                             adapter.FROZEN["deployments"][name]["stages"])

    def test_skips_repeats_and_missing_tail_rejected(self):
        app = "1"
        for stages in ([["GPU", 1, 23]], [["DLA0", 0, 16], ["GPU", 16, 23]], [["GPU", 0, 22]]):
            candidate = deepcopy(adapter.LIBRARY["applications"][app][0])
            candidate["stages"] = stages
            with self.assertRaises(ValueError):
                adapter.validate_candidate(int(app), candidate)
        candidate = deepcopy(adapter.LIBRARY["applications"][app][0])
        candidate["evidence_class"] = "unknown_support"
        with self.assertRaises(ValueError):
            adapter.validate_candidate(int(app), candidate)

    def test_v3_residual_survives_cut(self):
        candidate = next(c for c in adapter.LIBRARY["applications"]["3"] if len(c["stages"]) == 3)
        certificate = adapter.validate_candidate(3, candidate)
        cut = certificate["stages"][1]
        self.assertEqual(cut["last"], 46)
        self.assertTrue({42, 46}.issubset(cut["live_outputs"]))

    def test_historical_event_and_physical_replay_identical(self):
        scenes = split_workload("10s", 25)
        clocks = ("LLL", "LLL", "LHL", "LHL")
        for deployment in ("A", "C"):
            for scene, opp in zip(scenes, clocks):
                old = historical_time_scene(adapter.PLATFORM, scene, deployment, opp)
                new = adapter.time_scene(scene, deployment, opp)
                self.assertEqual(new.rows, old.rows)
                self.assertEqual(new.completions_ns, old.completions_ns)
                np.testing.assert_array_equal(new.active_w, old.active_w)
            old = replay_sequence(adapter.PLATFORM, scenes, deployment, clocks, 25)
            new = adapter.replay(scenes, deployment, clocks, 25)
            for key in ("feasible", "deadline_ok", "completed", "required", "energy_j",
                        "peak_lower_c", "peak_upper_c", "final_c", "min_slack_ms"):
                self.assertEqual(old[key], new[key])


if __name__ == "__main__":
    unittest.main()
