"""Reduce new certificates and historical Kim logs without evaluator calls."""
from collections import Counter
import csv
import gzip
import json
from pathlib import Path
import tarfile
from time import perf_counter
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
CFG=json.loads((HERE/"config.json").read_bytes())
CASES=json.loads((HERE/"inputs/cases.json").read_bytes())
HISTORY=ROOT/"research/ch3_algorithm_selection"

def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def lines(p):return [json.loads(x) for x in gzip.decompress(p.read_bytes()).splitlines() if x] if p.exists() else []
def csv_out(name,rows):
    if not rows:return
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (HERE/name).open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fields,lineterminator="\n");w.writeheader()
        for r in rows:w.writerow({k:json.dumps(v,ensure_ascii=False,separators=(",",":")) if isinstance(v,(dict,list,tuple)) else v for k,v in r.items()})

def inversions(rows):
    count=0;worst=None
    for i,a in enumerate(rows):
        for b in rows[i+1:]:
            dp=a["proxy_j"]-b["proxy_j"];de=a["continuous_j"]-b["continuous_j"]
            if dp*de<0 and abs(dp)>1e-9 and abs(de)>1e-7:
                count+=1
                if worst is None or abs(de)>worst["energy_difference_j"]:worst=dict(a=a,b=b,energy_difference_j=abs(de))
    return count,worst

def historical(case,seed):
    with tarfile.open(HISTORY/"archives"/(case["case_id"]+".tar")) as tar:
        prefix=f"kim_anytime_{seed}/"
        trace=[json.loads(x) for x in gzip.decompress(tar.extractfile(prefix+"events.jsonl.gz").read()).splitlines()]
        raw=json.loads(gzip.decompress(tar.extractfile(prefix+"result.json.gz").read()))
    ranked=next(p for _,k,p in trace if k=="kim_ranked")
    mapping={r[0]:dict(dep=r[0],indices=r[1],scores=r[2],proxy_j=r[3]) for r in ranked}
    visited={p[0] for _,k,p in trace if k=="scene_proxy"}
    checked={p[1][0]:dict(indices=p[1][1:],**p[2]) for _,k,p in trace if k=="kim_check"}
    safe=[]
    for dep,r in checked.items():
        assert dep in mapping and mapping[dep]["indices"]==r["indices"]
        if r["status"]=="SAFE":safe.append(dict(**mapping[dep],continuous_j=r["energy_j"]))
    n,worst=inversions(safe)
    min_actual=min(safe,key=lambda r:r["continuous_j"])
    assert abs(min_actual["continuous_j"]-raw["result"]["energy_j"])<=1e-7
    # This is an order diagnostic, NOT a replay of vector-valued Lexicase selection.
    first_proxy=min(safe,key=lambda r:r["proxy_j"])
    report=dict(case_id=case["case_id"],seed=seed,is_baseline_seed=seed==case["seed"],
        visited=len(visited),ranked=len(mapping),checked=len(checked),safe=len(safe),
        full_valid_pool_checked=set(mapping)==set(checked),ranking_inversions=n,largest_reversal=worst,
        original_winner_j=raw["result"]["energy_j"],first_safe_by_proxy_j=first_proxy["continuous_j"],
        best_checked_safe_j=min_actual["continuous_j"],
        proxy_first_minus_best_j=first_proxy["continuous_j"]-min_actual["continuous_j"],
        attribution="association only; proxy sum orders certification, Lexicase uses scene vectors")
    return report,visited,mapping,checked

def phase_data(case,phase):
    folder=HERE/"raw"/case/phase;receipt=read(folder/"receipt.json")
    trace=lines(folder/"events.jsonl.gz")
    result=read(folder/"result.json") if (folder/"result.json").exists() else {}
    completed=[r["data"] for r in trace if r["kind"]=="candidate_complete" and r["t_s"]<=CFG["cap_s"]]
    witnesses=[r["data"] for r in trace if r["kind"]=="safe_witness" and r["data"]["accepted"] and r["data"]["t_s"]<=CFG["cap_s"]]
    best=min(witnesses,key=lambda r:r["energy_j"]) if witnesses else None
    return folder,receipt,result,trace,completed,witnesses,best

def main():
    summary=[];candidates=[];history=[];policies=[];phases=[];attribution=[];probe_order=[];new_proxy_policies=[]
    for case in CASES:
        analysis_started=perf_counter()
        target=case["energy_j"];best=None;fixed=None;phase_times={};complete_counts={}
        old={}
        for seed in [20261121,20261122,20261123]:
            h,v,m,c=historical(case,seed);history.append(h);old[seed]=(v,m,c)
        for phase in CFG["phases"]:
            folder,receipt,raw,trace,rows,witnesses,phasebest=phase_data(case["case_id"],phase)
            for event in trace:
                if event["kind"]=="setfreq" and event["data"]["status"]=="SAFE":
                    sf=event["data"]
                    new_proxy_policies.append(dict(case_id=case["case_id"],phase=phase,dep=sf["dep"],
                        indices=sf["indices"],proxy_j=sf["proxy_j"],continuous_j=sf["continuous_j"]))
            complete_counts[phase]=len(rows);phase_times[phase]=receipt["total_wall_s"]
            if phasebest and (best is None or phasebest["energy_j"]<best["energy_j"]):best=dict(**phasebest,phase=phase)
            phases.append(dict(case_id=case["case_id"],phase=phase,status=receipt["status"],reason=raw.get("reason"),
                planned=1 if phase=="fixed_frequency" else 48,completed=len(rows),
                exact_certificates=sum(r["certificate"] for r in rows),search_end_s=raw.get("search_end_s"),
                total_wall_s=receipt["total_wall_s"],first_safe_s=min((r["t_s"] for r in witnesses),default=None),
                best_safe_j=phasebest["energy_j"] if phasebest else None,
                **{"time_"+k:v for k,v in raw.get("timings_s",{}).items()},**{"count_"+k:v for k,v in raw.get("counters",{}).items()}))
            if phase=="fixed_frequency" and rows:fixed=rows[0]
            for row in rows:
                b=row["best"];sf=row["setfreq"]
                c=dict(case_id=case["case_id"],phase=phase,dep=row["dep"],group=row["group"],certificate=row["certificate"],
                    no_safe=row["no_safe"],best_safe_j=b["energy_j"] if b else None,
                    saving_vs_best_kim_pct=100*(target-b["energy_j"])/target if b else None,
                    optimal_indices=b["indices"] if b else None,peak_upper_c=b["peak_upper_c"] if b else None,
                    slack_ms=b["slack_ms"] if b else None,e0_j=row["energy_lower_bound_j"],e0_status=row["e0_status"],
                    deadline_sequences=row["deadline_sequences"],safe_sequences=row["safe_sequences"],unresolved=row["unresolved"],
                    setfreq_indices=sf["indices"],setfreq_proxy_j=sf["proxy_j"],setfreq_status=sf["status"],setfreq_continuous_j=sf["continuous_j"],
                    setfreq_loss_j=sf["continuous_j"]-b["energy_j"] if b and sf["status"]=="SAFE" else None,
                    elapsed_s=row["elapsed_s"],begin_s=row["begin_s"],end_s=row["end_s"],arrays=row["arrays"])
                candidates.append(c)
            for w in witnesses:
                policies.append(dict(case_id=case["case_id"],phase=phase,**w,saving_vs_best_kim_pct=100*(target-w["energy_j"])/target))
                if w["energy_j"]<target-1e-7:
                    for seed,(visited,mapping,checked) in old.items():
                        dep=w["dep"];prior=checked.get(dep)
                        attribution.append(dict(case_id=case["case_id"],historical_seed=seed,is_baseline_seed=seed==case["seed"],
                            witness=w,visited=dep in visited,ranked=dep in mapping,certified=dep in checked,
                            historical_setfreq=mapping.get(dep),historical_check=prior,
                            same_frequency=prior["indices"]==w["indices"] if prior else None,
                            conclusion="counterfactual genetic causation not established by this diagnostic"))
        assert best is not None
        fixed_j=fixed["best"]["energy_j"] if fixed and fixed["certificate"] and fixed["best"] else None
        summary.append(dict(case_id=case["case_id"],load=case["load"],ambient_c=case["ambient_c"],kim_seed=case["seed"],
            kim_deployment=case["dep"],kim_energy_j=target,kim_indices=case["indices"],historical_kim_wall_s=case["wall_s"],
            fixed_deployment_optimum_j=fixed_j,fixed_certificate=bool(fixed and fixed["certificate"]),
            fixed_saving_pct=100*(target-fixed_j)/target if fixed_j is not None else None,
            best_this_round_j=best["energy_j"],saving_vs_best_kim_pct=100*(target-best["energy_j"])/target,
            best_deployment=best["dep"],best_indices=best["indices"],best_phase=best["phase"],best_proof=best["proof"],
            completed_probe_deployments=complete_counts["deployment_probe"],planned_probe_deployments=48,
            fixed_wall_s=phase_times["fixed_frequency"],probe_wall_s=phase_times["deployment_probe"],
            total_new_wall_s=sum(phase_times.values()),global_optimum_certified=False))
        pairs=[r for r in new_proxy_policies if r["case_id"]==case["case_id"]]
        n,worst=inversions(pairs)
        probe_order.append(dict(case_id=case["case_id"],observed_safe_policies=len(pairs),ranking_inversions=n,
            largest_reversal=worst,offline_analysis_s=perf_counter()-analysis_started))
    result=dict(cases=summary,phases=phases,candidates=candidates,historical_proxy=history,new_proxy=probe_order,
                improving_witness_attribution=attribution,policies=policies,new_proxy_policies=new_proxy_policies)
    (HERE/"summary.json").write_bytes((json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode())
    for name,rows in [("comparison.csv",summary),("phase_costs.csv",phases),("candidate_results.csv",candidates),
                     ("historical_proxy.csv",history),("new_proxy.csv",probe_order),("safe_witnesses.csv",policies),
                     ("new_proxy_policies.csv",new_proxy_policies),
                     ("improvement_attribution.csv",attribution)]:csv_out(name,rows)
    # Empty attribution has an explicit status, never an omitted negative result.
    (HERE/"attribution.json").write_bytes((json.dumps(dict(new_improving_witnesses=len(attribution),records=attribution,
        caveat="No causal claim about candidate generation from ranking reversal alone."),indent=2)+"\n").encode())
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
