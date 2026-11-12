"""Small hand-authored adapter oracles, never formal random task families.

Stage numbers and q_ref values are test data. Physical RC, OPP, baseline and
temperature coefficients are copied unchanged from the existing source config.
Only the dedicated test runner may execute these helpers; importing this module
does not schedule, evaluate temperature, or construct a solver model.
"""

from copy import deepcopy
from fractions import Fraction as F
import json
from pathlib import Path

from research.chapter3_calibration_adjustment.fixtures import manual_bundle
from research.chapter3_calibration_adjustment.transforms import derive_staggered
from research.chapter3_calibration_adjustment.window_policy import make_window_receipt
from research.chapter3_deadline_reference.contract import exact
from research.chapter3_deadline_reference.deadlines import make_deadlines, inherit_deadlines
from research.chapter3_deadline_reference.scheduler import build_references
from research.chapter3_workload_calibration.generator import (
    stamp, subset, transform, request_sources,
)


BETA = "13/10"  # Explicit hand-test value, not the frozen formal beta.
CONFIG_PATH = Path(__file__).resolve().parents[1] / "chapter3_experiments/config_v01.json"


def source_config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def small_base(*, scene_count=2, accelerators=False, restrict_later=False):
    """4+2 Stage, exact profiles; ID reuse across scenes is deliberate."""
    if scene_count not in (1, 2, 8):
        raise ValueError("Explicit manual scene count must be 1, 2 or 8")
    bundle = manual_bundle(large_nodes=4, small_nodes=2,
                           offsets=tuple(str(5 * i) for i in range(scene_count)))
    data = bundle["time_contract"]
    if accelerators:
        choices = {
            "L1.s0001": ("CPU1", "CPU2", "GPU0", "NPU0"),
            "L1.s0002": ("GPU0",), "L1.s0003": ("NPU0",),
        }
        for sid, units in choices.items():
            old = deepcopy(data["stage_profiles"][sid]["units"]["CPU1"])
            data["stage_profiles"][sid]["units"] = {u: deepcopy(old) for u in units}
            bundle["physical_profiles"][sid]["units"] = {
                u: {"d_ref_ms": old["d_ref_ms"], "alpha": old["alpha"],
                    "q_ref_W": "3/2"} for u in units}
            for scene in data["scenarios"]:
                for stage in scene["stage_instances"]:
                    if stage["shared_stage_id"] == sid:
                        stage["legal_units"] = list(units)
    if restrict_later:
        if scene_count != 8:
            raise ValueError("Manual S1 support case requires eight scenes")
        # The reference mapping must use CPU2 because of later scenes. Its
        # one/two-scene formal subset must still retain CPU1 as a legal choice.
        for scene in data["scenarios"][2:]:
            for stage in scene["stage_instances"]:
                if stage["shared_stage_id"] == "L1.s0001":
                    stage["legal_units"] = ["CPU2"]
    bundle["profile_traces"]["L1.s0001"]["test_note"] = "already_scaled_d_ref_not_work_times_d_ref"
    return stamp(bundle)


def evidence(bundle):
    refs = build_references(bundle["time_contract"])
    due = make_deadlines(bundle["time_contract"], refs["timetables"]["H"],
                         beta=BETA, reference_topology_id=bundle["time_contract"]["topology_id"])
    return {"state": "TIME_CALIBRATION_COMPLETE", "workload": bundle,
            "reference": refs, "deadlines": {BETA: due}, "fixture_only": True,
            "beta_selected": None, "thermal_status": "NOT_EVALUATED",
            "energy_status": "NOT_EVALUATED"}


def inherited_evidence(base, child):
    receipt = inherit_deadlines(base["workload"]["time_contract"], base["deadlines"][BETA],
        child["time_contract"], request_sources=request_sources(base["workload"], child))
    return {"workload": child, "deadlines": {BETA: receipt}, "fixture_only": True}


def package(base, members, *, kind, member_key):
    window = make_window_receipt("manual-formal-adapter-" + kind, kind, members,
                                 beta=BETA, baseline=base)
    chosen = members[member_key]
    return {"base": base, "members": members, "bundle": chosen["workload"],
            "deadline_receipt": chosen["deadlines"][BETA], "window_receipt": window,
            "member_key": member_key, "config": source_config(),
            "instance_id": "fixture_formal_adapter_" + kind}


def base_case(*, accelerators=False, scene_count=2):
    base = evidence(small_base(scene_count=scene_count, accelerators=accelerators))
    return package(base, {"base": base}, kind="S2", member_key="base")


def s1_case(*, count=2, restrict_later=False):
    base = evidence(small_base(scene_count=8, restrict_later=restrict_later))
    members = {str(n): inherited_evidence(base, subset(base["workload"], n))
               for n in (1, 2, 4, 6, 8)}
    return package(base, members, kind="S1", member_key=str(count))


def multi_output_case():
    """Manual S4 K2,2 DAG has two required outputs, with inherited deadlines."""
    base = evidence(small_base())
    child = deepcopy(base["workload"])
    data = child["time_contract"]
    data["derivation"] = {"axis": "S4", "parent_contract_hash": child["contract_hash"]}
    data["variant_id"] = "manual_layered_two_outputs"
    data["topology_id"] = "manual_layered_two_outputs"
    child["transform"] = {"axis": "S4", "parent_bundle_hash": base["workload"]["bundle_hash"],
                          "rule": "manual_two_layer_fixture_only"}
    large = child["applications"]["L1"]
    a, b, c, d = large["nodes"]
    large["edges"] = [[a, c], [a, d], [b, c], [b, d]]
    large["required_outputs"] = [c, d]
    large["trace"] = {"hand_written": True, "purpose": "multiple_required_outputs"}
    for scene in data["scenarios"]:
        scene["dependencies"] = sorted(
            [[a + ".r1", b + ".r1"] for spec in child["applications"].values()
             for a, b in spec["edges"]])
    derived = inherited_evidence(base, stamp(child))
    return package(base, {"base": base, "two_outputs": derived}, kind="S4", member_key="two_outputs")


def s7_case(*, member_key="staggered"):
    base = evidence(small_base())
    synchronous = transform(base["workload"], "S7", value=2,
                            settings={"s7_release_rule": "synchronous_same_application"})
    staggered = derive_staggered(base)
    members = {"single": base, "synchronous": inherited_evidence(base, synchronous),
               "staggered": inherited_evidence(base, staggered)}
    return package(base, members, kind="S7", member_key=member_key)


def adapter_args(case):
    return (case["bundle"], case["deadline_receipt"], case["window_receipt"]), {
        "member_key": case["member_key"], "config": case["config"],
        "instance_id": case["instance_id"]}


def remap_reference_candidate(case, result, *, opp="H"):
    """Only a test witness conversion; never a planner's free initial point."""
    source = case["base"]["reference"]["timetables"][opp]
    ids = {s["id"] for s in result["instance"]["scenarios"]}
    return {"scenes": {sid: [{**row, "stage_id": sid + "::" + row["stage_id"]}
                              for row in rows] for sid, rows in source["scenes"].items() if sid in ids}}
