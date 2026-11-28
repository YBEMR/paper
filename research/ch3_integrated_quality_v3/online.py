"""Compare frozen V2 against a single conditional HOT-only fourth position."""
import functools
import os
import sys
import numpy as np
from hot import ROOT,OUT,v2,f,m,census,nominees,valid,handoff,refine_hot


def select(events,physical,horizon):
    @functools.lru_cache(maxsize=None)
    def mapping(key):
        return v2.identity(f.read(physical/key/"plan.json"))
    seeds,_=v2.representatives(events,55,mapping)
    safe,hot,only,_=census(events,mapping)
    base4=seeds[3]["point"] if len(seeds)>3 else None
    winner,_=nominees(only)
    used=False
    if winner and winner["point"]["bounds"][1]<seeds[0]["point"]["bounds"][0]:
        src=physical/winner["point"]["plan"]
        with np.load(src/"trace.npz") as a:
            assert valid(a["events"],horizon)
        assert m.endpoint(f.read(src/"certificate.json"))==winner["point"]
        seeds=seeds[:3]+[winner]
        used=True
    meta=dict(safe_count=len(safe),hot_only=len(only),shared=len(set(safe)&set(hot)),displaced=base4,
              eligible=used,seeds=[r["point"]["plan"] for r in seeds])
    return seeds,meta


def refine(obj,dest,events):
    f.arm_alarm(f.ORIGIN+60)
    m.CLOCK=f.ORIGIN
    log=f.log
    ledger=dest/"refine.jsonl"
    root=dest/"search/physical/evidence"/obj["case"]
    log(ledger,"begin",task="selection")
    seeds,meta=select(events,root,obj["horizon_ticks"])
    log(ledger,"end",task="selection",**meta)
    global_best=seeds[0]["point"]
    original=f.handoff
    try:
        for i,seed in enumerate(seeds,1):
            point=seed["point"]
            is_hot=point["status"]=="HOT"
            rank=4 if is_hot else i
            tag=f"map{rank}"
            folder=dest/tag;folder.mkdir()
            local=None if is_hot else point
            log(ledger,"map_start",rank=rank,seed=point["plan"],kind=point["status"])
            def observe(event,**fields):
                nonlocal global_best,local
                if "stage" in fields:
                    fields["stage"]=tag+"/"+fields["stage"]
                if event=="certificate":
                    p=fields["point"]
                    if f.strict(p,local):
                        local=p
                        if f.strict(p,global_best):global_best=p
                    fields.update(local_best=local["plan"] if local else None,global_best=global_best["plan"])
                log(ledger,event,rank=rank,**fields)
            if is_hot:
                observe("begin",task="handoff",plan=point["plan"])
                eng,flow,init=handoff(obj,folder/"handoff",root/point["plan"],point)
                observe("end",task="handoff")
                native_cert=eng.cert
                def measured(*args,**kwargs):
                    stage=eng.out.name
                    observe("begin",task="dp_cert",stage=stage)
                    d,tr=native_cert(*args,**kwargs)
                    observe("end",task="dp_cert",stage=stage,kernel_s=d["cert_s"])
                    return d,tr
                eng.cert=measured
                result=refine_hot(eng,flow,init,folder,observe)
                assert result==local
            else:
                f.log=lambda path,event,**kw:observe(event,**kw)
                f.handoff=lambda case,target,unused,pt:original(case,target,root,pt)
                f.refine(obj,folder,seed)
                f.log,f.handoff=log,original
            log(ledger,"map_end",rank=rank,local_best=local["plan"] if local else None,global_best=global_best["plan"])
    finally:
        f.log,f.handoff=log,original


def main(code):
    gate=f.read(OUT/"history/gate.json")
    assert gate["passed"] and gate["witnesses"]
    example=gate["witnesses"][0]
    assert example["online_selected"] and example["witness"] and example["safe_upper"]<example["historical_four_J"]
    # Scope/acceptance interface precheck without running additional optimizations.
    def pt(status,lo,hi):return dict(status=status,bounds=[lo,hi])
    assert not f.strict(pt("HOT",0,1),None) and not f.strict(pt("OUT_OF_MODEL",0,1),None)
    assert f.strict(pt("SAFE",5,6),None) and not f.strict(pt("SAFE",5,6),pt("SAFE",6,7))
    assert f.strict(pt("SAFE",5,6),pt("SAFE",7,8))
    prep=f.warm()
    obj=next(r for r in m.u2.CASES if m.label(r)==code)
    directory=OUT/code
    order=[]
    for i in (1,2,3):
        arms=["multi","hot"]
        if (obj["index"]+i-1)%2:arms.reverse()
        order.extend((i,a) for a in arms)
    f.save(directory/"lane.json",dict(warm=prep,order=order,case=obj["case"],input_sha=obj["input_sha256"],source=os.environ["GITHUB_SHA"]))
    baseline=v2.refine_many
    for rep,arm in order:
        v2.refine_many=baseline if arm=="multi" else refine
        v2.cell(obj,rep,arm,directory/f"r{rep}-{arm}")
    v2.refine_many=baseline

if __name__=="__main__":
    main(sys.argv[1])
