"""One-shot D3 run ledger. Formal samples open only after the engineering gate."""
import gzip
import json
import subprocess
import sys
import time
import traceback
from datetime import datetime,timezone
import psutil
from design_d import BASE,COMPACT_BASE,C2,ROOT,REPO,METHODS,SEEDS,INITIAL,clock,sha,read,write
from batch import clean
def git(*args):return subprocess.check_output(["git",*args],cwd=REPO)
def utc():return datetime.now(timezone.utc).isoformat()
def record(s):write(ROOT/"execution.json",s)

def freeze():
    old=read(C2/"manifest.json");head=git("rev-parse","HEAD").decode().strip()
    assert git("rev-parse","HEAD^").decode().strip()==BASE
    git("merge-base","--is-ancestor",COMPACT_BASE,BASE)
    files={**old["inherited"],**old["source_hashes"]}
    for f in sorted(C2.glob("*.py")):
        n=f.relative_to(REPO).as_posix()
        assert git("show",BASE+":"+n)==f.read_bytes()
        files[n]=sha(f.read_bytes())
    for n,h in files.items():assert sha((REPO/n).read_bytes())==h,n
    src={}
    for f in [*ROOT.glob("*.py"),ROOT/"protocol.md"]:
        n=f.relative_to(REPO).as_posix();b=f.read_bytes()
        assert git("show",head+":"+n)==b
        src[n]=sha(b)
    sys.path.insert(0,str(ROOT.parent/"domain_joint_optimization_e2b"))
    from supervise import physical_cores
    cores=physical_cores();free=psutil.virtual_memory().available
    peaks=[read(p)["peak_bytes"] for p in (ROOT.parent/"domain_joint_optimization_e2b"/"runs").glob("D3_*/summary.json") if "G3" not in p.parent.name]
    unit=max(768*2**20,int(2.5*max(peaks)));reserve=640*2**20
    slots=min(3,len(cores),max(1,int((free-reserve)/unit)))
    assert free>384*2**20,"insufficient memory for even one historical D3 run"
    used=cores[:slots]
    cells=[]
    for i,seed in enumerate(SEEDS):
        for j in range(3):
            k=len(cells);wave=k//slots
            cells.append(dict(method=METHODS[(j+i)%3],seed=seed,cpu=used[(k%slots+wave)%slots],wave=wave+1))
    m=dict(base=BASE,compact_base=COMPACT_BASE,freeze=head,inherited=files,source_hashes=src,case="D3",initial=INITIAL,
        initial_J=63.39163095183008,initial_lower=old["initial_lower"],cpu_representatives=cores,cpus=used,
        free_bytes=free,estimated_bytes_per_run=unit,system_reserve_bytes=reserve,runs=cells,
        total_limit=9000,ancillary_limit=900,formal_limit=8100,seconds=900,cycles=3,auxiliary_s=11,local_s=30,
        warmup="private worker ready inside first G3 phase",pilots="all methods, seed 103, two 30+30-second cycles")
    write(ROOT/"manifest.json",m);return m

def investigate():
    src=C2/"runs"/"Hybrid-New_103"/"events.jsonl.gz"
    with gzip.open(src,"rb") as f:
        rows=[v for l in f if (v:=json.loads(l))["cycle"] in (1,2) and v["event"] in ("worker_start","worker_exit","subproblem")]
    write(ROOT/"preflight"/"historical_103.json",dict(source=BASE,sha=sha(src.read_bytes()),records=rows,
          starts=sum(v["event"]=="worker_start" for v in rows),old_timing=read(C2/"timing.json"),
          cause="Cold starts and readiness timeouts are recorded; historical import/asset latencies and OS cause are unknown."))

def launch(tag,args):
    path=ROOT/"logs"/(tag+".txt");path.parent.mkdir(exist_ok=True)
    with path.open("xb") as f:
        return subprocess.Popen([sys.executable,"-B","-u",*map(str,args)],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)

def wave(s,specs,pilot):
    live=[];cap=120 if pilot else 900
    key="pilot_runs" if pilot else "runs"
    try:
        for spec in specs:
            tag=spec["method"]+"_"+str(spec["seed"])
            where=ROOT/("preflight/pilots" if pilot else "runs")/tag
            t=clock();r=dict(**spec,tag=tag,begin=t,utc=utc(),limit=cap,status="RUNNING")
            p=launch(("pilot_" if pilot else "formal_")+tag,["run_d.py",where,spec["method"],spec["seed"],spec["cpu"],t,int(pilot)])
            live.append((p,r,where));s[key].append(r);record(s)
        while live:
            for item in live.copy():
                p,r,folder=item;code=p.poll()
                if code is None and clock()-r["begin"]<cap-.65:continue
                if code is None:clean(p);code=124
                elapsed=clock()-r["begin"]
                r.update(exit_s=elapsed,end_utc=utc(),code=code,charged_s=cap);live.remove(item)
                if code or elapsed>cap:
                    r["status"]="INTERRUPTED";record(s);raise RuntimeError((r["tag"],code,elapsed))
                z=read(folder/"summary.json")
                assert z["initial"]==INITIAL and z["charged_window_s"]==cap and z["elapsed_s"]<cap
                r.update(status="COMPLETE",endpoint_s=z["elapsed_s"],final=z["final"]);record(s)
            if live:time.sleep(.035)
    finally:
        for p,r,folder in live:
            clean(p);r.update(status="INTERRUPTED",charged_s=min(cap,clock()-r["begin"]),end_utc=utc())
        record(s)

def run():
    assert not (ROOT/"execution.json").exists(),"registered batch already exists"
    started=clock();s=dict(status="PREFLIGHT",start_utc=utc(),pilot_runs=[],runs=[],preliminary_s=12.)
    record(s)
    try:
        m=freeze();investigate()
        p=launch("regression",["verify_d.py"])
        try:code=p.wait(timeout=230)
        except subprocess.TimeoutExpired:clean(p);raise
        assert code==0,"regression failed; see logs/regression.txt"
        s["regression_and_identity_s"]=clock()-started
        # Sequential pilots keep startup profiles intelligible; all three are charged.
        for method in METHODS:
            wave(s,[dict(method=method,seed=103,cpu=m["cpus"][0],wave=0)],True)
        from verify_d import inspect
        reports=[inspect(ROOT/"preflight"/"pilots"/v["tag"]) for v in s["pilot_runs"]]
        s["preflight_s"]=s["preliminary_s"]+max(clock()-started,
            s["regression_and_identity_s"]+sum(r["charged_s"] for r in s["pilot_runs"]))
        assert s["preflight_s"]<680,"insufficient independent verification reserve"
        write(ROOT/"preflight"/"gate.json",dict(passed=True,reports=reports,seconds=s["preflight_s"]))
        s["status"]="FORMAL";record(s)
        for n in sorted({x["wave"] for x in m["runs"]}):
            wave(s,[v for v in m["runs"] if v["wave"]==n],False)
        s["status"]="AUDIT"
    except Exception:
        s["status"]="FORMAL_INTERRUPTION" if s["runs"] else "PREFLIGHT_STOP"
        s["error"]=traceback.format_exc()
        if "preflight_s" not in s:
            s["preflight_s"]=s["preliminary_s"]+max(clock()-started,s.get("regression_and_identity_s",0)+sum(r.get("charged_s",0) for r in s["pilot_runs"]))
        raise
    finally:
        s.update(end_utc=utc(),formal_s=sum(r.get("charged_s",0) for r in s["runs"]));record(s)
if __name__=="__main__":run()
