"""Offline reduction only: no evaluator, candidate generator or optimizer calls."""
import csv
import gzip
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
CFG=json.loads((HERE/"protocol.json").read_bytes())

def read(p):
    return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())

def lines(p):
    if not p.exists():return []
    return [json.loads(x) for x in gzip.decompress(p.read_bytes()).splitlines() if x]

def write_csv(name,rows):
    if not rows:return
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with (HERE/name).open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,keys,lineterminator="\n");w.writeheader()
        for row in rows:w.writerow({k:json.dumps(v,ensure_ascii=False,separators=(",",":")) if isinstance(v,(list,dict,tuple)) else v for k,v in row.items()})

def run_data(case,method,seed):
    folder=HERE/"raw"/case/f"{method}_{seed}"
    receipt=read(folder/"receipt.json")
    trace=lines(folder/"events.jsonl.gz")
    physics=lines(folder/"physical.jsonl.gz")
    raw=read(folder/"result.json") if (folder/"result.json").exists() else {}
    accepted=[dict(t_s=r["t_s"],**r["data"]) for r in trace if r["kind"]=="incumbent" and r["data"]["accepted"] and r["t_s"]<=CFG["cap_s"]]
    winner=min(accepted,key=lambda x:x["energy_j"]) if accepted else None
    proof=read(folder/winner["proof"]) if winner else None
    p=proof["physical"] if proof else {}
    identity=next(r["data"] for r in trace if r["kind"]=="identity")
    summary=raw.get("summary",{})
    certificates=[r for r in trace if r["kind"]=="certificate" and r["t_s"]<=CFG["cap_s"]]
    certificate=bool(certificates and summary.get("certificate"))
    e0key=summary.get("e0_key")
    e0physical=next((r["physical"] for r in physics if [r["dep"],*r["indices"]]==e0key),{})
    row=dict(case_id=case,method=method,seed=seed,domain=identity["domain_count"],required=identity["case"]["required"],
         status=receipt["status"],reason=summary.get("reason"),safe=winner is not None,
         energy_j=p.get("energy_j"),peak_upper_c=max(p["peak_upper_c"]) if p else None,
         slack_ms=p.get("min_slack_ms"),deployment=winner["key"][0] if winner else None,
         indices=winner["key"][1:] if winner else None,opps=proof["opps"] if proof else None,
         first_safe_s=accepted[0]["t_s"] if accepted else None,best_safe_first_s=winner["t_s"] if winner else None,
         search_end_s=raw.get("search_end_s"),total_wall_s=receipt["total_wall_s"],
         certificate=certificate,certificate_s=certificates[-1]["t_s"] if certificates else None,
         proven_no_safe=summary.get("proven_no_safe",False),energy_coverage=summary.get("coverage",{}).get("energy"),
         thermal_coverage=summary.get("coverage",{}).get("thermal"),e0_proven=summary.get("e0_proven",False),
         e0_j=summary.get("e0_j"),e0_status=e0physical.get("thermal_status"),
         e0_peak_lower_c=max(e0physical["peak_lower_c"]) if e0physical else None,
         e0_peak_upper_c=max(e0physical["peak_upper_c"]) if e0physical else None,
         lower_bound_j=summary.get("lower_bound_j"),evaluated_mappings=summary.get("evaluated_mappings"),
         checked=summary.get("checked"),completed_generations=summary.get("completed_generations"),
         initialization_s=identity["initialization_s"])
    for k,v in raw.get("counts",{}).items():row["count_"+k]=v
    for k,v in raw.get("timings_s",{}).items():row["time_"+k]=v
    return row,accepted,trace,physics

def main():
    rows=[];cases=[];mechanisms=[];progress=[];config=[];heat=[]
    for case in CFG["main_cases"]:
        ref,acc,trace,physical=run_data(case,"M2-reference",0)
        optimum=ref["energy_j"] if ref["certificate"] and ref["safe"] else None
        ref["certified_optimum_j"]=optimum;ref["gap_pct"]=0. if optimum is not None else None
        if ref["certificate"]:
            deployments=[r["data"] for r in trace if r["kind"]=="deployment"]
            heat.append(dict(case_id=case,e0_j=ref["e0_j"],e0_status=ref["e0_status"],
                 e0_peak_lower_c=ref["e0_peak_lower_c"],e0_peak_upper_c=ref["e0_peak_upper_c"],
                 optimum_safe_j=optimum,safe_peak_upper_c=ref["peak_upper_c"],safe_slack_ms=ref["slack_ms"],
                 deadline_deployments=sum(r["deadline_valid"]>0 for r in deployments if r["phase"]=="energy"),
                 deadline_sequences=sum(r["deadline_valid"] for r in deployments if r["phase"]=="energy"),
                 safe_deployments=sum(r["safe"]>0 for r in deployments if r["phase"]=="thermal"),
                 safe_sequences=sum(r["safe"] for r in deployments if r["phase"]=="thermal")))
        rows.append(ref)
        for a in acc:progress.append(dict(case_id=case,method="M2-reference",seed=0,t_s=a["t_s"],energy_j=a["energy_j"],key=a["key"]))
        kimrows=[]
        for seed in CFG["kim_seeds"]:
            row,accepted,trace,physics=run_data(case,"Kim-Anytime+SAFE",seed)
            row["certified_optimum_j"]=optimum
            row["gap_pct"]=100*(row["energy_j"]-optimum)/row["energy_j"] if optimum is not None and row["safe"] else None
            row["time_to_certified_optimum_s"]=next((a["t_s"] for a in accepted if optimum is not None and a["energy_j"]<=optimum+1e-7),None)
            row["time_to_0_1pct_s"]=next((a["t_s"] for a in accepted if optimum is not None and a["energy_j"]<=optimum*1.001+1e-7),None)
            rows.append(row);kimrows.append(row)
            for a in accepted:progress.append(dict(case_id=case,method=row["method"],seed=seed,t_s=a["t_s"],energy_j=a["energy_j"],key=a["key"]))
            mappings={r["data"]["dep"]:r["data"] for r in trace if r["kind"]=="setfreq_mapping"}
            checks=[r["data"][1] for r in trace if r["kind"]=="kim_check"]
            target=ref["deployment"] if optimum is not None else None
            mapping=mappings.get(target)
            proxy_physical=[]
            for record in physics:
                m=mappings.get(record["dep"]);p=record["physical"]
                if m and m["valid"]==len(record["indices"]) and m["indices"]==record["indices"] and p["thermal_status"]=="SAFE":
                    proxy_physical.append((sum(m["scores"]),p["energy_j"],record["dep"]))
            reversals=[]
            for i,a in enumerate(proxy_physical):
                for b in proxy_physical[i+1:]:
                    if (a[0]-b[0])*(a[1]-b[1])<0 and abs(a[0]-b[0])>1e-9 and abs(a[1]-b[1])>1e-7:
                        reversals.append(dict(a=a,b=b))
            mechanisms.append(dict(case_id=case,seed=seed,certified_optimum_j=optimum,gap_pct=row["gap_pct"],
                obtained_certified_optimum=abs(row["energy_j"]-optimum)<=1e-7 if optimum is not None and row["safe"] else None,
                reference_deployment=target,reference_indices=ref["indices"] if target else None,
                reference_deployment_visited=mapping is not None if target else None,
                reference_deployment_certified=any(c[0]==target for c in checks) if target else None,
                setfreq_indices_on_reference=mapping["indices"] if mapping else None,
                setfreq_matches_reference=mapping["indices"]==ref["indices"] if mapping else None,
                observed_safe_proxy_physical_pairs=len(proxy_physical),ranking_reversals=len(reversals),
                largest_reversal=max(reversals,key=lambda r:abs(r["a"][1]-r["b"][1])) if reversals else None))
        caseinput=read(HERE/"inputs/cases"/(case+".json"))
        safes=[r["energy_j"] for r in [ref,*kimrows] if r["safe"]]
        gaps=[r["gap_pct"] for r in kimrows if r["gap_pct"] is not None]
        cases.append(dict(case_id=case,models=caseinput["models"],required=caseinput["required"],counts=caseinput["counts"],
             domain=ref["domain"],scene_count=len(caseinput["switches"]),certified_optimum_j=optimum,
             reference_safe_j=ref["energy_j"],best_seen_safe_j=min(safes) if safes else None,
             lower_bound_j=ref["lower_bound_j"],certificate=ref["certificate"],e0_proven=ref["e0_proven"],e0_status=ref["e0_status"],
             energy_coverage=ref["energy_coverage"],thermal_coverage=ref["thermal_coverage"],
             kim_safe=sum(r["safe"] for r in kimrows),kim_runs=len(kimrows),
             kim_best_j=min((r["energy_j"] for r in kimrows if r["safe"]),default=None),
             kim_worst_j=max((r["energy_j"] for r in kimrows if r["safe"]),default=None),
             kim_gap_min_pct=min(gaps) if gaps else None,kim_gap_max_pct=max(gaps) if gaps else None))
        for method in CFG["methods"]:
            config.append(dict(case_id=case,method=method,domain=ref["domain"],required=caseinput["required"],
                 scenes=len(caseinput["switches"]),ambient_c=caseinput["ambient_c"],initial_c=caseinput["initial_c"],
                 population=CFG["population"] if method.startswith("Kim") else None,
                 generations=CFG["generations"] if method.startswith("Kim") else None,
                 seeds=CFG["kim_seeds"] if method.startswith("Kim") else [0],cap_s=120,admit_s=116,
                 generation_s=95 if method.startswith("Kim") else None,kernel_cache=4096 if method.startswith("M2") else None,
                 stop="generation limit + pool exhaustion or wall budget" if method.startswith("Kim") else "full-domain certificate or wall budget"))
    assert len(rows)==32
    result=dict(cases=cases,runs=rows,mechanisms=mechanisms,progress=progress,thermal_decisions=heat)
    (HERE/"summary.json").write_bytes((json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode())
    for name,values in [("run_results.csv",rows),("case_summary.csv",cases),("mechanism_evidence.csv",mechanisms),
                        ("safe_progress.csv",progress),("formal_experiment_config.csv",config),
                        ("thermal_decisions.csv",heat),("model_inventory.csv",read(HERE/"inputs/model_audit.json"))]:write_csv(name,values)
    print(json.dumps(cases,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
