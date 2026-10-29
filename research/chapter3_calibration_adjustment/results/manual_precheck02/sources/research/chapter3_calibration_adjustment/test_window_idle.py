"""Hand-written window/provenance and exact idle-box tests; no real tasks."""

from copy import deepcopy
from fractions import Fraction
import json
import unittest

from research.chapter3_deadline_reference.contract import ContractError, content_hash
from research.chapter3_deadline_reference.deadlines import inherit_deadlines
from research.chapter3_workload_calibration.generator import request_sources, subset, transform

from .fixtures import manual_evidence
from .transforms import derive_branch_multi, derive_staggered
from .window_policy import ceil_grid_ms, make_window_receipt, validate_window_receipt
from .idle_certificate import (SOURCE_PATH, SOURCE_SHA256, POLICY,
                               make_idle_certificate, validate_idle_certificate)


def inherited_evidence(base, bundle):
    """Copy deadline arithmetic only; do not reconstruct derived H/M/L tables."""
    deadlines = {key: inherit_deadlines(base["workload"]["time_contract"], receipt,
                                        bundle["time_contract"],
                                        request_sources=request_sources(base["workload"], bundle))
                 for key, receipt in base["deadlines"].items()}
    return {"workload": bundle, "deadlines": deadlines}


def s7_members(base):
    sync = transform(base["workload"], "S7", value=2,
                     settings={"s7_release_rule": "synchronous_same_application"})
    return {"single": base, "synchronous": inherited_evidence(base, sync),
            "staggered": inherited_evidence(base, derive_staggered(base))}


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = manual_evidence()

    def test_exact_ceiling_does_not_add_at_boundary(self):
        for value, expected in (("0", "0"), ("10", "10"), ("101/10", "15"),
                                ("4000001/10000", "405"), ("1500", "1500")):
            with self.subTest(value=value):
                self.assertEqual(ceil_grid_ms(value), expected)
        with self.assertRaises(ContractError):
            ceil_grid_ms("-1")

    def test_s7_three_roles_share_window_and_preserve_old_bundle(self):
        before = deepcopy(self.base)
        members = s7_members(self.base)
        receipt = make_window_receipt("manual-S7", "S7", members, beta="1.3", baseline=self.base)
        latest = max(Fraction(r["deadline_ms"]) for m in members.values()
                     for reqs in m["deadlines"]["13/10"]["requests"].values() for r in reqs.values())
        self.assertEqual(receipt["window_ms"], ceil_grid_ms(latest))
        self.assertEqual({r["window_ms"] for r in receipt["members"].values()}, {receipt["window_ms"]})
        self.assertTrue(validate_window_receipt(receipt, "manual-S7", "S7", members,
                                                beta="1.3", baseline=self.base))
        self.assertEqual(self.base, before)
        self.assertIsNone(self.base["workload"]["evaluation_window_ms"])
        self.assertFalse(receipt["formal_input_exported"])

    def test_s7_roles_missing_or_swapped_rejected(self):
        members = s7_members(self.base)
        for change in ("missing", "swapped"):
            altered = deepcopy(members)
            if change == "missing":
                del altered["staggered"]
            else:
                altered["synchronous"], altered["staggered"] = altered["staggered"], altered["synchronous"]
            with self.subTest(change=change), self.assertRaises(ContractError):
                make_window_receipt("manual", "S7", altered, beta="1.3", baseline=self.base)

    def test_candidate_completion_time_not_a_window_input(self):
        members = s7_members(self.base)
        receipt = make_window_receipt("manual-S7", "S7", members, beta="1.3", baseline=self.base)
        changed = deepcopy(members)
        # This is deliberately untrusted candidate metadata, not the anchored
        # baseline H record. It may not resize a deadline-based window.
        changed["staggered"]["candidate_completion_ms"] = "999999"
        changed["staggered"]["reference"] = {"candidate_only": "not used for W"}
        self.assertEqual(receipt, make_window_receipt("manual-S7", "S7", changed,
                                                      beta="1.3", baseline=self.base))

    def test_tampered_deadline_with_recomputed_hash_rejected(self):
        members = s7_members(self.base)
        altered = members["staggered"]["deadlines"]["13/10"]
        scene = sorted(altered["requests"])[0]
        rid = next(r for r in altered["requests"][scene] if r.endswith(".r2"))
        row = altered["requests"][scene][rid]
        row["deadline_ms"] = str(Fraction(row["deadline_ms"]) + 5)
        row["relative_deadline_ms"] = str(Fraction(row["relative_deadline_ms"]) + 5)
        altered["receipt_hash"] = content_hash({k: v for k, v in altered.items() if k != "receipt_hash"})
        with self.assertRaises(ContractError):
            make_window_receipt("manual", "S7", members, beta="1.3", baseline=self.base)

    def test_missing_beta_rejected_no_formal_default(self):
        with self.assertRaises(ContractError):
            make_window_receipt("manual", "S2", {"base": self.base}, beta="1.4", baseline=self.base)

    def test_s4_uses_base_deadlines_without_new_reference_table(self):
        derived = inherited_evidence(self.base, derive_branch_multi(self.base["workload"]))
        receipt = make_window_receipt("manual-S4", "S4", {"multi": derived},
                                      beta="1.3", baseline=self.base)
        baseline = make_window_receipt("manual-base", "S2", {"base": self.base},
                                       beta="1.3", baseline=self.base)
        self.assertEqual(receipt["window_ms"], baseline["window_ms"])
        self.assertEqual(receipt["baseline_deadline_receipt_hash"], baseline["baseline_deadline_receipt_hash"])
        self.assertNotIn("reference", derived)

    def test_s1_full_eight_scene_anchor_and_all_projections(self):
        base = manual_evidence(offsets=tuple(str(n * 15) for n in range(8)))
        members = {str(n): inherited_evidence(base, subset(base["workload"], n)) for n in (1, 2, 4, 6, 8)}
        result = make_window_receipt("manual-S1", "S1", members, beta="1.3", baseline=base)
        expected = make_window_receipt("manual-base", "S2", {"base": base}, beta="1.3", baseline=base)
        self.assertEqual(result["window_ms"], expected["window_ms"])
        self.assertEqual(result["members"]["1"]["window_ms"], result["members"]["8"]["window_ms"])
        del members["8"]
        with self.assertRaises(ContractError):
            make_window_receipt("manual-S1", "S1", members, beta="1.3", baseline=base)

    def test_s2_mixed_scale_rejected(self):
        other = manual_evidence(large_nodes=16, small_nodes=8)
        with self.assertRaises(ContractError):
            make_window_receipt("manual-S2", "S2", {"one": self.base, "two": other},
                                 beta="1.3", baseline=self.base)

    def test_window_receipt_identity_and_value_bound(self):
        members = {"base": self.base}
        receipt = make_window_receipt("manual-S2", "S2", members, beta="1.3", baseline=self.base)
        altered = deepcopy(receipt)
        altered["window_ms"] = str(Fraction(altered["window_ms"]) + 5)
        altered["receipt_hash"] = content_hash({k: v for k, v in altered.items() if k != "receipt_hash"})
        with self.assertRaises(ContractError):
            validate_window_receipt(altered, "manual-S2", "S2", members, beta="1.3", baseline=self.base)
        with self.assertRaises(ContractError):
            validate_window_receipt(receipt, "different-group", "S2", members,
                                    beta="1.3", baseline=self.base)

    def test_group_specific_windows_must_have_distinct_identity(self):
        base_window = make_window_receipt("base-group", "S2", {"base": self.base},
                                          beta="1.3", baseline=self.base)
        s7_window = make_window_receipt("S7-group", "S7", s7_members(self.base),
                                        beta="1.3", baseline=self.base)
        self.assertGreater(Fraction(s7_window["window_ms"]), Fraction(base_window["window_ms"]))
        self.assertNotEqual(base_window["receipt_hash"], s7_window["receipt_hash"])


class IdleBoxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))

    def certificate(self, config=None, **overrides):
        options = {"source_sha256": SOURCE_SHA256, "policy": POLICY, "lower_C": "20", "upper_C": "80"}
        options.update(overrides)
        return make_idle_certificate(self.config if config is None else config, **options)

    def test_exact_four_node_boundary_values(self):
        receipt = self.certificate()
        self.assertEqual(list(map(Fraction, receipt["lower_face_min_net_heat_W"])),
                         list(map(Fraction, (".49", ".49", ".68", ".485"))))
        self.assertEqual(list(map(Fraction, receipt["upper_face_max_net_heat_W"])),
                         list(map(Fraction, ("-1.79", "-1.79", "-2.68", "-2.335"))))
        self.assertEqual(receipt["thermal_integrations"], 0)
        self.assertFalse(receipt["schedule_safe_certified"])
        self.assertFalse(receipt["energy_after_window_included"])

    def test_shared_cpu_baseline_is_counted_once_and_slopes_are_local(self):
        receipt = self.certificate()
        bases, slopes = map(lambda key: list(map(Fraction, receipt[key])),
                            ("baseline_by_node_W", "local_slope_W_per_K"))
        self.assertEqual(bases[:2], [Fraction(".3")] * 2)
        self.assertEqual(sum(bases[:2]), Fraction(receipt["baseline_by_group_W"]["CPU"]))
        self.assertEqual(slopes[:2], [Fraction(".002")] * 2)
        self.assertEqual(Fraction(receipt["external_common_power_W"]), Fraction(".3"))
        self.assertEqual(receipt["external_injected_heat_W"], "0")

    def test_frozen_source_digest_cannot_be_asserted_by_caller(self):
        changed = deepcopy(self.config)
        changed["platform"]["domains"]["GPU"]["baseline_W"]["L"] = ".41"
        with self.assertRaises(ContractError):
            self.certificate(changed)
        with self.assertRaises(ContractError):
            self.certificate(source_sha256="0" * 64)

    def test_parameter_temperature_and_policy_changes_reject_old_proof(self):
        changes = (
            lambda c: c["platform"].update(ambient_temperature_degC="26"),
            lambda c: c["platform"]["external_common_heat_distribution"].__setitem__(0, "1"),
            lambda c: c["platform"]["heat_capacity_J_per_K"].__setitem__(0, ".05"),
            lambda c: c["platform"]["conductance_W_per_K"][0].__setitem__(0, ".065"),
        )
        for index, modify in enumerate(changes):
            config = deepcopy(self.config)
            modify(config)
            with self.subTest(index=index), self.assertRaises(ContractError):
                self.certificate(config)
        for options in ({"policy": "hold"}, {"lower_C": "19"}, {"upper_C": "81"}):
            with self.subTest(options=options), self.assertRaises(ContractError):
                self.certificate(**options)

    def test_cached_certificate_requires_exact_content(self):
        receipt = self.certificate()
        args = {"source_sha256": SOURCE_SHA256, "policy": POLICY, "lower_C": "20", "upper_C": "80"}
        self.assertTrue(validate_idle_certificate(receipt, self.config, **args))
        altered = deepcopy(receipt)
        altered["upper_face_max_net_heat_W"][0] = "-2"
        altered["certificate_hash"] = content_hash({k: v for k, v in altered.items() if k != "certificate_hash"})
        with self.assertRaises(ContractError):
            validate_idle_certificate(altered, self.config, **args)


if __name__ == "__main__":
    unittest.main()
