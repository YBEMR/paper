"""Summarize the frozen closure batch from saved files only.

No optimizer, model builder, evaluator or execution entry is imported. A SAFE
under the no-80-C planning view is not silently promoted to original-80-C SAFE.
Use: python -B summarize_closure.py BATCH --plan PLAN --out-dir NEW_DIRECTORY
"""
import argparse
from collections import Counter
import csv
from decimal import Decimal, localcontext, ROUND_FLOOR, ROUND_CEILING
from fractions import Fraction as Q
import hashlib
import json
from pathlib import Path

try:
    from .completion_metrics import build_completion_metrics
except ImportError:
    from completion_metrics import build_completion_metrics

ROOT = Path(__file__).resolve().parents[2]
COMPONENTS = ("baseline", "activity", "external_common", "temperature_correction")
NORMAL = {"NORMAL_COMPLETION", "NORMAL_TIME_LIMIT", "NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST", "NORMAL_UNRESOLVED"}


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def finite_scalar(value):
    return type(value) in (str, int, float) and Decimal(str(value)).is_finite()


def number(value, upper=False):
    if value is None:
        return None
    value = Q(str(value))
    with localcontext() as ctx:
        ctx.prec = 55
        ctx.rounding = ROUND_CEILING if upper else ROUND_FLOOR
        return str(Decimal(value.numerator) / Decimal(value.denominator))


def pair(value):
    if value is None:
        return None
    assert len(value) == 2
    lo, hi = map(Q, value)
    assert lo <= hi
    return [str(lo), str(hi)]


def qtile(values, probability):
    ordered = sorted(map(Q, values))
    if not ordered:
        return None
    pos = (len(ordered) - 1) * Q(probability)
    index = pos.numerator // pos.denominator
    fraction = pos - index
    return ordered[index] if not fraction else ordered[index] * (1 - fraction) + ordered[index + 1] * fraction


def dispersion(values):
    values = list(map(Q, values))
    if not values:
        return {"n": 0, "median": None, "minimum": None, "maximum": None, "IQR": None}
    mean = sum(values) / len(values)
    with localcontext() as ctx:
        ctx.prec = 35
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        deviation = (Decimal(variance.numerator) / Decimal(variance.denominator)).sqrt()
    return {"n": len(values), "median": str(qtile(values, Q(1, 2))),
            "minimum": str(min(values)), "maximum": str(max(values)),
            "q1": str(qtile(values, Q(1, 4))), "q3": str(qtile(values, Q(3, 4))),
            "IQR": str(qtile(values, Q(3, 4)) - qtile(values, Q(1, 4))),
            "range": str(max(values) - min(values)), "mean": str(mean),
            "population_standard_deviation_decimal": str(deviation)}


def saved_physics(evaluation, instance):
    """Extract complete saved physical values; does not establish new SAFE."""
    scenes = evaluation.get("scenes") or {}
    definitions = {s["id"]: s for s in instance["scenarios"]}
    if set(scenes) != set(definitions) or any(s.get("complete") is not True for s in scenes.values()):
        return {"complete": False, "energy_interval_J": None, "components_J": {}, "peak_degC": None}
    weights = {sid: Q(s["weight"]) for sid, s in definitions.items()}
    assert sum(weights.values()) == 1
    energy = [str(sum(weights[sid] * Q(s["energy_J"][i]) for sid, s in scenes.items())) for i in (0, 1)]
    parts = {key: [str(sum(weights[sid] * Q(s["energy_components_J"][key][i]) for sid, s in scenes.items())) for i in (0, 1)] for key in COMPONENTS}
    peaks = [str(max(Q(v[i]) for s in scenes.values() for v in s["peaks_degC"].values())) for i in (0, 1)]
    return {"complete": True, "energy_interval_J": energy, "components_J": parts, "peak_degC": peaks,
            "scene_peaks_degC": {sid: s["peaks_degC"] for sid, s in scenes.items()}}


def summarize(folder, plan_path):
    folder, plan_path = Path(folder).resolve(), Path(plan_path).resolve()
    source_hashes = {}

    def load(path, optional=False):
        path = Path(path)
        if optional and not path.exists():
            return {}
        source_hashes[str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)] = sha(path)
        return read(path)

    plan = load(plan_path)
    inputs = load(plan_path.parent / "inputs.json")
    assert plan["cases"] == inputs["cases"]
    assert plan["scope"]["method_seconds_each"] == 600
    batch = load(folder / "batch.json", optional=True)
    if batch:
        assert batch["plan_sha256"] == sha(plan_path)
    approval = load(plan_path.parent / "user_approval.json", optional=True)
    rows = []
    for job in plan["jobs"]:
        case = plan["cases"][job["case"]]
        for field, expected in case["sha256"].items():
            assert sha(ROOT / case[field]) == expected, case[field]
        instance = load(ROOT / case["input_file"])
        original = load(ROOT / case["posterior_file"])
        declaration = load(ROOT / case["declaration_file"])
        static_size = load(ROOT / case["static_size_file"])
        enforce = declaration["enforce_operating_limit"]
        slot = folder / "slots" / (job["id"] + "__method")
        rawpath = slot / "worker/raw_result.json"
        meta = load(slot / "slot_result.json", optional=True)
        worker = load(slot / "worker/worker_result.json", optional=True)
        row = dict(id=job["id"], method=job["method"], seed=job.get("seed"), case=job["case"],
                   deadline_beta=original["settings"]["deadline_beta"],
                   initial_temperature_degC=original["settings"]["initial_temperature_degC"],
                   original_temperature_limit_degC="80", enforce_80C_in_planning=enforce,
                   planning_SAFE_scope=declaration["planning_SAFE_scope"],
                   method_version=("existing_whole_milp+exact_equalities+reserve30" if job["method"] == "whole_milp"
                                   else "existing_adapted_" + job["method"]) + ";" + declaration.get("profile", "operating_temperature_limit_ablation_v1"),
                   execution_subject_commit=approval.get("subject_commit"),
                   plan_sha256=sha(plan_path), input_sha256=case["sha256"]["input_file"],
                   posterior_input_sha256=case["sha256"]["posterior_file"],
                   method_budget_s=600, delivery_reserve_s=30 if job["method"] == "whole_milp" else None,
                   execution_status=meta.get("status", "NOT_RUN" if not slot.exists() else "NO_TERMINAL_RECEIPT"),
                   method_state=worker.get("state"), error=meta.get("error") or worker.get("error"),
                   total_method_wall_s=meta.get("total_wall_s"), planning_complete_SAFE=False,
                   common_80_C_feasible=None, rankable_80C=False,
                   final_energy_is_feasible_upper_bound_80C=False,
                   exact_optimum_reference=None, independently_proven_optimal=False,
                   static_size=static_size, model_summary=None)
        if not rawpath.exists():
            row["missing_result_reason"] = "No saved raw method result; not imputed as zero or infeasible."
            rows.append(row)
            continue
        raw = load(rawpath)
        metrics = build_completion_metrics(raw, uses_matlab=job["method"] == "whole_milp", seconds=600)
        evaluation = raw.get("evaluation") or {}
        if evaluation:
            assert evaluation.get("evidence_identity") == {
                "input_sha256": canonical_sha(instance),
                "candidate_sha256": canonical_sha(raw.get("safe_candidate"))}, "Method receipt input/candidate identity"
        if worker:
            assert worker.get("plan_sha256") == sha(plan_path) and worker.get("job") == job
        physics = saved_physics(evaluation, instance)
        upper = raw.get("safe_upper_bound_J")
        accepted = metrics["complete_SAFE_receipts"]
        matching = [s["completed_at_s"] for s in accepted if upper is not None and Q(s["safe_upper_bound_J"]) == Q(upper)]
        preserved = (worker.get("safe") or {}).get("preserved") is True
        initial = metrics["initial_complete_SAFE_energy_interval_J"]
        audit = load(slot / "worker/whole_audit.json", optional=True)
        row.update(raw_sha256=sha(rawpath), method_state=raw.get("state"), reason=raw.get("reason"),
                   error=row["error"] or raw.get("error"),
                   initial_energy_interval_J=pair(initial), initial_energy_J=initial[1] if initial else None,
                   final_energy_interval_J=pair(evaluation.get("weighted_energy_J")),
                   final_energy_J=upper, first_planning_SAFE_s=metrics["first_complete_SAFE_at_s"],
                   best_planning_SAFE_s=min(matching) if matching else None,
                   method_root_s=(raw.get("timing") or {}).get("method_elapsed_s"),
                   first_safe_s=metrics["first_complete_SAFE_at_s"], best_safe_s=min(matching) if matching else None,
                   SAFE_time_scope=declaration["planning_SAFE_scope"],
                   planning_complete_SAFE=bool(preserved and matching and physics["complete"]),
                   initial_candidate=((raw.get("initialisation") or {}).get("witness") or {}).get("candidate"),
                   final_candidate=raw.get("safe_candidate"),
                   schedule_with_exact_ends={sid: {k: v for k, v in s.items() if k in ("rows", "request_completion_ms")}
                                             for sid, s in ((evaluation.get("legality") or {}).get("scenes") or {}).items()},
                   model_summary=raw.get("model_summary"), construction=raw.get("construction"),
                   timing=raw.get("timing"), completion_metrics=metrics,
                   maximum_peak_degC=physics["peak_degC"], weighted_energy_components_J=physics["components_J"],
                   physical_values_source="method_planning_evaluation" if physics["complete"] else None,
                   method_audit_status=(audit.get("execution") or {}).get("execution_status"),
                   independently_proven_optimal=raw.get("independently_proven_optimal", False))
        if row["initial_candidate"] is None:
            accepted_evals = [v for v in raw.get("evaluations", []) if v.get("accepted_safe")]
            if accepted_evals:
                row["initial_candidate"] = accepted_evals[0].get("candidate")
        postslot = folder / "slots" / (job["id"] + "__post")
        post = load(postslot / "worker/post_result.json", optional=True)
        postmeta = load(postslot / "slot_result.json", optional=True)
        postworker = load(postslot / "worker/worker_result.json", optional=True)
        row.update(post_state=post.get("state", postworker.get("state")),
                   post_execution_status=postmeta.get("status", "NOT_RUN" if not postslot.exists() else "NO_TERMINAL_RECEIPT"),
                   post_wall_s=postmeta.get("total_wall_s"), post_error=postmeta.get("error") or postworker.get("error"),
                   post_complete_physical_evaluation=False)
        if post:
            assert post["method_receipt_sha256"] == sha(rawpath)
            assert post["same_candidate"] == raw.get("safe_candidate")
            diagnostic = post.get("diagnostic") or {}
            if diagnostic:
                assert diagnostic.get("original_input_sha256") == canonical_sha(original)
                assert diagnostic.get("candidate_sha256") == canonical_sha(raw.get("safe_candidate"))
            row.update(post_diagnostic=diagnostic,
                       common_80_C_feasible=diagnostic.get("common_80_C_feasible"),
                       post_complete_physical_evaluation=diagnostic.get("complete_physical_evaluation") is True,
                       post_diagnostic_energy_interval_J=pair(diagnostic.get("diagnostic_weighted_energy_J")))
            if diagnostic.get("complete_physical_evaluation"):
                posterior_energy = pair(diagnostic["diagnostic_weighted_energy_J"])
                if row["final_energy_interval_J"]:
                    lo, hi = map(Q, row["final_energy_interval_J"])
                    plo, phi = map(Q, posterior_energy)
                    assert max(lo, plo) <= min(hi, phi), "Method/post energy conflict"
                row.update(maximum_peak_degC=pair(diagnostic["maximum_peak_degC"]),
                           weighted_energy_components_J=diagnostic["weighted_energy_components_J"],
                           physical_values_source="original_80C_posterior_same_candidate")
            row["final_energy_is_feasible_upper_bound_80C"] = bool(
                row["planning_complete_SAFE"] and row["common_80_C_feasible"] is True
                and diagnostic.get("energy_is_feasible_upper_bound") is True)
        row["method_original_80C_SAFE_without_post"] = bool(enforce and row["planning_complete_SAFE"])
        row["rankable_80C"] = bool(row["final_energy_is_feasible_upper_bound_80C"]
                                  and row["execution_status"] in NORMAL
                                  and row["post_execution_status"] == "NORMAL_COMPLETION")
        row["final_safe_energy_80C_J"] = upper if row["final_energy_is_feasible_upper_bound_80C"] else None
        bounds = load(slot / "worker/method/independent_bounds.json", optional=True)
        row["independent_lower_bound"] = bounds.get("L0", raw.get("independent_lower_bound"))
        native = []
        for path in sorted((slot / "worker/method/matlab").glob("request_*.response.json")):
            receipt = load(path)
            output = receipt.get("output") or {}
            fval, absolute_gap = receipt.get("fval"), output.get("absolutegap")
            native.append(dict(path=str(path.relative_to(folder)), sha256=sha(path),
                               status=receipt.get("status"), exitflag=receipt.get("exitflag"),
                               fval=fval, output=output, phase_seconds=receipt.get("phase_seconds"),
                               effective_MaxTime=(receipt.get("options") or {}).get("MaxTime"),
                               reported_bound_fval_minus_absolutegap_J=(number(Q(str(fval)) - Q(str(absolute_gap)))
                                   if finite_scalar(fval) and finite_scalar(absolute_gap) else None),
                               scope="Floating solver report, possibly delivered at termination; not an exact reference or a new accepted candidate"))
        row["native_diagnostics"] = native
        if row["independent_lower_bound"] and upper is not None:
            lower = row["independent_lower_bound"].get("lower_bound_J")
            if lower is not None:
                row["planning_U_minus_independent_L0_J"] = str(Q(upper) - Q(lower))
                row["planning_gap_scope"] = "Planning problem feasible upper bound versus analytic floor; no exact optimum; original-80C feasibility separately reported"
        rows.append(row)
    sa = [r for r in rows if r["method"] == "sa"]
    successful = [r for r in sa if r["rankable_80C"]]
    for case_name in plan["cases"]:
        comparable = [r for r in rows if r["case"] == case_name and r["rankable_80C"]]
        best = min((Q(r["final_energy_J"]) for r in comparable), default=None)
        for row in comparable:
            row["gap_to_same_case_best_observed_percent"] = number(100 * (Q(row["final_energy_J"]) - best) / best)
    return dict(schema="chapter3-closure-saved-results-v1", analysis_only=True,
                scope="Saved records only; 80-C posterior eligibility separate from planning SAFE; no exact reference for these natural-domain cases",
                plan_sha256=sha(plan_path), execution_subject_commit=approval.get("subject_commit"),
                batch_state=batch.get("state", "NO_BATCH_TERMINAL_RECEIPT"), batch_error=batch.get("error"),
                batch_total_wall_s=batch.get("total_wall_s"), method_calls=batch.get("method_attempts"),
                post_calls=batch.get("post_attempts"), not_run=batch.get("not_run"),
                method_status_counts=dict(Counter(r["execution_status"] for r in rows)), methods=rows,
                sa_statistics=dict(planned_seeds=[r["seed"] for r in sa],
                                   successful_seeds=[r["seed"] for r in successful],
                                   failed_or_unverified_seeds=[r["seed"] for r in sa if not r["rankable_80C"]],
                                   status_counts=dict(Counter(r["execution_status"] for r in sa)),
                                   energy_upper_J=dispersion([r["final_energy_J"] for r in successful]),
                                   method_wall_s=dispersion([str(r["total_method_wall_s"]) for r in successful if r.get("total_method_wall_s") is not None]),
                                   quartile_definition="Linear interpolation at index (n-1)*p; population SD; successful original-80C verified runs only",
                                   interpretation="Five independent single-600-s results; minimum is descriptive, not a claimed single-run or 3000-s algorithm result"),
                sources_sha256=source_hashes, new_optimization_calls=0, new_thermal_evaluations=0)


def csv_rows(summary):
    for row in summary["methods"]:
        native = (row.get("native_diagnostics") or [{}])[-1]
        output = native.get("output") or {}
        record = {key: row.get(key) for key in (
            "id", "case", "method", "method_version", "seed", "execution_subject_commit", "plan_sha256", "input_sha256",
            "deadline_beta", "initial_temperature_degC", "original_temperature_limit_degC", "enforce_80C_in_planning",
            "planning_SAFE_scope", "method_budget_s", "delivery_reserve_s", "execution_status", "method_state", "reason", "error",
            "planning_complete_SAFE", "common_80_C_feasible", "rankable_80C", "final_energy_is_feasible_upper_bound_80C",
            "first_planning_SAFE_s", "best_planning_SAFE_s", "method_root_s", "total_method_wall_s",
            "post_state", "post_execution_status", "post_wall_s", "post_complete_physical_evaluation", "post_error",
            "physical_values_source", "independently_proven_optimal", "gap_to_same_case_best_observed_percent")}
        for field in ("initial_energy_interval_J", "final_energy_interval_J", "post_diagnostic_energy_interval_J", "maximum_peak_degC"):
            values = row.get(field) or [None, None]
            record[field + "_lower"], record[field + "_upper"] = number(values[0]), number(values[1], True)
        record["final_safe_energy_80C_J"] = number(row.get("final_safe_energy_80C_J"), True)
        for key in COMPONENTS:
            values = (row.get("weighted_energy_components_J") or {}).get(key) or [None, None]
            record[key + "_J_lower"], record[key + "_J_upper"] = number(values[0]), number(values[1], True)
        record.update(native_exitflag=native.get("exitflag"), native_fval_J=native.get("fval"),
                      native_raw_relativegap=output.get("relativegap"), native_absolutegap_J=output.get("absolutegap"),
                      native_reported_bound_J=native.get("reported_bound_fval_minus_absolutegap_J"),
                      native_numnodes=output.get("numnodes"),
                      independent_L0_J=number((row.get("independent_lower_bound") or {}).get("lower_bound_J")))
        yield record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.folder, args.plan)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path, csv_path = args.out_dir / "summary.json", args.out_dir / "unified_results.csv"
    if json_path.exists() or csv_path.exists():
        raise SystemExit("Refusing to overwrite existing summary or table; use a fresh output directory")
    with json_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    records = list(csv_rows(result))
    with csv_path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    print(json.dumps({"summary": str(json_path), "table": str(csv_path), "batch_state": result["batch_state"],
                      "methods": len(records), "scientific_calls_in_analysis": 0}, ensure_ascii=False))
