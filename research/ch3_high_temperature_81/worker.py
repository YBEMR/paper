"""One cold, matched run; all evaluation and evidence costs use the parent clock."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
from time import perf_counter as clock

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OUT=Path(sys.argv[1])
START=float(os.environ["STUDY_START"])
job=json.loads((OUT/"job.json").read_bytes())
protocol=json.loads((HERE/"protocol.json").read_bytes())
sys.path.insert(0,str(ROOT/"research/ch3_final_experiments/formal"))
import run_formal as formal
import search

stream=gzip.open(OUT/"events.jsonl.gz","xt",encoding="utf-8",compresslevel=1,newline="\n")
def emit(kind,value=None,**data):
    payload=value if value is not None else data
    stream.write(json.dumps(dict(time_s=clock()-START,event=kind,data=payload),allow_nan=False)+"\n")
    stream.flush()


if hashlib.sha256(Path(formal.__file__).read_bytes()).hexdigest()!=protocol["formal_runner_sha256"]:
    raise ValueError("formal runner source changed")
ev=formal.setup(ROOT,job["case"],81,emit)
emit("identity",case=job["case"],method=job["method"],seed=job["seed"],ambient=ev.ambient,
     initial=ev.events.PLATFORM["thermal"]["initial_C"],limits=ev.events.PLATFORM["thermal"]["limits_C"],
     request_sha256=ev.identity,domain=ev.domain.order,opps=ev.events.OPPS,init_s=clock()-START)
if job["method"]=="Kim-Adapt+SAFE":
    rule=formal.config(("forward_flat_25C",81,"Kim-Adapt+SAFE",job["seed"]))
    wanted=protocol["kim"]
    assert (int(rule["population"]),int(rule["max_generations"]),int(rule["max_total_checks"]),
            int(rule["generation_cutoff_s"]),int(rule["accept_cutoff_s"]))==(
            wanted["population"],wanted["generations"],wanted["max_total_checks"],
            wanted["generation_cutoff_s"],wanted["accept_cutoff_s"])
    search.KIM_POP,search.KIM_GENS=wanted["population"],wanted["generations"]
    emit("configuration",formal_rule=rule)
    pool,info=search.kim_pool(ev.domain,ev.proxy,job["seed"],
                              search.Clock(START,START+wanted["generation_cutoff_s"]),emit)
    summary=formal.inspect_pool(pool,ev,search.Clock(START,START+wanted["accept_cutoff_s"]),
                                wanted["max_total_checks"],emit)
    summary["pool"]=info
    emit("result",summary)
else:
    import numpy as np
    from adapter import load_m2
    m,source=load_m2(ev.ambient,protocol["m2_sha256"])
    assert ev.events is m.events and ev.domain.order==m.CATALOG
    config=next(c for c in m.model.cases() if c["id"]==job["case"])
    assert config["ambient"]==ev.ambient
    # Identical writable/read-only JIT preparation to the historical M2 worker.
    t=clock()
    kw=m.events.thermal_kwargs(m.events.PLATFORM,"LLL",ev.ambient,True,"base")
    k=m.thermal.compile_scene(np.array([.005,.003]),np.zeros((2,4)),np.zeros(2),kw)
    for value in vars(k).values():
        if isinstance(value,np.ndarray):
            value.flags.writeable=False
    k.batch(m.joint.INITIAL[None,:])
    k.replay(m.joint.INITIAL)
    emit("cold_warmup",seconds=clock()-t)
    def report(kind,**data):
        if kind=="full_replay":
            choice=data["choice"]
            opps=choice["opps"]
            schedules=[{ev.events.OPPS.index(o):ev.events.time_scene(ev.events.PLATFORM,s,choice["deployment"],o)}
                       for s,o in zip(ev.scenes,opps)]
            ledger=ev.unit.completions(ev.scenes,schedules,opps)
            physical=choice["physical"]
            ev.unit.verify_replay(physical,ledger,ev.scenes,opps,
                                 {"SAFE":1,"VIOLATION":2,"UNRESOLVED":3}[physical["thermal_status"]],
                                 choice["predicted_j"])
            emit("request_ledger",deployment=choice["deployment"],code=choice["code"],rows=ledger)
        emit(kind,**data)
    trial=m.Trial(config,"M2",m.CATALOG,hashlib.sha256(source.encode()).hexdigest(),OUT,report)
    trial.run()
emit("finish")
stream.close()
