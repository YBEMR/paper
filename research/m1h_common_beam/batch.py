"""One fresh 60-second run per method/order; seven single-threaded independent lanes."""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = Path(os.environ.get("M1H_OUTPUT",ROOT/"raw")).resolve()
THREADS = ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS","NUMBA_NUM_THREADS")


def lane(index,core):
    os.sched_setaffinity(0,{core})
    os.environ["M1G_RAW"] = str(RAW/f"lane{index}")
    from framework import METHODS,case_for,e,inputs,run
    import scipy,numba
    assert os.sched_getaffinity(0)=={core} and all(os.environ[k]=="1" for k in THREADS)
    frozen=json.loads((e.ROOT/"holdout_freeze.json").read_bytes())["algorithm"]
    assert all(hashlib.sha256((e.ROOT/k).read_bytes()).hexdigest()==v for k,v in frozen.items())
    warm=e.p1.Engine("S32",RAW/f"lane{index}"/"warm")
    warm.cert(*warm.construct("quota",1)[0])
    e.p1.put(e.DATA/"environment.json",dict(lane=index,core=core,threads={k:os.environ[k] for k in THREADS},
           protocol_sha256=hashlib.sha256((ROOT/"PROTOCOL.md").read_bytes()).hexdigest(),
           implementation_sha256=hashlib.sha256((ROOT/"framework.py").read_bytes()).hexdigest(),
           python=sys.version,platform=platform.platform(),P1=e.p1.P1,numpy=e.np.__version__,scipy=scipy.__version__,numba=numba.__version__))
    for i,(_,path) in enumerate(inputs()):
        if i%7!=index:
            continue
        case=case_for(path)
        for method in METHODS[i%5:]+METHODS[:i%5]:
            run(case,method)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--lane",type=int)
    p.add_argument("--core",type=int)
    args=p.parse_args()
    if args.lane is not None:
        lane(args.lane,args.core)
        return
    cores=sorted(os.sched_getaffinity(0))[-7:]
    assert len(cores)==7
    RAW.mkdir(parents=True,exist_ok=False)
    jobs=[]
    env=dict(os.environ,**{k:"1" for k in THREADS})
    for index,core in enumerate(cores):
        with (RAW/f"lane{index}.log").open("w") as log:
            jobs.append(subprocess.Popen([sys.executable,"-Bu",__file__,"--lane",str(index),"--core",str(core)],
                                         env=env,stdout=log,stderr=subprocess.STDOUT))
    exits=[p.wait() for p in jobs]
    if any(exits):
        raise RuntimeError(exits)


if __name__=="__main__":
    main()
