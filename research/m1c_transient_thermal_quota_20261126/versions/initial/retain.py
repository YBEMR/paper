"""Four competing rules for the fourth open-window slot. No archived inputs."""
from bisect import bisect_left
from time import perf_counter
from common import WINDOW, diverse, window_types, np, p1

RULES=("original","time_energy","joint","suffix")

def positions(values):
    ordered=sorted(round(float(x),10) for x in values)
    return [bisect_left(ordered,round(float(x),10)) for x in values]

def shortlist(pool,original):
    locked={s["id"] for s in original[:3]}
    available=[s for s in pool if s["id"] not in locked]
    orders=[sorted(available,key=lambda s:(s[key]*sign,s["energy"],s["config"]))
            for key,sign in (("energy",1),("drain",1),("risk",1),("slack",-1))]
    out=[original[3]]; seen=locked|{out[0]["id"]}
    for group in zip(*orders):
        for s in group:
            if s["id"] not in seen:
                out.append(s);seen.add(s["id"])
                if len(out)==12:
                    return out
    return out

def probes(c,s,j,types):
    _,a,b=types
    d=c.eng.length; e=c.eng.inc
    actions=[];loads=[];costs=[]
    for g,n in p1.PAIRS:
        x,y=c.eng.quota(s,j,(g,n),(a,b))
        fg=max(0,s["f"][0]+5*(s["k"][0]!=g)-j*WINDOW)+(a-x)*d["A",2,g]+(b-y)*d["B",2,g]
        fn=max(0,s["f"][1]+5*(s["k"][1]!=n)-j*WINDOW)+x*d["A",3,n]+y*d["B",3,n]
        actions.append((g,n,x,y));loads.append(max(fg,fn))
        costs.append(((a-x)*e["A",2,g]+(b-y)*e["B",2,g]+x*e["A",3,n]+y*e["B",3,n])/c.eng.scale)
    er,tr=positions(costs),positions(loads)
    idx=range(len(actions))
    chosen=[]
    for order in (lambda i:(max(0,loads[i]-13000),costs[i],loads[i]),
                  lambda i:(loads[i],costs[i]),lambda i:(max(0,loads[i]-13000),tr[i]+er[i],costs[i])):
        chosen.append(min((i for i in idx if i not in chosen),key=order))
    return [actions[i] for i in chosen]

def prediction(c,s,j,thermal,counts,records):
    types=window_types(c,j)
    lo=j*WINDOW
    final=j+1==c.windows
    right=c.p.horizon if final else lo+WINDOW
    tick=perf_counter()
    actions=probes(c,s,j,types)
    counts["probe_design_s"]+=perf_counter()-tick
    counts["opp_centers"]+=len(p1.PAIRS)
    options=[]
    for act in actions:
        tick=perf_counter()
        cfg=s["config"]+c.extension(*types,*act)
        l=c.ledger(cfg,lo,right,2500,final,thermal)
        local_slack=min(c.args[5][len(s["config"]):len(cfg)]-l[6][len(s["config"]):]-c.args[4][len(s["config"]):len(cfg)])
        counts["look_fifo_s"]+=perf_counter()-tick
        counts["look_fifo"]+=1;counts["look_replayed_requests"]+=len(cfg)
        peak=None; end=None
        if thermal:
            tick=perf_counter()
            end=s["temperature"];peak=s["peak"]
            for i,m in enumerate(l[8]):
                end=c.propagate(end,m,min(2500,right-lo-i*2500)/WINDOW)
                peak=max(peak,max(end))
            counts["look_thermal_steps"]+=len(l[8])
            counts["look_thermal_s"]+=perf_counter()-tick
        record=dict(prefix=s["id"],window=j,next_counts=types[1:],action=act,
                    ok=bool(l[0]),slack_ticks=int(local_slack),all_slack_ticks=int(l[-1]),ref_cost=l[1],
                    projected_peak=peak,temperature=end,next_moments=l[8] if thermal else None)
        records.append(record)
        options.append(record)
    def score(v):
        thermal_gap=max(0.,v["projected_peak"]-80) if thermal else 0.
        return (not v["ok"],max(0,-v["all_slack_ticks"]),thermal_gap,v["ref_cost"],-v["slack_ticks"],v["action"])
    best=min(options,key=score)
    return best

def retain(c,j,pool,rule,counts,forecasts):
    ordered=sorted(pool,key=lambda s:(round(s["energy"],11),s["config"]))
    last=j+1==c.windows
    legacy=diverse(ordered,last)
    if last or len(legacy)<4 or rule=="original":
        return legacy,[]
    shortlist_states=shortlist(ordered,legacy)
    metrics=[]
    for s in shortlist_states:
        if rule=="joint":
            m=dict(peak=s["peak"],slack=s["slack"],energy=s["energy"],ok=True)
        else:
            v=prediction(c,s,j+1,rule=="suffix",counts,forecasts)
            m=dict(peak=v["projected_peak"],slack=v["slack_ticks"],energy=v["ref_cost"],ok=v["ok"],probe=v["action"])
        metrics.append(m)
    slack=positions([-v["slack"] for v in metrics])
    energy=positions([v["energy"] for v in metrics])
    heat=positions([v["peak"] for v in metrics]) if rule!="time_energy" else [0]*len(metrics)
    for i,(s,m) in enumerate(zip(shortlist_states,metrics)):
        gap=0. if rule=="time_energy" else max(0.,m["peak"]-80)
        ordinal=slack[i]+heat[i]+(energy[i] if rule!="joint" else 0)
        m.update(id=s["id"],key=(not m["ok"],max(0,-m["slack"]),gap,ordinal,energy[i],i))
    idx=min(range(len(metrics)),key=lambda i:metrics[i]["key"])
    return [*legacy[:3],shortlist_states[idx]],metrics
