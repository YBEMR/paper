"""Serial matched order, single launch per reservation. Stop on authenticity or supervisor fault."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter

from worker import HERE,ROOT,CFG,write


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def slot_id(load,temp,seed,arm,fixed=False):
    return f"{load}_{temp}_{seed}_{arm}"+("_trace" if fixed else "")


def run_slot(args,case,seed,arm,freeze,fixed=False):
    load,temp=case
    slot=slot_id(load,temp,seed,arm,fixed)
    folder=HERE/"units"/slot
    folder.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,NUMBA_CACHE_DIR=str(args.cache.resolve()),NUMBA_NUM_THREADS="1",
             MKL_NUM_THREADS="1",OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1",PYTHONDONTWRITEBYTECODE="1")
    command=[sys.executable,"-B","-X","utf8",str(HERE/"worker.py"),"--source",str(args.source.resolve()),
             "--slot",slot,"--load",load,"--temp",str(temp),"--seed",str(seed),"--arm",arm]
    if fixed: command+=["--fixed",slot_id(*case,seed,"A")]
    write(folder/"reservation.json",dict(freeze=freeze,case=case,seed=seed,arm=arm,trace=fixed,
          source_hash=sha(HERE/"identity.json"),core=CFG["core"],concurrent=1,cap=120))
    with (folder/"console.txt").open("w",encoding="utf8") as console:
        start=perf_counter()
        proc=subprocess.Popen(command+["--start",str(start)],stdout=console,stderr=console,env=env)
        try:
            proc.wait(timeout=max(0,120-(perf_counter()-start)))
            state="finished" if proc.returncode==0 and (folder/"result.json").exists() else "fault"
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            state="hard_timeout"
    wall=perf_counter()-start
    write(folder/"receipt.json",dict(slot=slot,state=state,returncode=proc.returncode,wall_s=wall,
                freeze=freeze,files={p.name:sha(p) for p in sorted(folder.iterdir())}))
    print(slot,state,round(wall,3),flush=True)
    if state!="finished": raise RuntimeError(f"{slot}: "+(folder/"console.txt").read_text()[-2000:])
    return json.loads((folder/"result.json").read_bytes())


def main(args):
    freeze=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    cases,seeds=CFG["cases"],CFG["seeds"]
    a=run_slot(args,cases[0],seeds[0],"A",freeze)
    b=run_slot(args,cases[0],seeds[0],"B",freeze)
    fixed=[run_slot(args,cases[0],seeds[0],arm,freeze,True) for arm in "AB"]
    with gzip.open(HERE/"units"/a["slot"]/"flow.jsonl.gz","rt",encoding="utf8") as f:
        expected=sum(json.loads(line)[4]<=20 for line in f)
    n=[r["summary"]["checked"] for r in fixed]
    if min(n)<=0 or any(r["summary"]["truncated"] or k!=expected for r,k in zip(fixed,n)):
        write(HERE/"units/trace_gate.json",dict(full_prefix=False,expected=expected,completed=n))
        raise RuntimeError("Fixed flow incomplete; no decision on acceleration")
    counts=b["meter"][1]
    shapes=b["gate_cold_counts"]
    enable=bool(len(shapes)>=2 and max(shapes)>0 and min(shapes)<4 and
                counts.get("kernel_builds") and counts.get("kernel_queries") and counts.get("peak_replays"))
    write(HERE/"units/trace_gate.json",dict(full_prefix=True,expected=expected,completed=n,
        C_enabled=enable,observed_cold_counts=shapes,builds=counts.get("kernel_builds"),
        queries=counts.get("kernel_queries"),peak_replays=counts.get("peak_replays")))
    print("fixed prefix",expected,"C enabled",enable,flush=True)
    arms="ABC" if enable else "AB"
    if enable: run_slot(args,cases[0],seeds[0],"C",freeze)
    for k,(seed,case) in enumerate((s,c) for s in seeds for c in cases):
        if k==0: continue
        offset=k%len(arms)
        for arm in arms[offset:]+arms[:offset]:
            run_slot(args,case,seed,arm,freeze)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",type=Path,default=ROOT)
    parser.add_argument("--cache",type=Path,required=True)
    main(parser.parse_args())
