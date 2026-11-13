"""Prospectively fixed unseen two-scene inputs; no algorithm or heat evaluation.

Reuse chapter 3 profile, topology, deadline-reference and formal-export code.
Only the selected two scenes define this experiment's BASE and time reference.
The H timetable is generation evidence, never an algorithm initialization.
"""
from copy import deepcopy
from fractions import Fraction as F
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

REPO = Path(__file__).resolve().parents[3]
SOURCE_CONFIG = REPO / "research/chapter3_experiments/config_v01.json"
NAMESPACE = "ch4-unseen-scale-v1"
ROOTS = (("U01", 2026111201), ("U02", 2026111202))
SCALES = (6, 12)
BETA = "13/10"


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False) + "\n", encoding="utf-8")


def fixed_plan():
    from research.chapter3_workload_calibration.configuration import approved_configuration
    return {
        "schema": "chapter4-unseen-scale-input-plan-v1",
        "namespace": NAMESPACE,
        "roots": [{"root_id": r, "seed": s} for r, s in ROOTS],
        "scales": list(SCALES), "scene_ids": ["C1", "C2"],
        "scene_weights": ["1/2", "1/2"],
        "scene_pool": "A", "compatibility_pool": "heterogeneous",
        "initial_temperature_C": ["50"] * 4, "maximum_temperature_C": "80",
        "start_grid_ms": "5", "deadline_beta": BETA,
        "settings": approved_configuration()["settings"],
        "two_scene_rule": "take original C1/C2 before any reference mapping or timetable; declare this projection as a new BASE",
        "deadline_rule": "a + (13/10)*(F_H-a), original independent time-only H constructor, on the selected two scenes",
        "window_rule": "5*ceil(max(two-scene absolute deadlines)/5)",
        "scale_rule": "existing build_base S2 extension: old profiles and edges retained; total work and window are not held constant",
        "scope": "new named parameter roots within the existing synthetic profile and branch_join topology families; not unseen topology families",
        "selection": "two root tuples fixed before generation; no replacement, ranking, algorithm or thermal screening",
        "method_inputs": "config.json and instance.json only; no reference schedule or fixed deployment",
        "source_config_sha256": _sha(SOURCE_CONFIG),
    }


def _project_base(eight, parent=None):
    """Declare the selected two scenes as the base, preserving full lineage."""
    from research.chapter3_workload_calibration.generator import stamp, validate_transform
    out = deepcopy(eight)
    out["time_contract"]["scenarios"] = out["time_contract"]["scenarios"][:2]
    for scene in out["time_contract"]["scenarios"]:
        scene["weight"] = "1/2"
    out["time_contract"]["variant_id"] = f"base_{out['provenance']['scale']}_two_scene"
    out["time_contract"]["derivation"] = {
        "axis": "BASE" if parent is None else "S2",
        "parent_contract_hash": None if parent is None else parent["contract_hash"],
    }
    out["provenance"]["two_scene_base"] = {
        "source_eight_scene_bundle_hash": eight["bundle_hash"],
        "source_eight_scene_contract_hash": eight["contract_hash"],
        "selected_scene_ids": ["C1", "C2"],
        "reference_created_after_selection": True,
    }
    stamp(out)
    if parent is not None:
        validate_transform(parent, out)
    return out


def _time_evidence(bundle):
    from research.chapter3_deadline_reference.contract import content_hash
    from research.chapter3_deadline_reference.scheduler import choose_mapping, build_timetable
    from research.chapter3_deadline_reference.checker import check_timetable
    from research.chapter3_deadline_reference.deadlines import make_deadlines
    data = bundle["time_contract"]
    record = choose_mapping(data)
    table = build_timetable(data, record["mapping"], "H")
    check = check_timetable(data, table, required_opp="H")
    if check["state"] != "TIME_STRUCTURAL_VALID":
        raise ValueError("REFERENCE_TIME_CHECK_FAILED")
    due = make_deadlines(data, table, beta=BETA, reference_topology_id="branch_join")
    return {
        "state": "TIME_CALIBRATION_COMPLETE", "workload": bundle,
        "reference": {"state": "REFERENCES_COMPLETE", "contract_hash": bundle["contract_hash"],
                      "mapping_record": record, "mapping_origin_hash": content_hash(record),
                      "timetables": {"H": table}, "checks": {"H": check}},
        "deadlines": {BETA: due},
        "counters": {"mapping_constructions": 1, "timetable_constructions": 1,
                     "scene_schedules": 2, "thermal_evaluations": 0, "HEFT_ON_SA_calls": 0},
        "thermal_status": "NOT_EVALUATED", "energy_status": "NOT_EVALUATED",
    }


def _static_check(adapted, evidence):
    # Existing schedule validator reconstructs power segments but never integrates heat.
    sys.path.insert(0, str(REPO / "research/chapter3_experiments"))
    from schedules import validate_schedule
    instance, receipt = adapted["instance"], adapted["receipt"]
    table = evidence["reference"]["timetables"]["H"]
    candidate = {"scenes": {
        sid: [{**row, "stage_id": receipt["identity_map"][sid]["stages"][row["stage_id"]]}
              for row in rows] for sid, rows in table["scenes"].items()}}
    check = validate_schedule(instance, candidate)
    if check["state"] != "SCHEDULE_VALID_THERMAL_UNCHECKED":
        raise ValueError("FORMAL_INPUT_STATIC_CHECK_FAILED:" + json.dumps(check))
    assert len(instance["scenarios"]) == 2
    assert sum(F(s["weight"]) for s in instance["scenarios"]) == 1
    assert all(s["entry"]["temperature_degC"] == ["50"] * 4 for s in instance["scenarios"])
    assert all(s["maximum_temperature_degC"] == ["80"] * 4 for s in instance["scenarios"])
    assert instance["platform"] == adapted["config"]["platform"]
    assert receipt["fixed_deployment"] is None and receipt["formal_initial_solution"] is None
    return {"state": check["state"], "time_reference_candidate": candidate,
            "thermal_evaluations": 0, "reference_is_not_method_initialization": True}


def _metrics(adapted, evidence):
    from research.chapter3_calibration_adjustment.transforms import structure_metrics
    from research.chapter3_deadline_reference.contract import duration
    instance, bundle = adapted["instance"], evidence["workload"]
    data = bundle["time_contract"]
    paths = {}
    for aid, app in bundle["applications"].items():
        lengths = {n: min(duration(data, n, unit, "H") for unit in data["stage_profiles"][n]["units"])
                   for n in app["nodes"]}
        paths[aid] = structure_metrics(app["nodes"], app["edges"], lengths)
    scene_ids = [set(s["shared_stage_id"] for s in scene["stage_instances"]) for scene in instance["scenarios"]]
    return {"stages_per_scene": [len(s["stage_instances"]) for s in instance["scenarios"]],
            "shared_stage_identities": len(instance["stage_modes"]),
            "identities_present_in_both_scenes": len(scene_ids[0] & scene_ids[1]),
            "mode_count": sum(len(ms) for ms in instance["stage_modes"].values()),
            "modes_per_stage": {s: len(ms) for s, ms in instance["stage_modes"].items()},
            "window_ms": instance["window_ms"], "optimistic_H_critical_paths": paths,
            "requests": {s["id"]: [{k: r[k] for k in ("id", "release_ms", "deadline_ms", "relative_deadline_ms")}
                                     for r in s["requests"]] for s in instance["scenarios"]},
            "H_reference_completions_ms": evidence["reference"]["checks"]["H"]["completions_ms"],
            "work_units_by_scene": {s["id"]: str(sum(F(data["stage_profiles"][t["shared_stage_id"]]["work_units"])
                                                        for t in s["stage_instances"])) for s in data["scenarios"]},
            "profile_categories": {s: t["category"] for s, t in bundle["profile_traces"].items()}}


def build_inputs(output):
    from research.chapter3_workload_calibration.profiles import load_catalog
    from research.chapter3_workload_calibration.generator import build_base
    from research.chapter3_calibration_adjustment.window_policy import make_window_receipt
    from research.chapter3_formal_input_adapter.core import adapt_bundle
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    plan = fixed_plan()
    _save(out / "input_plan.json", plan)  # Saved before drawing either root.
    catalog = load_catalog(SOURCE_CONFIG)
    config = json.loads(SOURCE_CONFIG.read_text(encoding="utf-8"))
    cases, total_seconds = [], time.perf_counter()
    for root_id, seed in ROOTS:
        raw_parent = parent = None
        for scale in SCALES:
            start = time.perf_counter()
            case_id = f"{root_id}__n{scale}"
            directory = out / case_id
            directory.mkdir()
            raw = build_base(catalog, root_id=root_id, namespace=NAMESPACE, seed=seed,
                             scene_pool="A", compatibility_pool="heterogeneous", scale=scale,
                             settings=plan["settings"], parent=raw_parent)
            bundle = _project_base(raw, parent)
            evidence = _time_evidence(bundle)
            window = make_window_receipt(case_id, "S2", {"base": evidence}, beta=BETA, baseline=evidence)
            adapted = adapt_bundle(bundle, evidence["deadlines"][BETA], window,
                                   member_key="base", config=config, instance_id=case_id)
            check = _static_check(adapted, evidence)
            metrics = _metrics(adapted, evidence)
            if metrics["stages_per_scene"] != [scale, scale]:
                raise ValueError("SCALE_MISMATCH")
            _save(directory / "config.json", adapted["config"])
            _save(directory / "instance.json", adapted["instance"])
            _save(directory / "generation_evidence.json", {
                "unprojected_eight_scene_bundle": raw, "two_scene_evidence": evidence,
                "window_receipt": window, "adaptation_receipt": adapted["receipt"],
                "static_check": check, "metrics": metrics,
                "generation_seconds": time.perf_counter() - start})
            cases.append({"case_id": case_id, "root_id": root_id, "seed": seed,
                          "stages_per_scene": scale, "scenes": 2,
                          "config_path": f"{case_id}/config.json", "instance_path": f"{case_id}/instance.json",
                          "config_sha256": _sha(directory / "config.json"),
                          "instance_sha256": _sha(directory / "instance.json"),
                          "generation_evidence_path": f"{case_id}/generation_evidence.json",
                          "generation_evidence_sha256": _sha(directory / "generation_evidence.json"),
                          "metrics": metrics})
            raw_parent, parent = raw, bundle
    manifest = {"schema": "chapter4-unseen-scale-inputs-v1", "plan_sha256": _sha(out / "input_plan.json"),
                "cases": cases, "input_construction_seconds": time.perf_counter() - total_seconds,
                "counters": {"mapping_constructions": 4, "H_timetable_constructions": 4,
                             "scene_schedules": 8, "thermal_evaluations": 0, "HEFT_ON_SA_calls": 0}}
    _save(out / "inputs_manifest.json", manifest)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = build_inputs(args.output)
    print(json.dumps({"cases": [r["case_id"] for r in result["cases"]], "counters": result["counters"]}))
