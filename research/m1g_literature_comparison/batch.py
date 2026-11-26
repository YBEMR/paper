"""Seven single-core lanes. Each public order runs all six methods in rotation."""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
RAW=Path(os.environ.get("M1G_BATCH",ROOT/"raw")).resolve()


def lane(number,core):
    os.sched_setaffinity(0,{core})
    os.environ["M1G_RAW"]=str(RAW/f"lane{number}")
    from experiment import OUT, METHODS, case_for, e, inputs, standalone, np
    from literature import HeatProbe
    import platform,numba,scipy
    assert os.sched_getaffinity(0)=={core}
    assert all(os.environ[k]=="1" for k in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS","NUMBA_NUM_THREADS"))
    dest=OUT/"literature"
    warm=e.p1.Engine("S32",OUT/"warm")
    warm.cert(*warm.construct("quota",1)[0])
    HeatProbe(warm.p).peak()
    for i,(phase,src) in enumerate(inputs()):
        if i%7!=number:
            continue
        c=case_for(src)
        # Warm common FIFO compiler, not an optimization call.
        c.ledger(bytes([0]),0,c.p.horizon,10000,False,False)
        e.p1.put(OUT/"environment.json",dict(lane=number,core=core,system=platform.platform(),python=sys.version,
                numba=numba.__version__,scipy=scipy.__version__,numpy=np.__version__,P1=e.p1.P1))
        order=METHODS[i%len(METHODS):]+METHODS[:i%len(METHODS)]
        for method in order:
            if method in ("NT","C2"):
                e.run(c,method,60.)
            else:
                result=standalone(c,method,dest)
                print(c.label,method,result["final_status"],round(result["wall_s"],3),flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--lane",type=int)
    parser.add_argument("--core",type=int)
    args=parser.parse_args()
    if args.lane is not None:
        lane(args.lane,args.core)
        return
    cores=sorted(os.sched_getaffinity(0))[-7:]
    assert len(cores)==7
    RAW.mkdir(parents=True,exist_ok=False)
    workers=[]
    for i,core in enumerate(cores):
        with (RAW/f"lane{i}.log").open("w") as log:
            workers.append(subprocess.Popen([sys.executable,"-Bu",__file__,"--lane",str(i),"--core",str(core)],
                            stdout=log,stderr=subprocess.STDOUT))
    codes=[p.wait() for p in workers]
    if any(codes):
        raise RuntimeError(codes)


if __name__=="__main__":
    main()

