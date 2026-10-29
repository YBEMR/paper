"""Small manual identity/profile tests; no calibration roots or schedules."""

from copy import deepcopy
from fractions import Fraction
from pathlib import Path
import tempfile
import unittest

from .profiles import (CPU_PROTOTYPES, CATEGORIES, SOURCE_SHA256, ProfileError,
                       load_catalog, make_profile, substream_digest)


def manual_settings():
    return {"category_weights": {key: "1/4" for key in CATEGORIES},
            "cpu_prototype_weights": {key: "1/6" for key in CPU_PROTOTYPES},
            "workload": {"minimum": "0.5", "maximum": "2.0", "quantum": "0.001",
                         "precision": 60, "rounding": "ROUND_HALF_UP"},
            "specialization_probabilities": {"gpu_friendly": "0.4", "npu_friendly": "0.4"}}


class ProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path(__file__).resolve().parents[1] / "chapter3_experiments" / "config_v01.json"
        cls.catalog = load_catalog(cls.source)

    def make(self, settings=None, **changes):
        args = dict(namespace="manual-fixture", seed=71, root_id="manual-profile",
                    app_id="L1", stage_id="stage001", pool="cpu_common",
                    settings=manual_settings() if settings is None else settings)
        args.update(changes)
        return make_profile(self.catalog, **args)

    def force_category(self, category):
        settings = manual_settings()
        settings["category_weights"] = {key: str(int(key == category)) for key in CATEGORIES}
        return settings

    def test_catalog_hash_physical_identity_and_auto_low(self):
        import json
        source = json.loads(self.source.read_text(encoding="utf-8"))
        self.assertEqual(self.catalog["source_sha256"], SOURCE_SHA256)
        self.assertEqual(self.catalog["physical_platform"], source["platform"])
        self.assertTrue(source["execution_rules"]["idle_holds_last_opp"])
        self.assertFalse(self.catalog["execution_rules"]["idle_holds_last_opp"])
        self.assertEqual(self.catalog["execution_rules"]["idle_policy"], "auto_low_immediate_v1")
        self.assertEqual(self.catalog["execution_rules"]["idle_delay_ms"], "0")

    def test_source_hash_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.json"
            path.write_bytes(self.source.read_bytes() + b"\n")
            with self.assertRaisesRegex(ProfileError, "P0_SOURCE_HASH_MISMATCH"):
                load_catalog(path)

    def test_shared_cpu_profiles_and_q_not_scaled(self):
        for category in CATEGORIES:
            with self.subTest(category=category):
                result = self.make(self.force_category(category))
                physical = result["physical_profile"]
                prototype = self.catalog["prototypes"][physical["prototype_id"]]["units"]
                units = result["time_profile"]["units"]
                self.assertEqual(units["CPU1"], units["CPU2"])
                multiplier = Fraction(result["trace"]["multiplier"])
                for unit, row in physical["units"].items():
                    self.assertEqual(Fraction(row["d_ref_ms"]),
                                     Fraction(prototype[unit]["d_ref_ms"]) * multiplier)
                    self.assertEqual(row["alpha"], prototype[unit]["alpha"])
                    self.assertEqual(row["q_ref_W"], prototype[unit]["q_ref_W"])
                    self.assertEqual(set(units[unit]["legal_opps"]), {"H", "M", "L"})

    def test_all_six_cpu_prototypes_are_explicitly_selectable(self):
        for prototype in CPU_PROTOTYPES:
            with self.subTest(prototype=prototype):
                settings = self.force_category("cpu_only")
                settings["cpu_prototype_weights"] = {key: str(int(key == prototype))
                                                      for key in CPU_PROTOTYPES}
                self.assertEqual(self.make(settings)["trace"]["prototype_id"], prototype)

    def test_specialization_removes_only_cpu_and_preserves_gpu_npu(self):
        for category, unit in (("gpu_friendly", "GPU0"), ("npu_friendly", "NPU0")):
            with self.subTest(category=category):
                settings = self.force_category(category)
                settings["specialization_probabilities"][category] = "1"
                ordinary = self.make(settings)
                specialized = self.make(settings, pool="heterogeneous")
                self.assertEqual(set(specialized["time_profile"]["units"]), {unit})
                self.assertEqual(specialized["time_profile"]["units"][unit],
                                 ordinary["time_profile"]["units"][unit])
                self.assertEqual(specialized["trace"]["removed_units"], ["CPU1", "CPU2"])
                self.assertFalse(ordinary["trace"]["specialized"])

    def test_zero_specialization_keeps_support(self):
        settings = self.force_category("gpu_friendly")
        settings["specialization_probabilities"]["gpu_friendly"] = "0"
        result = self.make(settings, pool="heterogeneous")
        self.assertEqual(set(result["time_profile"]["units"]), {"CPU1", "CPU2", "GPU0"})

    def test_no_mutation_determinism_and_call_order(self):
        settings, catalog_before = manual_settings(), deepcopy(self.catalog)
        before, first = deepcopy(settings), self.make(settings)
        self.make(settings, stage_id="unrelated-slot")
        self.assertEqual(first, self.make(settings))
        self.assertEqual(settings, before)
        self.assertEqual(self.catalog, catalog_before)

    def test_named_substreams_separate_namespace_root_and_purpose(self):
        slot = dict(namespace="manual-fixture", seed=71, root_id="manual-root", purpose="category",
                    app_id="L1", stage_id="p001", axis="fixed_stage_identity")
        first = substream_digest(**slot)
        for field in ("namespace", "root_id", "purpose", "app_id", "stage_id", "axis"):
            with self.subTest(field=field):
                other = dict(slot)
                other[field] += "-changed"
                self.assertNotEqual(first, substream_digest(**other))

    def test_explicit_missing_extra_and_float_settings_rejected(self):
        for key in manual_settings():
            with self.subTest(missing=key):
                settings = manual_settings()
                del settings[key]
                with self.assertRaises(ProfileError):
                    self.make(settings)
        settings = manual_settings()
        settings["topology_default"] = "diamond"
        with self.assertRaises(ProfileError):
            self.make(settings)
        settings = manual_settings()
        settings["category_weights"]["cpu_only"] = 0.25
        with self.assertRaises(ProfileError):
            self.make(settings)
        with self.assertRaises(ProfileError):
            self.make(seed=True)
        with self.assertRaises(ProfileError):
            self.make(pool="unknown")

    def test_workload_quantization_range_and_no_hidden_scale(self):
        result = self.make()
        value = Fraction(result["trace"]["multiplier"])
        self.assertGreaterEqual(value, Fraction(1, 2))
        self.assertLessEqual(value, Fraction(2))
        self.assertEqual((value * 1000).denominator, 1)
        self.assertFalse(result["trace"]["random_key_includes_scale_or_topology"])
        self.assertEqual(result["trace"]["slot"]["axis"], "fixed_stage_identity")


if __name__ == "__main__":
    unittest.main()
