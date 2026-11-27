"""Inventory M1-j evidence in place. No search, write, SQLite connection or process control."""
import argparse
import csv
import gzip
import json
import os
from collections import Counter
from pathlib import Path


def local_workers(root):
    proc = Path("/proc")
    if not (proc / "self/cmdline").is_file():
        return None
    workers = []
    for pid in proc.iterdir():
        if not pid.name.isdigit():
            continue
        try:
            args = [os.fsdecode(a) for a in (pid / "cmdline").read_bytes().split(b"\0") if a]
            for i, arg in enumerate(args[1:], 1):
                if Path(arg).name != "batch_j.py":
                    continue
                source = Path(arg)
                if not source.is_absolute():
                    source = (pid / "cwd").resolve() / source
                if source.resolve() == root / "batch_j.py":
                    lane = args[args.index("--lane") + 1] if "--lane" in args[i + 1:] else None
                    workers.append({"pid": int(pid.name), "lane": lane})
                    break
        except (FileNotFoundError, PermissionError, ProcessLookupError, IndexError):
            pass
    return sorted(workers, key=lambda w: w["pid"])


def read_receipt(path, slot):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as stream:
        raw = stream.read()
    run = json.loads(raw)
    if (run["case"], run["method"], run["budget_s"]) != (slot["case"], slot["method"], 60):
        raise ValueError("case/method/budget mismatch")
    records = run["records"]
    if not isinstance(records, list) or not run["stop"] or run["wall_s"] < 0:
        raise ValueError("missing stop, time or records")
    for record in records:
        if not record["cert"]["metrics"]["status"] or not record["cert"]["plan_sha256"]:
            raise ValueError("missing certificate identity or status")
    return raw, len(records)


def inspect(root, detail=False):
    with (root / "registration/rotation.csv").open(newline="", encoding="utf8") as stream:
        slots = list(csv.DictReader(stream))
    ids = {(s["case"], s["repeat"], s["method"]) for s in slots}
    if len(ids) != len(slots) or len(slots) != 144:
        raise ValueError("expected 144 unique registered slots")
    summary = Counter()
    lanes = {}
    observations = []
    for slot in slots:
        case, tag, lane = slot["case"], "r" + slot["repeat"] + "-" + slot["method"], slot["lane"]
        staging = root / "work/batch" / ("lane" + lane) / case / tag
        archive = root / "data/runs" / case / tag / "run.json.gz"
        working = staging / "run.json"
        state, count, error = "no_local_trace", None, None
        try:
            if archive.is_file():
                saved, count = read_receipt(archive, slot)
                if working.is_file() and read_receipt(working, slot)[0] != saved:
                    raise ValueError("archived and staged receipts differ")
                state = "archived_run_record"
            elif working.is_file():
                _, count = read_receipt(working, slot)
                state = "staged_run_record"
            elif staging.is_dir():
                state = "staging_directory_only"
        except (OSError, EOFError, ValueError, KeyError, TypeError) as exc:
            state, error = "unreadable_or_conflicting", type(exc).__name__ + " " + str(exc)
        summary[state] += 1
        lanes.setdefault(lane, Counter())[state] += 1
        if detail or error:
            observations.append(dict(slot, state=state, certificates=count, error=error))
    return {"registered_slots": len(slots), "states": dict(summary), "by_lane": lanes,
            "visible_local_linux_workers_at_observation": local_workers(root),
            "batch_logs": sorted(p.name for p in (root / "work/batch").glob("lane*.log")),
            "environment_files": sorted(p.name for p in (root / "data/environment").glob("lane*.json")),
            "physical_databases": sorted(p.name for p in (root / "work/physical").glob("*.sqlite")),
            "event_databases": sorted(p.name for p in (root / "work/events").glob("*.sqlite")),
            "observations": observations}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, nargs="?", default=Path(__file__).resolve().parent)
    parser.add_argument("--detail", action="store_true", help="include every registered slot")
    args = parser.parse_args()
    print(json.dumps(inspect(args.root.resolve(), args.detail), indent=2, ensure_ascii=False))
