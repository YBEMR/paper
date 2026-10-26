"""Static E2 resource-mask regressions; no planner or thermal evaluator calls."""
from copy import deepcopy
from fractions import Fraction as F
import unittest
from unittest.mock import patch

from h02_pair_preflight.common import ContractError
from inputs import load_config
from e2_resources.input_contract import (BASE_ID, MASKS, PROBLEM_IDS, idle_power_evidence,
                                        prepare_inputs, validate_inputs)


class ResourceInputContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = prepare_inputs()

    def setUp(self):
        self.packets = deepcopy(self.original)
        self.pid = PROBLEM_IDS[0]
        self.instance = self.packets[self.pid]["instance"]

    def reject(self):
        with self.assertRaises(ContractError):
            validate_inputs(self.packets)

    def test_actual_original_four_inputs_pass(self):
        report = validate_inputs(self.packets)
        self.assertEqual(report["state"], "STATIC_RESOURCE_INPUT_CONTRACT_PASSED")
        self.assertEqual([report["inputs"][pid]["total_catalog_mode_count"] for pid in PROBLEM_IDS],
                         [54, 60, 60, 66])
        self.assertEqual(len(report["mode_domain_inclusions"]), 4)
        self.assertFalse(report["candidate_search_performed"])
        self.assertFalse(report["thermal_propagation_performed"])
        self.assertFalse(report["real_SAFE_created"])

    def test_raw_config_reuses_exact_original_generator(self):
        self.assertEqual(prepare_inputs(load_config()), self.original)

    def test_auto_config_reuses_exact_original_generator(self):
        self.assertEqual(prepare_inputs(self.original[BASE_ID]["config"]), self.original)

    def test_reject_config_tuning_hook(self):
        c = load_config()
        c["defaults"]["maximum_temperature_degC"] = "81"
        with self.assertRaises(ContractError): prepare_inputs(c)

    def test_packets_and_caller_config_independent(self):
        c = load_config(); before = deepcopy(c); packets = prepare_inputs(c)
        self.assertEqual(c, before)
        packets[self.pid]["config"]["platform"]["node_order"].pop()
        self.assertEqual(packets[BASE_ID], self.original[BASE_ID])

    def test_validation_no_mutation(self):
        before = deepcopy(self.packets)
        validate_inputs(self.packets)
        self.assertEqual(self.packets, before)

    def test_all_physical_devices_and_domains_retained(self):
        for packet in self.packets.values():
            self.assertEqual(packet["instance"]["platform"], self.original[BASE_ID]["instance"]["platform"])
            self.assertEqual(packet["instance"]["platform"]["node_order"], ["CPU1", "CPU2", "GPU0", "NPU0"])
            self.assertEqual(set(packet["instance"]["platform"]["domains"]), {"CPU", "GPU", "NPU"})

    def test_empty_activity_still_charges_masked_domains(self):
        proof = idle_power_evidence(self.instance)
        self.assertEqual({d: F(v) for d, v in proof["baseline_by_power_group_W"].items()},
                         {"CPU": F("0.60"), "GPU": F("0.40"), "NPU": F("0.25")})
        self.assertEqual(F(proof["baseline_window_energy_at_reference_J"]), F("0.5"))
        self.assertEqual(F(proof["external_common_window_energy_J"]), F("0.12"))
        self.assertEqual(set(proof["local_leakage_slope_W_per_K"]), {"CPU1", "CPU2", "GPU0", "NPU0"})

    def test_cpu_modes_complete_in_every_mask(self):
        for packet in self.packets.values():
            for modes in packet["instance"]["stage_modes"].values():
                cpu = {(m["unit_id"], m["opp_id"]) for m in modes if m["domain_id"] == "CPU"}
                self.assertEqual(cpu, {(u, o) for u in ("CPU1", "CPU2") for o in ("L", "M", "H")})

    def test_gpu_npu_masks_not_mutual_subsets(self):
        gpu = self.packets[PROBLEM_IDS[1]]["instance"]["stage_modes"]["A.main"]
        npu = self.packets[PROBLEM_IDS[2]]["instance"]["stage_modes"]["A.main"]
        g, n = {m["mode_id"] for m in gpu}, {m["mode_id"] for m in npu}
        self.assertFalse(g <= n); self.assertFalse(n <= g)

    def test_generated_ablation_label_allowed_but_exact(self):
        self.assertFalse(self.instance["ablation_input"])
        self.assertTrue(self.packets[BASE_ID]["instance"]["ablation_input"])
        self.instance["ablation_input"] = True; self.reject()

    def test_exact_four_input_keys(self):
        self.packets.pop(self.pid); self.reject()

    def test_additional_input_rejected(self):
        self.packets["extra"] = deepcopy(self.packets[BASE_ID]); self.reject()

    def test_packet_extra_field_rejected(self):
        self.packets[self.pid]["seed_candidate"] = {}; self.reject()

    def test_packet_config_drift_rejected(self):
        self.packets[self.pid]["config"]["platform"]["external_common_power_W"] = "0"; self.reject()

    def test_omit_temp_objective_rejected(self):
        self.packets[self.pid]["objective"] = "OMIT_TEMP"; self.reject()

    def test_unknown_label_rejected(self):
        self.instance["condition_id"] = "resources_CPU_new"; self.reject()

    def test_wrong_problem_rejected(self):
        self.instance["id"] = BASE_ID; self.reject()

    def test_remove_masked_thermal_node_rejected(self):
        self.instance["platform"]["node_order"].remove("GPU0"); self.reject()

    def test_remove_masked_domain_rejected(self):
        del self.instance["platform"]["domains"]["GPU"]; self.reject()

    def test_remove_masked_unit_rejected(self):
        self.instance["platform"]["units"].pop(); self.reject()

    def test_idle_baseline_change_rejected(self):
        self.instance["platform"]["domains"]["GPU"]["baseline_W"]["L"] = "0"; self.reject()

    def test_idle_leakage_change_rejected(self):
        self.instance["platform"]["domains"]["NPU"]["local_temperature_slope_W_per_K"]["L"] = "0"; self.reject()

    def test_thermal_coupling_change_rejected(self):
        self.instance["platform"]["conductance_W_per_K"][0][0] = "0.065"; self.reject()

    def test_capacity_change_rejected(self):
        self.instance["platform"]["heat_capacity_J_per_K"][2] = "0.09"; self.reject()

    def test_window_change_rejected(self):
        self.instance["window_ms"] = "401"; self.reject()

    def test_grid_change_rejected(self):
        self.instance["start_grid_ms"] = "1"; self.reject()

    def test_response_change_rejected(self):
        self.instance["response_variant"] = "R"; self.reject()

    def test_opp_frequency_change_rejected(self):
        self.instance["platform"]["domains"]["CPU"]["opps"]["L"]["frequency_GHz"] = "0.9"; self.reject()

    def test_deadline_change_rejected(self):
        self.instance["scenarios"][0]["requests"][0]["deadline_ms"] = "200"; self.reject()

    def test_release_change_rejected(self):
        self.instance["scenarios"][0]["requests"][0]["release_ms"] = "5"; self.reject()

    def test_entry_temperature_change_rejected(self):
        self.instance["scenarios"][0]["entry"]["temperature_degC"][0] = "49"; self.reject()

    def test_limit_change_rejected(self):
        self.instance["scenarios"][0]["maximum_temperature_degC"][0] = "81"; self.reject()

    def test_scene_weight_change_rejected(self):
        self.instance["scenarios"][0]["weight"] = "1"; self.reject()

    def test_dependency_change_rejected(self):
        self.instance["scenarios"][0]["dependencies"].pop(); self.reject()

    def test_domain_entry_change_rejected(self):
        self.instance["scenarios"][0]["entry"]["domain_opp"]["GPU"] = "H"; self.reject()

    def test_missing_legal_mode_rejected(self):
        self.instance["stage_modes"]["A.main"].pop(); self.reject()

    def test_extra_masked_gpu_mode_rejected(self):
        all_modes = self.packets[BASE_ID]["instance"]["stage_modes"]["A.main"]
        self.instance["stage_modes"]["A.main"].append(deepcopy(next(m for m in all_modes if m["unit_id"] == "GPU0")))
        self.reject()

    def test_duplicate_mode_rejected(self):
        self.instance["stage_modes"]["A.main"].append(deepcopy(self.instance["stage_modes"]["A.main"][0])); self.reject()

    def test_mode_cost_modifications_rejected(self):
        for field in ("duration_ms", "d_ref_ms", "alpha", "activity_power_W", "activity_energy_J", "frequency_GHz", "voltage_V"):
            with self.subTest(field=field):
                self.packets = deepcopy(self.original)
                self.packets[self.pid]["instance"]["stage_modes"]["A.main"][0][field] = "999"
                self.reject()

    def test_stage_coverage_change_rejected(self):
        del self.instance["stage_modes"]["A.post"]; self.reject()

    def test_unexpected_input_field_rejected(self):
        self.instance["hidden_hint"] = "HISTORICAL_BEST"; self.reject()

    def test_base_physics_mutation_also_rejected(self):
        for packet in self.packets.values():
            packet["instance"]["platform"]["ambient_temperature_degC"] = "24"
        self.reject()

    def test_base_modes_mutation_also_rejected(self):
        for packet in self.packets.values():
            packet["instance"]["stage_modes"]["A.main"][0]["duration_ms"] = "999"
        self.reject()

    def test_mask_change_rejected(self):
        self.instance["settings"]["available_device_classes"].append("GPU"); self.reject()

    def test_malformed_packet_fails_closed(self):
        self.packets[self.pid] = None; self.reject()

    def test_label_bool_not_replaced_by_integer(self):
        self.instance["ablation_input"] = 0
        self.reject()

    def test_config_count_not_replaced_by_float(self):
        self.packets[self.pid]["config"]["defaults"]["requests_per_application"] = 1.0
        self.reject()

    def test_validation_no_search_or_heat_imports(self):
        import sys
        # These kernels are unnecessary even for the genuine frozen input pass.
        with patch.dict(sys.modules, {"heft_method": None, "thermal": None,
                                     "milp": None, "scipy.optimize": None}):
            validate_inputs(prepare_inputs())


if __name__ == "__main__":
    unittest.main()
