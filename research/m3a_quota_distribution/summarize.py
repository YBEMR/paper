"""Independently reconstruct time cuts and matched single-step counterfactuals from archives."""
import csv
import gzip
import json
import statistics as st
from collections import Counter,defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data"
TABLES=ROOT/"tables"
CUTS=(.25,.5,1,2,5,10,30)
ARMS=("original","ordinary","thermal")
def read(p):
    return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def write(name,rows):
    TABLES.mkdir(exist_ok=True)
    with (TABLES/(name+".csv")).open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)),lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
def phys(a):
    result=dict(status="TIMING",slack_ticks=a["fifo_slack_ticks"],drain_tick=a["drain_tick"],
                changed_requests=a["changed_requests"])
    if not a["fifo_ok"]:
        return result
    c=a["certificate"]
    m=c["metrics"]
    return dict(**{**result,"status":m["status"]},plan=c["plan_sha256"],E_J=m["E_J"],E35_J=c["E35_J"],
                lo_J=m["E_bounds"][0],hi_J=m["E_bounds"][1],peak_upper_C=max(m["peak_hi"]),
                peak_lower_C=max(m["peak_lo"]),margin_ms=m["min_deadline_slack_ms"],base_J=m["base_J"],
                activity_J=m["activity_J"],switch_J=m["switch_J"],external_J=m["external_J"],
                thermal_J=m["temperature_J"],switches=m["switch_count"],**a["occupancy"])
def saving(a,b):
    return 100*(a["E_J"]-b["E_J"])/a["E_J"]
def best_at(run,cut,p):
    best=run["start"]
    for t in run["calls"]:
        k=t["cfg"]
        if t["at"]<=cut and p[k]["status"]=="SAFE" and p[k]["hi_J"]<p[best]["lo_J"]:
            best=k
    return best

def main():
    endpoints,rows,edges,matched,wall,flow_rows,counts=[],[],[],[],[],[],[]
    for f in sorted(DATA.glob("*/audit.json.gz")):
        z=read(f)
        case=f.parent.name
        base=z["base"]
        p={k:phys(v) for k,v in z["physical"].items()}
        b=p[base]
        rows.extend(dict(case=case,cfg=k,**m) for k,m in p.items())
        edge=z["edges"]
        edges.extend({**r,"case":case,"action":json.dumps(r["action"],separators=(",",":"))} for r in edge)
        runs={}
        for stage in [1,2]:
            path=f.parent/f"s{stage}.json.gz"
            if not path.exists():continue
            for r in read(path)["runs"]:
                runs[stage,r["arm"],r["repeat"]]=r
                assert best_at(r,30,p)==r["winner"]
        rec=dict(case=case,NT_J=b["E_J"],NT_peak_C=b["peak_upper_C"],NT_slack_ms=b["margin_ms"])
        phase1={r["cfg"] for r in edge if r["stage"]==1}
        feasible=[p[k] for k in phase1 if p[k]["status"]=="SAFE"]
        rec.update(s1_variants=len(phase1),s1_SAFE=len(feasible),s1_TIMING=sum(p[k]["status"]=="TIMING" for k in phase1),
                   s1_HOT=sum(p[k]["status"]=="HOT" for k in phase1))
        best_audit=min([b,*feasible],key=lambda x:x["E_J"])
        rec["s1_audit_best_saving_pct"]=saving(b,best_audit)
        for arm in ARMS:
            for stage in [1,2]:
                r=runs.get((stage,arm,1))
                if stage==2 and not r:continue
                k=r["winner"] if r else base
                m=p[k]
                parent=p[r["start"]] if r else b
                prefix=f"s{stage}_{arm}_"
                rec[prefix+"J"]=m["E_J"]
                rec[prefix+"saving_pct"]=saving(b,m)
                rec[prefix+"increment_J"]=parent["E_J"]-m["E_J"]
                endpoints.append(dict(case=case,stage=stage,arm=arm,cfg=k,parent=r["start"] if r else base,
                                   n_candidates=len(r["candidates"]) if r else 0,n_certified=len(r["calls"]) if r else 0,
                                   saving_pct=saving(b,m),delta_ref_J=b["E35_J"]-m["E35_J"],
                                   delta_thermal_J=b["thermal_J"]-m["thermal_J"],**m))
                for rep in range(1,4):
                    q=runs.get((stage,arm,rep))
                    r1=runs.get((1,arm,rep))
                    for cut in CUTS:
                        for regime in (("stage",) if stage==1 else ("stage","cumulative")):
                            offset=(r1["elapsed"] if r1 else 0) if regime=="cumulative" else 0
                            if cut < offset:
                                key=best_at(r1,cut,p)
                                nc=sum(t["at"]<=cut for t in r1["calls"])
                            else:
                                key=best_at(q,cut-offset,p) if q else base
                                nc=sum(t["at"]<=cut-offset for t in q["calls"]) if q else 0
                                nc+=len(r1["calls"]) if regime=="cumulative" and r1 else 0
                            wall.append(dict(case=case,stage=stage,arm=arm,repeat=rep,regime=regime,cut_s=cut,cfg=key,
                                         certified_new=nc,SAFE_J=p[key]["E_J"],saving_pct=saving(b,p[key]),
                                         finish_s=offset+(q["elapsed"] if q else 0)))
        if (2,"original",1) in runs:
            orig={tuple(r["action"]):r for r in edge if r["stage"]==2 and r["arm"]=="original"}
            for arm in ARMS:
                tests=[v for v in edge if v["stage"]==2 and v["arm"]==arm]
                assert set(orig)=={tuple(t["action"]) for t in tests}
                for t in tests:
                    a=tuple(t["action"])
                    old=orig[a]["cfg"]
                    v=t["cfg"]
                    x,y=p[old],p[v]
                    label="same_status" if x["status"]==y["status"] else x["status"]+"_to_"+y["status"]
                    matched.append(dict(case=case,arm=arm,window_1based=a[0]+1,device=["GPU","NPU"][a[1]-2],
                                    original_cfg=old,changed_cfg=v,parent=t["parent"],original_status=x["status"],
                                    changed_status=y["status"],transition=label,original_slack_ticks=x["slack_ticks"],
                                    changed_slack_ticks=y["slack_ticks"],original_J=x.get("E_J"),changed_J=y.get("E_J"),
                                    original_peak_upper_C=x.get("peak_upper_C"),changed_peak_upper_C=y.get("peak_upper_C"),
                                    selected=runs[2,arm,1]["winner"]==v))
        flow_rows.append(rec)
        stage1_family={(r["family"],r["cfg"]) for r in edge if r["stage"]==1}
        for fam in ("phase","swap"):
            ks={k for family,k in stage1_family if family==fam}
            vals=[p[k] for k in ks if p[k]["status"]=="SAFE"]
            counts.append(dict(case=case,family=fam,total=len(ks),SAFE=len(vals),
                               **{s:sum(p[k]["status"]==s for k in ks) for s in ("TIMING","HOT","UNRESOLVED","OUT_OF_MODEL")},
                               min_peak_upper_C=min((v["peak_upper_C"] for v in vals),default=None),
                               max_peak_upper_C=max((v["peak_upper_C"] for v in vals),default=None),
                               best_saving_pct=max((saving(b,v) for v in vals),default=None)))
    for name,vals in [("cases",flow_rows),("endpoints",endpoints),("candidates",rows),("actions",edges),
                      ("paired_lower",matched),("wallclock",wall),("families",counts)]:
        write(name,vals)
    agg=defaultdict(list)
    for r in wall:
        agg[r["stage"],r["arm"],r["regime"],r["cut_s"]].append(r)
    means=[]
    for (stage,arm,regime,cut),items in agg.items():
        groups=defaultdict(list)
        for r in items:groups[r["case"]].append(r)
        means.append(dict(stage=stage,arm=arm,regime=regime,cut_s=cut,cases=len(groups),
                     mean_case_median_saving_pct=st.mean(st.median(x["saving_pct"] for x in g) for g in groups.values()),
                     improved_case_medians=sum(st.median(x["saving_pct"] for x in g)>0 for g in groups.values()),
                     min_run_saving_pct=min(x["saving_pct"] for x in items),
                     max_run_saving_pct=max(x["saving_pct"] for x in items)))
    write("wallclock_summary",means)

if __name__=="__main__":
    main()
