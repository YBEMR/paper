"""Charge restoration, frozen optimization, certification and result tables to one core."""
import json
import os
import signal
import subprocess
import sys
import time
from prepare import OLD, OUT, ROOT, pending


def science():
    sys.path.insert(0, str(OLD))
    import evaluate_fixed as fixed
    fixed.ROOT, fixed.OUT = ROOT, OUT
    rows = pending()
    cases = sorted({r["case"] for r in rows})
    recovered = [r for c in cases for b in (60,600) for r in fixed.nominations(c,b)]
    assert recovered == rows
    fixed.m.CLOCK = float(os.environ["STUDY_START"])
    fixed.m.RUN = fixed.m.u2.stack()
    verified = {("SAFE","ordinary"),("SAFE","thermal")}
    hot = [(r["case"], r["seed"]) for r in rows if r["point"]["status"] == "HOT"]
    assert [c for c,k in hot] == ["C10","C11"] and len(set(hot)) == 2
    groups = [[r for r in rows if (r["case"],r["seed"]) == key] for key in hot]
    groups.extend([r for r in rows if r["case"] == c and (c,r["seed"]) not in hot] for c in cases)
    for group in groups:
        print("Restoring and evaluating",group[0]["case"],len(group),group[0]["point"]["status"],flush=True)
        fixed.evaluate_case(group[0]["case"],group,verified)
    print("Verified stage classes",sorted(verified),flush=True)


def guard():
    core = min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{core})
    prior = json.loads((OLD/"out/budget.json").read_bytes())["cumulative_s"]
    start = time.monotonic()
    deadline = start + 597
    os.environ.update(CASE_DEADLINE=str(deadline-2),STUDY_START=str(start))
    steps = []
    def run(name, cmd, cwd):
        before = time.monotonic()
        child = subprocess.Popen(cmd,cwd=cwd,start_new_session=True)
        try:
            status = child.wait(timeout=max(0,deadline-time.monotonic()))
        except subprocess.TimeoutExpired:
            os.killpg(child.pid,signal.SIGKILL)
            child.wait()
            status = "budget"
        steps.append(dict(step=name,result=status,seconds=time.monotonic()-before))
        return status
    def receipt(status):
        elapsed = time.monotonic()-start
        data = dict(source=os.environ["GITHUB_SHA"],historical_core_s=prior,elapsed_s=elapsed,
                    supplemental_core_s=elapsed,cumulative_s=prior+elapsed,supplemental_limit_core_s=600,
                    cpu=core,steps=steps,status=status,preparation_receipt="../acquisition.json")
        (OUT/"budget.json").write_text(json.dumps(data,indent=2)+"\n")
        return data
    rc = run("compile frozen DP",["g++","-O3","-std=c++17","-ffp-contract=off","-fPIC","-shared","dp.cpp","-o","dp.so"],ROOT.parent/"m6a_global_frequency_mapping")
    if rc == 0:
        rc = run("restore, optimize and continuously certify", [sys.executable,"-Bu","resume.py","science"],ROOT)
    receipt(rc)
    if rc == 0:
        rc = run("write consolidated scientific tables and report", [sys.executable,"-Bu","summarize.py"],ROOT)
    data = receipt(rc)
    print(json.dumps(data),flush=True)
    assert data["supplemental_core_s"] < 600 and rc == 0


if __name__ == "__main__":
    if sys.argv[1:] == ["science"]:
        science()
    else:
        guard()
