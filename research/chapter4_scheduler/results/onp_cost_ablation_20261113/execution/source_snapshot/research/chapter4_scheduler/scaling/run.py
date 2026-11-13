"""Serial HEFT/ON pilot using unchanged scientific lifecycles.

prepare freezes four supplied inputs and source bytes; batch consumes exactly
eight slots, with no retry/replacement. Post-evaluation is separate and never
feeds search. No scientific calculation occurs in prepare or report.
"""
import argparse
from collections import Counter
from copy import deepcopy
import csv
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import traceback
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO), str(REPO / "research/chapter3_experiments")]
PROTOCOL = "chapter4-unseen-size-pilot-v1"
THREADS = {n: "1" for n in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")}
METHOD_S, POST_S = 300, 60
METHOD_WATCHDOG_S, POST_WATCHDOG_S = 360, 90


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def child(folder, relative):
    path = (Path(folder) / relative).resolve()
    if not path.is_relative_to(Path(folder).resolve()):
        raise ValueError("PATH_OUTSIDE_INPUT_ROOT")
    return path


def environment():
    return {"python": sys.version, "executable": sys.executable,
        "platform": platform.platform(), "cpu_count": os.cpu_count(),
        "packages": {n: importlib.metadata.version(n) for n in ("numpy", "scipy")}}


def slots(cases):
    ordered = sorted(cases, key=lambda c: (c["root_id"], c["stages_per_scene"]))
    if len(ordered) != 4 or len({c["case_id"] for c in ordered}) != 4:
        raise ValueError("FOUR_DISTINCT_CASES_REQUIRED")
    roots = sorted({c["root_id"] for c in ordered})
    if len(roots) != 2 or any(sorted(c["stages_per_scene"] for c in ordered if c["root_id"] == r) != [6, 12] for r in roots):
        raise ValueError("TWO_ROOTS_EACH_6_AND_12_REQUIRED")
    result = []
    for index, case in enumerate(ordered):
        for arm in (("HEFT", "ON") if index in (0, 3) else ("ON", "HEFT")):
            result.append({"id": f"{len(result)+1:02d}_{case['case_id']}_{arm}",
                "case_id": case["case_id"], "root_id": case["root_id"],
                "stages_per_scene": case["stages_per_scene"], "arm": arm})
    return result


def prepare(inputs, out):
    inputs, out = Path(inputs).resolve(), Path(out).resolve()
    if out.exists():
        raise FileExistsError(out)
    manifest = read(inputs / "inputs_manifest.json")
    if sha(inputs / "input_plan.json") != manifest["plan_sha256"]:
        raise ValueError("INPUT_GENERATION_PLAN_DRIFT")
    cases = manifest["cases"]
    run_slots = slots(cases)
    common_platform = common_accuracy = None
    identities = {}
    for case in cases:
        for key in ("config", "instance", "generation_evidence"):
            if key + "_path" in case and sha(child(inputs, case[key + "_path"])) != case[key + "_sha256"]:
                raise ValueError("GENERATED_INPUT_MANIFEST_DRIFT:" + case["case_id"] + ":" + key)
        config = read(child(inputs, case["config_path"]))
        instance = read(child(inputs, case["instance_path"]))
        scenes = instance["scenarios"]
        if len(scenes) != 2 or any(len(s["stage_instances"]) != case["stages_per_scene"] for s in scenes):
            raise ValueError("CASE_STAGE_OR_SCENE_COUNT_MISMATCH")
        if any(any(F(t) != 50 for t in s["entry"]["temperature_degC"]) for s in scenes):
            raise ValueError("ENTRY_TEMPERATURE_MUST_BE_50C")
        if common_platform is None:
            common_platform, common_accuracy = digest(instance["platform"]), digest(config["accuracy_targets"])
        if (digest(instance["platform"]), digest(config["accuracy_targets"])) != (common_platform, common_accuracy):
            raise ValueError("PLATFORM_OR_ACCURACY_CHANGED_ACROSS_CASES")
        identities[case["case_id"]] = {"config_sha256": digest(config), "instance_sha256": digest(instance)}
    out.mkdir(parents=True)
    frozen = out / "frozen_inputs"
    frozen.mkdir()
    shutil.copyfile(inputs / "inputs_manifest.json", frozen / "inputs_manifest.json")
    shutil.copyfile(inputs / "input_plan.json", frozen / "input_plan.json")
    input_files = {"frozen_inputs/inputs_manifest.json": sha(frozen / "inputs_manifest.json")}
    input_files["frozen_inputs/input_plan.json"] = sha(frozen / "input_plan.json")
    for case in cases:
        for key in ("config_path", "instance_path", "generation_evidence_path"):
            if key not in case:
                continue
            source, target = child(inputs, case[key]), child(frozen, case[key])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            input_files[target.relative_to(out).as_posix()] = sha(target)
    # Only materialized scientific source, never historical result archives.
    paths = []
    for directory, subdirs, filenames in os.walk(REPO / "research"):
        subdirs[:] = [s for s in subdirs if s not in ("results", "__pycache__", ".runtime", "source_snapshot", "source_snapshots", "frozen_sources")]
        paths.extend(Path(directory) / n for n in filenames if n.endswith(".py"))
    sources = {p.relative_to(REPO).as_posix(): sha(p) for p in sorted(paths)}
    for path in paths:
        target = out / "source_snapshot" / path.relative_to(REPO)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    plan = {"protocol": PROTOCOL, "created_utc": now(),
        "authorization": "Current user request: two previously unused roots, 6/12 stages per scene, two scenes, 50 C, unchanged HEFT/ON, one 300 s run each; no SA or algorithm changes.",
        "subject_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "source_branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=REPO, text=True).strip(),
        "environment": environment(), "thread_environment": THREADS,
        "budgets": {"method_s": METHOD_S, "post_s": POST_S, "method_slots": 8,
            "post_slots_at_most": 8, "method_process_watchdog_s": METHOD_WATCHDOG_S,
            "post_process_watchdog_s": POST_WATCHDOG_S},
        "slots": run_slots, "cases": cases, "input_identities": identities,
        "source_sha256": sources, "input_file_sha256": input_files,
        "clock": "One root starts before scientific imports, source/input checks and initialization. Interpreter and standard-library startup excluded uniformly; full process wall and archival overhead reported separately.",
        "initialization": "Each arm runs its own unchanged complete enhanced HEFT. No initial candidate, cache or result is shared between calls.",
        "evaluation": "Original continuous full-window thermal evaluator through the existing forwarding journal; original complete-SAFE recorder and strict ON energy-interval acceptance.",
        "post": "One independent process/root at most 60 s per normal SAFE run, same numerical implementation; full SAFE and energy-interval overlap required, no feedback to search.",
        "stops": "No retries/replacements. Preserve no-improvement/no-SAFE/budget outcomes and continue. Technical, numerical, input/source-integrity or post failure stops later slots, recorded explicitly as NOT_RUN.",
        "scope": "Descriptive 2-root size pilot; no statistical superiority, optimality, hardware calibration or independent-numerics claim."}
    save(out / "plan.json", plan)
    save(out / "plan_identity.json", {"sha256": sha(out / "plan.json")})
    verify(out, plan)
    print(json.dumps({"prepared": str(out), "slots": len(run_slots), "source_files": len(sources), "plan_sha256": sha(out / "plan.json")}))
    return plan


def verify(out, plan):
    out = Path(out)
    if plan.get("protocol") != PROTOCOL or plan["slots"] != slots(plan["cases"]):
        raise ValueError("PLAN_SCOPE_DRIFT")
    if plan["budgets"] != {"method_s": METHOD_S, "post_s": POST_S, "method_slots": 8,
            "post_slots_at_most": 8, "method_process_watchdog_s": METHOD_WATCHDOG_S,
            "post_process_watchdog_s": POST_WATCHDOG_S}:
        raise ValueError("BUDGET_DRIFT")
    if sha(out / "plan.json") != read(out / "plan_identity.json")["sha256"]:
        raise ValueError("PLAN_HASH_DRIFT")
    if environment() != plan["environment"]:
        raise ValueError("ENVIRONMENT_DRIFT")
    if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip() != plan["subject_commit"]:
        raise ValueError("SUBJECT_COMMIT_DRIFT")
    for relative, expected in plan["source_sha256"].items():
        if sha(REPO / relative) != expected:
            raise ValueError("SOURCE_DRIFT:" + relative)
    for relative, expected in plan["input_file_sha256"].items():
        if sha(child(out, relative)) != expected:
            raise ValueError("INPUT_DRIFT:" + relative)


def dispatch(arm, loader, folder, budget, bindings):
    """Forward the unchanged caller root; deliberately no SA route."""
    if arm == "HEFT":
        from research.chapter4_scheduler.validation.lifecycle import execute_heft
        return execute_heft(loader, folder, bindings=bindings, budget=budget)
    if arm == "ON":
        from research.chapter4_scheduler.blocking.method import execute_reconstruction
        return execute_reconstruction(loader, folder, bindings=bindings, budget=budget,
            seconds=budget.seconds, allow_blocking_edges=True)
    raise ValueError("ONLY_HEFT_AND_ON_ARE_AUTHORIZED")


def derived_metrics(raw, arm):
    """Read-only cost accounting; inclusive phase durations are not summed twice."""
    records = raw.get("timing", {}).get("phase_records", [])
    init = [p for p in records if p["phase"] == "heft_initialization"]
    freeze = [p for p in records if p["phase"] == "complete_initial_safe_freeze"]
    initialized = raw.get("initial_safe_snapshot") is not None
    end = max((p["end_s"] for p in freeze), default=None) if initialized else None
    rows = [r for r in raw.get("evaluations", []) if not r.get("cache_hit", False)]
    proposals, attempts = raw.get("graph_proposals", []), raw.get("reconstruction_attempts", [])
    receipt = raw.get("evaluation") or {}
    peaks = [F(v[1]) for scene in receipt.get("scenes", {}).values() for v in scene.get("peaks_degC", {}).values()]
    complete = [r for r in rows if len(r["receipt"].get("scenes", {})) == 2
        and all(s.get("complete") is True for s in r["receipt"]["scenes"].values())]
    complete_safe = [r for r in complete if r.get("accepted_safe")]
    counts = Counter(r.get("phase", "unknown") for r in complete_safe)
    elapsed = raw.get("timing", {}).get("method_elapsed_s")
    return {"initialization_complete": initialized,
        "initialization_s": sum(p["wall_s"] for p in init),
        "initial_safe_freeze_s": sum(p["wall_s"] for p in freeze),
        "initialization_completed_at_s": end,
        "search_s": max(0.0, elapsed-end) if arm == "ON" and end is not None else 0.0,
        "full_electrothermal_completed_evaluations": len(complete),
        "full_electrothermal_SAFE_evaluations": len(complete_safe),
        "full_electrothermal_thermal_violation_evaluations": sum(r["receipt"].get("state") == "THERMAL_VIOLATION" for r in complete),
        "initialization_full_SAFE_evaluations": counts["initialization"],
        "search_full_SAFE_evaluations": counts["refinement"],
        "electrothermal_evaluation_s": sum(p["wall_s"] for p in records if p["phase"] == "complete_continuous_evaluation"),
        "graph_construction_s": sum(p["exclusive_s"] for p in records if p["phase"] == "blocking_graph_construct"),
        "graph_reconstruction_attempts": len(attempts), "graph_proposals": len(proposals),
        "graph_strict_improvements": raw.get("graph_strict_improvements", 0),
        "graph_attempt_states": dict(Counter(a.get("state", "unknown") for a in attempts)),
        "graph_attempt_reasons": dict(Counter(a.get("reason") for a in attempts if a.get("reason"))),
        "peak_temperature_upper_C": float(max(peaks)) if peaks else None,
        "initialization_metadata": deepcopy(raw.get("initialization"))}


def assert_root(budget, root):
    if (budget.start, budget.deadline, budget.seconds, budget.clock) != root:
        raise ValueError("ROOT_BUDGET_CHANGED")


def worker(out, slot_id, post=False):
    entered = time.monotonic()
    out = Path(out).resolve()
    phase = "post" if post else "method"
    folder = out / "calls" / slot_id
    result = {"slot_id": slot_id, "phase": phase, "started_utc": now(),
        "error": None, "normal_stop": False, "has_SAFE_archive": False}
    budget = journal = None
    try:
        from timing import MethodBudget
        budget = MethodBudget(POST_S if post else METHOD_S)
        budget.start, budget.deadline = entered, entered + budget.seconds
        root = (budget.start, budget.deadline, budget.seconds, budget.clock)
        with budget.phase("frozen_identity_and_scientific_imports"):
            plan = read(out / "plan.json")
            verify(out, plan)
            slot = next(s for s in plan["slots"] if s["id"] == slot_id)
            claim = read(folder / (phase + "_claim.json"))
            if claim["slot"] != slot or claim["plan_sha256"] != sha(out / "plan.json"):
                raise ValueError("CLAIM_MISMATCH")
            if any(os.environ.get(k) != v for k, v in THREADS.items()):
                raise ValueError("THREAD_ENVIRONMENT_DRIFT")
            import thermal
            from heft_method import run_heft
            from research.chapter4_scheduler.blocking.method import Bindings
            from research.chapter4_scheduler.comparison.core import EvaluationJournal, normalize
            from h02_pair_preflight.receipts import safe_receipt
        with (folder / (phase + "_evaluation_journal.jsonl")).open("x", encoding="utf-8") as stream:
            journal = EvaluationJournal(thermal.evaluate_candidate, budget, stream)
            if post:
                with budget.phase("read_own_final_evidence"):
                    raw = read(folder / "method/result.json")
                    config = read(folder / "method/input_config.json")
                    instance = read(folder / "method/input_instance.json")
                    candidate = raw["safe_candidate"]
                    if {"config_sha256": digest(config), "instance_sha256": digest(instance)} != plan["input_identities"][slot["case_id"]]:
                        raise ValueError("ARCHIVED_INPUT_DRIFT")
                    before = tuple(map(digest, (instance, candidate, config)))
                with budget.phase("complete_post_evaluation"):
                    receipt = journal(instance, candidate, config["accuracy_targets"], budget)
                save(folder / "post_receipt.json", receipt)
                energy = safe_receipt(instance, candidate, receipt, config["accuracy_targets"], POST_S)
                if tuple(map(digest, (instance, candidate, config))) != before:
                    raise ValueError("POST_ARGUMENT_MUTATION")
                lo, hi = map(F, raw["evaluation"]["weighted_energy_J"])
                if max(lo, F(energy["lower"])) > min(hi, F(energy["upper"])):
                    raise ValueError("POST_INTERVAL_DISJOINT")
                result.update(normal_stop=True, passed=True, has_SAFE_archive=True,
                    energy=energy, timing=budget.summary(), same_numerical_evaluator=True)
            else:
                case = next(c for c in plan["cases"] if c["case_id"] == slot["case_id"])
                loads = []
                def loader(active):
                    if active is not budget or loads:
                        raise ValueError("ONE_INPUT_LOAD_ON_ORIGINAL_ROOT_REQUIRED")
                    loads.append(True)
                    with budget.phase("load_frozen_common_input"):
                        config = read(child(out / "frozen_inputs", case["config_path"]))
                        instance = read(child(out / "frozen_inputs", case["instance_path"]))
                        if {"config_sha256": digest(config), "instance_sha256": digest(instance)} != plan["input_identities"][slot["case_id"]]:
                            raise ValueError("FROZEN_INPUT_IDENTITY_MISMATCH")
                    return config, instance
                with patch.object(thermal, "evaluate_candidate", journal):
                    raw = dispatch(slot["arm"], loader, folder / "method", budget,
                        Bindings(run_heft, journal, "REAL_CORE"))
                result.update(normalize(raw, journal), metrics=derived_metrics(raw, slot["arm"]),
                    slot=slot, fresh_input_calls=len(loads), raw_result_sha256=sha(folder / "method/result.json"))
                result["failure_reason"] = None if result["normal_stop"] and result["has_SAFE_archive"] else raw.get("reason")
            assert_root(budget, root)
        # Verification after method stop is archival work, never extra search.
        verify(out, plan)
    except BaseException as error:
        result.update(normal_stop=False, error={"type": type(error).__name__,
            "reason": str(error), "traceback": traceback.format_exc()})
        if budget is not None:
            result["failure_timing"] = budget.summary()
    result.update(ended_utc=now(), worker_body_wall_s=time.monotonic()-entered,
        evaluation_attempts_journal=deepcopy(journal.attempts) if journal else [])
    save(folder / (phase + "_return.json"), result)
    print(json.dumps({k: result.get(k) for k in ("slot_id", "phase", "normal_stop", "has_SAFE_archive", "terminal", "error", "worker_body_wall_s")}, ensure_ascii=False), flush=True)
    return 0 if result["normal_stop"] and not result["error"] else 1


def batch(out):
    out = Path(out).resolve()
    plan = read(out / "plan.json")
    verify(out, plan)
    save(out / "batch_started.json", {"utc": now(), "plan_sha256": sha(out / "plan.json")})
    began = time.monotonic()
    env = dict(os.environ, **THREADS, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    rows, stop = [], None
    for slot in plan["slots"]:
        if stop:
            rows.append({"slot": slot, "status": "NOT_RUN_TECHNICAL_STOP", "reason": stop})
            continue
        folder = out / "calls" / slot["id"]
        folder.mkdir(parents=True, exist_ok=False)
        row = {"slot": slot, "status": "STARTED", "phases": []}
        rows.append(row)
        for phase, timeout in (("method", METHOD_WATCHDOG_S), ("post", POST_WATCHDOG_S)):
            if phase == "post":
                method = read(folder / "method_return.json")
                if not method.get("normal_stop") or not method.get("has_SAFE_archive"):
                    break
            try:
                verify(out, plan)
                save(folder / (phase + "_claim.json"), {"utc": now(), "slot": slot,
                    "plan_sha256": sha(out / "plan.json"), "no_retry": True})
            except Exception as error:
                stop = slot["id"] + ":" + phase + ":PREFLIGHT:" + str(error)
                row.update(status="STOPPED_TECHNICAL", reason=stop)
                save(folder / (phase + "_preflight_failure.json"), {"utc": now(),
                    "error_type": type(error).__name__, "reason": str(error),
                    "scientific_call_started": False})
                break
            command = [sys.executable, "-B", "-m", "research.chapter4_scheduler.scaling.run",
                "worker", "--out", str(out), "--slot", slot["id"]] + (["--post"] if phase == "post" else [])
            record = {"argv": command, "cwd": str(REPO), "started_utc": now(),
                "thread_environment": THREADS, "watchdog_s": timeout, "phase": phase}
            save(folder / (phase + "_command_started.json"), record)
            print(json.dumps({"event": "START", "slot": slot, "phase": phase, "utc": now()}), flush=True)
            started = time.monotonic()
            try:
                completed = subprocess.run(command, cwd=REPO, env=env,
                    capture_output=True, text=True, encoding="utf-8", timeout=timeout)
                (folder / (phase + "_stdout.log")).write_text(completed.stdout, encoding="utf-8")
                (folder / (phase + "_stderr.log")).write_text(completed.stderr, encoding="utf-8")
                record.update(exit_code=completed.returncode, wall_s=time.monotonic()-started,
                    ended_utc=now(), watchdog_expired=False)
                returned = read(folder / (phase + "_return.json"))
                if completed.returncode or returned.get("error") or not returned.get("normal_stop"):
                    stop = slot["id"] + ":" + phase + ":ABNORMAL_RETURN"
                record["normal_stop"] = returned.get("normal_stop", False)
                print(json.dumps({"event": "DONE", "slot": slot["id"], "phase": phase,
                    "terminal": returned.get("terminal"), "safe": returned.get("has_SAFE_archive"),
                    "counts": returned.get("counts"), "error": returned.get("error")}), flush=True)
            except BaseException as error:
                record.update(exit_code=None, wall_s=time.monotonic()-started, ended_utc=now(),
                    watchdog_expired=isinstance(error, subprocess.TimeoutExpired),
                    error={"type": type(error).__name__, "reason": str(error)})
                if isinstance(error, subprocess.TimeoutExpired):
                    for label, value in (("stdout", error.stdout), ("stderr", error.stderr)):
                        (folder / (phase + "_partial_" + label + ".log")).write_bytes(value.encode("utf-8") if isinstance(value, str) else value or b"")
                stop = slot["id"] + ":" + phase + ":" + type(error).__name__
            save(folder / (phase + "_command_return.json"), record)
            row["phases"].append(record)
            if stop:
                row["status"] = "STOPPED_TECHNICAL"
                row["reason"] = stop
                break
        if not stop:
            row["status"] = "COMPLETED"
    try:
        verify(out, plan)
        identity_ok = True
    except Exception as error:
        identity_ok = False
        stop = stop or str(error)
    final = {"protocol": PROTOCOL, "ended_utc": now(), "wall_s": time.monotonic()-began,
        "slots": rows, "stop_reason": stop, "frozen_identity_unchanged": identity_ok,
        "all_planned_method_slots_returned": all(r["status"] == "COMPLETED" for r in rows),
        "retry_count": 0, "replacement_count": 0}
    save(out / "batch_return.json", final)
    report(out)
    return 1 if stop else 0


def report(out):
    out = Path(out).resolve()
    plan = read(out / "plan.json")
    rows = []
    for slot in plan["slots"]:
        folder = out / "calls" / slot["id"]
        method = read(folder / "method_return.json") if (folder / "method_return.json").exists() else {}
        post = read(folder / "post_return.json") if (folder / "post_return.json").exists() else {}
        command = read(folder / "method_command_return.json") if (folder / "method_command_return.json").exists() else {}
        metrics, counts = method.get("metrics", {}), method.get("counts", {})
        energy = method.get("energy_interval_J")
        row = {**slot, "terminal": method.get("terminal", "NOT_RETURNED"),
            "reason": method.get("raw_reason"), "failure_reason": method.get("failure_reason"),
            "error": (method.get("error") or {}).get("reason"),
            "safe": method.get("has_SAFE_archive", False), "post_passed": post.get("passed", False),
            "energy_lower_J": str(F(energy[0])) if energy else None,
            "energy_upper_J": str(F(energy[1])) if energy else None,
            "energy_upper_J_decimal": float(F(energy[1])) if energy else None,
            "method_elapsed_s": method.get("timing", {}).get("method_elapsed_s"),
            "process_wall_s": command.get("wall_s"), "worker_body_wall_s": method.get("worker_body_wall_s"),
            "deadline_overshoot_s": method.get("timing", {}).get("deadline_overshoot_s"),
            **{k: v for k, v in metrics.items() if not isinstance(v, (dict, list))}, **counts,
            "post_wall_s": post.get("worker_body_wall_s")}
        if not method:
            row["error"] = (command.get("error") or {}).get("reason", "No method return; see batch_return.json")
        rows.append(row)
    summary = {"protocol": PROTOCOL, "subject_commit": plan["subject_commit"],
        "planned_runs": len(rows), "SAFE_and_post_passed": sum(r["safe"] and r["post_passed"] for r in rows),
        "all_results_retained": True, "rows": rows, "comparisons": []}
    for case in plan["cases"]:
        pair = {r["arm"]: r for r in rows if r["case_id"] == case["case_id"]}
        h, o = pair["HEFT"], pair["ON"]
        valid = all(r["safe"] and r["post_passed"] and not r["error"] for r in (h, o))
        summary["comparisons"].append({"case_id": case["case_id"], "comparable_SAFE_pair": valid,
            "ON_vs_HEFT_saving_percent": float((F(h["energy_upper_J"])-F(o["energy_upper_J"]))/F(h["energy_upper_J"])*100) if valid else None,
            "strict_interval_improvement": F(o["energy_upper_J"]) < F(h["energy_lower_J"]) if valid else None})
    save(out / "summary.json", summary)
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with (out / "metrics.csv").open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "batch", "worker", "report"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--slot")
    parser.add_argument("--post", action="store_true")
    args = parser.parse_args()
    if args.action == "prepare":
        if args.inputs is None:
            parser.error("prepare requires --inputs")
        prepare(args.inputs, args.out)
        return 0
    if args.action == "batch":
        return batch(args.out)
    if args.action == "worker":
        if not args.slot:
            parser.error("worker requires --slot")
        return worker(args.out, args.slot, args.post)
    report(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
