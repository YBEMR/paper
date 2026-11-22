"""One fresh process per case/method/seed. Budget starts before process launch."""
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
CFG = json.loads((HERE/"config.json").read_bytes())
CASES = [s+"_"+t for s in CFG["scene_configs"] for t in CFG["ambient_suffixes"]]
JOBS = [(c,m,k) for c in CASES for k in CFG["seeds"] for m in CFG["methods"]]


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def encode(obj):
    return json.dumps(obj,ensure_ascii=False,separators=(",",":"),allow_nan=False)


def write(path, obj):
    data = (encode(obj)+"\n").encode()
    tmp = path.with_suffix(path.suffix+".part")
    tmp.write_bytes(gzip.compress(data,compresslevel=3,mtime=0) if path.suffix==".gz" else data)
    tmp.replace(path)


def folder(job):
    return HERE/"units"/job[0]/f"{job[1]}_{job[2]}"


def worker(root,job,core,start):
    import psutil
    psutil.Process().cpu_affinity([core])
    sys.path[:0] = [str(root/"research/ch3_cooperative_cuts"),str(root/"research/ch3_final_experiments/p2")]
    import search
    from physical import Physical
    from catalog_ext import make_domain
    from optimizer import Explorer
    case,method,seed = job
    domain = make_domain(root)
    assert domain.size == CFG["deployments"]
    clock = search.Clock(start,start+CFG["admit_s"])
    ev = Physical(root,case,domain.stages)
    starts = ["A","C"]+random.Random(seed).sample([d for d in domain.legacy_ids if d not in ("A","C")],6)
    dest = folder(job)
    with gzip.open(dest/"events.jsonl.gz","wt",encoding="utf8",compresslevel=2) as stream:
        def emit(kind,payload,when=None):
            stream.write(encode([clock.elapsed() if when is None else when,kind,payload])+"\n")
        emit("identity",dict(job=job,starts=starts,domain=domain.size,requests_sha256=ev.identity))
        explorer = Explorer(ev,domain,seed,method,CFG,clock,emit)
        result = explorer.run(starts)
        end_s = clock.elapsed()
        key = explorer.best
        if key is None and explorer.returned:
            key = min(explorer.returned,key=lambda k:search.thermal_rank((k,explorer.returned[k])))
        if key is not None:
            write(dest/"selection.json.gz",ev.evidence(key[0],key[1:]))
        write(dest/"result.json.gz",dict(job=job,request_sha256=ev.identity,search_s=end_s,summary=result,
                                         selected=key,physical=asdict(explorer.returned[key]) if key else None,
                                         counters=dict(ev.counters)))


def slot(root,cache,index,core,inputs):
    job = JOBS[index]
    dest = folder(job)
    if (dest/"receipt.json").exists():
        rec = json.loads((dest/"receipt.json").read_bytes())
        if rec["inputs"]!=inputs or rec["job"]!=list(job):
            raise ValueError(f"Changed reservation: {dest}")
        return
    dest.mkdir(parents=True,exist_ok=False)
    write(dest/"reservation.json",dict(job=job,inputs=inputs,core=core,cap_s=CFG["cap_s"]))
    env = dict(os.environ,NUMBA_CACHE_DIR=str(cache),NUMBA_NUM_THREADS="1",OMP_NUM_THREADS="1",
               OPENBLAS_NUM_THREADS="1",MKL_NUM_THREADS="1",PYTHONDONTWRITEBYTECODE="1")
    with (dest/"console.txt").open("w") as stream:
        start = perf_counter()
        proc = subprocess.Popen([sys.executable,"-B","-X","utf8",str(HERE/"run.py"),"--root",str(root),
                                 "--worker",str(index),str(core),str(start)],env=env,stdout=stream,stderr=stream)
        try:
            proc.wait(max(0,CFG["cap_s"]-(perf_counter()-start)))
            state = "finished" if proc.returncode==0 and (dest/"result.json.gz").exists() else "fault"
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            state = "hard_timeout"
    elapsed = perf_counter()-start
    write(dest/"receipt.json",dict(job=job,inputs=inputs,core=core,elapsed_s=elapsed,state=state,
                                   exitcode=proc.returncode,files={p.name:digest(p) for p in sorted(dest.iterdir())}))
    print(index,*job,state,round(elapsed,2),flush=True)
    if state=="fault":
        raise RuntimeError((dest/"console.txt").read_text()[-1500:])


def batch(root,cache):
    inputs = {n:digest(HERE/n) for n in ("run.py","optimizer.py","config.json","frozen_inputs.json")}
    for n,h in json.loads((HERE/"frozen_inputs.json").read_bytes()).items():
        if digest(root/n)!=h:
            raise ValueError("Input drift: "+n)
    cache.mkdir(parents=True,exist_ok=True)
    order = list(range(len(JOBS)))
    random.Random(CFG["queue_seed"]).shuffle(order)
    def lane(core,jobs):
        for index in jobs:
            slot(root,cache,index,core,inputs)
    cores = CFG["cores"]
    with ThreadPoolExecutor(len(cores)) as pool:
        futures = [pool.submit(lane,core,order[i::len(cores)]) for i,core in enumerate(cores)]
        for f in futures:
            f.result()


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--jit-cache",type=Path)
    parser.add_argument("--worker",nargs=3)
    args = parser.parse_args()
    if args.worker:
        index,core,start = args.worker
        worker(args.root.resolve(),JOBS[int(index)],int(core),float(start))
    elif args.jit_cache:
        batch(args.root.resolve(),args.jit_cache.resolve())
    else:
        parser.error("--jit-cache required")
