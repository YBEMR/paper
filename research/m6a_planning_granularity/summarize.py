"""Read only completed online certificates. Separate offline replays retain their own labels."""
import collections
import itertools
from granularity_runtime import *

def rows(path, fast=False):
    try:
        import orjson
        parse=orjson.loads
    except ImportError:
        parse=json.loads
    with path.open("rb") as stream:
        for line in stream:
            if line.endswith(b"\n"):
                yield parse(line)

def table(path, rows):
    if rows:
        with path.open("w",encoding="utf8",newline="") as f:
            w=csv.DictWriter(f,lineterminator="\n",fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
            w.writeheader()
            w.writerows(rows)

def best(records):
    return min((r for r in records if r["metrics"]["status"]=="SAFE"),key=lambda r:r["metrics"]["E_J"],default=None)

def evidence(c,folder,r):
    loc=folder/"native/physical/evidence"/c.label/r["plan"]
    plan=read(loc/"plan.json")
    assert sha(p1.raw(plan))==r["plan"]
    assert read(loc/"certificate.json")["metrics"]==r["metrics"]
    return plan

def physical(c,cfg,cert,tr):
    m=cert["metrics"]
    dt=tr[:,1]-tr[:,0]
    z=c.ledger(cfg,0,c.p.horizon,2500,True)
    assert z[0]
    assert abs(float(dt@(tr[:,2:6].sum(axis=1)+.3))/10000-cert["E35_J"])<1e-8
    assert abs(tr[:,26:30].sum()+m["external_J"]-m["E_J"])<1e-8
    payload=read(c.eng.out/"evidence"/c.label/cert["plan_sha256"]/"plan.json")
    times=tr[:,0]
    idle=np.ones((len(tr),4),dtype=bool)
    for i,(u,k,s) in enumerate(payload["rows"]):
        lo,hi=times.searchsorted([s,s+c.p.dur(i,u,k)])
        idle[lo:hi,u]=False
    switched=sum((b-a)*3/10000 for a,b,*_ in cert["switches"])
    idle_J=float(np.sum(tr[:,26:30]*idle))-switched
    arr=np.frombuffer(cfg,np.uint8)
    freq=collections.Counter(map(int,arr))
    boundaries=(c.release//c.eng.dur+1)*c.eng.dur
    return dict(plan=cert["plan_sha256"],status=m["status"],J=m["E_J"],E35_J=cert["E35_J"],
                peak_C=max(m["peak_hi"]),slack_ms=m["min_deadline_slack_ms"],switches=m["switch_count"],
                idle_J=idle_J,idle35_J=float(np.sum(tr[:,2:6]*dt[:,None]*idle)/10000)-switched,
                base_J=m["base_J"],activity_J=m["activity_J"],temperature_J=m["temperature_J"],
                switch_J=m["switch_J"],external_J=m["external_J"],gpu=int((arr<10).sum()),
                npu=int((arr>=10).sum()),frequency_hist=json.dumps(freq,sort_keys=True),
                main_ends_after_window=int(np.count_nonzero(z[5]>boundaries)))

def swapped(c, mapping, frequencies, width):
    # Transfer only observed per-device modes. An unused donor device has no
    # assigned OPP; use recipient mode and explicitly count such requests.
    groups={}
    for i,k in enumerate(frequencies):
        key=(int(c.release[i])//width,k>=10)
        if key in groups: assert groups[key]==k
        groups[key]=k
    absent=0
    mixed=[]
    for i,k in enumerate(mapping):
        key=(int(c.release[i])//width,k>=10)
        absent+=key not in groups
        mixed.append(groups.get(key,k))
    return bytes(mixed),absent

def run():
    summary=[]; layers=[]; idle=[]; crossover=[]; fixed_enc=[]; counts=[]; calls=[]
    for code in CODES:
        c=flows[code]
        winners={}
        for arm in ARMS:
            ix=set_arm(c,arm)
            folder=OUT/"formal"/code/arm
            rc=read(folder/"receipt.json")
            events=list(rows(folder/"journal.jsonl"))
            completed=[v for v in events if v["kind"]=="certificate" and v["end_s"]<=60]
            attempts=[v for v in events if v["kind"]=="call"]
            for r in completed:
                plan=evidence(c,folder,r)
                assert sha(config(plan))==r["config"] and r["metrics"]["min_deadline_slack_ms"]>=0
                calls.append(dict(case=code,arm=arm,width=r["width"],rank=r["rank"],plan=r["plan"],
                                  end_s=r["end_s"],cert_s=r["end_s"]-r["begin_s"],status=r["metrics"]["status"],
                                  J=r["metrics"]["E_J"],E35_J=r["E35_J"]))
            agg=collections.defaultdict(collections.Counter)
            for grp in rows(folder/"candidates.jsonl",True):
                if isinstance(grp,dict): continue
                w,h,actions,heat=grp
                key=w,h["window"]
                agg[key].update(a[9] for a in actions)
                agg[key]["groups"]+=1
                agg[key]["last_heat_s"]=heat
            for (w,layer),v in agg.items():
                counts.append(dict(case=code,arm=arm,width=w,layer=layer,**v))
            for v in events:
                if "layer" in v:
                    layers.append(dict(case=code,arm=arm,**v))
            for cut in ("W4/K4",10,30,60):
                fixed=cut=="W4/K4"
                rc4=[v for v in completed if v["width"]==4][:4]
                used=rc4 if fixed else [v for v in completed if v["end_s"]<=cut]
                horizon=(rc4[-1]["end_s"] if len(rc4)==4 else 60) if fixed else cut
                timeline=[v for v in events if v["time_s"]<=horizon+.000001]
                w=best(used) if not fixed or len(rc4)==4 else None
                build=sum(max(0,min(horizon,next((b["time_s"] for b in events if b["kind"]=="build_end" and b["width"]==a["width"]),horizon))-a["time_s"]) for a in timeline if a["kind"]=="build")
                # Latest completed group/layer timing is a lower bound during an interrupted build.
                ht=max((v.get("heat_s",0.) for v in timeline),default=0.)
                if cut==60: ht=max([ht]+[v["last_heat_s"] for v in agg.values()])
                m=w["metrics"] if w else {}
                starts=sum(v["begin_s"]<=horizon for v in attempts)
                if fixed and len(rc4)==4: starts=4
                summary.append(dict(case=code,arm=arm,plan_ms=c.eng.dur//10,cut=cut,windows=c.windows,
                    core=rc["core"],fixed_complete=len(rc4)==4,started=starts,completed=len(used),
                    safe_calls=sum(v["metrics"]["status"]=="SAFE" for v in used),
                    first_SAFE_s=next((v["end_s"] for v in used if v["metrics"]["status"]=="SAFE"),None),
                    plan=w["plan"] if w else None,J=m.get("E_J"),lo=(m.get("E_bounds") or [None])[0],
                    hi=(m.get("E_bounds") or [None])[-1],E35_J=w["E35_J"] if w else None,
                    peak_C=max(m["peak_hi"]) if m else None,slack_ms=m.get("min_deadline_slack_ms"),
                    switches=m.get("switch_count"),build_s=build,heat_observed_s=ht,
                    continuous_s=sum(v["physics_s"] for v in used),
                    certification_with_io_s=sum(v["end_s"]-v["begin_s"] for v in used),
                    furthest_layer=max((v["layer"] for v in timeline if v["kind"]=="begin_layer"),default=0),
                    widest_beam=max((v["width"] for v in timeline if v["kind"]=="build"),default=0)))
            w=best(completed)
            if w:
                cfg=config(evidence(c,folder,w))
                winners[arm]=cfg
                for rule,info in (("native",c.eng.dur),("common",2500)):
                    c.information_ticks=info
                    c.eng.out=OUT/"offline"/code/arm/rule
                    cert,tr=c.certify(cfg)
                    if info==ARMS[arm][1]:
                        assert cert["plan_sha256"]==w["plan"]
                    idle.append(dict(case=code,arm=arm,rule=rule,information_ms=info//10,**physical(c,cfg,cert,tr)))
        for arm in "CD":
            set_arm(c,arm)
            if "A" in winners:
                fixed_enc.append(dict(case=code,arm=arm,source="online_A_60",**represent(c,winners["A"])))
            if "B" not in winners or arm not in winners: continue
            for mapped,frequencies,step in (("B",arm,c.eng.dur),(arm,"B",10000)):
                cfg,absent=swapped(c,winners[mapped],winners[frequencies],step)
                z=c.ledger(cfg,0,c.p.horizon,2500,True)
                res=dict(case=code,arm=arm,mapping=mapped,opp=frequencies,missing_opp_requests=absent,
                         slack_ticks=int(z[-1]),feasible=bool(z[0]))
                if z[0]:
                    c.eng.out=OUT/"offline"/code/("map"+mapped+"freq"+frequencies)
                    cert,tr=c.certify(cfg)
                    res.update(physical(c,cfg,cert,tr))
                crossover.append(res)
    for filename, records in (("results",summary),("layers",layers),("candidate_counts",counts),
                              ("certifications",calls),("idle_control",idle),("representability",fixed_enc),
                              ("crossed_controls",crossover)):
        table(OUT/(filename+".csv"),records)
    assert len(summary)==96

