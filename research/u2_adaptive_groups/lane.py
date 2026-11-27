"""Four independent single-core lanes, with all three repeats for a case on one host."""
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
from time import perf_counter
from common_u2 import *

def supervise(idx,rep,method,repdir,seed):
    folder=repdir/method
    if method in LOCAL and not seed["plan"]:
        folder.mkdir()
        save(folder/"receipt.json",dict(status="NO_W4_SAFE",charge=seed["charge"],new_s=0,charged_s=seed["charge"],calls=0))
        return
    charge=seed["charge"] if method in LOCAL else 0
    if charge>=60:
        folder.mkdir()
        save(folder/"receipt.json",dict(status="NO_REMAINING_BUDGET",charge=charge,new_s=0,charged_s=charge,calls=0))
        return
    log=repdir/(method+".log")
    with log.open("xb") as output:
        proc=subprocess.Popen([sys.executable,"-Bu",str(HERE/"cell.py"),str(idx),str(rep),method,str(folder)],stdout=output,stderr=subprocess.STDOUT)
        wait=perf_counter()
        while proc.poll() is None and not (folder/"ready.json").exists() and perf_counter()-wait<120:time.sleep(.015)
        if not (folder/"ready.json").exists():
            if proc.poll() is None:proc.kill()
            proc.wait()
            raise RuntimeError(log.read_text(errors="replace")[-2500:])
        start=perf_counter()
        save(folder/"clock.json",dict(start=start,charge=charge))
        try:
            rc=proc.wait(timeout=max(.001,60-charge-(perf_counter()-start)))
            status=read(folder/"end.json")["status"] if rc==0 else "ERROR"
        except subprocess.TimeoutExpired:
            proc.kill();rc=proc.wait();status="CAP"
        wall=perf_counter()-start
    rows=lines(folder/"certs.jsonl")
    save(folder/"receipt.json",dict(status=status,rc=rc,charge=charge,new_s=wall,charged_s=min(60,charge+wall),
        calls=len(rows),after_cut=sum(r["t"]>60 for r in rows)))
    if status=="ERROR":print("ERROR",log.read_text(errors="replace")[-2000:],flush=True)
    print("CELL",idx,rep,method,status,len(rows),round(charge+wall,3),flush=True)

def prefix(folder):
    allrows=lines(folder/"certs.jsonl")
    rows=[r for r in allrows if r["width"]==4 and r["t"]<=60][:4]
    fourth=rows[3]["t"] if len(rows)==4 else None
    boundary=next((r["t"] for r in lines(folder/"widths.jsonl") if r["width"]!=4),read(folder/"receipt.json")["charged_s"])
    charge=fourth if fourth is not None else min(60,boundary)
    w=best(rows)
    return dict(plan=w["plan"] if w else None,J=w["J"] if w else None,charge=charge,fourth_s=fourth,
                K=len(rows),rows=rows,status="FULL" if fourth else "PARTIAL")

def q4_check(repdir,obj,st):
    # Audit the standalone historical Q4 route against causal replay offline, without changing its decisions.
    src=repdir/"Q4"/"evidence"/obj["case"]
    out=repdir/"Q4_causal_audit"
    f=make_flow(st[0],obj,out)
    audit=[]
    for r in lines(repdir/"Q4/certs.jsonl"):
        p=src/r["plan"];plan=read(p/"plan.json")
        d,tr=f.certify(cfg(plan["rows"]))
        alt=out/"evidence"/obj["case"]/d["plan_sha256"]
        other=read(alt/"plan.json")
        assert plan["rows"]==other["rows"]
        a=set(map(tuple,plan["low"]));b=set(map(tuple,other["low"]))
        audit.append(dict(native=r["plan"],causal=d["plan_sha256"],changed_idle=len(a^b),native_J=r["J"],
            causal_J=d["metrics"]["E_J"],native_status=r["status"],causal_status=d["metrics"]["status"],kind=r["kind"]))
    save(out/"audit.json",audit)

def run(lane):
    import psutil
    cp=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cp})
    assert all(os.environ[k]=="1" for k in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS","NUMBA_NUM_THREADS"))
    root=OUT/("lane"+str(lane));root.mkdir(parents=True,exist_ok=False)
    env=dict(host=platform.node(),cpu=cp,model=Path("/proc/cpuinfo").read_text().split("model name")[1].splitlines()[0],
        python=sys.version,platform=platform.platform(),versions={n:importlib.metadata.version(n) for n in ("numpy","numba","scipy","psutil")},
        run=os.environ.get("GITHUB_RUN_ID"),boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip())
    with (HERE/"registration/roster.csv").open() as f:registered=list(csv.DictReader(f))
    assert len(registered)==216
    st=stack()
    for idx,obj in enumerate(CASES):
        if idx%4!=lane:continue
        code=obj["case"].split("_")[0]
        folder=root/code;folder.mkdir()
        save(folder/"environment.json",env)
        for repeat in (1,2,3):
            repdir=folder/("r"+str(repeat));repdir.mkdir()
            seed=None
            methods=order(idx,repeat)
            assert methods==[r["method"] for r in registered if r["case"]==obj["case"] and int(r["repeat"])==repeat]
            for m in methods:
                supervise(idx,repeat,m,repdir,seed)
                if m=="NT":
                    seed=prefix(repdir/"NT");save(repdir/"seed.json",seed)
            q4_check(repdir,obj,st)
        from archive_u2 import package
        package(code,folder)

if __name__=="__main__":
    if sys.argv[1]=="gate":
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});precheck(OUT/"gate")
    else:run(int(sys.argv[1]))
