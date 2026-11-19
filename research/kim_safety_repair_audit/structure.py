"""Describe energy/peak rank agreement using only the historical, frozen local actions."""
import argparse
import csv
import json
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy.stats import rankdata

HERE = Path(__file__).resolve().parent
NODES = ("CPU", "GPU", "DLA0", "DLA1")
CLOCK_ORDER = {name: i for i, name in enumerate("LMH")}
EPS_J = 1e-9


def signs_opp(opp):
    return tuple(CLOCK_ORDER[level] for level in opp)


def strength(energy, peak):
    energy_rank = rankdata(energy, method="average")
    peak_rank = rankdata(peak, method="average")
    if not np.ptp(peak_rank) or not np.ptp(energy_rank):
        return None
    return float(np.corrcoef(energy_rank, peak_rank)[0, 1])


def describe(actions):
    actions = sorted(actions, key=lambda row: (row["energy_j"], signs_opp(row["opp"])))
    cheapest = actions[0]
    e = [row["energy_j"] for row in actions]
    midpoint = [0.5*(row["hottest_upper_c"]+row["hottest_lower_c"]) for row in actions]
    cooler = sum(row["hottest_upper_c"] < cheapest["hottest_lower_c"] for row in actions[1:])
    hotter = sum(row["hottest_lower_c"] > cheapest["hottest_upper_c"] for row in actions[1:])

    counts = {"certified_concordant": 0, "certified_discordant": 0, "overlapping_peak_brackets": 0,
              "energy_tie": 0}
    maximally_discordant = None
    for low, high in combinations(actions, 2):
        if high["energy_j"] - low["energy_j"] <= EPS_J:
            counts["energy_tie"] += 1
        elif low["hottest_upper_c"] < high["hottest_lower_c"]:
            counts["certified_concordant"] += 1
        elif low["hottest_lower_c"] > high["hottest_upper_c"]:
            counts["certified_discordant"] += 1
            margin = low["hottest_lower_c"] - high["hottest_upper_c"]
            if maximally_discordant is None or margin > maximally_discordant["min_peak_excess_c"]:
                maximally_discordant = dict(lower_energy=low["opp"], higher_energy=high["opp"],
                                            min_peak_excess_c=margin)
        else:
            counts["overlapping_peak_brackets"] += 1
    if sum(counts.values()) != len(e)*(len(e)-1)//2:
        raise AssertionError("Unclassified local pair")
    winner_levels = np.array(signs_opp(cheapest["opp"]))
    return dict(n_deadline_valid=len(actions), cheapest_opp=cheapest["opp"],
                cheapest_energy_j=cheapest["energy_j"],
                cheapest_peak_bracket_c=[cheapest["hottest_lower_c"], cheapest["hottest_upper_c"]],
                cheapest_rank_among_coolest_interval=[1+cooler, len(e)-hotter],
                cheapest_is_componentwise_lowest_legal_opp=all(
                    np.all(winner_levels<=signs_opp(row["opp"])) for row in actions),
                spearman_j_vs_peak_midpoint=strength(e, midpoint),
                spearman_j_vs_peak_rounded_millikelvin=strength(e, np.round(midpoint, 3)),
                pair_counts=counts, largest_certified_inversion=maximally_discordant, actions=actions)


def main(source):
    sys.path.insert(0, str(source))
    from scene_events import OPPS, PLATFORM, evaluate_thermal, split_workload, thermal_kwargs, time_scene
    with (source/"raw"/"local.csv").open(encoding="utf-8-sig", newline="") as stream:
        old = {(r["deployment"], int(r["scene"]), r["opp"]): r for r in csv.DictReader(stream)
               if int(r["ambient"]) == 25}
    groups = []
    maximum_j_error = 0.
    for dep in ("A", "C"):
        for scene in split_workload("10s", 25):
            actions = []
            for opp in OPPS:
                archived = old[dep,scene.index,opp]
                schedule = time_scene(PLATFORM, scene, dep, opp)
                if schedule.deadline_feasible != (archived["deadline_ok"]=="True"):
                    raise AssertionError("Deadline classification drifted")
                if not schedule.deadline_feasible:
                    continue
                kwargs = thermal_kwargs(PLATFORM, opp,25,True,"base")
                if kwargs["ambient_C"]!=25 or list(kwargs["initial_C"]) != [30.]*4:
                    raise AssertionError("Historical independent-reset conditions changed")
                result = evaluate_thermal(schedule.duration_ns*1e-9,schedule.active_w,
                                          transfer_W=schedule.transfer_w,**kwargs)
                delta=abs(float(archived["energy_j"])-result["energy_J"])
                maximum_j_error=max(maximum_j_error, delta)
                if delta>1e-7 or result["thermal_status"]!="SAFE" or archived["status"]!="1":
                    raise AssertionError("Historical local result differs")
                lower, upper = result["peak_lower_C"], result["peak_upper_C"]
                actions.append(dict(opp=opp, energy_j=result["energy_J"], hottest_lower_c=max(lower),
                                    hottest_upper_c=max(upper), peak_lower_c=lower,peak_upper_c=upper,
                                    node_with_largest_lower_bound=NODES[int(np.argmax(lower))]))
            groups.append(dict(deployment=dep,scene=scene.name, **describe(actions)))
    return dict(coverage="Historical 25 C ambient, four 30 C reset entries, frozen 25 FPS/10s. Search limited to deadline-valid local actions of each fixed deployment and scene.",
                scope="These descriptive finite-set rank correlations apply to independently scored scene segments. They do not establish monotonicity, continuous-policy peak ranks or a hardware law. SC2 and SC3 have identical mappings across A and C.",
                order="ascending energy and ascending hottest-node continuous peak; 1 is cheapest or coolest. Ranks with exact ties are averaged. Second correlation rounds peak-bracket midpoints to 0.001 C. Pair inversions require disjoint brackets.",
                source_commit="2d352e715463641d6e49e4691d4b16fb02296c80",node_order=NODES,
                local_actions_replayed=sum(row["n_deadline_valid"] for row in groups),
                max_abs_energy_error_vs_archived_j=maximum_j_error,groups=groups)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=HERE.parent/"kim_scene_dvfs_admission")
    parser.add_argument("--output", type=Path, default=HERE/"raw"/"structure.json")
    args=parser.parse_args()
    result=main(args.source.resolve())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes((json.dumps(result,indent=2,allow_nan=False)+"\n").encode("utf8"))
