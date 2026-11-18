"""Build the comparison from archived paths and candidate evaluations only."""
import csv
import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from statistics import mean


ROOT = Path(__file__).resolve().parent
METHODS = ("A", "B", "D")
TOL = 1e-8  # only for descriptive comparisons, in joules


def occurrences(case, method):
    """Align reordered paths by scene and occurrence within that scene."""
    count = Counter()
    choices = {}
    for scene, cfg in zip(case["sequence"], method["path"]):
        count[scene] += 1
        choices[(scene, count[scene])] = cfg
    return choices


def pair_changes(records, changing, fixed):
    groups = defaultdict(list)
    for record in records:
        case = record["case"]
        groups[tuple(case[k] for k in fixed)].append(record)
    rows = []
    for pair in groups.values():
        assert len(pair) == 2
        left, right = sorted(pair, key=lambda r: r["case"][changing])
        for m in METHODS:
            l, r = left["methods"][m], right["methods"][m]
            lp, rp = occurrences(left["case"], l), occurrences(right["case"], r)
            keys = sorted(lp.keys() & rp.keys())
            def last_key(case):
                end=case["sequence"][-1]
                return (end,case["sequence"].count(end))
            # The final segment sees a fixed tail. Exclude a change of role as
            # a possible explanation for an order-dependent B decision.
            left_last=last_key(left["case"])
            right_last=last_key(right["case"])
            same_role=[k for k in keys if (k==left_last)==(k==right_last)]
            success=l["feasible"] and r["feasible"]
            rows.append(dict(factor=changing, method=m, left=left["case"]["id"],
                             right=right["case"]["id"], both_feasible=success,
                             compared=len(keys), differences=sum(lp[k] != rp[k] for k in keys),
                             same_terminal_role_compared=len(same_role),
                             same_terminal_role_differences=sum(lp[k]!=rp[k] for k in same_role),
                             right_minus_left_J=r["energy_J"]-l["energy_J"] if success else None))
    return rows


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def ties(options, field):
    if not options:
        return set()
    value = min(opt[field] for opt in options)
    return {opt["cfg"] for opt in options if opt[field] <= value + TOL}


def diagnose(records):
    rows=[]
    for rec in records:
        case=rec["case"]
        for method, result in rec["methods"].items():
            for i, candidates in enumerate(result["diagnostic"]):
                options=[c for c in candidates if c["deadline_ok"]]
                safe=[c for c in options if c["safe"]]
                cheapest=ties(options,"energy_J")
                best_safe=ties(safe,"energy_J")
                nominal=ties(options,"nominal_energy_J")
                kim_nominal=ties(options,"kim_score_J")
                cfg=result["path"][i] if i<len(result["path"]) else None
                chosen=next((c for c in options if c["cfg"]==cfg),None)
                row=dict(id=case["id"], method=method, index=i+1, scene=case["sequence"][i], cfg=cfg,
                         deadline_legal=len(options), rejected_deadline=sum(c["reason"]=="DEADLINE" for c in candidates),
                         rejected_boundary=sum(c["reason"]=="BOUNDARY_UNFINISHED" for c in candidates),
                         over_temperature=len(options)-len(safe),
                         heat_excludes_all_unconstrained_best=bool(options) and not bool(cheapest & best_safe),
                         actual_vs_nominal_best_disjoint=bool(options) and not bool(cheapest & nominal),
                         tail_changes_nominal_best=bool(options) and not bool(kim_nominal & nominal),
                         search_omits_nominal_best=None if method!="A" or not cfg else cfg not in kim_nominal,
                         chosen_extra_current_J=None if not chosen or not safe else
                         chosen["energy_J"]-min(x["energy_J"] for x in safe))
                rows.append(row)
    return rows


def analyze(records):
    assert len(records) == len({r["case"]["id"] for r in records}) == 24
    totals = {m: dict(statuses=Counter(), feasible=0, elapsed_s=0., visits=0) for m in METHODS}
    paths = Counter()
    rows, common = [], []
    for rec in records:
        case = rec["case"]
        row = {k:case[k] for k in ("id","load","state","seed","order")}
        methods = rec["methods"]
        comparable = all(methods[m]["feasible"] for m in METHODS)
        exact = comparable and methods["D"]["status"] == "optimal"
        for m in METHODS:
            result = methods[m]
            total = totals[m]
            total["statuses"][result["status"]] += 1
            total["feasible"] += result["feasible"]
            total["elapsed_s"] += result["elapsed_s"]
            total["visits"] += result.get("visits", 0)
            row[m+"_status"] = result["status"]
            row[m+"_feasible"] = result["feasible"]
            row[m+"_J"] = result["energy_J"] if result["feasible"] else None
            row[m+"_path"] = " ".join(result["path"])
            row[m+"_s"] = result["elapsed_s"]
            if m == "D":
                for k in ("lower_bound_J","upper_bound_J","visits","thermal_checks","thermal_rejects","bound_prunes"):
                    row[m+"_"+k] = result.get(k)
        row["common_feasible"], row["common_exact"] = comparable, exact
        row["AB_saved_J"] = row["A_J"] - row["B_J"] if comparable else None
        row["BD_saved_J"] = row["B_J"] - row["D_J"] if exact else None
        row["AB_saved_pct"] = 100*row["AB_saved_J"]/row["A_J"] if comparable else None
        row["BD_saved_pct"] = 100*row["BD_saved_J"]/row["B_J"] if exact else None
        if exact:
            assert row["BD_saved_J"] >= -TOL and row["A_J"]-row["D_J"] >= -TOL
        if comparable:
            common.append(row)
            for a,b in combinations(METHODS,2):
                paths[a+b+"_different_paths"] += methods[a]["path"] != methods[b]["path"]
        rows.append(row)
    comp = {}
    for a,b in (("A","B"),("B","D")):
        eligible = [row for row in common if row[a+b+"_saved_J"] is not None]
        if eligible:
            diffs = [row[a+b+"_saved_J"] for row in eligible]
            pcts = [row[a+b+"_saved_pct"] for row in eligible]
            comp[a+b] = dict(n=len(eligible), aggregate_pct=100*sum(diffs)/sum(row[a+"_J"] for row in eligible),
                              min_pct=min(pcts), max_pct=max(pcts), mean_saved_J=mean(diffs),
                              positive=sum(x>TOL for x in diffs), tied=sum(abs(x)<=TOL for x in diffs),
                              negative=sum(x< -TOL for x in diffs))
    changes = pair_changes(records,"order",("load","seed","state")) + pair_changes(records,"state",("load","seed","order"))
    counts = {}
    for factor in ("order","state"):
        for m in METHODS:
            pairs = [p for p in changes if p["factor"]==factor and p["method"]==m and p["both_feasible"]]
            counts[factor+"_"+m] = dict(both_feasible_pairs=len(pairs),changed_pairs=sum(p["differences"]>0 for p in pairs),
                                        changed_choices=sum(p["differences"] for p in pairs),compared_choices=sum(p["compared"] for p in pairs))
    summary = dict(n=len(records), common_feasible=len(common), totals=totals, comparisons=comp,
                   different_paths_on_common=paths, paired_changes=counts,
                   mean_energy_J_on_common={m:mean(row[m+"_J"] for row in common) for m in METHODS} if common else {})
    return rows,changes,summary


def main():
    records = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT/"raw").glob("*.json"))]
    rows,changes,summary = analyze(records)
    evidence=diagnose(records)
    summary["decision_diagnostics"]={}
    for m in METHODS:
        group=[row for row in evidence if row["method"]==m]
        summary["decision_diagnostics"][m]=dict(
            evaluated_entries=len(group),entries_with_deadline_rejections=sum(row["rejected_deadline"]>0 for row in group),
            entries_with_boundary_rejections=sum(row["rejected_boundary"]>0 for row in group),
            entries_with_over_temperature=sum(row["over_temperature"]>0 for row in group),
            entries_where_thermal_limit_removes_best=sum(row["heat_excludes_all_unconstrained_best"] for row in group),
            entries_where_actual_nominal_best_disjoint=sum(row["actual_vs_nominal_best_disjoint"] for row in group),
            entries_where_tail_changes_nominal_best=sum(row["tail_changes_nominal_best"] for row in group),
            kim_selected_above_exhaustive_nominal=sum(row["search_omits_nominal_best"] is True for row in group),
            accepted_positive_local_penalty=sum(row["chosen_extra_current_J"] is not None and
                                                row["chosen_extra_current_J"]>TOL for row in group))
    write_csv(ROOT/"decision_diagnostics.csv",evidence)
    write_csv(ROOT/"comparison.csv", rows)
    write_csv(ROOT/"pairs.csv", changes)
    (ROOT/"statistics.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")


if __name__ == "__main__":
    main()
