"""One causal certificate per distinct retained configuration; share recordings across policies."""
from runtime import *

def assess(ctx, obj, hexcode, rank, phase):
    code,dest,flow,eng,causal=ctx
    c=bytes.fromhex(hexcode)
    cfg=decode(c)
    history=read(dest/"history.json")
    start=times()
    native=eng.replay(cfg)
    assert native is not None
    native_key,native_built=full(obj["case"],eng,cfg,native)
    native_time=duration(start)
    start=times()
    r=causal(flow,c)
    assert r is not None
    key,built=full(obj["case"],eng,cfg,r)
    replay_time=duration(start)
    folder=dest/"evidence"/obj["case"]/key
    reuse=(folder/"certificate.json").is_file()
    if phase=="retained" and rank==1:
        assert native_key==history["native"]["key"] and key==history["causal"]["key"] and reuse
        native_folder=folder.parent/native_key
        check_trace(native_folder,native_built,eng.p.horizon)
        assert read(native_folder/"plan.json")==json.loads(raw(dict(case=obj["case"],rows=native_built["rows"],low=sorted(native_built["low"]))))
    start=times()
    if reuse:
        cert=read(folder/"certificate.json")
        assert cert["plan_sha256"]==key and sha((folder/"plan.json").read_bytes().strip())==key
    else:
        cert,_=eng.cert(cfg,r,built)
        assert cert["plan_sha256"]==key
    cert_time=duration(start)
    trace_sha=check_trace(folder,built,eng.p.horizon)
    native_path=folder.parent/native_key
    native_metrics=row(read(native_path/"certificate.json")) if (native_path/"certificate.json").exists() else None
    if native_key!=key and not native_path.exists():
        native_path.mkdir(parents=True)
        save(native_path/"plan.json",dict(case=obj["case"],rows=native_built["rows"],low=sorted(native_built["low"])))
    return dict(rank=rank,phase=phase,config_sha256=sha(c),native_plan=native_key,native_metrics=native_metrics,
                native_reference_J=native_built["e35"],changed_idle=len(set(r["low"])^set(native["low"])),
                native_build=native_time,causal_build=replay_time,cert_or_load=cert_time,reuse=reuse,
                trace_sha256=trace_sha,**row(cert))

def run(obj,stack):
    ctx=case_context(obj,stack)
    code,dest,*_=ctx
    construct=read(dest/"construction.json")
    rows=[]
    for i,c in enumerate(construct["retained"],1):
        p=dest/f"retained_{i}.json"
        if not p.exists():
            save(p,assess(ctx,obj,c,i,"retained"))
        rows.append(read(p))
    assert len(rows)<=4 and len(set(x["config_sha256"] for x in rows))==len(rows)
    def policy(selected):
        winner=None
        for r in selected:
            if r["status"]=="SAFE" and (winner is None or r["bounds"][1]<winner["bounds"][0]):
                winner=r
        extra=selected[1:]
        return dict(considered=len(selected),additional=len(extra),winner_rank=winner["rank"] if winner else None,
                    J=winner["J"] if winner else None,peak_hi=winner["peak_hi"] if winner else None,
                    selected_plan=winner["plan"] if winner else None,
                    extra_wall_s=sum(r["causal_build"]["wall_s"]+r["cert_or_load"]["wall_s"] for r in extra),
                    extra_cpu_s=sum(r["causal_build"]["cpu_s"]+r["cert_or_load"]["cpu_s"] for r in extra))
    first=next((r["rank"] for r in rows if r["status"]=="SAFE"),None)
    save(dest/"policies.json",dict(count=len(rows),first_safe=first,original=policy(rows[:1]),
                                   all=policy(rows),sequential=policy(rows[:first])))
    print(code,[r["status"] for r in rows],flush=True)

if __name__=="__main__":
    stack=u.stack()
    for obj in u.CASES:run(obj,stack)
