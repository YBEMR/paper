"""Verify deliverable identities and budget after the numerical owner has exited."""
import csv
import json
import subprocess
import time
from pathlib import Path
from settings import BASE,INITIAL,METHODS,ROOT,REPO,read,write,sha

def seal(post_start):
    m=read(ROOT/"manifest.json");s=read(ROOT/"execution.json");a=read(ROOT/"audit.json")
    assert s["status"] in ("AWAITING_INDEPENDENT_AUDIT","FORMAL_INTERRUPTION","PREFLIGHT_STOP")
    git=lambda *args:subprocess.check_output(["git",*args],cwd=REPO)
    assert git("rev-parse","HEAD").decode().strip()==m["freeze"]
    assert git("rev-parse","HEAD^").decode().strip()==BASE
    for n,h in m["source_hashes"].items():assert sha((REPO/n).read_bytes())==h,n
    for n,h in m["inherited"].items():assert sha((REPO/n).read_bytes())==h,n
    run_keys=[(r["method"],r["seed"]) for r in s["runs"]]
    assert len(run_keys)==len(set(run_keys)) and run_keys==[(v["method"],v["seed"]) for v in m["runs"][:len(run_keys)]]
    assert all(r["limit"]==1800 and r["charged_s"]<=1800 for r in s["runs"])
    out=list(csv.DictReader((ROOT/"results.csv").open(encoding="utf8",newline="")))
    pairs=list(csv.DictReader((ROOT/"paired.csv").open(encoding="utf8",newline="")))
    phases=list(csv.DictReader((ROOT/"phase_results.csv").open(encoding="utf8",newline="")))
    assert len(pairs)==9 and len(out)==12
    if a["verified"]==12:
        assert len(phases)==111 and sum(r["phase"]=="joint" for r in phases)==54
        assert s["main_charge"]==21600 and len(run_keys)==12 and all(v["status"]=="VERIFIED" for v in out)
        assert all((ROOT/"runs"/r["tag"]/"terminal_trace.npz").is_file() for r in s["runs"])
    post_s=time.time()-post_start
    assert s["preflight_s"]<=900 and s["main_charge"]<=21600 and post_s<900
    write(ROOT/"budget.json",dict(preflight_s=s["preflight_s"],formal_s=s["main_charge"],
           audit_and_seal_s=post_s,total_s=s["preflight_s"]+s["main_charge"]+post_s,
           publication_started=post_start,independent_audits=a["verified"],formal_budget=21600,total_limit=23400))
    files={p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in sorted(ROOT.rglob("*"))
           if p.is_file() and p.name!="snapshot.json" and "__pycache__" not in p.parts}
    assert not any(n.endswith(".tmp") for n in files)
    write(ROOT/"snapshot.json",dict(freeze=m["freeze"],initial=INITIAL,base=BASE,methods=METHODS,
           preflight=s["preflight_s"],formal_s=s["main_charge"],independently_verified=a["verified"],
           budget="budget.json",decision=a["title"],files=files))
if __name__=="__main__":
    import sys
    seal(float(sys.argv[1]))
