"""Bound and debit the entire single-worker lifetime, including failed attempts."""
import json
import math
import subprocess
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parent
log = root / "archive" / "budget.json"
log.parent.mkdir(exist_ok=True)
history = json.loads(log.read_bytes()) if log.exists() else []
remaining = 120 - sum(x["charge_s"] for x in history)
if any(x["returncode"] is None for x in history) or remaining < 2:
    raise SystemExit("budget closed")
stage = sys.argv[1]
history.append(dict(stage=stage, started_utc=time.time(), charge_s=remaining, returncode=None))
log.write_text(json.dumps(history, indent=1))
start = time.monotonic()
try:
    proc = subprocess.run([sys.executable, "-B", str(root/"archive_audit.py"), stage],
                          timeout=math.floor(remaining)-1, check=False)
    rc = proc.returncode
except subprocess.TimeoutExpired:
    rc = 124
history[-1].update(charge_s=time.monotonic()-start, returncode=rc)
log.write_text(json.dumps(history, indent=1)+"\n")
sys.exit(rc)
