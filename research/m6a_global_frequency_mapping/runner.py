"""Single-core hard wall supervisor. Runs spend only their own allocation."""
import multiprocessing as mp
import os
import platform
import sys
import time
from pathlib import Path
BOOT=time.perf_counter()
import experiment as ex
from interface import read,save

def call(fn,args,folder,cap,source=None):
    folder.mkdir(parents=True,exist_ok=True)
    begin=time.perf_counter()
    def work():
        ex.CLOCK=begin
        fn(*args)
    child=mp.get_context("fork").Process(target=work)
    child.start();child.join(max(0,cap-.12-(time.perf_counter()-begin)))
    if child.is_alive():child.kill();child.join();status="CAP"
    else:status="NATURAL" if child.exitcode==0 else "ERROR"
    used=time.perf_counter()-begin
    save(folder/"receipt.json",dict(wall_s=used,cap_s=cap,status=status,core=list(os.sched_getaffinity(0)),
        host=platform.node(),source=source or os.environ["GITHUB_SHA"],run=os.environ["GITHUB_RUN_ID"]))
    print(folder.relative_to(ex.OUT),status,round(used,3),flush=True)
    if status=="ERROR":raise RuntimeError(str(folder))
    return used
def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    ex.RUN=ex.u2.stack()
    overhead=time.perf_counter()-BOOT
    cap=300-overhead-5
    gt=call(ex.correctness,(),ex.OUT/"correctness",cap)
    assert (ex.OUT/"gate.json").is_file()
    for obj in ex.u2.CASES:
        code=ex.label(obj)
        if code in ex.DEV:
            for arm in ("adaptive","dp"):
                target=ex.OUT/"stage1"/code/arm
                call(ex.fixed,(obj,"dev",arm,target),target,120)
    for obj in ex.u2.CASES:
        code=ex.label(obj)
        for arm in ("NT","ZQ-Beam"):
            if (ex.OUT/"recovery"/code/arm/"match.json").is_file():
                target=ex.OUT/"stage2"/code/arm
                call(ex.fixed,(obj,arm,"dp",target),target,120)
    for obj in ex.u2.CASES:
        code=ex.label(obj)
        if code not in ex.DEV:continue
        for arm in ("direct","mixed"):
            target=ex.OUT/"stage3"/code/arm
            call(ex.mapping,(obj,arm,target),target,180)
    obj=next(r for r in ex.u2.CASES if ex.label(r)=="C10")
    target=ex.OUT/"regression"/"C10"
    call(ex.mapping,(obj,"regression",target),target,min(180,300-gt-overhead-5))
    save(ex.OUT/"environment.json",dict(startup_s=overhead,host=platform.node(),core=list(os.sched_getaffinity(0)),
        source=os.environ["GITHUB_SHA"],python=sys.version,run=os.environ["GITHUB_RUN_ID"]))
if __name__=="__main__":main()
