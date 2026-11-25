"""One frozen, bounded run with independent wall-clock watchdogs and fail-closed stage gates."""
import argparse
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime,timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent
OUT=HERE/"results"
SCRIPT=Path(__file__).resolve()
BUDGETS={"S16":900,"S32":1800,"S80":3600}
def utc():return datetime.now(timezone.utc).isoformat()
def worker(job,case,method,start,limit):
    from g1io import problem,read,write
    from g1_experiment import ref_job,baseline,cp_job,compare_suffix
    if job=="warm":
        from construct import assemble,reference,idle_plan
        from heat import evaluate
        p=problem("S16")
        evaluate(p,idle_plan(p,assemble(p,reference(p,"B0"))),cert=True)
    elif job=="refs":ref_job(case)
    elif job=="check":
        from checks import preflight
        preflight()
    elif job=="suffix":compare_suffix()
    elif job=="baseline":baseline(case,limit)
    elif job=="cp":cp_job(case,method,limit,start)
    else:raise KeyError(job)

def main():
    from g1io import read,write,record,sha
    from freeze import git
    from g1_experiment import lines
    if (OUT/"execution.json").exists():raise RuntimeError("a production record already exists")
    assert git("branch","--show-current").strip()==b"codex/global-config-g1"
    assert git("remote","get-url","origin").decode().strip()=="https://github.com/YBEMR/paper.git"
    assert not git("status","--porcelain","--untracked-files=all")
    head=git("rev-parse","HEAD").decode().strip()
    for row in read(HERE/"input_lock.json")["upstream"]:
        assert sha((HERE.parents[1]/row["path"]).read_bytes())==row["sha256"]
    for name,h in read(HERE/"input_lock.json")["new_instances"].items():
        assert sha((HERE/"instances"/name).read_bytes())==h
    begin=time.perf_counter()
    write(OUT/"execution.json",dict(freeze=head,utc=utc(),total_limit_s=16200,seed=101,threads=1))
    used=0
    def launch(job,case="",method="",seconds=0):
        t=time.perf_counter()
        budget=min(seconds,16200-(t-begin)-2)
        if budget<=1:raise TimeoutError("total wall clock")
        receipt=dict(job=job,case=case,method=method,budget_s=budget,utc=utc())
        print(json.dumps(receipt),flush=True)
        logfile=OUT/("worker_"+"_".join(filter(None,(job,case,method)))+".txt")
        try:
            with logfile.open("wb") as f:
                cmd=[sys.executable,"-B","-u",str(SCRIPT),"worker",job,case,method,str(t),str(t+budget)]
                ret=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=max(.1,t+budget-time.perf_counter()))
            result="OK" if ret.returncode==0 else "ERROR"
        except subprocess.TimeoutExpired:result="TIME_LIMIT"
        used=time.perf_counter()-t
        receipt.update(elapsed_s=used,status=result)
        record(OUT/"jobs.jsonl",receipt)
        print(json.dumps(receipt),flush=True)
        if result!="OK":
            if job=="cp" and result=="TIME_LIMIT" and (OUT/"cp"/case/method/"model.json").exists():
                return used
            raise RuntimeError(f"{job} {case} {method}: {result}. See {logfile.name}.")
        return used
    try:
        used+=launch("warm",seconds=90)
        for case in ("D1","D2","D3"):launch("refs",case,seconds=60)
        used+=launch("check",seconds=600-used)
        used+=launch("suffix",seconds=600-used)
        for case in ("S16","S32","S80","D1","D2","D3"):launch("baseline",case,seconds=180)
        for case,seconds in BUDGETS.items():
            for method in ("C0","C1"):
                gate=read(OUT/"preflight"/"gates.json")["barriers"][case][method]
                if not gate["passed"]:
                    record(OUT/"skips.jsonl",dict(case=case,method=method,reason="barrier_failed"))
                    continue
                launch("cp",case,method,seconds=seconds)
            if case=="S16":
                audit={}
                for method in ("C0","C1"):
                    path=OUT/"cp"/case/method
                    if not path.exists():continue
                    stats=read(path/"model.json")
                    slices=lines(path/"slices.jsonl")
                    audit[method]=dict(model=stats,statuses=[x["status"] for x in slices],
                       branches=sum(x["branches"] for x in slices),callback_count=sum(x["callback_count"] for x in slices),
                       solve_s=sum(x["solve_s"] for x in slices),cert_s=sum(x["assessment_archive_s"] for x in slices))
                write(OUT/"S16_bottleneck.json",audit)
        status="COMPLETED"
    except Exception:
        status="STOP"
        write(OUT/"stop.json",dict(utc=utc(),error=traceback.format_exc()))
        raise
    finally:
        write(OUT/"end.json",dict(utc=utc(),outcome=status,elapsed_s=time.perf_counter()-begin))

if __name__=="__main__":
    if len(sys.argv)>1 and sys.argv[1]=="worker":
        job,case,method,start,end=sys.argv[2:]
        worker(job,case,method,float(start),float(end))
    else:main()
