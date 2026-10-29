"""Manual clock/manifest/evaluation checks. No calibration root is constructed."""

from copy import deepcopy
from collections import Counter
from fractions import Fraction
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from .configuration import approved_configuration, planned_calls, validate_manifest
from .generator import build_base, transform
from .evaluation import evaluate_condition
from .profiles import load_catalog
from .runtime import decide_call_state, execute, read_json, write_json
from .test_generator import generator_fixture_settings


class ExecutionTests(unittest.TestCase):
    def test_manifest_has_exact_160_480_72_and_disjoint_namespaces(self):
        config = approved_configuration()
        manifest = planned_calls(config)
        self.assertTrue(validate_manifest(manifest))
        self.assertEqual(Counter(c["kind"] for c in manifest["calls"]),
                         {"base": 72, "S4": 48, "S5": 12, "S7": 12, "S3": 16})
        self.assertEqual(len({c["condition_id"] for c in manifest["calls"]}), 160)
        self.assertEqual(len({c["root_id"] for c in manifest["calls"]}), 24)
        self.assertEqual(manifest["planned_timetable_constructions"], 480)
        config["namespace"] = config["formal_namespace_reserved"]
        with self.assertRaises(ValueError):
            planned_calls(config)

    def test_manifest_parents_precede_children_and_all_strata_have_two_roots(self):
        manifest = planned_calls(approved_configuration())
        seen, root_strata = set(), {}
        for call in manifest["calls"]:
            if call["parent_condition_id"]:
                self.assertIn(call["parent_condition_id"], seen)
            seen.add(call["condition_id"])
            root_strata[call["root_id"]] = (call["focus_scale"], call["scene_pool"], call["compatibility_pool"])
        self.assertEqual(set(Counter(root_strata.values()).values()), {2})
        self.assertEqual(len(Counter(root_strata.values())), 12)

    def test_manifest_drift_cannot_be_restamped(self):
        m = planned_calls(approved_configuration())
        m["configuration"]["seed"] += 1
        m = planned_calls(m["configuration"])
        with self.assertRaises(ValueError):
            validate_manifest(m)

    def test_acceptance_rejects_failure_late_scope_violation_or_missing_receipt(self):
        good = {"state": "COMPLETE", "elapsed_s": 0.1, "denied_imports": [], "denied_events": []}
        self.assertEqual(decide_call_state(0, good, 0.2, 60), "COMPLETE")
        for code, receipt, elapsed in ((1, good, .2), (0, None, .2), (0, good, 61),
                                      (0, {**good, "elapsed_s": 61}, .2),
                                      (0, {**good, "state": "FAILED"}, .2),
                                      (0, {**good, "denied_events": ["subprocess.Popen"]}, .2)):
            with self.subTest(code=code, receipt=receipt, elapsed=elapsed):
                self.assertNotEqual(decide_call_state(code, receipt, elapsed, 60), "COMPLETE")

    def test_mock_launch_stops_on_first_failure_and_claim_is_one_shot(self):
        manifest = planned_calls(approved_configuration())
        manifest["calls"] = manifest["calls"][:2]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            freeze, out = root / "freeze", root / "execution"
            freeze.mkdir()
            out.mkdir()
            write_json(freeze / "manifest.json", manifest)
            calls = []

            class FakeProcess:
                def __init__(self, args, **kwargs):
                    calls.append(args)
                def wait(self, timeout):
                    return 2

            with patch("research.chapter3_workload_calibration.runtime.check_frozen", return_value=manifest), \
                 patch("research.chapter3_workload_calibration.runtime.fresh_output", return_value=out), \
                 patch("research.chapter3_workload_calibration.runtime.protected_files", return_value={}), \
                 patch("research.chapter3_workload_calibration.runtime.subprocess.Popen", FakeProcess):
                self.assertEqual(execute(freeze, out), 2)
                result = read_json(out / "batch_result.json")
                self.assertEqual(result["consumed_conditions"], 1)
                self.assertEqual(result["completed_conditions"], 0)
                self.assertEqual(len(calls), 1)
                with self.assertRaises(FileExistsError):
                    execute(freeze, out)
                self.assertEqual(len(calls), 1)

    def test_mock_launch_success_keeps_exact_order_and_counts(self):
        manifest = planned_calls(approved_configuration())
        manifest["calls"] = manifest["calls"][:2]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            freeze, out = root / "freeze", root / "execution"
            freeze.mkdir()
            out.mkdir()
            write_json(freeze / "manifest.json", manifest)
            seen = []

            class FakeProcess:
                def __init__(self, args, **kwargs):
                    index = int(args[args.index("--index") + 1])
                    seen.append(index)
                    target = out / manifest["calls"][index]["condition_id"]
                    target.mkdir()
                    write_json(target / "result.json", {"state": "COMPLETE", "elapsed_s": .01,
                               "counters": {"mapping_constructions": 1, "timetable_constructions": 3},
                               "denied_imports": [], "denied_events": []})
                def wait(self, timeout):
                    return 0

            with patch("research.chapter3_workload_calibration.runtime.check_frozen", return_value=manifest), \
                 patch("research.chapter3_workload_calibration.runtime.fresh_output", return_value=out), \
                 patch("research.chapter3_workload_calibration.runtime.protected_files", return_value={}), \
                 patch("research.chapter3_workload_calibration.runtime.subprocess.Popen", FakeProcess):
                self.assertEqual(execute(freeze, out), 0)
                result = read_json(out / "batch_result.json")
                self.assertEqual(seen, [0, 1])
                self.assertEqual(result["counters"]["timetable_constructions"], 6)

    def test_manual_base_and_derived_do_not_remap_or_refit_deadlines(self):
        config = approved_configuration()
        catalog = load_catalog(Path(__file__).resolve().parents[1] / "chapter3_experiments/config_v01.json")
        settings = generator_fixture_settings()
        base = build_base(catalog, root_id="manual-execution", namespace="manual-fixture", seed=17,
                          scene_pool="A", compatibility_pool="cpu_common", scale=6, settings=settings)
        phases = []
        record = evaluate_condition(base, config, progress=lambda p, c: phases.append((p, dict(c))))
        self.assertEqual(record["counters"]["timetable_constructions"], 3)
        self.assertEqual(record["counters"]["mapping_constructions"], 1)
        self.assertEqual(record["counters"]["S1_projections"], 5)
        child = transform(base, "S7", value=2, settings=settings)
        with patch("research.chapter3_workload_calibration.evaluation.choose_mapping", side_effect=AssertionError("remap")):
            derived = evaluate_condition(child, config, parent=record, progress=lambda *args: None)
        self.assertEqual(derived["counters"]["mapping_constructions"], 0)
        self.assertEqual(derived["counters"]["timetable_constructions"], 3)
        for beta in record["deadlines"]:
            self.assertEqual(record["deadlines"][beta]["deadline_origin_hash"],
                             derived["deadlines"][beta]["deadline_origin_hash"])
        for row in derived["thresholds"]["L"]["per_request"]:
            sid, rid = row["scene"], row["request"]
            r = derived["deadlines"]["1"]["requests"][sid][rid]
            f = derived["reference"]["checks"]["L"]["completions_ms"][sid][rid]
            self.assertEqual(Fraction(row["beta_required"]),
                             (Fraction(f) - Fraction(r["release_ms"])) / Fraction(r["relative_deadline_ms"]))
        self.assertIsNone(derived["beta_selected"])
        self.assertEqual(derived["thermal_status"], "NOT_EVALUATED")


if __name__ == "__main__":
    unittest.main()
