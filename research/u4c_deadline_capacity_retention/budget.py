"""Conservatively charge entire lifetime of every single-core offline job, including errors."""
import json
import subprocess
import sys
from pathlib import Path
from time import monotonic,time
here=Path(__file__).resolve().parent
path=here/"offline_budget.json"
ledger=json.loads(path.read_bytes()) if path.exists() else []
assert all("charge" in a for a in ledger)
left=600-sum(a["charge"] for a in ledger)
assert left>1
def save():path.write_text(json.dumps(ledger,indent=1)+"\n",encoding="utf8")
job=sys.argv[1] if len(sys.argv)>1 else "witness"
assert job in ("witness","verify","lineage")
r=dict(start_utc=time(),job=job,remaining=left);ledger.append(r);save();start=monotonic()
try:
    p=subprocess.Popen([sys.executable,"-Bu",str(here/(job+".py"))])
    try:rc=p.wait(timeout=max(0,left-.2))
    except subprocess.TimeoutExpired:p.kill();rc=p.wait();r["cutoff"]=True
finally:
    r.update(charge=monotonic()-start,rc=locals().get("rc"));save()
sys.exit(rc)
