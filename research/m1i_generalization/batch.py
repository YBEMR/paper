"""Execute the preregistered eight lanes; each case/method/repeat starts from empty."""
import argparse
import csv
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from design import ROOT,REPO,REG,sha,write_json

WORK=ROOT/"work"
DATA=ROOT/"data"
THREADS=("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS","NUMBA_NUM_THREADS")

def verify():
    frozen=json.loads((REG/"source_hashes.json").read_bytes())
    for name,digest in frozen.items():
        if sha((REPO/name).read_bytes())!=digest:raise ValueError(name)
    for row in json.loads((REG/"cases.json").read_bytes())["cases"]:
        assert sha((REG/"inputs"/row["input"]).read_bytes())==row["input_sha256"]

def lane(index,core):
    os.sched_setaffinity(0,{core})
    assert all(os.environ[k]=="1" for k in THREADS)
    work=WORK/"batch"/f"lane{index}"
    os.environ["M1G_RAW"]=str(work/"warm-runtime")
    from adapter import e,flow,template
    from runner import timed_run
    from archive import archive_run
    import numba,numpy,scipy
    from scipy.linalg import expm
    verify()
    assert os.sched_getaffinity(0)=={core}
    w=template()
    warm=e.p1.Engine("S32",work/"warm")
    warm.cert(*warm.construct("quota",1)[0])
    assert os.sched_getaffinity(0)=={core}
    write_json(DATA/"environment"/f"lane{index}.json",dict(lane=index,core=core,threads={k:os.environ[k] for k in THREADS},
               python=sys.version,numpy=numpy.__version__,scipy=scipy.__version__,numba=numba.__version__,host=platform.platform(),
               verified_manifest=sha((REG/"source_hashes.json").read_bytes()),P1=e.p1.P1))
    cases=json.loads((REG/"cases.json").read_bytes())["cases"]
    with (REG/"rotation.csv").open() as f:rotation=list(csv.DictReader(f))
    for item in cases:
        if item["index"]%8!=index:continue
        case=item["case"]
        for slot in (r for r in rotation if r["case"]==case):
            method=slot["method"];rep=slot["repeat"]
            tag=f"r{rep}-{method}"
            dest=work/case/tag
            c=flow(item,dest)
            timed_run(c,method,dest)
            archive_run(c,dest,DATA/"runs"/case/tag,WORK/"physical"/(case+".sqlite"),WORK/"events"/(case+".sqlite"))

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--lane",type=int);p.add_argument("--core",type=int)
    a=p.parse_args()
    if a.lane is not None:
        lane(a.lane,a.core)
        return
    verify()
    dst=WORK/"batch";dst.mkdir(parents=True,exist_ok=False)
    (WORK/"events").mkdir(parents=True,exist_ok=True)
    cores=sorted(os.sched_getaffinity(0))[-8:];assert len(cores)==8
    procs=[]
    for i,core in enumerate(cores):
        env=dict(os.environ,**{k:"1" for k in THREADS})
        with (dst/f"lane{i}.log").open("w") as f:
            procs.append(subprocess.Popen([sys.executable,"-Bu",__file__,"--lane",str(i),"--core",str(core)],env=env,stdout=f,stderr=subprocess.STDOUT))
    codes=[p.wait() for p in procs]
    if any(codes):raise RuntimeError(codes)
if __name__=="__main__":
    main()
