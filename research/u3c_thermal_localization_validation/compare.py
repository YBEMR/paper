"""Generate paired flow-level contrasts. Timing repeats stay nested within a flow."""
import csv
import json
from itertools import combinations
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent
T=HERE/"tables"
METHODS=["previous","peak","energy","slack","heat"]

def read_table(name):
    with (T/(name+".csv")).open(encoding="utf8",newline="") as f:
        return list(csv.DictReader(f))

def write_table(name,fields,rows):
    with (T/(name+".csv")).open("w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

def main():
    flows=read_table("flows")
    routes=read_table("routes")
    rows=[r for r in routes if r["case"]!="C10" and r["method"]!="terminal"]
    cases=[r["case"] for r in flows if r["triggered"]=="True"]
    projected={r["case"]:r for r in read_table("offline_windows")}
    primary={(r["case"],r["method"]):r for r in rows if r["repeat"]=="1"}
    paired=[]; costs=[]; counts=[]
    for m in METHODS:
        wins=[]; losses=[]; ties=0; both_located=0; common=0; shared=0
        for tag in cases:
            a,b=primary[tag,"heat"],primary[tag,m]
            sa=a["status"]=="SAFE"; sb=b["status"]=="SAFE"
            if sa and not sb: wins.append(tag)
            if sb and not sa: losses.append(tag)
            if a["selected_w"] and a["selected_w"]==b["selected_w"]: ties+=1
            both_located+=int(bool(a["selected_w"] and b["selected_w"]))
            if sa and sb:
                common+=1
                shared+=int(a["safe_plan"]==b["safe_plan"])
            paired.append(dict(case=tag,comparison=m,online_heat_window=a["selected_w"],online_other_window=b["selected_w"],
                   projected_heat_window=projected[tag]["heat"],projected_other_window=projected[tag][m],
                   heat_status=a["status"],other_status=b["status"],both_SAFE=sa and sb,
                   same_SAFE_plan=a["safe_plan"]==b["safe_plan"] if sa and sb else None,
                   heat_J=a["J"],other_J=b["J"],heat_T_hi=a["T_hi"],other_T_hi=b["T_hi"]))
            rep=[r for r in rows if r["case"]==tag and r["method"]==m]
            deliveries=[float(r["first_SAFE_delivery_s"]) for r in rep if r["first_SAFE_delivery_s"]]
            costs.append(dict(case=tag,method=m,repeats=len(rep),SAFE_deliveries=len(deliveries),
                 first_status=b["status"],window=b["selected_w"],same_status=len({r["status"] for r in rep})==1,
                 different_SAFE_plans=len({r["safe_plan"] for r in rep if r["safe_plan"]}),
                 first_replays=b["replays"],first_terminal=b["terminal"],first_local=b["local"],
                 median_SAFE_delivery_s=median(deliveries) if len(deliveries)==3 else None,
                 min_SAFE_s=min(deliveries) if deliveries else None,max_SAFE_s=max(deliveries) if deliveries else None))
        selected=[primary[c,m] for c in cases]
        counts.append(dict(method=m,triggered=len(cases),rescued=sum(r["status"]=="SAFE" for r in selected),
               total_covered=sum(r["screen"]=="SAFE" for r in flows)+sum(r["status"]=="SAFE" for r in selected),
               projected_same_window_as_heat=sum(projected[t]["heat"]==projected[t][m] for t in cases),
               both_located_online=both_located,online_same_window_as_heat=ties,heat_only=len(wins),comparator_only=len(losses),
               both_SAFE=common,same_SAFE_plan=shared,
               first_terminal=sum(int(r["terminal"]) for r in selected),
               first_local=sum(int(r["local"]) for r in selected),
               first_replays_lower_bound=sum(int(r["replays"] or 0) for r in selected),
               wall=sum(r["status"]=="WALL" for r in selected)))
    write_table("paired",list(paired[0]) if paired else ["case","comparison"],paired)
    write_table("repeat_costs",list(costs[0]) if costs else ["case","method"],costs)
    write_table("methods",list(counts[0]),counts)
    print(counts)

if __name__=="__main__":
    main()
