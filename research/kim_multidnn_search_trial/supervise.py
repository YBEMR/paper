"""Reserve each slot once, enforce hard deadlines from before spawn, and fail closed."""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
RAW=HERE/"raw"
DESIGN=json.loads((HERE/"design.json").read_bytes())
def read(path):
    return json.loads(path.read_bytes())
def write(path,data):
    tmp=path.with_suffix(path.suffix+".pending")
    tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
    tmp.replace(path)
def records(path):
    if not path.is_file():
        return []
    lines=path.read_bytes().splitlines(keepends=True)
    return [json.loads(line) for line in lines if line.endswith(b"\n")]
def append(path,data):
    with path.open("a",encoding="utf-8") as stream:
        stream.write(json.dumps(data,separators=(",",":"))+"\n")
        stream.flush()
        os.fsync(stream.fileno())

def execute(job,pin,freeze):
    out=RAW/job["id"]
    out.mkdir(exist_ok=False)
    slot=dict(**job,preregistration=pin,freeze_sha256=freeze)
    write(out/"job.json",slot)
    cache=HERE/"scratch"/job["id"]
    cache.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,PYTHONUTF8="1",PYTHONDONTWRITEBYTECODE="1",NUMBA_CACHE_DIR=str(cache),
             OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",NUMBA_NUM_THREADS="1",MKL_NUM_THREADS="1")
    start=time.perf_counter()
    env["TRIAL_START"]=str(start)
    with (out/"console.log").open("wb") as log:
        child=subprocess.Popen([sys.executable,"-B",str(HERE/"worker.py"),str(out)],env=env,
                               stdout=log,stderr=subprocess.STDOUT)
        cut=False
        try:
            child.wait(timeout=max(0.,start+job["cap"]-time.perf_counter()-.05))
        except subprocess.TimeoutExpired:
            cut=True
            child.kill()
            child.wait()
    elapsed=time.perf_counter()-start
    raw=records(out/"events.jsonl")
    rows=[r for r in raw if r["t"]<=job["cap"]]
    ok=bool(rows and rows[-1]["kind"]=="success" and child.returncode==0)
    if not cut and not ok:
        status="FAULT"
    elif ok:
        status="PASS"
    else:
        status="DEADLINE" if job["stage"] in ("dev","holdout") else "FAULT"
    if not rows and cut:
        status="FAULT"
    if elapsed>job["cap"]+.25:
        status="FAULT"
    done=[r for r in rows if r["kind"]=="deployment"]
    phase_counts={}
    for r in done:
        phase_counts[r["phase"]]=r["completed"]
    cert=next((r for r in rows if r["kind"]=="certificate"),None)
    safe=[r for r in rows if r["kind"]=="full_replay" and r["choice"]["physical"]["feasible"]]
    def physical_energy(r):
        return r["choice"]["physical"]["energy_j"]
    best=min(safe,key=physical_energy) if safe else None
    stats=next((r["stats"] for r in reversed(rows) if "stats" in r),{})
    result=dict(**slot,status=status,process_wall_s=elapsed,returncode=child.returncode,supervisor_cut=cut,
        last_event_t=rows[-1]["t"] if rows else None,first_safe_s=safe[0]["t"] if safe else None,
        certified_s=cert["t"] if cert else None,certificate_scope=cert["scope"] if cert else None,
        best_safe_j=physical_energy(best) if best else None,
        best_choice={k:best["choice"][k] for k in ("code","deployment","opps")} if best else None,
        best_peak_upper_c=max(best["choice"]["physical"]["peak_upper_c"]) if best else None,
        completed_by_phase=phase_counts,completed=max(phase_counts.values(),default=0),
        complete_logical_codes=max(phase_counts.values(),default=0)*27**4,
        deadline_legal_covered=sum(r["legal"] for r in done if r["phase"]!="fallback"),
        stats_last_checkpoint=stats,peak_rss_bytes=max((r.get("peak_rss_bytes",0) for r in rows),default=0),
        uncheckpointed_wall_s=max(0,elapsed-rows[-1]["t"]) if rows else elapsed)
    lbs=next((r["values"] for r in rows if r["kind"]=="lower_bounds"),{})
    for r in done:
        d=r["deployment"]
        if r.get("unresolved",0)==0:
            if r["strict_min_j"] is None:
                lbs.pop(d,None)
            else:
                lbs[d]=r["strict_min_j"]
    result["catalog_lower_bound_j"]=min(lbs.values(),default=None)
    write(out/"result.json",result)
    print(job["id"],status,round(elapsed,3),result["completed"],result["best_safe_j"],flush=True)
    return result

def fixed_gate(results):
    a,b=results["fixed-M1"],results["fixed-M2"]
    same=a["completed"]==b["completed"]==4 and a["best_choice"]==b["best_choice"]
    same=same and abs(a["best_safe_j"]-b["best_safe_j"])<=1e-7
    stats=lambda x:x["stats_last_checkpoint"]
    return dict(same_work=same,compile_ratio=stats(b)["compile_s"]/stats(a)["compile_s"],
                total_ratio=b["process_wall_s"]/a["process_wall_s"])

def development_gate(results):
    fixed=fixed_gate(results)
    allowed=fixed["same_work"] and fixed["compile_ratio"]<=.80 and fixed["total_ratio"]<=1.10
    comparisons=[]
    for i in range(4):
        a,b=[results[f"dev-{i}-M{m}"] for m in (1,2)]
        ea,eb=a["best_safe_j"],b["best_safe_j"]
        coverage_ok=b["completed"]>=a["completed"]
        energy_ok=ea is None or eb is not None and eb<=ea+1e-7
        time_ok=not a["certified_s"] or b["certified_s"] is not None and b["certified_s"]<=1.10*a["certified_s"]
        allowed=allowed and coverage_ok and energy_ok and time_ok
        comparisons.append(dict(case=a["case"],coverage_ok=coverage_ok,energy_ok=energy_ok,time_ok=time_ok))
    return dict(allowed=bool(allowed),fixed=fixed,development=comparisons)

def main(pin):
    import re
    assert re.fullmatch("[0-9a-f]{40}",pin)
    freeze=hashlib.sha256((HERE/"freeze.json").read_bytes()).hexdigest()
    assert sum(j["cap"] for j in DESIGN["jobs"])==3840
    RAW.mkdir(exist_ok=True)
    ledger=RAW/"ledger.jsonl"
    with (RAW/"launch.lock").open("x") as lock:
        lock.write(pin+"\n")
    results={}
    try:
        for job in DESIGN["jobs"]:
            if job["id"]=="hold-0-1-M0":
                gate=development_gate(results)
                write(RAW/"development_gate.json",gate)
                if not gate["allowed"]:
                    write(RAW/"stop.json",dict(reason="DEVELOPMENT_GATE",gate=gate))
                    return
            append(ledger,dict(event="reserve",id=job["id"],cap_s=job["cap"],unix=time.time()))
            result=execute(job,pin,freeze)
            results[job["id"]]=result
            append(ledger,dict(event="close",id=job["id"],status=result["status"],actual_s=result["process_wall_s"]))
            if result["status"]=="FAULT":
                write(RAW/"stop.json",dict(reason="TECHNICAL_OR_CORRECTNESS_FAULT",id=job["id"]))
                return
            if job["id"]=="fixed-M2" and not fixed_gate(results)["same_work"]:
                write(RAW/"stop.json",dict(reason="FIXED_WORK_MISMATCH"))
                return
        write(RAW/"stop.json",dict(reason="FINISHED",runs=len(results)))
    except BaseException as exc:
        write(RAW/"stop.json",dict(reason="SUPERVISOR_FAULT",detail=repr(exc)))
        raise

if __name__=="__main__":
    main(sys.argv[1])
