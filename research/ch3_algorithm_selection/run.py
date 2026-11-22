"""Formal selection batch. One cold search per worker; timer starts before process creation."""
import argparse
from collections import Counter
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

from loads import CFG, HERE, install

ROOT = HERE.parents[1]
JOBS = [(load,temp,seed,method) for load in CFG["loads"] for temp in CFG["temperatures"]
        for seed in CFG["seeds"] for method in [*CFG["main"],"energy_safe_parent"]]


def encoded(value):
    return json.dumps(value, separators=(",",":"), allow_nan=False).encode()


def save(path, value):
    data = encoded(value)+b"\n"
    path.write_bytes(gzip.compress(data, compresslevel=3, mtime=0) if path.suffix==".gz" else data)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dest(job):
    load,temp,seed,method = job
    return HERE/"units"/f"{load}_{temp}C"/f"{method}_{seed}"


def worker(root, index, core, start):
    import psutil
    psutil.Process().cpu_affinity([core])
    sys.path[:0] = [str(root/"research/ch3_final_experiments/p2"), str(root/"research/ch3_cooperative_cuts"),
                    str(ROOT/"research/ch3_joint_repair"),str(ROOT/"research/ch3_energy_repair")]
    import search
    from catalog_ext import make_domain
    from physical import Physical
    from optimizer import Explorer
    from repair import Repair
    import kim_anytime

    class SafeParentExplorer(Explorer):
        def parent(self, round_index):
            # Mask only parent eligibility. Retain all offspring, measurements, restarts and SAFE ranking.
            archives = self.archives
            self.archives = {"SAFE": archives["SAFE"], "VIOLATION": {}}
            try:
                return super().parent(round_index)
            finally:
                self.archives = archives

    job = JOBS[index]
    load,temp,seed,method = job
    clock = search.Clock(start,start+CFG["admit_s"])
    domain = make_domain(root)
    if domain.size != CFG["domain"]:
        raise ValueError("Wrong domain")
    ev = Physical(root,f"forward_flat_{temp}C",domain.stages)
    install(ev,load)
    folder = dest(job)
    with gzip.open(folder/"events.jsonl.gz","wb",compresslevel=1) as stream:
        def emit(kind, value, when=None):
            stream.write(encoded([clock.elapsed() if when is None else when, kind,value])+b"\n")
        emit("identity",dict(job=job,domain=domain.size,stream=ev.identity))
        if method == "joint":
            config = json.loads((ROOT/"research/ch3_joint_repair/config.json").read_bytes())
            summary = Repair(domain,ev,seed,method,clock,emit,config).run(config["initialize"])
        else:
            anchors = ["A","C"]+random.Random(seed).sample([d for d in domain.legacy_ids if d not in ("A","C")],6)
            if method == "kim_anytime":
                summary = kim_anytime.run(ev,domain,seed,anchors,search.Clock(start,start+CFG["kim_generate_s"]),
                                          clock,CFG,emit)
            else:
                config = json.loads((ROOT/"research/ch3_energy_repair/config.json").read_bytes())
                solver = Explorer if method == "energy_only" else SafeParentExplorer
                summary = solver(ev,domain,seed,"energy_only",config,clock,emit).run(anchors)
        end_s = clock.elapsed()
        key = summary["winner"]
        if key:
            proof = ev.evidence(key[0],key[1:])
            result = asdict(ev._outcomes[key[0],tuple(key[1:])])
            if result["status"] != "SAFE":
                raise ValueError("Selected policy lacks exact certificate")
            save(folder/"selection.json.gz",proof)
        else:
            result = None
        save(folder/"result.json.gz",dict(job=job,request_sha=ev.identity,search_end_s=end_s,summary=summary,
                                         key=key,result=result,physics_counts=dict(ev.counters)))


def inputs(root):
    registered = json.loads((ROOT/"research/ch3_joint_repair/inputs.json").read_bytes())
    registered.update(json.loads((ROOT/"research/ch3_energy_repair/frozen_inputs.json").read_bytes()))
    for name,expected in registered.items():
        if digest(root/name) != expected:
            raise ValueError(f"Frozen dependency changed: {name}")
    paths = [HERE/n for n in ("loads.py","run.py","kim_anytime.py","config.json")]
    paths += sorted((HERE/"streams").glob("*.json"))
    paths += [ROOT/"research"/name/file for name,file in [
        ("ch3_energy_repair","config.json"),("ch3_energy_repair","optimizer.py"),
        ("ch3_joint_repair","config.json"),("ch3_joint_repair","repair.py")]]
    return {p.relative_to(ROOT).as_posix():digest(p) for p in paths}


def slot(root, cache, index, core, sources):
    job, folder = JOBS[index], dest(JOBS[index])
    folder.mkdir(parents=True,exist_ok=False)
    save(folder/"reservation.json",dict(job=job,core=core,inputs=sources))
    env = dict(os.environ,NUMBA_CACHE_DIR=str(cache),NUMBA_NUM_THREADS="1",OMP_NUM_THREADS="1",
               OPENBLAS_NUM_THREADS="1",MKL_NUM_THREADS="1",PYTHONDONTWRITEBYTECODE="1")
    with (folder/"console.txt").open("w") as out:
        start = perf_counter()
        proc = subprocess.Popen([sys.executable,"-B","-X","utf8",str(HERE/"run.py"),"--source",str(root),
                                 "--worker",str(index),str(core),str(start)],env=env,stdout=out,stderr=out)
        try:
            proc.wait(max(0,CFG["cap_s"]-(perf_counter()-start)))
            status = "finished" if proc.returncode==0 and (folder/"result.json.gz").is_file() else "fault"
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            status = "hard_timeout"
    wall_s = perf_counter()-start
    save(folder/"receipt.json",dict(job=job,core=core,wall_s=wall_s,status=status,returncode=proc.returncode,
                                   files={p.name:digest(p) for p in sorted(folder.iterdir())}))
    print(index,*job,status,round(wall_s,2),flush=True)
    if status == "fault":
        raise RuntimeError((folder/"console.txt").read_text()[-2500:])


def batch(root,cache,ablation):
    sources = inputs(root)
    indices = [i for i,job in enumerate(JOBS) if (job[-1]=="energy_safe_parent")==ablation]
    random.Random(CFG["schedule_seed"]).shuffle(indices)
    def lane(core, items):
        for index in items:
            slot(root,cache,index,core,sources)
    cores = CFG["cores"]
    with ThreadPoolExecutor(max_workers=len(cores)) as pool:
        futures = [pool.submit(lane,core,indices[j::len(cores)]) for j,core in enumerate(cores)]
        for future in futures:
            future.result()


if __name__=="__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source",type=Path,default=ROOT)
    parser.add_argument("--cache",type=Path,default=Path(os.getenv("TEMP","/tmp"))/"ch3-selection-numba")
    parser.add_argument("--ablation",action="store_true")
    parser.add_argument("--worker",nargs=3)
    args = parser.parse_args()
    if args.worker:
        index,core,start = args.worker
        worker(args.source.resolve(),int(index),int(core),float(start))
    else:
        batch(args.source.resolve(),args.cache.resolve(),args.ablation)
