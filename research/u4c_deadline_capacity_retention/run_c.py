"""Frozen external wall-clock controller. All four diagnostic flows finish before controls."""
import inspect
from concurrent.futures import ThreadPoolExecutor
from foundation import *
import batch_control as control

def launch(case_ids,arms):
    native=inspect.getsource(control.unit);mark='str(HERE/"experiment.py")'
    assert native.count(mark)==1
    env=dict(control.__dict__,worker_path=str(HOME_C/"worker_c.py"))
    exec(compile(native.replace(mark,"worker_path"),"<unchanged external deadline>","exec"),env)
    OUT_C.mkdir(exist_ok=True)
    lanes={}
    for k in case_ids:
        cpu=read(B_SRC/"results"/k/"runs/C.json")["receipt"]["cpu"]
        lanes.setdefault(cpu,[]).append(k)
    def lane(entry):
        cpu,objects=entry
        for k in objects:
            i=(int(k[1:])-1)%len(arms)
            for arm in arms[i:]+arms[:i]:env["unit"](cases()[k],arm,cpu,10)
    with ThreadPoolExecutor(max_workers=len(lanes)) as pool:list(pool.map(lane,lanes.items()))

def gate():
    root=HOME_C/"offline"
    r=read(root/"I06/retention.json")
    allw=[read(p) for p in root.glob("*/window_*.json")]
    assert r["cert"]["status"]=="SAFE" and round(r["cert"]["energy"],3)==46.900
    assert len(r["real_pool"])==120 and r["target_rank"]==9 and len(set(r["original_parents"]))==1
    assert len(allw)==9 and all(z["first_failure"]==z["reported_failure"] and z["min_L1"]==z["reported_min"] for z in allw)
    safe={v["cert"]["plan"] for w in allw for v in w["minimum_candidates"] if v["cert"]["status"]=="SAFE" and not v["cert"]["previously_archived"]}
    alt=r["fixed_frequency_continuations"]["margin"]["cert"]
    assert safe and alt["status"]=="SAFE" and not alt["previously_archived"]
    put(HOME_C/"gate.json",dict(status="PASS",new_minimum_plans=sorted(safe),new_slot_continuation=alt,old_witness=r["cert"]["plan"]))
if __name__=="__main__":
    gate()
    if len(sys.argv)==1:arms=list(ARMS)
    else:
        decision=read(HOME_C/"joint_decision.json");assert decision["eligible"]
        arms=[decision["arm"]]
    launch(FOUR,arms)
    launch([k for k in cases() if k not in FOUR],arms)
