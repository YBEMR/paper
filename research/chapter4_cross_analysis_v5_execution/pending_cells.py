"""Claim one pending v5 cell at a time on the original host and merge only completed receipts."""
import argparse
import json
import msvcrt
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import shutil
import tempfile
from time import sleep
from types import SimpleNamespace

from continue_unopened import audit, cross, digest, inventory, require, BUNDLE, HERE


class ActiveSupervisor(Exception):
    pass


def copy_evidence(src, dest):
    shutil.copytree(src, dest)
    require(inventory(src) == inventory(dest), f"Evidence copy differs: {src}")


def before_deadline(folder):
    launch = cross.read(folder / "start.json")
    elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(launch["utc"])).total_seconds()
    return elapsed < launch["budget_s"] - launch["prior_charge_s"] + 10


@contextmanager
def claim(run):
    path = run / "continuation_04.lock"
    with path.open("a+b") as f:
        if f.tell() == 0:
            f.write(b"0")
            f.flush()
        f.seek(0)
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        except PermissionError as exc:
            raise ActiveSupervisor("Another supervisor holds the cell lock") from exc
        try:
            yield
        finally:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)


def initialize(repo, run, retry):
    old = run / "continuation_03/formal"
    target = run / "continuation_04"
    check = cross.check_repo(repo)
    start = cross.read(old / "batch_start.json")
    require(check == cross.read(old / "check.json") and check["versions_match"], "Environment differs")
    require(start["roster"] == cross.roster(), "Roster differs")
    gate = cross.read(run / "smoke/smoke_gate.json")
    import platform
    require(gate["status"] == "PASS" and gate["node"] == platform.node() and
            gate["environment"] == check["current_environment"] and
            start["smoke_gate_sha256"] == digest(run / "smoke/smoke_gate.json") ==
            cross.read(HERE / "freeze.json")["smoke_gate_sha256"], "Original smoke identity differs")
    for line in (BUNDLE / "manifest.sha256").read_text(encoding="utf8").splitlines():
        expected, name = line.split("  ", 1)
        require(digest(BUNDLE / name) == expected, name)
    receipts = cross.read(old / "batch_progress.json")
    completed = {r["id"] for r in receipts}
    rows = cross.roster()
    require([r["id"] for r in rows[:4]] == [r["id"] for r in receipts], "Prior progress changed")
    interrupted = rows[4]["id"]
    partial = old / "cells" / interrupted
    require({p.name for p in (old / "cells").iterdir()} == completed | {interrupted}, "Prior supervisor advanced")
    require(not (old / "batch_end.json").exists() and not (partial / "receipt.json").exists() and
            not (partial / "result.json").exists() and not before_deadline(partial), "Cell not confirmed interrupted")
    pools = cross.read(old / "pool_receipts.json")
    ids = cross.identities()
    for case, receipt in pools.items():
        path = old / "pools" / case
        initial = cross.read(path / "result.json")
        require(receipt == cross.read(path / "receipt.json") and receipt["status"] == "COMPLETE" and
                initial["status"] == "SAFE" and initial["plan"] == ids[case, "Q4"]["original_plan_sha256"], case)
    require(set(pools) == set(cross.CASES), "Incomplete pool inventory")
    for r in receipts:
        path = old / "cells" / r["id"]
        require(cross.read(path / "receipt.json") == r, "Saved receipt differs")
        audit.audit_cell(path, r["case"], r["method"], r["seed"], ids[r["case"], "Q4"],
                         audit.model_for(repo, r["case"]), expected_charge=pools[r["case"]]["charged_s"])
    eligible = [r["id"] for r in rows if r["id"] not in completed and (r["id"] != interrupted or retry)]
    with tempfile.TemporaryDirectory(prefix="ch4-prepare-", dir=run) as temp:
        stage = Path(temp) / "ready"
        formal = stage / "formal"
        (formal / "cells").mkdir(parents=True)
        for name in ("check.json", "batch_start.json", "pool_receipts.json", "batch_progress.json"):
            shutil.copyfile(old / name, formal / name)
        copy_evidence(old / "pools", formal / "pools")
        for key in completed:
            copy_evidence(old / "cells" / key, formal / "cells" / key)
        cross.write(stage / "control.json", dict(created=cross.utc(), source=str(old), source_progress_sha256=digest(old / "batch_progress.json"),
                    source_opened=sorted(completed | {interrupted}), partial_cell=interrupted, evidence=inventory(partial),
                    reused=sorted(completed), eligible=eligible, allowed_retry=[interrupted] if retry else [],
                    method_budget_s=900 * len(eligible), code_sha256=digest(Path(__file__))))
        stage.rename(target)


def one(repo, run, retry=False):
    with claim(run):
        dest = run / "continuation_04"
        if not dest.exists():
            initialize(repo, run, retry)
        ctl = cross.read(dest / "control.json")
        require(ctl["code_sha256"] == digest(Path(__file__)), "Continuation code drift")
        source = Path(ctl["source"])
        require(ctl["source_progress_sha256"] == digest(source / "batch_progress.json") and
                ctl["source_opened"] == sorted(p.name for p in (source / "cells").iterdir()) and
                not (source / "cells" / ctl["partial_cell"] / "receipt.json").exists(), "Old supervisor advanced")
        formal = dest / "formal"
        extra = dest / "additional_retry.json"
        if retry and not ctl["allowed_retry"] and not extra.exists():
            require(not (formal / "batch_end.json").exists(), "Closed batch requires a separate supplement")
            cross.write(extra, dict(cell=ctl["partial_cell"], budget_s=900, created=cross.utc(),
                                    control_sha256=digest(dest / "control.json")))
        eligible = set(ctl["eligible"])
        if extra.exists():
            permitted = cross.read(extra)
            require(permitted["cell"] == ctl["partial_cell"] and permitted["budget_s"] == 900 and
                    permitted["control_sha256"] == digest(dest / "control.json"), "Supplemental budget mismatch")
            eligible.add(permitted["cell"])
        check = cross.check_repo(repo)
        require(check == cross.read(formal / "check.json") and check["versions_match"], "Environment differs")
        batch = cross.load_original_batch(repo)
        cpus = batch.physical_cpus()
        require(cpus == cross.read(formal / "batch_start.json")["physical_cpus"], "Core allocation changed")
        rows = cross.roster()
        cells = formal / "cells"
        all_receipts = []
        for r in rows:
            folder = cells / r["id"]
            if not folder.exists():
                continue
            receipt = folder / "receipt.json"
            if receipt.exists():
                recorded = cross.read(receipt)
                require(all(recorded[k] == v for k, v in r.items()), "Receipt identity changed")
                all_receipts.append(recorded)
            else:
                require((folder / "start.json").is_file() and not before_deadline(folder),
                        "A prior launch is still inside its budget or lacks a start record")
        cross.write(formal / "batch_progress.json", all_receipts)
        remaining = [(i, r) for i, r in enumerate(rows) if r["id"] in eligible and not (cells / r["id"]).exists()]
        if remaining:
            i, r = remaining[0]
            cpu = cpus[(i // 2) % len(cpus)]
            charge = cross.read(formal / "pool_receipts.json")[r["case"]]["charged_s"]
            print(cross.utc(), "START", r["id"], flush=True)
            receipt = batch.run_process("cell", r, cells / r["id"], cpu, charge, cross.PIN)
            all_receipts.append(receipt)
            cross.write(formal / "batch_progress.json", all_receipts)
            print(cross.utc(), receipt["status"], r["id"], flush=True)
            require(receipt["status"] == "COMPLETE", "Failed attempt preserved")
            return True
        if not (formal / "batch_end.json").exists():
            accepted = {r["id"] for r in all_receipts if r["status"] == "COMPLETE"}
            missing = [r["id"] for r in rows if r["id"] not in accepted]
            cross.write(formal / "batch_end.json", dict(utc=cross.utc(), outcome="FINISHED" if not missing else "INCOMPLETE",
                        completed_receipts=len(all_receipts), registered=len(rows), receipts=all_receipts, missing=missing))
        if not (dest / "analysis").exists():
            with tempfile.TemporaryDirectory(dir=dest) as temp:
                staging = Path(temp) / "analysis"
                audit.main(SimpleNamespace(repo=repo, run=formal, out=staging, ab_root=None))
                staging.rename(dest / "analysis")
        print(json.dumps(cross.read(dest / "analysis/audit.json")), flush=True)
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--loop", action="store_true", help="Run all eligible positions serially in this local console.")
    parser.add_argument("--retry-d1-c103", action="store_true", help="Include one additional full retry of interrupted D1 C/103.")
    args = parser.parse_args()
    while True:
        try:
            progressed = one(args.repo.resolve(), args.run.resolve(), args.retry_d1_c103)
        except ActiveSupervisor as exc:
            print(exc, flush=True)
            if not args.loop:
                raise SystemExit(75)
            sleep(25)
            continue
        if not progressed or not args.loop:
            break
