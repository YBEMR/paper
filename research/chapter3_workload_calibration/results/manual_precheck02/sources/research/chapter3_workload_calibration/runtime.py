"""Auditable single-pass time calibration, with per-condition and batch clocks."""

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

from research.chapter3_deadline_reference.run_checks import ScopeGuard
from research.chapter3_deadline_reference.contract import content_hash
from .configuration import approved_configuration, planned_calls, validate_manifest

PACKAGE = Path(__file__).resolve().parent
REPO = PACKAGE.parent.parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_gzip(path, value):
    # Reproducible gzip metadata; elapsed times remain explicitly variable evidence.
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    Path(path).write_bytes(gzip.compress(payload, mtime=0))


def read_gzip(path):
    return json.loads(gzip.decompress(Path(path).read_bytes()))


def source_files():
    files = sorted(PACKAGE.glob("*.py")) + sorted((PACKAGE.parent / "chapter3_deadline_reference").glob("*.py"))
    files += [PACKAGE.parent / "chapter3_experiments/config_v01.json"]
    return {p.relative_to(REPO).as_posix(): sha(p) for p in files}


def protected_files():
    old = PACKAGE.parent / "chapter3_experiments"
    files = sorted(old.glob("*.py")) + sorted(old.glob("*.m")) + [old / "config_v01.json"]
    return {p.relative_to(REPO).as_posix(): sha(p) for p in files}


def fresh_output(path):
    path = Path(path).resolve()
    root = (PACKAGE / "results").resolve()
    if path == root or not path.is_relative_to(root) or path.exists():
        raise ValueError("NEW_PACKAGE_RESULTS_CHILD_REQUIRED")
    path.mkdir(parents=True)
    return path


def snapshot(directory):
    sources = source_files()
    for rel in sources:
        target = directory / "sources" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / rel, target)
    write_json(directory / "source_manifest.json", sources)
    return sources


def check_frozen(freeze):
    manifest = read_json(freeze / "manifest.json")
    validate_manifest(manifest)
    receipt = read_json(freeze / "freeze.json")
    if receipt["manifest_sha256"] != sha(freeze / "manifest.json"):
        raise ValueError("FROZEN_MANIFEST_DRIFT")
    if source_files() != read_json(freeze / "source_manifest.json"):
        raise ValueError("FROZEN_SOURCE_DRIFT")
    if protected_files() != receipt["protected_sources"]:
        raise ValueError("PROTECTED_SOURCE_DRIFT")
    return manifest


def freeze_run(output, checks_path):
    checks = read_json(checks_path)
    if checks["state"] != "PASS" or checks["source_files"] != source_files():
        raise ValueError("CURRENT_SOURCE_PRECHECK_REQUIRED")
    out = fresh_output(output)
    manifest = planned_calls(approved_configuration())
    validate_manifest(manifest)
    write_json(out / "manifest.json", manifest)
    snapshot(out)
    write_json(out / "freeze.json", {
        "state": "FROZEN_NOT_STARTED", "created_utc": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256": sha(out / "manifest.json"), "precheck_path": str(Path(checks_path).resolve()),
        "precheck_sha256": sha(checks_path), "protected_sources": protected_files(),
        "stop_rule": "first_error_or_timeout_no_retries",
        "no_other_algorithms_or_heat": True})
    print(json.dumps({"state": "FROZEN_NOT_STARTED", "conditions": len(manifest["calls"]), "directory": str(out)}))


def worker(freeze, execution, call_index, deadline, started):
    guard = ScopeGuard()
    sys.meta_path.insert(0, guard)
    sys.addaudithook(guard.audit)
    call_dir = None
    counters = {"mapping_constructions": 0, "timetable_constructions": 0, "S1_projections": 0,
                "formal_method_calls": 0, "thermal_integrations": 0}
    try:
        manifest = check_frozen(freeze)
        call = manifest["calls"][call_index]
        config = manifest["configuration"]
        call_dir = execution / call["condition_id"]
        call_dir.mkdir(exist_ok=False)

        def progress(phase, current):
            counters.update(current)
            if time.perf_counter() >= deadline:
                raise TimeoutError("CONDITION_TIME_LIMIT")
            write_json(call_dir / "progress.json", {"phase": phase, "counters": dict(counters),
                       "elapsed_s": time.perf_counter() - started, "condition": call})

        progress("STARTED", counters)
        from .profiles import load_catalog
        from .generator import build_base, transform
        from .evaluation import evaluate_condition
        parent = None
        if call["parent_condition_id"]:
            parent_dir = execution / call["parent_condition_id"]
            if read_json(parent_dir / "result.json")["state"] != "COMPLETE":
                raise ValueError("PARENT_NOT_COMPLETE")
            parent = read_gzip(parent_dir / "evidence.json.gz")
        catalog = load_catalog(PACKAGE.parent / "chapter3_experiments/config_v01.json")
        if call["kind"] == "base":
            workload = build_base(catalog, root_id=call["root_id"], namespace=config["namespace"], seed=call["seed"],
                                  scene_pool=call["scene_pool"], compatibility_pool=call["compatibility_pool"],
                                  scale=call["scale"], settings=config["settings"],
                                  parent=None if parent is None else parent["workload"])
        else:
            workload = transform(parent["workload"], call["kind"], value=call["value"], settings=config["settings"])
        write_gzip(call_dir / "generated_workload.json.gz", workload)
        progress("GENERATION_COMPLETE", counters)
        evidence = evaluate_condition(workload, config, parent=parent, progress=progress)
        evidence["call"] = call
        write_gzip(call_dir / "evidence.json.gz", evidence)
        progress("EVIDENCE_SAVED", counters)
        write_json(call_dir / "result.json", {"state": "COMPLETE", "condition": call,
                   "elapsed_s": time.perf_counter() - started, "counters": counters,
                   "evidence_sha256": sha(call_dir / "evidence.json.gz"),
                   "workload_sha256": sha(call_dir / "generated_workload.json.gz"),
                   "denied_imports": guard.denied_imports, "denied_events": guard.denied_events,
                   "beta_selected": None, "thermal_status": "NOT_EVALUATED", "energy_status": "NOT_EVALUATED"})
        return 0
    except Exception as error:
        detail = {"state": "TIMEOUT" if isinstance(error, TimeoutError) else "FAILED",
                  "elapsed_s": time.perf_counter() - started, "counters": counters,
                  "error": str(error), "error_type": type(error).__name__,
                  "details": getattr(error, "details", None), "traceback": traceback.format_exc(),
                  "denied_imports": guard.denied_imports, "denied_events": guard.denied_events}
        if call_dir is not None:
            write_json(call_dir / "result.json", detail)
        print(json.dumps(detail, ensure_ascii=False))
        return 2


def decide_call_state(returncode, receipt, elapsed, limit):
    if elapsed > limit or (receipt is not None and receipt.get("elapsed_s", float("inf")) > limit):
        return "TIMEOUT_OR_LATE"
    if returncode != 0 or receipt is None or receipt.get("state") != "COMPLETE":
        return "FAILED"
    if receipt.get("denied_imports") or receipt.get("denied_events"):
        return "SCOPE_FAILURE"
    return "COMPLETE"


def execute(freeze, output):
    freeze = Path(freeze).resolve()
    manifest = check_frozen(freeze)
    out = fresh_output(output)
    # Exclusive one-shot claim also protects against a second output path.
    with (freeze / "execution_claim.json").open("x", encoding="utf-8") as stream:
        json.dump({"output": str(out), "started_utc": datetime.now(timezone.utc).isoformat()}, stream)
    shutil.copyfile(freeze / "manifest.json", out / "manifest.json")
    before = protected_files()
    batch_start = time.perf_counter()
    limits = manifest["configuration"]["limits"]
    rows = []
    total = {"mapping_constructions": 0, "timetable_constructions": 0, "S1_projections": 0,
             "formal_method_calls": 0, "thermal_integrations": 0}
    state = "RUNNING"
    for index, call in enumerate(manifest["calls"]):
        remaining = limits["batch_seconds"] - (time.perf_counter() - batch_start)
        if remaining <= 0:
            state = "STOPPED_BATCH_TIMEOUT"
            break
        try:
            check_frozen(freeze)
        except Exception as error:
            state = "STOPPED_SOURCE_DRIFT"
            write_json(out / "source_drift.json", {"error": str(error)})
            break
        started = time.perf_counter()
        limit = min(limits["condition_seconds"], remaining)
        deadline = started + limit
        claim = {"index": index, "condition_id": call["condition_id"], "state": "CLAIMED",
                 "started_utc": datetime.now(timezone.utc).isoformat(), "limit_seconds": limit}
        with (out / "ledger.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(claim) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        args = [sys.executable, "-B", "-m", "research.chapter3_workload_calibration.runtime", "worker",
                "--freeze", str(freeze), "--output", str(out), "--index", str(index),
                "--deadline", repr(deadline), "--started", repr(started)]
        proc = None
        with (out / (call["condition_id"] + ".log")).open("w", encoding="utf-8") as log:
            try:
                proc = subprocess.Popen(args, cwd=REPO, stdout=log, stderr=subprocess.STDOUT)
                code = proc.wait(timeout=max(0.001, deadline - time.perf_counter()))
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
                code = -1
            except Exception as error:
                if proc is not None and proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=10)
                log.write(traceback.format_exc())
                code = -2
        elapsed = time.perf_counter() - started
        result_path = out / call["condition_id"] / "result.json"
        receipt = read_json(result_path) if result_path.exists() else None
        accepted = decide_call_state(code, receipt, elapsed, limit)
        if receipt:
            current = receipt.get("counters", {})
        else:
            progress_path = out / call["condition_id"] / "progress.json"
            current = read_json(progress_path).get("counters", {}) if progress_path.exists() else {}
        for name in total:
            total[name] += current.get(name, 0)
        row = {**claim, "state": accepted, "elapsed_s": elapsed, "returncode": code,
               "result_sha256": sha(result_path) if result_path.exists() else None, "counters": current}
        rows.append(row)
        with (out / "ledger.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row) + "\n")
        write_json(out / "status.json", {"state": "RUNNING" if accepted == "COMPLETE" else accepted,
                   "completed_conditions": sum(r["state"] == "COMPLETE" for r in rows),
                   "consumed_conditions": len(rows), "counters": total,
                   "elapsed_s": time.perf_counter() - batch_start, "last": row})
        print(json.dumps({"condition": call["condition_id"], "state": accepted,
                          "elapsed_s": round(elapsed, 3), "completed": sum(r["state"] == "COMPLETE" for r in rows)}), flush=True)
        if accepted != "COMPLETE":
            state = "STOPPED_" + accepted
            break
    if len(rows) == len(manifest["calls"]) and all(r["state"] == "COMPLETE" for r in rows):
        state = "COMPLETE"
    after = protected_files()
    if before != after:
        state = "STOPPED_PROTECTED_SOURCE_DRIFT"
    result = {"state": state, "rows": rows, "counters": total,
              "planned_conditions": len(manifest["calls"]), "consumed_conditions": len(rows),
              "completed_conditions": sum(r["state"] == "COMPLETE" for r in rows),
              "elapsed_s": time.perf_counter() - batch_start, "limits": limits,
              "protected_sources_before": before, "protected_sources_after": after,
              "protected_sources_unchanged": before == after, "formal_budget_consumed": False,
              "beta_selected": None, "thermal_status": "NOT_EVALUATED", "energy_status": "NOT_EVALUATED"}
    write_json(out / "batch_result.json", result)
    print(json.dumps({k: result[k] for k in ("state", "consumed_conditions", "completed_conditions", "elapsed_s", "counters")}), flush=True)
    return 0 if state == "COMPLETE" else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("freeze", "execute", "worker"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--checks")
    parser.add_argument("--freeze")
    parser.add_argument("--index", type=int)
    parser.add_argument("--deadline", type=float)
    parser.add_argument("--started", type=float)
    args = parser.parse_args()
    if args.operation == "freeze":
        freeze_run(args.output, args.checks)
        return 0
    if args.operation == "execute":
        return execute(args.freeze, args.output)
    return worker(Path(args.freeze).resolve(), Path(args.output).resolve(), args.index, args.deadline, args.started)


if __name__ == "__main__":
    raise SystemExit(main())
