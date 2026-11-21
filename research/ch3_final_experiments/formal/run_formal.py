"""Cold formal runs. Start from the repository root with --source-root pointing at frozen research/."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from time import perf_counter
import traceback

HERE = Path(__file__).resolve().parent
P2 = HERE.parent/"p2"
sys.path.insert(0, str(P2))
CORES = (0, 2, 4, 6)
METHODS = ("Kim-Adapt", "Kim-Adapt+SAFE", "Thermal-GA")
SEEDS = (20261121, 20261122, 20261123, 20261124, 20261125)
SCENES = ("forward_flat", "forward_alternating", "reverse_flat", "reverse_alternating")
PRESSURE = ("A", "C", "D001", "D015")
SUBJECT = "ba774cd2c90f7abdbcc1edb1c331a592ce989a4f"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def put(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, allow_nan=False, ensure_ascii=False, separators=(",", ":"))+"\n",
                   encoding="utf8", newline="\n")
    os.replace(tmp, path)


def jobs():
    setups = [(s+"_25C",81) for s in SCENES] + [("reverse_flat_25C",4),("reverse_flat_27p5C",4)]
    return [(case, domain, method, seed) for case,domain in setups for seed in SEEDS for method in METHODS]


def records(path):
    with path.open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))


def config(job):
    case,size,method,seed=job
    return next(r for r in records(HERE/"formal_experiment_config.csv") if r["source"]=="formal"
                and int(r["methods_domain"])==size and r["method"]==method and case in r["case_ids"].split("|")
                and str(seed) in r["seeds"].split("|"))


def inspect_pool(pool, ev, clock, limit, emit):
    """Reuse P2 single-candidate continuous validation for every distinct ordered candidate."""
    import search
    from collections import Counter
    seen=set()
    checks=duplicates=0
    attempts=[]
    stop="empty_pool" if not pool else "exhausted"
    winner=None
    for c in pool:
        key=c.dep,c.opps
        if key in seen:
            duplicates+=1
            continue
        seen.add(key)
        step=search.inspect_kim([c],False,ev.replay,clock,emit)
        checks+=step["checks_started"]
        attempts.extend(step["attempts"])
        if step["reason"] in ("first_safe","timeout"):
            winner,stop=step["winner"],step["reason"]
            break
        if len(attempts)>=limit:
            stop="first_only" if limit==1 else "exhausted"
            break
    return dict(winner=winner,reason=stop,attempts=attempts,duplicates=duplicates,checks_started=checks,
                status_counts=dict(Counter(r["result"]["status"] for r in attempts)),
                first_safe_s=attempts[-1]["at_s"] if winner else None,scope="checked_individuals_only")


def setup(root, case, size, emit):
    import evaluator
    instance = next(r for r in records(HERE.parent/"derived/instances.csv") if r["instance_id"]==case)
    evaluator.CASES[case] = (float(instance["ambient_c"]),instance["scene_order"].split("/"),
                             list(map(int,instance["frames_execution_order"].split("/"))),instance["request_sha"])
    catalog = json.loads((root/"research/kim_multidnn_expansion/catalog.json").read_bytes())
    allowed = catalog["search_order"] if size==81 else PRESSURE
    if len(allowed)!=size:
        raise ValueError("deployment domain differs")
    return evaluator.Evaluator(root, case, allowed, emit)


class Journal:
    def __init__(self, stream, start):
        self.stream, self.start = stream, start
        self.schedules = {}
        self.best_failure = None

    def emit(self, event, value):
        # Completion vectors reference the verified absolute workload in its original order.
        if event=="physical":
            value=dict(value)
            refs=[]
            rows=value.pop("completions")
            if rows:
                for j,scene in enumerate(value["physical"]["scene_rows"]):
                    key=(value["dep"],j,value["indices"][j])
                    finishes=[r["completion_ns"] for r in rows if r["scene"]==scene["scene"]]
                    if key not in self.schedules:
                        self.schedules[key]=finishes
                        self.emit("completion_vector",dict(key=key,finish_ns=finishes))
                    elif self.schedules[key]!=finishes:
                        raise ValueError("inconsistent repeated completion vector")
                    refs.append(key)
            value["completion_keys"]=refs
        if event in ("ga_position","kim_check"):
            from search import Result, thermal_rank
            r=Result(**value["result"])
            key=tuple(value["genome"]) if event=="ga_position" else (value["dep"],*value["opps"])
            if r.status!="SAFE":
                rank=thermal_rank((key,r))
                if self.best_failure is None or rank<self.best_failure[0]:
                    self.best_failure=(rank,dict(genome=key,result=value["result"]))
        row=[round(perf_counter()-self.start,6),event,value]
        self.stream.write(json.dumps(row,separators=(",",":"),allow_nan=False)+"\n")


def worker(root, index, out, start, core):
    import psutil
    psutil.Process().cpu_affinity([core])
    import search
    case,size,method,seed=jobs()[index]
    rule=config(jobs()[index])
    population=int(rule["population"])
    generations=int(rule["max_generations"])
    if method=="Thermal-GA":
        search.GA_POP,search.GA_GENS=population,generations
    else:
        search.KIM_POP,search.KIM_GENS=population,generations
    for filename,expected in (("search.py","9d8145253a56a0d2f3991518eaf50c864414d83574b826f0872c132d89c7165e"),
                              ("evaluator.py","b013404c8855d91a254844c80929b741f3ebc13e85516666ac8f8c0b0e614134")):
        if sha(P2/filename)!=expected:
            raise RuntimeError("P2 freeze mismatch")
    clock=search.Clock(start,start+int(rule["accept_cutoff_s"]))
    with gzip.open(out/"events.jsonl.gz","xt",encoding="utf8",compresslevel=1,newline="\n") as stream:
        journal=Journal(stream,start)
        ev=setup(root,case,size,journal.emit)
        identity=dict(case=case,domain=size,method=method,seed=seed,request_sha256=ev.identity,
                      allowed=ev.domain.order,core=core,init_s=clock.elapsed(),subject=SUBJECT,
                      runner_sha=sha(Path(__file__)),config_sha=sha(HERE/"formal_experiment_config.csv"),
                      pool_size=population,max_generations=generations)
        journal.emit("identity",identity)
        if method=="Thermal-GA":
            summary=search.thermal_ga(ev.domain,ev.replay,seed,clock,journal.emit)
        else:
            generation_clock=search.Clock(start,start+int(rule["generation_cutoff_s"]))
            pool,info=search.kim_pool(ev.domain,ev.proxy,seed,generation_clock,journal.emit)
            summary=inspect_pool(pool,ev,clock,int(rule["max_total_checks"]),journal.emit)
            summary["pool"]=info
        best=journal.best_failure[1] if journal.best_failure else None
    put(out/"result.json",dict(identity=identity,summary=summary,best_failed_diagnostic=best,
                               worker_s=perf_counter()-start))


def slot(root,index,core):
    out=HERE/"runs"/f"u{index:03d}"
    if out.exists():
        if (out/"receipt.json").is_file():
            return
        raise RuntimeError("unsettled slot "+out.name)
    out.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="ch3-numba-") as d:
        env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1","NUMBA_CACHE_DIR":d,"NUMBA_NUM_THREADS":"1",
             "OMP_NUM_THREADS":"1","MKL_NUM_THREADS":"1","OPENBLAS_NUM_THREADS":"1"}
        cap=int(config(jobs()[index])["wall_cap_s"])
        start=perf_counter()
        put(out/"reservation.json",dict(index=index,job=jobs()[index],core=core,cap_s=cap,
                                        config_sha=sha(HERE/"formal_experiment_config.csv"),
                                        runner_sha=sha(Path(__file__)),start=start))
        with (out/"console.txt").open("w",encoding="utf8") as log:
            p=subprocess.Popen([sys.executable,"-B","-X","utf8",str(HERE/"run_formal.py"),
                                "--source-root",str(root),"--worker",str(index),str(start),str(core)],
                               stdout=log,stderr=log,env=env)
            try:
                p.wait(timeout=max(0,start+cap-perf_counter()))
                state="finished" if p.returncode==0 and (out/"result.json").exists() else "fault"
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
                state="hard_timeout"
        duration=perf_counter()-start
        put(out/"receipt.json",dict(state=state,elapsed_s=duration,exitcode=p.returncode,
                                    result_sha=sha(out/"result.json") if (out/"result.json").exists() else None))
    print(out.name,state,round(duration,2),flush=True)
    if state=="fault":
        raise RuntimeError((out/"console.txt").read_text("utf8")[-1800:])


def batch(root):
    def lane(core,indices):
        for i in indices:
            slot(root,i,core)
    for group in (list(range(60)),list(range(60,90))):
        with ThreadPoolExecutor(len(CORES)) as pool:
            futures=[pool.submit(lane,core,group[j::len(CORES)]) for j,core in enumerate(CORES)]
            for f in futures:
                f.result()


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--source-root",type=Path,required=True)
    parser.add_argument("--worker",nargs=3)
    args=parser.parse_args()
    if args.worker:
        i,t,core=args.worker
        worker(args.source_root.resolve(),int(i),HERE/"runs"/f"u{int(i):03d}",float(t),int(core))
    else:
        batch(args.source_root.resolve())
