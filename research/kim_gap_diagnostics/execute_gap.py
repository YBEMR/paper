"""One frozen batch: six fixed-deployment and six bounded-probe workers, no automatic retries."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
CFG=json.loads((HERE/"config.json").read_bytes())
CASES=json.loads((HERE/"inputs/cases.json").read_bytes())

def encode(x):return json.dumps(x,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()
def save(p,x):p.write_bytes(encode(x)+b"\n")
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def folder(case,phase):return HERE/"raw"/case/phase

def worker(case_id,phase,core,start):
    import psutil
    psutil.Process().cpu_affinity([core])
    from common import verify_freeze,read,save as save_any,make_domain,Evaluator,search
    from frequency_opt import FrequencyOracle
    verify_freeze();case=next(c for c in CASES if c["case_id"]==case_id)
    clock=search.Clock(start,start+CFG["admit_s"]);dest=folder(case_id,phase)
    domain=make_domain(ROOT);assert domain.size==CFG["domain"]
    witnesses=[];results=[];serial=0
    with (dest/"events.jsonl").open("xb") as logs,(dest/"physical.jsonl").open("xb") as physics:
        def emit(kind,data):
            nonlocal serial
            if kind=="physical":
                physics.write(encode(dict(t_s=clock.elapsed(),**data))+b"\n");physics.flush()
                r=data["physical"]
                if r["thermal_status"]=="SAFE":
                    proof=ev.evidence(data["dep"],data["indices"])
                    serial+=1;name=f"safe_{serial:03d}.json.gz";save_any(dest/name,proof)
                    record=dict(dep=data["dep"],indices=data["indices"],energy_j=r["energy_j"],proof=name,
                                t_s=clock.elapsed(),accepted=clock.elapsed()<=CFG["cap_s"])
                    witnesses.append(record)
                    logs.write(encode(dict(t_s=clock.elapsed(),kind="safe_witness",data=record))+b"\n")
                data={k:v for k,v in data.items() if k!="physical"}
            logs.write(encode(dict(t_s=clock.elapsed(),kind=kind,data=data))+b"\n");logs.flush()
        ev=Evaluator(case,domain,emit)
        emit("identity",dict(case=case,phase=phase,core=core,request_sha=ev.identity,domain=domain.size,
            initial_c=ev.platform["thermal"]["initial_C"],ambient_c=ev.ambient,initialization_s=clock.elapsed()))
        old=read(HERE/"inputs"/(case_id+"_kim.json.gz"))
        baseline=ev.replay(case["dep"],case["indices"]);clock.check()
        assert ev._physical[case["dep"],tuple(case["indices"])]==old["physical"],"historical physical replay differs"
        assert ev.evidence(case["dep"],case["indices"])["completions"]==old["completions"]
        emit("historical_regression",dict(status="PASS",energy_j=baseline.energy_j,requests=500))
        oracle=FrequencyOracle(ev,clock,dest,emit,CFG)
        pool=[dict(dep=case["dep"],group="fixed")] if phase=="fixed_frequency" else read(HERE/"inputs/candidates.json")[case["dep"]]
        stop="completed";active=None
        try:
            for proposal in pool:
                clock.check();active=proposal["dep"]
                results.append(oracle.evaluate(active,proposal["group"],baseline=phase=="fixed_frequency"))
                active=None
        except search.Cutoff:stop="budget_unresolved"
        valid=[r for r in witnesses if r["accepted"]]
        best=min(valid,key=lambda r:r["energy_j"]) if valid else None
        save(dest/"result.json",dict(case_id=case_id,phase=phase,reason=stop,completed=results,
            planned=len(pool),incomplete=active,not_completed=[p["dep"] for p in pool if p["dep"] not in {r["dep"] for r in results}],
            best=best,witnesses=witnesses,counters=dict(ev.counters),timings_s=dict(ev.seconds),
            search_end_s=clock.elapsed(),request_sha=ev.identity))
    save(dest/"worker_end.json",dict(wall_s=clock.elapsed()))

def slot(case,phase,core,commit,stop):
    dest=folder(case,phase);dest.mkdir(parents=True,exist_ok=False)
    save(dest/"reservation.json",dict(case_id=case,phase=phase,core=core,execution_commit=commit,
         manifest_sha=sha(HERE/"execution_manifest.json")))
    env=dict(os.environ,OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1",MKL_NUM_THREADS="1",NUMBA_NUM_THREADS="1",
             PYTHONDONTWRITEBYTECODE="1",PYTHONHASHSEED="0")
    with (dest/"console.txt").open("w",encoding="utf-8") as out:
        start=perf_counter()
        p=subprocess.Popen([sys.executable,"-B","-X","utf8",str(HERE/"execute_gap.py"),"--worker",case,phase,str(core),str(start)],
                           env=env,stdout=out,stderr=out)
        try:
            p.wait(max(0,CFG["cap_s"]-(perf_counter()-start)))
            state="finished" if p.returncode==0 and (dest/"result.json").exists() else "fault"
        except subprocess.TimeoutExpired:
            p.kill();p.wait();state="hard_timeout"
    wall=perf_counter()-start
    for name in ["events.jsonl","physical.jsonl"]:
        f=dest/name
        if f.exists():
            (dest/(name+".gz")).write_bytes(gzip.compress(f.read_bytes(),compresslevel=6,mtime=0));f.unlink()
    save(dest/"receipt.json",dict(status=state,returncode=p.returncode,total_wall_s=wall,files={f.name:sha(f) for f in sorted(dest.iterdir())}))
    print(case,phase,state,round(wall,2),flush=True)
    if state=="fault":
        stop.set();raise RuntimeError((dest/"console.txt").read_text(encoding="utf-8")[-3000:])

def batch():
    from common import verify_freeze
    verify_freeze();assert not (HERE/"raw").exists(),"No overwrite or second batch"
    assert not subprocess.check_output(["git","diff","HEAD","--name-only"],cwd=ROOT,text=True).strip()
    commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    import platform,importlib.metadata as meta,psutil
    save(HERE/"environment.json",dict(execution_commit=commit,python=sys.version,platform=platform.platform(),cpu=platform.processor(),
        cores=CFG["cores"],physical_cpus=psutil.cpu_count(logical=False),logical_cpus=psutil.cpu_count(),
        versions={n:meta.version(n) for n in ["numpy","scipy","numba","llvmlite","psutil"]},manifest_sha=sha(HERE/"execution_manifest.json")))
    stop=Event()
    def lane(case,core):
        for phase in CFG["phases"]:
            if stop.is_set():return
            slot(case["case_id"],phase,core,commit,stop)
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures=[pool.submit(lane,c,core) for c,core in zip(CASES,CFG["cores"],strict=True)]
        for f in futures:f.result()
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--worker",nargs=4);a=p.parse_args()
    if a.worker:
        case,phase,core,start=a.worker;worker(case,phase,int(core),float(start))
    else:batch()
