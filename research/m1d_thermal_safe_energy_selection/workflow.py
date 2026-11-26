"""Reproduce the conditional workflow in an independent output directory."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time
import json

ROOT=Path(__file__).resolve().parent
def execute(out,resume):
    env=dict(os.environ,M1D_OUTPUT=str(out),PYTHONDONTWRITEBYTECODE="1")
    def read(f):return json.loads((out/f).read_bytes())
    def timed(file):
        t=time.perf_counter()
        subprocess.run([sys.executable,"-B","-u",str(ROOT/file)],env=env,check=True)
        spans[file]=time.perf_counter()-t
    spans={}
    if not resume:
        timed("study.py")
    else:
        finals=list((out/"terminal").glob("*/*/orders.json"));assert len(finals)==30
        # On the original workstation the lock was written immediately before
        # Python launch. Save the bracket once; Git checkout timestamps differ.
        spans["study.py"]=max(p.stat().st_mtime for p in finals)-(ROOT/"terminal_lock.json").stat().st_mtime
    (out/"job_times.json").write_text(json.dumps(spans,indent=2),encoding="utf8")
    timed("decisions.py")
    if read("terminal_decision.json")["run_stage2"]:
        timed("prefix.py")
        if read("coverage_decision.json")["witnesses"]:
            raise RuntimeError("Witness found. Inspect the actual matched pool before the optional coverage ablation.")
    timed("validation.py")
    timed("verify.py")
    timed("pool_summary.py")
    timed("tables.py")
    (out/"job_times.json").write_text(json.dumps(spans,indent=2),encoding="utf8")

if __name__=="__main__":
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("destination",type=Path,nargs="?")
    cli.add_argument("--continue-original",action="store_true")
    a=cli.parse_args()
    if a.continue_original:
        assert a.destination is None
        execute(ROOT/"data",True)
    else:
        if a.destination is None:cli.error("provide a new empty directory")
        dest=a.destination.resolve()
        if dest==ROOT or dest.is_relative_to(ROOT):cli.error("use a new directory outside the archived study")
        dest.mkdir(parents=True,exist_ok=False)
        execute(dest/"data",False)
