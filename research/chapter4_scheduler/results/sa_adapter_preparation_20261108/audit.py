"""Read-only artifact/receipt audit; integration and search are forbidden."""
from contextlib import ExitStack
from datetime import datetime, timezone
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import time
from unittest.mock import patch

REPO = Path.cwd()
OUT = Path(__file__).resolve().parent
sys.path[:0] = [str(REPO), str(REPO / "research/chapter3_experiments")]
from research.chapter4_scheduler.mechanism_check.run import read, save, sha, digest
from h02_pair_preflight.receipts import safe_receipt
from schedules import validate_schedule

started = datetime.now(timezone.utc).isoformat()
clock = time.monotonic()
checks = []
def check(name, condition):
    checks.append({"name": name, "passed": bool(condition)})
    if not condition:
        raise AssertionError(name)

def forbidden(*args, **kwargs):
    raise AssertionError("No new integration/search permitted in audit")

with ExitStack() as stack:
    for name in ("thermal.evaluate_candidate", "thermal.evaluate_piecewise", "sa_method.run_sa", "heft_method.run_heft"):
        stack.enter_context(patch(name, side_effect=forbidden))
    protected = read(OUT / "protected_before.json")["files"]
    check("1298 existing analysis/execution/design/mechanism files unchanged", all(sha(REPO / p) == h for p, h in protected.items()))
    check("all tracked files unchanged", subprocess.check_output(["git", "diff", "HEAD", "--name-only"], text=True) == "")
    check("HEAD unchanged", subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip() == "d47bfda700ce76df31d9aae0aea97d01279b501f")
    check("work branch retained", subprocess.check_output(["git", "branch", "--show-current"], text=True).strip() == "chapter4/r2-r5-validation-20261107")
    for folder, expected in (("unit_run02", 21), ("regression", 109), ("legacy_validation", 12)):
        record = read(OUT / folder / "checks.json")
        check(folder + " passing guarded tests", record["passed"] and record["tests_run"] == expected and not record["forbidden_calls"])
    plan = read(OUT / "smoke/plan.json")
    check("all 22 frozen source identities retained", all(sha(REPO / p) == h for p, h in plan["sources_sha256"].items()))
    old = read(REPO / "research/chapter4_scheduler/results/validation_execution_20261107/plan.json")
    check("original R2 input/config/raw identities", plan["input_identities"] == old["input_identities"]["base__R2"])
    result = read(OUT / "smoke/method/result.json")
    instance = read(OUT / "smoke/method/input_instance.json")
    config = read(OUT / "smoke/method/input_config.json")
    check("fresh input identity", digest(instance) == plan["input_identities"]["input_sha256"])
    check("explicit seed101 forwarded", result["seed"] == result["search"]["seed"] == 101)
    check("normal budget stop with valid SAFE archive", result["state"] == "SAFE" and result["run_terminal"] == "BUDGET_EXHAUSTED")
    check("not a formal comparison result", result["formal_comparison_result"] is False and plan["purpose"] == "ENGINEERING_SMOKE_NOT_A_COMPARISON_RESULT")
    check("ten attempts and ten returned receipts separately accounted", result["full_evaluator_calls"] == result["returned_evaluator_receipts"] == len(result["evaluator_attempts"]) == 10)
    safe_count = 0
    for number, row in enumerate(result["evaluations"]):
        receipt, candidate = row["receipt"], row["candidate"]
        check(f"row{number} candidate SHA", digest(candidate) == row["candidate_sha256"])
        check(f"row{number} receipt identities", receipt["evidence_identity"] == {"input_sha256": digest(instance), "candidate_sha256": digest(candidate)})
        check(f"row{number} complete schedule legality", receipt["legality"] == validate_schedule(instance, candidate))
        if receipt["state"] == "SAFE":
            safe_count += 1
            energy = safe_receipt(instance, candidate, receipt, config["accuracy_targets"], 5)
            check(f"row{number} full SAFE and timely formation", row["accepted_safe"] and energy == row["energy"] and receipt["completed_at_elapsed_s"] < 5)
        else:
            check(f"row{number} unresolved never accepted SAFE", not row["accepted_safe"])
    check("exactly nine complete SAFE returned before cutoff", safe_count == 9)
    safe_rows = [r for r in result["evaluations"] if r["accepted_safe"]]
    check("best upper archive independent of SA current", F(result["safe_upper_bound_J"]) == min(F(r["energy"]["upper"]) for r in safe_rows))
    check("first native SAFE snapshot preserved", result["initial_safe_snapshot"]["candidate_sha256"] == safe_rows[0]["candidate_sha256"])
    check("no forced full enhanced HEFT warm start", result["search"]["initialisation_source"] == "heft" and result["initial_safe_snapshot"]["source"] == "sa_initial_heft")
    check("native uphill acceptance remains possible", result["search"]["counters"]["accepted_uphill_midpoint"] == 1)
    check("real mapping coverage not claimed", result["search"]["moves_proposed"].get("mapping", 0) == 0)
    check("five-second unchanged root includes native initialization", result["root_context"]["root_seconds"] == result["timing"]["limit_s"] == 5)
    post = read(OUT / "smoke/post_return.json")
    receipt = read(OUT / "smoke/post_receipt.json")
    energy = safe_receipt(instance, result["safe_candidate"], receipt, config["accuracy_targets"], 5)
    check("one full SAFE fresh post", post["passed"] and not post["error"] and receipt["completed_at_elapsed_s"] < 5)
    check("post and method energy intervals overlap", max(F(energy["lower"]), F(result["evaluation"]["weighted_energy_J"][0])) <= min(F(energy["upper"]), F(result["evaluation"]["weighted_energy_J"][1])))
    check("one method and post claim; no retries", len(list((OUT / "smoke").glob("*_claim.json"))) == 2)
    check("post same evaluator, not independent numerical implementation", "Same original evaluator" in plan["post"])

record = {"started_utc": started, "ended_utc": datetime.now(timezone.utc).isoformat(), "wall_s": time.monotonic() - clock,
    "passed": all(c["passed"] for c in checks), "checks": checks, "protected_files": len(protected),
    "nature": "Read-only hashes, schedule validation and full-receipt revalidation; no search/integration",
    "real_integrations": 0, "real_searches": 0,
    "known_metadata_issue": "post_return.timing.clock_origin inherits generic imports-excluded text; worker source and phase records show selected imports included in the unchanged five-second root. Raw record retained."}
save(OUT / "audit.json", record)
print({k: record[k] for k in ("passed", "wall_s", "protected_files", "real_integrations", "real_searches")}, flush=True)
