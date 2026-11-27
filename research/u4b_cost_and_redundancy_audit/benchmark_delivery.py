"""Registered HOT archival / SAFE delivery comparison, using two real shortlists."""
import contextlib
import inspect
import os
import sys
import tempfile
import textwrap
import time
from pathlib import Path
from types import MethodType

import benchmark as b

def necessary_certificate(engine):
    # Keep every numerical assertion and result. Guard only the original persistence line.
    source=textwrap.dedent(inspect.getsource(engine.cert.__func__))
    marker="    path=self.out/"
    assert source.count(marker)==1
    before,sep,tail=source.partition(marker)
    line,_,rest=tail.partition("\n")
    assert line.endswith("np.savez_compressed(path/'trace.npz',events=trace)")
    scope=dict(engine.cert.__func__.__globals__)
    exec(before+'    if metrics["status"]=="SAFE":\n    '+sep+line+"\n"+rest,scope)
    return MethodType(scope["cert"],engine)

def shortlist(s,out,compact):
    original=s.ctx.e.cert
    s.ctx.e.out=out
    if compact:s.ctx.e.cert=necessary_certificate(s.ctx.e)
    log=b.src.Journal(out)
    def run():
        start=time.perf_counter()
        observed=[]; decision_times=[]
        for rank,cfg in enumerate(s.configs,1):
            if not compact:
                log.emit("choice","terminal",rank,cfg)
                log.emit("cert_start",rank,"terminal",time.perf_counter()-start,cfg)
            state=s.ctx.stack[3](s.ctx.flow,cfg)
            d,tr=s.ctx.e.cert(b.src.genes(cfg),state)
            m=d["metrics"]
            now=time.perf_counter()-start
            rec=dict(n=rank,phase="terminal",plan=d["plan_sha256"],status=m["status"],J=m["E_J"],
                     bounds=m["E_bounds"],peak=max(m["peak_hi"]),slack=m["min_deadline_slack_ms"],kernel_s=d["cert_s"],t=now)
            if compact:
                log.emit("minimal",s.obj["input_sha256"],b.sha(cfg),rank,rec["plan"],rec["status"],now)
            else:log.emit("cert",rec)
            observed.append((d,tr));decision_times.append(now)
            if m["status"]=="SAFE":
                log.emit("delivered",rec,time.perf_counter()-start)
                break
        if compact:log.emit("stop","first_safe",time.perf_counter()-start)
        log.close()
        return observed,decision_times
    try:
        (obs,times),cost=b.measure(run,f"{s.id} fixed shortlist {'delivery' if compact else 'full'}")
    finally:
        s.ctx.e.cert=original
    assert len(obs)==len(s.configs)
    actual=[];retained=[]
    for idx,((d,tr),w) in enumerate(zip(obs,s.references)):
        old=w["certificate"]
        assert all(b.raw(d[k])==b.raw(old[k]) for k in old if k!="cert_s")
        assert b.sha(tr.tobytes())==w["trace_sha256"]
        plan=d["plan_sha256"]
        path=out/"evidence"/s.obj["case"]/plan
        safe=d["metrics"]["status"]=="SAFE"
        assert safe==(idx==len(obs)-1)
        if safe or not compact:
            assert b.raw(b.read(path/"plan.json"))==b.raw(w["plan"])
            assert b.raw(b.read(path/"certificate.json"))==b.raw(d)
            with b.np.load(path/"trace.npz") as archive: assert b.np.array_equal(tr,archive["events"])
            retained.append(plan)
        else:assert not path.exists()
        actual.append(dict(plan=plan,config=b.sha(s.configs[idx]),status=d["metrics"]["status"],
                           trace=w["trace_sha256"],metrics_sha256=b.sha(b.raw(d["metrics"]))))
    return dict(**cost,ordered=actual,ordered_sha256=b.sha(b.raw(actual)),decision_sha256=actual[-1]["plan"],
        first_delivered_rank=len(obs),physical_bytes=sum(p.stat().st_size for p in (out/"evidence").rglob("*") if p.is_file()),
        archived=retained,decision_s=times,stop="first_safe")

def empty_probes():
    bench=b.Meter()
    n=30000
    def nil():return None
    t=time.perf_counter()
    for _ in range(n):nil()
    base=time.perf_counter()-t
    ns={"nil":nil}
    with bench.cleanup:
        bench.hook(ns,"nil","null")
        t=time.perf_counter()
        for _ in range(n):ns["nil"]()
        wrapped=time.perf_counter()-t
    return dict(n=n,bare_s=base,wrap_s=wrapped,increment_per_call_s=(wrapped-base)/n)

def propagation_keys(s,path):
    flow=s.ctx.flow
    original=flow.propagate
    encode=lambda a:b.np.asarray(a,dtype="<f8").tobytes()
    fixed=(encode(flow.p.G),encode(flow.p.cap),encode(float(flow.p.ta)))
    matrices={};full={};initial=set();stream=__import__("hashlib").sha256()
    def observed(temp,moment,dt):
        group=fixed+(encode(moment),encode(dt))
        state=group+(encode(temp),)
        matrices[group]=matrices.get(group,0)+1
        full[state]=full.get(state,0)+1
        initial.add(state[-1])
        stream.update(b"".join(state))
        return original(temp,moment,dt)
    flow.propagate=observed
    try:
        proof=b.nt_layer(s,0,"full",path,None)
    finally:
        flow.propagate=original
    assert sum(matrices.values())==sum(full.values())
    return dict(case=s.id,attempt=b.ATTEMPT,calls=sum(matrices.values()),unique_matrix_keys=len(matrices),
                unique_complete_keys=len(full),unique_temperatures=len(initial),matrix_max_multiplicity=max(matrices.values()),
                full_max_multiplicity=max(full.values()),ordered_keys_sha256=stream.hexdigest(),verified_stage=proof)

def main():
    b.ATTEMPT=int(sys.argv[1])
    b.pulse("delivery cold start",90)
    with tempfile.TemporaryDirectory(prefix="u4-delivery-") as tmp:
        root=Path(tmp)
        b.init_runtime(root)
        b.append("probe_overhead.jsonl",dict(attempt=b.ATTEMPT,**empty_probes()))
        done={(r["case"],r["rep"],r["stage"],r["mode"]) for r in b.rows(b.OUT/"delivery.jsonl")}
        for i,case in enumerate(("I01","I04")):
            b.pulse("prepare "+case,30)
            busy=b.snapshot(case+" before")
            if busy:
                time.sleep(1)
                assert not b.snapshot(case+" recheck"),busy
            p=root/case;p.mkdir()
            s=b.prepare(case,p)
            case_root=b.A/"results"/case
            unit=b.read(case_root/"runs/Base.json")
            ids=[x["plan"] for x in unit["certificates"] if x["phase"]=="terminal"]
            assert len(ids)==(7 if case=="I01" else 2) and ids[-1]==unit["delivered"][0]["plan"]
            import gzip,json
            plans={v["certificate"]["plan_sha256"]:v for line in gzip.decompress((case_root/"physical/plans.jsonl.gz").read_bytes()).splitlines()
                   if (v:=json.loads(line))["certificate"]["plan_sha256"] in ids}
            s.references=[plans[k] for k in ids]
            s.configs=[b.src.u.encoded([r[:2] for r in w["plan"]["rows"][1::3]]) for w in s.references]
            for rep in range(3):
                order=("full","delivery") if (i+rep)%2==0 else ("delivery","full")
                for stage in ("shortlist","nt1_compact"):
                    for mode in order:
                        if (case,rep,stage,mode) in done:continue
                        output=p/f"{rep}-{stage}-{mode}";output.mkdir()
                        if stage=="shortlist":res=shortlist(s,output,mode=="delivery")
                        else:res=b.nt_layer(s,0,"lean" if mode=="delivery" else "full",output,None,mode=="delivery")
                        b.append("delivery.jsonl",dict(case=case,rep=rep,stage=stage,mode=mode,attempt=b.ATTEMPT,
                            start_order=order[0],utc=time.time(),cpu=b.cpu,**res))
            if case not in {r["case"] for r in b.rows(b.OUT/"propagation.jsonl")}:
                output=p/"propagation";output.mkdir()
                b.append("propagation.jsonl",propagation_keys(s,output))
            b.snapshot(case+" after")
        b.pulse("delivery cleanup",30)
    print("Complete",flush=True)

if __name__=="__main__":
    main()
