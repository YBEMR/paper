"""One-shot supervisor. Keep preflight, online search and post-run quotas disjoint."""
import json
import os
import signal
import sys
import time
import traceback
from pathlib import Path

root=Path(__file__).resolve().parent
archive=root/"archive"
archive.mkdir(exist_ok=True)
def save(path,data):
    path.write_text(json.dumps(data,indent=2)+"\n",encoding="utf8")
def expired(*_):
    raise TimeoutError("phase time limit")
def bounded(name,limit,fn):
    start=time.monotonic()
    signal.signal(signal.SIGALRM,expired)
    signal.setitimer(signal.ITIMER_REAL,limit-.35)
    ok=False
    try:
        fn()
        ok=True
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        save(archive/(name+"-receipt.json"),dict(passed=ok,elapsed_s=time.monotonic()-start,
             cap_core_s=limit,host=os.uname().nodename,source=os.environ["GITHUB_SHA"],
             run_id=os.environ["GITHUB_RUN_ID"]))
    assert ok

def gate():
    global study
    import study
    import precheck
    precheck.run()
    save(archive/"machine.json",dict(single_thread=True,affinity=sorted(os.sched_getaffinity(0)),
         available=cores,python=sys.version,pools=study.threadpool_info(),numpy=study.np.__version__))

if __name__=="__main__":
    cores=sorted(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cores[0]})
    bounded("preflight",180,gate)
    import search_batch
    search_batch.orig_cores=cores
    print("ALL PREFLIGHT CHECKS PASSED",flush=True)
    search_batch.run()
    def post():
        import summarize
        summarize.run()
    bounded("diagnostics",180,post)

