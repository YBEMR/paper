"""Materialize predeclared diagnostic inputs. Never schedule, optimize or integrate heat."""
from collections import Counter
from hashlib import sha256
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def packed(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def build_stream(cfg, load, order):
    spec, offset, rows, scenes = cfg["loads"][load], 0, [], []
    canonical_starts, frame_offset = {}, 0
    for name, frames in cfg["scene_frames"].items():
        canonical_starts[name] = frame_offset
        frame_offset += frames
    for name in cfg["orders"][order]:
        end = offset + cfg["scene_frames"][name] * cfg["release_lattice_ns"]
        scenes.append(dict(name=name, start_ns=offset, service_end_ns=end,
                           end_ns=end + (cfg["tail_ns"] if end == cfg["service_ns"] else 0),
                           active=spec["active"][name]))
        for app in spec["active"][name]:
            period, deadline = spec["period_ns"][app], spec["deadline_ns"][app]
            if not 0 < deadline <= period:
                raise ValueError("Invalid declared period/deadline")
            for release in range(offset, end, period):
                due = release + deadline
                if due > end:
                    raise ValueError("Scene-crossing deadline: do not clip or discard")
                # Legacy-compatible identifiers on the retained 40 ms release grid.
                local_frame, residual = divmod(release - offset, cfg["release_lattice_ns"])
                frame = canonical_starts[name] + local_frame
                if residual:
                    raise ValueError("Phase-1 stream leaves its declared release lattice")
                rows.append([f"f{frame:04d}-a{app}", app, release, due])
        offset = end
    rows.sort(key=lambda q: (q[2], q[1], q[0]))
    if offset != cfg["service_ns"]:
        raise ValueError("Incorrect service duration")
    return dict(schema="periodic-scene-stream/v1", load=load, order=order,
                scenes=scenes, required=len(rows),
                counts=[Counter(q[1] for q in rows)[a] for a in range(4)],
                request_sha256=sha256(packed(rows)).hexdigest(), requests=rows)


def main():
    cfg = json.loads((HERE / "protocol.json").read_bytes())
    cat = json.loads((ROOT / cfg["domain"]["source_catalog"]).read_bytes())
    frozen = json.loads((ROOT / cfg["domain"]["source_deployments"]).read_bytes())
    domain = dict(search_order=cat["search_order"],
                  deployments={d: frozen["deployments"][d] for d in cat["search_order"]},
                  frequency_mhz=frozen["frequency_mhz"],
                  clock_policy=frozen["clock_policy"],
                  certificate_scope=cfg["domain"]["policy"])
    write(HERE / "inputs/domain81.json", domain)
    source = ROOT / cfg["preheat"]["source_path"]
    archived = json.loads(source.read_bytes())["independent"]
    p = archived["physical"]
    if archived["opps"] != cfg["preheat"]["opps"] or not (
        p["thermal_status"] == "SAFE" and p["fully_replayed"] and p["deadline_ok"]
        and p["required"] == p["completed"] == 500
        and p["scene_rows"][-1]["end_ns"] == cfg["preheat"]["duration_ns"]
        and p["scene_rows"][0]["entry_c"] == cfg["preheat"]["initial_c"]
    ):
        raise ValueError("Archived preheat does not match the frozen recipe")
    state = dict(recipe=cfg["preheat"], source_sha256=digest(source),
                 node_order=["CPU", "GPU", "DLA0", "DLA1"],
                 initial_c=p["final_c"], energy_j=p["energy_j"],
                 peak_upper_c=p["peak_upper_c"], deadline_slack_ms=p["min_slack_ms"],
                 evidence="ARCHIVED_SYNTHETIC_REPLAY_NOT_HARDWARE_OR_NEW_RUN")
    write(HERE / "inputs/preheat_state.json", state)
    summaries = []
    for load in cfg["loads"]:
        for order in cfg["orders"]:
            stream = build_stream(cfg, load, order)
            stream_path = HERE / f"inputs/streams/{load}_{order}.json"
            write(stream_path, stream)
            for mode in ("reference_start", "preheated"):
                case_id = f"{load}_{order}_{mode}"
                case = dict(case_id=case_id, load=load, order=order, thermal_start=mode,
                            ambient_c=cfg["ambient_c"],
                            initial_c=cfg["reference_initial_c"] if mode == "reference_start" else state["initial_c"],
                            input_stream=str(stream_path.relative_to(HERE)).replace("\\", "/"),
                            stream_file_sha256=digest(stream_path),
                            required=stream["required"], counts=stream["counts"],
                            domain="inputs/domain81.json", domain_sha256=digest(HERE / "inputs/domain81.json"),
                            objective_window_ns=cfg["service_ns"] + cfg["tail_ns"],
                            preheat_state="inputs/preheat_state.json" if mode == "preheated" else None,
                            status="FROZEN_INPUT_ONLY_NOT_EXECUTED")
                write(HERE / f"inputs/cases/{case_id}.json", case)
                summaries.append(dict(case_id=case_id, load=load, order=order, thermal_start=mode,
                                      requests=stream["required"], counts="/".join(map(str, stream["counts"])),
                                      ambient_c=cfg["ambient_c"], initial_c="/".join(map(str, case["initial_c"])),
                                      deployment_count=81, status=case["status"]))
    with (HERE / "cases.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summaries[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(summaries)
    manifest = {p.relative_to(HERE).as_posix(): digest(p)
                for p in sorted((HERE / "inputs").rglob("*.json"))}
    manifest["protocol.json"] = digest(HERE / "protocol.json")
    manifest["cases.csv"] = digest(HERE / "cases.csv")
    write(HERE / "input_manifest.json", manifest)
    print(f"Frozen {len(summaries)} cases, 6 streams; no scheduling/thermal/search calls.")


if __name__ == "__main__":
    main()
