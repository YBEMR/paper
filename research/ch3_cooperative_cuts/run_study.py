"""Run or resume the fixed comparison. Each slot owns a process, wall clock, log and receipt."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import gzip
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
from time import perf_counter
import traceback


HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE / "study_config.json").read_bytes())
RUNS = HERE / "units"
BASELINES = ("Kim-Adapt+SAFE", "Thermal-GA")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encode(data):
    return json.dumps(data, separators=(",", ":"), allow_nan=False, ensure_ascii=False)


def write(path, data):
    tmp = path.with_name(path.name + ".partial")
    if path.suffix == ".gz":
        with gzip.open(tmp, "wt", encoding="utf8", compresslevel=4) as stream:
            stream.write(encode(data) + "\n")
    else:
        tmp.write_text(encode(data) + "\n", encoding="utf8")
    os.replace(tmp, path)


def files_for(method):
    return ["study_config.json", "catalog_manifest.json", "run_study.py", "physical.py", "catalog_ext.py",
            "baselines.py" if method in BASELINES else "cooperative.py"]


def jobs():
    return [(case + "_" + temp, scope, method, seed)
            for case in CONFIG["cases"] for temp in CONFIG["ambient_suffixes"]
            for seed in CONFIG["seeds"] for scope, method in CONFIG["methods"]]


def directory(job):
    case, scope, method, seed = job
    return RUNS / case / (scope + "_" + method + "_" + str(seed))


class Observations:
    def __init__(self, evaluator, clock, emit, rank):
        self.ev, self.clock, self.emit, self.rank = evaluator, clock, emit, rank
        self.best_failure = None
        self.first_safe_s = None
        self.seen = {}

    def __getattr__(self, name):
        return getattr(self.ev, name)

    def replay(self, dep, opps):
        key = (dep, *opps)
        result = self.ev.replay(dep, opps)
        self.clock.check()
        if key not in self.seen:
            self.seen[key] = result
            self.emit("replay", [key, result.status, result.energy_j, result.slack_ms,
                                 result.completed, result.lower, result.upper, len(result.late_ids)])
            if result.status == "SAFE":
                if self.first_safe_s is None:
                    self.first_safe_s = self.clock.elapsed()
            elif self.best_failure is None or self.rank((key, result)) < self.rank(
                    (self.best_failure, self.seen[self.best_failure])):
                self.best_failure = key
        return result


def worker(root, index, core, start):
    import psutil
    psutil.Process().cpu_affinity([core])
    job = jobs()[index]
    case, scope, method, seed = job
    folder = directory(job)
    sys.path.insert(0, str(root / "research/ch3_final_experiments/p2"))
    import search
    from catalog_ext import make_domain
    from physical import Physical
    clock = search.Clock(start, start + CONFIG["accept_cutoff_s"])
    domain = make_domain(root, scope)
    if len(domain.order) != CONFIG["raw_deployments"][scope]:
        raise ValueError("Domain count changed")
    physical = Physical(root, case, domain.stages)
    anchors = ["A", "C"] + random.Random(seed).sample([d for d in domain.legacy_ids if d not in ("A", "C")], 6)
    with gzip.open(folder / "events.jsonl.gz", "wt", encoding="utf8", compresslevel=1) as log:
        def emit(kind, value):
            log.write(encode([round(perf_counter()-start, 6), kind, value]) + "\n")
        ev = Observations(physical, clock, emit, search.thermal_rank)
        emit("identity", dict(job=job, initial=anchors, domain=len(domain.order),
                              request_sha256=physical.identity, init_s=clock.elapsed()))
        if method == "Kim-Adapt+SAFE":
            from baselines import kim_safe
            generation = search.Clock(start, start + CONFIG["kim_generation_cutoff_s"])
            summary = kim_safe(ev, domain, seed, anchors, generation, clock, emit)
        elif method == "Thermal-GA":
            from baselines import thermal_ga
            summary = thermal_ga(ev, domain, seed, anchors, clock, emit)
        else:
            import cooperative
            summary = cooperative.run(ev, domain, seed, clock, emit, variant=method, initial_deps=anchors)
        search_end = perf_counter() - start
        winner = summary.get("winner")
        winner = tuple(winner) if winner else None
        if winner and (winner not in ev.seen or ev.seen[winner].status != "SAFE"):
            raise ValueError("Winner is not an admitted continuous SAFE observation")
        if not winner and ev.first_safe_s is not None:
            raise ValueError("Method discarded all confirmed SAFE observations")
        key = winner or ev.best_failure
        proof = physical.evidence(key[0], key[1:]) if key else None
        if proof:
            write(folder / "selection.json.gz", proof)
        stats = Counter(entry.status for entry in ev.seen.values())
        data = dict(job=job, domain_count=len(domain.order), request_sha256=physical.identity,
                    init_deps=anchors, summary=summary, search_end_s=search_end,
                    first_observed_safe_s=ev.first_safe_s, safe=bool(winner),
                    selected_kind="safe_winner" if winner else "failed_diagnostic" if key else "no_observation",
                    selected_genome=key, selected=asdict(ev.seen[key]) if key else None,
                    unique_observations=dict(stats), physics_counters=dict(physical.counters))
        write(folder / "result.json.gz", data)


def slot(root, index, core, cache):
    job = jobs()[index]
    folder = directory(job)
    hashes = {name: sha(HERE / name) for name in files_for(job[2])}
    if (folder / "receipt.json").exists():
        receipt = json.loads((folder / "receipt.json").read_bytes())
        if receipt["inputs"] != hashes or receipt["job"] != list(job):
            raise ValueError("Existing slot input mismatch: " + str(folder))
        return
    folder.mkdir(parents=True, exist_ok=False)
    write(folder / "reservation.json", dict(job=job, core=core, inputs=hashes, cap_s=CONFIG["slot_wall_cap_s"]))
    env = {**os.environ, "NUMBA_CACHE_DIR": str(cache), "OPENBLAS_NUM_THREADS":"1", "MKL_NUM_THREADS":"1",
           "NUMBA_NUM_THREADS":"1", "OMP_NUM_THREADS":"1", "PYTHONDONTWRITEBYTECODE":"1"}
    start = perf_counter()
    with (folder / "console.txt").open("w", encoding="utf8") as console:
        proc = subprocess.Popen([sys.executable, "-B", "-X", "utf8", str(Path(__file__)),
                                 "--source-root", str(root), "--worker", str(index), str(core), str(start)],
                                env=env, stdout=console, stderr=console)
        try:
            proc.wait(timeout=max(0, CONFIG["slot_wall_cap_s"] - (perf_counter()-start)))
            state = "finished" if proc.returncode == 0 and (folder / "result.json.gz").exists() else "fault"
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            state = "hard_timeout"
    elapsed = perf_counter()-start
    outputs = {p.name: sha(p) for p in sorted(folder.iterdir())}
    write(folder / "receipt.json", dict(job=job, inputs=hashes, state=state, elapsed_s=elapsed,
                                        core=core, exitcode=proc.returncode, files=outputs))
    print(index, *job, state, round(elapsed, 2), flush=True)
    if state == "fault":
        raise RuntimeError((folder / "console.txt").read_text("utf8")[-2500:])


def batch(root, cores, cache, only):
    all_jobs = jobs()
    indices = [i for i, j in enumerate(all_jobs) if only == "all" or
               (j[2] in BASELINES) == (only == "baselines")]
    random.Random(231121).shuffle(indices)
    cache.mkdir(parents=True, exist_ok=True)
    def lane(core, queue):
        for i in queue:
            slot(root, i, core, cache)
    with ThreadPoolExecutor(len(cores)) as pool:
        running = [pool.submit(lane, core, indices[j::len(cores)]) for j, core in enumerate(cores)]
        for task in running:
            task.result()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--cores", default="0,2,4,6,8,10")
    parser.add_argument("--jit-cache", type=Path)
    parser.add_argument("--only", choices=["all","baselines","cooperative"], default="all")
    parser.add_argument("--worker", nargs=3)
    args = parser.parse_args()
    if args.worker:
        index, core, start = args.worker
        worker(args.source_root.resolve(), int(index), int(core), float(start))
    else:
        if args.jit_cache is None:
            parser.error("--jit-cache is required for the batch supervisor")
        batch(args.source_root.resolve(), list(map(int,args.cores.split(","))), args.jit_cache.resolve(), args.only)
