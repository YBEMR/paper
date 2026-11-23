"""Audit only recorded candidates, completed deployment scans and original request streams."""
from collections import Counter
import csv
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
P=json.loads((HERE/"protocol.json").read_bytes())


def read(path):
    return json.loads(path.read_bytes())


def load_events(path):
    rows=[]
    truncated=False
    with gzip.open(path,"rt",encoding="utf8") as stream:
        try:
            for line in stream:
                rows.append(json.loads(line))
        except EOFError:
            truncated=True
    return rows,truncated


def check(ok,message):
    if not ok:
        raise ValueError(message)


def csv_rows(path):
    with path.open(encoding="utf-8-sig",newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(name,rows):
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (HERE/name).open("w",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,fields,lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def verify_physical(p,ledger,identity,case):
    check(p["required"]==p["completed"]==len(ledger)==len({r["request_id"] for r in ledger})==500,
          "request coverage")
    packed=[[r["request_id"],r["app_id"],r["release_ns"],r["deadline_ns"]] for r in ledger]
    digest=sha256(json.dumps(packed,separators=(",",":")).encode()).hexdigest()
    check(digest==identity["request_sha256"]==case["request_sha"],"request digest")
    check(Counter(r["app_id"] for r in ledger)=={i:125 for i in range(4)},"per-network count")
    check(all(r["deadline_ns"]-r["release_ns"]==40000000 and
              r["release_ns"]<=r["completion_ns"]<=r["deadline_ns"] and
              r["slack_ns"]==r["deadline_ns"]-r["completion_ns"] for r in ledger),"deadline")
    check(p["fully_replayed"] and p["deadline_ok"] and
          abs(p["min_slack_ms"]-min(r["slack_ns"] for r in ledger)/1e6)<1e-12,"slack")
    inlet=[30.]*4
    low=high=np.array(inlet)
    frames=list(map(int,case["frames_execution_order"].split("/")))
    start=0
    energy=0.
    for j,s in enumerate(p["scene_rows"]):
        check(s["entry_c"]==inlet and s["start_ns"]==start and
              s["service_end_ns"]-start==frames[j]*40000000 and
              s["scene"]==case["scene_order"].split("/")[j],"thermal/time continuity")
        requests=[r for r in ledger if r["scene"]==s["scene"]]
        check(len(requests)==s["required"] and s["min_slack_ns"]==min(r["slack_ns"] for r in requests),
              "scene deadlines")
        inlet=s["final_c"]
        start=s["end_ns"]
        low=np.maximum(low,s["peak_lower_c"])
        high=np.maximum(high,s["peak_upper_c"])
        energy+=s["energy_j"]
    check(start==10040000000 and p["scene_rows"][-1]["service_end_ns"]==10000000000,"window")
    state="VIOLATION" if max(low)>80 else "SAFE" if max(high)<=80 else "UNRESOLVED"
    check(list(low)==p["peak_lower_c"] and list(high)==p["peak_upper_c"] and np.all(low<=high)
          and state==p["thermal_status"] and p["feasible"]==(state=="SAFE")
          and abs(energy-p["energy_j"])<=1e-7,"continuous certificate")


def main():
    cases={r["instance_id"]:r for r in csv_rows(ROOT/"research/ch3_final_experiments/derived/instances.csv")}
    catalog=read(ROOT/"research/kim_multidnn_expansion/catalog.json")
    metrics,trajectories,coverage,checks=[],[],[],[]
    for folder in sorted((HERE/"raw").iterdir()):
        if not (folder/"receipt.json").exists():
            continue
        receipt=read(folder/"receipt.json")
        job=read(folder/"job.json")
        check(receipt["config_sha256"]==sha256((HERE/"protocol.json").read_bytes()).hexdigest(),"config")
        check(receipt["exit_code"]==0 or receipt["hard_timeout"],"worker fault")
        events,truncated=load_events(folder/"events.jsonl.gz")
        accepted=[e for e in events if e["time_s"]<=P["accept_cutoff_s"]]
        identity=next(e["data"] for e in accepted if e["event"]=="identity")
        check(identity["domain"]==catalog["search_order"] and len(identity["domain"])==81 and
              identity["ambient"]==float(cases[job["case"]]["ambient_c"]) and
              identity["initial"]==[30]*4 and identity["limits"]==[80]*4,"case contract")
        check(len(identity["opps"])==27,"frequency domain")
        ledger={}
        certificates={}
        verified=0
        first=None
        best=None
        best_t=None
        def candidate(t,d,code,p):
            nonlocal first,best,best_t
            if p["thermal_status"]=="SAFE":
                if first is None: first=t
                if best is None or p["energy_j"]<best["physical"]["energy_j"]-1e-9:
                    best=dict(deployment=d,code=code,physical=p)
                    best_t=t
            trajectories.append(dict(unit=folder.name,time_s=t,deployment=d,code=code,
                                     status=p["thermal_status"],energy_j=p["energy_j"],
                                     peak_lower_c=max(p["peak_lower_c"]),peak_upper_c=max(p["peak_upper_c"]),
                                     best_safe_j=best["physical"]["energy_j"] if best else None))
        for e in accepted:
            d=e["data"]
            if e["event"]=="request_ledger":
                ledger[d["deployment"],d["code"]]=d["rows"]
            if e["event"]=="full_replay":
                c=d["choice"]
                key=c["deployment"],c["code"]
                verify_physical(c["physical"],ledger[key],identity,cases[job["case"]])
                verified+=1
                candidate(e["time_s"],*key,c["physical"])
            if e["event"]=="physical":
                key=d["dep"],tuple(d["indices"])
                verify_physical(d["physical"],d["completions"],identity,cases[job["case"]])
                certificates[key]=d["physical"]
                verified+=1
            if e["event"]=="kim_check":
                key=d["dep"],tuple(d["opps"])
                p=certificates[key]
                check(d["result"]["status"]==p["thermal_status"] and
                      abs(d["result"]["energy_j"]-p["energy_j"])<=1e-7,"Kim accepted result")
                code=sum(f*27**(3-i) for i,f in enumerate(d["opps"]))
                candidate(d["at_s"],d["dep"],code,p)
        row=dict(unit=folder.name,case=job["case"],method=job["method"],seed=job["seed"],
                 wall_s=receipt["wall_s"],timeout=receipt["hard_timeout"],gzip_truncated=truncated,
                 first_safe_s=first,best_safe_first_s=best_t,physical_certificates=verified)
        if best:
            p=best["physical"]
            row.update(safe_j=p["energy_j"],deployment=best["deployment"],code=best["code"],
                       opps="/".join(s["opp"] for s in p["scene_rows"]),peak_lower_c=max(p["peak_lower_c"]),
                       peak_upper_c=max(p["peak_upper_c"]),slack_ms=p["min_slack_ms"],completed=p["completed"])
        if job["method"]=="M2":
            tables={"energy":{},"fallback":{}}
            static={}
            final=None
            for e in accepted:
                d=e["data"]
                if e["event"]=="lower_bounds": static=d["values"]
                if e["event"]=="deployment":
                    tables[d["phase"]][d["deployment"]]=d
                    coverage.append(dict(unit=folder.name,case=job["case"],time_s=e["time_s"],**d))
                    if d["phase"]=="fallback":
                        with np.load(folder/d["arrays"],allow_pickle=False) as data:
                            energy,state=data["energy_j"],data["status"]
                            check(energy.shape==state.shape==(27**4,) and
                                  sha256(np.ascontiguousarray(energy).tobytes()).hexdigest()==d["energy_sha256"] and
                                  sha256(np.ascontiguousarray(state).tobytes()).hexdigest()==d["status_sha256"],
                                  "stored arrays")
                            check(np.array_equal(np.isfinite(energy),state!=0),"deadline energy mask")
                            check(all(int(np.sum(state==i))==d[k] for i,k in
                                      [(1,"safe"),(2,"overtemp"),(3,"unresolved")]),"classifications")
                            exact=float(energy[state==1].min()) if d["safe"] else None
                            check((exact is None and d["strict_min_j"] is None) or
                                  (exact is not None and abs(exact-d["strict_min_j"])<1e-9),"local safe minimum")
                if e["event"]=="certificate":
                    final=e
            bounds=[]
            for dep in catalog["search_order"]:
                e=tables["energy"].get(dep)
                f=tables["fallback"].get(dep)
                if f and not f["unresolved"]:
                    if f["strict_min_j"] is not None: bounds.append(f["strict_min_j"])
                elif e:
                    if e["strict_min_j"] is not None: bounds.append(e["strict_min_j"])
                else: bounds.append(static.get(dep,0.))
            lb=min(bounds,default=None)
            row.update(energy_coverage=len(tables["energy"]),thermal_coverage=len(tables["fallback"]),
                       lower_bound_j=lb,certificate_s=final["time_s"] if final else None,
                       certificate=bool(final),fallbacks=sum(e["event"]=="policy_fallback" for e in accepted),
                       legal_codes_energy=sum(d["legal"] for d in tables["energy"].values()),
                       safe_codes_classified=sum(d["safe"] for d in tables["fallback"].values()),
                       unresolved_classified=sum(d["unresolved"] for d in tables["fallback"].values()))
            if final:
                check(final["data"]["n"]==81 and not final["data"]["unresolved"] and
                      len(tables["energy"])==81 and len(tables["fallback"])==81,"full high-temperature certificate")
                check(best is not None and abs(lb-best["physical"]["energy_j"])<=1e-7,"global bracket")
                row["status"]="OPTIMAL"
            else:
                row["status"]="SAFE_PARTIAL" if best else "NO_SAFE_WITHIN_BUDGET"
            row["gap_j"]=best["physical"]["energy_j"]-lb if best and lb is not None else None
            laststats=next((e["data"]["stats"] for e in reversed(accepted) if "stats" in e["data"]),{})
            row.update({f"cost_{k}":v for k,v in laststats.items() if k.endswith("_s")})
        else:
            result=next((e["data"] for e in accepted if e["event"]=="result"),None)
            pool=next((e["data"] for e in accepted if e["event"]=="kim_pool"),None)
            attempted=[e["data"] for e in accepted if e["event"]=="kim_check"]
            row.update(status="SAFE" if best else "NO_SAFE_WITHIN_BUDGET",certificate=False,
                       total_checks=len(attempted),rejected=sum(d["result"]["status"]!="SAFE" for d in attempted),
                       first_candidate=attempted[0]["dep"] if attempted else None,
                       first_status=attempted[0]["result"]["status"] if attempted else None,
                       first_peak_lower_c=max(attempted[0]["result"]["lower"]) if attempted else None,
                       generations=sum(e["event"]=="kim_generation" for e in accepted),
                       visited_deployments=pool["unique_deployments"] if pool else None,
                       pool_stop=pool["reason"] if pool else None,stop=result["reason"] if result else None)
        metrics.append(row)
        checks.append(dict(unit=folder.name,verified_physical=verified,archive_truncated=truncated,
                           execution_commit=receipt["execution_commit"],request_sha256=identity["request_sha256"]))
    write_csv("run_results.csv",metrics)
    write_csv("safe_progress.csv",trajectories)
    write_csv("deployment_coverage.csv",coverage)
    (HERE/"verification.json").write_bytes((json.dumps(checks,indent=2)+"\n").encode())
    for r in metrics:
        print(r["unit"],r["status"],r.get("safe_j"),r.get("deployment"),
              r.get("thermal_coverage"),r.get("rejected"))


if __name__=="__main__":
    main()
