"""Summarize only same-case, same-81-domain comparisons and preserve seed spread."""
from pathlib import Path
import json
import statistics
import gzip
from analyze import HERE,ROOT,P,csv_rows,write_csv,check

rows=csv_rows(HERE/"run_results.csv")
check(len(rows)==12,"all twelve preregistered runs are required")
catalog=json.loads((ROOT/"research/kim_multidnn_expansion/catalog.json").read_bytes())
summary=[]
mappings=[]
diagnostics=[]
for case in P["cases"]:
    runs=[r for r in rows if r["case"]==case]
    m=next(r for r in runs if r["method"]=="M2")
    kim=[r for r in runs if r["method"]=="Kim-Adapt+SAFE"]
    check(len(kim)==5 and {int(r["seed"]) for r in kim}==set(P["seeds"]),"seed coverage")
    safe=[r for r in kim if r.get("safe_j")]
    optimal=m["status"]=="OPTIMAL"
    ref=float(m["safe_j"]) if m["safe_j"] else None
    for k in kim:
        if optimal and k.get("safe_j"):
            energy=float(k["safe_j"])
            k["gap_vs_exact_pct"]=100*(energy-ref)/ref
            k["saving_of_exact_vs_kim_pct"]=100*(energy-ref)/energy
    values=[float(r["safe_j"]) for r in safe]
    summary.append(dict(case=case,domain=81,m2_status=m["status"],m2_safe_j=ref,
        m2_deployment=m.get("deployment"),m2_peak_upper_c=m.get("peak_upper_c"),
        m2_slack_ms=m.get("slack_ms"),m2_first_safe_s=m.get("first_safe_s"),
        m2_best_safe_first_s=m.get("best_safe_first_s"),m2_certificate_s=m.get("certificate_s"),
        m2_wall_s=m["wall_s"],m2_energy_coverage=m["energy_coverage"],m2_thermal_coverage=m["thermal_coverage"],
        kim_safe_runs=len(safe),kim_runs=5,kim_min_j=min(values) if values else None,
        kim_mean_j=statistics.mean(values) if values else None,kim_max_j=max(values) if values else None,
        kim_mean_gap_pct=statistics.mean(float(r["gap_vs_exact_pct"]) for r in safe) if values and optimal else None,
        exact_saving_vs_kim_mean_pct=100*(statistics.mean(values)-ref)/statistics.mean(values)
            if values and optimal else None,
        observed_safe_saving_pct=100*(statistics.mean(values)-ref)/statistics.mean(values) if values and ref else None,
        kim_check_counts="/".join(r["total_checks"] for r in kim),
        kim_deployments="/".join(r.get("deployment","") for r in kim),
        kim_wall_median_s=statistics.median(float(r["wall_s"]) for r in kim),
        kim_peak_upper_min_c=min(float(r["peak_upper_c"]) for r in safe) if safe else None,
        kim_peak_upper_max_c=max(float(r["peak_upper_c"]) for r in safe) if safe else None))
    for k in kim:
        folder=HERE/"raw"/k["unit"]
        events=[json.loads(s) for s in gzip.open(folder/"events.jsonl.gz","rt")]
        pool=next((e["data"]["pool"] for e in events if e["event"]=="kim_pool"),[])
        target=m.get("deployment")
        ranked=next(((i+1,c) for i,c in enumerate(pool) if c[0]==target),None)
        diagnostics.append(dict(case=case,seed=k["seed"],reference_deployment=target,
            reference_status=m["status"],reference_opps=m.get("opps"),found_in_kim_pool=bool(ranked),
            proxy_rank=ranked[0] if ranked else None,proxy_opps=ranked[1][1] if ranked else None,
            kim_checks=k["total_checks"],kim_winner=k.get("deployment"),
            reference_deployment_certified=any(e["event"]=="kim_check" and e["data"]["dep"]==target for e in events)))
    for dep in sorted({r["deployment"] for r in runs if r.get("deployment")}):
        for app,stages in catalog["deployments"][dep]["stages"].items():
            mappings.append(dict(case=case,deployment=dep,app=int(app),stages=json.dumps(stages)))
write_csv("run_results.csv",rows)
write_csv("comparison.csv",summary)
write_csv("selected_mappings.csv",mappings)
write_csv("pool_diagnostics.csv",diagnostics)
print(json.dumps(summary,indent=2))
