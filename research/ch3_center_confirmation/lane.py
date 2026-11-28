"""One pinned CPU per flow, twelve cold processes, offline archiving outside all clocks."""
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CASES = ("A01","A02","A03","A04","A05","A06","B07","B08","C09","C10","C11","C12")
SETTINGS = (("original",60), ("original",600), ("center",60), ("center",600))
# Four balanced sequences. Rotate the sequence across repetitions and streams.
ORDERS = ((0,1,3,2), (1,2,0,3), (2,3,1,0), (3,0,2,1))


def run_cell(code, arm, budget, repeat, position, dest, core):
    dest.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, NUMBA_CACHE_DIR=str(dest/"jit"), U1_OUT=str(dest/"scratch"), M1G_RAW=str(dest/"warm"))
    start = time.perf_counter()
    env["CELL_START"] = str(start)
    child = subprocess.Popen([sys.executable, "-Bu", str(ROOT/"cold_cell.py"), code, arm, str(budget), str(dest)],
                             env=env, start_new_session=True)
    try:
        child.wait(timeout=max(0,start+budget-.015-time.perf_counter()))
        status = "natural" if child.returncode == 0 else "error"
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait()
        status = "deadline"
    wall = time.perf_counter()-start
    receipt = dict(code=code, arm=arm, budget=budget, repeat=repeat, position=position,
                   charged_s=min(wall,budget),supervisor_s=wall,status=status,rc=child.returncode,
                   host=platform.node(),core=core,commit=os.environ["GITHUB_SHA"],run=os.environ["GITHUB_RUN_ID"])
    (dest/"receipt.json").write_text(json.dumps(receipt)+"\n")
    print(receipt,flush=True)
    if status=="error":
        raise RuntimeError(receipt)


def main(code):
    core = min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{core})
    persist = ROOT/"lanes"/code
    persist.mkdir(parents=True,exist_ok=False)
    for rep in (1,2,3):
        work = persist/f"r{rep}"
        for pos, setting in enumerate(ORDERS[(CASES.index(code)+rep-1)%4], 1):
            arm, budget = SETTINGS[setting]
            dest = work/"paired_raw"/code/f"{arm}-{budget}"
            run_cell(code,arm,budget,rep,pos,dest,core)
        subprocess.run([sys.executable,"-Bu",str(ROOT/"pack_repeat.py"),str(work),code],check=True)
        # This directory contains only the four just-verified temporary cell writers.
        shutil.rmtree(work/"paired_raw")


if __name__=="__main__":
    main(sys.argv[1])
