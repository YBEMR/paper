"""S16-only numerical checks and GA/SA calibration before any formal ranking."""
import json
import math
import os
import random
import statistics
import sys
from pathlib import Path
from time import perf_counter
import numpy as np
from setup_inputs import ROOT, checked_problem, g1io
from evaluation import make_pool, assess_mode
from assets import write, read, Layout
from algorithm import load_at
from fifo import Compact
from heat import evaluate
from model import independent_events
from evolution import mutate, genes, repair, evolved_plan
from trial import trial


def calibration(output):
    begin=perf_counter()
    p=checked_problem("S16")
    m=Compact(p)
    pool=output/"pool"
    pool.mkdir(parents=True)
    g1io.OUT=pool/"evidence"
    entries=make_pool(p,m,perf_counter()+35,pool)
    valid=[r["plan"] for r in entries if r.get("plan") and r["in_time"]]
    if not valid:
        raise ValueError("Empty S16 automatic pool")
    scores={}
    for mode in ("T0","T1","T2","T3"):
        out=output/mode
        g1io.OUT=out/"evidence"
        scores[mode]=[assess_mode(p,load_at(pool/"evidence",key),mode,out) for key in dict.fromkeys(valid)]
    winner=min((r for r in scores["T3"] if r["eligible"]),key=lambda r:r["J"])
    plan=load_at(pool/"evidence",winner["plan"])
    g1io.OUT=output/"calibration_evidence"
    _,cert=g1io.assess(p,plan)
    exact=float(sum(Layout(p,plan[0]).components(plan[1]).values()))
    if abs(exact+cert["metrics"]["temperature_J"]-winner["J"])>1e-8:
        raise ValueError("Continuous energy decomposition")
    c=evaluate(p,plan,cert=True,trace=True)
    r=evaluate(p,plan,cert=True,trace=True,reset=True)
    a,b=np.asarray(c["events"]),np.asarray(r["events"])
    if not np.array_equal(a[:,:14],b[:,:14]):
        raise ValueError("Reset changed the resource timeline")
    for boundary in p.boundaries:
        i=int(np.flatnonzero(a[:,0]==boundary)[0])
        if not(np.allclose(a[i,14:18],a[i-1,18:22]) and np.allclose(b[i,14:18],p.initial)):
            raise ValueError("Boundary thermal state")
    if np.max(abs(a[:,14:22]-b[:,14:22]))<=1e-6:
        raise ValueError("Missing thermal reset")
    rng=random.Random(101)
    base=genes(plan)
    increments=[]
    explored=set()
    # Fixed sample size; only positive normalized increments set the 0.8
    # initial uphill acceptance. No formal-case or ranking information enters.
    for j in range(96):
        requested=mutate(base,m.ops,rng)
        cfg=repair(m,requested,base)
        explored.update(op for i,op in enumerate(requested) if op!=base[i])
        assert m.replay(cfg) is not None
        pl=evolved_plan(p,cfg)
        independent_events(p,*pl)
        ev=evaluate(p,pl,cert=True)
        if ev["status"]=="SAFE" and ev["E_J"]>winner["J"]+1e-8:
            increments.append((ev["E_J"]-winner["J"])/winner["J"])
    assert increments and set(m.ops)==explored
    params=dict(population=40,tournament=3,elite=2,crossover=.8,per_gene="1/n",group_mutation_probability=.25,
                SA_group_probability=.4,group_size=[2,8],T_initial=-statistics.median(increments)/math.log(.8),
                final_ratio=math.log(.8)/math.log(.01),calibration_positive=len(increments))
    write(output/"calibration.json",dict(parameters=params,positive_normalized_increments=increments,
          pool=valid,scores=scores,elapsed_s=perf_counter()-begin))
    for method,mode in [(x,"T3") for x in ("Greedy","GA","SA","Adapted-ETA-TS","Adapted-eFLS","Compact","AB","Proposed")]+[("Proposed",x) for x in ("T0","T1","T2")]:
        f=output/(method+"_"+mode)
        f.mkdir()
        start=perf_counter()
        result=trial(p,m,"S16",method,mode,101,f,pool,start,start+13,15,0,params,smoke=True)
        assert result["status"]=="SAFE" and result["initial"] and result["post"]["rounds"]>=1, (method,mode,result)
        assert result["elapsed_s"]<15 and result["post"]["elapsed_s"]<=3
        if method=="GA": assert result["configuration_details"]["population"]==40
        if method=="Adapted-eFLS": assert len(result["native"])==4
        if method=="Adapted-ETA-TS": assert any(row.get("score") for row in result["native"])
    write(output/"passed.json",dict(status="PASS",case="S16",runs=11,elapsed_s=perf_counter()-begin,
           checked="paired physical timeline; original P1 certificate; all genes; legal repair; method paths and postprocess"))
    return params


if __name__=="__main__":
    dest=Path(sys.argv[1])
    if dest.exists():
        raise FileExistsError(dest)
    calibration(dest)

