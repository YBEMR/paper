"""Complete cold solve. Both arms use the frozen center-only construction and selector."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"ch3_center_only"))
from anchor_cell import f, m, paired
from simplified import expand


def direct(eng, flow, seed, dest, emit):
    original = m.endpoint(seed[2])
    incumbent = original if original["status"] == "SAFE" else None
    assert original["status"] in ("SAFE","HOT")
    eng.out = dest/"direct"
    emit("begin",task="refinement",stage="direct",guide=original["plan"])
    result = m.optimize(eng,flow,seed[0],seed,dest,"direct",True)
    proposal = None
    if result is not None:
        assert tuple(u for u,k in seed[0]) == tuple(u for u,k in result[0])
        assert paired.online.valid(result[3],eng.p.horizon)
        point = m.endpoint(result[2])
        proposal = point["plan"]
        if f.strict(point,incumbent):
            incumbent = point
        emit("certificate",stage="direct",point=point)
    emit("stage_end",stage="direct",attempt=proposal,incumbent=incumbent["plan"] if incumbent else None)
    return incumbent


def refine_safe(obj,dest,seed):
    f.arm_alarm(f.ORIGIN+60)
    m.CLOCK = f.ORIGIN
    def emit(event,**fields):
        f.log(dest/"refine.jsonl",event,**fields)
    p = seed["point"]
    emit("begin",task="handoff",plan=p["plan"])
    eng,flow,init = f.handoff(obj,dest/"handoff",dest/"search/physical/evidence"/obj["case"],p)
    emit("end",task="handoff")
    native = eng.cert
    def measured(*args,**kwargs):
        emit("begin",task="dp_cert",stage="direct")
        d,tr = native(*args,**kwargs)
        emit("end",task="dp_cert",stage="direct",kernel_s=d["cert_s"])
        return d,tr
    eng.cert = measured
    direct(eng,flow,init,dest,emit)
    emit("natural")


def main(code,arm,budget,dest):
    assert arm in ("A","B") and budget in (60,600)
    f.ORIGIN = m.CLOCK = float(os.environ["CELL_START"])
    f.log(dest/"start.jsonl","begin",core=list(os.sched_getaffinity(0)))
    m.RUN = m.u2.stack()
    m.RUN[0].e.expand = expand
    if arm == "B":
        f.refine = refine_safe
        paired.online.refine_hot = direct
    obj = next(o for o in m.u2.CASES if m.label(o)==code)
    paired.baseline(obj,dest,budget)


if __name__=="__main__":
    main(sys.argv[1],sys.argv[2],int(sys.argv[3]),Path(sys.argv[4]))
