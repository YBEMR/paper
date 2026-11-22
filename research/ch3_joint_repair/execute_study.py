"""One immutable time-box per method, seed and case; separate private process per unit."""
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

HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE/"config.json").read_bytes())
JOBS = [(c,m,k) for c in CONFIG["cases"] for k in CONFIG["seeds"] for m in CONFIG["new"]]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dumps(value):
    return json.dumps(value,separators=(",",":"),allow_nan=False)


def save(path, value):
    data = (dumps(value)+"\n").encode()
    tmp = path.with_name(path.name+".part")
    tmp.write_bytes(gzip.compress(data,compresslevel=3,mtime=0) if path.suffix==".gz" else data)
    os.replace(tmp,path)


def folder(job):
    case,method,seed = job
    return HERE/"units"/case/f"{method}_{seed}"


def inputs(root):
    frozen = json.loads((HERE/"inputs.json").read_bytes())
    for path,expected in frozen.items():
        if digest(root/path) != expected:
            raise ValueError(f"Frozen input drift: {path}")
    return {name:digest(HERE/name) for name in ("config.json","inputs.json","repair.py","execute_study.py")}


def worker(root, job, start, core):
    import psutil
    psutil.Process().cpu_affinity([core])
    case,method,seed = job
    sys.path[:0] = [str(root/"research/ch3_final_experiments/p2"),str(root/"research/ch3_cooperative_cuts")]
    import search
    from catalog_ext import make_domain
    from physical import Physical
    from repair import Repair

    clock=search.Clock(start,start+CONFIG["accept_s"])
    domain=make_domain(root)
    if len(domain.order)!=CONFIG["catalog"]:
        raise ValueError("Frozen deployment count differs")
    ev=Physical(root,case,domain.stages)
    dest=folder(job)
    with gzip.open(dest/"events.jsonl.gz","wt",encoding="utf8",compresslevel=1) as stream:
        def log(kind, payload, when=None):
            timestamp=clock.elapsed() if when is None else when
            stream.write(dumps([timestamp,kind,payload])+"\n")
        log("identity",dict(job=job,stream=ev.identity,ambient=ev.ambient,domain=domain.size))
        engine=Repair(domain,ev,seed,method,clock,log,CONFIG)
        summary=engine.run(CONFIG["initialize"])
        end=clock.elapsed()
        key=engine.best or min(engine.genomes,key=lambda k:search.thermal_rank((k,engine.genomes[k])),default=None)
        proof=ev.evidence(key[0],key[1:]) if key else None
        if proof:
            save(dest/"selection.json.gz",proof)
        save(dest/"result.json.gz",dict(job=job,safe=engine.best is not None,summary=summary,search_end_s=end,
                  first_safe_s=engine.first_safe_time,best_s=engine.best_time,request_sha256=ev.identity,
                  selected_genome=key,selected=asdict(engine.genomes[key]) if key else None,
                  physics_counts=dict(ev.counters)))


def slot(root, index, core, cache, hashes):
    job=JOBS[index]
    dest=folder(job)
    if (dest/"receipt.json").exists():
        receipt=json.loads((dest/"receipt.json").read_bytes())
        if receipt["job"]!=list(job) or receipt["inputs"]!=hashes:
            raise ValueError(f"Existing unit drift: {job}")
        return
    dest.mkdir(parents=True,exist_ok=False)
    save(dest/"reservation.json",dict(job=job,core=core,inputs=hashes,cap=CONFIG["cap_s"]))
    env=dict(os.environ,NUMBA_CACHE_DIR=str(cache),OPENBLAS_NUM_THREADS="1",MKL_NUM_THREADS="1",
             NUMBA_NUM_THREADS="1",OMP_NUM_THREADS="1",PYTHONDONTWRITEBYTECODE="1")
    with (dest/"console.txt").open("w",encoding="utf8") as stream:
        start=perf_counter()
        proc=subprocess.Popen([sys.executable,"-B","-X","utf8",str(Path(__file__)),"--source-root",str(root),
                               "--unit",str(index),str(core),str(start)],env=env,stdout=stream,stderr=stream)
        try:
            proc.wait(timeout=max(0,CONFIG["cap_s"]-(perf_counter()-start)))
            status="finished" if proc.returncode==0 and (dest/"result.json.gz").is_file() else "fault"
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            status="hard_timeout"
    elapsed=perf_counter()-start
    files={p.name:digest(p) for p in sorted(dest.iterdir())}
    save(dest/"receipt.json",dict(job=job,state=status,elapsed_s=elapsed,exitcode=proc.returncode,
                                  core=core,inputs=hashes,files=files))
    print(index,*job,status,round(elapsed,3),flush=True)
    if status=="fault":
        raise RuntimeError((dest/"console.txt").read_text("utf8")[-1600:])


def batch(root, cache):
    hashes=inputs(root)
    cache.mkdir(parents=True,exist_ok=True)
    order=list(range(len(JOBS)))
    random.Random(CONFIG["schedule_seed"]).shuffle(order)
    cores=CONFIG["cores"]
    def lane(core, tasks):
        for idx in tasks:
            slot(root,idx,core,cache,hashes)
    with ThreadPoolExecutor(len(cores)) as pool:
        futures=[pool.submit(lane,core,order[i::len(cores)]) for i,core in enumerate(cores)]
        for f in futures:
            f.result()


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-root",required=True,type=Path)
    p.add_argument("--jit-cache",type=Path)
    p.add_argument("--unit",nargs=3)
    args=p.parse_args()
    root=args.source_root.resolve()
    if args.unit:
        idx,core,start=args.unit
        worker(root,JOBS[int(idx)],float(start),int(core))
    else:
        if not args.jit_cache:
            p.error("--jit-cache required for the batch")
        batch(root,args.jit_cache.resolve())
