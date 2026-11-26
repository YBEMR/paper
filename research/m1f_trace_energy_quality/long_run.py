"""Run the four frozen methods on each public order with a common 60 s horizon."""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / "m1e_thermal_quota_ablation"
HOLD = ROOT.parent / "m1_independent_holdout"
OUT = Path(os.environ.get("M1F_OUTPUT", ROOT/"raw")).resolve()
METHODS = ("NT","NC","OT","C2")

def inputs():
    result = []
    for phase, path in (("development8",BASE),("former_holdout6",HOLD)):
        files = (path/"data/validation_inputs").glob("*.csv")
        for f in sorted(files,key=lambda p:(-int(p.stem.split("_")[0][1:]),p.stem.split("_")[1][0]!="L")):
            result.append((phase,f))
    assert len(result)==len({f.stem for _,f in result})==14
    return result

def lane_run(lane,core):
    os.sched_setaffinity(0,{core})
    dest=OUT/f"lane{lane}"/"data"
    os.environ["M1E_OUTPUT"]=str(dest)
    sys.path.insert(0,str(BASE))
    import experiment as e
    import numba,scipy
    assert all(hashlib.sha256((BASE/k).read_bytes()).hexdigest()==v for k,v in
               json.loads((BASE/"holdout_freeze.json").read_bytes())["algorithm"].items())
    assert os.sched_getaffinity(0)=={core}
    assert all(os.environ[k]=="1" for k in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS","NUMBA_NUM_THREADS"))
    e.p1.put(dest/"setup.json",dict(lane=lane,core=core,platform=platform.platform(),python=sys.version,
            numpy=e.np.__version__,numba=numba.__version__,scipy=scipy.__version__,P1=e.p1.P1,
            protocol_sha256=hashlib.sha256((ROOT/"PROTOCOL.md").read_bytes()).hexdigest()))
    warm=e.p1.Engine("S32",dest.parent/"warm")
    warm.cert(*warm.construct("quota",1)[0])
    for i,(phase,f) in enumerate(inputs()):
        if i%7!=lane:continue
        size,word=f.stem.split("_")
        c=e.reordered(e.case_for("L"+size[1:]),"L"+size[1:],word)
        assert (dest/"validation_inputs"/f.name).read_bytes().splitlines()==f.read_bytes().splitlines()
        rotation=METHODS[i%4:]+METHODS[:i%4]
        for m in rotation:
            e.run(c,m,60.0)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane",type=int)
    parser.add_argument("--core",type=int)
    a=parser.parse_args()
    if a.lane is not None:
        lane_run(a.lane,a.core)
        return
    cores=sorted(os.sched_getaffinity(0))
    assert len(cores)>=7
    OUT.mkdir(parents=True,exist_ok=False)
    jobs=[]
    for lane,core in enumerate(cores[-7:]):
        with (OUT/f"lane{lane}.log").open("w") as log:
            jobs.append(subprocess.Popen([sys.executable,"-Bu",__file__,"--lane",str(lane),"--core",str(core)],stdout=log,stderr=subprocess.STDOUT))
    exits=[p.wait() for p in jobs]
    if any(exits):raise RuntimeError(exits)

if __name__=="__main__":
    main()
