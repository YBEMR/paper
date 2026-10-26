"""Static deadline/input and hand-written legality checks; no science kernel."""
from copy import deepcopy
from fractions import Fraction as F
import unittest
from unittest.mock import patch

from h02_pair_preflight.common import ContractError, sha
from inputs import load_config
from schedules import validate_schedule
from e4_deadline.input_contract import (BASE_ID, BETAS, PROBLEM_IDS, _normalize,
                                        prepare_inputs, validate_inputs)


def handwritten_parallel_chains(instance,shift_A_AB_ms=0):
    """One fixed unit/OPP pattern, exact chain starts; not candidate search.

    A/B run CPU-H parallel chains, C uses GPU-H only for its main Stage.
    A's AB chain may be translated by the given declared grid offset.
    """
    candidate={"scenes":{}}
    grid=F(instance["start_grid_ms"])
    for scene in instance["scenarios"]:
        stages={s["id"]:s for s in scene["stage_instances"]}
        rows=[]
        for request in scene["requests"]:
            app=request["application"]
            cursor=F(request["release_ms"])
            if scene["id"]=="AB_offset_0ms" and app=="A": cursor+=shift_A_AB_ms
            for stage_id in request["stage_instance_ids"]:
                stage=stages[stage_id]
                unit="CPU1" if app=="A" else "CPU2"
                if stage["shared_stage_id"]=="C.main": unit="GPU0"
                mode=next(m for m in instance["stage_modes"][stage["shared_stage_id"]]
                          if m["unit_id"]==unit and m["opp_id"]=="H")
                start=-((-cursor)//grid)*grid
                rows.append({"stage_id":stage_id,"unit":unit,"opp":"H","start_ms":str(start)})
                cursor=start+F(mode["duration_ms"])
        candidate["scenes"][scene["id"]]=rows
    return candidate


class DeadlineInputContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.original=prepare_inputs()

    def setUp(self):
        self.packets=deepcopy(self.original)
        self.tight=self.packets[PROBLEM_IDS[0]]["instance"]
        self.base=self.packets[BASE_ID]["instance"]
        self.wide=self.packets[PROBLEM_IDS[2]]["instance"]

    def reject(self):
        with self.assertRaises(ContractError): validate_inputs(self.packets)

    def test_original_three_inputs_pass(self):
        proof=validate_inputs(self.packets)
        self.assertEqual(proof["state"],"STATIC_DEADLINE_INPUT_CONTRACT_PASSED")
        self.assertEqual(len(proof["deadline_domain_inclusions"]),2)
        self.assertFalse(proof["candidate_search_performed"])
        self.assertFalse(proof["thermal_propagation_performed"])
        self.assertFalse(proof["real_SAFE_created"])
        for pid in PROBLEM_IDS:
            r=proof["inputs"][pid]
            self.assertEqual(r["deployment_stage_count"],9)
            self.assertEqual(r["total_catalog_mode_count"],66)
            self.assertEqual(r["normalized_input_sha256"],sha(self.base))

    def test_original_declared_labels(self):
        for pid in (PROBLEM_IDS[0],PROBLEM_IDS[2]):
            i=self.packets[pid]["instance"]
            self.assertFalse(i["ablation_input"])
            self.assertEqual(i["experiment_group"],"3_deadline")
        self.assertTrue(self.base["ablation_input"])
        self.assertEqual(self.base["experiment_group"],"shared_base")

    def test_original_config_and_auto_copy_supported(self):
        self.assertEqual(prepare_inputs(load_config()),self.original)
        self.assertEqual(prepare_inputs(self.packets[BASE_ID]["config"]),self.original)

    def test_no_input_or_caller_config_mutation(self):
        before=deepcopy(self.packets);validate_inputs(self.packets)
        self.assertEqual(self.packets,before)
        c=load_config();before=deepcopy(c);prepare_inputs(c)
        self.assertEqual(c,before)

    def test_packet_config_copies_independent(self):
        self.packets[PROBLEM_IDS[0]]["config"]["platform"]["node_order"].pop()
        self.assertEqual(self.packets[BASE_ID],self.original[BASE_ID])

    def test_normalized_input_identical_to_base(self):
        for packet in self.packets.values(): self.assertEqual(_normalize(packet["instance"],self.base),self.base)

    def test_exact_CPU_H_reference_formula(self):
        evidence=validate_inputs(self.packets)
        for pid in PROBLEM_IDS:
            p=evidence["inputs"][pid]["deadline_formula"]
            self.assertEqual(p["application_reference_chain_ms"],{"A":"95","B":"121","C":"110"})
            for requests in p["requests"].values():
                for r in requests.values():
                    self.assertEqual(F(r["relative_deadline_ms"]),F(BETAS[pid])*F(r["reference_CPU_H_chain_ms"]))
                    self.assertEqual(F(r["deadline_ms"]),F(r["release_ms"])+F(r["relative_deadline_ms"]))

    def test_deadlines_and_only_deadlines_change(self):
        for packet in self.packets.values():
            i=packet["instance"]
            for name in ("platform","execution_rules","stage_modes","response_variant","window_ms","start_grid_ms"):
                self.assertEqual(i[name],self.base[name])
            self.assertEqual(i["window_ms"],"400");self.assertEqual(i["start_grid_ms"],"5")

    def test_tight_boundary_schedule_valid_in_all_three(self):
        candidate=handwritten_parallel_chains(self.tight)
        segments=None
        for packet in self.packets.values():
            result=validate_schedule(packet["instance"],candidate)
            self.assertEqual(result["state"],"SCHEDULE_VALID_THERMAL_UNCHECKED")
            current={sid:r["segments"] for sid,r in result["scenes"].items()}
            if segments is None: segments=current
            else: self.assertEqual(current,segments)
        # A finishes exactly at the tight 95 ms deadline, using original units.
        result=validate_schedule(self.tight,candidate)
        rows=result["scenes"]["AB_offset_0ms"]["rows"]
        self.assertEqual(next(r["end_ms"] for r in rows if r["shared_stage_id"]=="A.post"),"95")

    def test_middle_only_handwritten_witness(self):
        candidate=handwritten_parallel_chains(self.base,10)
        tight=validate_schedule(self.tight,candidate)
        self.assertEqual(tight["state"],"INVALID_SCHEDULE")
        self.assertEqual(tight["reason"],"REQUEST_DEADLINE_EXCEEDED")
        self.assertEqual(validate_schedule(self.base,candidate)["state"],"SCHEDULE_VALID_THERMAL_UNCHECKED")
        self.assertEqual(validate_schedule(self.wide,candidate)["state"],"SCHEDULE_VALID_THERMAL_UNCHECKED")

    def test_wide_only_handwritten_witness(self):
        candidate=handwritten_parallel_chains(self.wide,40)
        for instance in (self.tight,self.base):
            result=validate_schedule(instance,candidate)
            self.assertEqual(result["state"],"INVALID_SCHEDULE")
            self.assertEqual(result["reason"],"REQUEST_DEADLINE_EXCEEDED")
        self.assertEqual(validate_schedule(self.wide,candidate)["state"],"SCHEDULE_VALID_THERMAL_UNCHECKED")

    def test_missing_packet_rejected(self): del self.packets[BASE_ID];self.reject()
    def test_extra_packet_rejected(self): self.packets["extra"]=deepcopy(self.packets[BASE_ID]);self.reject()
    def test_mixed_problem_ID_rejected(self): self.tight["id"]=BASE_ID;self.reject()
    def test_extra_packet_field_rejected(self): self.packets[BASE_ID]["seed"]={};self.reject()
    def test_unknown_objective_rejected(self): self.packets[BASE_ID]["objective"]="OMIT_TEMP";self.reject()
    def test_packet_config_drift_rejected(self): self.packets[BASE_ID]["config"]["defaults"]["window_ms"]="401";self.reject()

    def test_config_tuning_not_supported(self):
        c=load_config();c["defaults"]["deadline_beta"]="1.4"
        with self.assertRaises(ContractError):prepare_inputs(c)

    def test_beta_edit_rejected(self):self.tight["settings"]["deadline_beta"]="0.8";self.reject()
    def test_unchanged_formula_but_new_beta_rejected(self):
        self.tight["settings"]["deadline_beta"]="1.1"
        for scene in self.tight["scenarios"]:
            for r in scene["requests"]:
                relative=F("1.1")*F(r["reference_CPU_H_chain_ms"])
                r["relative_deadline_ms"]=str(relative);r["deadline_ms"]=str(F(r["release_ms"])+relative)
        self.reject()

    def test_absolute_deadline_edit_rejected(self):self.tight["scenarios"][0]["requests"][0]["deadline_ms"]="96";self.reject()
    def test_relative_deadline_edit_rejected(self):self.tight["scenarios"][0]["requests"][0]["relative_deadline_ms"]="96";self.reject()
    def test_reference_chain_edit_rejected(self):self.tight["scenarios"][0]["requests"][0]["reference_CPU_H_chain_ms"]="96";self.reject()
    def test_release_time_edit_rejected(self):self.tight["scenarios"][0]["requests"][0]["release_ms"]="5";self.reject()
    def test_response_edit_rejected(self):self.tight["response_variant"]="R";self.reject()
    def test_window_edit_rejected(self):self.tight["window_ms"]="401";self.reject()
    def test_grid_edit_rejected(self):self.tight["start_grid_ms"]="1";self.reject()
    def test_available_devices_edit_rejected(self):self.tight["settings"]["available_device_classes"]=["CPU"];self.reject()
    def test_mode_removed_rejected(self):self.tight["stage_modes"]["A.main"].pop();self.reject()
    def test_mode_activity_edit_rejected(self):self.tight["stage_modes"]["A.main"][0]["activity_power_W"]="0";self.reject()
    def test_mode_duration_edit_rejected(self):self.tight["stage_modes"]["A.main"][0]["duration_ms"]="1";self.reject()
    def test_mode_response_edit_rejected(self):self.tight["stage_modes"]["A.main"][0]["alpha"]="1";self.reject()
    def test_temperature_limit_edit_rejected(self):self.tight["scenarios"][0]["maximum_temperature_degC"][0]="81";self.reject()
    def test_initial_temperature_edit_rejected(self):self.tight["scenarios"][0]["entry"]["temperature_degC"][0]="49";self.reject()
    def test_heat_node_removed_rejected(self):self.tight["platform"]["node_order"].pop();self.reject()
    def test_idle_policy_edit_rejected(self):self.tight["execution_rules"]["idle_delay_ms"]="1";self.reject()
    def test_weight_edit_rejected(self):self.tight["scenarios"][0]["weight"]="1";self.reject()
    def test_dependency_edit_rejected(self):self.tight["scenarios"][0]["dependencies"].pop();self.reject()
    def test_request_count_edit_rejected(self):self.tight["settings"]["requests_per_application"]=2;self.reject()
    def test_additional_hidden_input_rejected(self):self.tight["hidden_hint"]="answer";self.reject()
    def test_bool_label_type_edit_rejected(self):self.tight["ablation_input"]=0;self.reject()
    def test_common_physical_drift_rejected(self):
        for p in self.packets.values():p["instance"]["platform"]["ambient_temperature_degC"]="24"
        self.reject()

    def test_common_reference_and_deadline_drift_rejected(self):
        for p in self.packets.values():
            for scene in p["instance"]["scenarios"]:
                for r in scene["requests"]:
                    r["reference_CPU_H_chain_ms"]="100"
                    r["relative_deadline_ms"]=str(F(p["instance"]["settings"]["deadline_beta"])*100)
                    r["deadline_ms"]=r["relative_deadline_ms"]
        self.reject()

    def test_pure_checks_without_scientific_backend_imports(self):
        import sys
        with patch.dict(sys.modules,{"heft_method":None,"thermal":None,"milp":None,"scipy.optimize":None}):
            validate_inputs(prepare_inputs())


if __name__=="__main__":unittest.main()
