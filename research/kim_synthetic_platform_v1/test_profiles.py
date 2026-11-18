"""Topology, units, DVFS and stability checks; no requests are dispatched."""
import json
from pathlib import Path
import unittest

import numpy as np

from profiles import build_chains, graph_features, live_bytes, thermal_kwargs


HERE = Path(__file__).resolve().parent
PLATFORM = json.loads((HERE/"platform.json").read_text(encoding="utf-8-sig"))
SOURCE = json.loads((HERE.parent/"kim_case_b_freeze"/"input.json").read_text(encoding="utf-8-sig"))


class ParameterTests(unittest.TestCase):
    def test_conv_shape_count_and_residual_liveness(self):
        blocks = (("conv", 8, 3, 1, True), ("conv", 8, 1, 1, False), ("shortcut", -2))
        ops, heads = graph_features(blocks, 4, 3, 2)
        self.assertEqual(len(ops), 4)
        self.assertEqual(ops[0].mac, 4*4*8*3*9)
        self.assertEqual(ops[1].mac, 0)
        self.assertEqual(ops[3].inputs, (2,1))
        self.assertEqual(live_bytes(ops, heads, 2, 2), 2*4*4*8*2)

    def test_public_graph_sizes_match_frozen_networks(self):
        clock = PLATFORM["clock"]
        self.assertEqual(clock["mhz"], SOURCE["frequency_mhz"])
        for app in SOURCE["applications"]:
            raw = PLATFORM["architecture_reference"]["graphs"][str(app["id"])]["blocks"]
            ops, heads = graph_features(tuple(map(tuple,raw)), 256, 3, 2)
            self.assertEqual(len(ops), app["layers"])
            self.assertTrue(all(node.mac >= 0 and node.traffic_bytes > 0 for node in ops))
            self.assertTrue(heads)
            if app["id"] == 0:
                pieces = [sum(x.mac for x in ops[a:b]) for a,b in ((0,30), (30,41), (41,54))]
                self.assertEqual(sum(pieces), sum(x.mac for x in ops))
                self.assertAlmostEqual(sum(pieces)/1e9, 5.579015, places=5)
                self.assertEqual(live_bytes(ops, heads, 40, 2), 393216)

    def test_domains_and_dvfs_change_service_consistently(self):
        # This verifies unlocked synthetic single-stage properties only.
        for dep in ("A","C"):
            high = build_chains(PLATFORM, SOURCE, dep, "HHH")
            low = build_chains(PLATFORM, SOURCE, dep, "LLL")
            for app in high:
                for h,l in zip(high[app],low[app],strict=True):
                    self.assertEqual(h.resource, l.resource)
                    self.assertGreater(h.duration_ns,0)
                    if h.resource == "XFER":
                        self.assertEqual(h, l)
                    else:
                        self.assertGreater(l.duration_ns, h.duration_ns)
                        self.assertLess(l.activity_w, h.activity_w)
                    self.assertGreaterEqual(l.activity_w, 0)

    def test_stability_and_dla_baseline_conservation(self):
        for idx,level in enumerate("LMH"):
            args = thermal_kwargs(PLATFORM,level*3,30,True,"r120")
            g = np.array(args["conductance_W_K"])
            slopes = np.array(args["slope_W_K"])
            self.assertTrue(np.allclose(g,g.T))
            self.assertGreater(np.linalg.eigvalsh(g-np.diag(slopes)).min(),0)
            self.assertAlmostEqual(sum(args["idle_W"][2:]),
                                   PLATFORM["power"]["idle_by_domain_W"]["DLA"][idx])
            self.assertAlmostEqual(sum(args["transfer_heat_fraction"]),1.0)
            disabled = thermal_kwargs(PLATFORM,level*3,30,False,"r120")
            self.assertEqual(disabled["idle_W"],args["idle_W"])
            self.assertEqual(disabled["slope_W_K"],[0.0]*4)
