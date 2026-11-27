"""Independent reading of both group outputs, complete causal scheduling and continuous integration."""
from batch_control import ROOT, HERE, events, evidence, put, read
import os
import sys
from pathlib import Path
os.environ["U3B_RUNS"]=str(ROOT)
sys.path.insert(0,os.environ["U3B_SRC"])
import worker as old

def main():
    assert read(ROOT/"gate.json")["status"]=="PASS"
    u=old.u
    stack=u.stack()
    out=[]
    for folder in sorted(ROOT.glob("*-Gate*")):
        case,method=folder.name.split("-")
        obj=next(o for o in u.CASES if o["case"].startswith(case+"_"))
        logs=list(events(folder));returned=next(r[2] for r in logs if r[0]=="group_rounds")
        deliveries=[r[1] for r in logs if r[0]=="delivered"]
        assert returned==deliveries[-1]["plan"]
        ep=evidence(folder,returned);plan=read(ep/"plan.json");cd=read(ep/"certificate.json")
        flow=u.make_flow(stack[0],obj,folder)
        cfg=tuple(tuple(row[:2]) for row in plan["rows"][1::3])
        state=stack[3](flow,u.encoded(cfg))
        reproduced=flow.eng.build(cfg,state)
        assert u.raw(plan)==u.raw(dict(case=obj["case"],rows=reproduced["rows"],low=sorted(reproduced["low"])))
        m=stack[1].evaluate(flow.p,(reproduced["rows"],reproduced["low"]),cert=True,trace=True)
        tr=old.np.asarray(m.pop("events"))
        with old.np.load(ep/"trace.npz") as arc:assert old.np.array_equal(arc["events"],tr)
        assert u.raw(m)==u.raw(cd["metrics"]) and m["status"]=="SAFE"
        out.append(dict(case=case,method=method,seed=deliveries[0]["plan"],seed_J=deliveries[0]["J"],
            final=returned,J=m["E_J"],peak=max(m["peak_hi"]),slack=m["min_deadline_slack_ms"],
            segments=len(tr),trace_sha256=u.sha(tr.tobytes())))
    assert len(out)==6 and all(len({r["seed"] for r in out if r["case"]==c})==1 for c in ("A06","C10","C11"))
    put(ROOT/"gate_verified.json",out)
    print([(r["case"],r["method"],round(r["J"],6)) for r in out],flush=True)
if __name__=="__main__":main()
