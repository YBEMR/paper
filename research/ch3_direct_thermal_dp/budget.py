"""Guard all data restoration and scientific work with one monotonic, single-core clock."""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"out"
DRIVER=ROOT.parents[1]
CASES="A01 A02 A03 A04 A05 A06 B07 B08 C09 C10 C11 C12".split()


def main():
    OUT.mkdir(exist_ok=False)
    core=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{core})
    start=time.monotonic()
    previous=0.01726883600002793
    deadline=start+595-previous
    steps=[]
    def run(name,cmd,cwd):
        tick=time.monotonic()
        proc=subprocess.Popen(cmd,cwd=cwd,start_new_session=True)
        try:
            rc=proc.wait(timeout=max(0,deadline-time.monotonic()))
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid,signal.SIGKILL)
            proc.wait()
            rc="budget"
        steps.append(dict(step=name,elapsed_s=time.monotonic()-tick,result=rc))
        return rc
    os.environ["CASE_DEADLINE"]=str(deadline)
    os.environ["STUDY_START"]=str(start)
    patterns=[]
    for c in CASES:
        base=f"/research/ch3_center_confirmation/lanes/{c}/r1/paired_results/{c}"
        patterns.extend([base+"/physical/",base+"/center-60/refine.jsonl",base+"/center-600/refine.jsonl",
                         base+"/center-60/search.jsonl",base+"/center-600/search.jsonl",
                         base+"/center-60/certificates.jsonl",base+"/center-600/certificates.jsonl"])
    rc=run("acquire frozen r1 physical archives",["git","-c","pack.threads=1","sparse-checkout","add",*patterns],DRIVER)
    if rc==0:
        rc=run("compile frozen DP",["g++","-O3","-std=c++17","-ffp-contract=off","-fPIC","-shared","dp.cpp","-o","dp.so"],
               ROOT.parent/"m6a_global_frequency_mapping")
    if rc==0:
        rc=run("restore, compare and certify", [sys.executable,"-Bu","evaluate_fixed.py"],ROOT)
    elapsed=time.monotonic()-start
    receipt=dict(elapsed_s=elapsed,prior_s=previous,cumulative_s=previous+elapsed,limit_core_s=600,guard_s=595,core=core,steps=steps,status=rc,source=os.environ["GITHUB_SHA"])
    (OUT/"budget.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(receipt,flush=True)
    assert elapsed+previous<600
    if rc not in (0,"budget"):
        sys.exit(1)


if __name__=="__main__":
    main()
