"""Run the approved ten missing positions on build 26300 with the frozen worker."""
import argparse
import platform
from pathlib import Path

from pending_cells import BUNDLE, HERE, audit, before_deadline, claim, cross, digest, require


CHECKPOINT = HERE / "checkpoints/windows_26200/audit.json"
CHECKPOINT_SHA = "5feacd7fb3b286600afae76a0bdeb8dff8127354cf2cf2481c26c6da76da8f60"
SUBJECT = "12384b8e52f917b38497b65ee5c6045f094339e3"
STAGE = "windows_26300"


def verify(repo, run):
    require(digest(CHECKPOINT) == CHECKPOINT_SHA, "Original checkpoint changed")
    old = run / "continuation_04/formal"
    snapshot = cross.read(CHECKPOINT)
    for name, key in (("batch_progress.json", "source_progress_sha256"), ("check.json", "prior_check_sha256"),
                      ("batch_start.json", "original_roster_sha256")):
        require(digest(old / name) == snapshot[key], "Original stage changed: " + name)
    for line in (BUNDLE / "manifest.sha256").read_text(encoding="utf8").splitlines():
        expected, name = line.split("  ", 1)
        require(digest(BUNDLE / name) == expected, name)
    gate = run / "smoke/smoke_gate.json"
    require(digest(gate) == snapshot["smoke_sha256"] and cross.read(gate)["node"] == platform.node(), "Host changed")
    original = cross.read(old / "check.json")
    actual = cross.check_repo(repo)
    require(original["versions_match"] and not actual["versions_match"], "Unexpected original-build comparison")
    require(actual == {**original, "current_environment": snapshot["current_environment"], "versions_match": False}
            and actual["current_environment"]["platform"] == "Windows-11-10.0.26300-SP0", "Unapproved environment change")
    cores = cross.load_original_batch(repo).physical_cpus()
    require(cores == snapshot["physical_cpus"], "CPU assignment changed")
    remaining = {x["cell"] for x in snapshot["missing"]}
    completed = {r["id"] for r in cross.read(old / "batch_progress.json") if r["status"] == "COMPLETE"}
    require(completed == {p.parent.name for p in (old / "cells").glob("*/receipt.json")}, "Prior receipts changed")
    roster = cross.roster()
    rows = [r for r in roster if r["id"] in remaining]
    require(len(rows) == 10 and all(r["budget_s"] == 900 for r in rows)
            and {r["id"] for r in roster} - remaining == completed, "Missing roster changed")
    return actual, cores, rows


def child(action, repo, folder, case, cpu, budget, charge=0, method=None):
    if not folder.exists():
        args = [action, "--repo", str(repo), "--case", case, "--cpu", str(cpu)]
        if method:
            args.extend(["--method", method, "--seed", "101"])
        print(cross.utc(), action, folder.name, flush=True)
        cross.run_child(args, folder, budget, charge)
    require((folder / "receipt.json").is_file(), "Incomplete prior launch: " + str(folder))
    receipt = cross.read(folder / "receipt.json")
    require(receipt["status"] == "COMPLETE" and 0 <= charge <= receipt["charged_s"] <= budget, str(folder))
    return receipt, cross.read(folder / "result.json")


def prepare(repo, stage, report, cores, rows):
    smoke = stage / "smoke"
    ids = cross.identities()
    pool, result = child("_pool", repo, smoke / "pools/D1", "D1", cores[0], 180)
    require(result["status"] == "SAFE" and result["plan"] == ids["D1", "Q4"]["original_plan_sha256"], "Smoke Q4")
    smoke_rows = []
    for arm, method in (("C", "AB"), ("D", "Proposed")):
        folder = smoke / "cells" / f"D1_{method}_T3_101"
        receipt, result = child("_smoke", repo, folder, "D1", cores[0], 90, pool["charged_s"], method)
        require(result["status"] == "SAFE" and result["configuration_details"]["rounds"] >= 1
                and result["post"]["rounds"] >= 1 and result["elapsed_s"] <= 90
                and result["initial"]["plan"] == ids["D1", "Q4"]["original_plan_sha256"], "Smoke failed: " + method)
        smoke_rows.append(dict(arm=arm, method=method, receipt=receipt, result_sha256=digest(folder / "result.json")))
    gate = dict(status="PASS", environment=report["current_environment"], node=platform.node(),
                bundle_sha256=report["bundle_sha256"], lock_sha256=report["lock_sha256"], receipts=smoke_rows)
    cross.write(smoke / "smoke_gate.json", gate)
    formal = stage / "formal"
    (formal / "cells").mkdir(parents=True, exist_ok=True)
    pools = {}
    for ix, case in enumerate(cross.CASES):
        if any(r["case"] == case for r in rows):
            pool, result = child("_pool", repo, formal / "pools" / case, case, cores[ix % len(cores)], 180)
            require(result["status"] == "SAFE" and result["plan"] == ids[case, "Q4"]["original_plan_sha256"], case)
            pools[case] = pool
    cross.write(formal / "pool_receipts.json", pools)
    cross.write(formal / "batch_start.json", dict(roster=rows, physical_cpus=cores,
                smoke_gate_sha256=digest(smoke / "smoke_gate.json"), pool_sha256=digest(formal / "pool_receipts.json"),
                registration_sha256=digest(stage / "registration.json")))
    print("Prepared: both smoke arms passed and all formal Q4 pools were certified.", flush=True)


def next_cell(repo, stage, cores, rows):
    formal = stage / "formal"
    start = cross.read(formal / "batch_start.json")
    require(start["roster"] == rows and start["smoke_gate_sha256"] == digest(stage / "smoke/smoke_gate.json")
            and start["registration_sha256"] == digest(stage / "registration.json")
            and start["pool_sha256"] == digest(formal / "pool_receipts.json"), "Gate or roster changed")
    pools = cross.read(formal / "pool_receipts.json")
    batch = cross.load_original_batch(repo)
    eligible = {r["id"] for r in rows}
    cells = formal / "cells"
    require({p.name for p in cells.iterdir()} <= eligible, "Unexpected cell")
    receipts = []
    pending = []
    for ix, r in enumerate(cross.roster()):
        if r["id"] not in eligible:
            continue
        folder = cells / r["id"]
        if not folder.exists():
            pending.append((ix, r))
        elif (folder / "receipt.json").is_file():
            receipt = cross.read(folder / "receipt.json")
            require(all(receipt[k] == v for k, v in r.items()), r["id"])
            receipts.append(receipt)
        else:
            require((folder / "start.json").is_file() and not before_deadline(folder), "Prior launch still active")
    if pending:
        ix, r = pending[0]
        folder = cells / r["id"]
        charge = pools[r["case"]]["charged_s"]
        print(cross.utc(), "START", r["id"], flush=True)
        rec = batch.run_process("cell", r, folder, cores[(ix // 2) % len(cores)], charge, cross.PIN)
        receipts.append(rec)
        cross.write(formal / "batch_progress.json", receipts)
        require(rec["status"] == "COMPLETE", "Noncomplete receipt saved: " + r["id"])
        audit.audit_cell(folder, r["case"], r["method"], r["seed"], cross.identities()[r["case"], "Q4"],
                         audit.model_for(repo, r["case"]), expected_charge=charge)
        print(cross.utc(), "AUDITED", r["id"], flush=True)
        return True
    accepted = {r["id"] for r in receipts if r["status"] == "COMPLETE"}
    cross.write(formal / "batch_progress.json", receipts)
    if not (formal / "batch_end.json").exists():
        cross.write(formal / "batch_end.json", dict(utc=cross.utc(), outcome="FINISHED" if accepted == eligible else "INCOMPLETE",
                    registered=len(rows), completed=len(accepted), missing=sorted(eligible - accepted), receipts=receipts))
    print("BATCH_CLOSED", len(accepted), "/", len(rows), flush=True)
    return False


def run_step(action, repo, run):
    with claim(run):
        report, cores, rows = verify(repo, run)
        stage = run / STAGE
        registration = dict(source_commit=SUBJECT, source_audit_sha256=CHECKPOINT_SHA, roster=rows,
                            method_budget_s=9000, launches_per_position=1, environment=report["current_environment"],
                            original_versions_match=report["versions_match"], physical_cpus=cores,
                            launcher_sha256=digest(Path(__file__)))
        if action == "prepare" and not (stage / "registration.json").exists():
            stage.mkdir(exist_ok=True)
            cross.write(stage / "check.json", report)
            cross.write(stage / "registration.json", registration)
        require(cross.read(stage / "registration.json") == registration and cross.read(stage / "check.json") == report,
                "Stage registration differs")
        if action == "prepare":
            prepare(repo, stage, report, cores, rows)
            return False
        return next_cell(repo, stage, cores, rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "one", "remaining"))
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    a = parser.parse_args()
    while run_step(a.action, a.repo.resolve(), a.run.resolve()) and a.action == "remaining":
        pass
