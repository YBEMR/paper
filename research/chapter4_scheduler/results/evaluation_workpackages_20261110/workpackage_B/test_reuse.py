"""Pure rational synthetic arithmetic tests, no workload or evaluator calls."""
import importlib.util
from fractions import Fraction as F
from pathlib import Path
import unittest

path = Path(__file__).with_name("reuse_trajectories.py")
spec = importlib.util.spec_from_file_location("B_reuse_under_test", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class MeanTests(unittest.TestCase):
    def test_constant_temperature_exact(self):
        self.assertEqual(module.temperature_mean("25", ["10", "10"], "2/5"), (F(50), F(50)))

    def test_interval_endpoints_map_outward_exactly(self):
        self.assertEqual(module.temperature_mean("25", ["9", "10"], "2/5"), (F(95, 2), F(50)))

    def test_whole_window_not_active_time(self):
        self.assertEqual(module.temperature_mean("25", ["1", "1"], "2/5"), (F(55, 2), F(55, 2)))

    def test_negative_relative_integral_allowed(self):
        self.assertEqual(module.temperature_mean("25", ["-1", "-1/2"], "2/5"), (F(45, 2), F(95, 4)))

    def test_nonpositive_window_rejected(self):
        for value in ("0", "-1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                module.temperature_mean("25", ["1", "2"], value)

    def test_reversed_interval_rejected(self):
        with self.assertRaises(ValueError):
            module.temperature_mean("25", ["2", "1"], "2/5")

    def test_overlapping_comparison_is_not_new_independent_proof(self):
        value = module.comparison(["1", "2"], ["3/2", "5/2"])
        self.assertTrue(value["overlap"])
        self.assertEqual(value["interval_distance"], "0")
        self.assertEqual(value["right_minus_left_interval"], ["-1/2", "3/2"])

    def test_separated_comparison_distance(self):
        value = module.comparison(["1", "2"], ["3", "4"])
        self.assertFalse(value["overlap"])
        self.assertEqual(value["interval_distance"], "1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
