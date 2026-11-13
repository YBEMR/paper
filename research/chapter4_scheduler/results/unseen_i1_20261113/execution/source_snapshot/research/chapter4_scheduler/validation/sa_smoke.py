"""One fixed five-second SA engineering smoke, never a comparison batch.

Prepare writes an inert declaration. Each worker consumes an exclusive claim;
no retries, alternate cases/seeds or budget extensions are supported.
"""
from datetime import datetime, timezone
from fractions import Fraction as F
from pathlib import Path
import argparse
import subprocess
import sys
import time
import traceback

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO), str(REPO / "research/chapter3_experiments")]
from research.chapter4_scheduler.mechanism_check.run import read, save, sha, digest, environment


def now():
    return datetime.now(timezone.utc).isoformat()


def verify(plan):
    if (plan["case"], plan["seed"], plan["method_s"], plan["post_s"]) != ("base__R2", 101, 5, 5):
        raise ValueError("Fixed engineering smoke changed")
    if plan["purpose"] != "ENGINEERING_SMOKE_NOT_A_COMPARISON_RESULT":
        raise ValueError("Not a formal-comparison launcher")
    if environment() != plan["environment"]:
        raise ValueError("Runtime drift")
    if any(sha(REPO / p) != h for p, h in plan["sources_sha256"].items()):
        raise ValueError("Source drift")


def prepare(out, checks):
    from .sa_adapter import source_identity
    from p0_batch.run_p0 import fresh_input
    from timing import MethodBudget
    if not read(checks)["passed"]:
        raise ValueError("Passing adapter checks required")
    out.mkdir(parents=True, exist_ok=False)
    # Input-only preflight is separate from the fresh charged worker input.
    raw, config, instance = fresh_input("base__R2", MethodBudget(30))
    sources = {"research/" + p: h for p, h in source_identity().items()}
    for path in (Path(__file__), Path(__file__).with_name("sa_precheck.py"),
                 Path(__file__).with_name("test_sa_adapter.py")):
        sources[path.relative_to(REPO).as_posix()] = sha(path)
    plan = {"created_utc": now(), "purpose": "ENGINEERING_SMOKE_NOT_A_COMPARISON_RESULT",
        "case": "base__R2", "seed": 101, "method_s": 5, "post_s": 5,
        "method_calls_at_most": 1, "post_calls_at_most": 1, "retry": False,
        "baseline_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "environment": environment(), "sources_sha256": sources,
        "input_identities": {"raw_config_sha256": digest(raw), "config_sha256": digest(config),
                             "input_sha256": digest(instance)},
        "precheck_sha256": sha(checks), "precheck_path": str(checks),
        "initialization": "Unchanged native SA; fresh inputs and cache per call; no shared HEFT answer",
        "budget": "Each worker root includes selected imports, source checks, input and evaluation; serialization separate",
        "post": "Same original evaluator, fresh root; no independent numerical implementation",
        "no_gain_or_mapping_coverage_requirement": True}
    verify(plan)
    save(out / "plan.json", plan)
    print({"prepared": str(out), "purpose": plan["purpose"]}, flush=True)


def worker(out, phase):
    plan = read(out / "plan.json")
    verify(plan)
    if phase == "post":
        method = read(out / "method/result.json")
        if method["state"] != "SAFE" or method["run_terminal"] not in ("SEARCH_COMPLETED", "BUDGET_EXHAUSTED"):
            raise ValueError("Post requires a normally stopped complete SAFE method result")
    save(out / (phase + "_claim.json"), {"utc": now(), "no_retry": True, "plan_sha256": sha(out / "plan.json")})
    entered, started = time.monotonic(), now()
    outcome = {"phase": phase, "started_utc": started, "purpose": plan["purpose"], "error": None}
    budget = None
    try:
        from timing import MethodBudget
        budget = MethodBudget(5)
        budget.start, budget.deadline = entered, entered + 5
        root = (budget.start, budget.deadline, budget.seconds, budget.clock)
        with budget.phase("frozen_sources_and_selected_imports"):
            verify(plan)
            from .sa_adapter import execute_sa
            from p0_batch.run_p0 import fresh_input
            from thermal import evaluate_candidate
            from h02_pair_preflight.receipts import safe_receipt
        if phase == "method":
            loads = []
            def loader(active):
                if active is not budget or loads:
                    raise ValueError("Fresh input/root required")
                loads.append(True)
                raw, config, instance = fresh_input(plan["case"], active)
                actual = {"raw_config_sha256": digest(raw), "config_sha256": digest(config), "input_sha256": digest(instance)}
                if actual != plan["input_identities"]:
                    raise ValueError("Input drift")
                save(out / "input_raw_config.json", raw)
                return config, instance
            result = execute_sa(loader, out / "method", seed=plan["seed"], budget=budget)
            outcome.update(state=result["state"], run_terminal=result["run_terminal"], reason=result["reason"],
                full_evaluator_calls=result.get("full_evaluator_calls", 0),
                returned_evaluator_receipts=result.get("returned_evaluator_receipts", 0), fresh_input_calls=len(loads),
                formal_comparison_result=result["formal_comparison_result"], timing=result["timing"])
        else:
            with budget.phase("read_final_SAFE_candidate"):
                instance = read(out / "method/input_instance.json")
                config = read(out / "method/input_config.json")
                candidate = method["safe_candidate"]
                original = (digest(instance), digest(config), digest(candidate), sha(out / "method/result.json"))
            receipt = evaluate_candidate(instance, candidate, config["accuracy_targets"], budget)
            save(out / "post_receipt.json", receipt)
            energy = safe_receipt(instance, candidate, receipt, config["accuracy_targets"], 5)
            if receipt["completed_at_elapsed_s"] >= 5:
                raise ValueError("Post SAFE late")
            lo, hi = map(F, method["evaluation"]["weighted_energy_J"])
            if max(lo, F(energy["lower"])) > min(hi, F(energy["upper"])):
                raise ValueError("Disjoint post energy interval")
            if original != (digest(instance), digest(config), digest(candidate), sha(out / "method/result.json")):
                raise ValueError("Post mutated evidence")
            outcome.update(passed=True, energy=energy, timing=budget.summary())
        if root != (budget.start, budget.deadline, budget.seconds, budget.clock):
            raise ValueError("Root drift")
        verify(plan)
    except BaseException as error:
        outcome["error"] = {"type": type(error).__name__, "reason": str(error), "traceback": traceback.format_exc()}
        if budget is not None:
            outcome["failure_timing"] = budget.summary()
    outcome.update(ended_utc=now(), body_wall_s=time.monotonic() - entered)
    save(out / (phase + "_return.json"), outcome)
    print(outcome, flush=True)
    return bool(outcome["error"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "method", "post"))
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--checks", type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    out.relative_to(REPO / "research/chapter4_scheduler/results")
    if args.phase == "prepare":
        prepare(out, args.checks)
        return 0
    return worker(out, args.phase)


if __name__ == "__main__":
    sys.exit(main())
