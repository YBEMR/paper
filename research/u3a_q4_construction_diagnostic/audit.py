"""Bounded counterfactual diagnostics; only complete causal certificates establish thermal feasibility."""
import gzip
from collections import Counter
from runtime import *
from construct_once import ranked
from certify_retained import assess

def action(ctx,j,parent,pair):
    _,_,flow,e,_=ctx
    kinds=flow.kinds[e.groups[j]]
    a,b=(int(sum(kinds==v)) for v in (0,1))
    x,y=e.quota(parent,j,pair,(a,b))
    return flow.extension(kinds,a,b,*pair,x,y),(x,y)

def replay_witness(ctx,obj,layers,hist):
    _,dest,flow,e,causal=ctx
    key=hist["nt"]["key"]
    folder=dest/"evidence"/obj["case"]/key
    plan=read(folder/"plan.json")
    cfg=tuple(tuple(r[:2]) for r in plan["rows"][1::3])
    encoded=u.encoded(cfg)
    assert len(cfg)==e.n and sha((folder/"plan.json").read_bytes().strip())==key
    replay=causal(flow,encoded)
    computed,built=full(obj["case"],e,cfg,replay)
    assert computed==key and check_trace(folder,built,e.p.horizon)==hist["nt"]["trace"]
    cert=row(read(folder/"certificate.json"))
    assert cert["status"]=="SAFE"
    out=[]
    stop=0
    for j,ids in enumerate(e.groups):
        start=stop
        stop+=len(ids)
        assert ids==list(range(start,stop))
        prefix=encoded[:start]
        parent=e.replay(cfg[:start]) if start else dict(f=(0,0),k=(0,0))
        assert parent is not None
        wanted=encoded[start:stop]
        types=flow.kinds[ids]
        q=[sum(v>=10 and int(t)==h for v,t in zip(wanted,types)) for h in (0,1)]
        pairs=[]
        for pair in ((g,n) for g in range(10) for n in range(3)):
            ext,quota=action(ctx,j,parent,pair)
            pairs.append(dict(pair=pair,quota=quota,match=ext==wanted))
        matches=[p["pair"] for p in pairs if p["match"]]
        attempts=layers[j]["attempts"] if j<len(layers) else []
        present=any(a["score"] is not None and a["parent"]+a["extension"]==encoded[:stop].hex() for a in attempts)
        retained=j<len(layers) and encoded[:stop].hex() in layers[j]["retained"]
        out.append(dict(window=j+1,matched_pairs=matches,nt_quota=q,nt_opp=[sorted({v for v in wanted if v<10}),
            sorted({v-10 for v in wanted if v>=10})],parent_f=parent["f"],parent_k=parent["k"],
            generated_on_actual_path=present,retained_on_actual_path=retained,actual_layer=j<len(layers),
            tested=pairs,nt_prefix_sha256=sha(encoded[:stop])))
    return dict(witness=cert,trace_sha256=hist["nt"]["trace"],windows=out)

def empty_pool(ctx,layers):
    _,_,_,e,_=ctx
    j=len(layers)-1
    boundary=j*e.dur
    parents={}
    trials=[]
    for a in layers[j]["attempts"]:
        assert a["score"] is None
        key=a["parent"]
        prefix=decode(bytes.fromhex(key))
        if key not in parents:
            r=e.replay(prefix)
            parents[key]=dict(f=r["f"],k=r["k"],ticks_until_free=[max(0,t-boundary) for t in r["f"]],
                main_backlog=[sum(u==unit and end>boundary for (u,_),end in zip(prefix,r["ends"])) for unit in (2,3)],
                post_backlog=sum(t+e.q[i]>boundary for i,t in enumerate(r["posts"])),
                boundary_tick=boundary,slack_ticks=r["slack"])
        cfg=prefix+decode(bytes.fromhex(a["extension"]))
        f=[0,0]
        k=[0,0]
        ends=[]
        for i,(u,v) in enumerate(cfg):
            t=u-2
            f[t]=max(e.a[i],f[t]+5*(k[t]!=v))+e.op(i,u,v)[0]
            k[t]=v
            ends.append(f[t])
        post=0
        late=[]
        for i in sorted(range(len(cfg)),key=lambda i:(ends[i],i)):
            post=max(post,ends[i])+e.q[i]
            if post>e.D[i]:
                late.append(dict(request=i,window=e.p.req[i]["scene"]+1,release=e.p.req[i]["release_tick"],
                    unit=cfg[i][0],opp=cfg[i][1],main_end=ends[i],post_end=post,deadline=e.D[i],late_ticks=post-e.D[i]))
        tail_conflict=any(f[t]+5*(k[t]!=0)>e.p.horizon for t in (0,1))
        assert late or tail_conflict or post>e.p.horizon
        chosen,quota=action(ctx,j,parents[key],a["pair"])
        assert chosen.hex()==a["extension"] and list(quota)==a["quota"]
        trials.append(dict(parent=sha(bytes.fromhex(key)),pair=a["pair"],quota=a["quota"],
            ready_with_switch=[max(boundary,a["f"][t]+5*(a["k"][t]!=a["pair"][t])) for t in (0,1)],
            final_f=f,final_k=k,post_end=post,tail_horizon_conflict=tail_conflict,
            post_horizon_conflict=post>e.p.horizon,late_count=len(late),late=late))
    return dict(window=j+1,horizon=e.p.horizon,parents={sha(bytes.fromhex(k)):v for k,v in parents.items()},attempts=trials)

def audit_case(obj,stack):
    ctx=case_context(obj,stack)
    code,dest,flow,e,_=ctx
    pol=read(dest/"policies.json")
    assert pol["first_safe"] is None
    layers=json.loads(gzip.decompress((dest/"raw_pool.json.gz").read_bytes()))
    hist=read(dest/"history.json")
    info=dict(nt_path=replay_witness(ctx,obj,layers,hist))
    if code=="B07":
        info["empty"]=empty_pool(ctx,layers)
        save(dest/"audit.json",info)
        return
    final=ranked(layers[-1])
    terminal=[]
    for pos,h in enumerate(final[4:12],5):
        rec=assess(ctx,obj,h,pos,"terminal_discard")
        terminal.append(rec)
        if rec["status"]=="SAFE": break
    info.update(terminal_unique=len(final),terminal=terminal)
    attempts=[]
    completed={}
    stop=any(r["status"]=="SAFE" for r in terminal)
    # All raw pool members, including pruned ones, are genuine observations of the first run.
    for j,layer in enumerate(layers[:-1]):
        if stop:break
        for rank,hexcode in enumerate(ranked(layer)[4:6],5):
            prefix=bytes.fromhex(hexcode)
            cfg=decode(prefix)
            r=e.replay(cfg)
            assert r is not None
            rec=dict(window=j+1,rank=rank,prefix_sha256=sha(prefix),steps=[])
            for t in range(j+1,len(layers)):
                pair=hist["construction"]["choices"][t][0]
                ext,quota=action(ctx,t,r,pair)
                cfg+=decode(ext)
                r=e.replay(cfg)
                rec["steps"].append(dict(window=t+1,pair=pair,quota=quota,timing_legal=r is not None))
                if r is None:break
            if r is not None:
                assert len(cfg)==e.n
                c=u.encoded(cfg)
                if c not in completed:
                    completed[c]=assess(ctx,obj,c.hex(),len(completed)+1,"prefix_completion")
                rec["certificate"]=completed[c]
                stop=rec["certificate"]["status"]=="SAFE" or len(completed)>=8
            attempts.append(rec)
            if stop:break
    info.update(prefix_attempts=attempts,prefix_distinct_completed=len(completed))
    save(dest/"audit.json",info)

if __name__=="__main__":
    stack=u.stack()
    obj=next(o for o in u.CASES if o["case"].startswith(sys.argv[1]+"_"))
    audit_case(obj,stack)
