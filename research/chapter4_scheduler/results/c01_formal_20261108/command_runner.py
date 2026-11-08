"""Exclusive command journals for this preparation session, no retries."""
from datetime import datetime, timezone
from pathlib import Path
import json
import subprocess
import sys
import time

OUT = Path(__file__).resolve().parent


def save(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


label, *command = sys.argv[1:]
record = {"argv": command, "cwd": str(Path.cwd()), "started_utc": datetime.now(timezone.utc).isoformat()}
save(OUT / (label + "_started.json"), record)
started = time.monotonic()
with (OUT / (label + "_stdout.log")).open("x") as stdout, (OUT / (label + "_stderr.log")).open("x") as stderr:
    process = subprocess.run(command, stdout=stdout, stderr=stderr)
record.update(ended_utc=datetime.now(timezone.utc).isoformat(), wall_s=time.monotonic() - started, exit_code=process.returncode)
save(OUT / (label + "_return.json"), record)
print(json.dumps(record), flush=True)
sys.exit(process.returncode)
