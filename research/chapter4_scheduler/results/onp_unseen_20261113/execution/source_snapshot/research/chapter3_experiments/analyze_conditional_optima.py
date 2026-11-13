"""Read K.194 receipts and K.196 HEFT output; no model/search/thermal imports.

This is minimization over already evaluated records, not a new enumeration.
Fractions preserve saved endpoints exactly; displayed Decimal endpoints round
outward. The result applies only to the archived restricted K.194 domain.
"""
import argparse
from collections import Counter, defaultdict
from decimal import Decimal, localcontext, ROUND_FLOOR, ROUND_CEILING
from fractions import Fraction as Q
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "research/chapter3_experiments/results"
EXACT = RESULTS / "small_exact_execution01"
COMPARISON = RESULTS / "k196_quality_comparison02"


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def decimal(value, upper=False):
    value = Q(value)
    with localcontext() as ctx:
        ctx.prec = 55
        ctx.rounding = ROUND_CEILING if upper else ROUND_FLOOR
        return str(Decimal(value.numerator) / Decimal(value.denominator))


def interval(lo, hi):
    assert lo <= hi
    return {"exact_J": [str(lo), str(hi)],
            "decimal_J": [decimal(lo), decimal(hi, True)],
            "width_J": str(hi - lo)}


def weighted(values, weights):
    return tuple(sum(weights[s] * Q(values[s][i]) for s in weights) for i in (0, 1))


def subtract(a, b):
    return a[0] - b[1], a[1] - b[0]


def percent(a, b):
    """Positive numerator interval divided by positive denominator interval."""
    assert a[0] >= 0 and b[0] > 0
    return [decimal(100 * a[0] / b[1]), decimal(100 * a[1] / b[0], True)]


def analyze():
    sources = {}

    def load(path):
        sources[path.relative_to(ROOT).as_posix()] = digest(path)
        return read(path)

    declaration = load(EXACT / "declaration.json")
    instance = load(EXACT / "input_instance.json")
    load(EXACT / "input_config.json")
    assert not declaration["fixture_only"]
    assert digest(EXACT / "input_instance.json") == declaration["input_sha256"]
    assert digest(EXACT / "input_config.json") == declaration["config_sha256"]
    for path, expected in declaration["source_sha256"].items():
        assert digest(ROOT / path) == expected, path
    manifest_path = EXACT / "scene_manifest.jsonl"
    sources[manifest_path.relative_to(ROOT).as_posix()] = digest(manifest_path)
    assert digest(manifest_path) == declaration["manifest_sha256"]
    manifest = [json.loads(line) for line in manifest_path.read_bytes().splitlines()]
    records = load(EXACT / "coverage_records.json")
    counts = load(RESULTS / "small_exact_protocol01/domain_counts.json")
    reference = load(EXACT / "reference.json")
    previous = load(EXACT / "selected_summary02.json")
    terminal = load(EXACT / "terminal.json")
    assert reference["formal_reference_accepted"] and reference["formed_before_root_deadline"]
    assert terminal["formal_reference_accepted"] and terminal["calls_started"] == 1550
    assert len(manifest) == len(records) == counts["scene_evaluations_for_full_coverage"] == 1550
    assert [r["ordinal"] for r in manifest] == list(range(1, 1551))
    assert len({r["id"] for r in manifest}) == 1550
    assert set(records) == {r["id"] for r in manifest}
    assert Counter(r["state"] for r in records.values()) == {"SAFE": 1550}
    weights = {s["id"]: Q(s["weight"]) for s in instance["scenarios"]}
    assert all(w > 0 for w in weights.values()) and sum(weights.values()) == 1
    assert instance["execution_rules"]["scenario_entry"].startswith("independent;")

    ledger_path = EXACT / "ledger.jsonl"
    sources[ledger_path.relative_to(ROOT).as_posix()] = digest(ledger_path)
    ledger = [json.loads(line) for line in ledger_path.read_bytes().splitlines()]
    finished = {e["id"]: e for e in ledger if e["event"] == "CALL_FINISHED"}
    assert len(finished) == 1550
    groups, mappings, raw_scenes = defaultdict(list), defaultdict(set), {}
    largest_saved_width = Q(0)
    for row in manifest:
        key, scene, unit = row["id"], row["scene_id"], row["shared_A_device"]
        assert sha256(canonical(row["candidate"]).encode()).hexdigest() == key
        assert set(row["candidate"]["scenes"]) == {scene}
        for task in row["candidate"]["scenes"][scene]:
            shared = task["stage_id"].split("::")[-1]
            mappings[shared].add(task["unit"])
            if shared == "A.main":
                assert task["unit"] == unit
        event = finished[key]
        assert event["candidate_sha256"] == key
        assert event["full_input_sha256"] == declaration["input_sha256"]
        raw_path, adm_path = EXACT / event["raw_file"], EXACT / event["admission_file"]
        assert digest(raw_path) == event["raw_sha256"]
        assert digest(adm_path) == event["admission_sha256"]
        admission = read(adm_path)
        assert admission == records[key] and admission["safe_completed_before_deadline"]
        raw = read(raw_path)
        assert raw["request"]["full_input_sha256"] == declaration["input_sha256"]
        assert raw["request"]["candidate_sha256"] == key
        saved = raw["raw_receipt"]["scenes"][scene]
        assert saved["state"] == "SAFE" and saved["complete"]
        assert tuple(map(Q, saved["energy_J"])) == tuple(map(Q, admission["energy_J"]))
        lo, hi = map(Q, admission["energy_J"])
        assert 0 < lo <= hi and saved["energy_accuracy_met"]
        largest_saved_width = max(largest_saved_width, hi - lo)
        raw_scenes[key] = saved
        groups[scene, unit].append(row)
    assert mappings["A.main"] == {"CPU1", "NPU0"}
    occurrence_count = Counter(t["shared_stage_id"] for s in instance["scenarios"] for t in s["stage_instances"])
    repeated = {stage for stage, count in occurrence_count.items() if count > 1}
    assert repeated == {"A.pre", "A.main", "A.post"}
    assert all(len(mappings[stage]) == 1 for stage in repeated if stage != "A.main")

    group_results, envelopes, witnesses = [], {}, {}
    for (scene, unit), rows in sorted(groups.items()):
        assert len(rows) == counts["by_scene"][scene]["legal_count_by_shared_A_unit"][unit]
        lower = min(Q(records[r["id"]]["energy_J"][0]) for r in rows)
        winner = min(rows, key=lambda r: (Q(records[r["id"]]["energy_J"][1]), r["id"]))
        upper = Q(records[winner["id"]]["energy_J"][1])
        old = next(g for g in reference["groups"] if g["scene_id"] == scene and g["shared_A_device"] == unit)
        assert (lower, upper) == (Q(old["lower"]), Q(old["upper"]))
        assert winner["id"] == old["SAFE_witness_id"]
        envelopes[scene, unit] = (lower, upper)
        witnesses[scene, unit] = winner
        group_results.append({"scene": scene, "A.main_unit": unit, "saved_schedules": len(rows),
                              "optimum_enclosure": interval(lower, upper),
                              "witness_id": winner["id"], "candidate": winner["candidate"]})

    conditioned = {}
    for unit in ("CPU1", "NPU0"):
        bounds = weighted({s: envelopes[s, unit] for s in weights}, weights)
        assert bounds == tuple(map(Q, previous["device_conditioned_joint_minimum_enclosures_J"][unit]))
        conditioned[unit] = bounds
    opened = (min(v[0] for v in conditioned.values()), min(v[1] for v in conditioned.values()))
    assert opened == (Q(reference["lower_bound_J"]), Q(reference["upper_bound_J"]))
    independent = weighted({s: (min(envelopes[s, u][0] for u in ("CPU1", "NPU0")),
                                min(envelopes[s, u][1] for u in ("CPU1", "NPU0"))) for s in weights}, weights)
    assert all(envelopes[s, "NPU0"][1] < envelopes[s, "CPU1"][0] for s in weights)
    assert independent == opened == conditioned["NPU0"]
    assert counts["global_legal_complete_arrangements"] == sum(
        len(groups[next(iter(weights)), u]) * len(groups[list(weights)[1], u]) for u in ("CPU1", "NPU0"))

    plan = load(RESULTS / "k196_comparison_preparation01/plan.json")
    assert plan["input_sha256"] == declaration["input_sha256"]
    assert plan["config_sha256"] == declaration["config_sha256"]
    assert digest(ROOT / plan["input_file"]) == declaration["input_sha256"]
    assert digest(ROOT / plan["config_file"]) == declaration["config_sha256"]
    summary = load(COMPARISON / "summary.json")
    batch = load(COMPARISON / "batch.json")
    assert batch["plan_sha256"] == digest(RESULTS / "k196_comparison_preparation01/plan.json")
    heft = next(row for row in summary["heuristics"] if row["id"] == "heft")
    raw_heft = COMPARISON / "slots/heft__method/worker/raw_result.json"
    sources[raw_heft.relative_to(ROOT).as_posix()] = digest(raw_heft)
    assert digest(raw_heft) == heft["raw_sha256"]
    worker = next(row for row in batch["methods"] if row["job"] == "heft")["worker"]
    assert worker["safe"]["candidate"] == heft["final_candidate"]
    assert worker["safe"]["U_J"] == heft["final_energy_J"]
    assert heft["rankable"] and heft["post_state"] == "SAFE"
    heft_ids = {}
    for scene, rows in heft["final_candidate"]["scenes"].items():
        one = {"scenes": {scene: rows}}
        key = sha256(canonical(one).encode()).hexdigest()
        assert key in records
        assert next(t for t in rows if t["stage_id"].endswith("::A.main"))["unit"] == "CPU1"
        heft_ids[scene] = key
    heft_archived_enclosure = weighted({s: tuple(map(Q, records[k]["energy_J"])) for s, k in heft_ids.items()}, weights)
    heft_enclosure = tuple(map(Q, heft["weighted_energy_interval_J"]))
    assert max(heft_archived_enclosure[0], heft_enclosure[0]) <= min(heft_archived_enclosure[1], heft_enclosure[1])
    assert heft_enclosure[1] == Q(heft["final_energy_J"])
    gap_fixed = subtract(conditioned["CPU1"], opened)
    gap_heft_conditioned = subtract(heft_enclosure, conditioned["CPU1"])
    gap_heft_open = subtract(heft_enclosure, opened)
    components = {}
    for unit in ("CPU1", "NPU0"):
        names = raw_scenes[witnesses[next(iter(weights)), unit]["id"]]["energy_components_J"].keys()
        components[unit] = {name: interval(*weighted({s: tuple(map(Q, raw_scenes[witnesses[s, unit]["id"]]["energy_components_J"][name])) for s in weights}, weights)) for name in names}

    return {
        "schema": "k194-condition-optima-readonly-v1",
        "state": "SAVED_RECORDS_VERIFIED",
        "scope": "K.194 restricted device/mode/start domain only; not the natural full-choice-domain instance",
        "source_sha256": sources,
        "input_identity": {"input_sha256": declaration["input_sha256"], "config_sha256": declaration["config_sha256"],
                           "HEFT_matches_exact_input_and_config": True, "scene_weights": {s: str(w) for s, w in weights.items()},
                           "window_ms": instance["window_ms"], "settings": instance["settings"]},
        "coverage": {"saved_scene_schedules": len(manifest), "hashed_raw_receipts": len(finished),
                     "all_SAFE": True, "all_cross_scene_shared_mappings_except_A.main_fixed": True,
                     "devices_seen_by_stage": {s: sorted(units) for s, units in mappings.items()},
                     "complete_shared_arrangements": counts["global_legal_complete_arrangements"],
                     "complete_independent_arrangements": 1100 * 450,
                     "largest_saved_scene_energy_interval_width_J": str(largest_saved_width),
                     "coverage_basis": "Original frozen manifest, protocol counts and complete receipts; no new generation or legality/thermal execution"},
        "scene_conditional_optima": group_results,
        "shared_conditioned_optima": {u: interval(*v) for u, v in conditioned.items()},
        "open_shared_optimum": interval(*opened),
        "independent_scene_deployment_optimum": interval(*independent),
        "shared_deployment_cost": {"exact_J": "0", "proof": "Each scene's NPU0 upper bound is strictly below its CPU1 lower bound; the other cross-scene shared stages A.pre/A.post have fixed devices. B.main remains free within AB and has no cross-scene coupling. Both independent scene minima therefore lie in the same compatible NPU0 domain."},
        "CPU1_fixing_penalty_J": interval(*gap_fixed),
        "CPU1_fixing_penalty_percent_of_open": percent(gap_fixed, opened),
        "opening_CPU1_choice_saving_percent_of_CPU1": percent(gap_fixed, conditioned["CPU1"]),
        "HEFT": {"A.main_unit": "CPU1", "saved_scene_candidate_ids": heft_ids,
                 "energy": interval(*heft_enclosure),
                 "same_schedule_K194_energy": interval(*heft_archived_enclosure),
                 "independent_evaluation_intervals_overlap": True,
                 "gap_to_CPU1_conditional_optimum_J": interval(*gap_heft_conditioned),
                 "gap_to_CPU1_conditional_optimum_percent": percent(gap_heft_conditioned, conditioned["CPU1"]),
                 "gap_to_open_optimum_J": interval(*gap_heft_open),
                 "fraction_of_HEFT_open_gap_due_to_CPU1_condition_percent": percent(gap_fixed, gap_heft_open)},
        "conditional_witness_weighted_energy_components": components,
        "interpretation": ["Fixing CPU1 makes the NPU0 subdomain inaccessible; optimizing all remaining archived choices cannot close that gap.",
                           "HEFT is already near the CPU1-conditioned optimum; this instance's major HEFT gap is deployment choice, not lack of timing refinement within CPU1.",
                           "The NPU0 witness jointly changes working points and timing; no single-factor causal attribution to timing alone.",
                           "This instance supports keeping deployment open, but does not demonstrate a penalty from enforcing shared deployment.",
                           "Finite-domain optimum values are enclosed, not exact real-number values; no uniqueness claim or full-domain/global-method superiority."],
        "new_optimization_calls": 0, "new_enumeration_calls": 0, "new_thermal_calls": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = analyze()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"state": result["state"], "output": str(args.out),
                      "CPU1": result["shared_conditioned_optima"]["CPU1"]["decimal_J"],
                      "open": result["open_shared_optimum"]["decimal_J"],
                      "new_scientific_calls": 0}, ensure_ascii=False))
