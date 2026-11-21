"""One fixed-policy physical replay with native thermal event-time sampling."""
import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from time import perf_counter

from run_formal import HERE, setup, put, sha


def sample(root, out):
    import psutil
    psutil.Process().cpu_affinity([8])
    import numpy as np
    witnesses=[]
    def emit(event,value):
        if event=="physical":
            witnesses.append(value)
    ev=setup(root,"forward_flat_25C",4,emit)
    original=ev.events.evaluate_thermal
    samples=[]
    def traced(*args,**kwargs):
        rec=original(*args,**kwargs,trace=True)
        samples.append((rec.pop("trace_time_s"),rec.pop("trace_C")))
        return rec
    ev.events.evaluate_thermal=traced
    try:
        result=ev.replay("C",(0,0,6,6))
    finally:
        ev.events.evaluate_thermal=original
    witness=witnesses[0]
    # LHL is index 6 in CPU/GPU/DLA order. Tail is part of the fourth scene.
    refpath=root/"research/kim_multidnn_expansion/raw/expanded/forward_flat_25C/deployment_C.json"
    ref=json.loads(refpath.read_bytes())["joint"]
    phy=witness["physical"]
    if ref["opps"]!=["LLL","LLL","LHL","LHL"] or ref["code"]!=168 or result.status!="SAFE":
        raise ValueError("policy identity mismatch")
    for k in ("energy_j","min_slack_ms","peak_lower_c","peak_upper_c","final_c"):
        np.testing.assert_allclose(phy[k],ref["physical"][k],rtol=0,atol=1e-7)
    with (out/"samples.csv").open("x",encoding="utf8",newline="") as f:
        w=csv.writer(f);w.writerow(["scene","opp","t_ns","cpu_c","gpu_c","dla0_c","dla1_c"])
        for scene, row, archived, (t,temps) in zip(ev.scenes,phy["scene_rows"],ref["physical"]["scene_rows"],samples,strict=True):
            for k in ("entry_c","final_c","peak_upper_c","peak_lower_c","energy_j"):
                np.testing.assert_allclose(row[k],archived[k],rtol=0,atol=1e-7)
            ns=scene.start_ns+np.rint(t*1e9).astype(np.int64)
            if ns[0]!=scene.start_ns or ns[-1]!=scene.end_ns or np.any(np.diff(ns)<=0):
                raise ValueError("nonmonotone sample times")
            np.testing.assert_allclose([temps[0],temps[-1]],[row["entry_c"],row["final_c"]],rtol=0,atol=1e-7)
            w.writerows((scene.name,row["opp"],int(n),*temp) for n,temp in zip(ns,temps,strict=True))
    put(out/"certificate.json",dict(request_sha256=ev.identity,code=168,physical=phy,completions=witness["completions"],
                                    native_rows=sum(len(t) for t,_ in samples),reference_sha256=sha(refpath)))


def run(root):
    out=HERE/"raw"/"figureC"
    out.mkdir(parents=True,exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="ch3-trace-") as cache:
        env={**os.environ,"NUMBA_CACHE_DIR":cache,"NUMBA_NUM_THREADS":"1","MKL_NUM_THREADS":"1",
             "OPENBLAS_NUM_THREADS":"1","OMP_NUM_THREADS":"1","PYTHONDONTWRITEBYTECODE":"1"}
        start=perf_counter()
        with (out/"console.txt").open("w",encoding="utf8") as log:
            p=subprocess.Popen([sys.executable,"-B","-X","utf8",str(Path(__file__).resolve()),
                                "--source-root",str(root),"--worker"],env=env,stdout=log,stderr=log)
            try:
                p.wait(timeout=max(0,start+30-perf_counter()))
                state="finished" if p.returncode==0 else "fault"
            except subprocess.TimeoutExpired:
                p.kill();p.wait();state="hard_timeout"
        put(out/"receipt.json",dict(cap_s=30,elapsed_s=perf_counter()-start,state=state,source_sha=sha(Path(__file__))))
    print(state)
    if state!="finished":
        raise RuntimeError((out/"console.txt").read_text("utf8"))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--source-root",required=True,type=Path)
    parser.add_argument("--worker",action="store_true")
    a=parser.parse_args()
    if a.worker:
        sample(a.source_root.resolve(),HERE/"raw"/"figureC")
    else:
        run(a.source_root.resolve())
