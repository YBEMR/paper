"""Materialize the preregistered cases and replay all returned schedules."""
import argparse
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from physics import compile_template
from solvers import Action, solve_a, solve_b, solve_d
from workload import (BASE, CONFIGS, LIMIT, NODES, PLATFORM, SPEC, cases, scenes,
                      schedule, tail_segments)


def write_json(path, obj):
    path.parent.mkdir(exist_ok=True, parents=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(",", ":")),
                    encoding="utf-8")


@lru_cache(maxsize=2)
def prepare(load, seed):
    started = perf_counter()
    scene_inputs = scenes(load, seed)
    templates = {}
    schedules = {}
    tail = tail_segments()
    nominal = np.full(len(NODES), SPEC["nominal_degC"])
    for sid, scene in scene_inputs.items():
        for cfg in CONFIGS:
            sched = schedule(scene, cfg)
            schedules[sid, cfg] = sched
            t = compile_template(PLATFORM, sched["segments"]) if sched["legal"] else None
            score = float(t.w @ nominal + t.e) if t else None
            templates[sid, cfg, False] = Action(t, sched["legal"], score)
            end = compile_template(PLATFORM, sched["segments"] + tail) if t else None
            templates[sid, cfg, True] = Action(end, sched["legal"], score)
    return scene_inputs, templates, schedules, perf_counter() - started


def layer_list(templates, seq):
    return [{cfg: templates[sid, cfg, i+1==len(seq)] for cfg in CONFIGS}
            for i, sid in enumerate(seq)]


def replay(method, case, layers, inputs, schedules):
    entry = case["initial"]
    stages, diagnostic = [], []
    nominal = np.full(len(entry), SPEC["nominal_degC"])
    total = 0.
    for i, (sid, layer) in enumerate(zip(case["sequence"], layers)):
        candidates = []
        for cfg, action in layer.items():
            item = {"cfg": cfg, "deadline_ok": action.deadline_ok,
                    "reason": schedules[sid, cfg]["reason"]}
            if action.deadline_ok:
                t = action.thermal
                test = t.step(entry, LIMIT)
                item.update(safe=test["safe"], energy_J=test["energy_J"],
                            nominal_energy_J=float(t.w @ nominal + t.e),
                            kim_score_J=action.nominal_energy, after_T=test["final_T"],
                            peak_upper=test["peak_upper"])
            candidates.append(item)
        diagnostic.append(candidates)
        if i >= len(method["path"]):
            break
        cfg = method["path"][i]
        result = layer[cfg].thermal.step(entry, LIMIT, detail=True)
        sched = schedules[sid, cfg]
        assert sched["legal"]
        if method["feasible"]:
            assert result["safe"]
        total += result["energy_J"]
        assert abs(sum(s["energy_J"] for s in result["trace"]) - result["energy_J"]) < 1e-8
        stages.append(dict(scene=sid, index=i, time_offset_ms=i*inputs[sid]["duration_ms"],
                           cfg=cfg, entry=entry, completions=sched["completions"],
                           rows=sched["rows"], **result))
        entry = result["final_T"]
    if method["feasible"]:
        assert len(stages) == len(layers) and abs(total-method["energy_J"]) < 1e-8
    method.update(stages=stages, diagnostic=diagnostic)


def run(out):
    # The gate records the exact source hashes that passed the checks.
    gate = json.loads((out.parent/"checks.json").read_text(encoding="utf-8"))
    for name, digest in gate["sha256"].items():
        if hashlib.sha256((BASE/name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Frozen source changed after correctness checks: {name}")
    if not gate["passed"]:
        raise ValueError("Correctness checks did not pass")
    out.mkdir(exist_ok=False, parents=True)
    batch = sorted(cases(), key=lambda c: (c["load"],c["seed"],c["order"],c["state"]))
    for case in batch:
        data, templates, schedules, prep_time = prepare(case["load"], case["seed"])
        seq = case["sequence"]
        layers = layer_list(templates, seq)
        entry = case["initial"]
        methods = {
            "A": solve_a(layers, entry, LIMIT, [SPEC["nominal_degC"]]*len(NODES)),
            "B": solve_b(layers, entry, LIMIT),
            "D": solve_d(layers, entry, LIMIT, max_visits=100000, time_limit_s=60.0)
        }
        start = perf_counter()
        for method in methods.values():
            replay(method, case, layers, data, schedules)
        record = dict(case=case, inputs=data, methods=methods, limits_degC=LIMIT,
                      nodes=NODES, times={"shared_group_preparation_s":prep_time,
                                          "output_replay_s":perf_counter()-start})
        write_json(out/(case["id"]+".json"), record)
        print(case["id"], {k:v["status"] for k,v in methods.items()}, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path, help="New raw output directory; sibling checks.json required")
    run(parser.parse_args().output)

