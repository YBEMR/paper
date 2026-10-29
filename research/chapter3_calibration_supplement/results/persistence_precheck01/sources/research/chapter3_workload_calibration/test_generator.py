"""Manual workload-transform fixtures, independent of all calibration roots."""

from copy import deepcopy
from fractions import Fraction
from pathlib import Path
import unittest
from unittest.mock import patch

from research.chapter3_deadline_reference.contract import ContractError, duration
from research.chapter3_deadline_reference.scheduler import (
    build_references, build_timetable, project_references)
from research.chapter3_deadline_reference.checker import check_timetable
from research.chapter3_deadline_reference.deadlines import (
    make_deadlines, inherit_deadlines, compare_deadlines)
from .profiles import load_catalog
from .generator import (build_base, transform, subset, inherited_mapping,
                        request_sources, statistics, stamp, validate_bundle,
                        validate_transform)
from .test_profiles import manual_settings
from .test_topology import fixture_settings


def generator_fixture_settings():
    return {"profiles": manual_settings(), "topology": fixture_settings(),
            "reference_topology": "branch_join", "relative_release_factor": "0.1",
            "s7_release_rule": "synchronous_same_application", "split_rule": "equal_contiguous"}


class GeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog(Path(__file__).resolve().parents[1] /
                                   "chapter3_experiments" / "config_v01.json")
        cls.settings = generator_fixture_settings()
        cls.a = build_base(cls.catalog, root_id="manual-generator-A", namespace="manual-fixture",
                           seed=73, scene_pool="A", compatibility_pool="cpu_common", scale=6,
                           settings=cls.settings)
        cls.b = build_base(cls.catalog, root_id="manual-generator-B", namespace="manual-fixture",
                           seed=73, scene_pool="B", compatibility_pool="cpu_common", scale=6,
                           settings=cls.settings)
        cls.references = build_references(cls.a["time_contract"])
        cls.deadlines = make_deadlines(cls.a["time_contract"], cls.references["timetables"]["H"],
                                       beta="1.3", reference_topology_id="branch_join")

    def derived(self, axis, value):
        return transform(self.a, axis, value=value, settings=self.settings)

    def assert_inherited(self, child):
        receipt = inherit_deadlines(self.a["time_contract"], self.deadlines, child["time_contract"],
                                    request_sources=request_sources(self.a, child))
        self.assertEqual(receipt["deadline_origin_hash"], self.deadlines["deadline_origin_hash"])
        for sid, rows in self.deadlines["requests"].items():
            if sid in receipt["requests"]:
                for rid, row in rows.items():
                    self.assertEqual(receipt["requests"][sid][rid], row)
        return receipt

    def test_A_eight_scenes_have_relative_not_global_release_shifts(self):
        delta = Fraction(self.a["provenance"]["delta_ms"])
        self.assertGreaterEqual(delta, 5)
        self.assertEqual((delta / 5).denominator, 1)
        seen = set()
        for i, scene in enumerate(self.a["time_contract"]["scenarios"]):
            releases = {r["id"]: Fraction(r["release_ms"]) for r in scene["requests"]}
            self.assertEqual(releases["L1.r1"], 0)
            self.assertEqual(releases[f"S{1 + i % 2}.r1"], (i // 2) * delta)
            self.assertEqual(scene["weight"], "1/8")
            key = tuple(sorted(releases.items()))
            self.assertNotIn(key, seen)
            seen.add(key)
        self.assertEqual(len(seen), 8)

    def test_B_eight_scenes_match_declared_app_pairs_and_offsets(self):
        expected = [("L1", "S1", 0), ("L1", "S2", 0), ("L2", "S1", 0),
                    ("L2", "S2", 0), ("L1", "S3", 0), ("L2", "S3", 0),
                    ("L1", "S1", 1), ("L2", "S2", 1)]
        delta = Fraction(self.b["provenance"]["delta_ms"])
        for scene, (large, small, offset) in zip(self.b["time_contract"]["scenarios"], expected):
            releases = {r["id"]: Fraction(r["release_ms"]) for r in scene["requests"]}
            self.assertEqual(releases, {large + ".r1": Fraction(0), small + ".r1": offset * delta})
        self.assertEqual(statistics(self.b)["family_application_identities"], 5)
        for app, spec in self.b["applications"].items():
            self.assertEqual(len(spec["nodes"]), 4 if app.startswith("L") else 2)

    def test_release_offset_uses_fastest_H_diamond_CP_not_reference_schedule(self):
        for bundle in (self.a, self.b):
            data, cps = bundle["time_contract"], []
            for app, spec in bundle["applications"].items():
                if not app.startswith("L"):
                    continue
                times = [min(duration(data, node, unit, "H")
                             for unit in data["stage_profiles"][node]["units"])
                         for node in spec["nodes"]]
                cp = times[0] + max(times[1], times[2]) + times[3]
                cps.append(cp)
                self.assertEqual(Fraction(bundle["provenance"]["base_cp_ms"][app]), cp)
            quotient = Fraction(1, 10) * max(cps) / 5
            expected_delta = 5 * max(1, -(-quotient.numerator // quotient.denominator))
            self.assertEqual(Fraction(bundle["provenance"]["delta_ms"]), expected_delta)

    def test_S2_appends_real_nodes_and_work_preserving_old_profiles_and_edges(self):
        parent = self.a
        for scale in (12, 24):
            child = build_base(self.catalog, root_id="manual-generator-A", namespace="manual-fixture",
                               seed=73, scene_pool="A", compatibility_pool="cpu_common", scale=scale,
                               settings=self.settings, parent=parent)
            self.assertTrue(validate_transform(parent, child))
            for sid, profile in parent["time_contract"]["stage_profiles"].items():
                self.assertEqual(profile, child["time_contract"]["stage_profiles"][sid])
                self.assertEqual(parent["profile_traces"][sid], child["profile_traces"][sid])
            for app, spec in parent["applications"].items():
                self.assertLess(set(spec["nodes"]), set(child["applications"][app]["nodes"]))
                self.assertLessEqual(set(map(tuple, spec["edges"])),
                                     set(map(tuple, child["applications"][app]["edges"])))
            oldstats, newstats = statistics(parent)["scenes"], statistics(child)["scenes"]
            for sid in oldstats:
                self.assertEqual(newstats[sid]["execution_instances"], scale)
                self.assertEqual(newstats[sid]["requests"], 2)
                self.assertGreater(Fraction(newstats[sid]["work_units"]), Fraction(oldstats[sid]["work_units"]))
            parent = child

    def test_S3_conserves_every_device_OPP_duration_activity_energy_and_work(self):
        original = self.a["time_contract"]
        for factor in (2, 4):
            with self.subTest(factor=factor):
                child = self.derived("S3", factor)
                data, mapping = child["time_contract"], child["transform"]["child_to_parent"]
                for sid, profile in original["stage_profiles"].items():
                    children = [node for node, parent in mapping.items() if parent == sid]
                    self.assertEqual(len(children), factor)
                    self.assertEqual(sum(Fraction(data["stage_profiles"][node]["work_units"])
                                         for node in children), Fraction(profile["work_units"]))
                    self.assertEqual(sum(Fraction(child["physical_profiles"][node]["work_units"])
                                         for node in children), Fraction(profile["work_units"]))
                    for unit in profile["units"]:
                        domain = next(u["domain_id"] for u in original["platform"]["units"] if u["id"] == unit)
                        opps = self.a["physical_platform"]["domains"][domain]["opps"]
                        q = Fraction(self.a["physical_profiles"][sid]["units"][unit]["q_ref_W"])
                        for opp in ("H", "M", "L"):
                            with self.subTest(parent=sid, unit=unit, opp=opp):
                                q_at_opp = q * (Fraction(opps[opp]["voltage_V"]) /
                                                Fraction(opps["H"]["voltage_V"])) ** 2 * (
                                                    Fraction(opps[opp]["frequency_GHz"]) /
                                                    Fraction(opps["H"]["frequency_GHz"]))
                                self.assertEqual(sum(duration(data, node, unit, opp) for node in children),
                                                 duration(original, sid, unit, opp))
                                self.assertEqual(sum(duration(data, node, unit, opp) * q_at_opp / 1000
                                                     for node in children),
                                                 duration(original, sid, unit, opp) * q_at_opp / 1000)
                        for node in children:
                            self.assertEqual(set(data["stage_profiles"][node]["units"]), set(profile["units"]))
                            self.assertEqual(Fraction(child["physical_profiles"][node]["units"][unit]["q_ref_W"]), q)
                self.assert_inherited(child)
                deployment = inherited_mapping(self.references["mapping_record"]["mapping"], child)
                for node, parent in mapping.items():
                    self.assertEqual(deployment[node], self.references["mapping_record"]["mapping"][parent])

    def test_S3_edges_connect_parent_tail_to_successor_head(self):
        child = self.derived("S3", 2)
        original_scene = self.a["time_contract"]["scenarios"][0]
        derived_scene = child["time_contract"]["scenarios"][0]
        actual = set(map(tuple, derived_scene["dependencies"]))
        for left, right in original_scene["dependencies"]:
            self.assertIn((left[:-3] + ".p2.r1", right[:-3] + ".p1.r1"), actual)
        for stage in original_scene["stage_instances"]:
            root = stage["shared_stage_id"]
            self.assertIn((root + ".p1.r1", root + ".p2.r1"), actual)

    def test_S4_only_changes_dependencies_preserving_profiles_and_releases(self):
        for kind in ("serial", "layered"):
            with self.subTest(kind=kind):
                child = self.derived("S4", kind)
                self.assertEqual(child["time_contract"]["stage_profiles"], self.a["time_contract"]["stage_profiles"])
                self.assertEqual(child["physical_profiles"], self.a["physical_profiles"])
                changed = False
                for original, derived in zip(self.a["time_contract"]["scenarios"], child["time_contract"]["scenarios"]):
                    self.assertEqual({k: v for k, v in original.items() if k != "dependencies"},
                                     {k: v for k, v in derived.items() if k != "dependencies"})
                    changed |= original["dependencies"] != derived["dependencies"]
                self.assertTrue(changed)
                self.assertEqual(child["provenance"]["delta_ms"], self.a["provenance"]["delta_ms"])
                self.assert_inherited(child)

    def test_S5_scales_only_work_and_durations_and_keeps_absolute_deadlines(self):
        for factor in ("0.75", "1", "1.25"):
            with self.subTest(factor=factor):
                child = self.derived("S5", factor)
                self.assertEqual(child["time_contract"]["scenarios"], self.a["time_contract"]["scenarios"])
                self.assertEqual(child["physical_platform"], self.a["physical_platform"])
                for sid, source in self.a["time_contract"]["stage_profiles"].items():
                    changed = child["time_contract"]["stage_profiles"][sid]
                    self.assertEqual(Fraction(changed["work_units"]), Fraction(source["work_units"]) * Fraction(factor))
                    self.assertEqual(Fraction(child["physical_profiles"][sid]["work_units"]),
                                     Fraction(changed["work_units"]))
                    for unit, row in source["units"].items():
                        self.assertEqual(Fraction(changed["units"][unit]["d_ref_ms"]),
                                         Fraction(row["d_ref_ms"]) * Fraction(factor))
                        self.assertEqual(changed["units"][unit]["alpha"], row["alpha"])
                        self.assertEqual(child["physical_profiles"][sid]["units"][unit]["q_ref_W"],
                                         self.a["physical_profiles"][sid]["units"][unit]["q_ref_W"])
                self.assert_inherited(child)

    def test_S6_changes_only_four_entry_temperatures(self):
        child = self.derived("S6", "78")
        before, after = deepcopy(self.a["time_contract"]), deepcopy(child["time_contract"])
        for data in (before, after):
            data.pop("variant_id")
            data.pop("derivation")
        self.assertEqual(after["context"]["initial_temperature_C"], ["78"] * 4)
        after["context"]["initial_temperature_C"] = before["context"]["initial_temperature_C"]
        self.assertEqual(before, after)
        self.assert_inherited(child)

    def test_S7_preserves_shared_identities_synchronous_releases_and_deadlines(self):
        child = self.derived("S7", 2)
        receipt = self.assert_inherited(child)
        for original, derived in zip(self.a["time_contract"]["scenarios"], child["time_contract"]["scenarios"]):
            requests = {r["id"]: r for r in derived["requests"]}
            for request in original["requests"]:
                copy_id = request["id"][:-1] + "2"
                self.assertEqual(requests[copy_id]["release_ms"], request["release_ms"])
                self.assertEqual(receipt["requests"][derived["id"]][copy_id],
                                 receipt["requests"][derived["id"]][request["id"]])
            identities = {s["shared_stage_id"] for s in original["stage_instances"]}
            self.assertEqual({s["shared_stage_id"] for s in derived["stage_instances"]}, identities)
            self.assertEqual(len(derived["stage_instances"]), 2 * len(original["stage_instances"]))
            for sid in identities:
                self.assertEqual(sum(s["shared_stage_id"] == sid for s in derived["stage_instances"]), 2)
        mapping = inherited_mapping(self.references["mapping_record"]["mapping"], child)
        table = build_timetable(child["time_contract"], mapping, "H")
        self.assertEqual(check_timetable(child["time_contract"], table, required_opp="H")["state"],
                         "TIME_STRUCTURAL_VALID")
        comparison = compare_deadlines(child["time_contract"], table, receipt)
        self.assertEqual(comparison["thermal_status"], "NOT_EVALUATED")

    def test_E2_keeps_full_physical_platform_and_rejects_unsupported_specialist(self):
        child = self.derived("E2", ["CPU1", "CPU2"])
        self.assertEqual(child["physical_platform"], self.a["physical_platform"])
        self.assertEqual(len(child["time_contract"]["platform"]["units"]), 4)
        for scene in child["time_contract"]["scenarios"]:
            self.assertTrue(all(set(s["legal_units"]) <= {"CPU1", "CPU2"}
                                for s in scene["stage_instances"]))
        self.assert_inherited(child)
        settings = generator_fixture_settings()
        settings["profiles"]["category_weights"] = {key: str(int(key == "gpu_friendly"))
                                                     for key in settings["profiles"]["category_weights"]}
        settings["profiles"]["specialization_probabilities"]["gpu_friendly"] = "1"
        specialist = build_base(self.catalog, root_id="manual-specialist", namespace="manual-fixture",
                                 seed=73, scene_pool="A", compatibility_pool="heterogeneous", scale=6,
                                 settings=settings)
        with self.assertRaises(ContractError) as caught:
            transform(specialist, "E2", value=["CPU1", "CPU2"], settings=settings)
        self.assertEqual(caught.exception.code, "E2_RESOURCE_UNSUPPORTED")

    def test_S1_projects_without_scheduler_or_mapping_calls(self):
        for count in (1, 2, 4, 6, 8):
            with self.subTest(count=count):
                child = subset(self.a, count)
                with patch("research.chapter3_deadline_reference.scheduler.choose_mapping",
                           side_effect=AssertionError("S1 remapped")), patch(
                               "research.chapter3_deadline_reference.scheduler.build_timetable",
                               side_effect=AssertionError("S1 rescheduled")):
                    projected = project_references(self.a["time_contract"], self.references, child["time_contract"])
                self.assertEqual(projected["mapping_origin_hash"], self.references["mapping_origin_hash"])
                expected = {f"C{i}" for i in range(1, count + 1)}
                for opp in ("H", "M", "L"):
                    self.assertEqual(set(projected["timetables"][opp]["scenes"]), expected)
                    for sid in expected:
                        self.assertEqual(projected["timetables"][opp]["scenes"][sid],
                                         self.references["timetables"][opp]["scenes"][sid])
                self.assertTrue(all(Fraction(s["weight"]) == Fraction(1, count)
                                    for s in child["time_contract"]["scenarios"]))
                self.assert_inherited(child)

    def test_formal_mapping_is_never_fixed_and_hash_tampering_is_rejected(self):
        for bundle in (self.a, self.b, subset(self.a, 2), self.derived("S7", 2)):
            self.assertIsNone(bundle["formal_mapping_constraint"])
            self.assertIsNone(bundle["formal_initial_solution"])
            self.assertIsNone(bundle["evaluation_window_ms"])
            self.assertTrue(validate_bundle(bundle))
        tampered = deepcopy(self.a)
        tampered["formal_mapping_constraint"] = {"L1.s0001": "CPU1"}
        with self.assertRaises(ContractError):
            stamp(tampered)
        tampered = deepcopy(self.a)
        tampered["time_contract"]["scenarios"][0]["requests"][0]["release_ms"] = "5"
        with self.assertRaises(ContractError):
            validate_bundle(tampered)

    def test_transform_does_not_mutate_parent_or_settings(self):
        original, settings = deepcopy(self.a), deepcopy(self.settings)
        self.derived("S3", 2)
        self.derived("S7", 2)
        self.derived("S5", "1.25")
        self.assertEqual(self.a, original)
        self.assertEqual(self.settings, settings)

    def test_physical_work_metadata_cannot_diverge_from_time_profile(self):
        child = self.derived("S5", "1.25")
        sid = next(iter(child["physical_profiles"]))
        child["physical_profiles"][sid]["work_units"] = "999"
        with self.assertRaises(ContractError):
            stamp(child)

    def test_S5_tampered_q_alpha_and_scale_cannot_pass_transform_check(self):
        for corruption in ("power", "alpha", "factor"):
            with self.subTest(corruption=corruption):
                child = self.derived("S5", "1.25")
                sid = next(iter(child["time_contract"]["stage_profiles"]))
                unit = next(iter(child["time_contract"]["stage_profiles"][sid]["units"]))
                if corruption == "power":
                    child["physical_profiles"][sid]["units"][unit]["q_ref_W"] = "999"
                elif corruption == "alpha":
                    child["time_contract"]["stage_profiles"][sid]["units"][unit]["alpha"] = "1/17"
                    child["physical_profiles"][sid]["units"][unit]["alpha"] = "1/17"
                else:
                    child["transform"]["factor"] = "3/4"
                stamp(child)
                with self.assertRaises(ContractError):
                    validate_transform(self.a, child)

    def test_S7_wrong_release_missing_copy_or_dependency_is_rejected(self):
        for corruption in ("release", "copy_count", "edge"):
            with self.subTest(corruption=corruption):
                child = self.derived("S7", 2)
                scene = child["time_contract"]["scenarios"][0]
                copied = next(r for r in scene["requests"] if r["id"].endswith(".r2"))
                if corruption == "release":
                    copied["release_ms"] = str(Fraction(copied["release_ms"]) + 5)
                elif corruption == "copy_count":
                    removed = set(copied["stage_instance_ids"])
                    scene["requests"] = [r for r in scene["requests"] if r["id"] != copied["id"]]
                    scene["stage_instances"] = [s for s in scene["stage_instances"] if s["id"] not in removed]
                    scene["dependencies"] = [e for e in scene["dependencies"]
                                             if not (set(e) & removed)]
                else:
                    edge = next(e for e in scene["dependencies"] if e[0].endswith(".r2"))
                    scene["dependencies"].remove(edge)
                stamp(child)
                with self.assertRaises(ContractError):
                    validate_transform(self.a, child)


if __name__ == "__main__":
    unittest.main()
