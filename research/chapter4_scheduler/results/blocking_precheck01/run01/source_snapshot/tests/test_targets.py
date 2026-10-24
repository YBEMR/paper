"""Artificial mode-table checks; no real workload, HEFT or thermal call."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

RESEARCH = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RESEARCH / "chapter3_experiments"))
sys.path.insert(0, str(RESEARCH.parent))

from research.chapter4_scheduler.blocking.method import energy_targets
from research.chapter4_scheduler.tests.test_graph_core import fixture, Budget, BudgetExpired


class ModeTargetTests(unittest.TestCase):
    def collect(self, instance, candidate):
        return energy_targets(instance, candidate, Budget(100000))

    def test_equal_activity_is_not_a_target(self):
        i, c = fixture([{"id": "x"}])
        self.assertEqual(self.collect(i, c), [])

    def test_selects_by_q_times_duration_not_frequency_order(self):
        i, c = fixture([{"id": "x", "duration_L": "10", "duration_H": "5"}])
        out = self.collect(i, c)
        self.assertEqual([(t["stage_id"], t["target_opp"], t["weighted_activity_saving_J"]) for t in out],
                         [("x", "H", "1/200")])

    def test_cheap_other_unit_is_not_a_fixed_device_target(self):
        i, c = fixture([{"id": "x"}])
        for m in i["stage_modes"]["x"]:
            if m["unit_id"] == "GPU0":
                m["activity_power_W"] = "1/100"
        self.assertEqual(self.collect(i, c), [])

    def test_exact_saving_order_and_stable_identifier_tie(self):
        i, c = fixture([{"id": "b", "unit": "CPU1", "opp": "H", "activity_H": "3"},
                        {"id": "a", "unit": "CPU2", "opp": "H", "activity_H": "3"}])
        out = self.collect(i, c)
        self.assertEqual([t["stage_id"] for t in out], ["a", "b"])
        self.assertTrue(all(t["weighted_activity_saving_J"] == "1/100" for t in out))

    def test_zero_weight_scene_remains_in_input_but_has_no_target(self):
        i, c = fixture([{"id": "x", "opp": "H", "activity_H": "3"}], second_scene=True)
        i["scenarios"][0]["weight"], i["scenarios"][1]["weight"] = "1", "0"
        out = self.collect(i, c)
        self.assertEqual([t["scene_id"] for t in out], ["S0"])
        self.assertEqual(set(c["scenes"]), {"S0", "S1"})

    def test_shared_device_does_not_require_shared_opp(self):
        i, c = fixture([{"id": "x", "opp": "H", "activity_H": "3"}], second_scene=True)
        c["scenes"]["S1"][0]["opp"] = "L"
        out = self.collect(i, c)
        self.assertEqual([(t["scene_id"], t["target_opp"]) for t in out], [("S0", "L")])
        self.assertEqual(out[0]["weighted_activity_saving_J"], "1/200")

    def test_targets_do_not_mutate_input_or_incumbent(self):
        i, c = fixture([{"id": "x", "opp": "H", "activity_H": "3"}])
        old_i, old_c = deepcopy(i), deepcopy(c)
        self.collect(i, c)
        self.assertEqual(i, old_i); self.assertEqual(c, old_c)

    def test_invalid_weight_sum_and_negative_weight_rejected(self):
        for weight in ("0", "2", "-1"):
            i, c = fixture([{"id": "x"}])
            i["scenarios"][0]["weight"] = weight
            with self.subTest(weight=weight), self.assertRaises(ValueError):
                self.collect(i, c)

    def test_budget_expiry_propagates_without_target(self):
        i, c = fixture([{"id": "x"}])
        with self.assertRaises(BudgetExpired):
            energy_targets(i, c, Budget(0))


if __name__ == "__main__":
    unittest.main()
