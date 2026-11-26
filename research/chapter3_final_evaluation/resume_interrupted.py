"""Reconcile the November 26 interruption and execute only the authorized missing cells."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import gzip
import hashlib
from importlib.metadata import version
from pathlib import Path
import platform
from queue import Queue
import sys
from threading import Event

from formal_batch import OUT, ROOT, physical_cpus, read, roster, run_process, sha, utc, write


PARTIAL = {
    "D1_SA_T3_101", "D1_AB_T3_101", "D1_Compact_T3_101",
    "D1_Proposed_T0_101", "D1_Proposed_T1_101", "D1_Proposed_T3_101",
}
CELLS = OUT / "cells"
HISTORY = OUT / "interruption_01"


def inventory(folder):
    return {p.relative_to(folder).as_posix(): sha(p)
            for p in sorted(folder.rglob("*")) if p.is_file()}


def inspect_batch():
    import formal_worker  # load the frozen worker's exact native libraries before opening any cell
    from setup_inputs import g1io

    lock = read(ROOT / "execution_lock.json")
    start = read(OUT / "batch_start.json")
    subject = read(ROOT / "publication_freeze.json")["remote_protocol_commit"]
    if ((OUT / "batch_end.json").exists() or HISTORY.exists()
            or start["subject"] != subject or start["protocol_sha256"] != sha(ROOT / "execution_lock.json")
            or lock["roster"] != roster() or start["cores"] != physical_cpus()):
        raise ValueError("The original batch or continuation state has changed")
    checks = [(ROOT / n, h) for n, h in lock["files"].items()]
    upstream = read(ROOT.parent / "global_config_coordination_g1" / "input_lock.json")
    checks.extend((g1io.runtime / n, h) for n, h in upstream["solver_runtime_files"])
    if any(sha(p) != h for p, h in checks):
        raise ValueError("Frozen source or solver digest mismatch")
    env = lock["environment"]
    if (sys.version != env["python"] or platform.platform() != env["platform"]
            or any(version(k) != v for k, v in env["packages"].items())):
        raise ValueError("Runtime differs from the formal batch")

    pool_receipts = {}
    pool_files = {}
    for case in sorted({job["case"] for job in lock["roster"]}):
        folder = OUT / "pools" / case
        receipt = read(folder / "receipt.json")
        keys = {item["plan"] for item in read(folder / "pool.json") if item.get("plan") and item["in_time"]}
        if (receipt["case"] != case or receipt["subject"] != subject or receipt["status"] != "COMPLETE"
                or not keys or len(keys) != read(folder / "result.json")["distinct"]):
            raise ValueError(f"Invalid original pool: {case}")
        for key in keys:
            raw = gzip.decompress((folder / "evidence" / "plans" / (key + ".json.gz")).read_bytes())
            if hashlib.sha256(raw).hexdigest() != key:
                raise ValueError(f"Pool plan digest mismatch: {case}")
        pool_receipts[case] = receipt
        pool_files[case] = inventory(folder)

    completed, partial, pending = {}, {}, []
    for job in lock["roster"]:
        name = job["id"]
        folder = CELLS / name
        if (folder / "receipt.json").is_file():
            receipt = read(folder / "receipt.json")
            if (receipt["status"] != "COMPLETE" or receipt["subject"] != subject
                    or any(receipt[k] != v for k, v in job.items()) or not (folder / "result.json").is_file()):
                raise ValueError(f"Unexpected original receipt: {name}")
            completed[name] = sha(folder / "receipt.json")
            continue
        pending.append(job)
        if folder.exists():
            opened = read(folder / "start.json")
            if (name not in PARTIAL or opened["subject"] != subject or any(opened[k] != v for k, v in job.items())
                    or (folder / "result.json").exists()):
                raise ValueError(f"Unexpected unfinished cell: {name}")
            elapsed = [read(folder / "progress.json").get("elapsed_s", 0)]
            import json
            for line in (folder / "rounds.jsonl").read_bytes().splitlines():
                elapsed.append(json.loads(line).get("elapsed_s", 0))
            partial[name] = dict(files=inventory(folder), status="INTERRUPTED", final=None,
                                 actual_charged_s=None, last_observed_charged_s=max(elapsed),
                                 budget_s=job["budget_s"], prior_charge_s=opened["prior_charge_s"])

    if set(partial) != PARTIAL or len(completed) != 61 or len(pending) != 104:
        raise ValueError("The on-disk attempts differ from the authorized recovery")
    return start, completed, partial, pending, pool_receipts, pool_files


def resume(check_only):
    start, completed, partial, pending, pools, pool_files = inspect_batch()
    print(f"Verified {len(completed)} sealed cells, {len(partial)} interrupted, {len(pending)-len(partial)} unopened", flush=True)
    if check_only:
        return
    HISTORY.mkdir()  # exclusive claim; a second parent cannot launch the same roster
    originals = HISTORY / "original_cells"
    originals.mkdir()
    write(HISTORY / "before.json", dict(utc=utc(), subject=start["subject"], completed_receipt_sha256=completed,
          original_progress=read(OUT / "batch_progress.json"), original_pool_digests=pool_files, interrupted=partial,
          pending=[r["id"] for r in pending], supervisor_sha256=sha(Path(__file__)),
          reason="User authorized one fresh timed attempt for each of six interrupted cells and the 98 unopened cells.",
          selection="Every missing endpoint; no first-attempt candidate may seed a replacement."))
    for name in sorted(partial):
        source = (CELLS / name).resolve()
        target = (originals / name).resolve()
        if source.parent != CELLS.resolve() or target.parent != originals.resolve() or target.exists():
            raise ValueError(f"Invalid original evidence path: {name}")
        source.rename(target)
        if inventory(target) != partial[name]["files"]:
            raise ValueError(f"Archived attempt digest mismatch: {name}")
    slots = Queue()
    for cpu in start["cores"]:
        slots.put(cpu)
    stop = Event()

    def launch(row):
        cpu = slots.get()
        try:
            if stop.is_set():
                return None
            receipt = run_process("cell", row, CELLS / row["id"], cpu, pools[row["case"]]["charged_s"], start["subject"])
            if receipt["status"] == "ERROR":
                stop.set()
            return receipt
        except BaseException:
            stop.set()
            raise
        finally:
            slots.put(cpu)

    statuses = Counter(COMPLETE=len(completed))
    with ThreadPoolExecutor(max_workers=len(start["cores"])) as workers:
        futures = [workers.submit(launch, row) for row in pending]
        for future in as_completed(futures):
            receipt = future.result()
            if receipt is not None:
                statuses[receipt["status"]] += 1
                write(OUT / "batch_progress.json", dict(at=utc(), outcomes=dict(statuses), total=165))
                print(utc(), receipt["id"], receipt["status"], sum(statuses.values()), flush=True)
    if sum(statuses.values()) != 165:
        raise RuntimeError("Worker error stopped the remaining queue; inspect the first error receipt")
    if any(sha(CELLS / name / "receipt.json") != digest for name, digest in completed.items()):
        raise ValueError("An original completed receipt changed")
    write(OUT / "batch_end.json", dict(utc=utc(), outcome="FINISHED", outcomes=dict(statuses), original_finished=61,
          originally_interrupted=sorted(partial), retries=6, first_attempts_after_resume=98,
          physical_attempts_including_interrupted=171))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    resume(parser.parse_args().check)
