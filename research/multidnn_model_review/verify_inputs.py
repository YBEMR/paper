"""Independent admission checks only: no optimization or thermal integrations."""
from bisect import bisect_right
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def read(path):
    return json.loads(path.read_bytes())


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return sha256(path.read_bytes()).hexdigest()


def verify_rows(stream, cfg):
    spec = cfg["loads"][stream["load"]]
    names = cfg["orders"][stream["order"]]
    starts, end = [], 0
    canonical_starts, frame_offset = {}, 0
    for name, frames in cfg["scene_frames"].items():
        canonical_starts[name] = frame_offset
        frame_offset += frames
    for name in names:
        starts.append(end)
        end += cfg["scene_frames"][name] * cfg["release_lattice_ns"]
    require(end == cfg["service_ns"], "service window")
    counts, seen, arrivals = Counter(), set(), {}
    for ident, app, release, due in stream["requests"]:
        require(all(type(v) is int for v in (app, release, due)), "integer ns")
        require(0 <= app < 4 and 0 <= release < end and ident not in seen, "ID/range")
        seen.add(ident)
        scene = bisect_right(starts, release) - 1
        name = names[scene]
        stop = starts[scene + 1] if scene + 1 < len(starts) else end
        require(app in spec["active"][name], "inactive app")
        require((release - starts[scene]) % spec["period_ns"][app] == 0, "period/phase")
        require(due == release + spec["deadline_ns"][app] and release < due <= stop,
                "declared deadline / scene boundary")
        stable_frame = canonical_starts[name] + (release - starts[scene]) // cfg["release_lattice_ns"]
        require(ident == f"f{stable_frame:04d}-a{app}"
                and release % cfg["release_lattice_ns"] == 0, "legacy ID")
        counts[app] += 1
        arrivals.setdefault((scene, app), []).append(release)
    for scene, name in enumerate(names):
        stop = starts[scene + 1] if scene + 1 < len(starts) else end
        for app in spec["active"][name]:
            n = (stop - starts[scene] + spec["period_ns"][app] - 1) // spec["period_ns"][app]
            a = arrivals[scene, app]
            require(len(a) == n and a[0] == starts[scene], "missing/extra release")
            require(all(y - x == spec["period_ns"][app] for x, y in zip(a, a[1:])),
                    "nonperiodic stream")
    require([counts[a] for a in range(4)] == spec["expected_counts"] == stream["counts"],
            "declared per-app counts")
    require(sum(counts.values()) == stream["required"], "required count")
    rows = stream["requests"]
    require(rows == sorted(rows, key=lambda q: (q[2], q[1], q[0])), "request order")
    request_sha = sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()
    require(request_sha == stream["request_sha256"], "request digest")
    for j, s in enumerate(stream["scenes"]):
        stop = starts[j + 1] if j + 1 < len(starts) else end
        require(s == dict(name=names[j], start_ns=starts[j], service_end_ns=stop,
                          end_ns=stop + (cfg["tail_ns"] if j == len(starts)-1 else 0),
                          active=spec["active"][names[j]]), "scene specification")
    return starts


def main():
    cfg = read(HERE / "protocol.json")
    manifests = read(HERE / "input_manifest.json")
    for name, expected in manifests.items():
        require(sha(HERE / name) == expected, f"input drift: {name}")
    guard = read(HERE / "frozen_sources.json")
    for name, expected in guard["sha256"].items():
        require(sha(ROOT / name) == expected, f"frozen source drift: {name}")
    domain = read(HERE / "inputs/domain81.json")
    catalog = read(ROOT / cfg["domain"]["source_catalog"])
    original = read(ROOT / cfg["domain"]["source_deployments"])
    require(len(domain["search_order"]) == len(set(domain["search_order"])) == 81, "domain size")
    require(domain["search_order"] == catalog["search_order"], "domain order")
    require(domain["deployments"] == {k: original["deployments"][k] for k in domain["search_order"]},
            "physical binding altered")
    require(domain["clock_policy"] == original["clock_policy"] and
            domain["frequency_mhz"] == original["frequency_mhz"], "frequency set drift")
    state = read(HERE / "inputs/preheat_state.json")
    prior = read(ROOT / cfg["preheat"]["source_path"])["independent"]["physical"]
    require(state["recipe"] == cfg["preheat"] and state["initial_c"] == prior["final_c"]
            and state["source_sha256"] == sha(ROOT / cfg["preheat"]["source_path"]),
            "preheat provenance")
    require(prior["thermal_status"] == "SAFE" and prior["deadline_ok"] and prior["fully_replayed"]
            and prior["completed"] == prior["required"] == 500, "preheat certification")
    require(max(prior["peak_upper_c"]) <= 80 and min(state["initial_c"]) >= 25,
            "preheat thermal domain")
    for before, after in zip(prior["scene_rows"], prior["scene_rows"][1:]):
        require(before["final_c"] == after["entry_c"], "preheat continuity")

    # Invoke the original partitioner, not the physical evaluator. It rejects
    # crossing deadlines and preserves every absolute release and due time.
    sys.path.insert(0, str(ROOT / "research/kim_scene_dvfs_admission"))
    import scene_events as events
    # A stray optimizer import or eager call would make this audit fail.
    def forbidden(*args, **kwargs):
        raise RuntimeError("Physical evaluation is outside this input-review task")
    events.simulate = forbidden
    events.evaluate_thermal = forbidden
    streams = {}
    for path in sorted((HERE / "inputs/streams").glob("*.json")):
        stream = read(path)
        starts = verify_rows(stream, cfg)
        switches = list(zip(starts, cfg["orders"][stream["order"]]))
        scenes = events.partition_requests([events.Request(*q) for q in stream["requests"]],
                                           switches, cfg["service_ns"] + cfg["tail_ns"],
                                           cfg["service_ns"])
        recovered = [[q.id, q.app, q.release_ns + s.start_ns, q.deadline_ns + s.start_ns]
                     for s in scenes for q in s.requests]
        require(recovered == stream["requests"], "original partitioner changed requests")
        require([(s.start_ns, s.service_end_ns, s.end_ns) for s in scenes] ==
                [(s["start_ns"], s["service_end_ns"], s["end_ns"]) for s in stream["scenes"]],
                "original partitioner changed windows")
        streams[stream["load"], stream["order"]] = stream

    historical_sha = read(ROOT / "research/ch3_algorithm_selection/config.json")["original_sha"]
    require(streams["balanced", "forward"]["request_sha256"] == historical_sha,
            "balanced forward differs from historical 500-request input")
    sys.path.insert(0, str(ROOT / "research/kim_safety_repair_audit"))
    import design
    for old in design.cases():
        if old["dwell_id"] == "flat" and old["ambient"] == 25:
            old_scenes = design.make_scenes(old)
            old_rows = [[q.id, q.app, q.release_ns + s.start_ns, q.deadline_ns + s.start_ns]
                        for s in old_scenes for q in s.requests]
            require(old_rows == streams["balanced", old["order_id"]]["requests"],
                    "balanced differs from historical order input")
    cases = [read(p) for p in sorted((HERE / "inputs/cases").glob("*.json"))]
    required_cases = {(a, b, c) for a in cfg["loads"] for b in cfg["orders"]
                      for c in ("reference_start", "preheated")}
    require(len(cases) == 12 and {(c["load"], c["order"], c["thermal_start"]) for c in cases}
            == required_cases, "12-case factorial coverage")
    for c in cases:
        s = streams[c["load"], c["order"]]
        require(c["stream_file_sha256"] == sha(HERE / c["input_stream"])
                and read(HERE / c["input_stream"]) == s, "case/stream binding")
        require(c["required"] == s["required"] and c["counts"] == s["counts"], "case counts")
        require(c["domain_sha256"] == sha(HERE / c["domain"]), "case domain")
        expected = cfg["reference_initial_c"] if c["thermal_start"] == "reference_start" else state["initial_c"]
        require(c["initial_c"] == expected and c["ambient_c"] == cfg["ambient_c"],
                "case initial/ambient state")
        require(c["objective_window_ns"] == 10_040_000_000 and
                c["status"] == "FROZEN_INPUT_ONLY_NOT_EXECUTED", "case scope")

    # Two focused negative checks protect against the former fixed-count shortcut.
    import copy
    rejected = []
    for mutation in ("delete_request", "cross_scene_deadline"):
        bad = copy.deepcopy(streams["asymmetric", "forward"])
        if mutation == "delete_request":
            bad["requests"].pop()
        else:
            bad["requests"][0][3] = cfg["service_ns"] + 1
        try:
            verify_rows(bad, cfg)
        except (ValueError, KeyError):
            rejected.append(mutation)
        else:
            raise ValueError(f"Accepted malformed stream: {mutation}")
    result = dict(status="PASS_INPUT_AND_STATIC_REVIEW_ONLY", cases=12, streams=6,
                  requests_per_load={k: sum(v["expected_counts"]) for k, v in cfg["loads"].items()},
                  historical_balanced_forward_sha256=historical_sha,
                  original_partitioner_roundtrips=6, malformed_streams_rejected=rejected,
                  historical_order_streams_matched=["forward_flat_25C", "reverse_flat_25C"],
                  protected_source_files=len(guard["sha256"]),
                  preheated_dla_exchange_symmetry=False,
                  simulation_calls=0, thermal_integration_calls=0, optimization_calls=0,
                  deadline_feasibility="NOT_EVALUATED", safe_optimality="NOT_EVALUATED")
    (HERE / "validation.json").write_bytes((json.dumps(result, indent=2) + "\n").encode("utf-8"))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
