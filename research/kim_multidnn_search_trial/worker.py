"""One cold worker. The supervising parent owns the deadline and the persistent ledger."""
import json
import os
from pathlib import Path
import sys
from time import perf_counter

HERE = Path(__file__).resolve().parent
START = float(os.environ["TRIAL_START"])
OUT = Path(sys.argv[1])
JOB = json.loads((OUT/"job.json").read_bytes())
stream = (OUT/"events.jsonl").open("x",encoding="utf-8",buffering=1)

def emit(kind,**data):
    stream.write(json.dumps(dict(t=perf_counter()-START,kind=kind,**data),allow_nan=False,separators=(",",":"))+"\n")
    stream.flush()

emit("process")
import hashlib
import platform
import numpy as np
import numba
import psutil
from solver import (Trial, SceneTable, OPPS, EXP, FROZEN, CATALOG, Counter, events, joint, model,
                    make_scenes, thermal, read)
from design import cases
from thermal import _replay

proc=psutil.Process()
def log(kind,**fields):
    mem=proc.memory_info()
    emit(kind,peak_rss_bytes=getattr(mem,"peak_wset",mem.rss),**fields)

def check_freeze():
    manifest=read(HERE/"freeze.json")
    for path,want in manifest["files"].items():
        assert hashlib.sha256((HERE.parents[1]/path).read_bytes()).hexdigest()==want,path
    return hashlib.sha256((HERE/"freeze.json").read_bytes()).hexdigest()

def event_fixture(case,freeze):
    scenes=make_scenes(case)
    counts=Counter()
    source=SceneTable(scenes,"M2",counts,freeze)
    pairs=[("A","D025","LLL"),("D001","D003","LLL"),("A","C","LHL"),("A","C","LHL")]
    for i,(a,b,o) in enumerate(pairs):
        assert source.key(a,i,o)==source.key(b,i,o)
        ka=source.get(a,i,o)
        kb=source.get(b,i,o)
        direct=SceneTable(scenes,"M1",Counter(),freeze).get(b,i,o)
        assert ka is not kb and ka is not None and direct is not None
        for name in ("dt","activity","transfer","F","w","final0","upper","witness_temp","witness_exp"):
            assert np.array_equal(getattr(ka,name),getattr(direct,name)),(i,name)
        assert ka.energy0==direct.energy0
        sa,sb=[events.time_scene(events.PLATFORM,scenes[i],d,o) for d in (a,b)]
        assert sa.rows==sb.rows and sa.completions_ns==sb.completions_ns
        assert sa.deadline_feasible==sb.deadline_feasible and np.array_equal(sa.active_w,sb.active_w)
        for inlet in (np.array([30.,30.,30.,30.]),np.array([40.,55.,42.,43.])):
            out=ka.batch(inlet[None,:])
            ref=direct.batch(inlet[None,:])
            assert all(np.array_equal(x,y) for x,y in zip(out,ref))
            raw=direct.replay(inlet)
            assert abs(out[0][0]-raw["energy_J"])<=1e-7
            assert np.max(np.abs(out[1][0]-raw["final_C"]))<=1e-7
            assert int(out[2][0])=={"SAFE":1,"VIOLATION":0,"UNRESOLVED":-1}[raw["thermal_status"]]
        assert kb.screen_calls==kb.fallback_calls==0 and ka.screen_calls==2
        c=next(d for d in CATALOG if source.key(d,i,o)!=source.key(a,i,o))
        different=events.time_scene(events.PLATFORM,scenes[i],c,o)
        assert different.rows!=sa.rows
        previous=counts["misses"]
        source.get(c,i,o)
        assert counts["misses"]==previous+1
        log("fixture",index=i,positive=[a,b],negative=[a,c],opp=o,entries=2)
    assert counts["scene_requests"]==12 and counts["hits"]==4 and counts["misses"]==8
    assert scenes[-1].end_ns-scenes[-1].service_end_ns==40000000
    log("fixture_counters",stats=dict(counts))

def test_policy(case,freeze,unsafe):
    # The very same Trial.run() used by the formal comparison, restricted only in deployments.
    order=["D019"] if unsafe else ["C"]
    record=read(EXP/"raw"/"expanded"/case["id"]/("deployment_"+order[0]+".json"))
    for method in ("M1","M2"):
        log("fixture_method",method=method)
        observed=[]
        def collect(kind,**data):
            observed.append((kind,data))
            log(kind,method_label=method,**data)
        trial=Trial(case,method,order,freeze,OUT,collect)
        winner=trial.run()
        fallback=[x for k,x in observed if k=="policy_fallback"]
        certificates=[x for k,x in observed if k=="certificate"]
        assert len(certificates)==1 and certificates[0]["scope"]=="subset"
        if unsafe:
            assert winner is None and len(fallback)==1
            assert fallback[0]["reason"]=="VIOLATION" and fallback[0]["candidate"]["code"]==record["no_thermal_constraint"]["code"]
            completed=[x for k,x in observed if k=="deployment" and x["phase"]=="fallback"]
            assert len(completed)==1 and completed[0]["safe"]==0 and completed[0]["overtemp"]==59049
        else:
            assert winner and not fallback and winner["physical"]["thermal_status"]=="SAFE"
            assert winner["code"]==record["joint"]["code"]

def main():
    freeze=check_freeze()
    assert freeze==JOB["freeze_sha256"]
    configs={c["id"]:c for c in cases() if c["ambient"]==25}
    configs.update({c["id"]:c for c in read(HERE/"design.json")["holdouts"]})
    case=configs[JOB["case"]]
    log("imports_and_freeze",python=sys.version,numpy=np.__version__,numba=numba.__version__,
        host=platform.platform(),cpu=platform.processor(),freeze=freeze,preregistration=JOB["preregistration"])
    # Identical cold JIT preparation charged to all methods; the original functions see writable
    # compile inputs and the read-only map arrays used in the search.
    mark=perf_counter()
    kw=events.thermal_kwargs(events.PLATFORM,"LLL",25,True,"base")
    k=thermal.compile_scene(np.array([.005,.003]),np.zeros((2,4)),np.zeros(2),kw)
    for value in vars(k).values():
        if isinstance(value,np.ndarray):
            value.flags.writeable=False
    k.batch(joint.INITIAL[None,:])
    k.replay(joint.INITIAL)
    log("cold_warmup",wall_s=perf_counter()-mark)
    if JOB["stage"]=="e0":
        if JOB["id"]=="e0-normal":
            event_fixture(case,freeze)
        test_policy(case,freeze,JOB["id"]=="e0-reject")
    else:
        subset=read(HERE/"design.json")["fixed_subset"] if JOB["stage"]=="fixed" else CATALOG
        trial=Trial(case,JOB["method"],subset,freeze,OUT,log)
        trial.run()
    log("success")

if __name__=="__main__":
    main()
