"""Run exactly one named pool or timed formal cell in a separate process."""
import sys
from pathlib import Path
from time import perf_counter
from setup_inputs import ROOT, checked_problem, g1io
from evaluation import make_pool
from trial import trial
from fifo import Compact
from assets import read,write


def main():
    action,case,method,mode,seed,folder,begin,end,budget,charge=sys.argv[1:]
    start,end,budget,charge=map(float,(begin,end,budget,charge))
    folder=Path(folder)
    p=checked_problem(case)
    model=Compact(p)
    if action=="pool":
        g1io.OUT=folder/"evidence"
        pool=make_pool(p,model,end-2,folder)
        write(folder/"result.json",dict(case=case,attempts=len(pool),
              distinct=len({x["plan"] for x in pool if x.get("plan") and x["in_time"]})))
    else:
        params=read(ROOT/"execution_lock.json")["parameters"]
        trial(p,model,case,method,mode,int(seed),folder,folder.parent.parent/"pools"/case,
              start,end-4,budget,charge,params)


if __name__=="__main__":
    main()

