"""Single isolated, cold formal MILP worker. Run with launch.py."""
import hashlib
import json
import math
from pathlib import Path
import sys
from time import perf_counter as clock
import warnings

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CASE, OUT, START = sys.argv[1], Path(sys.argv[2]), float(sys.argv[3])
ELAPSED = lambda: clock() - START
OUT.mkdir(exist_ok=True, parents=True)


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False,
                               default=lambda x: x.tolist()), encoding="utf-8")


def emit(event, **data):
    with (OUT / "events.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps(dict(event=event, time_s=ELAPSED(), **data), allow_nan=False,
                             default=lambda x: x.tolist()) + "\n")


emit("load")
import numpy as np
from scipy.optimize import milp
from master import Kernel, Master
sys.path.insert(0, str(ROOT / "research/ch3_cooperative_cuts"))
from physical import Physical

config = json.loads((HERE / "protocol.json").read_text())
case = config["cases"][CASE]
catalog_path = ROOT / "research/kim_multidnn_expansion/catalog.json"
catalog = json.loads(catalog_path.read_bytes())
deps = case["deployments"] or catalog["search_order"]
assert len(deps) == len(set(deps)) == case["domain"] and set(deps) <= set(catalog["deployments"])
ev = Physical(ROOT, case["id"], lambda d: catalog["deployments"][d]["stages"])
assert ev.identity == case["request_sha256"]
assert len(ev.opps) == 27 and sum(s.duration_ns for s in ev.scenes) == 10040000000
from joint_thermal import modes

budget = config["budget_s"]
cost = dict(schedule_s=0., coefficient_s=0., matrix_s=0., solver_s=0., full_cert_s=0.)
grid, kernels, cache, cuts = {}, [], {}, []
stats = dict(schedule_hits=0, deadline_hits=0, distinct_deadline_rejects=0, grid_lookups=0)
best = first = lb = proof_time = None
certs, solves = [], []
emit("input", cases=deps, request_sha256=ev.identity, opps=ev.opps,
     catalog_sha256=hashlib.sha256(catalog_path.read_bytes()).hexdigest(),
     frames=[(s.service_end_ns-s.start_ns)//40000000 for s in ev.scenes], window_ns=sum(s.duration_ns for s in ev.scenes))


def compile_mode(d,j,f):
    stats["grid_lookups"] += 1
    key = (j, ev._signature(d,j), f)
    if key in cache:
        stats["schedule_hits"] += 1
        stats["deadline_hits"] += int(cache[key] < 0)
        return cache[key]
    t = clock()
    sch = ev._bound_schedule(ev.platform, ev.scenes[j], d, ev.opps[f])
    cost["schedule_s"] += clock()-t
    if not sch.deadline_feasible:
        stats["distinct_deadline_rejects"] += 1
        cache[key] = -1
        return -1
    t = clock()
    dt = sch.duration_ns * 1e-9
    kw = ev.events.thermal_kwargs(ev.platform, ev.opps[f], ev.ambient, True, "base")
    base = ev.events.evaluate_thermal(dt, sch.active_w, transfer_W=sch.transfer_w, trace=True, **kw)
    lam,u,inv = modes(tuple(kw["capacity_J_K"]), tuple(map(tuple, kw["conductance_W_K"])),
                      tuple(kw["slope_W_K"]))
    span = dt.sum()
    F = (u*np.exp(lam*span)) @ inv
    w = ((np.asarray(kw["slope_W_K"]) @ u)*(np.expm1(lam*span)/lam)) @ inv
    trace = base["trace_C"]
    anchors = np.argmax(trace,axis=0)
    times = base["trace_time_s"][anchors]
    peak = trace[anchors, np.arange(4)]
    h = (u * np.exp(times[:,None] * lam)) @ inv
    cache[key] = len(kernels)
    kernels.append(Kernel(np.asarray(base["final_C"])-30., F, base["energy_J"], w, peak, h, times))
    cost["coefficient_s"] += clock()-t
    return cache[key]


def certify(d, seq, origin, predicted=None):
    global first, best
    t = clock()
    result = ev.replay(d, seq)
    evidence = ev.evidence(d, seq)
    affine = 0.
    delta = np.zeros(4)
    for j,f in enumerate(seq):
        k = kernels[grid[d][j][f]]
        energy = k.e + k.w @ delta
        delta = k.b + k.F @ delta
        scene = evidence["physical"]["scene_rows"][j]
        if (abs(energy-scene["energy_j"]) > 1e-7 or
                max(abs(delta+30-np.array(scene["final_c"]))) > 1e-7):
            raise ArithmeticError("affine prediction disagrees with original scene")
        affine += energy
    if result.completed != 500 or abs(affine-result.energy_j)>1e-7:
        raise ArithmeticError("invalid full-window energy or request count")
    if predicted is not None and abs(predicted-affine)>1e-7:
        raise ArithmeticError("master objective differs from selected physical schedule")
    name = f"certificate_{len(certs):02d}.json"
    dump(OUT / name, evidence)
    cost["full_cert_s"] += clock()-t
    c = dict(file=name, time_s=ELAPSED(), deployment=d, opp=seq, origin=origin,
             status=result.status, completed=result.completed, slack_ms=result.slack_ms,
             peak_lower_c=max(result.lower), peak_upper_c=max(result.upper), energy_j=result.energy_j,
             affine_j=affine)
    certs.append(c)
    if result.status == "SAFE":
        if first is None:
            first = c["time_s"]
        if best is None or c["energy_j"] < best["energy_j"] - 1e-9:
            best = c
    emit("certificate", **{k:v for k,v in c.items() if k!="time_s"})
    return c, evidence["physical"]["scene_rows"]


def run():
    global lb, proof_time
    for index,d in enumerate(deps):
        slots = []
        for j in range(4):
            slot = {}
            for f in range(27):
                if ELAPSED() > budget-2:
                    return "incomplete_preparation"
                k = compile_mode(d,j,f)
                if k >= 0:
                    slot[f] = k
            slots.append(slot)
        grid[d] = slots
        emit("deployment_compiled", deployment=d, kernels=len(kernels), legal=[len(s) for s in slots])
        if index == 0 and all(slots):
            delta = np.zeros(4)
            seq = []
            for slot in slots:
                f = min(slot, key=lambda f:(kernels[slot[f]].e + kernels[slot[f]].w @ delta, f))
                k = kernels[slot[f]]
                seq.append(f)
                delta = k.b + k.F @ delta
            certify(d, seq, "first deployment greedy")
    dump(OUT/"grid.json", grid)
    np.savez_compressed(OUT/"kernels.npz", **{field:np.asarray([getattr(k,field) for k in kernels])
                                            for field in Kernel.__dataclass_fields__})
    witnesses = False
    while ELAPSED() < budget-2.5:
        t = clock()
        ub = best["energy_j"] if best else math.inf
        master = Master(grid, kernels, ub, witnesses, cuts)
        cost["matrix_s"] += clock()-t
        interval_lb = min(master.energy_bounds.values(), default=math.inf)
        if math.isfinite(interval_lb):
            lb = max(lb if lb is not None else -math.inf, interval_lb)
        remaining = budget-ELAPSED()-2.
        emit("model", witnesses=witnesses, prefix_cuts=len(cuts), interval_lb=interval_lb,
             available_solver_s=remaining, **master.size)
        if remaining <= 0:
            return "incomplete_model"
        t = clock()
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Unrecognized options detected.*")
            result = milp(master.obj, integrality=master.integer, bounds=master.bounds,
                          constraints=master.constraint, options=dict(time_limit=remaining,
                          presolve=True, mip_rel_gap=0., mip_abs_gap=0., threads=1, disp=True,
                          mip_feasibility_tolerance=1e-9, primal_feasibility_tolerance=1e-9,
                          dual_feasibility_tolerance=1e-9))
        seconds = clock()-t
        cost["solver_s"] += seconds
        dual = getattr(result, "mip_dual_bound", None)
        dual = float(dual) if dual is not None and np.isfinite(dual) else None
        if dual is not None:
            lb = max(lb, min(ub,dual)-1e-8)
        log = dict(status=int(result.status), message=result.message, seconds=seconds,
                   objective=result.fun, dual_j=dual, valid_lb_j=lb, nodes=getattr(result,"mip_node_count",None),
                   witnesses=witnesses, cuts=len(cuts), size=master.size)
        solves.append(log)
        emit("solve", **log)
        if result.x is None:
            return "no_solver_incumbent"
        d, seq = master.decode(result.x)
        c, rows = certify(d,seq,"MILP",result.fun)
        if c["status"]=="UNRESOLVED":
            return "unresolved_continuous_peak"
        if best and best["energy_j"]+1e-7 < lb:
            raise ArithmeticError("certified energy below numeric lower bound")
        if best and best["energy_j"]-lb <= 1e-7:
            proof_time = ELAPSED()
            return "optimal_within_tolerance"
        if c["status"]=="SAFE":
            return "safe_open_bound"
        if c["status"]!="VIOLATION":
            raise ValueError("unexpected certificate")
        j = next(j for j,row in enumerate(rows) if max(row["peak_lower_c"])>80.)
        prefix = seq[:j+1]
        if (d,prefix) in cuts:
            raise ArithmeticError("violating prefix reappeared")
        cuts.append((d,prefix))
        emit("cut", deployment=d, prefix=prefix, peak_lower_c=max(rows[j]["peak_lower_c"]))
        witnesses = True
    return "time_limit"


status = run()
dump(OUT/"result.json", dict(case=case["id"], status=status, budget_s=budget, first_safe_s=first,
     best=best, lower_bound_j=lb, certificate_s=proof_time, worker_s=ELAPSED(), cost=cost,
     stats=stats, kernels=len(kernels), finished_deployments=len(grid), cuts=cuts,
     certificates=certs, solves=solves))
emit("finish", status=status)
