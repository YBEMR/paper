"""Nonthermal pool, isolated mode scoring and final common certificate export."""
import gzip
import json
from time import perf_counter
from setup_inputs import ROOT, G2, sha, g1io
from assets import Layout, assemble, idle_plan, write, read, record
from algorithm import load_at
from fifo import Compact
from heat import evaluate
from model import independent_events, transitions, event_arrays
from validation import common_grid
import numpy as np


def make_pool(p, model, until, folder):
    """The producer never imports or consults candidate temperature or SAFE flags."""
    entries = []
    begin = perf_counter()
    legacy, depth = model.f.search(1024, True, begin + .35 * max(0, until-begin-2))
    def add(plan, name, width, depth):
        row = dict(generator=name, width=width, depth=depth)
        if plan is not None:
            transitions(p, *plan)
            independent_events(p, *plan)
            key = g1io.store(p, plan)
            row["plan"] = key
            row["in_time"] = perf_counter() <= until
        entries.append(row)
        write(folder/"pool.json", entries)
    add(legacy, "G1", 1024, depth)
    for width, priced in ((1,False),(32,True),(128,True),(256,False),(512,True)):
        if perf_counter() >= until-2:
            break
        cfg, depth = model.construct(width, until-2, priced)
        plan = idle_plan(p, assemble(p, cfg)) if cfg is not None else None
        add(plan, "G2", width, depth)
    return entries


def assess_mode(p, plan, mode, folder, expected_switches=None):
    rows, low = plan
    key = g1io.store(p, plan)
    path = folder/"scores"/(key+".json")
    if expected_switches is not None:
        assert transitions(p, rows, low)[1] == expected_switches
    if path.exists():
        return read(path)
    if mode == "T3":
        _, cert = g1io.assess(p, plan, expected_switches=expected_switches)
        m = cert["metrics"]
        result = dict(plan=key, status=m["status"], J=m["E_J"], bounds=m["E_bounds"],
                      eligible=m["status"]=="SAFE")
    else:
        a, sw, _ = event_arrays(p,rows,low)
        b, check = independent_events(p,rows,low)
        x,y = common_grid(a,b)
        assert sw == check and np.array_equal(x,y)
        if mode == "T0":
            parts = Layout(p,rows).components(low)
            exact = sum(parts.values())
            val = float(exact)
            result = dict(plan=key,status="NONTHERMAL_LEGAL",J=val,
                          bounds=[float(np.nextafter(val,-np.inf)),float(np.nextafter(val,np.inf))],
                          eligible=True,exact=str(exact))
        else:
            m = evaluate(p,plan,cert=True,reset=mode=="T2")
            if mode == "T1":
                inside = min(m["minimum_lo"])>=20 and max(m["peak_hi"])<=100
                resolved = m["E_bounds"][1]-m["E_bounds"][0]<=2e-6 and max(m["peak_hi"])-max(m["peak_lo"])<=.001
                eligible = bool(inside and resolved)
                status = "IN_MODEL" if eligible else "OUT_OF_MODEL" if m["status"]=="OUT_OF_MODEL" else "UNRESOLVED"
            else:
                status = m["status"]
                eligible = status=="SAFE"
            result = dict(plan=key,status=status,J=m["E_J"],bounds=m["E_bounds"],eligible=eligible)
    write(path,result)
    return result


def best_in_pool(p, source, mode, folder):
    seen = set()
    choices = []
    best = None
    for item in read(source/"pool.json"):
        key = item.get("plan")
        if not key or not item["in_time"] or key in seen:
            continue
        seen.add(key)
        plan = load_at(source/"evidence", key)
        score = assess_mode(p,plan,mode,folder)
        choices.append(score)
        if score["eligible"] and (best is None or score["bounds"][1]<best["bounds"][0]):
            best = score
    write(folder/"initial_choices.json", choices)
    return best


def certify_output(p, best, folder):
    plan = load_at(folder/"evidence", best["plan"])
    key, cert = g1io.assess(p, plan)
    m = cert["metrics"]
    tasks = [dict(request=i//3,stage=("pre","main","post")[i%3],unit=u,
                  frequency=k,start=t,end=p.finish(i,(u,k,t))) for i,(u,k,t) in enumerate(plan[0])]
    write(folder/"final_schedule.json",dict(plan=key,tasks=tasks,low=sorted(plan[1]),switches=cert["switches"]))
    return dict(plan=key,status=m["status"],J=m["E_J"],bounds=m["E_bounds"],
                peak_upper=max(m["peak_hi"]),peak_lower=max(m["peak_lo"]),slack_ms=m["min_deadline_slack_ms"],
                activity=m["activity_J"],residency=m["base_J"],switch=m["switch_J"],
                temperature=m["temperature_J"],public=m["external_J"])
