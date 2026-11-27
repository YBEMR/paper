"""Drive registered routes serially, resume completed units, guard deadlines outside the worker."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=Path(os.environ["U3B_RUNS"]).resolve()
def load(path):
    return json.loads(path.read_bytes())
def save(path,obj):
    path.write_text(json.dumps(obj,indent=2),encoding="utf8")
def run(case,method,r=1,offline=False):
    label=("offline" if offline else "online")+f"-{case}-{method}-r{r}"
    out=ROOT/label
    receipt=out/"receipt.json"
    if receipt.exists():
        return load(receipt)
    out.mkdir(parents=True,exist_ok=False)
    start=time.perf_counter()
    remaining=600-sum(load(p)["charged_s"] for p in ROOT.glob("offline-*/receipt.json"))
    remaining-=load(HERE/"tables/historical.json")["wall_s"]
    cap=min(90,remaining-1) if offline else 10
    assert cap>0
    with (out/"worker.log").open("wb") as log:
        proc=subprocess.Popen([sys.executable,"-B",str(HERE/"worker.py"),str(out),case,method],
                              stdout=log,stderr=subprocess.STDOUT)
        logical=None
        while True:
            now=time.perf_counter()
            if logical is None and (out/"start.json").is_file():
                logical=load(out/"start.json")["clock"]
            if (out/"finish.json").is_file() or proc.poll() is not None:
                break
            if (logical is not None and now>=logical+cap) or (offline and now-start>=remaining-.25):
                proc.kill()
                break
            if logical is None and now-start>120:
                proc.kill()
                break
            time.sleep(.003)
        code=proc.wait(timeout=30)
    elapsed=time.perf_counter()-start
    finished=load(out/"finish.json") if (out/"finish.json").is_file() else {}
    in_time=finished.get("wall_s",float("inf"))<=cap
    delivered=load(out/"delivery.json") if (out/"delivery.json").is_file() else {}
    status=delivered.get("status","ERROR") if in_time else ("WALL" if logical is not None and time.perf_counter()-logical>=cap else "ERROR")
    rec=dict(label=label,case=case,method=method,repeat=r,offline=offline,cap_s=cap,status=status,
             exit_code=code,wall_s=finished.get("wall_s"),process_wall_s=elapsed,charged_s=elapsed if offline else 0)
    save(receipt,rec)
    print(label,status,rec["wall_s"],flush=True)
    if status=="ERROR":
        raise RuntimeError((out/"worker.log").read_text(errors="replace"))
    return rec

def main():
    if len(sys.argv)>1 and sys.argv[1]=="unit":
        run(*sys.argv[2:4])
        return
    cases=[v["case"] for v in load(HERE/"tables/historical.json")["cases"]]
    for c in cases:
        run(c,"terminal")
    b=run("B07","b1")
    methods=["b1"]
    if b["status"]!="SAFE":
        run("B07","b2")
        methods.append("b2")
    cells=["oo","oh","ho","hh"]
    for m in cells:
        run("C10",m)
    for c,arms in (("B07",methods),("C10",cells)):
        for m in arms:
            if run(c,m)["status"]=="WALL":
                run(c,m,offline=True)
    for c in ("A06","C11"):
        if run(c,"terminal")["status"]=="SAFE":
            run(c,"first")
            for r in (2,3):
                for m in (["first","terminal"] if r==2 else ["terminal","first"]):
                    run(c,m,r)
    for c,arms in (("B07",methods),("C10",cells)):
        if any(run(c,m)["status"]=="SAFE" for m in arms):
            for r in (2,3):
                order=["terminal",*arms]
                for m in (order[::-1] if r==2 else order):
                    run(c,m,r)
if __name__=="__main__":
    main()

