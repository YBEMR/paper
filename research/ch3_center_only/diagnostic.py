"""Common-parent probe. Historical material is loaded only by this offline program."""
import csv
import importlib.util
import itertools
import math
from pathlib import Path
from types import FunctionType

import numpy as np
from anchor_cell import ROOT, PREV, analytic_expand, f, m

spec = importlib.util.spec_from_file_location("archived_analytic_diagnosis", PREV/"diagnose.py")
archived_diagnosis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archived_diagnosis)
GroupView = archived_diagnosis.GroupView


def save(name, rows):
    with (ROOT / "diagnostic" / name).open("w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def evaluate(fn, flow, parent, j, items):
    info = {}
    sampler = fn.__globals__["synthesize"]
    def tap(load, planes, seeds, balance, cost, a, b, slots, **kw):
        chosen = sampler(load, planes, seeds, balance, cost, a, b, slots, **kw)
        info.update(seeds=list(seeds), direct=list(chosen), slots=slots)
        return chosen
    instrumented = FunctionType(fn.__code__, dict(fn.__globals__, synthesize=tap))
    view = GroupView(flow, items)
    log = dict(actions=[], groups=[])
    _, done = instrumented(view, j, [parent], "NT", 0, math.inf, log)
    actions = {(r[4], r[5]): r for r in log["actions"]}
    assert done and len(log["groups"]) == 1 and len(actions) == len(log["actions"]) == info["slots"]
    return actions, info, view.calls


def grid_audit(flow, p, j, cfg, api):
    left, right = j * api.e.WINDOW, flow.p.horizon
    small, big = [flow.ledger(cfg, left, right, w, True, True) for w in (500, 2500)]
    for field in (0, 1, 2, 3, 4, 5, 6, 7, 9):
        np.testing.assert_array_equal(small[field], big[field])
    def widths(size, count):
        return np.minimum(size, right-left-np.arange(count)*size) / api.e.WINDOW
    aggregated = api.e.grouped_means(small[8], widths(500, len(small[8])), 5)
    direct = big[8]
    assert aggregated.shape == direct.shape
    error = float(np.max(abs(direct - aggregated)))
    temps = []
    for means in (aggregated, direct):
        temp = p["temperature"]
        path = [temp]
        for mean, dt in zip(means, widths(2500, len(means))):
            temp = flow.propagate(temp, mean, dt)
            path.append(temp)
        temps.append(np.array(path))
    temp_err = float(np.max(abs(temps[0] - temps[1])))
    peak_err = abs(max(p["peak"], temps[0].max()) - max(p["peak"], temps[1].max()))
    assert error < 1.e-10 and temp_err < 1.e-9 and peak_err < 1.e-9
    return dict(moment_max_error=error, temperature_max_error_C=temp_err, peak_error_C=peak_err)


def main():
    m.RUN = m.u2.stack()
    from simplified import expand
    api = m.RUN[0]
    control = analytic_expand(api.e.expand)
    groups, details, checks = [], [], []
    with (PREV/"diagnostic/candidates.csv").open() as stream:
        historical = {(r["case"], int(r["window"]), r["parent"], int(r["gpu_opp"]), int(r["npu_opp"]), int(r["x"]), int(r["y"])) for r in csv.DictReader(stream) if r["analytic_selected"] == "True"}
    reproduced = set()
    for code in ("A02", "A06", "C10", "C11"):
        obj = next(o for o in m.u2.CASES if m.label(o) == code)
        flow = m.u2.make_flow(api, obj, ROOT/"diag_scratch"/code)
        for j in (0, flow.windows//2, flow.windows-1):
            p = f.read(PREV/"paired_results"/code/"fit-60"/f"parent-{j}.json")
            p["config"] = bytes.fromhex(p["config"])
            p["temperature"] = np.array(p["temperature"])
            assert p["j"] == j and f.digest(p["config"]) == p["id"]
            types, a, b = api.e.window_types(flow, j)
            for (g,n), group in itertools.groupby(flow.candidates(j,p), key=lambda v:v[0][:2]):
                ctx = dict(case=code, window=j+1, parent=p["id"], gpu_opp=g, npu_opp=n)
                items = list(group)
                old, oi, ol = evaluate(control, flow, p, j, items)
                new, ni, nl = evaluate(expand, flow, p, j, items)
                assert ni["seeds"] == oi["seeds"][:1] and len(oi["seeds"]) == 3
                assert len(old) == len(new) == len(items)
                reproduced.update(tuple(ctx.values()) + xy for xy in old)
                removed = set(oi["seeds"][1:])
                def config(xy):
                    return p["config"] + flow.extension(types,a,b,g,n,*xy)
                for xy in sorted(old.keys() | new.keys()):
                    cfg = config(xy)
                    row = old.get(xy, new.get(xy))
                    valid, ref, slack = (ol if xy in old else nl)[cfg]
                    assert valid == (row[9] == "valid")
                    if xy in old and xy in new:
                        assert ol[cfg] == nl[cfg]
                        if valid:
                            assert abs(old[xy][12]-new[xy][12]) < 1.e-9
                    details.append(dict(**ctx,x=xy[0],y=xy[1],center=xy in ni["seeds"],removed_anchor=xy in removed,
                        anchor_rank=list(old).index(xy)+1 if xy in old else None,
                        center_rank=list(new).index(xy)+1 if xy in new else None,
                        center_source=("center" if xy in ni["seeds"] else "slice" if xy in ni["direct"] else "fallback") if xy in new else None,
                        fifo_valid=valid,ref_J=ref,slack_ticks=slack,risk_C=row[12],peak_C=row[11]))
                if j == flow.windows-1:
                    for xy in oi["seeds"]:
                        checks.append(dict(**ctx,x=xy[0],y=xy[1],**grid_audit(flow,p,j,config(xy),api)))
                def stats(actions, ledgers, prefix):
                    valid = [xy for xy,r in actions.items() if r[9]=="valid"]
                    ds = [math.hypot((x-u)/a,(y-v)/b) for (x,y),(u,v) in itertools.combinations(actions,2)]
                    return {prefix+"_valid":len(valid),prefix+"_best_ref_J":min((ledgers[config(xy)][1] for xy in valid),default=None),
                            prefix+"_min_risk_C":min((actions[xy][12] for xy in valid),default=None),
                            prefix+"_mean_distance":sum(ds)/len(ds)}
                groups.append(dict(**ctx,slots=len(old),common=len(old.keys() & new.keys()),
                           set_equal=old.keys()==new.keys(),order_equal=list(old)==list(new),
                           recovered_direct=len(removed.intersection(ni["direct"])),
                           recovered_total=len(removed.intersection(new)),**stats(old,ol,"anchors"),**stats(new,nl,"center")))
    assert reproduced == historical and len(groups)==360 and len(checks)==360
    (ROOT/"diagnostic").mkdir(exist_ok=True)
    save("groups.csv",groups)
    save("candidates.csv",details)
    save("terminal_grid.csv",checks)


if __name__=="__main__":
    main()
