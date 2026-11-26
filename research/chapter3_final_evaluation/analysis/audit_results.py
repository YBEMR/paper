"""Read immutable receipts and verify completed endpoints against the archived P1 evidence."""
import csv
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from formal_batch import ROOT,OUT,CASES,MAIN,SEEDS,roster,read
from setup_inputs import checked_problem
from model import transitions,independent_events
from heat import evaluate

RESULTS=ROOT/"results"
THERMAL=("S80","D1","D2")


def save(name, rows, fields=None):
    RESULTS.mkdir(exist_ok=True)
    if not rows and not fields:
        raise ValueError("Empty table requires an explicit schema: "+name)
    keys=fields or list(dict.fromkeys(k for r in rows for k in r))
    with (RESULTS/name).open("w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=keys,lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def rows_of(path):
    return [json.loads(line) for line in path.read_bytes().splitlines() if line] if path.is_file() else []


def plan_for(base,h):
    raw=gzip.decompress((base/"plans"/(h+".json.gz")).read_bytes())
    if hashlib.sha256(raw).hexdigest()!=h:
        raise ValueError("Plan hash mismatch: "+h)
    o=json.loads(raw)
    return list(map(tuple,o["rows"])),frozenset(map(tuple,o["low"]))


def verify_final(folder,res,p):
    final=res["final"]
    h=final["plan"]
    base=folder/"evidence"
    plan=plan_for(base,h)
    schedule=read(folder/"final_schedule.json")
    assert schedule["plan"]==h and [tuple((r["unit"],r["frequency"],r["start"])) for r in schedule["tasks"]]==plan[0]
    assert [r["end"] for r in schedule["tasks"]]==[p.finish(i,row) for i,row in enumerate(plan[0])]
    assert sorted(map(tuple,schedule["low"]))==sorted(plan[1])
    events,sw=independent_events(p,*plan)
    assert sw==transitions(p,*plan)[1]==list(map(tuple,schedule["switches"]))
    cert=read(base/"certificates"/(h+".json"))
    assert cert["plan"]==h and cert["case"]==p.case and cert["metrics"]["status"]==final["status"]
    with np.load(base/"certificates"/(h+".npz"),allow_pickle=False) as data:
        trajectory=data["events"]
    assert np.array_equal(trajectory[:,:14],events) and trajectory.shape[1]==31
    assert np.allclose(trajectory[:-1,18:22],trajectory[1:,14:18],rtol=0,atol=1e-9)
    m=evaluate(p,plan,cert=True)
    assert m["status"]==final["status"] and np.allclose(m["E_bounds"],final["bounds"],rtol=0,atol=1e-10)
    assert abs(sum(final[n] for n in ("activity","residency","switch","temperature","public"))-final["J"])<1e-8


def collect(require_end=True):
    cases={c:checked_problem(c) for c in CASES}
    lock=read(ROOT/"execution_lock.json")
    subject=read(ROOT/"publication_freeze.json")["remote_protocol_commit"]
    records=[]
    native=[]
    if require_end and (not (OUT/"batch_end.json").is_file() or read(OUT/"batch_end.json")["outcome"]!="FINISHED"):
        raise RuntimeError("The formal batch is still open")
    for job in lock["roster"]:
        folder=OUT/"cells"/job["id"]
        row=dict(**job,receipt="NOT_STARTED",actual_status="",status="PENDING")
        records.append(row)
        if not (folder/"receipt.json").exists():
            if (folder/"start.json").exists():
                row["receipt"]="OPEN"
            continue
        receipt=read(folder/"receipt.json")
        assert receipt["subject"]==subject and all(receipt[k]==v for k,v in job.items())
        row.update(receipt=receipt["status"],wall_s=receipt["wall_s"],charged_s=receipt["charged_s"],
                   init_charge_s=receipt["prior_charge_s"],cpu=receipt["cpu"])
        if receipt["status"]!="COMPLETE":
            row["status"]=receipt["status"]
            continue
        res=read(folder/"result.json")
        assert all(job[k]==res[k] for k in ("case","method","mode","seed","budget_s"))
        row.update(status=res["status"],actual_status=res["status"],post_s=res["post"]["elapsed_s"],
                   worker_elapsed_s=res["elapsed_s"],calls=res["assessments"],post_rounds=res["post"]["rounds"])
        flags=[]
        if receipt["charged_s"]>job["budget_s"]:
            flags.append("WALL_OVERRUN")
        if res["elapsed_s"]>job["budget_s"]:
            flags.append("COMPUTE_OVERRUN")
        if row["post_s"]>job["budget_s"]*.2:
            flags.append("POST_OVERRUN")
        for stage in ("initial","configuration","selected"):
            val=res[stage]
            if val:
                row[stage+"_J"]=val["J"]
                row[stage+"_plan"]=val["plan"]
                row[stage+"_status"]=val["status"]
        if res["initial"] and res["configuration"] and res["selected"]:
            row["config_gain_J"]=res["initial"]["J"]-res["configuration"]["J"]
            row["post_gain_J"]=res["configuration"]["J"]-res["selected"]["J"]
        native_scores=[]
        for idx,entry in enumerate(res["native"]):
            val=entry.get("score") or {}
            native.append(dict(id=job["id"],case=job["case"],method=job["method"],seed=job["seed"],entry=idx,
                  source=entry["source"],origin=entry.get("origin"),construction_status=entry.get("status"),
                  level=entry.get("level"),plan=val.get("plan"),energy_J=val.get("J"),thermal_status=val.get("status"),
                  stages=entry.get("stages",entry.get("depth")),in_time=val.get("in_time")))
            if val.get("eligible") and val.get("in_time") and entry.get("origin")!="common-only":
                native_scores.append(val)
        if res["native"]:
            row["native_best_J"]=min((s["J"] for s in native_scores),default=None)
            row["configuration_source"]=("native" if any(s["plan"]==row.get("configuration_plan") for s in native_scores)
                          else "common" if row.get("initial_plan") and row.get("initial_plan")==row.get("configuration_plan")
                          else "other" if row.get("configuration_plan") else "none")
        fin=res["final"]
        if fin:
            verify_final(folder,res,cases[job["case"]])
            row.update(plan=fin["plan"],actual_J=fin["J"],actual_lo=fin["bounds"][0],actual_hi=fin["bounds"][1],
                   peak_lo=fin["peak_lower"],peak_hi=fin["peak_upper"],deadline_slack_ms=fin["slack_ms"],
                   **{k+"_J":fin[k] for k in ("activity","residency","switch","temperature","public")})
        row["protocol_flags"]=" ".join(flags)
        if flags:
            row["status"]="PROTOCOL_DEVIATION"
        if fin and row["status"]=="SAFE":
            row["SAFE_J"]=fin["J"]
    if require_end and any(r["receipt"] in ("NOT_STARTED","OPEN") for r in records):
        raise RuntimeError("Batch closure and per-cell receipt set disagree")
    by={(r["case"],r["method"],r["mode"],r["seed"]):r for r in records}
    saved_init=defaultdict(set)
    for r in records:
        if r.get("initial_plan") and r["mode"]=="T3":
            saved_init[r["case"]].add(r["initial_plan"])
    assert all(len(plans)<=1 for plans in saved_init.values()),saved_init
    logical=[]
    for r in records:
        category="thermal" if r["mode"]!="T3" else "ablation_supplement" if r["method"]=="Compact" else "main"
        logical.append(dict(comparison=category,reused=0,**r))
        if r["method"]=="Proposed" and r["mode"]=="T3" and r["case"] in THERMAL:
            logical.append(dict(comparison="thermal",reused=1,**r))
    assert len(records)==165 and len(logical)==174
    save("endpoints.csv",records)
    save("logical_positions.csv",logical)
    save("native_construction.csv",native, list(native[0]) if native else ["id","source","status"])
    bounds={r["case"]:float(r["lower_J"]) for r in csv.DictReader((HERE/"full_domain_bounds.csv").open())}
    quality=[]
    for case in CASES:
        eligible=[r for r in records if r["case"]==case and r.get("SAFE_J") is not None and r["mode"]=="T3" and r["method"] in MAIN]
        best=min(eligible,key=lambda r:r["actual_hi"],default=None)
        u=best["actual_hi"] if best else None
        l=bounds[case]
        assert u is None or u>=l
        quality.append(dict(case=case,lower_J=l,best_SAFE_upper_J=u,method=best and best["method"],seed=best and best["seed"],
              plan=best and best["plan"],absolute_gap_J=(u-l if u is not None else None),
              gap_pct_of_upper=(100*(u-l)/u if u is not None else None)))
    save("quality.csv",quality)
    paired=[]
    for case in CASES:
        for seed in SEEDS:
            pro=by[case,"Proposed","T3",seed]
            for method in MAIN[:-1]:
                base=by[case,method,"T3",seed]
                ok=pro["status"]==base["status"]=="SAFE"
                verdict=("strict_win" if pro["actual_hi"]<base["actual_lo"] else "strict_loss" if base["actual_hi"]<pro["actual_lo"]
                         else "same_plan" if pro["plan"]==base["plan"] else "overlap") if ok else "unpaired"
                paired.append(dict(case=case,seed=seed,baseline=method,proposed_status=pro["status"],baseline_status=base["status"],
                      savings_pct=(100*(base["SAFE_J"]-pro["SAFE_J"])/base["SAFE_J"] if ok else None),verdict=verdict))
    save("paired_savings.csv",paired)
    return records,logical

if __name__=="__main__":
    collect()
