"""Charge the entire single-core offline child lifetime, including startup and failed attempts."""
import json
import subprocess
import sys
import time
from pathlib import Path
root=Path(__file__).resolve().parent
path=root/"offline_budget.json"
if path.exists():ledger=json.loads(path.read_text())
else:ledger=[]
assert all("charged_s" in r for r in ledger),"Unclosed attempt; reconcile conservative charge first"
left=600-sum(r["charged_s"] for r in ledger)
assert left>1
def save():path.write_text(json.dumps(ledger,indent=1)+"\n",encoding="utf8")
job=sys.argv[1] if len(sys.argv)>1 else "offline"
assert job in ("offline","detail","proof_check","out_of_model","residual")
r=dict(utc_start=time.time(),remaining_s=left,job=job);ledger.append(r);save()
start=time.monotonic()
try:
    p=subprocess.Popen([sys.executable,"-Bu",str(root/(job+".py"))])
    try:rc=p.wait(timeout=max(0,left-0.2))
    except subprocess.TimeoutExpired:p.kill();rc=p.wait();r["cutoff"]=True
finally:
    r["charged_s"]=time.monotonic()-start;r["returncode"]=locals().get("rc");save()
sys.exit(rc)
