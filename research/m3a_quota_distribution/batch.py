"""Use three stable cores and a barrier before applying the registered gate."""
import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
cores = sorted(os.sched_getaffinity(0))[:3]
(root/"work").mkdir(exist_ok=True)
for stage in ("1","2"):
    if stage == "2":
        subprocess.run([sys.executable,"run.py","gate"],cwd=root,check=True)
        import json
        if not json.loads((root/"data/gate.json").read_text())["open"]:
            break
    children = []
    for lane,core in enumerate(cores):
        logfile = open(root/"work"/f"stage{stage}-lane{lane}.log","w",buffering=1)
        args = [sys.executable,"-u","run.py",stage,*map(str,range(lane,12,len(cores)))]
        child = subprocess.Popen(["taskset","-c",str(core),*args],cwd=root,stdout=logfile,stderr=subprocess.STDOUT)
        children.append((child,logfile))
    statuses = [p.wait() for p,_ in children]
    for _,f in children:
        f.close()
    if any(statuses):
        raise RuntimeError(f"stage {stage} worker exit codes {statuses}")
