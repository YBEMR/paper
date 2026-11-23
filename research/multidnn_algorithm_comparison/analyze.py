"""Postprocess archived traces. This module is never imported by a search worker."""
import csv
import gzip
import json
from pathlib import Path
from statistics import median
from collections import Counter
from math import isfinite

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
CFG=json.loads((HERE/"protocol.json").read_bytes())

def read(p):
    return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def lines(p):
    with gzip.open(p,"rt",encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
def table(name,rows):
    if not rows: return
    (HERE/"tables").mkdir(exist_ok=True)
    with (HERE/"tables"/name).open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n")
        w.writeheader();w.writerows(rows)
def main():
    refs={r["case_id"]:r for r in read(ROOT/"research/multidnn_diagnostics/summary.json")}
    runs,progress,checkpoints,costs=[],[],[],[]
    for case in CFG["cases"]:
        optimum=refs[case]["best_safe_j"]
        for seed in CFG["seeds"]:
            for method in CFG["methods"]:
                folder=HERE/"raw"/case/f"{method}_{seed}"
                receipt=read(folder/"receipt.json")
                trace=lines(folder/"events.jsonl.gz")
                result=read(folder/"result.json") if (folder/"result.json").exists() else None
                changes=[e for e in trace if e["kind"]=="incumbent" and e["data"]["accepted"] and e["t_s"]<=CFG["cap_s"]]
                best=min(changes,key=lambda e:e["data"]["energy_j"]) if changes else None
                e=best["data"]["energy_j"] if best else None
                proof=read(folder/best["data"]["proof"]) if best else None
                p=proof["physical"] if proof else None
                def first(threshold):
                    return next((x["t_s"] for x in changes if x["data"]["energy_j"]<=threshold),None)
                winner=best["data"]["key"] if best else None
                summary=result["summary"] if result else {}
                row=dict(case_id=case,load=refs[case]["load"],order=refs[case]["order"],
                    thermal_start=refs[case]["thermal_start"],required=refs[case]["requests"],
                    method=method,seed=seed,core=receipt["core"],status=receipt["status"],
                    safe=bool(best),safe_energy_j=e,optimum_j=optimum,
                    gap_pct=100*(e-optimum)/optimum if e is not None else None,
                    matched_optimum=e is not None and e<=optimum+CFG["energy_tolerance_j"],
                    first_safe_s=changes[0]["t_s"] if changes else None,
                    best_safe_first_s=best["t_s"] if best else None,
                    time_to_optimum_s=first(optimum+CFG["energy_tolerance_j"]),
                    time_to_01pct_s=first(optimum*(1+CFG["common_quality_relative_gap"])),
                    search_end_s=result["search_end_s"] if result else None,
                    total_wall_s=receipt["total_wall_s"],deployment=winner[0] if winner else None,
                    opps="/".join(proof["opps"]) if proof else None,
                    peak_upper_c=max(p["peak_upper_c"]) if p else None,
                    thermal_margin_c=80-max(p["peak_upper_c"]) if p else None,
                    min_slack_ms=p["min_slack_ms"] if p else None,
                    completed=p["completed"] if p else None,
                    checked_policies=result["physics_counts"].get("unique_replays",0) if result else None,
                    last_unique_certificate_s=max((x["t_s"] for x in trace if x["kind"]=="physical"),default=None),
                    last_candidate_trial_s=max((x["t_s"] for x in trace if x["kind"] in ("candidate","kim_check")),default=None),
                    rounds=summary.get("rounds"),
                    completed_generations=summary.get("completed_generations"),
                    evaluated_mappings=summary.get("evaluated_mappings"),
                    stop=summary.get("reason",summary.get("stop")),
                    proof=best["data"]["proof"] if best else None)
                runs.append(row)
                for x in changes:
                    progress.append(dict(case_id=case,method=method,seed=seed,t_s=x["t_s"],
                       energy_j=x["data"]["energy_j"],gap_pct=100*(x["data"]["energy_j"]-optimum)/optimum,
                       deployment=x["data"]["key"][0],proof=x["data"]["proof"]))
                for t in CFG["checkpoints_s"]:
                    candidates=[x for x in changes if x["t_s"]<=t]
                    eb=min((x["data"]["energy_j"] for x in candidates),default=None)
                    checkpoints.append(dict(case_id=case,load=refs[case]["load"],method=method,seed=seed,
                         checkpoint_s=t,safe=eb is not None,safe_energy_j=eb,
                         gap_pct=100*(eb-optimum)/optimum if eb is not None else None,
                         optimum=eb is not None and eb<=optimum+CFG["energy_tolerance_j"],
                         quality_01pct=eb is not None and eb<=optimum*1.001))
                if result:
                    cnt=result["physics_counts"]; tim=result["timings_s"]
                    identity=next(x["data"] for x in trace if x["kind"]=="identity")
                    costs.append(dict(case_id=case,method=method,seed=seed,total_wall_s=receipt["total_wall_s"],
                         initialization_s=identity["initialization_s"],
                         setfreq_mapping_calls=cnt.get("setfreq_mapping_calls",0),
                         setfreq_mapping_inclusive_s=tim.get("setfreq_mapping_inclusive_s",0),
                         event_dispatches=cnt.get("event_dispatches",0),event_schedule_s=tim.get("event_schedule_s",0),
                         deadline_schedule_pass=cnt.get("deadline_schedule_pass",0),
                         deadline_schedule_fail=cnt.get("deadline_schedule_fail",0),
                         proxy_calls=cnt.get("proxy_calls",0),unique_scene_proxies=cnt.get("unique_scene_proxies",0),
                         proxy_inclusive_s=tim.get("proxy_inclusive_s",0),
                         thermal_evaluate_calls=cnt.get("thermal_evaluate_calls",0),
                         thermal_evaluate_s=tim.get("thermal_evaluate_s",0),
                         unique_continuous_replays=cnt.get("unique_replays",0),
                         continuous_replay_inclusive_s=tim.get("continuous_replay_inclusive_s",0),
                         evidence_s=tim.get("evidence_s",0),
                         safe_replays=cnt.get("SAFE",0),violation_replays=cnt.get("VIOLATION",0),
                         deadline_replays=cnt.get("DEADLINE",0),unresolved_replays=cnt.get("UNRESOLVED",0)))
    cases=[]
    for case in CFG["cases"]:
        for method in CFG["methods"]:
            group=[r for r in runs if r["case_id"]==case and r["method"]==method]
            good=[r for r in group if r["safe"]]
            def med(k):
                vals=[r[k] for r in good if r[k] is not None]
                return median(vals) if vals else None
            cases.append(dict(case_id=case,method=method,runs=len(group),safe=len(good),
                 optimum=sum(r["matched_optimum"] for r in group),
                 quality_01pct=sum(r["time_to_01pct_s"] is not None for r in group),
                 best_j=min((r["safe_energy_j"] for r in good),default=None),
                 worst_gap_pct=max((r["gap_pct"] for r in good),default=None),
                 median_gap_pct=med("gap_pct"),median_first_safe_s=med("first_safe_s"),
                 median_best_first_s=med("best_safe_first_s"),
                 median_time_to_optimum_s_conditional=med("time_to_optimum_s"),
                 median_time_to_01pct_s_conditional=med("time_to_01pct_s"),
                 median_end_s=median(r["total_wall_s"] for r in group),
                 deployments="/".join(sorted({r["deployment"] for r in good}))))
    pairs=[]
    for case in CFG["cases"]:
        for seed in CFG["seeds"]:
            k=next(r for r in runs if r["case_id"]==case and r["seed"]==seed and r["method"]=="kim_anytime_safe")
            e=next(r for r in runs if r["case_id"]==case and r["seed"]==seed and r["method"]=="energy_only")
            both=k["safe"] and e["safe"]
            pairs.append(dict(case_id=case,load=k["load"],seed=seed,both_safe=both,
                 kim_gap_pct=k["gap_pct"],energy_gap_pct=e["gap_pct"],
                 energy_saving_vs_kim_pct=100*(k["safe_energy_j"]-e["safe_energy_j"])/k["safe_energy_j"] if both else None,
                 kim_optimum_s=k["time_to_optimum_s"],energy_optimum_s=e["time_to_optimum_s"],
                 kim_01pct_s=k["time_to_01pct_s"],energy_01pct_s=e["time_to_01pct_s"],
                 energy_faster_01pct=(e["time_to_01pct_s"]<k["time_to_01pct_s"])
                  if e["time_to_01pct_s"] is not None and k["time_to_01pct_s"] is not None else None))
    for name,rows in [("runs.csv",runs),("safe_progress.csv",progress),("checkpoints.csv",checkpoints),
                      ("costs.csv",costs),("case_summary.csv",cases),("paired.csv",pairs)]:
        table(name,rows)
    (HERE/"summary.json").write_text(json.dumps(dict(runs=runs,cases=cases,pairs=pairs),indent=2,allow_nan=False)+"\n",encoding="utf-8",newline="\n")
    print("Runs:",len(runs),"SAFE:",sum(r["safe"] for r in runs))
    for load in ("all","concurrent","balanced","asymmetric"):
        for method in CFG["methods"]:
            g=[r for r in runs if r["method"]==method and (load=="all" or r["load"]==load)]
            vals=[r["time_to_01pct_s"] for r in g if r["time_to_01pct_s"] is not None]
            print(load,method,len(g),"opt",sum(r["matched_optimum"] for r in g),
                  "maxgap",max((r["gap_pct"] for r in g if r["safe"]),default=None),
                  "median01",median(vals) if vals else None,"attain",len(vals))
if __name__=="__main__":
    main()
