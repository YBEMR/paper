"""Read original ledgers and physical witnesses. No solver or certificate evaluator is imported."""
import csv
import gzip
import hashlib
import itertools
import json
import os
import sys
import zlib
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

for var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[var] = "1"
import numpy as np
import psutil

HERE = Path(__file__).resolve().parent
LAB = Path(os.environ.get("U4_LAB", HERE.parents[2]))
A = Path(os.environ.get("U4A_SRC", LAB / "U4a_worktree/research/u4a_integrated_fast_scheduler"))
OUT = HERE / "archive"
FOCUS = {"I03", "I05", "I06", "I07", "I09", "I11"}
def read(p):
    return json.loads(p.read_bytes())

def sha(b):
    return hashlib.sha256(b).hexdigest()

def raw(obj):
    return json.dumps(obj, separators=(",", ":"), sort_keys=True).encode()

def table(name, rows):
    rows = list(rows)
    assert rows, name
    with (OUT / (name + ".csv")).open("w", encoding="utf8", newline="") as f:
        w = csv.DictWriter(f, list(dict.fromkeys(k for row in rows for k in row)), lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow({k: raw(v).decode() if isinstance(v, (dict, list, tuple)) else v for k, v in row.items()})

def ledger(root, run):
    for rel in run["journal"]:
        body = gzip.decompress((root / rel).read_bytes())
        assert sha(body) == Path(rel).name.split(".")[0]
        yield from map(json.loads, body.splitlines())

def clocks():
    saved = []
    for p in sorted((LAB / "U4a_raw").glob("*/start.json")):
        r = read(p.parent / "receipt.json")
        duration = r["cap"] if r["status"] == "wall" else r["finish"]["wall_s"]
        saved.append(dict(route=p.parent.name, start=read(p)["start"], duration=duration,
                          core=r["cpu"], source_sha256=sha(p.read_bytes())))
    if saved:
        table("archived_clock_origins", saved)
    else:
        with (OUT / "archived_clock_origins.csv").open(encoding="utf8") as f:
            saved = [dict(x, start=float(x["start"]), duration=float(x["duration"])) for x in csv.DictReader(f)]
    return saved

def overlaps(origins, route):
    row = next(x for x in origins if x["route"] == route)
    a, b = row["start"], row["start"] + row["duration"]
    return sum(max(0, min(b, x["start"]+x["duration"]) - max(a, x["start"]))
               for x in origins if x["route"] != route) / (b-a)

def workload(obj):
    source = A / "registration/inputs" / obj["input"]
    assert sha(source.read_bytes()) == obj["input_sha256"]
    with source.open(encoding="utf8") as f:
        rows = list(csv.DictReader(f))
    split = [[int(r["kind"] == "B") for r in rows if int(r["scene"]) == j] for j in range(obj["windows"])]
    @lru_cache(None)
    def extension(j, gpu, npu, x, y):
        types = split[j]
        counts = (types.count(0), types.count(1))
        seen = [0, 0]
        code = bytearray()
        for k in types:
            old = seen[k]
            seen[k] += 1
            q = (x, y)[k]
            code.append(10+npu if seen[k]*q//counts[k] != old*q//counts[k] else gpu)
        return bytes(code)
    return rows, split, extension

def scan(obj, method, origins, extension):
    case = obj["id"]
    root = A / "results" / case
    run = read(root / "runs" / (method + ".json"))
    cap = run["receipt"]["cap"]
    phases, count, starts, pairs, last = defaultdict(Counter), Counter(), {}, [], {}
    last_action = {}
    active, begin, alltime = "outside", {}, Counter()
    safe = False
    target = method in ("NT10", "NT60")
    actions, beams, terminals, groups, by_window = [], [], [], 0, Counter()
    group_ends, first_begin, first_end = {}, None, None
    parent, levels, stats, distinct = {}, {}, defaultdict(Counter), defaultdict(set)
    ranked, shortlist, certs = [], [], []
    for e in ledger(root, run):
        name = e[0]
        count[name] += 1
        if name == "begin":
            active = e[1]
            begin[active] = min(e[2], cap)
        elif name == "end":
            alltime[e[1]] += max(0, min(e[2], cap)-begin.pop(e[1]))
            active = "outside"
        else:
            phases[active][name] += 1
            last[active] = name
        if name == "cert_start" and e[3] <= cap:
            starts[e[1]] = e[3]
            if first_begin is None:
                first_begin = e[3]
        if name == "cert" and e[1]["t"] <= cap and e[1]["n"] in starts:
            c = e[1]
            interval = c["t"] - starts[c["n"]]
            assert interval + 1e-5 >= c["kernel_s"]
            pairs.append((active, interval, c["kernel_s"]))
            if method == "Base" and active == "terminal":
                certs.append(dict(c, call_s=interval))
        if not safe and target:
            if name == "nt_actions":
                w, a = e[1:]
                actions.append(sha(raw([w, a])))
                by_window[(w, a[0], a[9])] += 1
            elif name == "nt_groups":
                groups += 1
                g = e[2]
                group_ends[(e[1], g["window"])] = g["end_s"]
            elif name == "nt_beam":
                beams.append(sha(raw(e[1:])))
            elif name == "nt_terminals":
                terminals.append([e[1], len(e[2]), sha(raw(e[2]))])
            elif name == "delivered" and e[2] <= cap:
                first_end, safe = e[2], True
        if name == "nt_actions":
            last[active] = "NT W%d window %d %s" % (e[1], e[2][0], e[2][9])
            last_action[active]=last[active]
        if name == "nt_groups":
            last[active] = "NT W%d completed group window %d" % (e[1], e[2]["window"])
        if name == "q4_action":
            last[active] = "FIFO window %d" % (e[2]+1)
            last_action[active]=last[active]
        if method not in ("Base", "Previous"):
            continue
        if name == "parent":
            parent[e[1]] = bytes.fromhex(e[2])
        elif name == "q4_action":
            _, pid, j, freq, quota, _, state = e
            p = parent[pid]
            code = p + extension(j, *freq, *quota)
            k = (active, j)
            st = stats[k]
            st.update(attempt=1, replay_requests=len(code), parent_requests=len(p), legal=int(not state[-1]))
            distinct[k].add(code)
            if active == "construct" and not state[-1]:
                levels.setdefault(j, {}).setdefault(code, state)
        elif name == "store" and e[1] == "base":
            layers = e[2]["layers"]
            for j, entry in enumerate(layers):
                legal = levels.get(j, {})
                final = j+1 == obj["windows"]
                order = sorted(legal, key=lambda c: (legal[c][4] + (legal[c][5] if final else 0), c))
                assert len(order) == entry["distinct"] and [c.hex() for c in order[:4]] == entry["retained"]
                if final:
                    ranked = order
            shortlist = [bytes.fromhex(c) for c in e[2]["terminal"]]
            assert shortlist == ranked[:12]
    for phase, st in begin.items():
        alltime[phase] += max(0, run["wall_s"]-st)
    assert dict(count) == run["counts"]
    assert all(abs(v-run["phases"][k]) < 1e-8 for k,v in alltime.items())
    summary = []
    for ph, duration in alltime.items():
        spans = [p for p in pairs if p[0] == ph]
        summary.append(dict(case=case, method=method, phase=ph, clipped_wall_s=duration,
                            actions=phases[ph]["q4_action"]+phases[ph]["native_action"]+phases[ph]["nt_actions"],
                            nt_groups=phases[ph]["nt_groups"], nt_beams=phases[ph]["nt_beam"],
                            started=phases[ph]["cert_start"], timed_completed=len(spans),
                            completed_call_s=sum(p[1] for p in spans), nested_kernel_s=sum(p[2] for p in spans),
                            last_observed=last.get(ph), last_archived_action=last_action.get(ph), unclosed=ph in begin))
    route = dict(case=case, method=method, windows=obj["windows"], requests=obj["requests"],
                 input=obj["input_sha256"], receipt=run["receipt"]["status"], limit_s=cap, wall_s=run["wall_s"],
                 decision_cpu_s=run["receipt"]["finish"].get("cpu_s"), process_wall_s=run["receipt"]["process_s"],
                 mean_other_timed_lanes=overlaps(origins, case+"-"+method), core=run["receipt"]["cpu"],
                 warm_s=run["warm"]["warm_s"], all_actions=count["nt_actions"]+count["q4_action"]+count["native_action"],
                 first_SAFE=(run["delivered"] or [{}])[0].get("t"), started=run["started_certificates"],
                 complete=len(run["certificates"]), partial_files=run["partial"], unclosed=list(begin),
                 unassigned_s=run["wall_s"]-sum(alltime.values()), journals=run["journal"])
    replay = [dict(case=case,method=method,phase=phase,window=j+1,**v,unique_configs=len(distinct[phase,j]))
              for (phase,j),v in stats.items()]
    nt = dict(actions=actions,beams=beams,groups=groups,terminals=terminals,
              windows=[dict(width=w,window=j,status=k,n=n) for (w,j,k),n in by_window.items()],
              group_ends=[(w,j,t) for (w,j),t in group_ends.items()], first_cert_start=first_begin,first_safe=first_end)
    return route, summary, replay, nt, ranked, shortlist, certs

def common(a,b):
    return next((i for i,(x,y) in enumerate(zip(a,b)) if x!=y), min(len(a),len(b)))

def routes():
    routes_out, phases, replay, nt_paths, nt_levels, pools = [], [], [], [], [], {}
    origins = clocks()
    for obj in read(A / "registration/cases.json"):
        case = obj["id"]
        if not case.startswith("I"):
            continue
        _, _, ext = workload(obj)
        nt = {}
        for path in sorted((A/"results"/case/"runs").glob("*.json")):
            method=path.stem
            route, ph, rep, path_nt, ranked, shortlist, certs = scan(obj, method, origins, ext)
            routes_out.append(route); phases.extend(ph); replay.extend(rep)
            if method in ("NT10","NT60"):
                nt[method] = path_nt
                nt_levels.extend(dict(case=case,method=method,**rec) for rec in path_nt["windows"])
            if method=="Base":
                pools[case]=dict(ranked=[c.hex() for c in ranked], shortlist=[c.hex() for c in shortlist], certs=certs)
        a,b=nt["NT10"],nt["NT60"]
        nt_paths.append(dict(case=case,windows=obj["windows"],short_last=max(r["window"] for r in a["windows"]),
                             short_actions=len(a["actions"]),long_pre_SAFE_actions=len(b["actions"]),
                             identical_action_prefix=common(a["actions"],b["actions"]),short_beams=len(a["beams"]),
                             long_beams=len(b["beams"]),identical_beam_prefix=common(a["beams"],b["beams"]),
                             short_groups=a["groups"],long_groups=b["groups"],long_terminals=b["terminals"],
                             short_group_ends=a["group_ends"],long_group_ends=b["group_ends"],
                             short_actions_sha256=sha(raw(a["actions"])),long_actions_sha256=sha(raw(b["actions"])),
                             first_start=b["first_cert_start"],first_SAFE=b["first_safe"]))
    for name,rows in (("routes",routes_out),("phases",phases),("fifo_work",replay),("nt_paths",nt_paths),("nt_windows",nt_levels)):
        table(name,rows)
    (OUT/"base_pools.json.gz").write_bytes(gzip.compress(raw(pools),mtime=0))

def development_routes():
    origins=clocks()
    rrows=[]; prows=[]
    for o in read(A/"registration/cases.json"):
        if o["cohort"]!="development":
            continue
        _,_,ext=workload(o)
        for p in sorted((A/"results"/o["id"]/"runs").glob("*.json")):
            route,ph,*_=scan(o,p.stem,origins,ext)
            rrows.append(route);prows.extend(ph)
    table("development_routes",rrows);table("development_phases",prows)

if __name__ == "__main__":
    psutil.Process().cpu_affinity([int(os.environ.get("AUDIT_CPU", "0"))])
    OUT.mkdir(exist_ok=True)
    if sys.argv[1] == "routes":
        routes()
    elif sys.argv[1] == "development":
        development_routes()
    elif sys.argv[1] == "physics":
        from pool_audit import physics
        physics()
    elif sys.argv[1] == "context":
        from archive_context import context
        context()
    elif sys.argv[1] == "identities":
        from archive_context import verify_sources_and_nt
        verify_sources_and_nt()
    else:
        raise SystemExit("choose routes, physics, context or identities")
