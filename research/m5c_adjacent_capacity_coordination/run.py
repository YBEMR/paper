"""One preregistered batch. The gate, each cell and the offline audit have separate clocks."""
import csv
import gzip
import json
import os
import platform
import resource
import signal
import sys
import time
from pathlib import Path

CPUS = sorted(os.sched_getaffinity(0))
START = time.perf_counter()
for variable in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS", "NUMEXPR_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[variable] = "1"
ROOT = Path(__file__).resolve().parent
OLD = ROOT.parent / "m5b_suffix_capacity"
OUT = ROOT / "work"
ARC = ROOT / "archive"
sys.path.insert(0, str(OLD))
import study
from study import prior, failed_physical
from planning import generate
from suffix import Timing, Boundary
from coordination import Space, Leg, scan, recipes
import numpy as np
import multiprocessing as mp

CODES = ["A02", "A06", "C10", "C11"]
REF = dict(zip(CODES, [27.735636354, 46.232637555, 58.686370337, 73.873570783]))
read, save, sha = prior.read, prior.save, prior.sha
encode = lambda plan: prior.enc([row[:2] for row in plan["rows"][1::3]])


def setup():
    sys.path.insert(0, str(ROOT.parent / "u2_adaptive_groups"))
    import common_u2
    prior.u2 = common_u2
    prior.api, prior.fourth, _, prior.state = common_u2.stack()


def seed(case):
    rows = list(csv.DictReader((OLD / "archive/results.csv").open()))
    row = min((r for r in rows if r["case"] == case), key=lambda r: float(r["J"]))
    path = OLD / "archive/endpoints" / case / row["method"]
    plan, cert = read(path / "plan.json"), read(path / "certificate.json")
    assert sha(prior.u2.raw(plan)) == row["plan"] == cert["plan_sha256"]
    assert cert["metrics"]["status"] == "SAFE" and abs(float(row["J"]) - REF[case]) < 5.1e-10
    assert [float(row[k]) for k in ("lower", "upper")] == cert["metrics"]["E_bounds"]
    return encode(plan), cert, path


def splice(c, g, patch):
    return c[:g[0]] + patch + c[g[-1]+1:]


def functional_gate():
    pins = {"planning.py":"160e333d5e0b430dde98a7081eddbf3b0bd0c535",
            "suffix.py":"22d4893c93729cb81aa9b7f8080b0f267da6f969",
            "study.py":"22fb927d6ffdb53cca6b7071b431d52288e0be90",
            "../m5a_mixed_frequency_quota/planner.py":"ce7ead668df9e5b66efdea30cbf7b75d99e0a9f6",
            "../m5a_mixed_frequency_quota/run.py":"d01d2d980e2887f758ed0421fe60a20f3aa94d12"}
    for name, pin in pins.items():
        assert prior.fourth.blob((OLD / name).read_bytes()) == pin, name
    for name, pin in prior.fourth.PIN.items():
        assert prior.fourth.blob((prior.fourth.ROOT / "p1" / name).read_bytes()) == pin
    negative = read(OLD / "adjacent_capacity.json")["cases"]
    assert sum(x["adjacent_pairs"] for x in negative.values()) == 161
    assert not any(x["main_capacity_witnesses"] for x in negative.values())
    gate = {"negative_pairs": {c:r["adjacent_pairs"] for c,r in negative.items()}, "seeds": {},
            "source_blobs": pins, "p1_blobs":prior.fourth.PIN, "p1_commit":prior.fourth.P1}
    for case in CODES:
        eng, obj = prior.engine(case, OUT / case / "gate")
        c, old, path = seed(case)
        r = eng.replay(prior.dec(c))
        new, tr = eng.cert(prior.dec(c), r)
        assert new["plan_sha256"] == old["plan_sha256"] and prior.u2.raw(new["switches"]) == prior.u2.raw(old["switches"])
        a, b = new["metrics"], old["metrics"]
        assert a["status"] == "SAFE" and max(a["E_bounds"][0], b["E_bounds"][0]) <= min(a["E_bounds"][1], b["E_bounds"][1])
        assert new["E35_exact"] == old["E35_exact"]
        tm = Timing(eng)
        assert tm.check(c)[0]
        tests = Boundary(eng, c, r, tm).prove_boundaries()
        gate["seeds"][case] = dict(**prior.endpoint(new), historical_bounds=b["E_bounds"],
            source=str(path.relative_to(OLD)), input_sha256=obj["input_sha256"], trace=sha(tr.tobytes()), boundary_checks=tests)
        # Warm only the generic device kernel and compare its final state with the independent boundary oracle.
        space = Space(eng, c, r, tm, lambda *args, **kwargs: None)
        for d in range(2):
            ids = space.groups[0]
            ix = ids[(space.bound.parent[ids] >= 10) == d]
            start, old_k, cap, target, _ = space.bound.limits(d, 0)
            pol = recipes(len(ix), len(ix)//2, d)[:1]
            own, margin, _, end, last = scan(ix,d,pol,start,old_k,cap,target,tm.ready,tm.limits,tm.lengths,space.inc)
            changed = bytearray(c)
            for i in ix:
                changed[i] = 10*d
            probe = space.bound.inspect(bytes(changed),0)[d]
            assert (bool(own[0]),int(margin[0]),int(end[0]),int(last[0])) == (probe["own"],probe["remaining"],probe["finish"],probe["last_freq"])
        if case == "C10":
            path0 = prior.ROOT / "history/C10/plan.json"
            orig = encode(read(path0))
            events = study.event_rows(OLD / "archive/logs/C10/D/events.jsonl")
            accepted = [z for z in events if z["kind"] == "accepted"]
            configs, states = [], []
            for z in accepted:
                orig = splice(orig, eng.groups[z["meta"]["win"]], bytes.fromhex(z["meta"]["patch"]))
                state = eng.replay(prior.dec(orig))
                cert, _ = eng.cert(prior.dec(orig), state)
                assert cert["plan_sha256"] == z["plan"] and abs(cert["metrics"]["E_J"]-z["J"]) < 1e-8
                configs.append(orig)
                states.append(state)
            before, rear, joint = configs
            ids = eng.groups[5]
            front = splice(before, ids, joint[ids[0]:ids[-1]+1])
            m0 = Boundary(eng,before,states[0],tm).inspect(front,5)
            m1 = Boundary(eng,rear,states[1],tm).inspect(joint,5)
            hist = next(x for x in negative[case]["observed_adjoining_chains"] if x["compensation"])
            assert [v["remaining"] for v in m0] == hist["original_margins"] == [339,-163]
            assert [v["remaining"] for v in m1] == hist["new_margins"] == [61,15]
            assert joint == c and not tm.check(front)[0]
            gate["history"] = dict(parent=accepted[0]["plan"],rear=accepted[1]["plan"],
                joint=accepted[2]["plan"],front_only=m0,with_rear=m1,J=a["E_J"],front_timing=tm.check(front))
    (ARC / "gate").mkdir(parents=True, exist_ok=True)
    save(ARC / "gate/checks.json", gate)


def cell(case, method, cpu, path, start):
    os.sched_setaffinity(0, {cpu})
    clock = lambda: time.perf_counter()-start
    log = (path / "events.jsonl").open("w", buffering=1)
    def emit(kind, **kwargs):
        log.write(json.dumps(dict(t=clock(), kind=kind, **kwargs), default=lambda x:x.tolist(), separators=(",",":"))+"\n")

    eng, _ = prior.engine(case, path)
    code, cert, _ = seed(case)
    state = eng.replay(prior.dec(code))
    tm = Timing(eng)
    cache = {code: (state, cert)}
    best = cert
    emit("seed", **prior.endpoint(cert))
    total = 0
    for turn in range(3):
        parent, parent_cert = code, cert
        number = 0
        emit("round", turn=turn, parent=parent_cert["plan_sha256"], noop=sha(parent))
        pool, coverage, _ = generate(eng, code, state, "R", tm, path/f"s{turn}.jsonl.gz")
        singles = [(c,dict(role="single",win=m["win"],patch=m["patch"],hint=m["hint_delta_J"])) for c,m in pool]
        emit("single_pool", turn=turn, coverage=coverage, selected=[m for _,m in singles])
        visited = set()
        winner = (code, state, cert)
        def assess(c, meta):
            nonlocal number, total, winner, best
            if c in visited or number >= 16:
                return None
            visited.add(c)
            was_cached = c in cache
            if was_cached:
                r, d = cache[c]
            else:
                r = eng.replay(prior.dec(c))
                assert (r is not None) == bool(tm.check(c)[0])
                d = None
                if r is not None:
                    number += 1
                    total += 1
                    d, _ = eng.cert(prior.dec(c), r)
                cache[c] = r, d
            kwargs = dict(turn=turn,parent=parent_cert["plan_sha256"],cfg=sha(c),meta=meta,n=total)
            if d is None:
                emit("timing_fail",**kwargs)
                return None
            emit("cache" if was_cached else "cert",**kwargs,**prior.endpoint(d))
            if d["metrics"]["status"] != "SAFE":
                return None
            if d["metrics"]["E_bounds"][1] < best["metrics"]["E_bounds"][0]:
                best=d
                emit("incumbent",turn=turn,n=total,meta=meta,**prior.endpoint(d))
            if d["metrics"]["E_bounds"][1] < winner[2]["metrics"]["E_bounds"][0]:
                winner=(c,r,d)
            return c,r,d
        if method == "S":
            for c,m in singles:
                assess(c,m)
        else:
            with gzip.open(path/f"pairs{turn}.jsonl.gz","wt",compresslevel=1) as ledger:
                def record(stage, **kw):
                    ledger.write(json.dumps(dict(stage=stage,**kw),default=lambda x:x.tolist(),separators=(",",":"))+"\n")
                space = Space(eng, code, state, tm, record)
                if method == "R":
                    # Distinct certified rear windows are branches of the current round's parent.
                    rear_choices = {}
                    for c,m in singles:
                        if m["win"] > 0:
                            rear_choices.setdefault(m["win"], (c,m))
                    branches=[]
                    for c,m in list(rear_choices.values())[:4]:
                        o = assess(c,dict(m,role="rear_branch"))
                        if o:
                            branches.append((o,m))
                    for c,m in singles[:4]:
                        assess(c,m)
                    pairs = []
                    for (back, br, bd), m in sorted(branches,key=lambda x:x[0][2]["metrics"]["E_bounds"][1])[:2]:
                        w = m["win"]-1
                        branch_space = Space(eng, back, br, tm, record)
                        legs, _ = branch_space.leg_pool(w, f"reverse-{w}")
                        for f in legs:
                            patch = bytes.fromhex(m["patch"])
                            rear = Leg(0.,patch,(),(),False)
                            raw = space.bound.inspect(space.splice(w,f.patch),w)
                            f = Leg(f.hint,f.patch,f.end,tuple(x["remaining"] for x in raw),f.fixed)
                            item = space.paired(w,f,rear,"R")
                            if item:
                                item[1]["via"]=bd["plan_sha256"]
                                pairs.append(item)
                    pairs.sort(key=lambda x:(x[1]["hint"],x[0]))
                else:
                    for c,m in singles[:4]:
                        assess(c,m)
                    pairs = space.joint(method)
                emit("pair_pool",turn=turn,offered=len(pairs),ordered=[sha(c) for c,m in pairs])
                for c,m in [*pairs,*singles]:
                    if number == 16:
                        break
                    assess(c,m)
        code, state, cert = winner
        assert best["plan_sha256"] == cert["plan_sha256"]
        emit("close", turn=turn, new=number, chosen=cert["plan_sha256"])
        if code == parent:
            break
    emit("natural", n=total)


def lane(i):
    case, cpu = CODES[i], CPUS[i % len(CPUS)]
    os.sched_setaffinity(0, {cpu})
    order = "SRPJ"
    for method in order[i:]+order[:i]:
        folder=OUT/case/method
        folder.mkdir(parents=True,exist_ok=False)
        st=time.perf_counter()
        proc=mp.get_context("fork").Process(target=cell,args=(case,method,cpu,folder,st))
        baseline=resource.getrusage(resource.RUSAGE_CHILDREN)
        proc.start()
        proc.join(max(0,59.75-(time.perf_counter()-st)))
        if proc.is_alive():
            proc.kill()
            proc.join()
            status="CAP"
        else:
            status="NATURAL" if proc.exitcode==0 else "ERROR"
        used=resource.getrusage(resource.RUSAGE_CHILDREN)
        wall=time.perf_counter()-st
        save(folder/"receipt.json",dict(status=status,wall_s=wall,cpu_s=used.ru_utime+used.ru_stime-baseline.ru_utime-baseline.ru_stime,
             core=cpu,host=platform.node(),limit_s=60,rc=proc.exitcode))
        print(case,method,status,round(wall,2),flush=True)
        assert status != "ERROR" and wall<=60


def main():
    os.sched_setaffinity(0,{CPUS[0]})
    signal.alarm(max(1,115-int(time.perf_counter()-START)))
    setup()
    functional_gate()
    save(ARC/"gate/receipt.json",dict(wall_s=time.perf_counter()-START+2, startup_allowance_s=2,
         cpu_s=time.process_time(),core=CPUS[0],host=platform.node(),run=os.getenv("GITHUB_RUN_ID"),
         source=os.getenv("GITHUB_SHA"),versions={k:__import__(k).__version__ for k in ["numpy","numba","scipy"]}))
    signal.alarm(0)
    print("Verified four seeds and the historical compensation.",flush=True)
    for offset in range(0,4,len(CPUS)):
        lanes=[mp.get_context("fork").Process(target=lane,args=(i,)) for i in range(offset,min(4,offset+len(CPUS)))]
        for p in lanes:p.start()
        for p in lanes:p.join()
        assert all(p.exitcode==0 for p in lanes)


if __name__ == "__main__":
    main()
