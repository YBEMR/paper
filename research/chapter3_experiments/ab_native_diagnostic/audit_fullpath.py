"""Audit the fixed-mapping delivery and its stored continuous receipts."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def audit(task):
    plan = read(task / "PLAN.json")
    run = task / "runs/native_once"
    condition = run / "condition"
    driver = read(run / "driver_audit.json")
    result = read(condition / "result.json")
    native = condition / "matlab"
    scenes = []
    for index, sid in enumerate(("AB_offset_0ms", "AC_offset_0ms"), 1):
        prefix = native / f"request_{index:06d}"
        paths = {suffix: prefix.with_suffix("." + suffix) for suffix in
                 ("response.json", "equivalence.json", "original_admission_final.json", "native.mat")}
        row = {"scene": sid, "native_final_SAFE": False,
               "sources_sha256": {k: digest(p.read_bytes()) for k, p in paths.items() if p.is_file()}}
        if not paths["response.json"].is_file():
            scenes.append(dict(row, state="NO_NATIVE_RESPONSE"))
            continue
        response = read(paths["response.json"])
        options, output = response.get("options", {}), response.get("output", {})
        roots = [c["values"] for c in response.get("callbacks", [])
                 if c["values"].get("phase") == "rootlp"]
        status_conflict = bool(response.get("exitflag") == 1
            and options.get("AbsoluteGapTolerance") == options.get("RelativeGapTolerance") == 0
            and ((output.get("absolutegap") or 0) > 0 or (output.get("relativegap") or 0) > 0))
        row.update(native_status=response.get("status"), exitflag=response.get("exitflag"),
                   native_output=output, native_options=options, native_fval=response.get("fval"),
                   native_call_s=response.get("phase_seconds", {}).get("intlinprog_call"),
                   native_rootlp=roots, optimal_status_gap_conflict=status_conflict,
                   native_final_length=len(response.get("x") or []),
                   independently_proven_optimal=False)
        if paths["equivalence.json"].is_file():
            eq = read(paths["equivalence.json"])
            row.update(exact_pairs=eq["exact_pairs_moved"], model_sha256=eq["original_payload_sha256"])
        if not row["native_final_length"] or not paths["original_admission_final.json"].is_file():
            scenes.append(dict(row, state="NO_ADMITTED_NATIVE_FINAL"))
            continue
        admission = read(paths["original_admission_final.json"])
        row["original_rows"] = admission
        binary = loadmat(paths["native.mat"], variable_names=["x", "initialPoint"])
        x = binary["x"].reshape(-1)
        row["returned_same_x0_bytes"] = x.tobytes() == binary["initialPoint"].reshape(-1).tobytes()
        if x.size != row["native_final_length"] or not np.array_equal(x, response["x"]):
            raise ValueError(f"Native MAT and JSON final vector disagree: {sid}")
        # The final recorder source is bound to the returned vector by the
        # unchanged scene driver. A duplicate log binds the exact same schedule.
        entries = [json.loads(line) for line in
                   (condition / f"scene_{index-1}/diagnostic_events.jsonl").read_bytes().splitlines()]
        finals = [e for e in entries if e.get("source") == "round1:final"
                  and e.get("event") in ("candidate_evaluated", "duplicate_receipt_reused")]
        if len(finals) != 1:
            scenes.append(dict(row, state="NO_UNIQUE_FINAL_RECORDER_BINDING"))
            continue
        final_key = finals[0]["candidate_sha256"]
        original_records = result["scenes"][sid]["original_scene_evaluations"]
        receipt = next((r["receipt"] for r in original_records
                        if r.get("accepted_safe") and
                        digest(json.dumps(r["candidate"], sort_keys=True).encode()) == final_key), None)
        if receipt:
            v = receipt["result"]
            row["native_final_SAFE"] = bool(
                admission["admission"]["accepted_numerically"]
                and admission["at_elapsed_s"] < plan["root_seconds"]
                and receipt["state"] == "SAFE" and v["complete"] and v["energy_accuracy_met"]
                and Fraction(v["covered_until_s"]) == Fraction(2, 5) and not v["violations"]
                and receipt["completed_at_elapsed_s"] < plan["root_seconds"])
            row["original_SAFE_energy_J"] = receipt["energy_J"]
            row["original_SAFE_receipt_sha256"] = receipt["receipt_sha256"]
            row["final_candidate_sha256"] = final_key
        scenes.append(row)
    initial = result.get("initial_global_weighted_energy_J")
    best = result.get("weighted_energy_J")
    improved = bool(initial and best and Fraction(best[1]) < Fraction(initial[0]))
    return {
        "plan_sha256": digest((task / "PLAN.json").read_bytes()),
        "delivery_gate_pass": bool(driver["native_technical_pass"]
                                   and all(r["native_final_SAFE"] for r in scenes)),
        "scenes": scenes, "method_elapsed_s": driver["method_stopped_elapsed_s"],
        "cleanup_s": driver["cleanup_elapsed_s"], "cleanup_verified": driver["physical_cleanup_verified"],
        "initial_weighted_energy_J": initial, "best_weighted_energy_J": best,
        "strict_interval_improvement": improved,
        "best_source": result.get("safe_solution_source"),
        "driver_sha256": digest((run / "driver_audit.json").read_bytes()),
        "condition_result_sha256": digest((condition / "result.json").read_bytes()),
        "formal_comparison": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    report = audit(args.task)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({k: report[k] for k in ("delivery_gate_pass", "method_elapsed_s",
                     "strict_interval_improvement", "best_weighted_energy_J")}))
