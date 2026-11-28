"""Equal-flow quality and same-repetition time-to-target, derived only from deadline-eligible receipts."""
import csv
import json
import statistics as st
from collections import Counter,defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
TAB=HERE/"tables"
ARMS=("C1","C2")


def load(path):
    with path.open(encoding="utf-8",newline="") as f:return list(csv.DictReader(f))


def write(name,rows):
    with (TAB/(name+".csv")).open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,list(rows[0]),lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def median(xs):
    return st.median(xs) if xs else None


def mean(xs):
    return st.mean(xs) if xs else None


def main():
    cells=load(TAB/"cells.csv")
    ref=load(HERE.parent/"ch4_inherited_fast_v1/tables/reference60.csv")
    phases=load(TAB/"phases.csv")
    curves=defaultdict(list)
    for r in load(TAB/"improvements.csv"):
        curves[r["case"],r["cap"],r["rep"],r["arm"]].append((float(r["t"]),float(r["upper"])))
    cases=sorted({r["case"] for r in cells})
    bycell={(r["case"],r["cap"],r["rep"],r["arm"]):r for r in cells}
    assert len(cases)==12 and len(bycell)==144
    pairs=[]
    flows=[]
    summaries=[]
    paired_summary=[]
    quality_checks=[]
    for cap in ("10","20"):
        for case in cases:
            baselines=[float(r["J"]) for r in ref if r["case"]==case and r["status"]=="SAFE"]
            assert len(baselines)==3
            base=median(baselines)
            flow=dict(case=case,cap=cap,A60_J=base)
            for arm in ARMS:
                rr=[bycell[case,cap,r,arm] for r in ("1","2","3")]
                js=[float(r["J"]) for r in rr if r["J"]]
                flow.update({arm+"_n":len(js),arm+"_J":median(js),arm+"_gap_pct":100*(median(js)/base-1) if js else None})
            flows.append(flow)
            for rep in ("1","2","3"):
                r1,r2=[bycell[case,cap,rep,m] for m in ARMS]
                a,b=[curves[case,cap,rep,m] for m in ARMS]
                assert bool(a)==bool(r1["hi"]) and bool(b)==bool(r2["hi"])
                target=max(a[-1][1],b[-1][1]) if a and b else None
                def meet(p,goal):
                    if goal is not None:return next((tt for tt,v in p if v<=goal),None)
                quality_checks.append(dict(case=case,cap=cap,rep=rep,reference_target_J=base*1.01,
                        C1_s=meet(a,base*1.01),C2_s=meet(b,base*1.01)))
                t1,t2=[meet(p,target) for p in (a,b)]
                win=None
                if target:
                    win="C2" if float(r2["hi"])<float(r1["lo"]) else "C1" if float(r1["hi"])<float(r2["lo"]) else "overlap"
                pairs.append(dict(case=case,cap=cap,rep=rep,both=int(target is not None),target_upper_J=target,
                         C1_s=t1,C2_s=t2,difference_s=t2-t1 if target else None,lower=win,
                         C2_meets_C1=meet(b,a[-1][1] if a else None),C1_meets_C2=meet(a,b[-1][1] if b else None)))
        fs=[r for r in flows if r["cap"]==cap]
        shared=[r for r in fs if min(r["C1_n"],r["C2_n"])>=2]
        for arm in ARMS:
            group=[r for r in cells if (r["cap"],r["arm"])==(cap,arm)]
            good=[r for r in group if r["J"]]
            reliable=[f for f in fs if f[arm+"_n"]>=2]
            summary=dict(cap=cap,arm=arm,success=len(good),reliable=len(reliable),all_three=sum(f[arm+"_n"]==3 for f in fs),
              gap_pct=mean([f[arm+"_gap_pct"] for f in reliable]),shared_gap_pct=mean([f[arm+"_gap_pct"] for f in shared]),
              shared_J=mean([f[arm+"_J"] for f in shared]),first_s=median([float(r["first_s"]) for r in good]),
              last_s=median([float(r["last_s"]) for r in good]),peak_rss_MiB=max(float(r["rss_KiB"])/1024 for r in group),
              cache_peak_MiB=max(float(r["cache_bytes"])/1048576 for r in group),
              dp_improved=sum(float(r["seed_J"])-float(r["J"])>1e-7 for r in good))
            for k in ("certs","hot","hot_started","events","reused","slots","predictions","integrate","identity","checkpoint","cert_s","cpu_s","charged"):
                summary[k]=sum(float(r[k]) for r in group)
            summary["reuse_pct"]=100*summary["reused"]/summary["events"] if summary["events"] else 0
            summaries.append(summary)
        paired=[r for r in pairs if r["cap"]==cap and r["both"]]
        differences=[r["difference_s"] for r in paired]
        wins=Counter(r["lower"] for r in paired)
        byflow=[median([r["difference_s"] for r in paired if r["case"]==k]) for k in cases]
        paired_summary.append(dict(cap=cap,shared_flows=len(shared),both=len(paired),faster=sum(d<0 for d in differences),
               t1=median([r["C1_s"] for r in paired]),t2=median([r["C2_s"] for r in paired]),
               median_delta=median(differences),flow_time_improves=sum(d is not None and d<0 for d in byflow),
               flow_time_observed=sum(d is not None for d in byflow),
               relative_energy_pct=mean([(r["C2_J"]/r["C1_J"]-1)*100 for r in shared]),
               lower_C2=wins["C2"],lower_C1=wins["C1"],overlap=wins["overlap"],
               C2_meets_C1=sum(r["C2_meets_C1"] is not None for r in paired),
               C1_meets_C2=sum(r["C1_meets_C2"] is not None for r in paired)))
    write("flows",flows)
    write("targets",pairs)
    write("comparison",paired_summary)
    write("arms",summaries)
    write("reference_targets",quality_checks)
    split=[]
    for arm in ARMS:
        for stage in ("search","refine"):
            g=[r for r in phases if r["arm"]==arm and r["stage"]==stage]
            split.append(dict(arm=arm,stage=stage,workers=len(g),**{k:sum(float(r[k]) for r in g) for k in
                 ("delivered","integrals","events","reused","integrate","identity","checkpoint","cert_s")}))
    write("stage_totals",split)
    print(json.dumps(dict(arms=summaries,pairs=paired_summary)))


if __name__=="__main__":
    main()
