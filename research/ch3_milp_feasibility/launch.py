"""Run exactly the two predeclared cases, serially. Refuse to overwrite evidence."""
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
protocol = json.loads((HERE/"protocol.json").read_text())
destination = Path(sys.argv[1]).resolve() if len(sys.argv)>1 else HERE/"raw"
destination.mkdir(parents=True, exist_ok=True)
parent = psutil.Process()
affinity = parent.cpu_affinity()
parent.cpu_affinity([affinity[0]])
version = subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
for label in protocol["cases"]:
    out = destination/label
    out.mkdir()
    env = dict(os.environ, NUMBA_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
               OPENBLAS_NUM_THREADS="1", BLIS_NUM_THREADS="1", PYTHONHASHSEED="0",
               NUMBA_CACHE_DIR=tempfile.mkdtemp(prefix=f"ch3-milp-{label}-"))
    with (out/"solver.log").open("wb") as log:
        start = perf_counter()
        proc = subprocess.Popen([sys.executable, "-B", "-u", str(HERE/"worker.py"), label,
                                 str(out), repr(start)], cwd=ROOT, env=env, stdout=log,
                                stderr=subprocess.STDOUT)
        timed_out = False
        try:
            proc.wait(timeout=max(0.,protocol["budget_s"]-(perf_counter()-start)))
        except subprocess.TimeoutExpired:
            if proc.poll() is None:
                timed_out = True
                proc.kill()
                proc.wait()
        elapsed = perf_counter()-start
    receipt = dict(case=label, budget_s=protocol["budget_s"], wall_s=elapsed,
                   killed=timed_out, exit_code=proc.returncode, base=protocol["source"],
                   execution_commit=version, cpu=platform.processor(), logical_cpu=affinity[0],
                   python=platform.python_version(), system=platform.platform(), cold_numba_cache=True,
                   config_sha256=hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest())
    (out/"receipt.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
    print(label, receipt,flush=True)
    if proc.returncode and not timed_out:
        raise SystemExit("worker failed; see solver.log")
