"""One cold target instance using the frozen method, one thread and a supervisor deadline."""
import json
import os
import sys
import time
from pathlib import Path
from time import perf_counter

from interface import OUT, THREE, cfg, decode, item, problem, raw, read, save, setup, sha, verify_seed

def run(code, method):
    folder = OUT / "cells" / code / method
    folder.mkdir(parents=True, exist_ok=False)
    family = method if method in ("NT","Q4") else "Proposed"
    api = setup(family)
    if family == "NT":
        from runner import timed_run
        api.template()  # immutable device arrays on L320, no target and no search
    import psutil
    assert len(psutil.Process().cpu_affinity()) == 1
    save(folder/"ready.json",dict(cpu=psutil.Process().cpu_affinity(),pid=os.getpid()))
    while not (folder/"clock.json").exists():
        time.sleep(.005)
    timing = read(folder/"clock.json")
    start = timing["start"]
    charged = timing["charged"]
    end = start + 180 - charged
    elapsed = lambda: charged + perf_counter()-start
    history = folder/"certificates.jsonl"
    def emit(key, met, source, stamp=None):
        row = dict(t=elapsed() if stamp is None else stamp,plan=key,J=met["E_J"],bounds=met["E_bounds"],
                   status=met["status"],source=source)
        with history.open("ab") as f:
            f.write(raw(row)+b"\n")
    obj = item(code)
    p, engine = problem(family,api,obj,folder)
    if family=="NT":
        native = engine.certify
        def observe(config,*args,**kwargs):
            d,tr = native(config,*args,**kwargs)
            emit(d["plan_sha256"],d["metrics"],"NT")
            return d,tr
        engine.certify=observe
        import runner
        original_builder=runner.builder
        def measured_builder(name):
            build,progress=original_builder(name)
            def measured(case,arm,width,begin,deadline,stage):
                ordered=build(case,arm,width,begin,deadline,stage)
                with (folder/"widths.jsonl").open("ab") as f:
                    f.write(raw(dict(width=width,terminals=len(ordered),t=elapsed(),last=progress))+b"\n")
                return ordered
            return measured,progress
        runner.builder=measured_builder
        timed_run(engine,"NT",folder/"search",budget=max(.001,end-perf_counter()))
    elif family=="Q4":
        native=engine.cert
        def observe(*args,**kwargs):
            d,tr=native(*args,**kwargs)
            emit(d["plan_sha256"],d["metrics"],"Q4" if not history.exists() else "ThermalUnion")
            return d,tr
        engine.cert=observe
        cr,info=engine.construct("quota",4)
        save(folder/"construction.json",info)
        if cr:
            d,tr=engine.cert(*cr)
            if d["metrics"]["status"]=="SAFE":
                result=engine.optimize((*cr,d,tr),"adaptive","union")
                save(folder/"optimization.json",result)
    else:
        import trial as frozen
        from assets import write
        from evaluation import make_pool
        from fifo import Compact
        from setup_inputs import g1io
        pool = folder/"pool"
        model = Compact(p)
        g1io.OUT = pool/"evidence"
        if method.startswith("NT+"):
            obj=read(OUT/"seeds"/(code+".json"))
            plan=verify_seed(p,obj["plan"])
            key=g1io.store(p,plan)
            write(pool/"pool.json",[dict(plan=key,in_time=True,generator="NT60")])
            save(folder/"seed_identity.json",dict(native=key,canonical=sha(raw(obj["plan"])),source=obj["key"]))
        else:
            # Published construction limits: 60/300 and 180/900; preserve one fifth.
            make_pool(p,model,start+36-2,pool)
        orig=frozen.Contest.consider
        def observe(ctx,plan,until,archive=False,switches=None):
            result=orig(ctx,plan,until,archive,switches)
            if result is not None:
                emit(result["plan"],dict(E_J=result["J"],E_bounds=result["bounds"],status=result["status"]),"T3")
            return result
        frozen.Contest.consider=observe
        params=read(THREE/"chapter3_final_evaluation/execution_lock.json")["parameters"]
        # 'charged' counts only time before this process. Pool time already ran on start's clock.
        frozen.trial(p,model,p.case,method.split("+")[-1],"T3",101,folder,pool,start,end-4,180,charged,params)
    save(folder/"finished.json",dict(elapsed=elapsed()))

if __name__=="__main__":
    run(*sys.argv[1:])
