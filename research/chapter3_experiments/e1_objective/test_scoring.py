"""Pure mock contracts: zero search, thermal propagation, or research SAFE."""
from copy import deepcopy
from fractions import Fraction as F
import unittest
from h02_pair_preflight.common import ContractError, sha
from e1_objective.mock_fixtures import make_fixture
from e1_objective.scoring import score_candidate


def score(f, objective="FULL", seconds=300):
    return score_candidate(**f, seconds=seconds, objective=objective)


def reseal(f):
    f["receipt"]["evidence_identity"] = {"input_sha256": sha(f["instance"]),
                                         "candidate_sha256": sha(f["candidate"])}


def update_legality(f, change):
    change(f["legality"])
    f["receipt"]["legality"] = deepcopy(f["legality"])


class ScoringContracts(unittest.TestCase):
    def reject(self, f, **kwargs):
        with self.assertRaises(ContractError): score(f, **kwargs)

    def test_full_score(self):
        f=make_fixture(); value=score(f)
        self.assertEqual(value["planning_score_J"], ["19/25", "19/25"])
        self.assertEqual(value["true_energy_J"], value["planning_score_J"])
        self.assertEqual(value["true_U_J"], f["receipt"]["safe_upper_bound_J"])
        self.assertEqual(value["candidate_sha256"], sha(f["candidate"]))
        self.assertEqual(value["input_sha256"], sha(f["instance"]))

    def test_omitted_score_keeps_true_U(self):
        f=make_fixture(); value=score(f, "OMIT_TEMP")
        self.assertEqual(value["planning_score_J"], ["18/25", "18/25"])
        self.assertEqual(value["true_energy_J"], ["19/25", "19/25"])
        self.assertEqual(value["true_U_J"], "19/25")

    def test_no_mutation(self):
        f=make_fixture(); before=deepcopy(f)
        score(f); score(f,"OMIT_TEMP")
        self.assertEqual(f,before)

    def test_omit_not_interval_subtraction(self):
        f=make_fixture(); eps=F(1,100000000)
        for r in f["receipt"]["scenes"].values():
            for name in ("external_common","temperature_correction"):
                exact=F(r["energy_components_J"][name][0])
                r["energy_components_J"][name]=[str(exact-eps),str(exact+eps)]
            r["energy_J"]=[str(F(19,25)-2*eps),str(F(19,25)+2*eps)]
        f["receipt"]["weighted_energy_J"]=[str(F(19,25)-2*eps),str(F(19,25)+2*eps)]
        f["receipt"]["safe_upper_bound_J"]=str(F(19,25)+2*eps)
        self.assertEqual(score(f,"OMIT_TEMP")["planning_score_J"],["18/25","18/25"])
        self.assertEqual(score(f)["planning_score_J"],f["receipt"]["weighted_energy_J"])

    def test_zero_weight_needs_safety(self):
        f=make_fixture(); f["instance"]["scenarios"][0]["weight"]="0"
        f["instance"]["scenarios"][1]["weight"]="1"; reseal(f)
        score(f,"OMIT_TEMP")
        f["receipt"]["scenes"]["AB"]["state"]="UNRESOLVED"
        self.reject(f,objective="OMIT_TEMP")

    def test_negative_weights(self):
        f=make_fixture(); f["instance"]["scenarios"][0]["weight"]="-1"
        f["instance"]["scenarios"][1]["weight"]="2"; reseal(f); self.reject(f)

    def test_weight_sum(self):
        f=make_fixture(); f["instance"]["scenarios"][0]["weight"]="0"; reseal(f); self.reject(f)

    def test_unknown_objective(self): self.reject(make_fixture(),objective="TEMP_ONLY")

    def test_root_budget(self):
        for seconds in (0,-1,True,float("inf"),float("nan")):
            with self.subTest(seconds=seconds): self.reject(make_fixture(),seconds=seconds)

    def test_strict_deadline(self):
        for value in (300,301,-1): self.reject(make_fixture(completed_at_s=value))
        score(make_fixture(completed_at_s=299.999))

    def test_bad_timestamp(self):
        for value in (None,True,"1",float("inf"),float("nan")):
            with self.subTest(value=value): self.reject(make_fixture(completed_at_s=value))

    def test_candidate_identity(self):
        f=make_fixture(); f["candidate"]["scenes"]["AB"][0]["start_ms"]="5"; self.reject(f)

    def test_input_identity(self):
        f=make_fixture(); f["instance"]["id"]="WRONG"; self.reject(f)

    def test_illegal_mode(self):
        f=make_fixture(); f["candidate"]["scenes"]["AB"][0]["opp"]="UNKNOWN"; reseal(f); self.reject(f)

    def test_float_start(self):
        f=make_fixture(); f["candidate"]["scenes"]["AB"][0]["start_ms"]=0.0; reseal(f); self.reject(f)

    def test_invalid_top_states(self):
        for state in ("INVALID_SCHEDULE","UNRESOLVED","THERMAL_VIOLATION"):
            f=make_fixture(); f["receipt"]["state"]=state; self.reject(f,objective="OMIT_TEMP")

    def test_legality_drift(self):
        f=make_fixture(); f["legality"]["scenes"]["AB"]["rows"]=[]; self.reject(f)

    def test_invalid_legality(self):
        f=make_fixture(); update_legality(f,lambda x:x.update(state="INVALID_SCHEDULE")); self.reject(f)

    def test_missing_scene(self):
        f=make_fixture(); f["receipt"]["scenes"].pop("AC"); self.reject(f)

    def test_incomplete_window(self):
        f=make_fixture(); f["receipt"]["scenes"]["AB"]["covered_until_s"]="1/5"; self.reject(f)

    def test_overtemperature_both_objectives(self):
        for objective in ("FULL","OMIT_TEMP"):
            f=make_fixture(); f["receipt"]["scenes"]["AB"]["peaks_degC"]["N0"]=["81","81"]
            self.reject(f,objective=objective)

    def test_violation(self):
        f=make_fixture(); f["receipt"]["violations"]=[{"state":"THERMAL_VIOLATION"}]; self.reject(f)

    def test_nested_technical(self):
        f=make_fixture(); f["receipt"]["scenes"]["AB"]["reason"]="INTERFACE_ERROR"; self.reject(f)

    def test_interval_order(self):
        f=make_fixture(); f["receipt"]["weighted_energy_J"][0]="1"; self.reject(f)

    def test_true_upper_not_planning_score(self):
        f=make_fixture(); f["receipt"]["safe_upper_bound_J"]="18/25"; self.reject(f,objective="OMIT_TEMP")

    def test_negative_power(self):
        f=make_fixture(); update_legality(f,lambda x:x["scenes"]["AB"]["segments"][0]["activity_by_node_W"].update(N0="-2")); self.reject(f)

    def test_baseline_consistency(self):
        f=make_fixture(); update_legality(f,lambda x:x["scenes"]["AB"]["segments"][0]["baseline_by_node_W"].update(N0="2")); self.reject(f)

    def test_segment_gap(self):
        f=make_fixture(); update_legality(f,lambda x:x["scenes"]["AB"]["segments"][1].update(start_ms="105",duration_ms="295")); self.reject(f)

    def test_segment_duration(self):
        f=make_fixture(); update_legality(f,lambda x:x["scenes"]["AB"]["segments"][0].update(duration_ms="99")); self.reject(f)

    def test_no_omitted_idle_tail(self):
        f=make_fixture(); update_legality(f,lambda x:x["scenes"]["AB"]["segments"].pop()); self.reject(f)

    def test_external_power(self):
        f=make_fixture(); update_legality(f,lambda x:x["scenes"]["AB"]["segments"][0].update(external_common_power_W="0")); self.reject(f)

    def test_exact_component_receipt_match(self):
        f=make_fixture(); r=f["receipt"]["scenes"]["AB"]
        r["energy_components_J"]["baseline"]=["39/100","39/100"]
        r["energy_components_J"]["temperature_correction"]=["1/20","1/20"]
        self.reject(f)

    def test_all_components_required(self):
        f=make_fixture(); f["receipt"]["scenes"]["AB"]["energy_components_J"].pop("temperature_correction"); self.reject(f)

    def test_malformed(self):
        f=make_fixture(); f["legality"]=None; self.reject(f)

    def test_distinct_identity(self):
        left,right=make_fixture(opp="L"),make_fixture(opp="H")
        self.assertNotEqual(score(left)["candidate_sha256"],score(right)["candidate_sha256"])
        self.assertEqual(score(left)["input_sha256"],score(right)["input_sha256"])


if __name__=="__main__": unittest.main()
