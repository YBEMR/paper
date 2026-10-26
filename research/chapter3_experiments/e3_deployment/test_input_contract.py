"""Pure E3 identities and hand-written schedule legality/power regressions.

No HEFT, schedule search, temperature propagation or real SAFE is produced.
"""
from copy import deepcopy
from fractions import Fraction as F
import unittest
from unittest.mock import patch

from h02_pair_preflight.common import ContractError, sha
from inputs import load_config
from schedules import validate_schedule
from e3_deployment.input_contract import (A_STAGE_IDS, BASE_ID, LOCAL_A_ID, PROBLEM_IDS,
    _aliases, _normalize, derive_scene_local_a, prepare_inputs, validate_inputs)


def hand_written_cpu_chains(instance, *, different_A_unit=False, AB_A_pre_low=False,
                            AC_A_start_shift=False):
    """Fixed CPU parallel-chain fixture; exact earliest chain starts, no search.

    This deliberately picks one predeclared unit/OPP pattern. It proves legal
    domain relationships only and carries no heat or energy-safety conclusion.
    """
    result = {"scenes": {}}
    grid = F(instance["start_grid_ms"])
    for scene in instance["scenarios"]:
        rows = []
        stages = {stage["id"]: stage for stage in scene["stage_instances"]}
        is_ac = scene["id"] == "AC_offset_0ms"
        for request in scene["requests"]:
            app = request["application"]
            unit = "CPU1" if app == "A" else "CPU2"
            if different_A_unit and is_ac:
                unit = "CPU2" if app == "A" else "CPU1"
            cursor = F(request["release_ms"])
            if AB_A_pre_low and not is_ac and app == "B": cursor += 15
            if AC_A_start_shift and is_ac and app == "A": cursor += 5
            for stage_id in request["stage_instance_ids"]:
                stage = stages[stage_id]
                opp = ("L" if AB_A_pre_low and not is_ac and app == "A" and
                       stage["chain_position"] == 0 else "H")
                mode = next(m for m in instance["stage_modes"][stage["shared_stage_id"]]
                            if m["unit_id"] == unit and m["opp_id"] == opp)
                start = -((-cursor) // grid) * grid
                rows.append({"stage_id": stage_id, "unit": unit, "opp": opp, "start_ms": str(start)})
                cursor = start + F(mode["duration_ms"])
        result["scenes"][scene["id"]] = rows
    return result


class DeploymentInputContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = prepare_inputs()

    def setUp(self):
        self.packets = deepcopy(self.original)
        self.base = self.packets[BASE_ID]["instance"]
        self.local = self.packets[LOCAL_A_ID]["instance"]

    def reject(self):
        with self.assertRaises(ContractError): validate_inputs(self.packets)

    def test_actual_original_pair_passes(self):
        proof = validate_inputs(self.packets)
        self.assertEqual(proof["state"], "STATIC_DEPLOYMENT_INPUT_CONTRACT_PASSED")
        self.assertEqual(proof["inputs"][BASE_ID]["deployment_stage_count"], 9)
        self.assertEqual(proof["inputs"][LOCAL_A_ID]["deployment_stage_count"], 12)
        self.assertEqual(proof["inputs"][BASE_ID]["total_catalog_mode_count"], 66)
        self.assertEqual(proof["inputs"][LOCAL_A_ID]["total_catalog_mode_count"], 90)
        self.assertTrue(proof["normalized_input_identical_to_shared"])
        self.assertEqual(proof["normalized_local_input_sha256"], sha(self.base))
        self.assertFalse(proof["candidate_search_performed"])
        self.assertFalse(proof["thermal_propagation_performed"])
        self.assertFalse(proof["real_SAFE_created"])

    def test_raw_and_auto_config_supported_without_changes(self):
        self.assertEqual(prepare_inputs(load_config()), self.original)
        self.assertEqual(prepare_inputs(self.packets[BASE_ID]["config"]), self.original)

    def test_input_and_config_no_mutation(self):
        old = deepcopy(self.packets); validate_inputs(self.packets)
        self.assertEqual(self.packets, old)
        original_base = deepcopy(self.base)
        derived = derive_scene_local_a(self.base)
        self.assertEqual(derived, self.local)
        self.assertEqual(self.base, original_base)

    def test_config_and_packets_independent(self):
        self.packets[BASE_ID]["config"]["platform"]["node_order"].pop()
        self.assertEqual(self.packets[LOCAL_A_ID], self.original[LOCAL_A_ID])

    def test_normalize_is_original_input(self):
        self.assertEqual(_normalize(self.local, self.base), self.base)

    def test_physics_rules_and_settings_identical(self):
        for name in ("platform", "settings", "execution_rules", "duration_scale", "response_variant",
                     "window_ms", "start_grid_ms", "sample_id", "condition_id", "experiment_group"):
            self.assertEqual(self.base[name], self.local[name])
        self.assertEqual(self.packets[BASE_ID]["config"], self.packets[LOCAL_A_ID]["config"])

    def test_non_A_stage_modes_unchanged(self):
        for sid in self.base["stage_modes"]:
            if sid not in A_STAGE_IDS:
                self.assertEqual(self.base["stage_modes"][sid], self.local["stage_modes"][sid])

    def test_aliases_stable_and_collision_free(self):
        aliases = _aliases(self.base)
        values = [v for m in aliases.values() for v in m.values()]
        self.assertEqual(len(values), len(set(values)))
        for scene, table in aliases.items():
            for sid, alias in table.items(): self.assertEqual(alias, sid + "@@" + scene)
        self.assertEqual(derive_scene_local_a(self.base), derive_scene_local_a(self.base))

    def test_each_mode_changes_only_two_identity_fields(self):
        aliases = _aliases(self.base)
        for table in aliases.values():
            for sid, alias in table.items():
                for before, after in zip(self.base["stage_modes"][sid], self.local["stage_modes"][alias]):
                    self.assertEqual({k: v for k, v in before.items() if k not in {"shared_stage_id", "mode_id"}},
                                     {k: v for k, v in after.items() if k not in {"shared_stage_id", "mode_id"}})
                    self.assertEqual(after["shared_stage_id"], alias)
                    self.assertEqual(after["mode_id"], alias + "@" + after["unit_id"] + ":" + after["opp_id"])

    def test_actual_stage_ids_requests_dependencies_weights_not_changed(self):
        for original, local in zip(self.base["scenarios"], self.local["scenarios"]):
            normalized = deepcopy(local)
            for stage, before in zip(normalized["stage_instances"], original["stage_instances"]):
                stage["shared_stage_id"] = before["shared_stage_id"]
            self.assertEqual(original, normalized)

    def test_OPP_choices_not_locked_by_alias(self):
        for table in _aliases(self.base).values():
            for alias in table.values():
                modes = self.local["stage_modes"][alias]
                for unit in {m["unit_id"] for m in modes}:
                    self.assertEqual({m["opp_id"] for m in modes if m["unit_id"] == unit}, {"L", "M", "H"})

    def test_identical_handwritten_schedule_legal_and_same_power_segments(self):
        shared = hand_written_cpu_chains(self.base)
        local = hand_written_cpu_chains(self.local)
        self.assertEqual(shared, local)
        a, b = validate_schedule(self.base, shared), validate_schedule(self.local, local)
        self.assertEqual(a["state"], "SCHEDULE_VALID_THERMAL_UNCHECKED")
        self.assertEqual(b["state"], "SCHEDULE_VALID_THERMAL_UNCHECKED")
        for sid in a["scenes"]:
            self.assertEqual(a["scenes"][sid]["segments"], b["scenes"][sid]["segments"])

    def test_A_unit_may_differ_only_in_scene_local_view(self):
        candidate = hand_written_cpu_chains(self.local, different_A_unit=True)
        shared = validate_schedule(self.base, candidate)
        local = validate_schedule(self.local, candidate)
        self.assertEqual(shared["state"], "INVALID_SCHEDULE")
        self.assertEqual(shared["reason"], "SHARED_DEPLOYMENT_MISMATCH")
        self.assertEqual(local["state"], "SCHEDULE_VALID_THERMAL_UNCHECKED")

    def test_same_unit_can_have_different_OPP_across_scenes(self):
        for instance in (self.base, self.local):
            candidate = hand_written_cpu_chains(instance, AB_A_pre_low=True)
            self.assertEqual(validate_schedule(instance, candidate)["state"],
                             "SCHEDULE_VALID_THERMAL_UNCHECKED")

    def test_same_unit_can_have_different_start_across_scenes(self):
        for instance in (self.base, self.local):
            candidate = hand_written_cpu_chains(instance, AC_A_start_shift=True)
            self.assertEqual(validate_schedule(instance, candidate)["state"],
                             "SCHEDULE_VALID_THERMAL_UNCHECKED")

    def test_derive_rejects_other_problem(self):
        self.base["id"] = "base__R2"
        with self.assertRaises(ContractError): derive_scene_local_a(self.base)

    def test_derive_rejects_already_adapted_input(self):
        with self.assertRaises(ContractError): derive_scene_local_a(self.local)

    def test_derive_rejects_modified_base_even_legal_variant(self):
        self.base["scenarios"][0]["maximum_temperature_degC"][0] = "81"
        with self.assertRaises(ContractError): derive_scene_local_a(self.base)

    def test_config_tuning_rejected(self):
        c = load_config(); c["defaults"]["requests_per_application"] = 2
        with self.assertRaises(ContractError): prepare_inputs(c)

    def test_input_ID_mixing_rejected(self):
        self.local["id"] = BASE_ID; self.reject()

    def test_packet_views_swapped_rejected(self):
        self.packets[BASE_ID], self.packets[LOCAL_A_ID] = self.packets[LOCAL_A_ID], self.packets[BASE_ID]
        self.reject()

    def test_missing_packet_rejected(self):
        del self.packets[BASE_ID]; self.reject()

    def test_extra_packet_rejected(self):
        self.packets["EXTRA"] = deepcopy(self.packets[BASE_ID]); self.reject()

    def test_packet_extra_field_rejected(self):
        self.packets[LOCAL_A_ID]["initial_solution"] = {}; self.reject()

    def test_config_drift_rejected(self):
        self.packets[LOCAL_A_ID]["config"]["defaults"]["window_ms"] = "401"; self.reject()

    def test_omit_temperature_objective_rejected(self):
        self.packets[LOCAL_A_ID]["objective"] = "OMIT_TEMP"; self.reject()

    def test_unknown_alias_rejected(self):
        self.local["scenarios"][0]["stage_instances"][0]["shared_stage_id"] = "A.pre@@BAD"
        self.reject()

    def test_missing_alias_mode_list_rejected(self):
        self.local["stage_modes"].pop("A.main@@AB_offset_0ms"); self.reject()

    def test_additional_original_A_mode_list_rejected(self):
        self.local["stage_modes"]["A.main"] = deepcopy(self.base["stage_modes"]["A.main"]); self.reject()

    def test_wrong_mode_shared_ID_rejected(self):
        self.local["stage_modes"]["A.main@@AB_offset_0ms"][0]["shared_stage_id"] = "A.main"; self.reject()

    def test_wrong_canonical_mode_ID_rejected(self):
        self.local["stage_modes"]["A.main@@AB_offset_0ms"][0]["mode_id"] = "A.main@CPU1:L"; self.reject()

    def test_mode_cost_or_response_changes_rejected(self):
        for field in ("duration_ms", "activity_power_W", "alpha", "activity_energy_J", "frequency_GHz", "voltage_V"):
            with self.subTest(field=field):
                self.packets = deepcopy(self.original)
                self.packets[LOCAL_A_ID]["instance"]["stage_modes"]["A.main@@AB_offset_0ms"][0][field] = "999"
                self.reject()

    def test_missing_legal_mode_rejected(self):
        self.local["stage_modes"]["A.main@@AB_offset_0ms"].pop(); self.reject()

    def test_extra_or_duplicate_mode_rejected(self):
        modes = self.local["stage_modes"]["A.main@@AB_offset_0ms"]
        modes.append(deepcopy(modes[0])); self.reject()

    def test_B_deployment_change_rejected(self):
        stage = next(s for s in self.local["scenarios"][0]["stage_instances"] if s["application"] == "B")
        stage["shared_stage_id"] += "@@AB_offset_0ms"; self.reject()

    def test_stage_instance_ID_change_rejected(self):
        self.local["scenarios"][0]["stage_instances"][0]["id"] += "NEW"; self.reject()

    def test_deadline_change_rejected(self):
        self.local["scenarios"][0]["requests"][0]["deadline_ms"] = "200"; self.reject()

    def test_heat_node_removed_rejected(self):
        self.local["platform"]["node_order"].pop(); self.reject()

    def test_extra_hidden_input_field_rejected(self):
        self.local["extra_feedback"] = True; self.reject()

    def test_base_and_local_common_physics_drift_rejected(self):
        for packet in self.packets.values():
            packet["instance"]["platform"]["ambient_temperature_degC"] = "24"
        self.reject()

    def test_bool_tag_type_change_rejected(self):
        self.local["ablation_input"] = 1; self.reject()

    def test_static_contract_does_not_import_planner_or_heat(self):
        import sys
        with patch.dict(sys.modules, {"heft_method": None, "thermal": None, "milp": None}):
            validate_inputs(prepare_inputs())


if __name__ == "__main__":
    unittest.main()
