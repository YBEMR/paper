"""Six pinned single-thread lanes. Input and execution order are read from registration."""
import argparse
import csv
import json
import os
import platform
import subprocess
import sys
from paths_j import ROOT,REG,WORK,DATA,REPO,inputs,sha,write_json

THREADS=("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS","NUMBA_NUM_THREADS")

def verify():
    for rel,expected in json.loads((REG/"hashes.json").read_bytes()).items():
        assert sha((REPO/rel).read_bytes())==expected,rel
    assert inputs()==json.loads((REG/"cases.json").read_bytes())

def lane(index,core):
    os.sched_setaffinity(0,{core})
    assert all(os.environ[k]=="1" for k in THREADS)
    work=WORK/"batch"/f"lane{index}"
    os.environ["M1G_RAW"]=str(work/"warm-runtime")
    from archive import archive_run
    from retention import timed_run
    from adapter import e,flow,template
    import numba,numpy,scipy
    verify()
    template()
    warm=e.p1.Engine("S32",work/"warm")
    warm.cert(*warm.construct("quota",1)[0])
    assert os.sched_getaffinity(0)=={core}
    write_json(DATA/"environment"/f"lane{index}.json",dict(lane=index,core=core,
               threads={k:os.environ[k] for k in THREADS},python=sys.version,numpy=numpy.__version__,
               numba=numba.__version__,scipy=scipy.__version__,platform=platform.platform(),P1=e.p1.P1,
               manifest=sha((REG/"hashes.json").read_bytes())))
    with (REG/"rotation.csv").open() as f:slots=list(csv.DictReader(f))
    for c in inputs():
        if c["index"]%6!=index:continue
        for s in (r for r in slots if r["case"]==c["case"]):
            tag=f"r{s['repeat']}-{s['method']}"
            dest=work/c["case"]/tag
            item=flow(c,dest)
            timed_run(item,s["method"],dest)
            archive_run(item,dest,DATA/"runs"/c["case"]/tag,WORK/"physical"/(c["case"]+".sqlite"),WORK/"events"/(c["case"]+".sqlite"))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--lane",type=int);parser.add_argument("--core",type=int)
    a=parser.parse_args()
    if a.lane is not None:
        lane(a.lane,a.core)
        return
    verify()
    out=WORK/"batch";out.mkdir(parents=True,exist_ok=False)
    (WORK/"events").mkdir(parents=True,exist_ok=True)
    cores=sorted(os.sched_getaffinity(0))[-6:];assert len(cores)==6
    processes=[]
    for i,core in enumerate(cores):
        env=dict(os.environ,**{k:"1" for k in THREADS})
        with (out/f"lane{i}.log").open("w") as f:
            processes.append(subprocess.Popen([sys.executable,"-Bu",__file__,"--lane",str(i),"--core",str(core)],env=env,stdout=f,stderr=subprocess.STDOUT))
    codes=[p.wait() for p in processes]
    if any(codes): raise RuntimeError(codes)

if __name__=="__main__":main()
