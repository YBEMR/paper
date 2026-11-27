"""Wall-clock upper bound for all single-thread worker attempts, including failures."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "measurements"
OUT.mkdir(exist_ok=True)
LEDGER = OUT / "budget.json"
PULSE = OUT / "current.json"

def save(path, data):
    temp = path.with_suffix(".new")
    temp.write_text(json.dumps(data, indent=1), encoding="utf8")
    for retry in range(20):
        try:
            os.replace(temp, path)
            return
        except PermissionError:
            if retry == 19:
                raise
            time.sleep(.015)

def main():
    entries = json.loads(LEDGER.read_bytes()) if LEDGER.exists() else []
    assert all("charged_s" in row for row in entries), "reconcile unfinished previous attempt first"
    left = 480 - sum(row["charged_s"] for row in entries)
    assert left > 2
    attempt = len(entries) + 1
    begin = time.monotonic()
    job=sys.argv[1] if len(sys.argv)>1 else "main"
    assert job in ("main","delivery")
    row = dict(attempt=attempt, utc=time.time(), available_s=left,job=job)
    entries.append(row)
    save(LEDGER, entries)
    with (OUT / f"attempt-{attempt}.txt").open("x",encoding="utf8") as log:
        script="benchmark.py" if job=="main" else "benchmark_delivery.py"
        proc = subprocess.Popen([sys.executable, "-Bu", str(HERE/script), str(attempt)],
                                stdout=log, stderr=subprocess.STDOUT)
        while proc.poll() is None:
            stage_end = begin + 90
            if PULSE.exists():
                try:
                    state = json.loads(PULSE.read_bytes())
                except (FileNotFoundError, PermissionError, json.JSONDecodeError):
                    state = {}
                if state.get("attempt") == attempt:
                    stage_end = state["start"] + state["limit"]
                elif state.get("attempt") is None:
                    # Keep the previous stage cutoff during a Windows sharing violation.
                    stage_end = previous_end if 'previous_end' in locals() else begin + 90
            previous_end=stage_end
            if time.monotonic() >= min(stage_end, begin + left - .6):
                proc.kill()
                row["cutoff"] = state if PULSE.exists() else "launch"
                break
            time.sleep(.05)
        row["rc"] = proc.wait()
    row["charged_s"] = time.monotonic() - begin
    assert row["charged_s"] <= left
    save(LEDGER, entries)
    print(row, flush=True)
    return row["rc"]

if __name__ == "__main__":
    sys.exit(main())
