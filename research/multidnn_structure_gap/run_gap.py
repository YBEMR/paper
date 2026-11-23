"""Single frozen batch; model construction and all certification count in wall time."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
from time import perf_counter
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import argparse
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
CFG=json.loads((HERE/"protocol.json").read_bytes())
def enc(x):return json.dumps(x,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()
def save(p,x):p.write_bytes(enc(x)+b"\n")
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def verify_freeze():
    for name,value in json.loads((HERE/"execution_manifest.json").read_bytes()).items():
        assert sha(ROOT/name)==value,("execution drift",name)
def folder(case,method,seed):
    return HERE/"raw"/case/f"{method}_{seed}"

def worker(case,method,seed,core,start):
    import psutil
    psutil.Process().cpu_affinity([core])
    verify_freeze()
    from model import Instance,Physical,bind_kim,encoded,load_module
    from dataclasses import asdict
    from unittest.mock import patch
    instance=Instance(case);ev=Physical(instance)
    search,kim,bindings=bind_kim(instance)
    clock=search.Clock(start,start+CFG["admit_s"])
    dest=folder(case,method,seed);accepted=[];cert_no=0
    with (dest/"events.jsonl").open("xb") as log,(dest/"physical.jsonl").open("xb") as physics:
        def emit(kind,data,when=None):
            nonlocal cert_no
            if kind=="physical":
                physics.write(enc(dict(t_s=clock.elapsed(),identity=instance.identity,**data))+b"\n")
                physics.flush()
                data=dict(dep=data["dep"],indices=data["indices"],energy_j=data["physical"]["energy_j"],
                          status=data["physical"]["thermal_status"])
            if kind=="incumbent":
                key,energy=data;proof=ev.evidence(key[0],key[1:])
                assert proof["physical"]["thermal_status"]=="SAFE"
                cert_no+=1;name=f"safe_{cert_no:03d}.json.gz"
                (dest/name).write_bytes(gzip.compress(enc(proof)+b"\n",compresslevel=1,mtime=0))
                when=clock.elapsed()
                data=dict(key=key,energy_j=energy,proof=name,accepted=when<=CFG["cap_s"])
                if data["accepted"]:accepted.append(dict(t_s=when,**data))
            log.write(enc(dict(t_s=clock.elapsed() if when is None else when,kind=kind,data=data))+b"\n")
            log.flush()
        ev.emit=emit
        emit("identity",dict(case=instance.case,instance_sha=instance.identity,models=instance.case["models"],
             domain_count=len(instance.order),domain_sha=sha(HERE/instance.case["domain_file"]),opps=list(ev.opps),
             method=method,seed=seed,core=core,initialization_s=clock.elapsed(),kim_binding=bindings))
        old_thermal=ev.events.evaluate_thermal
        old_mapping=search.evaluate_mapping
        def thermal(*args,**kwargs):
            t=perf_counter();ev.counters["direct_thermal_calls"]+=1
            try:return old_thermal(*args,**kwargs)
            finally:ev.seconds["direct_thermal_s"]+=perf_counter()-t
        def mapping(dep,observe):
            t=perf_counter();ev.counters["setfreq_mappings"]+=1
            try:sol=old_mapping(dep,observe)
            finally:ev.seconds["setfreq_inclusive_s"]+=perf_counter()-t
            emit("setfreq_mapping",dict(dep=dep,indices=sol.opps,valid=sol.valid,
                 scores=[v if v<float("inf") else None for v in sol.scores],compute_s=perf_counter()-t))
            return sol
        with patch.object(ev.events,"evaluate_thermal",thermal),patch.object(search,"evaluate_mapping",mapping):
            if method=="M2-reference":
                module=load_module("structure_exact",HERE/"exact.py")
                outcome=module.Exact(ev,clock,emit).run(search.Cutoff)
            else:
                domain=search.Domain(instance.domain,instance.order)
                gpu=next(d for d in domain.order if instance.domain["deployments"][d]["resident_dla_stages"]==0)
                anchor=next(d for d in domain.order if all(len(c)==2 and c[0][0]==f"DLA{i%2}"
                    for i,c in enumerate(instance.domain["deployments"][d]["stages"].values())))
                anchors=[gpu,anchor]+random.Random(seed).sample([d for d in domain.order if d not in (gpu,anchor)],6)
                emit("anchors",anchors)
                outcome=kim.run(ev,domain,seed,anchors,search.Clock(start,start+CFG["kim_generate_s"]),
                                clock,CFG,emit)
        end=clock.elapsed();emit("search_end",dict(summary=outcome,search_end_s=end))
        winner=min(accepted,key=lambda r:r["energy_j"]) if accepted else None
        result=asdict(ev._outcomes[winner["key"][0],tuple(winner["key"][1:])]) if winner else None
        save(dest/"result.json",dict(case_id=case,method=method,seed=seed,core=core,
             identity=instance.identity,required=instance.required,summary=outcome,winner=winner,result=result,
             search_end_s=end,incumbents=accepted,counts=dict(ev.counters),timings_s=dict(ev.seconds)))
    save(dest/"worker_end.json",dict(wall_s=clock.elapsed()))

def slot(case,method,seed,core,commit,stop):
    dest=folder(case,method,seed);dest.mkdir(parents=True,exist_ok=False)
    save(dest/"reservation.json",dict(case_id=case,method=method,seed=seed,core=core,
         execution_commit=commit,manifest_sha256=sha(HERE/"execution_manifest.json")))
    env=dict(os.environ,OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1",MKL_NUM_THREADS="1",NUMBA_NUM_THREADS="1",
             PYTHONDONTWRITEBYTECODE="1",PYTHONHASHSEED="0")
    with (dest/"console.txt").open("w",encoding="utf-8") as console:
        start=perf_counter()
        proc=subprocess.Popen([sys.executable,"-B","-X","utf8",str(HERE/"run_gap.py"),
           "--worker",case,method,str(seed),str(core),str(start)],env=env,stdout=console,stderr=console)
        try:
            proc.wait(max(0,CFG["cap_s"]-(perf_counter()-start)))
            state="finished" if proc.returncode==0 and (dest/"result.json").is_file() else "fault"
        except subprocess.TimeoutExpired:
            proc.kill();proc.wait();state="hard_timeout"
    wall=perf_counter()-start
    for name in ("events.jsonl","physical.jsonl"):
        p=dest/name
        if p.exists():
            (dest/(name+".gz")).write_bytes(gzip.compress(p.read_bytes(),compresslevel=6,mtime=0));p.unlink()
    save(dest/"receipt.json",dict(status=state,returncode=proc.returncode,total_wall_s=wall,
         files={p.name:sha(p) for p in sorted(dest.iterdir())}))
    print(case,method,seed,state,round(wall,2),flush=True)
    if state=="fault":
        stop.set()
        raise RuntimeError((dest/"console.txt").read_text(encoding="utf-8")[-2500:])

def batch():
    verify_freeze()
    assert not (HERE/"raw").exists(),"Refuse a second/overwriting batch"
    assert not subprocess.check_output(["git","diff","HEAD","--name-only"],cwd=ROOT,text=True).strip()
    commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    import platform,psutil
    save(HERE/"environment.json",dict(execution_commit=commit,python=sys.version,platform=platform.platform(),
         cpu=platform.processor(),cores=CFG["cores"],logical_cpus=psutil.cpu_count(),
         physical_cpus=psutil.cpu_count(logical=False),source_manifest_sha=sha(HERE/"execution_manifest.json")))
    rng=random.Random(CFG["queue_seed"]);cases=CFG["main_cases"].copy();rng.shuffle(cases)
    schedule=[]
    for index,case in enumerate(cases):
        jobs=[("M2-reference",0)]+[("Kim-Anytime+SAFE",s) for s in CFG["kim_seeds"]]
        rng.shuffle(jobs)
        schedule.append(dict(case_id=case,lane=index%len(CFG["cores"]),core=CFG["cores"][index%len(CFG["cores"])],jobs=jobs))
    save(HERE/"schedule.json",schedule)
    stop=Event()
    def lane(n):
        for block in schedule:
            if block["lane"]==n:
                for method,seed in block["jobs"]:
                    if stop.is_set():return
                    slot(block["case_id"],method,seed,block["core"],commit,stop)
    with ThreadPoolExecutor(max_workers=len(CFG["cores"])) as pool:
        futures=[pool.submit(lane,i) for i in range(len(CFG["cores"]))]
        for f in futures:f.result()
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--worker",nargs=5);a=p.parse_args()
    if a.worker:
        case,method,seed,core,start=a.worker
        worker(case,method,int(seed),int(core),float(start))
    else:batch()
