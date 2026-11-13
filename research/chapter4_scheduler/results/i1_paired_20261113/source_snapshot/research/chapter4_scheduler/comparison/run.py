"""New authorized R2/R5 fourteen-call comparison, with exclusive claims."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction as F
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO), str(REPO / "research/chapter3_experiments")]
from research.chapter4_scheduler.mechanism_check.run import read, save, sha, digest, environment
from .core import ORDER, CLOCK_ORIGIN, EvaluationJournal, normalize, time_to_quality, conditional_statistics

BASE = "183701e3394454ad588f538085bc06f08e7621a3"
BRANCH = "chapter4/r2-r5-validation-20261107"
THREADS = {n: "1" for n in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")}
BUDGETS = {"method_s": 300, "method_calls": 14, "method_total_s": 4200,
           "post_s": 60, "post_calls_at_most": 14, "post_total_s_at_most": 840, "calendar_s": 9000}


def now():
    return datetime.now(timezone.utc).isoformat()


def resources():
    memory = next(int(line.split()[1]) * 1024 for line in Path("/proc/meminfo").read_text().splitlines() if line.startswith("MemAvailable:"))
    result = {"utc": now(), "available_memory_bytes": memory, "disk_free_bytes": shutil.disk_usage(REPO).free,
              "loadavg": list(os.getloadavg()), "cpu_count": os.cpu_count()}
    result["sufficient"] = memory >= 2 * 1024**3 and result["disk_free_bytes"] >= 4 * 1024**3 and result["loadavg"][0] <= 2 * result["cpu_count"]
    return result


def slots():
    return [{"id": f"{i:02d}_{case}_{arm}" + (f"_{seed}" if seed is not None else ""),
             "case": case, "arm": arm, "seed": seed} for i, (case, arm, seed) in enumerate(ORDER, 1)]


def verify(plan, *, protected=False):
    if not plan.get("authorized") or not plan.get("execution_enabled") or plan.get("protocol") != "chapter4-main-comparison-v1":
        raise ValueError("New current-version declaration required; old proposal is not executable")
    if plan["slots"] != slots() or plan["budgets"] != BUDGETS or plan["thread_environment"] != THREADS:
        raise ValueError("Frozen order/budget/runtime settings drift")
    if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip() != BASE:
        raise ValueError("Subject commit changed")
    if subprocess.check_output(["git", "branch", "--show-current"], cwd=REPO, text=True).strip() != BRANCH:
        raise ValueError("Work branch changed")
    if environment() != plan["environment"]:
        raise ValueError("Environment drift")
    identities = dict(plan["source_sha256"])
    if protected:
        identities.update(plan["protected_archive_sha256"])
    for relative, expected in identities.items():
        if sha(REPO / relative) != expected:
            raise ValueError("Frozen bytes changed: " + relative)


def prepare(out, checks):
    if out.exists():
        raise FileExistsError(str(out))
    checked = read(checks)
    if not checked.get("passed") or checked.get("forbidden_calls"):
        raise ValueError("Passing new guarded prechecks required")
    parent = out.parent
    regression = read(parent / "regression/checks.json")
    sa_checks = read(parent / "sa_regression/checks.json")
    legacy = read(parent / "legacy_validation/checks.json")
    if not (regression["passed"] and regression["tests_run"] == 109 and sa_checks["passed"]
            and sa_checks["tests_run"] == 21 and legacy["passed"] and legacy["tests_run"] == 12):
        raise ValueError("Fresh original regression suites required")
    from p0_batch.run_p0 import fresh_input
    from timing import MethodBudget
    from sa_method import algorithm_parameters
    import numpy, scipy
    resources_before = resources()
    if not resources_before["sufficient"]:
        raise ValueError("Insufficient resources")
    out.mkdir(parents=True)
    old = read(REPO / "research/chapter4_scheduler/results/algorithm_analysis_20261107/comparison_proposal.json")
    inputs = {}
    for case in ("base__R2", "base__R5"):
        raw, config, instance = fresh_input(case, MethodBudget(30))
        identities = {"raw_config_sha256": digest(raw), "config_sha256": digest(config), "input_sha256": digest(instance)}
        if identities != old["inputs"][case]:
            raise ValueError("Original input changed")
        inputs[case] = identities
        folder = out / "frozen_inputs" / case
        folder.mkdir(parents=True)
        for name, value in (("raw_config", raw), ("config", config), ("instance", instance)):
            save(folder / (name + ".json"), value)
    paths = set()
    for root in ("research/chapter3_experiments", "research/chapter4_scheduler", "research/v1_evaluator"):
        for directory, subdirs, filenames in os.walk(REPO / root):
            subdirs[:] = [s for s in subdirs if s not in ("results", "__pycache__", ".runtime")]
            paths.update(Path(directory) / name for name in filenames if Path(name).suffix in (".py", ".json", ".m", ".csv"))
    paths.update((checks, parent / "regression/checks.json", parent / "sa_regression/checks.json", parent / "legacy_validation/checks.json"))
    tracked = subprocess.check_output(["git", "ls-files", "-z", "research/chapter4_scheduler/results"], cwd=REPO).decode().strip("\0").split("\0")
    archives = {p: sha(REPO / p) for p in tracked if p}
    sources = {p.relative_to(REPO).as_posix(): sha(p) for p in sorted(paths)}
    for path in paths:
        if "/results/" not in path.as_posix():
            target = out / "source_snapshot" / path.relative_to(REPO)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    plan = {"protocol": "chapter4-main-comparison-v1", "authorized": True, "execution_enabled": True,
        "created_utc": now(), "subject_commit": BASE, "branch": BRANCH,
        "uncommitted_new_code_frozen_by_sha256_and_source_snapshot": True,
        "authorization": "Latest delegated user request: implement/test fresh executor then run R2,R5 HEFT1 ON1 original SA101..105 each; 14x300s including initialization, at most14x60s same-evaluator post; no expansion, main change or push",
        "old_proposal_left_inert": True, "slots": slots(), "budgets": BUDGETS,
        "environment": environment(), "thread_environment": THREADS, "resource_preflight": resources_before,
        "source_sha256": sources, "protected_archive_sha256": archives, "input_identities": inputs,
        "SA_parameters": algorithm_parameters(),
        "initialization": "Native, independently charged, no shared answer. SA uses HEFT construction only; HEFT and ON run complete enhanced HEFT initialization. Primary comparison is end-to-end, not an initialization ablation.",
        "evaluation": "Unchanged original thermal.evaluate_candidate forwarded by the same counting journal for every arm; full original scenes/nodes/window/accuracy/thermal safety and energy",
        "instrumentation": "Temporary process-local callable at thermal.evaluate_candidate forwards exact original arguments and return; common attempt/receipt accounting only. All instrumentation overhead charged; SA-specific recorder overhead remains part of method cost.",
        "timing": CLOCK_ORIGIN + "; interpreter and standard launcher imports excluded uniformly; actual process wall times separately recorded",
        "counts": "Attempts includes evaluator exceptions; returned includes incomplete receipts; SAFE means recorder-validated full timely noncached receipt. Cache hits separate; no legacy full_evaluator_calls pooling.",
        "quality_times": "First SAFE, first strict upper<first-SAFE.lower, own final upper, and retrospectively upper<=fresh HEFT/ON upper; thresholds for analysis only, never fed to search",
        "statistics": "All seeds retained; conditional median/range of final upper among SAFE+post successes and success count/5; no best-seed substitution or pooling cases",
        "post": "One separate fresh process/root <=60s per normal SAFE method, same original evaluator, not independent numerical implementation; complete SAFE and overlapping energy required",
        "stops": "No retries, refunds, seed/case replacement or tuning. Retain normal no-SAFE/budget/poor outcomes. Technical/numerical/identity/post failure halts later slots.",
        "limits": "Two already exposed same-family cases; one deterministic run per method/case, SA5x300s aggregate cost; no generalization, statistical speedup or optimality claim",
        "prechecks": {"new": {"path": str(checks.relative_to(REPO)), "count": checked["tests_run"]},
            "original": 109, "SA_adapter": 21, "legacy_launcher": 12}}
    verify(plan, protected=True)
    save(out / "plan.json", plan)
    save(out / "plan_identity.json", {"plan_sha256": sha(out / "plan.json"), "created_utc": now()})
    print({"prepared": str(out), "plan_sha256": sha(out / "plan.json"), "sources": len(sources), "protected_archives": len(archives), "slots": 14}, flush=True)


def assert_root(budget, root):
    if (budget.start, budget.deadline, budget.seconds, budget.clock) != root:
        raise ValueError("ROOT_BUDGET_CHANGED")


def worker(out, slot_id, *, post=False):
    entered, started = time.monotonic(), now()
    phase = "post" if post else "method"
    folder = out / "calls" / slot_id
    result = {"phase": phase, "slot_id": slot_id, "started_utc": started, "error": None,
              "normal_stop": False, "has_SAFE_archive": False}
    budget = journal = raw = None
    try:
        from timing import MethodBudget
        budget = MethodBudget(60 if post else 300)
        budget.start, budget.deadline = entered, entered + budget.seconds
        root = (budget.start, budget.deadline, budget.seconds, budget.clock)
        with budget.phase("frozen_identity_and_scientific_imports"):
            plan = read(out / "plan.json")
            if read(out / "plan_identity.json")["plan_sha256"] != sha(out / "plan.json"):
                raise ValueError("PLAN_HASH_CHANGED")
            slot = next(s for s in plan["slots"] if s["id"] == slot_id)
            claim = read(folder / ("post_claim.json" if post else "claim.json"))
            if claim["plan_sha256"] != sha(out / "plan.json") or claim["slot"] != slot:
                raise ValueError("CLAIM_PLAN_MISMATCH")
            verify(plan)
            if any(os.environ.get(k) != v for k, v in THREADS.items()):
                raise ValueError("THREAD_RUNTIME_CHANGED")
            import thermal
            from heft_method import run_heft
            from p0_batch.run_p0 import fresh_input
            from research.chapter4_scheduler.validation.sa_adapter import dispatch_with_sa, SABindings
            from research.chapter4_scheduler.blocking.method import Bindings
            from sa_method import run_sa, algorithm_parameters
            from h02_pair_preflight.receipts import safe_receipt
            if algorithm_parameters() != plan["SA_parameters"]:
                raise ValueError("SA_PARAMETERS_CHANGED")
        with (folder / (phase + "_evaluation_journal.jsonl")).open("x", encoding="utf-8") as stream:
            journal = EvaluationJournal(thermal.evaluate_candidate, budget, stream)
            if post:
                with budget.phase("read_own_final_evidence"):
                    raw = read(folder / "method/result.json")
                    instance = read(folder / "method/input_instance.json")
                    config = read(folder / "method/input_config.json")
                    candidate = raw["safe_candidate"]
                    immutable = (sha(folder / "method/result.json"), digest(instance), digest(config), digest(candidate))
                with budget.phase("complete_post_evaluation"):
                    receipt = journal(instance, candidate, config["accuracy_targets"], budget)
                save(folder / "post_receipt.json", receipt)
                energy = safe_receipt(instance, candidate, receipt, config["accuracy_targets"], 60)
                if receipt["completed_at_elapsed_s"] >= 60:
                    raise ValueError("POST_SAFE_AFTER_DEADLINE")
                lo, hi = map(F, raw["evaluation"]["weighted_energy_J"])
                if max(lo, F(energy["lower"])) > min(hi, F(energy["upper"])):
                    raise ValueError("POST_INTERVAL_DISJOINT")
                if immutable != (sha(folder / "method/result.json"), digest(instance), digest(config), digest(candidate)):
                    raise ValueError("POST_ARGUMENT_OR_RESULT_MUTATED")
                timing = budget.summary()
                timing["clock_origin"] = CLOCK_ORIGIN
                result.update(passed=True, normal_stop=True, has_SAFE_archive=True, energy=energy, timing=timing,
                              evaluation_attempts=len(journal.attempts), same_numerical_evaluator=True)
            else:
                loads = []
                def loader(active):
                    if active is not budget or loads:
                        raise ValueError("FRESH_INPUT_AND_ORIGINAL_ROOT_REQUIRED")
                    loads.append(True)
                    with budget.phase("fresh_input_expansion"):
                        config_raw, config, instance = fresh_input(slot["case"], active)
                        actual = {"raw_config_sha256": digest(config_raw), "config_sha256": digest(config), "input_sha256": digest(instance)}
                        if actual != plan["input_identities"][slot["case"]]:
                            raise ValueError("FROZEN_INPUT_CHANGED")
                        save(folder / "input_raw_config.json", config_raw)
                    return config, instance
                # All existing REAL identity checks see the same forwarding
                # callable; its captured original is never replaced internally.
                with patch.object(thermal, "evaluate_candidate", journal):
                    bindings = SABindings(run_sa, journal, "REAL_CORE") if slot["arm"] == "SA" else Bindings(run_heft, journal, "REAL_CORE")
                    raw = dispatch_with_sa(slot["arm"], loader, folder / "method", budget, seed=slot["seed"], bindings=bindings)
                result.update(normalize(raw, journal), slot=slot, formal_comparison_result=True,
                              fresh_input_calls=len(loads), raw_result_sha256=sha(folder / "method/result.json"), plan_sha256=sha(out / "plan.json"))
                if not result["normal_stop"]:
                    raise ValueError("ABNORMAL_METHOD_STOP:" + str(result["raw_reason"]))
            assert_root(budget, root)
            verify(plan)
    except BaseException as error:
        result["error"] = {"type": type(error).__name__, "reason": str(error), "traceback": traceback.format_exc()}
        if budget is not None:
            timing = budget.summary();timing["clock_origin"] = CLOCK_ORIGIN
            result["failure_timing"] = timing
    result.update(ended_utc=now(), process_body_wall_s=time.monotonic() - entered,
                  evaluation_attempts_journal=deepcopy(journal.attempts) if journal else [])
    save(folder / (phase + "_return.json"), result)
    print({k: result.get(k) for k in ("slot_id", "phase", "normal_stop", "has_SAFE_archive", "terminal", "error", "process_body_wall_s")}, flush=True)
    return bool(result["error"])


def batch(out):
    plan = read(out / "plan.json")
    verify(plan, protected=True)
    if sha(out / "plan.json") != read(out / "plan_identity.json")["plan_sha256"]:
        raise ValueError("Plan hash mismatch")
    began = time.monotonic()
    save(out / "batch_started.json", {"utc": now(), "plan_sha256": sha(out / "plan.json"), "resources": resources()})
    consumed, posts, error = [], [], None
    env = dict(os.environ, **THREADS)
    for slot in plan["slots"]:
        if time.monotonic() - began + 510 > plan["budgets"]["calendar_s"]:
            error = "INSUFFICIENT_CALENDAR_FOR_FULL_SLOT";break
        if not resources()["sufficient"]:
            error = "RESOURCE_PREFLIGHT_FAILED";break
        verify(plan)
        folder = out / "calls" / slot["id"]
        folder.mkdir(parents=True, exist_ok=False)
        save(folder / "claim.json", {"utc": now(), "slot": slot, "plan_sha256": sha(out / "plan.json"), "no_retry": True})
        consumed.append(slot["id"])
        for phase, timeout in (("worker", 420), ("post", 90)):
            if phase == "post":
                if not read(folder / "method_return.json")["has_SAFE_archive"]:
                    break
                save(folder / "post_claim.json", {"utc": now(), "slot": slot, "plan_sha256": sha(out / "plan.json"), "no_retry": True})
                posts.append(slot["id"])
            command = [sys.executable, "-B", "-m", "research.chapter4_scheduler.comparison.run", phase, "--out", str(out), "--slot", slot["id"]]
            command_record = {"argv": command, "cwd": str(REPO), "started_utc": now(), "thread_environment": THREADS, "process_watchdog_s": timeout}
            save(folder / (phase + "_command_started.json"), command_record)
            print({"event": "START", "slot": slot, "phase": phase, "utc": now()}, flush=True)
            started = time.monotonic()
            try:
                completed = subprocess.run(command, cwd=REPO, env=env, capture_output=True, text=True, timeout=timeout)
                (folder / (phase + "_stdout.log")).write_text(completed.stdout)
                (folder / (phase + "_stderr.log")).write_text(completed.stderr)
                command_record.update(ended_utc=now(), wall_s=time.monotonic() - started, exit_code=completed.returncode)
                save(folder / (phase + "_command_return.json"), command_record)
                if completed.returncode:
                    error = slot["id"] + ":" + phase + ":NONZERO_EXIT";break
                returned = read(folder / ("method_return.json" if phase == "worker" else "post_return.json"))
                if returned.get("error") or not returned.get("normal_stop"):
                    error = slot["id"] + ":" + phase + ":ABNORMAL_RETURN";break
                print({"event": "DONE", "slot": slot, "phase": phase, "utc": now(),
                       "terminal": returned.get("terminal"), "safe": returned.get("has_SAFE_archive"), "counts": returned.get("counts")}, flush=True)
            except BaseException as failure:
                if isinstance(failure, subprocess.TimeoutExpired):
                    for name, value in (("stdout", failure.stdout), ("stderr", failure.stderr)):
                        (folder / (phase + "_partial_" + name + ".log")).write_bytes(value.encode() if isinstance(value, str) else value or b"")
                error = slot["id"] + ":" + phase + ":" + type(failure).__name__
                save(folder / (phase + "_process_failure.json"), {"utc": now(), "reason": str(failure), "traceback": traceback.format_exc()})
                break
        if error:
            break
    try:
        verify(plan, protected=True)
    except Exception as failure:
        error = (error or "") + ";FINAL_IDENTITY_FAILURE:" + str(failure)
    result = {"ended_utc": now(), "wall_s": time.monotonic() - began, "consumed_method_slots": consumed,
              "consumed_post_slots": posts, "error": error, "completed": not error and len(consumed) == 14,
              "no_retry_or_refund": True, "plan_sha256": sha(out / "plan.json")}
    save(out / "batch_return.json", result)
    print(result, flush=True)
    return not result["completed"]


def summarize(out):
    plan = read(out / "plan.json")
    verify(plan, protected=True)
    all_rows, raw_by_slot = [], {}
    for slot in plan["slots"]:
        folder = out / "calls" / slot["id"]
        returned = folder / "method_return.json"
        row = {"slot": slot, "state": "NOT_RUN", "success": False}
        if returned.exists():
            method = read(returned)
            row.update(state=method.get("terminal", "TECHNICAL_STOP"), result=method)
            post_path = folder / "post_return.json"
            post = read(post_path) if post_path.exists() else None
            row.update(post=post, success=bool(method.get("normal_stop") and not method.get("error") and method.get("has_SAFE_archive") and post and post.get("passed") and not post.get("error")))
            if (folder / "method/result.json").exists():
                raw_by_slot[slot["id"]] = read(folder / "method/result.json")
        elif folder.exists():
            row["state"] = "PROCESS_FAILED_WITHOUT_METHOD_RETURN"
        all_rows.append(row)
    by_case = {}
    for case in ("base__R2", "base__R5"):
        rows = [r for r in all_rows if r["slot"]["case"] == case]
        references = {r["slot"]["arm"]: r["result"]["energy_interval_J"] for r in rows if r["slot"]["arm"] in ("HEFT", "ON") and r["success"]}
        for row in rows:
            raw = raw_by_slot.get(row["slot"]["id"])
            row["time_to_reference_upper_s"] = {arm: time_to_quality(raw, energy[1]) if raw else None for arm, energy in references.items()}
        sa_rows = [r for r in rows if r["slot"]["arm"] == "SA"]
        by_case[case] = {"SA": conditional_statistics([r["result"]["energy_interval_J"][1] for r in sa_rows if r["success"]], 5),
            "SA_seed_outcomes": [{"seed": r["slot"]["seed"], "state": r["state"], "success": r["success"],
                "energy_interval_J": r.get("result", {}).get("energy_interval_J")} for r in sa_rows], "references": references}
    result = {"created_utc": now(), "plan_sha256": sha(out / "plan.json"), "batch": read(out / "batch_return.json"),
              "rows": all_rows, "cases": by_case, "nature": "Read-only aggregation; no search or thermal integration",
              "post_is_same_evaluator": True, "conditional_statistics_not_best_seed": True}
    save(out / "summary.json", result)
    print({"summary": str(out / "summary.json"), "batch_complete": result["batch"]["completed"], "cases": by_case}, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "batch", "worker", "post", "summarize"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--checks", type=Path)
    parser.add_argument("--slot")
    args = parser.parse_args()
    out = args.out.resolve()
    out.relative_to(REPO / "research/chapter4_scheduler/results")
    if args.phase == "prepare":
        prepare(out, args.checks.resolve());return 0
    if args.phase in ("worker", "post"):
        return worker(out, args.slot, post=args.phase == "post")
    if args.phase == "batch":
        return batch(out)
    summarize(out);return 0


if __name__ == "__main__":
    sys.exit(main())
