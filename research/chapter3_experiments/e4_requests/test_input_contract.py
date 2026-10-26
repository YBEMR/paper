"""Pure request-copy contracts and fixed handwritten legality fixtures.

No HEFT, MILP, thermal propagation or SAFE. A handwritten legal fixture only
checks scheduling rules, not whole-domain feasibility or continuous safety.
"""
from copy import deepcopy
from fractions import Fraction as F
import unittest
from unittest.mock import patch

from h02_pair_preflight.common import ContractError, sha
from inputs import load_config
from schedules import validate_schedule
from e4_requests.input_contract import (BASE_ID, DOUBLE_ID, PROBLEM_IDS, _normalize,
    prepare_inputs, validate_inputs, weighted_request_denominator_if_all_complete)


# A fixed declared pattern, no enumeration or objective-driven selection.
HANDWRITTEN={
    "A.pre":("CPU1",(0,10)), "A.main":("NPU0",(10,40)), "A.post":("CPU1",(40,70)),
    "B.pre":("CPU2",(0,15)), "B.main":("NPU0",(70,105)), "B.post":("CPU2",(105,140)),
    "C.pre":("CPU2",(0,15)), "C.main":("GPU0",(15,60)), "C.post":("CPU2",(60,105))}


def handwritten_candidate(instance):
    candidate={"scenes":{}}
    for scene in instance["scenarios"]:
        requests={r["id"]:r for r in scene["requests"]}
        rows=[]
        for stage in scene["stage_instances"]:
            unit,starts=HANDWRITTEN[stage["shared_stage_id"]]
            copy=requests[stage["request_id"]]["copy_index"]
            rows.append({"stage_id":stage["id"],"unit":unit,"opp":"H","start_ms":str(starts[copy-1])})
        candidate["scenes"][scene["id"]]=rows
    return candidate


def row(candidate,scene="AB_offset_0ms",suffix="A_r2::A.post"):
    return next(r for r in candidate["scenes"][scene] if r["stage_id"].endswith(suffix))


class RequestInputContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.original=prepare_inputs()
    def setUp(self):
        self.packets=deepcopy(self.original)
        self.base=self.packets[BASE_ID]["instance"]
        self.double=self.packets[DOUBLE_ID]["instance"]
    def reject(self):
        with self.assertRaises(ContractError):validate_inputs(self.packets)

    def test_original_pair_passes(self):
        proof=validate_inputs(self.packets)
        self.assertEqual(proof["state"],"STATIC_REQUEST_INPUT_CONTRACT_PASSED")
        for pid,count in ((BASE_ID,1),(DOUBLE_ID,2)):
            r=proof["inputs"][pid]
            self.assertEqual(r["requests_per_application"],count)
            self.assertEqual(r["deployment_stage_count"],9)
            self.assertEqual(r["total_catalog_mode_count"],66)
            self.assertEqual(r["total_stage_executions_across_alternative_scenarios"],12*count)
            for scene in r["scenes"].values():
                self.assertEqual(scene["requests"],2*count)
                self.assertEqual(scene["stage_executions"],6*count)
            self.assertEqual(r["normalized_input_sha256"],sha(self.base))
        self.assertFalse(proof["candidate_search_performed"])
        self.assertFalse(proof["thermal_propagation_performed"])
        self.assertFalse(proof["real_SAFE_created"])

    def test_original_generator_labels(self):
        self.assertEqual(self.double["condition_id"],"requests_2")
        self.assertEqual(self.double["experiment_group"],"2_request_count")
        self.assertFalse(self.double["ablation_input"])
        self.assertTrue(self.base["ablation_input"])

    def test_fresh_raw_and_auto_config_supported(self):
        self.assertEqual(prepare_inputs(load_config()),self.original)
        self.assertEqual(prepare_inputs(self.packets[BASE_ID]["config"]),self.original)

    def test_no_mutation(self):
        old=deepcopy(self.packets);validate_inputs(self.packets);self.assertEqual(old,self.packets)
        c=load_config();old=deepcopy(c);prepare_inputs(c);self.assertEqual(old,c)

    def test_packet_copies_independent(self):
        self.packets[BASE_ID]["config"]["platform"]["node_order"].pop()
        self.assertEqual(self.packets[DOUBLE_ID],self.original[DOUBLE_ID])

    def test_remove_copy_two_normalizes_exact_base(self):
        self.assertEqual(_normalize(self.double,self.base),self.base)
        self.assertEqual(_normalize(self.base,self.base),self.base)

    def test_platform_modes_and_thermal_conditions_unchanged(self):
        for field in ("platform","execution_rules","stage_modes","duration_scale","window_ms","start_grid_ms","response_variant"):
            self.assertEqual(self.double[field],self.base[field])
        for ds,bs in zip(self.double["scenarios"],self.base["scenarios"]):
            for field in ("weight","entry","maximum_temperature_degC","application_pair"):
                self.assertEqual(ds[field],bs[field])

    def test_all_copies_zero_release_and_same_individual_deadline(self):
        for ds,bs in zip(self.double["scenarios"],self.base["scenarios"]):
            original={r["application"]:r for r in bs["requests"]}
            for r in ds["requests"]:
                self.assertEqual(r["release_ms"],"0")
                self.assertEqual(r["deadline_ms"],original[r["application"]]["deadline_ms"])
                self.assertEqual(r["relative_deadline_ms"],original[r["application"]]["relative_deadline_ms"])

    def test_shared_Stage_identity_across_copies_and_scenes(self):
        for scene in self.double["scenarios"]:
            requests={r["id"]:r for r in scene["requests"]}
            by_shared={}
            for stage in scene["stage_instances"]:
                by_shared.setdefault(stage["shared_stage_id"],set()).add(requests[stage["request_id"]]["copy_index"])
            self.assertTrue(all(copies=={1,2} for copies in by_shared.values()))
            self.assertEqual({s["shared_stage_id"] for s in scene["stage_instances"] if s["application"]=="A"},
                             {"A.pre","A.main","A.post"})

    def test_weighted_denominator_is_two_and_four_not_four_and_eight(self):
        self.assertEqual(weighted_request_denominator_if_all_complete(self.base),2)
        self.assertEqual(weighted_request_denominator_if_all_complete(self.double),4)
        for instance in (self.base,self.double):
            raw=sum(len(s["requests"]) for s in instance["scenarios"])
            self.assertNotEqual(weighted_request_denominator_if_all_complete(instance),raw)

    def test_denominator_weight_checks(self):
        for values in (("-1","2"),("1","1"),("0","0")):
            instance=deepcopy(self.double)
            for s,w in zip(instance["scenarios"],values):s["weight"]=w
            with self.assertRaises(ContractError):weighted_request_denominator_if_all_complete(instance)

    def test_handwritten_legality_fixtures_only_not_SAFE(self):
        for instance in (self.base,self.double):
            result=validate_schedule(instance,handwritten_candidate(instance))
            self.assertEqual(result["state"],"SCHEDULE_VALID_THERMAL_UNCHECKED")
            self.assertEqual(result["thermal_status"],"NOT_EVALUATED")
            self.assertEqual(result["energy_status"],"NOT_EVALUATED")

    def test_copy_two_different_unit_rejected_as_shared_mapping(self):
        c=handwritten_candidate(self.double);row(c)["unit"]="CPU2"
        result=validate_schedule(self.double,c)
        self.assertEqual(result["state"],"INVALID_SCHEDULE")
        self.assertEqual(result["reason"],"SHARED_DEPLOYMENT_MISMATCH")

    def test_cross_scene_shared_A_unit_still_required(self):
        c=handwritten_candidate(self.double);row(c,"AC_offset_0ms")["unit"]="CPU2"
        self.assertEqual(validate_schedule(self.double,c)["reason"],"SHARED_DEPLOYMENT_MISMATCH")

    def test_copy_two_individual_deadline_not_whole_window(self):
        c=handwritten_candidate(self.double);row(c)["start_ms"]="125"
        result=validate_schedule(self.double,c)
        self.assertEqual(result["reason"],"REQUEST_DEADLINE_EXCEEDED")
        self.assertIn("A_r2",result["details"]["request"])

    def test_copy_resource_overlap_still_rejected(self):
        c=handwritten_candidate(self.double);row(c,suffix="B_r2::B.pre")["start_ms"]="0"
        self.assertEqual(validate_schedule(self.double,c)["reason"],"EXECUTION_UNIT_OVERLAP")

    def test_copy_NPU_resource_overlap_still_rejected(self):
        c=handwritten_candidate(self.double);row(c,suffix="A_r2::A.main")["start_ms"]="20"
        self.assertEqual(validate_schedule(self.double,c)["reason"],"EXECUTION_UNIT_OVERLAP")

    def test_OPP_per_execution_not_shared_by_copy_identity(self):
        c=handwritten_candidate(self.double)
        for scene in c["scenes"]:row(c,scene,suffix="A_r1::A.post")["opp"]="L"
        self.assertEqual(validate_schedule(self.double,c)["state"],"SCHEDULE_VALID_THERMAL_UNCHECKED")

    def test_missing_second_copy_not_a_complete_candidate(self):
        c=handwritten_candidate(self.base)
        self.assertEqual(validate_schedule(self.double,c)["reason"],"INCOMPLETE_STAGE_COVERAGE")

    def test_extra_packet_rejected(self):self.packets["extra"]=deepcopy(self.packets[BASE_ID]);self.reject()
    def test_missing_packet_rejected(self):del self.packets[BASE_ID];self.reject()
    def test_wrong_input_ID_rejected(self):self.double["id"]=BASE_ID;self.reject()
    def test_extra_packet_field_rejected(self):self.packets[DOUBLE_ID]["seed_candidate"]={};self.reject()
    def test_wrong_objective_rejected(self):self.packets[DOUBLE_ID]["objective"]="OMIT_TEMP";self.reject()
    def test_config_mutation_rejected(self):self.packets[DOUBLE_ID]["config"]["defaults"]["requests_per_application"]=2;self.reject()
    def test_explicit_config_tuning_not_supported(self):
        c=load_config();c["defaults"]["requests_per_application"]=2
        with self.assertRaises(ContractError):prepare_inputs(c)

    def test_count_change_rejected(self):self.double["settings"]["requests_per_application"]=3;self.reject()
    def test_float_count_rejected(self):self.double["settings"]["requests_per_application"]=2.0;self.reject()
    def test_delayed_copy_release_rejected(self):self.double["scenarios"][0]["requests"][1]["release_ms"]="5";self.reject()
    def test_copy_deadline_relaxation_rejected(self):self.double["scenarios"][0]["requests"][1]["deadline_ms"]="247";self.reject()
    def test_copy_relative_deadline_relaxation_rejected(self):self.double["scenarios"][0]["requests"][1]["relative_deadline_ms"]="247";self.reject()
    def test_new_shared_ID_per_copy_rejected(self):self.double["scenarios"][0]["stage_instances"][3]["shared_stage_id"]="A.pre@@COPY2";self.reject()
    def test_removed_copy_rejected(self):self.double["scenarios"][0]["requests"].pop();self.reject()
    def test_removed_stage_rejected(self):self.double["scenarios"][0]["stage_instances"].pop();self.reject()
    def test_removed_dependency_rejected(self):self.double["scenarios"][0]["dependencies"].pop();self.reject()
    def test_cross_copy_dependency_added_rejected(self):
        s=self.double["scenarios"][0];s["dependencies"].append([s["stage_instances"][2]["id"],s["stage_instances"][3]["id"]]);self.reject()
    def test_mode_removed_rejected(self):self.double["stage_modes"]["A.main"].pop();self.reject()
    def test_mode_cost_mutation_rejected(self):self.double["stage_modes"]["A.main"][0]["activity_power_W"]="0";self.reject()
    def test_heat_node_removed_rejected(self):self.double["platform"]["node_order"].pop();self.reject()
    def test_initial_temperature_mutation_rejected(self):self.double["scenarios"][0]["entry"]["temperature_degC"][0]="49";self.reject()
    def test_temperature_limit_mutation_rejected(self):self.double["scenarios"][0]["maximum_temperature_degC"][0]="81";self.reject()
    def test_window_mutation_rejected(self):self.double["window_ms"]="401";self.reject()
    def test_grid_mutation_rejected(self):self.double["start_grid_ms"]="1";self.reject()
    def test_scenario_weight_mutation_rejected(self):self.double["scenarios"][0]["weight"]="1";self.reject()
    def test_bool_label_type_mutation_rejected(self):self.double["ablation_input"]=0;self.reject()
    def test_hidden_field_rejected(self):self.double["historical_best"]={};self.reject()
    def test_common_physics_mutation_rejected(self):
        for p in self.packets.values():p["instance"]["platform"]["ambient_temperature_degC"]="24"
        self.reject()

    def test_static_imports_no_scientific_backends(self):
        import sys
        with patch.dict(sys.modules,{"heft_method":None,"thermal":None,"milp":None}):
            validate_inputs(prepare_inputs())


if __name__=="__main__":unittest.main()
