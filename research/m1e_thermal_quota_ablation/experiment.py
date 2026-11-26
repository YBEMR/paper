"""M1-e independent runs. Set M1E_OUTPUT to a fresh directory to reproduce."""
import csv
import gzip
import json
import os
import platform
import sys
from collections import Counter
from itertools import groupby
from pathlib import Path
from time import perf_counter as clock

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("M1E_OUTPUT", ROOT / "data")).resolve()
D = ROOT.parent / "m1d_thermal_safe_energy_selection"
os.environ["M1D_OUTPUT"] = str(DATA)
sys.path.insert(0, str(D))
from validation import case_for, reordered, sequences
from study import CASES, WINDOW, diverse, initial, np, p1, ranking
from common import anchors, capacity, digest, grouped_means, load_planes, window_types
from sampler import synthesize

METHODS = ("OC", "OT", "NC", "NT", "HC", "C2")
FIELDS = ("window", "parent", "g", "n", "x", "y", "config", "pilot", "original",
          "status", "energy", "peak", "risk", "drain", "slack")

def write_gz(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wb", compresslevel=6) as stream:
        stream.write(p1.raw(obj))

def expand(c, j, parents, method, start, deadline, log):
    gen = "O" if method == "C2" else method[0]
    rank_thermal = method[1] == "T"
    moments = method != "C2"
    lo = j * WINDOW
    final = j + 1 == c.windows
    right = c.p.horizon if final else lo + WINDOW
    types, a, b = window_types(c, j)
    pool = {}
    for parent in parents:
        for (g, n), group in groupby(c.candidates(j, parent), key=lambda item: item[0][:2]):
            if clock() >= deadline:
                return pool, False
            original = {tuple(action[2:]): ext for action, ext in group}
            load = load_planes(c, j, parent, g, n, a, b)
            pilots = []
            entries = {}

            def evaluate(xy):
                if xy not in entries:
                    ext = original.get(xy)
                    if ext is None:
                        ext = c.extension(types, a, b, g, n, *xy)
                    config = parent["config"] + ext
                    identity = digest(config)
                    grid = 500 if final and xy in pilots else 2500
                    ledger = None
                    if identity not in pool or xy in pilots:
                        ledger = c.ledger(config, lo, right, grid, final, moments)
                    entries[xy] = config, identity, grid, ledger
                return entries[xy]

            chosen = list(original)
            calibration = None
            if gen != "O":
                center = c.eng.quota(parent, j, (g, n), (a, b))
                pilots, balance = anchors(load, center, a, b)
                ledgers = [evaluate(xy)[3] for xy in pilots]
                energies = [v[1] for v in ledgers]
                cost = np.linalg.solve(np.column_stack((np.ones(3), pilots)), energies)
                fine = evaluate(pilots[0])[2]
                durations = np.minimum(fine, right-lo-np.arange(len(ledgers[0][8]))*fine)/WINDOW
                planes = np.empty((0, 3))
                if gen in ("H", "B"):
                    obs = [v[8] for v in ledgers]
                    steps = np.repeat(.25, 4)
                    if final:
                        obs = [np.vstack((grouped_means(m[:20], durations[:20], 5), m[20:])) for m in obs]
                        steps = np.r_[steps, durations[20:]]
                    planes = capacity(c, parent["temperature"], pilots, np.array(obs), steps, not final)
                chosen = synthesize(load, planes, pilots, balance, cost, a, b, len(original),
                                    boundary_only=gen == "B")
                for xy in original:
                    if len(chosen) == len(original):
                        break
                    if xy not in chosen:
                        chosen.append(xy)
                calibration = dict(points=pilots, grid=fine, bins=len(durations), ref=energies,
                                   nonthermal=digest(p1.raw([load, balance, cost, a, b, list(original)])),
                                   moment_hash=digest(b"".join(v[8].tobytes() for v in ledgers)))
                assert set(pilots) <= set(chosen)
            assert len(set(chosen)) == len(original) == len(chosen)
            for x, y in chosen:
                xy = (x, y)
                cfg, key, grid, ledger = evaluate(xy)
                action = (g, n, x, y)
                info = (j+1, parent["id"], *action, key, xy in pilots, xy in original)
                if key in pool:
                    log["actions"].append((*info, "duplicate", None, None, None, None, None))
                    continue
                if not ledger[0]:
                    log["actions"].append((*info, "timing", None, None, None, None, int(ledger[-1])))
                    continue
                energy = ledger[1] + (c.base*c.p.horizon/WINDOW if final else 0.)
                temp, peak = parent["temperature"], parent["peak"]
                risk = max(load[:, 0] + load[:, 1:] @ xy)
                if moments:
                    means = ledger[8]
                    if grid == 500:
                        means = grouped_means(means, durations, 5)
                    widths = np.minimum(2500, right-lo-2500*np.arange(len(means)))/WINDOW
                    for mean, dt in zip(means, widths):
                        temp = c.propagate(temp, mean, dt)
                        peak = max(peak, max(temp))
                    if rank_thermal:
                        risk = peak if final else max(peak, max(c.propagate(temp, means[:4].mean(axis=0), 1.)))
                drain = max(max(ledger[2]), max(ledger[6]+c.args[4][:len(cfg)]))
                state = dict(config=cfg, id=key, f=tuple(map(int, ledger[2])),
                             k=tuple(map(int, ledger[3])), temperature=temp,
                             peak=peak, risk=risk, energy=energy, drain=drain, slack=int(ledger[-1]),
                             action=action, parent=parent["id"])
                pool[key] = state
                log["actions"].append((*info, "valid", energy, peak if moments else None,
                                       risk, drain, state["slack"]))
            log["groups"].append(dict(window=j+1, parent=parent["id"], g=g, n=n, slots=len(original),
                                      calibration=calibration, end_s=clock()-start))
    return pool, True

def build(c, method, width, start, deadline, stage):
    parents = [initial(c)]
    for j in range(c.windows):
        pool, completed = expand(c, j, parents, method, start, deadline, stage)
        if not completed or not pool:
            return []
        if j+1 == c.windows:
            return ranking(pool, "legacy" if method == "C2" else "safe_energy")
        ordered = sorted(pool.values(), key=lambda s: (round(s["energy"], 11), s["config"]))
        parents = diverse(ordered, False)
        if width > len(parents):
            picked = {s["id"] for s in parents}
            parents += [s for s in ordered if s["id"] not in picked][:width-len(parents)]
        stage["beam"].append([s["id"] for s in parents])
    raise AssertionError("missing terminal window")

def run(c, method, budget=None):
    fixed_only = method in ("HT", "BT")
    c.eng.out = DATA / "physical"
    stages, records, seen = [], [], set()
    start = clock()
    deadline = start + budget if budget is not None else float("inf")
    width = 4
    while True:
        stage = dict(width=width, actions=[], groups=[], beam=[], start_s=clock()-start)
        stages.append(stage)
        tick = clock()
        ordered = build(c, method, width, start, float("inf") if width == 4 else deadline, stage)
        built = clock()
        stage.update(build_s=built-tick, ready_s=built-start, terminal=len(ordered))
        if not ordered:
            assert width > 4
            stop = "deadline_during_build"
            break
        new = 0
        widen = False
        for rank, s in enumerate(ordered, 1):
            if len(records) >= 4 and clock() >= deadline:
                break
            if s["id"] in seen:
                continue
            t = clock()
            cert, _ = c.certify(s["config"])
            end = clock()
            assert abs(cert["E35_J"]-s["energy"]) < 1e-8
            seen.add(s["id"])
            new += 1
            records.append(dict(width=width, rank=rank, id=s["id"], prediction=None if method=="C2" else s["peak"],
                                ref_E=s["energy"], cert=cert, cert_s=end-t, start_s=t-start, end_s=end-start))
            if fixed_only and len(records) == 4:
                break
            if new >= 2*width and deadline-clock() >= 2*stage["build_s"] + end-t:
                widen = True
                break
        if fixed_only:
            stop = "fixed_four"
            break
        if clock() >= deadline:
            stop = "deadline_after_certificate" if records[-1]["end_s"] > budget else "deadline_between_actions"
            break
        assert widen or all(s["id"] in seen for s in ordered)
        width *= 2
    wall = clock()-start
    assert len(records) >= 4
    result = dict(case=c.label, method=method, budget_s=budget, wall_s=wall, stop=stop, records=records,
                  stages=[{k:v for k,v in stage.items() if k not in ("actions","groups","beam")} for stage in stages])
    folder = DATA / "runs" / c.label / method
    for stage in stages:
        write_gz(folder / f"w{stage['width']}.json.gz", stage)
    p1.put(folder / "run.json", result)
    print(c.label, method, len(records), round(wall, 3), flush=True)
    return records[3]["end_s"]

def main():
    import numba, psutil, scipy
    if (DATA/"runs").exists():
        raise FileExistsError("use a fresh M1E_OUTPUT")
    DATA.mkdir(parents=True, exist_ok=True)
    warm = p1.Engine("S32", DATA.parent / ".m1e-warm")
    warm.cert(*warm.construct("quota", 1)[0])
    p1.put(DATA/"environment.json", dict(python=sys.version, platform=platform.platform(), numpy=np.__version__,
           scipy=scipy.__version__, numba=numba.__version__, affinity=psutil.Process().cpu_affinity(),
           threads={k:os.environ[k] for k in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS","NUMBA_NUM_THREADS")},
           P1=p1.P1, frozen_files=p1.PIN, source={p.name:digest(p.read_bytes()) for p in
           (ROOT/"experiment.py",ROOT/"sampler.py",ROOT/"PROTOCOL.md")}))
    i = 0
    for label in CASES:
        for word in sequences(int(label[1:])//80):
            c = reordered(case_for(label), label, word)
            current = DATA/"validation_inputs"/(c.label+".csv")
            frozen = D/"data/validation_inputs"/current.name
            assert current.read_bytes().splitlines() == frozen.read_bytes().splitlines()
            budget = run(c, "HT")
            for method in METHODS[i%6:] + METHODS[:i%6]:
                run(c, method, budget)
            run(c, "BT")
            i += 1

if __name__ == "__main__":
    main()
