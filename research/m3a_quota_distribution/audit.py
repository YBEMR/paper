"""Offline census. Never import these observations into search or gate decisions."""
import csv
import io
import json
import zipfile
from collections import Counter
from core import (
    OUT,WORK,bind,cases,distribution,e,evaluate,lower,np,read,save,seed,sha,transitions,
)

def csv_bytes(rows):
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf,fieldnames=list(dict.fromkeys(k for z in rows for k in z)),lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode()


def check_action(c,parent,cfg,stage,action):
    if stage == 1:
        for ids in c.eng.groups:
            for typ in (0,1):
                idx = [i for i in ids if c.kinds[i] == typ]
                assert Counter(parent[i] for i in idx) == Counter(cfg[i] for i in idx)
    else:
        j,u = action
        idx = set(i for i in c.eng.groups[j] if (parent[i] >= 10) == (u == 3))
        assert idx and all(cfg[i] == x-int(i in idx) and (cfg[i]>=10)==(x>=10) for i,x in enumerate(parent))


def occupancy(c,plan,cert):
    by_node = {}
    for u in range(4):
        spans = [(s,s+c.p.dur(i,unit,k),"busy",i,k) for i,(unit,k,s) in enumerate(plan["rows"]) if unit == u]
        domain = (0,0,1,2)[u]
        spans.extend((a,b,"switch",-1,k) for a,b,d,_,k in cert["switches"] if d == domain)
        spans.sort()
        end,opp = 0,0
        full = []
        for a,b,state,i,k in spans:
            assert end <= a < b
            if a > end:
                full.append((end,a,"idle",-1,opp))
            full.append((a,b,state,i,k))
            end,opp = b,k
        if end < c.p.horizon:
            full.append((end,c.p.horizon,"idle",-1,opp))
        by_node[u] = full
    return by_node


def audit(item):
    c = bind(item)
    label = c.label
    folder = OUT/label
    cfg,_,ix = seed(label)
    base = sha(cfg)
    stages = [read(folder/"s1.json.gz")["runs"]]
    if read(OUT/"gate.json")["open"]:
        stages.append(read(folder/"s2.json.gz")["runs"])
    plans = {base:cfg}
    edges = []
    selected = {base}
    for stage,runs in enumerate(stages,1):
        for arm in sorted({r["arm"] for r in runs}):
            group = [r for r in runs if r["arm"] == arm]
            primary, = [r for r in group if r["repeat"] == 1]
            for r in group:
                assert r["start"] == primary["start"] and r["winner"] == primary["winner"]
                assert [(x["cfg"],x["metrics"]) for x in r["calls"]] == [(x["cfg"],x["metrics"]) for x in primary["calls"]]
            parent = plans[primary["start"]]
            candidates = (distribution if stage == 1 else lower)(c,parent)
            assert [z["cfg"] for z in primary["candidates"]] == [sha(x) for _,_,x in candidates]
            for (fam,action,new),rr in zip(candidates,primary["candidates"]):
                check_action(c,parent,new,stage,action)
                assert fam == rr["family"] and action == rr["action"]
                key = sha(new)
                plans[key] = new
                edges.append(dict(stage=stage,arm=arm,parent=sha(parent),cfg=key,family=fam,action=action))
            selected.add(primary["winner"])
    env = WORK/"native/evidence"/label
    archive = {}
    timing_bad = 0
    members = []
    with zipfile.ZipFile(folder/"traces.zip","w",compression=zipfile.ZIP_DEFLATED,compresslevel=5) as z:
        for key,new in plans.items():
            r = c.ledger(new,0,c.p.horizon,2500,True,True,True)
            slack = np.asarray(c.eng.D)-r[6]-np.asarray(c.eng.q)
            finish = int(max(r[6]+c.args[4]))
            info = dict(config_hex=new.hex(),fifo_ok=bool(r[0]),fifo_slack_ticks=int(min(slack)),
                        drain_tick=finish,changed_requests=sum(a!=b for a,b in zip(cfg,new)))
            assert min(slack) == r[-1]
            if r[0]:
                cert,arr = c.certify(new)
                dest = env/cert["plan_sha256"]
                plan = read(dest/"plan.json")
                assert sha(e.p1.raw(plan)) == cert["plan_sha256"]
                assert np.array_equal(np.asarray(plan["rows"])[1::3,2],r[4])
                m = cert["metrics"]
                assert abs(cert["E35_J"]-m["base_J"]-m["activity_J"]-m["switch_J"]-m["external_J"]) < 1e-8
                assert abs(m["E_J"]-cert["E35_J"]-m["temperature_J"]) < 1e-8
                assert abs(r[1]+c.base*c.p.horizon/10000-cert["E35_J"]) < 1e-8
                if key == base:
                    assert sha(arr.tobytes()) == ix["event_array_sha256"]
                info.update(certificate=cert,plan=plan,event_sha256=sha(arr.tobytes()))
                occ = occupancy(c,plan,cert)
                summary = {}
                for u,intervals in occ.items():
                    total = 0
                    for s in ("busy","idle","switch"):
                        lengths = [b-a for a,b,v,_,_ in intervals if v == s]
                        summary[f"u{u}_{s}_ticks"] = sum(lengths)
                        summary[f"u{u}_{s}_count"] = len(lengths)
                        if s == "idle":
                            summary[f"u{u}_max_idle_ticks"] = max(lengths,default=0)
                        total += sum(lengths)
                    assert total == c.p.horizon
                info["occupancy"] = summary
                if key in selected:
                    # Column-major layout improves lossless ZIP compression for repeated power fields.
                    buf = io.BytesIO()
                    np.save(buf,np.ascontiguousarray(arr.T),allow_pickle=False)
                    z.writestr(key+"/events_T.npy",buf.getvalue())
                    z.writestr(key+"/intervals.csv",csv_bytes([dict(node=u,start_tick=a,end_tick=b,state=v,
                                                              stage_row=i,opp_after_or_active=k)
                               for u,spans in occ.items() for a,b,v,i,k in spans]))
                    z.writestr(key+"/requests.csv",csv_bytes([dict(request=i,kind=c.eng.types[i],release_tick=c.release[i],
                                      deadline_tick=c.eng.D[i],pre_start=c.eng.ps[i],ready=c.eng.a[i],
                                      device=plan["rows"][3*i+1][0],opp=plan["rows"][3*i+1][1],
                                      main_start=r[4][i],main_end=r[5][i],post_start=r[6][i],
                                      post_end=r[6][i]+c.eng.q[i]) for i in range(len(new))]))
                    members.append(key)
            else:
                timing_bad += 1
                info.update(status="TIMING",starts=r[4],ends=r[5],posts=r[6],post_finish=r[6]+c.args[4],
                            missed=np.flatnonzero(slack<0),device_end=r[2],last_opp=r[3],horizon=c.p.horizon)
                assert c.eng.replay([(3,k-10) if k>=10 else (2,k) for k in new]) is None
            archive[key] = info
    assert selected == set(members)
    for runs in stages:
        for r in runs:
            for t in r["calls"]:
                a = archive[t["cfg"]]["certificate"]
                assert t["plan"] == a["plan_sha256"] and t["metrics"] == a["metrics"]
    save(folder/"audit.json.gz",dict(case=label,base=base,traces=members,edges=edges,physical=archive))
    print(label,"unique",len(plans),"timing rejects",timing_bad,"traces",len(members),flush=True)


if __name__ == "__main__":
    import sys
    for item in cases():
        if not sys.argv[1:] or item["index"] in list(map(int,sys.argv[1:])):
            audit(item)
