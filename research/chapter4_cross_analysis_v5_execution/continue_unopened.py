"""Continue the 22 never-opened v5 cells using the frozen parent, worker and original pool charges."""
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


def main(repo, run):
    repo, run = repo.resolve(), run.resolve()
    old = run / "restart_01/formal"
    dest = run / "continuation_02"
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
    old_partial = inventory(old / "cells" / partial)
    cross.write(dest / "continuation.json", dict(created=cross.utc(), original=str(old), runner_sha256=digest(Path(__file__)),
        original_freeze_sha256=digest(HERE / "freeze.json"), reused=complete, copied=copied,
        interrupted=partial, interrupted_files=old_partial, retry_budget_s=0, new_cells=rows[2:],
        max_new_method_s=22 * 900, supervisor_pid=os.getpid(), policy="First attempts only; preserved original pool charges and paired CPU allocation."))
    records = [saved]
    cross.write(formal / "batch_progress.json", records)
    for index, row in enumerate(rows[2:], 2):
        require(not (old / "cells" / row["id"]).exists(), "another original attempt opened")
        cpu = cpus[(index // 2) % len(cpus)]
        print(cross.utc(), "START", row["id"], flush=True)
        receipt = batch.run_process("cell", row, formal / "cells" / row["id"], cpu, pools[row["case"]]["charged_s"], cross.PIN)
        records.append(receipt)
        cross.write(formal / "batch_progress.json", records)
        print(cross.utc(), receipt["status"], row["id"], flush=True)
        require(receipt["status"] == "COMPLETE", "cell failed; retain evidence: " + row["id"])
    cross.write(formal / "batch_end.json", dict(outcome="INCOMPLETE_INTERRUPTED_CELL", utc=cross.utc(),
        completed_receipts=len(records), registered=len(rows), receipts=records, missing=[partial]))
    from types import SimpleNamespace
    audit.main(SimpleNamespace(repo=repo, run=formal, out=dest / "analysis_partial", ab_root=None))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    main(args.repo, args.run)
