"""Archive-only inventory checks; never generate a C-root workload."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from .manifest import make_manifest, validate_manifest, planned_conditions, PINS


class ManifestTests(unittest.TestCase):
    def test_coverage_and_order(self):
        rows = planned_conditions()
        self.assertEqual(len(rows), 28)
        self.assertEqual(len({x["condition_id"] for x in rows}), 28)
        self.assertEqual(len({x["root_id"] for x in rows}), 20)
        self.assertEqual([x["root_id"] for x in rows[:16]], [f"C{i:02d}" for i in range(9, 25)])
        self.assertEqual([x["root_id"] for x in rows[16:]], [f"C{i:02d}" for i in range(2, 25, 2)])
        self.assertEqual({x["scale"] for x in rows[:16]}, {24, 96})
        self.assertEqual(sum(3 * 8 for _ in rows), 672)
        for row in rows:
            self.assertEqual(row["parent_id"], f'{row["root_id"]}__base_{row["scale"]}')

    def test_real_archive_manifest_is_only_an_inventory(self):
        repo = Path(__file__).resolve().parents[2]
        with patch("research.chapter3_workload_calibration.generator.build_base", side_effect=AssertionError("generation")), \
             patch("research.chapter3_deadline_reference.scheduler.build_timetable", side_effect=AssertionError("schedule")):
            manifest = make_manifest(repo)
        self.assertFalse(manifest["execution_authorized"])
        self.assertIsNone(manifest["execution_limits"]["condition_seconds"])
        self.assertIsNone(manifest["execution_limits"]["batch_seconds"])
        self.assertIsNone(manifest["beta_selected"])
        self.assertTrue(all(v == 0 for v in manifest["consumed"].values()))
        self.assertEqual(len(manifest["archive_references"]), 64)
        self.assertEqual(manifest["parent_namespace"], "ch3-calibration-v1")
        self.assertTrue(validate_manifest(manifest, repo))

    def test_no_permission_or_budget_can_be_smuggled_into_manifest(self):
        repo = Path(__file__).resolve().parents[2]
        manifest = make_manifest(repo)
        # Recompare against one immutable independently generated expectation.
        with patch("research.chapter3_calibration_adjustment.manifest.make_manifest", return_value=manifest):
            for field, value in (("execution_authorized", True), ("beta_selected", "1.3")):
                bad = deepcopy(manifest)
                bad[field] = value
                with self.assertRaises(ValueError):
                    validate_manifest(bad, repo)
            bad = deepcopy(manifest)
            bad["calls"][0]["parent_id"] = "C09__base_96"
            with self.assertRaises(ValueError):
                validate_manifest(bad, repo)

    def test_pinned_archive_drift_rejected_before_reading_workloads(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = root / next(iter(PINS))
            first.parent.mkdir(parents=True)
            first.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "PINNED_ARCHIVE_CHANGED"):
                make_manifest(root)
