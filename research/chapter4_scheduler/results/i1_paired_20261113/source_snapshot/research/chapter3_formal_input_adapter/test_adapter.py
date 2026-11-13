"""Pure adapter tests; no optimizer, thermal integration or formal workload run."""

from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
import ast
import sys
import unittest
from unittest.mock import patch

from research.chapter3_deadline_reference.contract import content_hash
from research.chapter3_workload_calibration.generator import stamp
from .fixtures import (base_case, s1_case, s7_case, multi_output_case, adapter_args,
                       remap_reference_candidate, BETA, evidence, package)
from .core import adapt_bundle


def adapt(case):
    args, kwargs = adapter_args(case)
    return adapt_bundle(*args, **kwargs)


def rehash_negative_case(case):
    """Reach semantic guards with hash-consistent, deliberately invalid input.

    This never certifies an altered archive or deadline origin. It is only a
    negative oracle: the adapter must reject the resulting template mismatch.
    """
    stamp(case["bundle"])
    due = case["deadline_receipt"]
    due["contract_hash"] = case["bundle"]["contract_hash"]
    due["receipt_hash"] = content_hash({k: v for k, v in due.items() if k != "receipt_hash"})
    window = case["window_receipt"]
    window["members"][case["member_key"]].update(
        bundle_hash=case["bundle"]["bundle_hash"], contract_hash=case["bundle"]["contract_hash"],
        deadline_receipt_hash=due["receipt_hash"])
    window["receipt_hash"] = content_hash({k: v for k, v in window.items() if k != "receipt_hash"})
    return case


def formal_module(name):
    # The unchanged production modules use flat imports. This only exposes
    # their public pure validators/option expansion to the manual test suite.
    folder = str(Path(__file__).resolve().parents[1] / "chapter3_experiments")
    if folder not in sys.path:
        sys.path.insert(0, folder)
    import importlib
    return importlib.import_module(name)


class AdapterTests(unittest.TestCase):
    def test_no_input_mutation(self):
        case = base_case(accelerators=True)
        before = deepcopy(case)
        adapt(case)
        self.assertEqual(case, before)

    def test_scenario_request_stage_edge_identity_is_lossless(self):
        case = base_case(accelerators=True)
        out = adapt(case)
        src = case["bundle"]["time_contract"]
        target = {s["id"]: s for s in out["instance"]["scenarios"]}
        for scene in src["scenarios"]:
            sid = scene["id"]
            given = target[sid]
            self.assertEqual(F(scene["weight"]), F(given["weight"]))
            self.assertEqual(set(map(tuple, given["dependencies"])),
                {(sid + "::" + a, sid + "::" + b) for a, b in scene["dependencies"]})
            stages = {s["id"]: s for s in given["stage_instances"]}
            requests = {r["id"]: r for r in given["requests"]}
            for stage in scene["stage_instances"]:
                new = stages[sid + "::" + stage["id"]]
                self.assertEqual(new["shared_stage_id"], stage["shared_stage_id"])
                self.assertEqual(new["request_id"], sid + "::" + stage["request_id"])
            for req in scene["requests"]:
                new = requests[sid + "::" + req["id"]]
                self.assertEqual(set(new["stage_instance_ids"]),
                                 {sid + "::" + i for i in req["stage_instance_ids"]})
                due = case["deadline_receipt"]["requests"][sid][req["id"]]
                self.assertEqual(F(new["release_ms"]), F(due["release_ms"]))
                self.assertEqual(F(new["deadline_ms"]), F(due["deadline_ms"]))

    def test_ids_and_option_ids_are_globally_unique(self):
        result = adapt(base_case())
        ins = result["instance"]
        stages = [s["id"] for sc in ins["scenarios"] for s in sc["stage_instances"]]
        requests = [r["id"] for sc in ins["scenarios"] for r in sc["requests"]]
        self.assertEqual(len(stages), len(set(stages)))
        self.assertEqual(len(requests), len(set(requests)))
        options = formal_module("inputs").expand_options(ins, result["config"])
        self.assertTrue(options)
        self.assertEqual(len(options), len({o["option_id"] for o in options}))

    def test_receipt_id_maps_are_reversible(self):
        case = base_case()
        receipt = adapt(case)["receipt"]
        for sid, row in receipt["identity_map"].items():
            for kind in ("requests", "stages"):
                for old, new in row[kind].items():
                    self.assertEqual(new, sid + "::" + old)
                    self.assertEqual(receipt["inverse_identity_map"][sid][kind][new], old)

    def test_exact_response_power_and_no_second_work_scaling(self):
        case = base_case(accelerators=True)
        out = adapt(case)
        ins = out["instance"]
        units = {u["id"]: u for u in ins["platform"]["units"]}
        for shared, modes in ins["stage_modes"].items():
            p = case["bundle"]["physical_profiles"][shared]
            for m in modes:
                uid, opp = m["unit_id"], m["opp_id"]
                d = ins["platform"]["domains"][units[uid]["domain_id"]]
                ref, point = d["opps"][d["reference_opp"]], d["opps"][opp]
                alpha, dref = F(p["units"][uid]["alpha"]), F(p["units"][uid]["d_ref_ms"])
                expected_d = dref * (1 - alpha + alpha * F(ref["frequency_GHz"]) / F(point["frequency_GHz"]))
                expected_q = F(p["units"][uid]["q_ref_W"]) * (F(point["voltage_V"]) / F(ref["voltage_V"])) ** 2 * F(point["frequency_GHz"]) / F(ref["frequency_GHz"])
                self.assertEqual(F(m["duration_ms"]), expected_d)
                self.assertEqual(F(m["activity_power_W"]), expected_q)
                self.assertEqual(F(m["activity_energy_J"]), expected_q * expected_d / 1000)

    def test_dedicated_gpu_npu_modes_survive(self):
        ins = adapt(base_case(accelerators=True))["instance"]
        for shared, unit in (("L1.s0002", "GPU0"), ("L1.s0003", "NPU0")):
            modes = ins["stage_modes"][shared]
            self.assertEqual({m["unit_id"] for m in modes}, {unit})
            self.assertEqual({m["opp_id"] for m in modes}, {"H", "M", "L"})

    def test_s1_uses_current_support_intersection_not_reference_mapping(self):
        case = s1_case(count=2, restrict_later=True)
        shared = "L1.s0001"
        self.assertEqual(case["base"]["reference"]["mapping_record"]["mapping"][shared], "CPU2")
        ins = adapt(case)["instance"]
        self.assertEqual({m["unit_id"] for m in ins["stage_modes"][shared]}, {"CPU1", "CPU2"})
        full_case = deepcopy(case)
        full_case["bundle"] = case["members"]["8"]["workload"]
        full_case["deadline_receipt"] = case["members"]["8"]["deadlines"][BETA]
        full_case["member_key"] = "8"
        full = adapt(full_case)["instance"]
        self.assertEqual({m["unit_id"] for m in full["stage_modes"][shared]}, {"CPU2"})

    def test_s1_all_subsets_have_same_window_and_original_due(self):
        case = s1_case(count=1)
        windows = set()
        for n in (1, 2, 4, 6, 8):
            chosen = deepcopy(case)
            chosen["member_key"] = str(n)
            chosen["bundle"] = case["members"][str(n)]["workload"]
            chosen["deadline_receipt"] = case["members"][str(n)]["deadlines"][BETA]
            ins = adapt(chosen)["instance"]
            self.assertEqual(len(ins["scenarios"]), n)
            self.assertEqual(sum(F(s["weight"]) for s in ins["scenarios"]), 1)
            windows.add(ins["window_ms"])
        self.assertEqual(windows, {case["window_receipt"]["window_ms"]})

    def test_multi_output_dag_does_not_become_chain(self):
        case = multi_output_case()
        ins = adapt(case)["instance"]
        for scene in ins["scenarios"]:
            large = [s["id"] for s in scene["stage_instances"] if s["shared_stage_id"].startswith("L1.")]
            edges = [e for e in scene["dependencies"] if e[0] in large]
            sinks = set(large) - {a for a, b in edges}
            self.assertEqual(len(sinks), 2)
            self.assertEqual(len(edges), 4)

    def test_s7_copies_share_modes_but_keep_independent_due_and_instance(self):
        case = s7_case()
        ins = adapt(case)["instance"]
        self.assertEqual(len(ins["stage_modes"]), 6)
        for scene in ins["scenarios"]:
            self.assertEqual(len(scene["stage_instances"]), 12)
            self.assertEqual(len(scene["requests"]), 4)
            reqs = {r["id"]: r for r in scene["requests"]}
            for app in ("L1", "S1"):
                a, b = (reqs[scene["id"] + "::" + app + ".r" + str(n)] for n in (1, 2))
                self.assertGreater(F(b["release_ms"]), F(a["release_ms"]))
                self.assertEqual(F(a["deadline_ms"]) - F(a["release_ms"]),
                                 F(b["deadline_ms"]) - F(b["release_ms"]))

    def test_s7_three_conditions_share_window_and_platform(self):
        case = s7_case()
        windows = set()
        for role in ("single", "synchronous", "staggered"):
            chosen = deepcopy(case)
            chosen["member_key"] = role
            chosen["bundle"] = case["members"][role]["workload"]
            chosen["deadline_receipt"] = case["members"][role]["deadlines"][BETA]
            ins = adapt(chosen)["instance"]
            windows.add(ins["window_ms"])
            self.assertEqual(ins["platform"], case["config"]["platform"])
        self.assertEqual(windows, {case["window_receipt"]["window_ms"]})

    def test_reference_h_witness_is_time_legal_after_identity_conversion(self):
        case = base_case(accelerators=True)
        out = adapt(case)
        candidate = remap_reference_candidate(case, out)
        result = formal_module("schedules").validate_schedule(out["instance"], candidate)
        self.assertEqual(result["state"], "SCHEDULE_VALID_THERMAL_UNCHECKED", result)

    def test_full_window_power_coverage_and_domain_baseline_once(self):
        case = base_case()
        out = adapt(case)
        candidate = remap_reference_candidate(case, out)
        checked = formal_module("schedules").validate_schedule(out["instance"], candidate)
        self.assertEqual(checked["state"], "SCHEDULE_VALID_THERMAL_UNCHECKED")
        found_one_busy_cpu = False
        for scene in checked["scenes"].values():
            pieces = scene["segments"]
            row_by_id = {row["stage_id"]: row for row in scene["rows"]}
            self.assertEqual(F(pieces[0]["start_ms"]), 0)
            self.assertEqual(F(pieces[-1]["end_ms"]), F(out["instance"]["window_ms"]))
            self.assertEqual(sum(F(p["duration_ms"]) for p in pieces), F(out["instance"]["window_ms"]))
            for piece in pieces:
                self.assertEqual(sum(F(v) for v in piece["baseline_by_power_group_W"].values()),
                                 sum(F(v) for v in piece["baseline_by_node_W"].values()))
                active_cpu_units = {row_by_id[s]["unit"] for s in piece["active_stage_ids"]
                                    if row_by_id[s]["domain_id"] == "CPU"}
                if len(active_cpu_units) == 1:
                    found_one_busy_cpu = True
                    self.assertEqual(piece["domain_opps"]["CPU"], "H")
            self.assertEqual(pieces[-1]["active_stage_ids"], [])
            self.assertEqual(set(pieces[-1]["domain_opps"].values()), {"L"})
        self.assertTrue(found_one_busy_cpu, "fixture must cover a busy CPU domain with an idle peer")

    def test_config_and_instance_auto_low_are_explicit(self):
        case = base_case()
        out = adapt(case)
        policy = formal_module("control_policy").resolve_idle_policy
        self.assertEqual(policy(out["config"]), "auto_low_immediate_v1")
        self.assertEqual(policy(out["instance"]), "auto_low_immediate_v1")
        self.assertEqual(out["instance"]["platform"], case["config"]["platform"])
        self.assertEqual(out["config"]["accuracy_targets"], case["config"]["accuracy_targets"])
        self.assertEqual(out["config"]["defaults"]["window_ms"], case["config"]["defaults"]["window_ms"])

    def test_adapter_does_not_reconstruct_reference_or_old_chain_inputs(self):
        case = base_case()
        with patch("research.chapter3_deadline_reference.scheduler.build_references", side_effect=AssertionError("reference reconstruction forbidden")), patch.object(formal_module("inputs"), "build_instance", side_effect=AssertionError("old chain reconstruction forbidden")):
            adapt(case)

    def test_external_reference_mapping_has_no_formal_input_channel(self):
        case = base_case()
        original = adapt(case)["instance"]
        changed = deepcopy(case)
        changed["base"]["reference"]["mapping_record"]["mapping"] = {"x": "NPU0"}
        # External reference is not an adapter argument. It cannot alter the
        # accepted bundle, due/window receipts or resulting formal problem.
        self.assertEqual(adapt(changed)["instance"], original)
        self.assertFalse(any(k in original for k in ("reference", "formal_mapping_constraint", "formal_initial_solution", "fixed_deployment")))

    def test_bundle_hash_tamper_is_rejected(self):
        case = base_case()
        case["bundle"]["physical_profiles"]["L1.s0001"]["units"]["CPU1"]["q_ref_W"] = "999"
        with self.assertRaises(ValueError): adapt(case)

    def test_deadline_hash_tamper_is_rejected(self):
        case = base_case()
        sid = next(iter(case["deadline_receipt"]["requests"]))
        rid = next(iter(case["deadline_receipt"]["requests"][sid]))
        case["deadline_receipt"]["requests"][sid][rid]["deadline_ms"] = "999"
        with self.assertRaises(ValueError): adapt(case)

    def test_window_hash_tamper_is_rejected(self):
        case = base_case()
        case["window_receipt"]["window_ms"] = "999"
        with self.assertRaises(ValueError): adapt(case)

    def test_rehashed_window_too_short_is_rejected(self):
        case = base_case()
        row = case["window_receipt"]
        row["window_ms"] = "5"
        row["members"][case["member_key"]]["window_ms"] = "5"
        row["receipt_hash"] = content_hash({k: v for k, v in row.items() if k != "receipt_hash"})
        with self.assertRaises(ValueError): adapt(case)

    def test_wrong_member_key_is_rejected(self):
        case = base_case()
        case["member_key"] = "unknown"
        with self.assertRaises(ValueError): adapt(case)

    def test_physical_config_drift_is_rejected(self):
        case = base_case()
        case["config"]["platform"]["external_common_power_W"] = "99"
        with self.assertRaises(ValueError): adapt(case)

    def test_physical_profile_time_drift_even_rehashed_is_rejected(self):
        case = base_case()
        case["bundle"]["physical_profiles"]["L1.s0001"]["units"]["CPU1"]["d_ref_ms"] = "999"
        with self.assertRaises(ValueError): stamp(case["bundle"])

    def test_reference_mapping_cannot_be_installed_as_constraint(self):
        case = base_case()
        case["bundle"]["formal_mapping_constraint"] = {"L1.s0001": "CPU1"}
        with self.assertRaises(ValueError): stamp(case["bundle"])

    def test_float_in_physical_profile_is_rejected(self):
        case = base_case()
        case["bundle"]["physical_profiles"]["L1.s0001"]["units"]["CPU1"]["q_ref_W"] = 1.0
        with self.assertRaises(ValueError): stamp(case["bundle"])

    def test_application_template_edge_mismatch_is_rejected_after_hashes_match(self):
        case = base_case()
        case["bundle"]["applications"]["L1"]["edges"].pop(0)
        rehash_negative_case(case)
        with self.assertRaisesRegex(ValueError, "ADAPTER_REQUEST_TEMPLATE_EDGE_MISMATCH"):
            adapt(case)

    def test_actual_request_dag_mismatch_is_rejected_after_hashes_match(self):
        case = base_case()
        scene = case["bundle"]["time_contract"]["scenarios"][0]
        scene["dependencies"] = [e for e in scene["dependencies"]
                                  if e != ["L1.s0001.r1", "L1.s0002.r1"]]
        rehash_negative_case(case)
        with self.assertRaisesRegex(ValueError, "ADAPTER_REQUEST_TEMPLATE_EDGE_MISMATCH"):
            adapt(case)

    def test_incorrect_required_output_is_rejected_after_hashes_match(self):
        case = base_case()
        case["bundle"]["applications"]["L1"]["required_outputs"].append("L1.s0001")
        rehash_negative_case(case)
        with self.assertRaisesRegex(ValueError, "ADAPTER_REQUIRED_OUTPUTS_MISMATCH"):
            adapt(case)


if __name__ == "__main__":
    unittest.main()
