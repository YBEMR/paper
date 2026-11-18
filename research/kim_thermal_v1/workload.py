"""Frozen finite workload and deterministic nonpreemptive event dispatch (ms)."""
from fractions import Fraction
from itertools import product
from pathlib import Path
import hashlib
import json
import random
import sys

BASE = Path(__file__).resolve().parent
SPEC = json.loads((BASE / "inputs.json").read_text(encoding="utf-8-sig"))
UPSTREAM = (BASE / SPEC["source"]).resolve()
if hashlib.sha256(UPSTREAM.read_bytes()).hexdigest() != SPEC["source_sha256"]:
    raise ValueError("Unexpected upstream config bytes")
sys.path.append(str(UPSTREAM.parent))
from inputs import load_config, _expand_modes
from schedules import _power_segments

OLD = load_config(UPSTREAM)
PLATFORM = OLD["platform"]
NODES = PLATFORM["node_order"]
DOMAINS = SPEC["domains"]
UNITS = {unit["id"]: unit for unit in PLATFORM["units"]}
CONFIGS = tuple("".join(levels) for levels in product(SPEC["opp_levels"], repeat=3))
LIMIT = SPEC["limit_degC"]
TAIL_MS = SPEC["tail_ms"]
SAMPLE = next(s for s in OLD["samples"] if s["id"] == SPEC["duration_sample"])
_ALL_MODES, _ = _expand_modes(OLD, SAMPLE, {**OLD["defaults"], "response_variant": SPEC["response_variant"]})
MODES = {(stage, mode["opp_id"]): mode for stage, candidates in _ALL_MODES.items()
         for mode in candidates if SPEC["fixed_units"][stage] == mode["unit_id"]}
STAGES = ("pre", "main", "post")
CHAIN_MS = {app: sum(Fraction(s["profiles"]["CPU"]["d_ref_ms"]) for s in OLD["stage_catalog"]
                    if s["application"] == app) * Fraction(SAMPLE["duration_scale"][app])
            for app in ("A", "B", "C")}


def scenes(load, seed):
    """Same materialized requests across temperatures and both orderings."""
    if seed not in SPEC["seeds"]:
        raise ValueError("Unknown seed")
    scenarios = {}
    for scene_id, apps in SPEC["scenario_apps"].items():
        requests = []
        for copy, offset in enumerate(SPEC["load_releases_ms"][load]):
            for app in apps:
                key = f'{seed}/{scene_id}/{copy}/{app}'.encode("ascii")
                rng = random.Random(int.from_bytes(hashlib.sha256(key).digest(), "big"))
                release = offset + rng.randint(*SPEC["release_jitter_inclusive_ms"])
                deadline = release + SPEC["deadline_beta"] * CHAIN_MS[app]
                requests.append({"id": f"{scene_id}.{app}.{copy}", "app": app,
                                 "release_ms": release, "deadline_ms": int(deadline)})
        scenarios[scene_id] = {"id": scene_id, "duration_ms": SPEC["scene_duration_ms"],
                               "requests": requests}
    return scenarios


def cases():
    return [{"id": f"{load}_{state}_{seed}_{order}", "load": load, "seed": seed,
             "order": order, "state": state, "initial": [temp] * len(NODES), "sequence": list(seq)}
            for load in SPEC["load_releases_ms"] for state,temp in SPEC["initial_degC"].items()
            for seed in SPEC["seeds"] for order,seq in SPEC["orders"].items()]


def _intervals(rows, cfg, duration):
    # Enter the old hold-last waveform builder with the three domains already pinned.
    opp = dict(zip(DOMAINS, cfg))
    scene = {"id": "V1", "entry": {"unfinished_work": [], "domain_opp": opp,
                                    "temperature_degC": [SPEC["nominal_degC"]] * len(NODES)}}
    segments = _power_segments(PLATFORM, scene, rows, NODES, UNITS, PLATFORM["domains"],
                               Fraction(duration))
    for s in segments:
        s["opp"] = cfg
        s["activity_W"] = [float(Fraction(s["activity_by_node_W"][n])) for n in NODES]
        # Keep rational timing in native archive fields for the interval oracle.
    return segments


def tail_segments():
    return _intervals([], "LLL", TAIL_MS)


def schedule(scene, cfg):
    """Release and completion events, EDF, ties by request ID. All times exact."""
    result = {"legal": False, "reason": "", "rows": [], "completions": {}, "segments": []}
    if cfg not in CONFIGS:
        result["reason"] = "INVALID_CONFIG"
        return result
    requests = {r["id"]: r for r in scene["requests"]}
    if len(requests) != len(scene["requests"]):
        raise ValueError("Duplicate request ID")
    if any(r["app"] not in CHAIN_MS or not 0 <= r["release_ms"] <= r["deadline_ms"]
           for r in requests.values()) or scene["duration_ms"] <= 0:
        raise ValueError("Invalid scene input")

    opp = dict(zip(DOMAINS, cfg))
    next_stage = {rid: 0 for rid in requests}
    running = {}
    exact_completions = {}
    occupied = set()
    rows = []
    now = Fraction(0)
    while len(result["completions"]) < len(requests):
        for unit, (finish, rid) in list(running.items()):
            if finish == now:
                del running[unit]
                occupied.remove(rid)
                next_stage[rid] += 1
                if next_stage[rid] == len(STAGES):
                    exact_completions[rid] = now
                    result["completions"][rid] = float(now)
        for unit in NODES:
            if unit in running:
                continue
            eligible = []
            for rid, req in requests.items():
                pos = next_stage[rid]
                if pos == len(STAGES) or rid in occupied or req["release_ms"] > now:
                    continue
                stage = req["app"] + "." + STAGES[pos]
                if SPEC["fixed_units"][stage] == unit:
                    eligible.append((req["deadline_ms"], rid, stage))
            if not eligible:
                continue
            _, rid, stage = min(eligible)
            domain = UNITS[unit]["domain_id"]
            mode = MODES[stage, opp[domain]]
            finish = now + Fraction(mode["duration_ms"])
            rows.append({"request": rid, "stage": stage, "stage_id": rid + "." + stage,
                         "unit": unit, "thermal_node_id": unit, "domain_id": domain,
                         "opp": opp[domain], "start_ms": now, "end_ms": finish,
                         "activity_power_W": Fraction(mode["activity_power_W"])})
            running[unit] = (finish, rid)
            occupied.add(rid)
        events = [end for end,_ in running.values()]
        events += [r["release_ms"] for r in requests.values() if r["release_ms"] > now]
        if not events:
            if len(result["completions"]) != len(requests):
                raise RuntimeError("Incomplete schedule with no remaining event")
            break
        now = min(events)
    result["rows"] = [{"request": r["request"], "stage": r["stage"], "unit": r["unit"],
                       "start_ms": float(r["start_ms"]), "end_ms": float(r["end_ms"]),
                       "opp": r["opp"], "activity_W": float(r["activity_power_W"])} for r in rows]
    late = [rid for rid, end in exact_completions.items() if end > requests[rid]["deadline_ms"]]
    result["late_requests"] = late
    if any(r["end_ms"] > scene["duration_ms"] for r in rows):
        result["reason"] = "BOUNDARY_UNFINISHED"
        return result
    result["segments"] = _intervals(rows, cfg, scene["duration_ms"])
    result["legal"] = not late
    result["reason"] = "DEADLINE" if late else "OK"
    return result
