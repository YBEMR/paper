"""Use the frozen external hard-stop controller with only the worker path replaced."""
import inspect
from concurrent.futures import ThreadPoolExecutor
from shared import *
import batch_control as control

def main():
    checks=[read(HERE/"offline"/k/"audit.json") for k in FOCUS]
    missing=checks[0]["first_loss"]
    assert not missing["balance"] and not missing["perturb"] and missing["composition"] and missing["late"]==0
    assert all(r["open_equal"]>0 for r in checks)
    proofs=[a for k in FOCUS for a in read(HERE/"offline"/k/"certificates.json")
            if a["duplicate_source"] and a["duplicate_source"]!=a["plan"] and a["method"]=="Base"]
    assert proofs and not any(a["status"]=="SAFE" for a in proofs)
    put(HERE/"gate.json",dict(result="PASS",quota_case=checks[0]["case"],safe_plan=checks[0]["NT60"],
        first_loss=missing,distinct_shared_prefix_examples=len(proofs),example=proofs[0],
        open_event_validations=sum(r["open_equal"] for r in checks)))
    native=inspect.getsource(control.unit);mark='str(HERE/"experiment.py")'
    assert native.count(mark)==1
    env=dict(control.__dict__,worker_path=str(HERE/"routes.py"))
    exec(compile(native.replace(mark,"worker_path"),"<frozen external deadline>","exec"),env)
    RAW.mkdir(exist_ok=True)
    lanes={}
    for k,o in cases().items():
        cpu=read(A/"results"/k/"runs/Base.json")["receipt"]["cpu"]
        lanes.setdefault(cpu,[]).append(o)
    def lane(entry):
        cpu,objects=entry
        for o in objects:
            arms=list("RPDCH");i=(int(o["id"][1:])-1)%5
            for arm in arms[i:]+arms[:i]:env["unit"](o,arm,cpu,10)
    with ThreadPoolExecutor(max_workers=len(lanes)) as pool:list(pool.map(lane,lanes.items()))
if __name__=="__main__":main()
