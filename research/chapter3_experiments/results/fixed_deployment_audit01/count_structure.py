"""Read-only finite-set audit; no MILP matrix, schedules or RC evaluation.

Run from any directory with Python. Only static_counts.json/counts.csv beside
this script are written. The historical witness supplies a deployment example,
never a candidate for a new solver invocation. Every compatible OPP/start stays.
"""

import csv
from fractions import Fraction as F
from hashlib import sha256
from itertools import product
import json
from math import prod
from pathlib import Path
import sys


OUT = Path(__file__).resolve().parent
PROJECT = OUT.parents[3]
ARCHIVE = OUT.parent / "base_warm_diagnostic01"
MODULES = PROJECT / "research/chapter3_experiments"
sys.path.insert(0, str(MODULES))
from inputs import expand_options  # Only the existing pure local-option reader.


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def read(name):
    return json.loads((ARCHIVE / name).read_text(encoding="utf-8"))


def independent_options(instance):
    """Independent Cartesian local choices, not complete Stage arrangements."""
    rows = []
    grid, window = F(instance["start_grid_ms"]), F(instance["window_ms"])
    for scene in instance["scenarios"]:
        requests = {r["id"]: r for r in scene["requests"]}
        for stage in scene["stage_instances"]:
            req = requests[stage["request_id"]]
            for mode in instance["stage_modes"][stage["shared_stage_id"]]:
                for index in range(int(window // grid) + 1):
                    start, end = grid * index, grid * index + F(mode["duration_ms"])
                    if start >= F(req["release_ms"]) and end <= window:
                        rows.append((scene["id"], stage["id"], mode["unit_id"],
                                     mode["opp_id"], start, end))
    return rows


def option_key(o):
    return (o["scenario_id"], o["stage_instance_id"], o["unit_id"],
            o["opp_id"], F(o["start_ms"]), F(o["end_ms"]))


def structure(instance, options):
    domains = list(instance["platform"]["domains"])
    nodes = list(instance["platform"]["node_order"])
    rows = []
    for scene in instance["scenarios"]:
        choices = [o for o in options if o["scenario_id"] == scene["id"]]
        events = sorted({F(0), F(instance["window_ms"])} |
                        {F(o[k]) for o in choices for k in ("start_ms", "end_ms")})
        # Sweep matches the construction's necessary prefix OPP superset.
        starts, first = {}, {}
        for o in choices:
            t = F(o["start_ms"])
            starts.setdefault(t, []).append(o)
            key = o["domain_id"], o["opp_id"]
            first[key] = min(first.get(key, t), t)
        prefix = {d: {scene["entry"]["domain_opp"][d]} for d in domains}
        state_count, max_states = 0, 0
        signatures = set()
        for left, right in zip(events, events[1:]):
            for o in starts.get(left, []):
                prefix[o["domain_id"]].add(o["opp_id"])
            # Independent first-start characterization of the same superset.
            direct = {d: {scene["entry"]["domain_opp"][d]} |
                      {opp for (dom, opp), t in first.items() if dom == d and t <= left}
                      for d in domains}
            assert prefix == direct
            number = prod(len(prefix[d]) for d in domains)
            state_count += number
            max_states = max(max_states, number)
            for state in product(*(sorted(prefix[d]) for d in domains)):
                signatures.add((state, right-left))
        intervals = len(events) - 1
        inactive = [d for d in domains if not any(o["domain_id"] == d for o in choices)]
        rows.append({
            "scene": scene["id"], "options": len(choices),
            "events": len(events), "intervals": intervals,
            "max_prefix_joint_states": max_states,
            "interval_state_pairs": state_count,
            "conditional_thermal_energy_rows": 2*(len(nodes)+1)*state_count,
            "energy_lower_bound_rows": intervals,
            "temperature_variables_at_all_boundaries": len(nodes)*len(events),
            "thermal_nodes_retained": nodes,
            "domains_without_stage_work": inactive,
            "held_opp_for_domains_without_work": {d: scene["entry"]["domain_opp"][d] for d in inactive},
            "distinct_state_duration_pairs": len(signatures),
            "event_set_sha256": sha256("\n".join(map(str, events)).encode()).hexdigest(),
            "prefix_count_crosscheck": "PASS",
        })
    totals = {name: sum(r[name] for r in rows) for name in (
        "options", "events", "intervals", "interval_state_pairs",
        "conditional_thermal_energy_rows", "energy_lower_bound_rows",
        "temperature_variables_at_all_boundaries")}
    return {"scenes": rows, "total": totals}


def main():
    instance, config = read("input_instance.json"), read("input_config.json")
    integrity = read("source_integrity.json")
    source_paths = [MODULES / f for f in ("inputs.py", "milp.py", "schedules.py", "thermal.py", "milp_coefficients.py", "config_v01.json")]
    before = {p.relative_to(PROJECT).as_posix(): digest(p) for p in source_paths}
    assert all(integrity["before"][name] == value for name, value in before.items())
    # The archive uses a different JSON serialization, not different inputs.
    assert config == json.loads((MODULES / "config_v01.json").read_text(encoding="utf-8"))
    options = expand_options(instance, config)
    assert set(map(option_key, options)) == set(independent_options(instance))
    assert len(options) == len(set(map(option_key, options)))
    receipt = read("initial_receipt_checkpoint.json")
    candidate = receipt["initialisation"]["witness"]["candidate"]
    deployment = {}
    candidate_keys = []
    for scene in instance["scenarios"]:
        stages = {s["id"]: s for s in scene["stage_instances"]}
        for row in candidate["scenes"][scene["id"]]:
            shared = stages[row["stage_id"]]["shared_stage_id"]
            if shared in deployment:
                assert deployment[shared] == row["unit"]
            deployment[shared] = row["unit"]
            mode = next(m for m in instance["stage_modes"][shared]
                        if m["unit_id"] == row["unit"] and m["opp_id"] == row["opp"])
            candidate_keys.append((scene["id"], row["stage_id"], row["unit"], row["opp"],
                                   F(row["start_ms"]), F(row["start_ms"])+F(mode["duration_ms"])))
    assert set(deployment) == set(instance["stage_modes"])
    filters = {
        "original": lambda o: True,
        "deadline_only": lambda o: F(o["end_ms"]) <= F(o["request_deadline_ms"]),
        "deployment_only": lambda o: o["unit_id"] == deployment[o["shared_stage_id"]],
        "deployment_and_deadline": lambda o: o["unit_id"] == deployment[o["shared_stage_id"]]
        and F(o["end_ms"]) <= F(o["request_deadline_ms"]),
    }
    counts = {name: structure(instance, [o for o in options if keep(o)]) for name, keep in filters.items()}
    retained = [o for o in options if filters["deployment_and_deadline"](o)]
    assert set(candidate_keys) <= set(map(option_key, retained))
    # For each chosen unit, no OPP or start satisfying the local request/window
    # restrictions has been selectively removed.
    for scene in instance["scenarios"]:
        for stage in scene["stage_instances"]:
            group = [o for o in retained if o["stage_instance_id"] == stage["id"]]
            assert group
            assert {o["opp_id"] for o in group} == {m["opp_id"] for m in instance["stage_modes"][stage["shared_stage_id"]]
                                                    if m["unit_id"] == deployment[stage["shared_stage_id"]]}
    archived = json.loads((ARCHIVE / "build_progress.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    original = counts["original"]
    assert original["total"]["options"] == archived["options"] == 6422
    assert {r["scene"]: r["events"] for r in original["scenes"]} == archived["events_per_scene"]
    assert original["total"]["interval_state_pairs"] == archived["construction_components"]["coefficient_lookup_and_generation"]["calls"]
    assert original["total"]["interval_state_pairs"] == 48033
    assert not ({"milp", "thermal", "matlab_bridge", "milp_coefficients"} & set(sys.modules))
    after = {p.relative_to(PROJECT).as_posix(): digest(p) for p in source_paths}
    assert before == after
    unit_counts = {s: len({m["unit_id"] for m in modes}) for s, modes in instance["stage_modes"].items()}
    result = {
        "scope": "STATIC_FINITE_SETS_ONLY_NO_MODEL_BUILD_SOLVE_OR_RC_EVALUATION",
        "date": "2026-10-17", "problem_id": instance["id"],
        "input_hashes": {name: digest(ARCHIVE/name) for name in ("input_instance.json", "input_config.json", "initial_receipt_checkpoint.json", "build_progress.jsonl")},
        "audit_source_sha256": digest(Path(__file__)),
        "source_hashes_before": before, "source_hashes_after": after,
        "deployment_example_source": "base_warm_diagnostic01/initial_receipt_checkpoint.json; unit identities filter options; historical OPPs/starts only crosscheck retention, never seed a solve",
        "deployment_example": deployment,
        "remaining_choices": "all compatible OPPs and grid starts; exact rational ends; dependencies/resources/heat not assumed feasible",
        "state_semantics": "necessary prefix OPP Cartesian superset, not exact reachable states",
        "row_semantics": "2*(4 thermal nodes+1 energy)*interval-state pairs; dominant family only, no matrix assembled",
        "original_archive_count_match": True,
        "option_reader_independent_crosscheck": "PASS",
        "historical_arrangement_local_choices_retained": True,
        "all_compatible_opps_retained_for_example": True,
        "source_unchanged": before == after,
        "archived_current_config_semantic_match": True,
        "legal_unit_combinations_before_timing_and_thermal_checks": prod(unit_counts.values()),
        "distinct_scene_deployment_combinations_before_timing_and_thermal_checks": {
            s["id"]: prod(unit_counts[k] for k in {st["shared_stage_id"] for st in s["stage_instances"]})
            for s in instance["scenarios"]},
        "variants": counts,
        "model_built": False, "solver_called": False, "thermal_evaluated": False,
        "speedup_measured": False, "new_algorithm_selected": False,
    }
    (OUT/"static_counts.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    fields = ["variant", "scene", "options", "events", "intervals", "max_prefix_joint_states", "interval_state_pairs", "conditional_thermal_energy_rows", "energy_lower_bound_rows"]
    with (OUT/"counts.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for name, value in counts.items():
            for row in value["scenes"]:
                writer.writerow({"variant": name, **{k: row[k] for k in fields[1:]}})
    print(json.dumps({"scope": result["scope"], "totals": {k: v["total"] for k, v in counts.items()}, "checks": "PASS"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
