"""Exactly one sequential run of each of the twelve approved cases."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from time import perf_counter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REVIEW = ROOT / "research/multidnn_model_review"


def dump(path, value):
    path.write_bytes((json.dumps(value,indent=2,allow_nan=False)+"\n").encode())


def main():
    cfg = json.loads((HERE / "protocol.json").read_bytes())
    inputs = json.loads((REVIEW / "protocol.json").read_bytes())
    if json.loads((HERE / "regression.json").read_bytes())["status"] != "PASS":
        raise RuntimeError("Legacy regression must pass before diagnostics")
    commit = subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    for name, expected in json.loads((HERE / "execution_manifest.json").read_bytes()).items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError("Execution file drift: " + name)
    env = os.environ.copy()
    for key in ("OMP_NUM_THREADS","MKL_NUM_THREADS","OPENBLAS_NUM_THREADS","NUMBA_NUM_THREADS"):
        env[key] = "1"
    env["PYTHONHASHSEED"] = "0"
    raw = HERE / "raw"
    raw.mkdir(exist_ok=False)
    dump(HERE / "environment.json",dict(python=sys.version, executable=sys.executable,
         platform=platform.platform(), processor=platform.processor(), logical_cpus=os.cpu_count(),
         execution_commit=commit, input_commit=cfg["input_commit"], threads=1,
         affinity="OS default; sequential workers, no concurrent experiment workers",
         numba_disk_cache="existing code cache allowed; loading/JIT charged"))
    cases = [f"{l}_{o}_{t}" for l in inputs["loads"] for o in inputs["orders"]
             for t in ("reference_start","preheated")]
    assert len(cases) == cfg["max_runs"] == 12
    for index, case_id in enumerate(cases,1):
        out = raw / case_id
        out.mkdir()
        start = perf_counter()
        dump(out / "job.json",dict(case_id=case_id, execution_commit=commit,
                                  budget_s=cfg["wall_budget_s"], index=index))
        env["DIAGNOSTIC_START"] = str(start)
        print(f"START {index}/12 {case_id}",flush=True)
        with (out / "console.txt").open("wb") as console:
            proc = subprocess.Popen([sys.executable,"-B",str(HERE/"worker.py"),str(out)],
                cwd=ROOT,env=env,stdout=console,stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            killed = False
            try:
                proc.wait(timeout=max(0.001,cfg["wall_budget_s"]-(perf_counter()-start)))
            except subprocess.TimeoutExpired:
                killed = True
                proc.kill()
                proc.wait()
        elapsed = perf_counter()-start
        dump(out / "exit.json",dict(returncode=proc.returncode,hard_timeout=killed,
                                   total_wall_s=elapsed,budget_s=cfg["wall_budget_s"]))
        print(f"END {index}/12 {case_id} wall={elapsed:.3f}s exit={proc.returncode} hard_timeout={killed}",flush=True)
        # Archival compression after termination performs no evaluation.
        log = out / "events.jsonl"
        if log.exists():
            with log.open("rb") as src, gzip.open(out / "events.jsonl.gz","wb",compresslevel=6) as dst:
                shutil.copyfileobj(src,dst)
            log.unlink()
        if proc.returncode != 0 and not killed:
            raise RuntimeError(f"Implementation error in {case_id}; no automatic rerun")
    print("ALL 12 PREDECLARED DIAGNOSTICS FINISHED",flush=True)


if __name__ == "__main__":
    main()
