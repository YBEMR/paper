"""Single isolated host, serial roster, no automatic repeat of a timed cell."""
import csv
import gzip
import importlib.metadata
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from time import perf_counter

from interface import CASES, CUTS, HERE, NT, THREE, FOUR, OUT, audit, item, raw, read, save, sha, witness

def ledger(folder):
    p=folder/"certificates.jsonl"
    return [__import__("json").loads(line) for line in p.read_bytes().splitlines() if line.endswith(b"}")] if p.exists() else []

def choose(records,cut):
    best=None
    for r in records:
        if r["t"]<=cut and r["status"]=="SAFE" and (best is None or r["bounds"][1]<best["bounds"][0]):
            best=r
    return best

def invoke(code,method,charge):
    folder=OUT/"cells"/code/method
    assert not folder.exists()
    logs=OUT/"logs";logs.mkdir(parents=True,exist_ok=True)
    with (logs/(code+"_"+method+".txt")).open("xb") as f:
        proc=subprocess.Popen([sys.executable,"-Bu",str(HERE/"cell.py"),code,method],stdout=f,stderr=subprocess.STDOUT)
        boot=perf_counter()
        while proc.poll() is None and not (folder/"ready.json").exists() and perf_counter()-boot<150:
            time.sleep(.025)
        if not (folder/"ready.json").exists():
            if proc.poll() is None: proc.kill()
            proc.wait()
            raise RuntimeError(f"Runtime import failed before target clock: {code}/{method}")
        start=perf_counter()
        save(folder/"clock.json",dict(start=start,charged=charge))
        try:
            rc=proc.wait(timeout=max(.001,180-charge-(perf_counter()-start)))
            status="COMPLETE" if rc==0 else "ERROR"
        except subprocess.TimeoutExpired:
            proc.kill()
            rc=proc.wait()
            status="CAP"
        finish=perf_counter()-start
    rows=ledger(folder)
    rec=dict(code=code,method=method,charge=charge,wall_observed_s=finish,total_charged_s=min(180,finish+charge),
             status=status,returncode=rc,certificates=len(rows),after_cap=sum(r["t"]>180 for r in rows))
    save(folder/"receipt.json",rec)
    print("CELL",raw(rec).decode(),flush=True)

def curves(code,method):
    folder=OUT/"cells"/code/method
    rows=ledger(folder)
    if method.startswith("NT+"):
        rows=[r for r in ledger(OUT/"cells"/code/"NT") if r["t"]<=60]+rows
    receipt=read(folder/"receipt.json")
    result=[]
    for cut in CUTS:
        b=choose(rows,cut)
        result.append(dict(case=code,method=method,cut_s=cut,J=b["J"] if b else None,
            plan=b["plan"] if b else None,cert_s=b["t"] if b else None,
            first_SAFE_s=next((r["t"] for r in rows if r["t"]<=cut and r["status"]=="SAFE"),None),
            attempts=sum(r["t"]<=cut for r in rows),receipt=receipt["status"]))
    return result

def from_nt(code,key):
    return read(OUT/"cells"/code/"NT/search/physical/evidence"/item(code)["case"]/key/"plan.json")

def main():
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    versions={m:importlib.metadata.version(m) for m in ("numpy","scipy","numba","ortools","psutil")}
    assert all(os.environ[k]=="1" for k in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS","NUMBA_NUM_THREADS"))
    save(OUT/"environment.json",dict(cpu=cpu,cpuinfo=Path("/proc/cpuinfo").read_text().split("model name")[1].splitlines()[0],
        platform=platform.platform(),host=platform.node(),python=sys.version,versions=versions,run=os.environ["GITHUB_RUN_ID"],
        cores=sorted(os.sched_getaffinity(0)),refs={k:subprocess.check_output(["git","-C",os.environ[k],"rev-parse","HEAD"]).decode().strip() for k in ("U1_NT","U1_THREE","U1_FOUR")}))
    # Compare exact physics sources across all three selected snapshots.
    shared={}
    for name in ["model.py","heat.py","config/p1_frozen.json","config/cpu_npu_profiles.csv","config/gpu_profiles.csv"]:
        paths=[NT/"m1_transient_thermal_quota_20261126/frozen/p1"/name,THREE/"cross_scene_taskflow_diagnostic"/name,FOUR/"p1"/name]
        hashes=[sha(p.read_bytes()) for p in paths]
        assert len(set(hashes))==1,(name,hashes)
        shared[name]=hashes[0]
    save(OUT/"interface/source_hashes.json",shared)
    for code in CASES:
        plan,key=witness(code)
        save(OUT/"interface"/code/"witness.json",plan)
        reports=[]
        for method in ("NT","Proposed","Q4"):
            subprocess.run([sys.executable,"-Bu",__file__,"audit",code,method],check=True)
            reports.append(read(OUT/"interface"/code/method/"audit.json"))
        assert len({raw(r["physical"]) for r in reports})==1,(code,reports)
        assert all(r["archived_plan"]==key for r in reports)
        print("INTERFACE PASS",code,key,flush=True)
    save(OUT/"interface/gate.json",dict(status="PASS",cases=CASES,search_calls=0))
    for i,code in enumerate(CASES):
        order=("NT","Proposed","Q4")
        for method in order[i%3:]+order[:i%3]:
            invoke(code,method,0)
        if code in ("A03","C12"):
            b=choose(ledger(OUT/"cells"/code/"NT"),60)
            for method in ("NT+AB","NT+Proposed"):
                if b:
                    save(OUT/"seeds"/(code+".json"),dict(key=b["plan"],t=b["t"],J=b["J"],plan=from_nt(code,b["plan"])))
                    invoke(code,method,60)
                else:
                    save(OUT/"cells"/code/method/"receipt.json",dict(code=code,method=method,status="NO_NT60_SAFE",total_charged_s=60))
    rows=[]
    for code in CASES:
        for method in ("NT","Proposed","Q4")+(("NT+AB","NT+Proposed") if code in ("A03","C12") else ()):
            rows.extend(curves(code,method))
    with (OUT/"curves.csv").open("w",newline="") as f:
        cw=csv.DictWriter(f,rows[0],lineterminator="\n");cw.writeheader();cw.writerows(rows)
    print("CURVES",len(rows))

if __name__=="__main__":
    if len(sys.argv)>1:
        audit(*sys.argv[2:])
    else:
        main()
