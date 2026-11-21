"""Account for the four certified old-domain winners and their new-domain witnesses.

SAFE implies that every request completed every stage within its scene, so the
active integral is the sum of each frozen stage's watts times service duration.
Only the temperature-dependent leakage component is obtained by subtraction
from the certified system total. No schedules, thermal trajectories or searches
are rerun here.
"""
import argparse
from collections import defaultdict
import json
from math import fsum, isfinite
from pathlib import Path
import sys

from analyze import OPPS, read_csv, write_csv


def decode_legacy(code):
    indices = []
    for _ in range(4):
        code, index = divmod(code, 27)
        indices.append(index)
    if code:
        raise ValueError("Archived frequency code exceeds four scenes")
    return [OPPS[i] for i in reversed(indices)]


def components(build_chains, platform, model, stages, opps, scene_order, frames, energy):
    binding = dict(applications=model["applications"], deployments={"selected": {"stages": stages}})
    activity = defaultdict(list)
    idle, board = [], []
    for index, (scene, n, opp) in enumerate(zip(scene_order, frames, opps, strict=True)):
        span_s = (n + int(index == 3)) * 0.040
        power = platform["power"]
        clocks = platform["clock"]
        for domain, level in zip(clocks["domain_order"], opp, strict=True):
            idle.append(span_s * power["idle_by_domain_W"][domain][clocks["levels"].index(level)])
        board.append(span_s * power["board_W"])
        chains = build_chains(platform, binding, "selected", opp)
        for app in model["fsm"]["active_apps"][scene]:
            for stage in chains[app]:
                resource = "CPU" if stage.resource.startswith("CPU") else stage.resource
                activity[resource].append(n * stage.duration_ns * 1e-9 * stage.activity_w)
    values = {r.lower()+"_active_j": fsum(activity[r]) for r in ("CPU","GPU","DLA0","DLA1","XFER")}
    values.update(board_j=fsum(board), reference_idle_j=fsum(idle))
    residual = energy - fsum(values.values())
    if not isfinite(residual) or residual < -1e-8:
        raise ValueError("Negative or nonfinite temperature-dependent residual")
    return {**values, "temperature_leakage_residual_j": residual}


def main(root, tables):
    sys.path.insert(0, str(root / "research/kim_synthetic_platform_v1"))
    from profiles import build_chains
    platform = json.loads((root/"research/kim_synthetic_platform_v1/platform.json").read_bytes())
    model = json.loads((root/"research/kim_case_b_freeze/input.json").read_bytes())
    catalog = json.loads((root/"research/kim_multidnn_expansion/catalog.json").read_bytes())
    instances = {r["instance_id"]: r for r in read_csv(root/"research/ch3_final_experiments/derived/instances.csv")}
    old = [r for r in read_csv(tables/"historical_references.csv") if r["domain"] == "81" and r["method"] == "CT-Joint"]
    new = {(r["case"],r["method"],r["seed"]): r for r in read_csv(tables/"run_results.csv") if r["scope"] == "extended"}
    bounds = {(r["case"],r["method"]): r for r in read_csv(tables/"domain_witnesses.csv") if r["scope"] == "extended"}
    output = []
    for reference in old:
        case = reference["case"]
        inst = instances[case]
        scenes, frames = inst["scene_order"].split("/"), [int(s) for s in inst["frames_execution_order"].split("/")]
        dep = reference["winner_dep"]
        records = [("legacy81_certified_min","CT-Joint","",dep,catalog["deployments"][dep]["stages"],
                    decode_legacy(int(reference["opp_code"])),float(reference["safe_energy_j"]))]
        for group in ("all_extended_methods","full"):
            w = bounds[case,group]
            entry = new[case,w["witness_method"],w["witness_seed"]]
            records.append((group,entry["method"],entry["seed"],entry["deployment"],
                            json.loads(entry["resident_stages"]),entry["frequency_sequence"].split("/"),
                            float(entry["safe_energy_j"])))
        for role, method, seed, dep, stages, opps, energy in records:
            values = components(build_chains,platform,model,stages,opps,scenes,frames,energy)
            output.append(dict(case=case, role=role, method=method, seed=seed, deployment=dep,
                               opps="/".join(opps), stages=json.dumps(stages,separators=(",",":")),
                               certified_policy_energy_j=energy, **values))
    if len(output) != 12:
        raise ValueError("Expected four complete 25 C comparisons")
    write_csv(tables/"witness_energy_components.csv", output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--tables", type=Path, required=True)
    args = parser.parse_args()
    main(args.source_root.resolve(), args.tables)
