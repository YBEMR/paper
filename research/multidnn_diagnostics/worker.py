"""One cold diagnostic process; the parent clock includes imports and initialization."""
import hashlib
import json
import os
from pathlib import Path
import sys
from time import perf_counter as clock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = Path(sys.argv[1])
START = float(os.environ["DIAGNOSTIC_START"])
LIMIT = START + 119.75
LOG = (OUT / "events.jsonl").open("x", encoding="utf-8", newline="\n")
COUNTS, TIMES = {}, {}
PHASE = "initialization"
CERT = None


class Budget(Exception):
    pass


def check():
    if clock() >= LIMIT:
        raise Budget("admission cutoff; hard wall budget is 120 seconds")


def bump(data, key, value=1):
    data[key] = data.get(key, 0) + value


def emit(kind, **data):
    LOG.write(json.dumps(dict(t_s=clock()-START, kind=kind, data=data,
                             calls=COUNTS, timings=TIMES), allow_nan=False) + "\n")
    LOG.flush()


def read(path):
    return json.loads(path.read_bytes())


def main():
    global PHASE, CERT
    job = read(OUT / "job.json")
    cfg = read(HERE / "protocol.json")
    # Manifest is created once at execution freeze, including new adapter files.
    for relative, expected in read(HERE / "execution_manifest.json").items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("Execution freeze drift: " + relative)
    from instance import Instance, events
    from adapter import load_m2
    instance = Instance(job["case_id"])
    source_sha = read(ROOT / "research/multidnn_model_review/frozen_sources.json")["sha256"][
        "research/kim_multidnn_search_trial/solver.py"]
    m, source, patches = load_m2(instance, source_sha)
    t = clock()
    builder_context = hashlib.sha256(source.encode() + instance.identity.encode()).hexdigest()
    emit("identity", case=instance.case, instance_sha=instance.identity,
         m2_source_sha=source_sha, bound_source_sha=hashlib.sha256(source.encode()).hexdigest(),
         runtime_bindings=patches, cache_scope=builder_context,
         deployments=instance.order, opps=list(m.OPPS), setfreq_calls=0,
         initialization_s=t-START)
    TIMES["initialization_s"] = t - START
    COUNTS["setfreq"] = 0

    old_schedule, old_compile = events.time_scene, m.thermal.compile_scene
    old_kernel_physics, old_final_physics = m.thermal.evaluate_thermal, events.evaluate_thermal
    old_replay = events.replay_sequence

    def schedule(platform, scene, deployment, opp):
        check()
        start = clock()
        result = old_schedule(platform, scene, deployment, opp)
        elapsed = clock() - start
        bump(TIMES, "event_schedule_s", elapsed)
        bump(COUNTS, "event_schedule")
        # Explicit completed-request deadline screen, not a per-frame proxy.
        start = clock()
        jobs = {q.id:q for q in scene.requests}
        if set(result.completions_ns) != set(jobs):
            raise AssertionError("Incomplete scheduled request set")
        late = [k for k,v in result.completions_ns.items() if v > jobs[k].deadline_ns]
        if bool(late) == result.deadline_feasible:
            raise AssertionError("Deadline screen disagrees with frozen evaluator")
        bump(TIMES, "deadline_audit_s", clock()-start)
        bump(COUNTS, "deadline_screen")
        emit("schedule", deployment=deployment, scene_index=scene.index, scene=scene.name,
             opp=opp, required=len(jobs), deadline_ok=result.deadline_feasible,
             late=len(late), slack_ns=result.min_slack_ns, schedule_s=elapsed,
             purpose="certificate" if CERT is not None else "kernel")
        if CERT is not None:
            CERT["ledger"].extend([
                [q.id, q.app, scene.index, q.release_ns+scene.start_ns,
                 q.deadline_ns+scene.start_ns, result.completions_ns[q.id]+scene.start_ns]
                for q in scene.requests])
        check()
        return result

    def kernel_physics(*args, **kwargs):
        check()
        label = "compile" if PHASE == "compile" else "fallback"
        start = clock()
        result = old_kernel_physics(*args, **kwargs)
        bump(TIMES, label+"_thermal_s", clock()-start)
        bump(COUNTS, label+"_thermal")
        check()
        return result

    def compile_kernel(*args, **kwargs):
        global PHASE
        check()
        previous, PHASE = PHASE, "compile"
        start = clock()
        try:
            return old_compile(*args, **kwargs)
        finally:
            bump(TIMES, "compile_inclusive_s", clock()-start)
            bump(COUNTS, "compile")
            PHASE = previous

    def final_physics(*args, **kwargs):
        check()
        start = clock()
        result = old_final_physics(*args, **kwargs)
        bump(TIMES, "certificate_thermal_s", clock()-start)
        bump(COUNTS, "certificate_thermal")
        if CERT is not None:
            CERT["energy_components"].append({k: result[k] for k in
                ("energy_J","common_J","transfer_J","idle_J","activity_J","leakage_J")})
        check()
        return result

    def certified_replay(platform, scenes, deployment, opps, ambient, **kwargs):
        global CERT
        check()
        start = clock()
        CERT = dict(ledger=[], energy_components=[])
        try:
            result = old_replay(platform, scenes, deployment, opps, ambient, **kwargs)
            if result["fully_replayed"]:
                rows = CERT["ledger"]
                if len(rows) != instance.required or len({r[0] for r in rows}) != instance.required:
                    raise AssertionError("Invalid full ledger")
                if any(r[5] > r[4] for r in rows):
                    raise AssertionError("Deadline miss in claimed full certificate")
                if result["scene_rows"][0]["entry_c"] != instance.initial:
                    raise AssertionError("Wrong inlet")
                for left, right in zip(result["scene_rows"], result["scene_rows"][1:]):
                    if left["final_c"] != right["entry_c"]:
                        raise AssertionError("Thermal reset")
                component_j = sum(x["common_J"]+x["transfer_J"]+sum(x["idle_J"])
                                  +sum(x["activity_J"])+sum(x["leakage_J"])
                                  for x in CERT["energy_components"])
                if abs(component_j-result["energy_j"]) > 1e-7:
                    raise AssertionError("Energy component mismatch")
            bump(COUNTS, "full_certificate")
            bump(TIMES, "certificate_inclusive_s", clock()-start)
            check()
            emit("physical_certificate", deployment=deployment, opps=opps,
                 physical=result, ledger=CERT["ledger"],
                 energy_components=CERT["energy_components"])
            return result
        finally:
            CERT = None

    events.time_scene, events.replay_sequence = schedule, certified_replay
    events.evaluate_thermal = final_physics
    m.thermal.compile_scene, m.thermal.evaluate_thermal = compile_kernel, kernel_physics
    original_screen = m.thermal._screen

    def screen(*args):
        check()
        start = clock()
        result = original_screen(*args)
        bump(TIMES, "peak_screen_s", clock()-start)
        bump(COUNTS, "peak_screen_batches")
        bump(COUNTS, "peak_screen_entries", len(result))
        check()
        return result
    m.thermal._screen = screen

    def report(kind, **data):
        check()
        emit(kind, **data)

    trial = m.Trial(dict(id=job["case_id"], ambient=instance.ambient), "M2",
                    instance.order, builder_context, OUT, report)
    trial.archive = {}  # No historical candidate arrays enter new optimization.
    trial.run()
    check()
    emit("finished", reason="algorithm_completed")


if __name__ == "__main__":
    try:
        main()
    except Budget as exc:
        emit("stopped", reason="TIMEOUT", detail=str(exc))
    except BaseException as exc:
        emit("error", type=type(exc).__name__, detail=str(exc))
        raise
    finally:
        LOG.close()
