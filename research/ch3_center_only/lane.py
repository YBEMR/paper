"""Four independent cells per host, with absolute deadlines and a single CPU."""
import json
import os
import platform
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def main(code):
    core=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{core})
    out=ROOT/"paired_raw"/code
    out.mkdir(parents=True,exist_ok=False)
    order=["anchors","center"] if code in ("A02","C11") else ["center","anchors"]
    for budget in (60,600):
        for arm in (order if budget==60 else list(reversed(order))):
            folder=out/f"{arm}-{budget}"
            folder.mkdir()
            env=dict(os.environ,NUMBA_CACHE_DIR=str(folder/"jit"),U1_OUT=str(folder/"scratch"),
                     M1G_RAW=str(folder/"warm"))
            start=time.perf_counter()
            env["CELL_START"]=str(start)
            child=subprocess.Popen([sys.executable,"-Bu",str(ROOT/"trial.py"),code,arm,str(budget),str(folder)],
                                   env=env,start_new_session=True)
            try:
                child.wait(timeout=max(0,start+budget-.015-time.perf_counter()))
                status="natural" if child.returncode==0 else "error"
            except subprocess.TimeoutExpired:
                os.killpg(child.pid,signal.SIGKILL)
                child.wait()
                status="deadline"
            wall=time.perf_counter()-start
            receipt=dict(code=code,arm=arm,budget=budget,charged_s=min(wall,budget),supervisor_s=wall,
                         status=status,rc=child.returncode,host=platform.node(),core=core,
                         commit=os.environ["GITHUB_SHA"],run=os.environ["GITHUB_RUN_ID"])
            (folder/"receipt.json").write_text(json.dumps(receipt)+"\n")
            print(receipt,flush=True)
            if status=="error":raise RuntimeError(receipt)

if __name__=="__main__":
    main(sys.argv[1])
