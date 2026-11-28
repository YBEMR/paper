"""Run the frozen one-map route and its four-map extension under one absolute clock."""
import os
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
V1 = ROOT.parent / "ch3_integrated_quality_v1"
sys.path.insert(0, str(V1))
import trial as frozen

OUT = ROOT / "archive"
m = frozen.m


def identity(plan):
    return bytes(row[0] for row in plan["rows"][1::3])


def representatives(events, cutoff, mapping_for):
    seed = frozen.best(events, cutoff)
    if seed is None:
        return [], {}
    by_map = {}
    by_plan = {}
    for event in events:
        if event["event"] != "certificate" or event["t"] > cutoff:
            continue
        point = event["point"]
        key = point["plan"]
        if point["status"] != "SAFE" or key in by_plan:
            continue
        mapping = mapping_for(key)
        by_plan[key] = mapping
        order = (point["bounds"][1], event["t"], key)
        if mapping not in by_map or order < by_map[mapping][0]:
            by_map[mapping] = (order, event)
    first = by_plan[seed["point"]["plan"]]
    chosen = [seed] + [row[1] for key, row in sorted(by_map.items(), key=lambda p: p[1][0])
                       if key != first][:3]
    return chosen, by_map


def refine_many(obj, dest, events):
    frozen.arm_alarm(frozen.ORIGIN + 60)
    ledger = dest / "refine.jsonl"
    native_log = frozen.log
    native_handoff = frozen.handoff
    physical = dest / "search/physical/evidence" / obj["case"]
    native_log(ledger, "begin", task="selection")
    def mapping_for(key):
        return identity(frozen.read(physical / key / "plan.json"))
    nominees, pool = representatives(events, 55, mapping_for)
    native_log(ledger, "end", task="selection", pool_size=len(pool),
               seeds=[p["point"]["plan"] for p in nominees],
               representatives=[dict(mapping=frozen.digest(k), plan=p[1]["point"]["plan"],
                                     upper=p[0][0]) for k, p in pool.items()])
    global_best = nominees[0]["point"]
    try:
        for rank, seed in enumerate(nominees, 1):
            tag = f"map{rank}"
            folder = dest / tag
            folder.mkdir()
            local_best = seed["point"]
            native_log(ledger, "map_start", rank=rank, seed=local_best["plan"])
            def forward(_path, event, **fields):
                nonlocal local_best, global_best
                if "stage" in fields:
                    fields["stage"] = tag + "/" + fields["stage"]
                if event == "certificate" and frozen.strict(fields["point"], local_best):
                    local_best = fields["point"]
                    if frozen.strict(local_best, global_best):
                        global_best = local_best
                if event == "certificate":
                    fields.update(local_best=local_best["plan"], global_best=global_best["plan"])
                native_log(ledger, event, rank=rank, **fields)
            def shared_handoff(case, target, _source, point):
                return native_handoff(case, target, physical, point)
            frozen.log, frozen.handoff = forward, shared_handoff
            frozen.refine(obj, folder, seed)
            native_log(ledger, "map_end", rank=rank, local_best=local_best["plan"],
                       global_best=global_best["plan"])
    finally:
        frozen.log, frozen.handoff = native_log, native_handoff


def cell(obj, rep, arm, dest):
    if arm == "single":
        return frozen.cell(obj, rep, "integrated", dest)
    dest.mkdir(parents=True, exist_ok=False)
    frozen.ORIGIN = frozen.T()
    search = frozen.worker(frozen.search, (obj, "integrated", dest), frozen.ORIGIN + 60)
    events = frozen.readlog(dest / "search.jsonl")
    first = next((r for r in events if r["event"] == "certificate" and
                  r["point"]["status"] == "SAFE" and r["t"] <= 60), None)
    cut = 55 if first and first["t"] < 55 else 60
    post = None
    if cut == 55 and frozen.T() < frozen.ORIGIN + 60:
        post = frozen.worker(refine_many, (obj, dest, events), frozen.ORIGIN + 60)
    stop = frozen.T() - frozen.ORIGIN
    frozen.save(dest / "receipt.json", dict(case=obj["case"], rep=rep, version=arm,
        host=platform.node(), cpu=frozen.CPU, limit=60, cut=cut, search_rc=search, refine_rc=post,
        wall_including_supervision=stop, charged_s=min(60, stop), source=os.environ["GITHUB_SHA"],
        run=os.environ["GITHUB_RUN_ID"]))
    print(obj["case"], rep, arm, round(stop, 3), flush=True)


def lane(code):
    prep = frozen.warm()
    obj = next(r for r in m.u2.CASES if m.label(r) == code)
    dest = OUT / code
    order = []
    for rep in (1, 2, 3):
        arms = ["single", "multi"]
        if (obj["index"] + rep - 1) % 2:
            arms.reverse()
        order.extend((rep, arm) for arm in arms)
    frozen.save(dest / "lane.json", dict(warm=prep, order=order, case=obj["case"],
        input_sha=obj["input_sha256"], source=os.environ["GITHUB_SHA"]))
    for rep, arm in order:
        cell(obj, rep, arm, dest / f"r{rep}-{arm}")


def gate():
    import time
    start = frozen.T()
    warm = frozen.warm()
    dest = OUT / "gate"
    dest.mkdir(parents=True)
    def event(key, upper, t, status="SAFE"):
        return dict(event="certificate", point=dict(plan=key, bounds=[upper-.01, upper], status=status), t=t)
    events = [event("a", 5, 1), event("b", 4, 2), event("c", 3, 3), event("d", 1, 56),
              event("e", 2, 4,"HOT"),event("f", 6, 5),event("g", 7, 6),event("h", 8, 7)]
    keys = dict(a=b"A", b=b"A", c=b"C", f=b"F", g=b"G", h=b"H")
    reps, pool = representatives(events, 55, keys.__getitem__)
    assert [r["point"]["plan"] for r in reps] == ["c","b","f","g"] and len(pool)==5
    assert representatives([events[4]], 55, keys.__getitem__)==([], {})
    assert identity({"rows":[[],[2,0],[],[],[3,1],[]]}) == identity({"rows":[[],[2,5],[],[],[3,0],[]]})
    frozen.ORIGIN = frozen.T()
    timer = frozen.worker(time.sleep, (1,), frozen.ORIGIN + .05)
    assert timer["rc"] < 0 and timer["supervisor_t"] < 1
    obj = next(r for r in m.u2.CASES if m.label(r)=="A06")
    old = ROOT.parent/"m5b_suffix_capacity/archive/endpoints/A06/E"
    cfg = m.genes(frozen.read(old/"plan.json"))
    test = dest/"same_seed"
    eng, flow = m.build(obj, test/"search/physical")
    d, _ = flow.certify(m.u2.encoded(cfg))
    pt = m.endpoint(d)
    assert pt == m.endpoint(frozen.read(old/"certificate.json"))
    seed = dict(event="certificate",point=pt,t=1)
    frozen.ORIGIN = frozen.T()
    # refines arm a hard timer and must therefore execute in child processes.
    assert frozen.worker(frozen.refine,(obj,test,seed),frozen.ORIGIN+60)["rc"] == 0
    assert frozen.worker(refine_many,(obj,test,[seed]),frozen.ORIGIN+60)["rc"] == 0
    log = frozen.readlog(test/"refine.jsonl")
    single = [e["point"] for e in log if e["event"]=="certificate" and "rank" not in e]
    multi = [e["point"] for e in log if e["event"]=="certificate" and "rank" in e]
    assert len(single)==2 and single==multi
    assert log[-1]["event"]=="map_end" and log[-1]["global_best"]==frozen.best(log)["point"]["plan"]
    frozen.save(dest/"gate.json",dict(passed=True, warm=warm, clock_probe=timer,
        ordinary=single[0],thermal=single[1],wall_s=frozen.T()-start))


if __name__ == "__main__":
    gate() if sys.argv[1]=="gate" else lane(sys.argv[1])
