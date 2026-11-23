"""Twelve preregistered serial runs with hard wall cutoff and persistent receipts."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
from time import perf_counter
import psutil

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
p=json.loads((HERE/"protocol.json").read_bytes())
cpu=psutil.Process().cpu_affinity()[0]
psutil.Process().cpu_affinity([cpu])
version=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
output=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else HERE/"raw"
output.mkdir(exist_ok=True,parents=True)
for ci,case in enumerate(p["cases"]):
    jobs=[dict(case=case,method="M2",seed=None)]+[
        dict(case=case,method="Kim-Adapt+SAFE",seed=seed) for seed in p["seeds"]]
    for ji,job in enumerate(jobs):
        out=output/f"c{ci}-r{ji}"
        out.mkdir()
        (out/"job.json").write_text(json.dumps(job),encoding="utf8")
        env=dict(os.environ,OMP_NUM_THREADS="1",MKL_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1",
                 NUMBA_NUM_THREADS="1",PYTHONHASHSEED="0",
                 NUMBA_CACHE_DIR=tempfile.mkdtemp(prefix="ch3-high-temp-"))
        with (out/"console.txt").open("wb") as console:
            start=perf_counter()
            env["STUDY_START"]=repr(start)
            proc=subprocess.Popen([sys.executable,"-B","-X","utf8",str(HERE/"worker.py"),str(out)],
                                  cwd=ROOT,env=env,stdout=console,stderr=subprocess.STDOUT)
            killed=False
            try:
                proc.wait(timeout=max(0.,start+p["accept_cutoff_s"]-perf_counter()))
            except subprocess.TimeoutExpired:
                if proc.poll() is None:
                    killed=True
                    proc.kill()
                    proc.wait()
            wall=perf_counter()-start
        receipt=dict(job=job,wall_s=wall,hard_timeout=killed,exit_code=proc.returncode,
                     execution_commit=version,config_sha256=hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest(),
                     cpu=platform.processor(),logical_cpu=cpu,python=platform.python_version(),
                     system=platform.platform(),budget_s=p["budget_s"],cold_numba=True)
        (out/"receipt.json").write_text(json.dumps(receipt,indent=2),encoding="utf8")
        print(out.name,job["method"],round(wall,3),"timeout" if killed else proc.returncode,flush=True)
        if proc.returncode and not killed:
            raise SystemExit("execution fault; inspect console")
