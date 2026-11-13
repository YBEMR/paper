"""Input contract tests use a separate test-only named root, no algorithms/heat."""
from copy import deepcopy
import unittest

from .input import fixed_plan, _project_base, _time_evidence, SOURCE_CONFIG
from research.chapter3_workload_calibration.profiles import load_catalog
from research.chapter3_workload_calibration.generator import build_base, validate_transform
from research.chapter3_deadline_reference.contract import ContractError


class InputTests(unittest.TestCase):
    def test_nested_two_scene_base_and_profile_integrity(self):
        plan, catalog = fixed_plan(), load_catalog(SOURCE_CONFIG)
        args = dict(root_id="TEST_ONLY_INPUT", namespace="ch4-scaling-manual-check", seed=1,
                    scene_pool="A", compatibility_pool="heterogeneous", settings=plan["settings"])
        raw6 = build_base(catalog, scale=6, **args)
        raw12 = build_base(catalog, scale=12, parent=raw6, **args)
        base6, base12 = _project_base(raw6), None
        base12 = _project_base(raw12, base6)
        self.assertTrue(validate_transform(base6, base12))
        self.assertEqual([len(s["stage_instances"]) for s in base12["time_contract"]["scenarios"]], [12, 12])
        self.assertEqual([s["weight"] for s in base12["time_contract"]["scenarios"]], ["1/2", "1/2"])
        self.assertEqual(base6["provenance"]["two_scene_base"]["source_eight_scene_bundle_hash"], raw6["bundle_hash"])
        bad = deepcopy(base12)
        bad["physical_profiles"]["L1.s0001"]["work_units"] = "999"
        with self.assertRaises(ContractError):
            validate_transform(base6, bad)

    def test_plan_declares_only_requested_scales_and_no_screening(self):
        plan = fixed_plan()
        self.assertEqual(plan["scales"], [6, 12])
        self.assertEqual(len(plan["roots"]), 2)
        self.assertEqual(plan["initial_temperature_C"], ["50"] * 4)
        self.assertIn("no replacement", plan["selection"])
        self.assertIn("two-scene", plan["window_rule"])


if __name__ == "__main__":
    unittest.main()
