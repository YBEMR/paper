"""Verify the frozen comparison and derive the paper tables from per-call evidence."""
import csv
import gzip
import json
from collections import Counter, defaultdict
from functools import lru_cache
from itertools import groupby
from pathlib import Path
from statistics import median

from experiment import DATA, D, ROOT, CASES, FIELDS, WINDOW, case_for, reordered, sequences
from experiment import anchors, digest, diverse, initial, load_planes, np, p1, ranking, window_types
from verify import physical

def read(path):
    return json.loads(path.read_bytes())

def table(name, rows):
    with (DATA/name).open("w",newline="",encoding="utf-8") as out:
        writer=csv.DictWriter(out,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def verify_stage(c, method, stage, geometry, ext, backgrounds, audit):
    width=stage["width"]
    states={initial(c)["id"]:b""}
    all_groups=iter(stage["groups"])
    volumes=[]
    terminal={}
    for w, actions in groupby(stage["actions"],key=lambda a:a[0]):
        j=w-1
        _,a,b=window_types(c,j)
        pool={}
        for key, records in groupby(actions,key=lambda x:tuple(x[1:4])):
            parent,g,n=key
            group=next(all_groups)
            assert (w,parent,g,n)==tuple(group[k] for k in ("window","parent","g","n"))
            cfg0=states[parent]
            options,background=backgrounds(j,cfg0)
            options=options[g,n]
            load,points=geometry(j,cfg0,g,n)
            rows=list(records)
            assert len(rows)==len(options)==group["slots"]
            coords={(r[4],r[5]) for r in rows}
            assert len(coords)==len(rows)
            if method[0]=="O" or method=="C2":
                assert coords==options and group["calibration"] is None
            else:
                cal=group["calibration"]
                assert cal["points"]==[list(q) for q in points] and set(points)<=coords
                grid=500 if w==c.windows else 2500
                assert cal["grid"]==grid and cal["bins"]==(27 if w==c.windows else 4)
            for row in rows:
                _,_,_,_,x,y,identity,pilot,original,status,energy,peak,risk,drain,slack=row
                assert original == ((x,y) in options)
                assert pilot == (group["calibration"] is not None and (x,y) in points)
                cfg=cfg0+ext(j,g,n,x,y)
                assert digest(cfg)==identity
                if status=="duplicate":
                    assert identity in pool
                elif status=="valid":
                    assert identity not in pool and slack >= 0
                    if method=="C2" or method[1]=="C":
                        assert risk==max(load[:,0]+load[:,1:]@(x,y))
                        audit["ordinary_risk_values"]+=1
                    if method=="C2":
                        assert peak is None
                    else:
                        assert peak is not None
                    pool[identity]=dict(id=identity,config=cfg,energy=energy,risk=risk,peak=peak,drain=drain)
                else:
                    # FIFO feasibility also includes horizon/return constraints.
                    assert status=="timing"
            volumes.append((group["end_s"],w,len(rows),sum(r[9]=="valid" for r in rows),
                            sum(not r[8] for r in rows)))
            audit["quota_groups"]+=1
        if j<len(stage["beam"]):
            order=sorted(pool.values(),key=lambda s:(round(s["energy"],11),s["config"]))
            front=diverse(order,False)
            frontids={s["id"] for s in front}
            extra=[s for s in order if s["id"] not in frontids]
            chosen=(front+extra)[:width]
            assert [s["id"] for s in chosen]==stage["beam"][j]
            states={s["id"]:s["config"] for s in chosen}
        if w==c.windows and stage["terminal"]:
            assert len(pool)==stage["terminal"]
            terminal=pool
    assert next(all_groups,None) is None
    ids=[s["id"] for s in ranking(terminal,"legacy" if method=="C2" else "safe_energy")] if terminal else []
    return volumes,ids

def summarize(run,stages,mode,budget,nwin):
    cut=run["records"][3]["end_s"] if mode=="fixed" else budget
    records=[r for r in run["records"] if r["end_s"]<=cut]
    safe=[r for r in records if r["cert"]["metrics"]["status"]=="SAFE"]
    best=min(safe,key=lambda r:r["cert"]["metrics"]["E_J"],default={}).get("cert",{})
    m=best.get("metrics",{})
    ready=[s for s in stages if s["ready_s"]<=cut and s["ids"]]
    terminal=set().union(*(set(s["ids"]) for s in ready))
    vols=[v for s in stages for v in s["volumes"] if v[0]<=cut]
    return dict(case=run["case"],method=run["method"],mode=mode,budget_s=cut,observed_s=min(run["wall_s"],cut),
                full_run_s=run["wall_s"],post_cutoff_s=max(0,run["wall_s"]-cut) if mode=="time" else 0,
                first_SAFE_s=safe[0]["end_s"] if safe else None,first_SAFE_rank=records.index(safe[0])+1 if safe else None,
                last_cert_s=records[-1]["end_s"] if records else None,completed=len(records),SAFE=len(safe),
                cert_SAFE_rate=len(safe)/len(records) if records else None,SAFE_J=m.get("E_J"),
                E_low=m.get("E_bounds",[None,None])[0],E_high=m.get("E_bounds",[None,None])[1],
                peak_C=max(m["peak_hi"]) if m else None,lowest_cert_peak_C=min((max(r["cert"]["metrics"]["peak_hi"]) for r in records),default=None),
                plan=best.get("plan_sha256"),proposed=sum(v[2] for v in vols),valid=sum(v[3] for v in vols),
                outside_original=sum(v[4] for v in vols),terminal_proposed=sum(v[2] for v in vols if v[1]==nwin),
                terminal_unique=len(terminal),uncertified_terminal=len(terminal)-len(records),
                ready_widths="/".join(str(s["width"]) for s in ready),started_widths="/".join(str(s["width"]) for s in stages if s["start_s"]<=cut))

def comparison(base,other):
    a,b=base["SAFE_J"],other["SAFE_J"]
    if a is None or b is None:
        verdict="neither" if a is None and b is None else "only_base" if b is None else "only_other"
        pct=None
    else:
        pct=100*(a-b)/a
        verdict="win" if other["E_high"]<base["E_low"] else "loss" if base["E_high"]<other["E_low"] else "tie"
    return dict(case=base["case"],mode=base["mode"],base=base["method"],other=other["method"],
                base_J=a,other_J=b,saving_pct=pct,result=verdict)

def analyze():
    audit=Counter()
    rows=[]; certs=[]; pairs=[]; matched=[]; coverage=[]
    environment=read(DATA/"environment.json")
    for filename,sha in environment["source"].items():
        assert digest((ROOT/filename).read_bytes())==sha
    for label in CASES:
        for word in sequences(int(label[1:])//80):
            c=reordered(case_for(label),label,word)
            assert (DATA/"validation_inputs"/(c.label+".csv")).read_bytes().splitlines()==(D/"data/validation_inputs"/(c.label+".csv")).read_bytes().splitlines()
            folder=DATA/"runs"/c.label
            budget=read(folder/"HT/run.json")["records"][3]["end_s"]
            archived=read(D/"data/validation"/c.label/"trajectories.json")
            baselines={}; visited={}; evidence={}; case_rows={}
            @lru_cache(None)
            def ext(j,g,n,x,y):
                return c.extension(*window_types(c,j),g,n,x,y)
            @lru_cache(None)
            def backgrounds(j,cfg):
                s=initial(c)
                if cfg:
                    v=c.ledger(cfg,(j-1)*WINDOW,j*WINDOW,2500,False,False)
                    s.update(f=tuple(map(int,v[2])),k=tuple(map(int,v[3])))
                groups=defaultdict(set)
                for act,_ in c.candidates(j,s):
                    groups[act[:2]].add(act[2:])
                return groups,s
            @lru_cache(None)
            def geometry(j,cfg,g,n):
                groups,s=backgrounds(j,cfg)
                _,a,b=window_types(c,j)
                load=load_planes(c,j,s,g,n,a,b)
                center=c.eng.quota(s,j,(g,n),(a,b))
                pts,_=anchors(load,center,a,b)
                return load,pts
            for method in ("HT","NT","BT","NC","HC","OC","OT","C2"):
                run=read(folder/method/"run.json")
                records=run["records"]; assert all(x["end_s"]<=y["start_s"] for x,y in zip(records,records[1:]))
                assert len({r["id"] for r in records})==len(records)
                assert run["budget_s"]==(None if method in ("HT","BT") else budget)
                if method in ("HT","C2"):
                    old=archived["frozen" if method=="HT" else "C2"]["records"][:4]
                    for r,o in zip(records[:4],old,strict=True):
                        m=r["cert"]["metrics"]
                        assert (r["id"],r["cert"]["plan_sha256"],m["status"])==(o["id"],o["plan"],o["status"])
                        assert abs(m["E_J"]-o["E"])<1e-8 and abs(max(m["peak_hi"])-o["peak"])<1e-8
                        audit["archived_certificates_reproduced"]+=1
                stages=[]; seen=set()
                for s in run["stages"]:
                    with gzip.open(folder/method/f"w{s['width']}.json.gz","rt") as f: stage=json.load(f)
                    volumes,ids=verify_stage(c,method,stage,geometry,ext,backgrounds,audit)
                    if s["width"]==4 and method in ("NT","HT","BT"):
                        visited[method]={(g["window"],g["parent"],g["g"],g["n"]):(g["slots"],g["calibration"]) for g in stage["groups"]}
                        baselines[method]=set(ids)
                    rec=[r for r in records if r["width"]==s["width"]]
                    eligible=[(i,k) for i,k in enumerate(ids,1) if k not in seen]
                    assert [(r["rank"],r["id"]) for r in rec]==eligible[:len(rec)]
                    seen.update(r["id"] for r in rec)
                    stages.append(dict(**s,volumes=volumes,ids=ids))
                for i,r in enumerate(records,1):
                    cert=r["cert"]; plan=cert["plan_sha256"]; m=cert["metrics"]
                    ref=read(DATA/"physical/evidence"/c.label/plan/"certificate.json")
                    assert {k:v for k,v in ref.items() if k!="cert_s"}=={k:v for k,v in cert.items() if k!="cert_s"}
                    if plan not in evidence:
                        evidence[plan]=physical(c.label,dict(plan=plan,id=r["id"]),len(c.p.req),c.p.horizon)
                    assert evidence[plan][0]==r["id"]
                    certs.append(dict(case=c.label,method=method,call=i,width=r["width"],rank=r["rank"],id=r["id"],plan=plan,
                                 predicted_peak_C=r["prediction"],E35_J=r["ref_E"],E_J=m["E_J"],E_low=m["E_bounds"][0],
                                 E_high=m["E_bounds"][1],status=m["status"],peak_hi_C=max(m["peak_hi"]),slack_ms=m["min_deadline_slack_ms"],
                                 start_s=r["start_s"],end_s=r["end_s"],cert_s=r["cert_s"],within_HT_time=(r["end_s"]<=budget) if method!="BT" else None))
                for mode in (("fixed",) if method=="BT" else ("fixed","time")):
                    row=summarize(run,stages,mode,budget,c.windows)
                    assert row["uncertified_terminal"]>=0
                    rows.append(row); case_rows[method,mode]=row
            audit["unique_physical_plans"]+=len(evidence)
            for A,B in (("NT","HT"),("NT","BT"),("BT","HT")):
                x,y=visited[A],visited[B]; same=x.keys()&y.keys()
                for key in same:
                    assert x[key]==y[key], (c.label,A,B,key)
                matched.append(dict(case=c.label,base=A,other=B,base_groups=len(x),other_groups=len(y),shared_groups=len(same),
                                    checked_calibration_points=3*len(same),unmatched_base=len(x)-len(same),unmatched_other=len(y)-len(same)))
                a,b=baselines[A],baselines[B]; shared=a&b
                coverage.append(dict(case=c.label,base=A,other=B,base_terminal=len(a),other_terminal=len(b),shared=len(shared),
                                     only_base=len(a-b),only_other=len(b-a),jaccard=len(shared)/len(a|b)))
            for mode in ("fixed","time"):
                contrasts=[("NT","HT"),("C2","HT"),("OT","NT"),("OC","NC"),("NC","HC"),("OC","OT"),("NC","NT"),("HC","HT")]
                if mode=="fixed": contrasts += [("NT","BT"),("BT","HT")]
                for A,B in contrasts:
                    pairs.append(comparison(case_rows[A,mode],case_rows[B,mode]))
            ext.cache_clear(); backgrounds.cache_clear(); geometry.cache_clear()
            print("verified",c.label,len(evidence),flush=True)
    table("ablation.csv", rows); table("certifications.csv",certs); table("paired.csv",pairs)
    table("same_parent.csv",matched); table("pool_overlap.csv",coverage)
    counts={}
    for mode in ("fixed","time"):
        for base in ("NT","C2"):
            items=[p for p in pairs if (p["base"],p["other"],p["mode"])==(base,"HT",mode)]
            counts[mode+"_"+base]=dict(Counter(p["result"] for p in items))
    def passed(mode,base,strict):
        p=counts[mode+"_"+base]
        w,l=p.get("win",0),p.get("loss",0)
        return p.get("only_other",0)>=p.get("only_base",0) and (w>l if strict else w>=l)
    promote=passed("fixed","NT",True) and passed("time","NT",True) and passed("time","C2",False)
    p1.put(DATA/"decision.json",dict(freeze_H=promote,counts=counts))
    p1.put(DATA/"verification.json",dict(**audit,independent_runs=64,fixed_rows=64,time_rows=56,actual_certifications=len(certs),
                                       paired_rows=len(pairs),checked_inputs=8))
    return rows,pairs

if __name__=="__main__":
    analyze()
