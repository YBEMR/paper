"""Inventory physical C/D launches across v5 folders. Copied evidence retains its original launch identity."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


FORMAL_ROOTS = ("formal", "restart_01/formal", "continuation_02/formal", "continuation_03/formal", "continuation_04/formal")


def read(path):
    return json.loads(path.read_bytes())


def attempts(run, *, closed=False):
    rows = {}
    for location in FORMAL_ROOTS:
        cells = run / location / "cells"
        for start in sorted(cells.glob("*/start.json")):
            folder = start.parent
            launch = read(start)
            key = hashlib.sha256(start.read_bytes()).hexdigest()
            receipt_path = folder / "receipt.json"
            receipt = read(receipt_path) if receipt_path.exists() else {}
            status = receipt.get("status", "NO_RECEIPT")
            result_path = folder / "result.json"
            result = read(result_path) if result_path.exists() else {}
            receipt_sha = hashlib.sha256(receipt_path.read_bytes()).hexdigest() if receipt_path.is_file() else None
            result_sha = hashlib.sha256(result_path.read_bytes()).hexdigest() if result_path.is_file() else None
            if key in rows:
                original = rows[key]
                if (original["cell"], original["receipt_sha256"], original["result_sha256"]) != (
                        folder.name, receipt_sha, result_sha):
                    raise ValueError(f"Conflicting copies of {folder.name}")
                original["copies"].append(folder.relative_to(run).as_posix())
                continue
            log = folder / "rounds.jsonl"
            rounds = [json.loads(line) for line in log.read_bytes().splitlines() if line.strip()] if log.is_file() else []
            progress = read(folder / "progress.json") if (folder / "progress.json").is_file() else {}
            lower = max([float(launch["prior_charge_s"]), float(progress.get("elapsed_s", 0)),
                         *(float(r["elapsed_s"]) for r in rounds)])
            charged = receipt.get("charged_s")
            if charged is not None and lower > charged + 0.01:
                raise ValueError(f"Round/receipt time inversion in {folder}")
            final = result.get("final", {})
            rows[key] = dict(cell=folder.name, case=launch["case"], arm=launch["arm"], seed=launch["seed"],
                             source=folder.relative_to(run).as_posix(), copies=[], start_sha256=key,
                             receipt_sha256=receipt_sha, result_sha256=result_sha,
                             started_utc=launch["utc"], ended_utc=receipt.get("ended"),
                             budget_s=launch["budget_s"], prior_charge_s=launch["prior_charge_s"],
                             completed_rounds=len(rounds), status=status, last_recorded_s=lower,
                             charged_s=charged, final_status=final.get("status"), final_J=final.get("J"),
                             final_plan=final.get("plan"))
    records = sorted(rows.values(), key=lambda r: r["started_utc"])
    if closed:
        latest = next((run / loc for loc in reversed(FORMAL_ROOTS) if (run / loc).is_dir()))
        end = read(latest / "batch_end.json")
        complete = [r for r in records if r["status"] == "COMPLETE"]
        roster = read(latest / "batch_start.json")["roster"]
        accepted = {r["cell"] for r in complete}
        missing = {r["id"] for r in roster} - accepted
        stage_receipts = {p.parent.name: read(p) for p in (latest / "cells").glob("*/receipt.json")}
        if (len(stage_receipts) != end["completed_receipts"] or len(end["receipts"]) != len(stage_receipts)
                or {r["id"]: r for r in end["receipts"]} != stage_receipts):
            raise ValueError("Formal receipt inventory disagrees with closure")
        expected_outcomes = ("INCOMPLETE", "INCOMPLETE_INTERRUPTED_CELL") if missing else ("FINISHED",)
        if (len(complete) != len(accepted) or accepted != {k for k, r in stage_receipts.items() if r["status"] == "COMPLETE"}
                or set(end["missing"]) != missing or end["outcome"] not in expected_outcomes):
            raise ValueError("Formal closure and complete attempts disagree")
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--closed", action="store_true")
    args = parser.parse_args()
    rows = attempts(args.run.resolve(), closed=args.closed)
    if not rows:
        raise ValueError("No C/D launches found")
    with args.out.open("x", newline="", encoding="utf8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "copies": json.dumps(row["copies"], ensure_ascii=False)})


if __name__ == "__main__":
    main()
