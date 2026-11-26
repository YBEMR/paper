"""Run offline evidence and decision checks after the sole timed batch has finished."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
from queue import Queue
import subprocess
import sys

ROOT=Path(__file__).resolve().parent

CORES=Queue()
for core in sorted(os.sched_getaffinity(0))[:3]:
    CORES.put(core)

def check(index):
    env=dict(os.environ,M1G_RAW=str(ROOT/"audit_work"/str(index)),OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MKL_NUM_THREADS="1",NUMBA_NUM_THREADS="1")
    core=CORES.get()
    try:
        for script in ("pool_audit.py","evidence.py"):
            subprocess.run(["taskset","-c",str(core),sys.executable,"-Bu",str(ROOT/script),str(index)],env=env,check=True)
    finally:
        CORES.put(core)

if __name__=="__main__":
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(check,range(14)))
    subprocess.run([sys.executable,"-B",str(ROOT/"summarize.py")],check=True)
