"""Continue v5 cells with the original parent, worker, Q4 pools and budget."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sys

HERE = Path(__file__).resolve().parent
BUNDLE = HERE.parent / "chapter4_cross_analysis_v5"
sys.path.insert(0, str(BUNDLE))
import analyze_cross as audit
import run_cross as cross


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root):
    return {p.relative_to(root).as_posix(): digest(p) for p in sorted(root.rglob("*")) if p.is_file()}


def require(ok, detail):
    if not ok:
        raise ValueError(detail)


def main(repo, run, after_continuation_02=False, retry_interrupted=False):
    require(not retry_interrupted or after_continuation_02, "retry mode requires both interruption records")
    repo, run = repo.resolve(), run.resolve()
    old = run / "restart_01/formal"
    dest = run / ("continuation_03" if after_continuation_02 else "continuation_02")
    formal = dest / "formal"
    gate_path = run / "smoke/smoke_gate.json"
    freeze = cross.read(HERE / "freeze.json")
    for line in (BUNDLE / "manifest.sha256").read_text(encoding="utf8").splitlines():
        expected, name = line.split("  ", 1)
        require(digest(BUNDLE / name) == expected, name)
    require(digest(BUNDLE / "manifest.sha256") == freeze["bundle_manifest_sha256"], "bundle manifest")
    check = cross.check_repo(repo)
    start = cross.read(old / "batch_start.json")
    gate = cross.read(gate_path)
    require(check["versions_match"] and check == cross.read(old / "check.json"), "environment changed")
    require(gate["node"] == platform.node() and gate["status"] == "PASS" and
            gate["environment"] == check["current_environment"] and
            digest(gate_path) == start["smoke_gate_sha256"] == freeze["smoke_gate_sha256"], "original smoke gate")
    batch = cross.load_original_batch(repo)
    cpus = batch.physical_cpus()
    rows = cross.roster()
    require(start["roster"] == rows and cpus == start["physical_cpus"], "registered roster or cores")
    complete, partial = [row["id"] for row in rows[:2]]
    require(sorted(p.name for p in (old / "cells").iterdir()) == sorted([complete, partial]), "old roster advanced")
    require(not (old / "batch_end.json").exists() and not (old / "cells" / partial / "receipt.json").exists(),
            "interruption state changed")
    pools = cross.read(old / "pool_receipts.json")
    ids = cross.identities()
    for case in cross.CASES:
        folder = old / "pools" / case
        result = cross.read(folder / "result.json")
        choices = cross.read(folder / "pool.json")
        require(pools[case] == cross.read(folder / "receipt.json") and pools[case]["status"] == "COMPLETE" and
                result["status"] == "SAFE" and result["plan"] == ids[case, "Q4"]["original_plan_sha256"] and
                len(choices) == 1 and choices[0]["plan"] == result["plan"] and choices[0]["in_time"],
                "Q4 evidence " + case)
    saved = cross.read(old / "cells" / complete / "receipt.json")
    require(cross.read(old / "batch_progress.json") == [saved], "reused receipt")
    audit.audit_cell(old / "cells" / complete, "D1", "AB", 101, ids["D1", "Q4"], audit.model_for(repo, "D1"),
                     expected_charge=pools["D1"]["charged_s"])
    first_unopened = 2
    prior_runs = [old]
    interrupted = {partial: old / "cells" / partial}
    if after_continuation_02:
        previous = run / "continuation_02/formal"
        second = rows[2]["id"]
        require(sorted(p.name for p in (previous / "cells").iterdir()) == sorted([complete, second]),
                "continuation_02 advanced; inspect receipts")
        require(cross.read(previous / "batch_progress.json") == [saved] and
                not (previous / "batch_end.json").exists(), "continuation_02 closure changed")
        previous_cell = previous / "cells" / second
        opened = cross.read(previous_cell / "start.json")
        require(all(opened[k] == v for k, v in rows[2].items()) and opened["subject"] == cross.PIN and
                not (previous_cell / "receipt.json").exists() and not (previous_cell / "result.json").exists(),
                "second interruption identity changed")
        interrupted[second] = previous_cell
        first_unopened = 3
        prior_runs.append(previous)
    remaining = rows[1:] if retry_interrupted else rows[first_unopened:]
    retries = set(interrupted) if retry_interrupted else set()
    require(not formal.is_relative_to(repo) and not formal.is_relative_to(BUNDLE), "destination")
    dest.mkdir(exist_ok=False)
    formal.mkdir()
    (formal / "cells").mkdir()
    copied = {}
    for name in ("pools", "cells/" + complete):
        original, target = old / name, formal / name
        copied[name] = inventory(original)
        shutil.copytree(original, target)
        require(inventory(target) == copied[name], "copy differs: " + name)
    for name in ("check.json", "pool_receipts.json", "batch_start.json"):
        shutil.copyfile(old / name, formal / name)
        require(digest(old / name) == digest(formal / name), "copy differs: " + name)
    cross.write(dest / "continuation.json", dict(created=cross.utc(), original=str(old), runner_sha256=digest(Path(__file__)),
        original_freeze_sha256=digest(HERE / "freeze.json"), reused=complete, copied=copied,
        prior_attempts={name: dict(folder=str(folder), files=inventory(folder)) for name, folder in interrupted.items()},
        retry_budget_s=sum(row["budget_s"] for row in remaining if row["id"] in retries),
        retry_ids=sorted(retries), new_cells=rows[first_unopened:], execution_order=[row["id"] for row in remaining],
        max_new_method_s=sum(row["budget_s"] for row in remaining), supervisor_pid=os.getpid(),
        policy="One attempt per listed cell, starting from Q4 with its original charge and paired CPU allocation."))
    records = [saved]
    cross.write(formal / "batch_progress.json", records)
    for index, row in enumerate(rows):
        if row not in remaining:
            continue
        prior_cells = {prior / "cells" / row["id"] for prior in prior_runs if (prior / "cells" / row["id"]).exists()}
        expected_prior = {interrupted[row["id"]]} if row["id"] in retries else set()
        require(prior_cells == expected_prior and all(not (p / "receipt.json").exists() for p in prior_cells),
                "prior attempt status changed: " + row["id"])
        cpu = cpus[(index // 2) % len(cpus)]
        print(cross.utc(), "START", row["id"], flush=True)
        receipt = batch.run_process("cell", row, formal / "cells" / row["id"], cpu, pools[row["case"]]["charged_s"], cross.PIN)
        records.append(receipt)
        cross.write(formal / "batch_progress.json", records)
        print(cross.utc(), receipt["status"], row["id"], flush=True)
        require(receipt["status"] == "COMPLETE", "cell failed; retain evidence: " + row["id"])
    missing = [row["id"] for row in rows if row["id"] not in {r["id"] for r in records}]
    cross.write(formal / "batch_end.json", dict(outcome="INCOMPLETE_INTERRUPTED_CELL" if missing else "FINISHED",
        utc=cross.utc(), completed_receipts=len(records), registered=len(rows), receipts=records, missing=missing))
    from types import SimpleNamespace
    analysis = dest / ("analysis_partial" if missing else "analysis")
    audit.main(SimpleNamespace(repo=repo, run=formal, out=analysis, ab_root=None))
    if not missing:
        result = cross.read(analysis / "audit.json")
        require((result["outcome"], result["audited_CD"], result["audited_AB_raw"], result["complete_pairs"]) ==
                ("PASS", 24, 24, 12), "formal audit incomplete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--after-continuation-02", action="store_true",
                        help="Skip the interrupted D1 C/102 as well as D1 D/101; start at D1 D/102.")
    parser.add_argument("--retry-interrupted", action="store_true",
                        help="Also retry D1 D/101 and C/102 once, starting fresh at Q4 under 900 s each.")
    args = parser.parse_args()
    main(args.repo, args.run, args.after_continuation_02, args.retry_interrupted)
