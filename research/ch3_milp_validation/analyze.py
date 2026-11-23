"""Offline evidence audit and cross-case tables. No physical evaluator or optimizer is run."""
from collections import Counter
from hashlib import sha256
import csv
import json
from math import prod
from pathlib import Path
import sys

import numpy as np

from execute import HERE, FROZEN, load_files, config_bytes

sys.path.insert(0,str(FROZEN))
from verify import check, read, readcsv, verify_certificate, verify_lower_bound

RESEARCH = HERE.parent
REG, ORIGINAL = load_files()
ORDER = ("N1","N2","N3","N4","P1","P2","P3","F19")


def write_csv(name, records):
    with (HERE/name).open("w",encoding="utf-8",newline="") as stream:
        writer = csv.DictWriter(stream,fieldnames=list(dict.fromkeys(k for r in records for k in r)),
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def infeasibility_cover(grid, coeff, valid_prefixes):
    """Disjoint coverage by missed deadlines, certified prefixes or analytic point violations."""
    count = Counter()
    for d, slots in grid.items():
        counts = [len(slot) for slot in slots]
        count["deadline"] += 27**4-prod(counts)
        def visit(j, seq, inlet):
            if (d,seq) in valid_prefixes:
                count["replayed_violation_prefix"] += prod(counts[j:])
                return
            if j==4:
                raise ValueError("uncovered feasible-frequency sequence")
            for f,i in slots[j].items():
                if max(coeff["peak"][i]+coeff["h"][i]@inlet)>80.+1e-6:
                    count["overtemp_witness"] += prod(counts[j+1:])
                else:
                    visit(j+1,seq+(int(f),),coeff["b"][i]+coeff["F"][i]@inlet)
        visit(0,(),np.zeros(4))
    check(sum(count.values())==len(grid)*27**4,"incomplete infeasibility proof")
    return count


def history(spec, label, m2, pressure):
    case = spec["id"]
    if label=="F19":
        path = RESEARCH/"kim_multidnn_expansion/raw/expanded/forward_alternating_25C/deployment_D019.json"
        row = read(path)
        check(row["safe"]==row["unresolved"]==0 and row["status"]=="COMPLETE"
              and row["overtemp"]==59049 and row["conditional_optimality_proven"],"D019 historical domain")
        return "fixed deployment full classification",None,row["overtemp"],None
    if spec["domain"]==81:
        row = next(r for r in m2 if r["method"]=="M2" and r["case"]==case and r["scope"]=="catalog")
        return "M2 whole catalog",float(row["best_safe_j"]),int(row["legal_codes"]),float(row["certificate_s"])
    group = [r for r in pressure if r["case_id"]==case]
    check({r["deployment"] for r in group}==set(spec["deployments"]) and
          all(sum(r["counts"].values())==27**4 and not r["counts"]["unresolved"] for r in group),
          "historical four-deployment complete classification")
    return ("four exact classifications",min(r["physical"]["energy_j"] for r in group if r["safe_witness"]),
            sum(r["counts"]["safe"]+r["counts"]["overtemp"] for r in group),None)


def iteration_rows(label, events):
    result = []
    ub = lb = None
    round_id = 0
    for e in events:
        name = e["event"]
        if name not in {"model","solve","cut","certificate","finish"}:
            continue
        if name=="model":
            round_id += 1
            lb = max(e["interval_lb"],lb if lb is not None else -np.inf)
        if name=="solve" and e["valid_lb_j"] is not None:
            lb=e["valid_lb_j"]
        if name=="certificate" and e["status"]=="SAFE":
            ub=min(ub if ub is not None else np.inf,e["energy_j"])
        status = e.get("status")
        if name=="solve" and status==2:
            lb=None  # Infeasible relaxation: no finite energy bound to plot.
        result.append(dict(label=label,iteration=round_id,event=name,wall_s=e["time_s"],
            lower_j=lb,safe_upper_j=ub,candidate_j=e.get("energy_j",e.get("objective")),
            status=status,deployment=e.get("deployment"),opp_indices=e.get("opp",e.get("prefix")),
            peak_lower_c=e.get("peak_lower_c"),peak_upper_c=e.get("peak_upper_c"),
            matrix_rows=e.get("rows"),witness_bank=e.get("witnesses"),prefix_cuts=e.get("prefix_cuts"),
            nodes=e.get("nodes"),dual_j=e.get("dual_j")))
    return result


def main():
    catalog=read(RESEARCH/"kim_multidnn_expansion/catalog.json")
    inputs=readcsv(RESEARCH/"ch3_final_experiments/derived/instances.csv")
    m2=readcsv(RESEARCH/"kim_multidnn_search_trial/results/run_metrics.csv")
    pressure=read(RESEARCH/"kim_pressure_feasibility/raw_execution/summary.json")
    kim=readcsv(RESEARCH/"ch3_final_experiments/formal/tables/run_results.csv")
    rows, iterations, audit = [],[],{}
    for label in ORDER:
        reused = REG["reuse"].get(label)
        spec = ORIGINAL["cases"][reused] if reused else REG["cases"][label]
        folder = FROZEN/"raw"/reused if reused else HERE/"raw"/label
        receipt=read(folder/"receipt.json")
        config = (FROZEN/"protocol.json").read_bytes() if reused else config_bytes(REG,ORIGINAL,label)
        check(receipt["config_sha256"]==sha256(config).hexdigest() and receipt["budget_s"]==120,"receipt")
        expected_commit = ("54ee4d29ab1f7f4ee84c123a5cfa3bd47589df8e" if reused
                           else "8a7bc4c4e71c41519bfedb591589502e8a1a6d3d")
        check(receipt["execution_commit"]==expected_commit,"execution commit")
        events=[json.loads(s) for s in (folder/"events.jsonl").read_text().splitlines()]
        iterations.extend(iteration_rows(label,events))
        method,reference,histlegal,histtime=history(spec,label,m2,pressure)
        row=dict(label=label,case=spec["id"],domain=spec["domain"],reused=bool(reused),
                 wall_s=receipt["wall_s"],exact_source=method,exact_j=reference,historical_proof_s=histtime,
                 historical_deadline_legal=histlegal)
        rows.append(row)
        if receipt["killed"] or receipt["exit_code"] or not (folder/"result.json").exists():
            row["outcome"]="timeout" if receipt["killed"] else "worker_error"
            audit[label]=dict(verified=False,receipt=receipt)
            continue
        r=read(folder/"result.json")
        grid=read(folder/"grid.json")
        k=dict(np.load(folder/"kernels.npz",allow_pickle=False))
        inst=next(i for i in inputs if i["instance_id"]==spec["id"])
        order=inst["scene_order"].split("/")
        frames=list(map(int,inst["frames_execution_order"].split("/")))
        inp=next(e for e in events if e["event"]=="input")
        deps=spec["deployments"] or catalog["search_order"]
        check(list(grid)==inp["cases"]==deps and r["finished_deployments"]==len(deps)==spec["domain"],
              "original domain")
        check(inp["request_sha256"]==spec["request_sha256"]==inst["request_sha"] and
              inp["window_ns"]==10040000000 and len(inp["opps"])==27 and
              (bool(reused) or inp["frames"]==frames),"frozen inputs")
        check(inp["catalog_sha256"]==sha256((RESEARCH/"kim_multidnn_expansion/catalog.json").read_bytes()).hexdigest(),
              "catalog digest")
        bound_cuts=set()
        verified_certs=[]
        for c in r["certificates"]:
            e=read(folder/c["file"])
            check(e["stages"]==catalog["deployments"][e["dep"]]["stages"],"fixed binding")
            verify_certificate(e,grid,k,c,spec,order,frames)
            p=e["physical"]
            check(c["peak_upper_c"]==max(p["peak_upper_c"]) and c["peak_lower_c"]==max(p["peak_lower_c"])
                  and c["slack_ms"]==p["min_slack_ms"] and e["ambient_c"]==float(inst["ambient_c"]),
                  "summary extrema, slack and ambient")
            verified_certs.append((c,e))
        for d,prefix in r["cuts"]:
            check(any(c["deployment"]==d and c["opp"][:len(prefix)]==prefix and c["status"]=="VIOLATION"
                      and any(max(s["peak_lower_c"])>80 for s in e["physical"]["scene_rows"][:len(prefix)])
                      for c,e in verified_certs),"uncertified prefix")
            bound_cuts.add((d,tuple(prefix)))
        legal=sum(prod(len(s) for s in slots) for slots in grid.values())
        check(legal==histlegal and receipt["wall_s"]<=120,"deadline-feasible count and budget")
        best=r["best"]
        calls=r["solves"]
        selected=[i for i in kim if i["method"]=="Kim-Adapt+SAFE" and i["case"]==spec["id"]
                  and i["domain"]==str(spec["domain"]) and i["request_sha256"]==spec["request_sha256"]]
        safe_k=[float(i["safe_energy_j"]) for i in selected if i["outcome"]=="SAFE"]
        raw_status=r["status"]
        coverage=None
        outcome=raw_status
        proven_s=r["certificate_s"]
        if raw_status=="optimal_within_tolerance":
            check(best["status"]=="SAFE" and abs(best["energy_j"]-reference)<=1e-7 and
                  -1e-10<=best["energy_j"]-r["lower_bound_j"]<=1e-7,"optimality tolerance")
            coverage=verify_lower_bound(grid,k,r["lower_bound_j"])
        elif (not best and calls and calls[-1]["status"]==2 and calls[-1]["size"]["certified_cost_fixings"]==0):
            coverage=infeasibility_cover(grid,k,bound_cuts)
            check(reference is None,"infeasibility differs from historical optimum")
            outcome="infeasible_verified"
            proven_s=next(e["time_s"] for e in events if e["event"]=="solve" and e["status"]==2)
        sol_certs=[c for c,e in verified_certs if c["origin"]=="MILP"]
        lb=r["lower_bound_j"] if outcome!="infeasible_verified" else None
        row.update(outcome=outcome,worker_status=raw_status,first_safe_s=r["first_safe_s"],
                   best_safe_first_s=best["time_s"] if best else None,proof_or_infeasible_signal_s=proven_s,
                   safe_j=best["energy_j"] if best else None,lb_j=lb,
                   gap_j=best["energy_j"]-lb if best and lb is not None else None,
                   deploy=best["deployment"] if best else None,
                   opp="/".join(inp["opps"][f] for f in best["opp"]) if best else None,
                   peak_upper_c=best["peak_upper_c"] if best else None,slack_ms=best["slack_ms"] if best else None,
                   kim_safe_n=len(safe_k),kim_runs=len(selected),kim_safe_mean_j=np.mean(safe_k) if safe_k else None,
                   solves=len(calls),feedback=len(bound_cuts),physical_certificates=len(verified_certs),
                   integer_nodes=sum(s["nodes"] or 0 for s in calls),rows_initial=calls[0]["size"]["rows"],
                   rows_final=calls[-1]["size"]["rows"],variables=calls[-1]["size"]["columns"],
                   fixings=calls[0]["size"]["certified_cost_fixings"],first_milp_j=sol_certs[0]["energy_j"] if sol_certs else None,
                   first_milp_peak_lower_c=sol_certs[0]["peak_lower_c"] if sol_certs else None,
                   first_milp_deploy=sol_certs[0]["deployment"] if sol_certs else None,
                   relaxed_j=calls[0]["objective"],**r["cost"],other_wall_s=receipt["wall_s"]-sum(r["cost"].values()))
        audit[label]=dict(outcome=outcome,coverage=coverage,frames=frames,scope_codes=len(deps)*27**4,
                          legal_codes=legal,physical_certificates=len(verified_certs),requests_per_certificate=500,
                          input_sha256=inp["request_sha256"],execution_commit=receipt["execution_commit"])
    write_csv("summary.csv",rows)
    write_csv("iterations.csv",iterations)
    (HERE/"verification.json").write_bytes((json.dumps(audit,indent=2)+"\n").encode())
    for row in rows:
        print(row["label"],row["outcome"],row.get("safe_j"),row.get("solves"),row.get("feedback"))


if __name__=="__main__":
    main()
