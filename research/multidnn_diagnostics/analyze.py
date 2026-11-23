"""Read and verify archived outputs only. No scheduling/thermal calls after budget."""
import csv
import gzip
from hashlib import sha256
import json
from math import inf, isfinite
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REVIEW = ROOT / "research/multidnn_model_review"
TOL = 1e-7


def read(p):
    return json.loads(p.read_bytes())


def dump(p, value):
    p.write_bytes((json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode())


def table(name, rows):
    if not rows:
        return
    with (HERE/name).open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def load_events(directory):
    rows=[]
    discarded=0
    with gzip.open(directory/"events.jsonl.gz","rt",encoding="utf-8") as f:
        for line in f:
            try:
                x=json.loads(line)
            except json.JSONDecodeError:
                discarded += 1
                continue
            if x["t_s"] <= 120:
                rows.append(x)
            else:
                discarded += 1
    return rows,discarded


def verify_certificate(data, case, stream, domain):
    p=data["physical"]
    assert data["deployment"] in domain["deployments"]
    assert len(data["opps"]) == 4
    assert all(o in {"".join(x) for x in domain["clock_policy"]["constant_opp_levels"]} for o in data["opps"])
    assert p["fully_replayed"] and p["deadline_ok"]
    assert p["required"] == p["completed"] == case["required"]
    ledger=data["ledger"]
    assert len(ledger) == len({r[0] for r in ledger}) == case["required"]
    expected={q[0]:q for q in stream["requests"]}
    for ident,app,scene,release,due,complete in ledger:
        assert expected[ident] == [ident,app,release,due]
        assert release <= complete <= due
        s=stream["scenes"][scene]
        assert s["start_ns"] <= release < s["service_end_ns"]
    slack=min(row[4]-row[5] for row in ledger)/1e6
    assert abs(slack-p["min_slack_ms"]) <= 1e-12
    scenes=p["scene_rows"]
    assert len(scenes)==4 and scenes[-1]["end_ns"]==10_040_000_000
    assert scenes[0]["entry_c"] == case["initial_c"]
    for before,after in zip(scenes,scenes[1:]):
        assert before["final_c"]==after["entry_c"]
        assert before["end_ns"]==after["start_ns"]
    for i,s in enumerate(scenes):
        original=stream["scenes"][i]
        assert (s["start_ns"],s["service_end_ns"],s["end_ns"]) == (
            original["start_ns"],original["service_end_ns"],original["end_ns"])
    assert all(a<=b+1e-8 for a,b in zip(p["peak_lower_c"],p["peak_upper_c"]))
    assert abs(sum(s["energy_j"] for s in scenes)-p["energy_j"])<=TOL
    components=data["energy_components"]
    energy=sum(c["common_J"]+c["transfer_J"]+sum(c["idle_J"])+sum(c["activity_J"])+sum(c["leakage_J"])
               for c in components)
    assert len(components)==4 and abs(energy-p["energy_j"])<=TOL
    if p["thermal_status"]=="SAFE":
        assert p["feasible"] and max(p["peak_upper_c"])<=80
    if p["thermal_status"]=="VIOLATION":
        assert not p["feasible"] and max(p["peak_lower_c"])>80


def summarize(directory):
    case=read(REVIEW/"inputs/cases"/(directory.name+".json"))
    stream=read(REVIEW/case["input_stream"])
    domain=read(REVIEW/case["domain"])
    events,discarded=load_events(directory)
    assert not [e for e in events if e["kind"]=="error"]
    certificates=[e for e in events if e["kind"]=="physical_certificate"]
    for e in certificates:
        verify_certificate(e["data"],case,stream,domain)
    by_choice={(e["data"]["deployment"],tuple(e["data"]["opps"])):e for e in certificates}
    energy={e["data"]["deployment"]:e["data"] for e in events if e["kind"]=="deployment" and e["data"]["phase"]=="energy"}
    thermal={e["data"]["deployment"]:e["data"] for e in events if e["kind"]=="deployment" and e["data"]["phase"]=="fallback"}
    if thermal:
        import numpy as np
        for data in thermal.values():
            with np.load(directory/data["arrays"],allow_pickle=False) as saved:
                assert sha256(np.ascontiguousarray(saved["energy_j"]).tobytes()).hexdigest()==data["energy_sha256"]
                assert sha256(np.ascontiguousarray(saved["status"]).tobytes()).hexdigest()==data["status_sha256"]
                assert int(np.sum(saved["status"]==1))==data["safe"]
                assert int(np.sum(saved["status"]==2))==data["overtemp"]
                assert int(np.sum(saved["status"]==3))==data["unresolved"]
    options=[v["choice"] for v in energy.values() if v["choice"]]
    best0=None
    if options:
        floor=min(v["predicted_j"] for v in options)
        choice=min((v for v in options if v["predicted_j"]<=floor+1e-9),
                   key=lambda v:(v["deployment"],v["code"]))
        best0=by_choice[choice["deployment"],tuple(choice["opps"])]
    safe=[e for e in certificates if e["data"]["physical"]["feasible"]]
    best=min(safe,key=lambda e:e["data"]["physical"]["energy_j"],default=None)
    first=safe[0]["t_s"] if safe else None
    first_best=next((e["t_s"] for e in safe if abs(e["data"]["physical"]["energy_j"]-
                  best["data"]["physical"]["energy_j"])<=1e-9),None)
    complete=[e for e in events if e["kind"]=="certificate"]
    e0_complete=len(energy)==81
    proven_opt=bool(complete and complete[-1]["data"]["winner"])
    proven_no_safe=bool(complete and complete[-1]["data"]["winner"] is None)
    if proven_opt:
        winner=complete[-1]["data"]["winner"]
        assert abs(winner["physical"]["energy_j"]-best["data"]["physical"]["energy_j"])<=TOL
    e0p=best0["data"]["physical"] if best0 else None
    bestp=best["data"]["physical"] if best else None
    status="UNRESOLVED"
    if e0_complete and not options:
        status="PROVEN_DEADLINE_INFEASIBLE"
    elif e0_complete and e0p["feasible"]:
        status="NONBINDING_E0_SAFE"
    elif e0_complete and e0p["thermal_status"]=="VIOLATION" and best:
        status="UNSAFE_E0_SAFE_WITNESS"
        if proven_opt:
            status="ACTIVE_SAFE_ENERGY_PENALTY" if bestp["energy_j"]>e0p["energy_j"]+TOL else "SAFE_ENERGY_TIE"
    elif proven_no_safe:
        status="PROVEN_NO_SAFE"
    static=next((e["data"]["values"] for e in events if e["kind"]=="lower_bounds"),{})
    lower=dict(static)
    known_no_safe=set()
    known_safe={e["data"]["deployment"] for e in safe}
    deployment_rows=[]
    for d in domain["search_order"]:
        a,b=energy.get(d),thermal.get(d)
        if a:
            lower[d]=a["strict_min_j"] if a["legal"] else inf
            if not a["legal"]:
                known_no_safe.add(d)
        if b and not b["unresolved"]:
            lower[d]=b["strict_min_j"] if b["safe"] else inf
            if not b["safe"]:
                known_no_safe.add(d)
        assert d not in known_safe.intersection(known_no_safe)
        mine=by_choice.get((d,tuple(a["choice"]["opps"]))) if a and a["choice"] else None
        deployment_rows.append(dict(case_id=case["case_id"],deployment=d,
             energy_enumeration_complete=bool(a),thermal_classification_complete=bool(b),
             deadline_legal_sequences=a["legal"] if a else None,
             energy_min_j=a["strict_min_j"] if a else None,
             energy_min_status=mine["data"]["physical"]["thermal_status"] if mine else None,
             safe_sequences=b["safe"] if b else None,hot_sequences=b["overtemp"] if b else None,
             thermal_unresolved_sequences=b["unresolved"] if b else None,
             known_safe=d in known_safe,proven_no_safe=d in known_no_safe,
             energy_array_sha256=a.get("energy_sha256") if a else None,
             thermal_array_sha256=b.get("status_sha256") if b else None))
    lb=min(lower.values()) if len(lower)==81 else None
    if lb is not None and not isfinite(lb):
        lb=None
    if proven_opt:
        lb=complete[-1]["data"]["lower_bound_j"]
    bounds_gap=None if not bestp or lb is None or lb<=0 else 100*(bestp["energy_j"]-lb)/lb
    if bounds_gap is not None:
        assert bounds_gap >= -1e-6
    stop=read(directory/"exit.json")
    timing=events[-1]["timings"]
    calls=events[-1]["calls"]
    stats=next((e["data"]["stats"] for e in reversed(events) if "stats" in e["data"]),{})
    row=dict(case_id=case["case_id"],load=case["load"],order=case["order"],thermal_start=case["thermal_start"],
        requests=case["required"],diagnosis=status,
        e0_proven=e0_complete,e0_j=e0p["energy_j"] if e0p else None,
        e0_deployment=best0["data"]["deployment"] if best0 else None,
        e0_peak_upper_c=max(e0p["peak_upper_c"]) if e0p else None,
        e0_thermal_status=e0p["thermal_status"] if e0p else None,
        safe_optimum_proven=proven_opt,proven_no_safe=proven_no_safe,
        best_safe_j=bestp["energy_j"] if bestp else None,
        best_safe_deployment=best["data"]["deployment"] if best else None,
        best_safe_opps="/".join(best["data"]["opps"]) if best else None,
        best_safe_peak_c=max(bestp["peak_upper_c"]) if bestp else None,
        best_safe_thermal_margin_c=80-max(bestp["peak_upper_c"]) if bestp else None,
        best_safe_deadline_slack_ms=bestp["min_slack_ms"] if bestp else None,
        safe_energy_penalty_pct=100*(bestp["energy_j"]-e0p["energy_j"])/e0p["energy_j"] if bestp and e0p and proven_opt and e0_complete else None,
        valid_safe_lower_bound_j=lb,bound_gap_pct=bounds_gap,
        safe_deployments_lower=len(known_safe),safe_deployments_upper=81-len(known_no_safe),
        energy_deployments_completed=len(energy),thermal_deployments_completed=len(thermal),
        first_safe_s=first,best_safe_first_s=first_best,
        certificate_s=complete[-1]["t_s"] if complete else None,
        total_wall_s=stop["total_wall_s"],timed_out=bool(stop["hard_timeout"] or any(e["kind"]=="stopped" for e in events)),
        discarded_incomplete_or_late_lines=discarded)
    # Non-overlapping chart leaves; original inclusive statistics remain in raw logs.
    leaves=dict(case_id=case["case_id"],initialization_s=timing.get("initialization_s",0),
        event_schedule_s=timing.get("event_schedule_s",0),deadline_audit_s=timing.get("deadline_audit_s",0),
        kernel_thermal_s=timing.get("compile_thermal_s",0),
        kernel_other_s=max(0,timing.get("compile_inclusive_s",0)-timing.get("compile_thermal_s",0)),
        affine_search_s=stats.get("affine_search_s",0),peak_screen_s=timing.get("peak_screen_s",0),
        fallback_thermal_s=timing.get("fallback_thermal_s",0),certificate_thermal_s=timing.get("certificate_thermal_s",0),
        array_io_s=stats.get("array_io_s",0),lower_bound_s=stats.get("bounds_s",0))
    leaves["other_and_pending_s"]=max(0,stop["total_wall_s"]-sum(v for k,v in leaves.items() if k!="case_id"))
    leaves["total_wall_s"]=stop["total_wall_s"]
    leaves.update({f"calls_{k}":calls.get(k,0) for k in (
        "setfreq","event_schedule","deadline_screen","compile","compile_thermal","peak_screen_batches",
        "peak_screen_entries","fallback_thermal","certificate_thermal","full_certificate")})
    curve=[]
    incumbent=inf
    for e in safe:
        value=e["data"]["physical"]["energy_j"]
        if value < incumbent - 1e-9:
            incumbent=value
            curve.append(dict(case_id=case["case_id"],t_s=e["t_s"],safe_j=value,
                              deployment=e["data"]["deployment"]))
    return row,deployment_rows,leaves,curve,len(certificates)


def main():
    input_ok=all(sha256((REVIEW/k).read_bytes()).hexdigest()==v
                 for k,v in read(REVIEW/"input_manifest.json").items())
    execution_ok=all(sha256((ROOT/k).read_bytes()).hexdigest()==v
                     for k,v in read(HERE/"execution_manifest.json").items())
    assert input_ok and execution_ok, "Frozen input or executed source drift"
    cfg=read(REVIEW/"protocol.json")
    ids=[f"{l}_{o}_{t}" for l in cfg["loads"] for o in cfg["orders"]
         for t in ("reference_start","preheated")]
    rows,deployments,costs,curves=[],[],[],[]
    certs=0
    for ident in ids:
        row,dep,cost,curve,n=summarize(HERE/"raw"/ident)
        rows.append(row); deployments.extend(dep); costs.append(cost); curves.extend(curve); certs+=n
    table("summary.csv",rows)
    table("deployment_coverage.csv",deployments)
    table("costs.csv",costs)
    table("safe_progress.csv",curves)
    dump(HERE/"verification.json",dict(status="PASS_ARCHIVE_CHECK",case_count=len(rows),
         physical_certificates_checked=certs,deadline_ledgers_checked=certs,
         optimization_or_thermal_reexecution=False,
         input_files_unchanged=input_ok,execution_manifest_files_unchanged=execution_ok))
    dump(HERE/"summary.json",rows)
    for row in rows:
        print(row["case_id"],row["diagnosis"],row["e0_j"],row["best_safe_j"],
              row["safe_optimum_proven"],round(row["total_wall_s"],3))


if __name__=="__main__":
    main()
