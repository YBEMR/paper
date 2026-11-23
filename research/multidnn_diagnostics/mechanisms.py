"""Within-case deployment regret and mechanism evidence from existing certificates."""
from pathlib import Path
from math import isfinite
import json
from analyze import read,load_events,table,dump,HERE,REVIEW,TOL


def main():
    summary=read(HERE/"summary.json")
    domain=read(REVIEW/"inputs/domain81.json")
    winners=sorted({r["best_safe_deployment"] for r in summary if r["best_safe_deployment"]})
    components,transfers,sets=[],[],[]
    for row in summary:
        events,_=load_events(HERE/"raw"/row["case_id"])
        physical={(e["data"]["deployment"],tuple(e["data"]["opps"])):e["data"]
                  for e in events if e["kind"]=="physical_certificate"}
        energy={e["data"]["deployment"]:e["data"] for e in events
                if e["kind"]=="deployment" and e["data"]["phase"]=="energy"}
        thermal={e["data"]["deployment"]:e["data"] for e in events
                 if e["kind"]=="deployment" and e["data"]["phase"]=="fallback"}
        local={}
        for dep in domain["search_order"]:
            a,b=energy.get(dep),thermal.get(dep)
            value,status=None,"UNRESOLVED"
            if a and not a["legal"]:
                status="PROVEN_DEADLINE_INFEASIBLE"
            elif a and a["choice"]:
                p=physical[dep,tuple(a["choice"]["opps"])]["physical"]
                if p["feasible"]:
                    value,status=p["energy_j"],"PROVEN_LOCAL_SAFE_MIN"
            if b and not b["unresolved"]:
                if b["safe"]:
                    p=physical[dep,tuple(b["choice"]["opps"])]["physical"]
                    value,status=p["energy_j"],"PROVEN_LOCAL_SAFE_MIN"
                elif a and a["legal"]:
                    value,status=None,"PROVEN_THERMAL_INFEASIBLE"
            local[dep]=(value,status)
        optimum_set=[d for d,(v,s) in local.items() if v is not None and row["best_safe_j"] is not None
                     and abs(v-row["best_safe_j"])<=TOL]
        sets.append(dict(case_id=row["case_id"],optimality_proven=row["safe_optimum_proven"],
                         equivalent_within_j=TOL,deployment_ids=optimum_set,
                         local_deployments_unresolved=sum(s=="UNRESOLVED" for v,s in local.values()),
                         possibly_optimal_unresolved=[d for d,(v,s) in local.items() if s=="UNRESOLVED" and
                             (d not in energy or energy[d]["strict_min_j"] is None or
                              row["best_safe_j"] is None or energy[d]["strict_min_j"]<=row["best_safe_j"]+TOL)]))
        for dep in winners:
            value,status=local[dep]
            transfers.append(dict(case_id=row["case_id"],deployment=dep,status=status,
                   within_case_safe_min_j=value,
                   within_case_regret_pct=100*(value-row["best_safe_j"])/row["best_safe_j"]
                   if value is not None and row["safe_optimum_proven"] else None))
        for role,dep in (("E0",row["e0_deployment"]),("SAFE",row["best_safe_deployment"])):
            if dep is None:
                continue
            if role=="E0":
                choice=energy[dep]["choice"]
                cert=physical[dep,tuple(choice["opps"])]
            else:
                cert=min((v for (d,o),v in physical.items() if d==dep and v["physical"]["feasible"]),
                         key=lambda v:v["physical"]["energy_j"])
                choice={"opps":cert["opps"]}
            p=cert["physical"]; c=cert["energy_components"]
            components.append(dict(case_id=row["case_id"],role=role,deployment=dep,
                 opps="/".join(choice["opps"]),energy_j=p["energy_j"],
                 board_j=sum(x["common_J"] for x in c),transfer_j=sum(x["transfer_J"] for x in c),
                 idle_j=sum(sum(x["idle_J"]) for x in c),
                 activity_j=sum(sum(x["activity_J"]) for x in c),
                 leakage_j=sum(sum(x["leakage_J"]) for x in c),
                 cpu_peak_c=p["peak_upper_c"][0],gpu_peak_c=p["peak_upper_c"][1],
                 dla0_peak_c=p["peak_upper_c"][2],dla1_peak_c=p["peak_upper_c"][3],
                 minimum_deadline_slack_ms=p["min_slack_ms"],thermal_status=p["thermal_status"],
                 per_network_candidates="/".join(domain["deployments"][dep]["per_app_candidate_ids"])))
    table("deployment_transfer.csv",transfers)
    table("energy_components.csv",components)
    dump(HERE/"optimal_deployment_sets.json",sets)
    dump(HERE/"winning_deployments.json",{d:domain["deployments"][d] for d in winners})


if __name__=="__main__":
    main()
