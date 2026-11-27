"""Complete interrupted, receiptless 26300 positions once after the registered batch closes."""
import argparse
from pathlib import Path
import tempfile

from pending_cells import before_deadline, claim, copy_evidence, inventory
from windows_26300 import STAGE, audit, cross, digest, require, verify


RECOVERY = "windows_26300_recovery"


def recovery_manifest(run):
    source = run / STAGE / "formal"
    start = cross.read(source / "batch_start.json")
    end = cross.read(source / "batch_end.json")
    rows = start["roster"]
    cells = source / "cells"
    require({p.name for p in cells.iterdir()} == {r["id"] for r in rows}, "Source roster incomplete")
    receipts = {p.parent.name: cross.read(p) for p in cells.glob("*/receipt.json")}
    require({r["id"]: r for r in end["receipts"]} == receipts, "Closed receipts differ")
    complete = {key for key, r in receipts.items() if r["status"] == "COMPLETE"}
    require(end["completed"] == len(complete) and set(end["missing"]) == {r["id"] for r in rows} - complete,
            "Closed endpoints differ")
    eligible = []
    interrupted = {}
    for row in rows:
        key = row["id"]
        folder = cells / key
        if key in receipts or (folder / "result.json").exists():
            continue
        launch = cross.read(folder / "start.json")
        require(all(launch[k] == v for k, v in row.items()) and not before_deadline(folder),
                "Prior launch identity or deadline")
        eligible.append(row)
        interrupted[key] = inventory(folder)
    cases = sorted({row["case"] for row in eligible})
    return dict(source=STAGE, registration_sha256=digest(source.parent / "registration.json"),
                closure_sha256=digest(source / "batch_end.json"), pool_receipts_sha256=digest(source / "pool_receipts.json"),
                worker_subject=cross.PIN, recovery_code_sha256=digest(Path(__file__)), roster=eligible,
                eligible_rule="Original 26300 launch past deadline, without receipt or result, once per position",
                method_budget_s=sum(row["budget_s"] for row in eligible), prior_evidence=interrupted,
                pools={case: inventory(source / "pools" / case) for case in cases})


def validate_recovery(run):
    root = run / RECOVERY
    reg = cross.read(root / "registration.json")
    require(reg == recovery_manifest(run), "Recovery registration or prior evidence changed")
    src = run / STAGE / "formal"
    formal = root / "formal"
    require(digest(formal / "pool_receipts.json") == digest(src / "pool_receipts.json"), "Pool charges changed")
    for case, hashes in reg["pools"].items():
        require(inventory(formal / "pools" / case) == hashes, "Recovery pool differs: " + case)
    return formal, reg


def verified_receipts(formal, reg):
    eligible = {row["id"]: row for row in reg["roster"]}
    folders = {p.name for p in (formal / "cells").iterdir()}
    require(folders <= eligible.keys(), "Unregistered recovery folder")
    receipts = []
    for key in sorted(folders):
        folder = formal / "cells" / key
        require(all(cross.read(folder / "start.json")[k] == v for k, v in eligible[key].items()), key)
        if (folder / "receipt.json").exists():
            receipt = cross.read(folder / "receipt.json")
            require(all(receipt[k] == v for k, v in eligible[key].items()), key)
            receipts.append(receipt)
    return receipts


def execute(repo, run):
    with claim(run):
        actual, cores, rows = verify(repo, run)
        stage = run / STAGE
        require(actual == cross.read(stage / "check.json") and rows == cross.read(stage / "registration.json")["roster"],
                "Source registration or environment differs")
        src = stage / "formal"
        pools = cross.read(src / "pool_receipts.json")
        target = run / RECOVERY
        if not target.exists():
            reg = recovery_manifest(run)
            if not reg["roster"]:
                return
            with tempfile.TemporaryDirectory(dir=run) as tmp:
                new = Path(tmp) / "prepared"
                (new / "formal/cells").mkdir(parents=True)
                (new / "formal/pools").mkdir()
                import shutil
                shutil.copyfile(src / "pool_receipts.json", new / "formal/pool_receipts.json")
                for case in reg["pools"]:
                    copy_evidence(src / "pools" / case, new / "formal/pools" / case)
                cross.write(new / "registration.json", reg)
                new.rename(target)
        formal, reg = validate_recovery(run)
        if (formal / "batch_end.json").exists():
            return
        batch = cross.load_original_batch(repo)
        chosen = {r["id"] for r in reg["roster"]}
        for ix, row in enumerate(cross.roster()):
            key, case = row["id"], row["case"]
            if key not in chosen:
                continue
            folder = formal / "cells" / key
            if folder.exists():
                require((folder / "receipt.json").exists() or not before_deadline(folder), "Recovery still active")
                continue
            charge = pools[case]["charged_s"]
            print(cross.utc(), "RECOVERY START", key, flush=True)
            rec = batch.run_process("cell", row, folder, cores[(ix // 2) % len(cores)], charge, cross.PIN)
            if rec["status"] == "COMPLETE":
                audit.audit_cell(folder, case, row["method"], row["seed"], cross.identities()[case, "Q4"],
                                 audit.model_for(repo, case), expected_charge=charge)
            print(cross.utc(), key, rec["status"], flush=True)
        receipts = verified_receipts(formal, reg)
        complete = {r["id"] for r in receipts if r["status"] == "COMPLETE"}
        cross.write(formal / "batch_end.json", dict(utc=cross.utc(), receipts=receipts,
                    registered=len(chosen), completed=len(complete), missing=sorted(chosen - complete)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("repo", "run"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    execute(args.repo.resolve(), args.run.resolve())
