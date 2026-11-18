"""Toy regressions of changes in clock, scene partitioning, and continuous replay."""
import unittest
from unittest.mock import patch

import numpy as np

from scene_events import PLATFORM, Request, partition_requests, replay_sequence, simulate, thermal_kwargs
from events import Stage
from thermal import evaluate_thermal


MS = 1_000_000


def stage_set(app, opp):
    factor = 2 if opp == "LLL" else 1
    return [Stage("pre", f"CPU{app}", factor*MS, 1.0), Stage("run", "GPU", factor*2*MS, 3.0)]


def toy_time(platform, scene, deployment, opp):
    return simulate(scene.requests, {i:stage_set(i,opp) for i in range(4)}, scene.duration_ns)


class SceneTests(unittest.TestCase):
    def setUp(self):
        self.jobs = [Request("a", 0, 0, 10*MS), Request("b", 1, 10*MS, 20*MS)]
        self.scenes = partition_requests(self.jobs, [(0,"sc0"),(10*MS,"sc1")], 25*MS, 20*MS)

    def test_partition_preserves_tail_and_absolute_deadlines(self):
        a,b = self.scenes
        self.assertEqual((0,10*MS,10*MS), (a.start_ns,a.service_end_ns,a.end_ns))
        self.assertEqual((10*MS,20*MS,25*MS), (b.start_ns,b.service_end_ns,b.end_ns))
        self.assertEqual(b.requests, (Request("b", 1, 0, 10*MS),))
        with self.assertRaises(ValueError):
            partition_requests([Request("a",0,2*MS,12*MS)],[(0,"A"),(10*MS,"B")],30*MS,20*MS)
        with self.assertRaises(ValueError):
            partition_requests(self.jobs+self.jobs,[(0,"A")],30*MS,20*MS)

    @patch("scene_events.time_scene", toy_time)
    def test_constant_opp_matches_full_timeline_heat(self):
        out = replay_sequence(PLATFORM,self.scenes,"A",("HHH","HHH"),25)
        self.assertTrue(out["feasible"])
        self.assertEqual(out["switches"],0)
        self.assertEqual((out["required"],out["completed"],out["min_slack_ms"]),(2,2,7.0))
        gather = simulate(self.jobs,{i:stage_set(i,"HHH") for i in range(2)},25*MS,(10*MS,))
        args = thermal_kwargs(PLATFORM,"HHH",25,True,"base")
        truth = evaluate_thermal(gather.duration_ns*1e-9,gather.active_w,transfer_W=gather.transfer_w,**args)
        self.assertAlmostEqual(out["energy_j"],truth["energy_J"],places=11)
        np.testing.assert_allclose(out["final_c"],truth["final_C"],atol=1e-10,rtol=0)
        np.testing.assert_allclose(out["peak_upper_c"],truth["peak_upper_C"],atol=1e-10,rtol=0)

    @patch("scene_events.time_scene", toy_time)
    def test_switch_and_reset_semantics(self):
        opps = ("LLL","HHH")
        continuous = replay_sequence(PLATFORM,self.scenes,"A",opps,25)
        independent = replay_sequence(PLATFORM,self.scenes,"A",opps,25,reset=True)
        self.assertEqual(continuous["switches"],1)
        self.assertEqual(continuous["min_slack_ms"],4.0)
        prior,end = continuous["scene_rows"]
        self.assertEqual(prior["final_c"],end["entry_c"])
        self.assertEqual(independent["scene_rows"][1]["entry_c"],[30.0]*4)
        self.assertNotEqual(end["entry_c"],independent["scene_rows"][1]["entry_c"])
        self.assertEqual(continuous["completed"],independent["completed"])

    @patch("scene_events.time_scene", toy_time)
    def test_miss_does_not_restart_queue(self):
        jobs = [Request("a",0,0,2*MS),Request("b",1,2*MS,12*MS)]
        scenes = partition_requests(jobs,[(0,"s0"),(2*MS,"s1")],15*MS,12*MS)
        out = replay_sequence(PLATFORM,scenes,"C",("LLL","HHH"),25)
        self.assertFalse(out["deadline_ok"])
        self.assertFalse(out["fully_replayed"])
        self.assertIsNone(out["energy_j"])
        self.assertEqual(out["scene_rows"][0]["late_ids"],["a"])
        self.assertEqual(len(out["scene_rows"]),1)


if __name__=="__main__":
    unittest.main()
