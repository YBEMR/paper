"""Read the accepted per-deployment minima and expose all four ablation cells."""
import csv
import hashlib
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent / "derived"
CASE = "reverse_flat_25C"
FROZEN_MINIMA_SHA256 = "b0fcc0165a6119cba226a0ac0c72cbb18095e8a8f01b046b771634ec44c85cba"
POLICIES = ("Static-DVFS", "Scene-DVFS")


def savings(reference, value):
    return 100 * (reference - value) / reference if reference is not None and value is not None else None


def load_minima():
    path = ROOT / "grid_minima.csv"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == FROZEN_MINIMA_SHA256
    lookup = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            policy = row["policy"]
            if row["instance_id"] != CASE or policy not in POLICIES:
                continue
            assert int(row["unresolved"]) == 0
            assert int(row["n_codes"]) == (27 if policy == POLICIES[0] else 27**4)
            value = float(row["strict_min_j"]) if row["strict_min_j"] else None
            assert (value is not None) == (int(row["safe"]) > 0)
            entry = lookup.setdefault(row["deployment"], {})
            assert policy not in entry
            entry[policy] = (value, row["code"], row["source_path"])
    assert len(lookup) == 81 and all(set(x) == set(POLICIES) for x in lookup.values())
    return lookup


def main():
    lookup = load_minima()
    winners = {}
    for policy in POLICIES:
        winners[policy] = min((data[policy][0], dep) for dep, data in lookup.items() if data[policy][0] is not None)
    (best_static, static_dep), (best_scene, scene_dep) = (winners[p] for p in POLICIES)
    rows = []
    for dep, data in sorted(lookup.items()):
        (fixed_static, static_code, source), (fixed_scene, scene_code, _) = (data[p] for p in POLICIES)
        if fixed_static is not None:
            assert fixed_scene is not None and fixed_scene <= fixed_static + 1e-9
        rows.append(dict(instance_id=CASE, fixed_deployment=dep,
            fixed_static_j=fixed_static, fixed_static_code=static_code, fixed_static_status="MIN_SAFE" if fixed_static is not None else "NO_SAFE_PROVED",
            fixed_scene_j=fixed_scene, fixed_scene_code=scene_code, fixed_scene_status="MIN_SAFE" if fixed_scene is not None else "NO_SAFE_PROVED",
            select81_static_j=best_static, select81_static_winner=static_dep, select81_static_code=lookup[static_dep][POLICIES[0]][1],
            select81_scene_j=best_scene, select81_scene_winner=scene_dep, select81_scene_code=lookup[scene_dep][POLICIES[1]][1],
            scene_only_saving_pct=savings(fixed_static, fixed_scene), deployment_only_saving_pct=savings(fixed_static, best_static),
            joint_saving_pct=savings(fixed_static, best_scene), deployment_saving_given_scene_pct=savings(fixed_scene, best_scene),
            fixed_array=source, select81_static_winner_array=lookup[static_dep][POLICIES[0]][2], select81_scene_winner_array=lookup[scene_dep][POLICIES[1]][2]))
    with (ROOT / "figE_sensitivity.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        w = csv.DictWriter(stream, fieldnames=rows[0], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    valid = [r for r in rows if r["scene_only_saving_pct"] is not None]
    rates = [r["scene_only_saving_pct"] for r in valid]
    print(f"{len(valid)}/{len(rows)} comparable; min/median/max = {min(rates):.4f}/{median(rates):.4f}/{max(rates):.4f}%")
    print("Scene-only gain exceeds deployment-only gain:", sum(r["scene_only_saving_pct"] > r["deployment_only_saving_pct"] for r in valid))


if __name__ == "__main__":
    main()
