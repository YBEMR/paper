"""Fresh four-slot experiment, no historical candidates, no native solvers.

prepare freezes sources and identities after guarded prechecks. run consumes
each slot once in a new process; method and post have separate root clocks.
Any uncertain/technical outcome stops the batch, with no retries or refunds.
"""
import argparse
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

REPO = Path(__file__).resolve().parents[3]
SCIENCE = REPO / "research/chapter3_experiments"
for directory in (REPO, SCIENCE):
    sys.path.insert(0, str(directory))
ORDER = (("base__R1", False), ("base__R1", True),
         ("base__R3", True), ("base__R3", False))
ENVIRONMENT_ID = "ccarenv_b64_Y2NhcmVudl9hMjAyYzEwMWY2ZjA4MTkxOTM5NzM4ZWI5NGMwMWQzNQ"


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def environment():
    return {"environment_id": ENVIRONMENT_ID, "python": sys.version,
        "executable": sys.executable, "platform": platform.platform(),
        "cpu_count": os.cpu_count(), "matlab": shutil.which("matlab"),
        "octave": shutil.which("octave"),
        "packages": {n: importlib.metadata.version(n) for n in ("numpy", "scipy")}}


def semantic(candidate):
    return digest({sid: sorted((r["stage_id"], r["unit"], r["opp"], str(F(r["start_ms"])))
        for r in rows) for sid, rows in candidate["scenes"].items()})


def verify(plan):
    mismatches = [p for p, expected in plan["source_sha256"].items() if sha(REPO / p) != expected]
    if mismatches:
        raise ValueError("Frozen source/archive drift: " + repr(mismatches))
    if environment() != plan["environment"]:
        raise ValueError("Frozen environment drift")


def prepare(out, checks):
    out.mkdir(parents=True, exist_ok=True)
    checked = read(checks)
    if checked.get("passed") is not True or checked.get("forbidden_calls"):
        raise ValueError("Passing guarded prechecks required")
    prior = read(REPO / "research/chapter4_scheduler/results/resume_execution01/declaration.json")
    paths = {REPO / p for key in ("source_sha256", "frozen_dependency_sha256", "protected_archive_sha256")
             for p in prior[key]}
    # Include new code and all existing scientific Python/config inputs, while
    # pruning archived result trees. No old claim/declaration is modified.
    for root in (SCIENCE, REPO / "research/chapter4_scheduler", REPO / "research/v1_evaluator"):
        for directory, subdirs, files in os.walk(root):
            subdirs[:] = [s for s in subdirs if s not in ("results", "__pycache__", ".runtime")]
            paths.update(Path(directory) / f for f in files if Path(f).suffix in (".py", ".json", ".m"))
    paths.add(checks.resolve())
    source = {p.relative_to(REPO).as_posix(): sha(p) for p in sorted(paths)}
    slots = [{"id": f"{i:02d}_{case}_{'ON' if enabled else 'OFF'}",
              "case": case, "allow_blocking_edges": enabled} for i, (case, enabled) in enumerate(ORDER, 1)]
    plan = {"protocol": "chapter4-fresh-blocking-edge-ablation-20261107-v1",
        "created_utc": now(), "baseline_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "authorization_scope": "Current delegated request: bounded R1/R3 mechanism check; new independent calls only",
        "old_budget_or_candidate_reused": False, "development_cases_only": True,
        "budgets": {"method_s": 300, "post_s": 60, "method_calls": 4,
                    "max_method_s": 1200, "max_post_s": 240, "calendar_s": 1800},
        "slots": slots, "environment": environment(), "source_sha256": source,
        "checks": {"path": str(checks.relative_to(REPO)), "sha256": sha(checks), "tests": checked["tests_run"]},
        "inputs": {c["common"]["case_id"]: {k: c["common"][k]
            for k in ("input_sha256", "config_sha256")} for c in prior["cases"]},
        "stops": "No retries, no expanded cases; technical/uncertain outcome or post failure stops later slots",
        "ablation": "Identical initializer, target generator, base skeletons, ranking, evaluator, and 300s root; only allow_blocking_edges differs",
        "sorting": "Same exact nonthermal energy and candidate-hash keys; added repaired candidates compete for the same evaluation budget",
        "post": "One fresh <=60s complete original evaluation of each normally returned SAFE; never modifies method U"}
    snapshot = out / "source_snapshot"
    for relative in source:
        if "/results/" not in relative:
            destination = snapshot / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / relative, destination)
    save(out / "plan.json", plan)
    print(json.dumps({"prepared": str(out), "sources": len(source), "slots": slots}), flush=True)


def worker(out, slot_id, post=False):
    entered, started = time.monotonic(), now()
    plan = read(out / "plan.json")
    slot = next(s for s in plan["slots"] if s["id"] == slot_id)
    folder = out / "calls" / slot_id
    phase = "post" if post else "method"
    # Claim exists before launching; started record is exclusive, so an
    # interrupted/uncertain process cannot be silently rerun.
    if not (folder / "claim.json").exists():
        raise ValueError("Unclaimed slot")
    save(folder / (phase + "_started.json"), {"utc": started, "pid": os.getpid(),
        "root_monotonic": entered, "plan_sha256": sha(out / "plan.json")})
    outcome = {"slot": slot, "started_utc": started, "phase": phase, "error": None}
    try:
        from timing import MethodBudget
        seconds = plan["budgets"]["post_s" if post else "method_s"]
        budget = MethodBudget(seconds)
        budget.start, budget.deadline = entered, entered + seconds
        with budget.phase("frozen_identity_and_selected_imports"):
            verify(plan)
            from research.chapter4_scheduler.blocking.method import Bindings, execute_reconstruction
            from heft_method import run_heft
            from thermal import evaluate_candidate
            from p0_batch.run_p0 import fresh_input
        if post:
            with budget.phase("post_read_original_evidence"):
                result = read(folder / "method/result.json")
                instance = read(folder / "method/input_instance.json")
                config = read(folder / "method/input_config.json")
                candidate = result["safe_candidate"]
                hashes = {"input": digest(instance), "candidate": digest(candidate), "method_result": sha(folder / "method/result.json")}
            receipt = evaluate_candidate(instance, candidate, config["accuracy_targets"], budget)
            # Original receipt is retained even if the independent audit fails.
            save(folder / "post_receipt.json", receipt)
            from h02_pair_preflight.receipts import safe_receipt
            energy = safe_receipt(instance, candidate, receipt, config["accuracy_targets"], seconds)
            lo, hi = map(F, result["evaluation"]["weighted_energy_J"])
            if max(lo, F(energy["lower"])) > min(hi, F(energy["upper"])):
                raise ValueError("Independent energy intervals do not overlap")
            if hashes != {"input": digest(instance), "candidate": digest(candidate), "method_result": sha(folder / "method/result.json")}:
                raise ValueError("Post changed original evidence or arguments")
            outcome.update(passed=True, energy=energy, hashes=hashes, timing=budget.summary())
        else:
            loads = []
            def loader(active):
                if active is not budget or loads:
                    raise ValueError("Input/root reuse")
                loads.append(True)
                with budget.phase("fresh_input_expansion_and_hash_check"):
                    raw, config, instance = fresh_input(slot["case"], active)
                    if {"input_sha256": digest(instance), "config_sha256": digest(config)} != plan["inputs"][slot["case"]]:
                        raise ValueError("Original R1/R3 input drift")
                    save(folder / "input_raw_config.json", raw)
                return config, instance
            result = execute_reconstruction(loader, folder / "method", bindings=Bindings(
                run_heft, evaluate_candidate, kind="REAL_CORE"), budget=budget,
                seconds=seconds, allow_blocking_edges=slot["allow_blocking_edges"])
            outcome.update(run_terminal=result["run_terminal"], reason=result["reason"],
                safe=result["safe_candidate"] is not None, fresh_input_calls=len(loads),
                usable=result["usable_as_research_evidence"], timing=result["timing"],
                result_sha256=sha(folder / "method/result.json"))
            if result["run_terminal"] not in ("SEARCH_COMPLETED", "BUDGET_EXHAUSTED"):
                raise ValueError("Non-normal method return: " + str(result["reason"]))
        verify(plan)
    except BaseException as error:
        outcome.update(error={"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()})
    outcome.update(ended_utc=now(), process_body_wall_s=time.monotonic()-entered)
    save(folder / (phase + "_return.json"), outcome)
    print(json.dumps({k: outcome.get(k) for k in ("slot", "phase", "started_utc", "ended_utc", "error", "run_terminal", "passed")}), flush=True)
    return 1 if outcome["error"] else 0


def run(out):
    plan = read(out / "plan.json")
    verify(plan)
    began = time.monotonic()
    save(out / "batch_started.json", {"utc": now(), "plan_sha256": sha(out / "plan.json"), "pid": os.getpid()})
    consumed, error = [], None
    for slot in plan["slots"]:
        if time.monotonic()-began + 480 > plan["budgets"]["calendar_s"]:
            error = "INSUFFICIENT_CALENDAR_FOR_FULL_SLOT"
            break
        folder = out / "calls" / slot["id"]
        folder.mkdir(parents=True, exist_ok=False)
        save(folder / "claim.json", {"utc": now(), "slot": slot, "plan_sha256": sha(out / "plan.json"), "no_retry": True})
        consumed.append(slot["id"])
        for phase, timeout in (("worker", 420), ("post", 70)):
            if phase == "post" and not read(folder / "method_return.json")["safe"]:
                break
            cmd = [sys.executable, "-B", "-m", "research.chapter4_scheduler.mechanism_check.run",
                   phase, "--out", str(out), "--slot", slot["id"]]
            save(folder / (phase + "_command.json"), {"argv": cmd, "cwd": str(REPO), "utc": now()})
            print(json.dumps({"launch": slot["id"], "phase": phase, "utc": now()}), flush=True)
            try:
                process = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=timeout)
                (folder / (phase + "_stdout.log")).write_text(process.stdout, encoding="utf-8")
                (folder / (phase + "_stderr.log")).write_text(process.stderr, encoding="utf-8")
                if process.returncode:
                    error = "WORKER_FAILURE: " + slot["id"] + ":" + phase
                    break
            except subprocess.TimeoutExpired as exc:
                (folder / (phase + "_timeout.log")).write_text(str(exc), encoding="utf-8")
                error = "UNCERTAIN_TIMEOUT: " + slot["id"] + ":" + phase
                break
        if error:
            break
    record = {"started": read(out / "batch_started.json"), "ended_utc": now(),
        "wall_s": time.monotonic()-began, "consumed_method_slots": consumed, "error": error,
        "not_run": [s["id"] for s in plan["slots"] if s["id"] not in consumed]}
    save(out / "batch_return.json", record)
    print(json.dumps(record), flush=True)
    return bool(error)


def analyze(out):
    plan = read(out / "plan.json")
    verify(plan)
    rows = []
    for slot in plan["slots"]:
        folder = out / "calls" / slot["id"]
        if not (folder / "method/result.json").exists():
            rows.append({**slot, "state": "NOT_RUN_OR_NO_RESULT"})
            continue
        result = read(folder / "method/result.json")
        initial = result.get("initial_safe_snapshot")
        evaluations = result["evaluations"]
        graphs = result["graph_proposals"]
        d = result["reconstruction_attempts"]
        rows.append({**slot, "state": result["state"], "run_terminal": result["run_terminal"],
            "initialization_completed": result.get("initialization", {}).get("status") == "BOUNDED_SEARCH_COMPLETED" and initial is not None,
            "initial_semantic_sha256": semantic(initial["candidate"]) if initial else None,
            "initial_candidate_sha256": initial["candidate_sha256"] if initial else None,
            "initial_energy": initial["energy"] if initial else None,
            "final_semantic_sha256": semantic(result["safe_candidate"]) if result["safe_candidate"] else None,
            "final_energy": result["evaluation"]["weighted_energy_J"] if result["evaluation"] else None,
            "method_wall_s": result["timing"]["method_elapsed_s"],
            "phases_s": result["timing"]["phases_exclusive_s"],
            "full_evaluator_calls": sum(not r.get("cache_hit", False) for r in evaluations),
            "initial_evaluator_calls": sum(r["phase"] == "initialization" and not r.get("cache_hit", False) for r in evaluations),
            "refinement_evaluator_calls": sum(r["phase"] == "refinement" and not r.get("cache_hit", False) for r in evaluations),
            "cache_hits": result["cache_hits"], "proposals": len(graphs),
            "extra_edge_proposals": sum(bool(p.get("additional_reversed_edges")) for p in graphs),
            "graph_strict_improvements": result["graph_strict_improvements"],
            "accepted_extra_edge_proposals": [p for p in graphs if p["strict_accepted"] and p.get("additional_reversed_edges")],
            "structural_attempts": len(d), "extra_edge_attempts": sum(p["extra_resource_edge"] is not None for p in d),
            "deadline_failures": sum(bool(p["deadline_violations"]) for p in d),
            "post_passed": read(folder / "post_return.json").get("passed", False) if (folder / "post_return.json").exists() else False,
            "result_sha256": sha(folder / "method/result.json")})
    comparisons = []
    for case in ("base__R1", "base__R3"):
        pair = [r for r in rows if r["case"] == case]
        comparable = all(r.get("initialization_completed") for r in pair) and len(pair) == 2
        comparable &= len({r.get("initial_semantic_sha256") for r in pair}) == 1
        comparable &= len({digest(r.get("initial_energy")) for r in pair}) == 1
        comparisons.append({"case": case, "same_completed_initialization_and_interval": comparable,
            "attribution": "toggle-only under equal wall budgets; evaluation counts may differ" if comparable else "initialization mismatch/incomplete: no single-factor attribution"})
    summary = {"created_utc": now(), "rows": rows, "comparisons": comparisons,
        "batch": read(out / "batch_return.json"), "source_and_archive_hashes_unchanged": True,
        "scope": "Two development cases, one call per arm; no generalization or optimality proof"}
    save(out / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "worker", "post", "analyze"))
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--checks", type=Path)
    parser.add_argument("--slot")
    args = parser.parse_args()
    out = args.out.resolve()
    out.relative_to(REPO / "research/chapter4_scheduler/results")
    if args.action == "prepare":
        prepare(out, args.checks.resolve())
    elif args.action == "run":
        return run(out)
    elif args.action in ("worker", "post"):
        return worker(out, args.slot, args.action == "post")
    else:
        analyze(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
