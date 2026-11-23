"""One preregistered paired batch. No oracle values are read by a worker."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import gzip
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
from time import perf_counter

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
CFG=json.loads((HERE/"protocol.json").read_bytes())
PAIRS=[(case,seed) for case in CFG["cases"] for seed in CFG["seeds"]]

def encoded(v):
    return json.dumps(v,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
def save(p,v):
    p.write_bytes(encoded(v)+b"\n")
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def destination(case,seed,method):
    return HERE/"raw"/case/f"{method}_{seed}"

def verify_manifest():
    sources=json.loads((HERE/"execution_manifest.json").read_bytes())
    for relative,expected in sources.items():
        if sha(ROOT/relative)!=expected:
            raise ValueError("Execution/input drift: "+relative)
    return sources

def worker(case,seed,method,core,start):
    import psutil
    psutil.Process().cpu_affinity([core])
    verify_manifest()
    from common import Instance,Physical,domain_for,energy_explorer,search,kim_anytime,events
    from unittest.mock import patch
    folder=destination(case,seed,method)
    clock=search.Clock(start,start+CFG["admit_s"])
    inst=Instance(case)
    domain=domain_for(inst)
    ev=Physical(inst,domain)
    proof_count=0
    accepted=[]
    with (folder/"events.jsonl").open("xb") as log, (folder/"certificates.jsonl").open("xb") as certs:
        def emit(kind,value,when=None):
            nonlocal proof_count
            if kind=="physical":
                value=dict(value,identity=ev.identity,required=inst.required,ambient_c=inst.ambient,
                           initial_c=inst.initial)
                certs.write(encoded(dict(t_s=clock.elapsed(),data=value))+b"\n")
                certs.flush()
                value=dict(dep=value["dep"],indices=value["indices"],
                           status=value["physical"]["thermal_status"],energy_j=value["physical"]["energy_j"])
            if kind=="incumbent":
                key,energy=value
                proof=ev.evidence(key[0],key[1:])
                assert proof["physical"]["thermal_status"]=="SAFE"
                proof_count+=1
                filename=f"incumbent_{proof_count:03d}.json.gz"
                (folder/filename).write_bytes(gzip.compress(encoded(proof)+b"\n",compresslevel=1,mtime=0))
                # Only fully written, independently checked evidence within the wall cap counts.
                when=clock.elapsed()
                if when<=CFG["cap_s"]:
                    accepted.append(dict(t_s=when,key=key,energy_j=energy,proof=filename))
                value=dict(key=key,energy_j=energy,proof=filename,accepted=when<=CFG["cap_s"])
            log.write(encoded(dict(t_s=clock.elapsed() if when is None else when,kind=kind,data=value))+b"\n")
            log.flush()
        ev.emit=emit
        anchors=["A","C"]+random.Random(seed).sample([d for d in domain.legacy_ids if d not in ("A","C")],6)
        emit("identity",dict(case=inst.case,identity=inst.identity,method=method,seed=seed,core=core,
                            anchors=anchors,domain=domain.order,opps=search.OPPS,initialization_s=clock.elapsed()))
        original_mapping=search.evaluate_mapping
        original_thermal=events.evaluate_thermal
        def mapping(dep,observe):
            t=perf_counter()
            ev.counters["setfreq_mapping_calls"]+=1
            try:
                value=original_mapping(dep,observe)
            finally:
                ev.seconds["setfreq_mapping_inclusive_s"]+=perf_counter()-t
            emit("setfreq_mapping",dict(dep=dep,opps=value.opps,valid_scenes=value.valid,compute_s=perf_counter()-t))
            return value
        def thermal(*args,**kwargs):
            t=perf_counter()
            ev.counters["thermal_evaluate_calls"]+=1
            try:
                return original_thermal(*args,**kwargs)
            finally:
                ev.seconds["thermal_evaluate_s"]+=perf_counter()-t
        with patch.object(search,"evaluate_mapping",mapping),patch.object(events,"evaluate_thermal",thermal):
            if method=="kim_anytime_safe":
                result=kim_anytime.run(ev,domain,seed,anchors,
                    search.Clock(start,start+CFG["kim_generate_s"]),clock,CFG,emit)
            elif method=="energy_only":
                config=json.loads((ROOT/"research/ch3_energy_repair/config.json").read_bytes())
                result=energy_explorer()(ev,domain,seed,"energy_only",config,clock,emit).run(anchors)
            else:
                raise ValueError(method)
        finish=clock.elapsed()
        emit("search_end",dict(summary=result,search_end_s=finish))
        winner=min(accepted,key=lambda x:x["energy_j"]) if accepted else None
        details=asdict(ev._outcomes[winner["key"][0],tuple(winner["key"][1:])]) if winner else None
        save(folder/"result.json",dict(case_id=case,method=method,seed=seed,identity=inst.identity,
             required=inst.required,core=core,search_end_s=finish,summary=result,winner=winner,
             first_safe_s=accepted[0]["t_s"] if accepted else None,result=details,
             physics_counts=dict(ev.counters),timings_s=dict(ev.seconds),incumbents=accepted))
    save(folder/"worker_end.json",dict(wall_s=clock.elapsed()))

def slot(case,seed,method,core,sources,commit):
    folder=destination(case,seed,method)
    folder.mkdir(parents=True,exist_ok=False)
    save(folder/"reservation.json",dict(case_id=case,seed=seed,method=method,core=core,
         execution_commit=commit,manifest_sha256=sha(HERE/"execution_manifest.json")))
    env=dict(os.environ,OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1",MKL_NUM_THREADS="1",
             NUMBA_NUM_THREADS="1",PYTHONDONTWRITEBYTECODE="1",PYTHONHASHSEED="0")
    with (folder/"console.txt").open("w",encoding="utf-8") as console:
        start=perf_counter()
        proc=subprocess.Popen([sys.executable,"-B","-X","utf8",str(HERE/"run.py"),
               "--worker",case,str(seed),method,str(core),str(start)],env=env,stdout=console,stderr=console)
        try:
            proc.wait(max(0,CFG["cap_s"]-(perf_counter()-start)))
            status="finished" if proc.returncode==0 and (folder/"result.json").is_file() else "fault"
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            status="hard_timeout"
    wall=perf_counter()-start
    # Archival compression only, AFTER the measured search process. No evaluations here.
    for name in ("events.jsonl","certificates.jsonl"):
        p=folder/name
        if p.exists():
            raw=p.read_bytes()
            (folder/(name+".gz")).write_bytes(gzip.compress(raw,compresslevel=6,mtime=0))
            p.unlink()
    save(folder/"receipt.json",dict(case_id=case,seed=seed,method=method,core=core,status=status,
         total_wall_s=wall,returncode=proc.returncode,
         files={p.name:sha(p) for p in sorted(folder.iterdir())}))
    print(case,seed,method,status,round(wall,2),flush=True)
    if status=="fault":
        raise RuntimeError((folder/"console.txt").read_text(encoding="utf-8")[-3000:])

def batch():
    sources=verify_manifest()
    if (HERE/"raw").exists():
        raise RuntimeError("Refuse to overwrite or automatically append a second batch")
    commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    changed=subprocess.check_output(["git","status","--porcelain","--untracked-files=no"],cwd=ROOT,text=True)
    assert not changed,"Tracked files must match the execution freeze"
    import platform,psutil
    save(HERE/"environment.json",dict(python=sys.version,executable=sys.executable,platform=platform.platform(),
         processor=platform.processor(),logical_cpus=psutil.cpu_count(),physical_cpus=psutil.cpu_count(logical=False),
         cpu_affinity=psutil.Process().cpu_affinity(),execution_commit=commit,protocol=CFG,
         source_manifest_sha256=sha(HERE/"execution_manifest.json")))
    indices=list(range(len(PAIRS)))
    random.Random(CFG["queue_seed"]).shuffle(indices)
    schedule=[]
    for lane,core in enumerate(CFG["cores"]):
        for ordinal,index in enumerate(indices[lane::len(CFG["cores"])]):
            methods=CFG["methods"] if (lane+ordinal)%2==0 else list(reversed(CFG["methods"]))
            schedule.append(dict(lane=lane,core=core,index=index,case_id=PAIRS[index][0],
                                 seed=PAIRS[index][1],methods=methods))
    save(HERE/"schedule.json",schedule)
    def lane_run(lane):
        for row in schedule:
            if row["lane"]==lane:
                for method in row["methods"]:
                    slot(row["case_id"],row["seed"],method,row["core"],sources,commit)
    with ThreadPoolExecutor(max_workers=len(CFG["cores"])) as pool:
        futures=[pool.submit(lane_run,i) for i in range(len(CFG["cores"]))]
        for future in futures:
            future.result()

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--worker",nargs=5)
    args=parser.parse_args()
    if args.worker:
        case,seed,method,core,start=args.worker
        worker(case,int(seed),method,int(core),float(start))
    else:
        batch()
