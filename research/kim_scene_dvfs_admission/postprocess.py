"""Read-only diagnostics from the saved exhaustive decisions and sequence arrays."""
import argparse
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
NODES = ("CPU", "GPU", "DLA0", "DLA1")
TRIPLETS = tuple(a+b+c for a in "LMH" for b in "LMH" for c in "LMH")


def substitutions(raw, ambient, selected):
    deployment = selected["deployment"]
    if not deployment:
        return None
    choices = [TRIPLETS.index(opp) for opp in selected["opps"]]
    with np.load(raw / f"space_{ambient}_{deployment}.npz") as f:
        feasible = np.flatnonzero(f["status"] == 1)
        energy = f["energy_j"][feasible]
    if not len(feasible):
        return {"deployment": deployment, "feasible_count": 0}
    digits = np.column_stack([(feasible // 27**i) % 27 for i in (3, 2, 1, 0)])
    distance = (digits != choices).sum(axis=1)
    minimum = int(distance.min())
    cheapest = np.min(energy[distance == minimum])
    idx = np.flatnonzero((distance == minimum) & (energy <= cheapest+1e-9))[0]
    return {"deployment": deployment, "feasible_count": int(len(feasible)),
            "minimum_changed_scenes": minimum,
            "count_at_minimum_distance": int(np.sum(distance == minimum)),
            "best_at_minimum_distance_opp": [TRIPLETS[i] for i in digits[idx]],
            "best_at_minimum_distance_j": float(energy[idx])}


def diagnosis(raw):
    decisions = json.loads((raw / "decisions.json").read_text(encoding="utf-8"))
    by_ambient = {}
    for decision in decisions:
        by_ambient.setdefault(decision["ambient"], {})[decision["method"]] = decision
    results = []
    for ambient, methods in sorted(by_ambient.items()):
        independent = methods["independent"]
        physical = independent["physical"]
        first = None
        if physical:
            for row in physical["scene_rows"]:
                if row.get("thermal_status") == "VIOLATION":
                    first = {"scene": row["scene"], "opp": row["opp"],
                             "entry_c": row["entry_c"],
                             "violating_peak_lower_c": {n: t for n,t in zip(NODES, row["peak_lower_c"]) if t>80}}
                    break
        fixed, joint = methods["fixed"]["physical"], methods["joint"]["physical"]
        # Savings require two feasible physical replays of the whole workload.
        def gap(left, right):
            if left and right and left["feasible"] and right["feasible"]:
                return left["energy_j"]-right["energy_j"]
            return None
        results.append({"ambient": ambient, "fixed_minus_independent_j": gap(fixed,physical),
                        "independent_minus_joint_j": gap(physical,joint),
                        "fixed_minus_joint_j": gap(fixed,joint),
                        "independent_first_physical_violation": first,
                        "same_deployment_distance": substitutions(raw,ambient,independent)})
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=HERE/"raw")
    print(json.dumps(diagnosis(parser.parse_args().raw), indent=2))
