import tarfile
from time import perf_counter
from granularity_runtime import *

def history(code):
    item=CASES[code]
    folder=HISTORY/"research/m1i_generalization/data/evidence"/item["case"]
    path=folder/"runs.tar.xz"
    assert sha(path.read_bytes())==read(folder/"receipt.json")["files"][path.name]
    with tarfile.open(path,"r|xz") as arc:
        for member in arc:
            if member.name=="r1-NT/run.json":
                return json.load(arc.extractfile(member))
    raise ValueError("missing frozen repeat 1")

def control_flags(c,cfg,z):
    available=[0,0]
    flags=z[7]
    for i,k in enumerate(cfg):
        dev=int(k>=10)
        epoch=int(c.release[i])//c.information_ticks*c.information_ticks
        if flags[i]:
            assert available[dev]>=epoch
        available[dev]=int(z[5][i])
    epoch=int(c.release[-1])//c.information_ticks*c.information_ticks
    assert all(not flag or end>=epoch for end,flag in zip(available,flags[-2:]))
    return int(flags.sum())

def run():
    OUT.mkdir(exist_ok=True)
    for code in CODES:
        start=perf_counter()
        c=init_flow(code)
        ix=set_arm(c,"A")
        old=history(code)
        log=stage()
        ordered=e.build(c,"NT",4,start,float("inf"),log)
        prev=old["search"][0]
        assert prev["width"]==4 and len(ordered)==prev["terminal"]
        assert log["beam"]==prev["beam"]
        initial_records=[r for r in old["records"] if r["width"]==4]
        assert len(initial_records)>=4
        for r in initial_records:
            assert ordered[r["rank"]-1]["id"]==r["id"]
        pool=[]
        for r in initial_records[:4]:
            state=ordered[r["rank"]-1]
            cert,ev=c.certify(state["config"])
            m=cert["metrics"]
            frozen=r["cert"]
            assert cert["plan_sha256"]==frozen["plan_sha256"] and cert["E35_exact"]==frozen["E35_exact"]
            assert m["status"]==frozen["metrics"]["status"] and abs(m["E_J"]-frozen["metrics"]["E_J"])<1e-8
            pool.append((m["status"]!="SAFE",m["E_J"],state["config"],cert))
        _,_,cfg,orig=min(pool,key=lambda q:q[:2])
        checks={}
        for arm in ARMS:
            ix=set_arm(c,arm)
            c.eng.out=OUT/"gate"/code/arm
            cert,events=c.certify(cfg)
            z=c.ledger(cfg,0,c.p.horizon,2500,True)
            audit=event_check(c,cfg,events)
            assert abs(audit["integrated_E35_J"]-cert["E35_J"])<1e-8
            flags=control_flags(c,cfg,z)
            if arm in "CD":
                assert cert["plan_sha256"]==checks["B"]["plan"]
            if arm=="A":
                assert cert["plan_sha256"]==orig["plan_sha256"] and represent(c,cfg)["exact_encoding"]
            # Exercise the actual multi-quota generator including clock, grid and forecast.
            l=stage()
            batch,done=e.expand(c,0,[e.initial(c)],"NT",perf_counter(),float("inf"),l)
            assert done and batch and all(len(s["config"])==ix[1] for s in batch.values())
            checks[arm]=dict(**audit,plan=cert["plan_sha256"],early_downs=flags,
                             encoding=represent(c,cfg),first_layer=len(batch),requests=int(ix[-1]))
        save(OUT/"gate"/(code+".json"),dict(case=c.label, sha256_input=CASES[code]["input_sha256"],
             W4_terminal=len(ordered),W4_history_identities=len(initial_records),
             beam_sha256=sha(p1.raw(log["beam"])),W4_order_sha256=sha(p1.raw([s["id"] for s in ordered])),
             first4_plans=[v[3]["plan_sha256"] for v in pool],controls=checks,elapsed_s=perf_counter()-start))
        print("GATE",code,round(perf_counter()-start,2),flush=True)

