"""Reanalyse the frozen 25 C policy table, without invoking a thermal solver."""
import argparse
import csv
import hashlib
import json
from collections import Counter
from itertools import product
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "kim_scene_dvfs_admission" / "raw"
FROZEN = "2d352e715463641d6e49e4691d4b16fb02296c80"
INPUT_BLOBS = {
    "local.csv": "aab47f649bf87c44b98ec6c2ce65f923a261692f",
    "space_25_A.npz": "977bdeea3e9da822dc3cfc79357743262f08d1a8",
    "space_25_C.npz": "4f8d79b1847e7e9594925afc7d3a2a4c2747f0b3",
}
OPPS = tuple("".join(v) for v in product("LMH", repeat=3))
N = len(OPPS)
SIZE = N**4
STRIDES = np.array([N**3, N**2, N, 1], dtype=np.int64)
TOL = 1e-9


def digits(code):
    return code // STRIDES % N


def seq(code):
    return " ".join(OPPS[i] for i in digits(code))


def check_input(source):
    for name, expected in INPUT_BLOBS.items():
        data = (source / name).read_bytes()
        # Windows may materialize the original tracked text using CRLF.
        if name.endswith(".csv"):
            data = data.replace(b"\r\n", b"\n")
        digest = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
        if digest != expected:
            raise ValueError(f"input differs from {FROZEN}: {name}")


def load_table(source, deployment, rows):
    local = np.full((4, N), np.inf)
    selected = [r for r in rows if r["deployment"] == deployment and int(r["ambient"]) == 25]
    if len(selected) != 4*N:
        raise ValueError("incomplete local response table")
    for r in selected:
        if int(r["status"]) == 1:
            local[int(r["scene"]), OPPS.index(r["opp"])] = float(r["energy_j"])
    reset = (local[0,:,None,None,None]+local[1,None,:,None,None]
             +local[2,None,None,:,None]+local[3,None,None,None,:]).reshape(-1)
    with np.load(source / f"space_25_{deployment}.npz", allow_pickle=False) as data:
        physical, energy = data["status"], data["energy_j"]
    if (physical.shape != (SIZE,) or not np.array_equal(np.isfinite(reset), physical != 0)
            or np.any(physical==3) or not np.array_equal(np.isfinite(energy), physical!=0)):
        raise ValueError("25 C frozen classifications no longer match their documented domain")
    return reset, physical, energy


def rank_tables(tables):
    # Exact-score ascending with deterministic tie breaks A,C then numeric code.
    # Ranking is descriptive. The original 1e-9-J tie convention applies to winners.
    ranks, global_ranks, ds, cs, scores = {}, {}, [], [], []
    for deployment, (reset, physical, energy) in tables.items():
        feasible = np.flatnonzero(np.isfinite(reset))
        order = feasible[np.lexsort((feasible,reset[feasible]))]
        rank = np.zeros(SIZE, dtype=np.int32)
        rank[order] = np.arange(1,len(order)+1)
        ranks[deployment] = rank
        global_ranks[deployment] = np.zeros_like(rank)
        ds.extend([deployment]*len(order))
        cs.append(order)
        scores.append(reset[order])
    ds, cs, scores = np.asarray(ds), np.concatenate(cs), np.concatenate(scores)
    order = np.lexsort((cs, ds, scores))
    ds, cs = ds[order], cs[order]
    for d in tables:
        mask = ds==d
        global_ranks[d][cs[mask]] = np.flatnonzero(mask)+1
    return ranks, global_ranks, ds, cs


def neighbors(code):
    old = digits(code)
    grid = code + (np.arange(N)[None,:] - old[:,None])*STRIDES[:,None]
    return grid[grid!=code]


def distribution(values):
    if not values:
        return None
    data = np.asarray(values)
    return {"min":float(data.min()),"median":float(np.median(data)),"mean":float(data.mean()),
            "max":float(data.max())}


def sum_rows(records):
    success=[r for r in records if r["first_safe_code"] is not None]
    return {
        "false_safe":len(records),"one_scene_repairable":len(success),
        "not_repairable_in_one_scene":len(records)-len(success),
        "global_rank_range":[min(r["global_reset_rank"] for r in records),max(r["global_reset_rank"] for r in records)],
        "first_safe_full_heat_queries":distribution([r["first_search_queries"] for r in records]),
        "first_safe_total_queries":sum(r["first_search_queries"] for r in records),
        "all_neighbors_total_queries":sum(r["all_search_queries"] for r in records),
        "first_safe_minus_original_diagnostic_j":distribution([r["first_minus_original_j"] for r in success]),
        "best_safe_minus_original_diagnostic_j":distribution([r["best_minus_original_j"] for r in success]),
        "first_safe_minus_best_safe_neighbor_j":distribution([r["first_minus_best_j"] for r in success]),
        "best_safe_minus_global_feasible_min_j":distribution([r["best_minus_global_min_j"] for r in success]),
        "first_equals_neighborhood_best_energy":sum(r["first_minus_best_j"]<=TOL for r in success),
        "first_safe_cost_sign_relative_to_unsafe_original": {
            "higher":sum(r["first_minus_original_j"]>TOL for r in success),
            "same":sum(abs(r["first_minus_original_j"])<=TOL for r in success),
            "lower":sum(r["first_minus_original_j"]< -TOL for r in success)},
        "cheapest_false_safe_reset_j":min(r["reset_j"] for r in records),
        "number_of_safe_neighbors":distribution([r["safe_neighbors"] for r in records]),
    }


def write_csv(path, rows):
    with path.open("w",newline="",encoding="utf8") as f:
        w = csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def run(source, out):
    check_input(source)
    with (source/"local.csv").open(encoding="utf-8-sig",newline="") as f:
        local_rows=list(csv.DictReader(f))
    tables={d:load_table(source,d,local_rows) for d in "AC"}
    ranks,global_ranks,ordered_d,ordered_c=rank_tables(tables)
    global_min=min(energy[physical==1].min() for reset,physical,energy in tables.values())
    results=[]
    summary={}
    winners={}
    for d,(reset,physical,energy) in tables.items():
        candidates = np.flatnonzero(np.isfinite(reset))
        lowest = reset[candidates].min()
        winner = int(candidates[reset[candidates]<=lowest+TOL][0])
        winners[d]={"code":winner,"opps":seq(winner),"score_j":float(reset[winner]),
                    "status":int(physical[winner]),"continuous_j":float(energy[winner])}
        false_cases=np.flatnonzero(np.isfinite(reset)&(physical==2))
        deploy_min=energy[physical==1].min()
        all_accessed, first_accessed = set(),set()
        per_d=[]
        for code in false_cases:
            hood=neighbors(code)
            elig=hood[physical[hood]!=0]
            order=elig[np.lexsort((elig,reset[elig]))]
            safe=np.flatnonzero(physical[order]==1)
            first_count=int(safe[0])+1 if len(safe) else len(order)
            all_accessed.update(order.tolist())
            first_accessed.update(order[:first_count].tolist())
            r={"deployment":d,"code":int(code),"opps":seq(code),
               "global_reset_rank":int(global_ranks[d][code]),"deployment_reset_rank":int(ranks[d][code]),
               "reset_j":float(reset[code]),"continuous_j":float(energy[code]),"continuous_status":"VIOLATION",
               "nominal_neighbors":len(hood),"deadline_failed_neighbors":len(hood)-len(elig),
               "safe_neighbors":len(safe),"first_search_queries":first_count,"all_search_queries":len(order),
               "first_safe_code":None,"first_changed_scene":None,"first_safe_j":None,"first_minus_original_j":None,
               "best_safe_code":None,"best_changed_scene":None,"best_safe_j":None,"best_minus_original_j":None,
               "first_minus_best_j":None,"best_minus_deployment_min_j":None,"best_minus_global_min_j":None}
            if len(safe):
                good=order[safe]
                first=int(good[0])
                best=int(np.min(good[energy[good]<=np.min(energy[good])+TOL]))
                r.update(first_safe_code=first,first_changed_scene=int(np.flatnonzero(digits(code)!=digits(first)).item()),
                         first_safe_j=float(energy[first]),first_minus_original_j=float(energy[first]-energy[code]),
                         best_safe_code=best,best_changed_scene=int(np.flatnonzero(digits(code)!=digits(best)).item()),
                         best_safe_j=float(energy[best]),best_minus_original_j=float(energy[best]-energy[code]),
                         first_minus_best_j=float(energy[first]-energy[best]),
                         best_minus_deployment_min_j=float(energy[best]-deploy_min),
                         best_minus_global_min_j=float(energy[best]-global_min))
            if len(hood)!=104 or len(set(hood))!=104 or code in hood or len(order)!=68:
                raise ArithmeticError("unfrozen or invalid one-scene graph")
            per_d.append(r)
        results.extend(per_d)
        summary[d]={**sum_rows(per_d),"first_safe_unique_queries_if_cache_shared":len(first_accessed),
                    "all_neighbors_unique_queries_if_cache_shared":len(all_accessed),
                    "independent_feasible":len(candidates),"continuous_feasible":int(np.sum(physical==1)),
                    "lowest_false_deployment_rank":min(r["deployment_reset_rank"] for r in per_d)}
    results.sort(key=lambda r:r["global_reset_rank"])
    if len(results)!=4707 or summary["A"]["false_safe"]!=2742 or summary["C"]["false_safe"]!=1965:
        raise ArithmeticError("historical false-safe identities or counts have drifted")
    if any(v["status"]!=1 for v in winners.values()):
        raise ArithmeticError("frozen independent winner is unexpectedly unsafe")
    scene_counts, transitions, first_queries = Counter(), Counter(), Counter()
    increased_domain_cases = 0
    for r in results:
        first_queries[str(r["first_search_queries"])] += 1
        if r["first_safe_code"] is None:
            continue
        scene = r["first_changed_scene"]
        old = OPPS[digits(r["code"])[scene]]
        new = OPPS[digits(r["first_safe_code"])[scene]]
        scene_counts[str(scene)] += 1
        transitions[old + "->" + new] += 1
        increased_domain_cases += int(any("LMH".index(y) > "LMH".index(x) for x,y in zip(old,new)))
    structure = {"first_safe_changed_scene_counts":dict(sorted(scene_counts.items())),
                 "first_safe_search_query_histogram":dict(sorted(first_queries.items())),
                 "first_safe_OPP_changes":dict(sorted(transitions.items())),
                 "first_safe_had_any_domain_increase":increased_domain_cases,
                 "first_three_deciles_without_false_safe":all(r["global_reset_rank"]>len(ordered_c)*3//10 for r in results)}
    n=len(ordered_c)
    bands=[]
    for band in range(10):
        lo=n*band//10
        hi=n*(band+1)//10
        failures=sum(lo<r["global_reset_rank"]<=hi for r in results)
        bands.append({"global_score_decile":band+1,"rank_start":lo+1,"rank_end":hi,
                      "independent_feasible":hi-lo,"continuous_violations":failures,
                      "violation_fraction":failures/(hi-lo)})
    global_winner=min(winners,key=lambda d:(winners[d]["score_j"],d))
    out.mkdir(parents=True,exist_ok=True)
    write_csv(out/"historical_repairs.csv",results)
    write_csv(out/"historical_rank_bands.csv",bands)
    payload={"input_commit":FROZEN,"independent_rank_population":n,"deployments":summary,
             "per_deployment_independent_winners":winners,"global_independent_winner":global_winner,
             "aggregate":sum_rows(results),"cheapest_false_safe":results[0],"structural_diagnostics":structure,
             "ranking":"One-based among reset-feasible complete sequences; increasing exact reset J, A/C then base-27 code.",
             "query_accounting":"Each query is one complete-sequence thermal classification if no cache; first/all are alternative scans, excluding the already rejected source. All results here are lookups of the frozen physical array: no calls to a thermal simulator in this script. Repeated queries across different source candidates counted separately unless unique is indicated.",
             "energy_accounting":"Repair minus rejected original is a diagnostic difference. A rejected original is never an admissible baseline for energy savings.",
             "repair_choice":"Within the same resident deployment, one of four scene triplets changes. Filter deadline-failed neighbors, sort reset energy then numeric code, stop at first SAFE. Neighborhood optimum minimizes continuous joules, original 1e-9 J tie tolerance with lowest code."}
    (out/"historical_summary.json").write_bytes((json.dumps(payload,indent=2,ensure_ascii=False)+"\n").encode())
    return payload


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,default=SOURCE)
    parser.add_argument("--out",type=Path,default=HERE/"raw")
    args=parser.parse_args()
    result=run(args.source,args.out)
    print(json.dumps(result["aggregate"],indent=2))
