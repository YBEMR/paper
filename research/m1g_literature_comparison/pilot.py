"""Independent S32 and 160-request L/H functionality checks before the public batch."""
from pathlib import Path
import os
os.environ.setdefault("M1G_RAW",str(Path(__file__).resolve().parent/"pilot_raw"))
import numpy as np
from types import SimpleNamespace
from experiment import OUT, ROOT, e, standalone, certify_native
from literature import Calendar,Profile,HeatProbe,li_map,lft,reference
from collections import Counter


def run():
    dest=OUT/"pilot"
    small=e.p1.Engine("S32",dest)
    case=SimpleNamespace(p=small.p,label="S32")
    stats=Counter()
    prof=Profile(case.p)
    assert set(prof.order["main"])=={(u,k) for u,K in [(2,10),(3,3)] for k in range(K)}
    assert prof.residual["main"]>1e-10
    assert len(reference(case.p,prof))==case.p.n
    book=Calendar(case.p)
    book.add(0,0,1,5)
    assert book.slot(3,1,1,5,100)==5
    assert book.slot(3,1,0,5,100)>=5+case.p.dur(0,0,1)+5
    probe=HeatProbe(case.p)
    cold=probe.peak()
    probe.add(1,2,9,100,1)
    hot=probe.peak()
    probe.add(1,2,9,100,-1)
    assert hot>cold and abs(probe.peak()-cold)<1e-9
    results=[]
    for method in ("Zhou","Li"):
        result=standalone(case,method,dest)
        assert result["stages"],result
        results.append(result)
    # Exercise the reverse-LFT frequency and time adjustment even when a natural
    # small mapping already uses low OPPs. This fixture never enters the comparison.
    # Use a complete, deliberately high-frequency legal schedule for LFT.
    full=Calendar(case.p)
    for j,req in enumerate(case.p.req):
        for h,(u,k) in enumerate(((0,2),(2,9),(1,2))):
            i=3*j+h
            left=req["release_tick"] if h==0 else case.p.finish(i-1,full.rows[i-1])
            t=full.slot(i,u,k,left,case.p.horizon)
            if t is None:
                break
            full.add(i,u,k,t)
    assert all(r is not None for r in full.rows)
    prior=certify_native(case,full,dest)
    lft(case.p,full,stats)
    after=certify_native(case,full,dest)
    assert prior["metrics"]["status"]==after["metrics"]["status"]=="SAFE"
    assert stats["LFT_lowered"]>0 and stats["LFT_delayed"]>0
    # A matched two-window fixture uses the same stream generator as the large batch.
    c=e.case_for("L320")
    label="V160_LH"
    e.p1.CFG["instances"][label]=[list("LH"),1,35,1]
    eng=e.p1.Engine(label,dest)
    eng.dur=10000
    c.label,c.p,c.eng,c.windows=label,eng.p,eng,2
    c.release=np.array([r["release_tick"] for r in c.p.req],np.int64)
    c.kinds=np.array(eng.kindidx,np.int64)
    c.args=(c.release,c.kinds,*[np.array(x,np.int64) for x in (eng.ps,eng.a,eng.q,eng.D)],*c.args[6:-1],eng.p.horizon)
    for method in ("ZQ","LQ"):
        result=standalone(c,method,dest)
        assert result["stats"]["valid_pool"]>0
        results.append(result)
    e.p1.put(ROOT/"data/pilot.json",dict(fixture="S32 and V160_LH",native_LFT_fixture=dict(stats),fixture_certificates=[prior["plan_sha256"],after["plan_sha256"]],
             cold_peak=cold,hot_probe=hot,factor_residual=prof.residual,runs=results))
    print([(r["method"],r["final_status"]) for r in results],dict(stats))


if __name__=="__main__":
    run()
