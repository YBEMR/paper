"""Monitor one authorized full restart of the frozen C/D runner and its offline audit."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic
import traceback


HERE = Path(__file__).resolve().parent
BUNDLE = HERE.parent / "chapter4_cross_analysis_v5"


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def write(path, data):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")
    temp.replace(path)


def snapshot(formal):
    progress = formal / "batch_progress.json"
    receipts = read(progress) if progress.exists() else []
    completed = {r["id"] for r in receipts}
    active = []
    for start in sorted((formal / "cells").glob("*/start.json")):
        folder = start.parent
        if folder.name not in completed:
            log = folder / "rounds.jsonl"
            active.append(dict(cell=folder.name, log_bytes=log.stat().st_size if log.exists() else 0))
    return dict(completed=len(completed), active=active)


def observed_process(stage, args, dest, formal):
    path = dest / (stage + "_process.json")
    with (dest / (stage + "_console.log")).open("xb") as log:
        launch = utc()
        begin = monotonic()
        process = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT)
        state = dict(stage=stage, started=launch, observer_pid=os.getpid(), child_pid=process.pid)
        write(path, state)
        print(launch, stage, "started", process.pid, flush=True)
        while True:
            try:
                code = process.wait(timeout=25)
                break
            except subprocess.TimeoutExpired:
                beat = dict(**state, at=utc(), elapsed_s=round(monotonic()-begin, 3))
                try:
                    beat.update(snapshot(formal))
                except (OSError, ValueError) as exc:
                    beat["observation_error"] = str(exc)
                write(dest / "heartbeat.json", beat)
                print(beat["at"], stage, beat.get("completed"), beat.get("active"), flush=True)
        state.update(ended=utc(), wall_s=monotonic()-begin, returncode=code)
        write(path, state)
        print(state["ended"], stage, "exit", code, flush=True)
        if code:
            raise subprocess.CalledProcessError(code, args)


def restart(repo, previous):
    repo, previous = repo.resolve(), previous.resolve()
    history_file = previous / "interruption_review_01.json"
    lost = read(history_file)
    if (lost["status"],lost["completed_formal_cells"],lost["interrupted_cells"],lost["unopened_cells"]) != (
        "INTERRUPTED_WITHOUT_RECEIPT",0,1,23):
        raise RuntimeError("Original run state differs from the authorized restart")
    if any(sha(previous / name) != digest for name, digest in lost["sha256"].items()):
        raise RuntimeError("The original attempt has changed")
    original = previous / "formal"
    opened = [d.name for d in (original / "cells").iterdir()]
    if opened != [lost["job"]] or (original / "cells" / lost["job"] / "receipt.json").exists() or (original / "batch_end.json").exists():
        raise RuntimeError("The previous batch has new evidence")
    gate = previous / "smoke" / "smoke_gate.json"
    freeze = read(HERE / "freeze.json")
    if read(gate)["status"] != "PASS" or sha(gate) != freeze["smoke_gate_sha256"]:
        raise RuntimeError("Smoke gate no longer matches the frozen execution")
    for line in (BUNDLE / "manifest.sha256").read_text(encoding="utf8").splitlines():
        digest, name = line.split("  ", 1)
        if sha(BUNDLE / name) != digest:
            raise RuntimeError(f"Bundle file changed: {name}")
    dest = previous / "restart_01"
    dest.mkdir(exist_ok=False)
    formal, analysis = dest / "formal", dest / "analysis"
    prefix = [sys.executable, "-B", "-u"]
    policy = dict(created=utc(), interrupted_job=lost["job"], prior_charged_lower_s=lost["last_logged_charged_s"],
                  prior_actual_charged_s=None, prior_evidence_sha256=sha(history_file), wrapper_sha256=sha(Path(__file__)),
                  original_freeze_sha256=sha(HERE / "freeze.json"), smoke_gate_sha256=sha(gate),
                  registered_cells=24, second_attempts=1, first_attempts=23, per_cell_budget_s=900,
                  execution="Frozen execute entry point, fresh Q4 pools, serial C/D, and no warm start from the interrupted search.")
    write(dest / "restart_record.json", policy)
    try:
        observed_process("formal", prefix + [str(BUNDLE / "formal_runner" / "run_cross.py"), "execute",
            "--repo", str(repo), "--out", str(formal), "--smoke-gate", str(gate), "--confirm-original-environment"], dest, formal)
        end = read(formal / "batch_end.json")
        if end["outcome"] != "FINISHED" or end["completed_receipts"] != 24:
            raise RuntimeError(f"Formal closure: {end['outcome']}, {end['completed_receipts']}/24")
        observed_process("analysis", prefix + [str(BUNDLE / "analyze_cross.py"), "--repo", str(repo),
            "--run", str(formal), "--out", str(analysis)], dest, formal)
        audit = read(analysis / "audit.json")
        if (audit["outcome"],audit["audited_CD"],audit["audited_AB_raw"],audit["complete_pairs"]) != ("PASS",24,24,12):
            raise RuntimeError(f"Incomplete audit: {audit}")
    except BaseException:
        write(dest / "observer_end.json", dict(utc=utc(), outcome="ERROR_OR_INTERRUPTION", detail=traceback.format_exc()))
        raise
    write(dest / "observer_end.json", dict(utc=utc(), outcome="PASS", audit=audit))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--previous", type=Path, required=True)
    args = parser.parse_args()
    restart(args.repo, args.previous)
