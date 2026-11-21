"""Rebuild formal result tables from the thirty raw archives and pinned CT reference rows."""
import argparse
from collections import Counter,defaultdict
import csv
import hashlib
import json
from math import isclose
from pathlib import Path
from statistics import mean,median
import tarfile

from run_formal import HERE, METHODS, SEEDS, config, jobs, records, sha

OUT=HERE/"tables"


def write(name,rows):
    cols=list(dict.fromkeys(k for row in rows for k in row))
    with (OUT/(name+".csv")).open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,cols);w.writeheader();w.writerows(rows)


def check(condition,message):
    if not condition:
        raise ValueError(message)


def code(freqs):
    n=0
    for i in freqs:n=n*27+i
    return n


def unpack(path):
    items={}
    digests={}
    with tarfile.open(path,"r|xz") as arc:
        for entry in arc:
            data=arc.extractfile(entry).read()
            if entry.name=="member_sha256.json":
                expected=json.loads(data)
            else:
                digests[entry.name]=hashlib.sha256(data).hexdigest()
                uid,name=entry.name.split("/")
                items.setdefault(uid,{})[name]=data
    check(digests==expected,"archive member digest: "+path.name)
    return items


def reference_rows(root):
    metrics=records(root/"research/kim_multidnn_search_trial/results/run_metrics.csv")
    inst={r["instance_id"]:r for r in records(HERE.parent/"derived/instances.csv")}
    src=records(HERE.parent/"derived/method_results.csv")
    refs={}
    for case,size in dict.fromkeys((c,n) for c,n,_,_ in jobs()):
        row=next(r for r in src if r["run_id"]==f"{case}|CT-Joint|{size}")
        energy=float(row["best_safe_energy_j"])
        wall=None
        if size==81:
            m=next(r for r in metrics if r["case"]==case and r["method"]=="M2" and r["scope"]=="catalog")
            check(m["status"]=="PASS" and float(m["best_safe_j"])==energy and m["winner"]==row["mapping_id"],"M2 reference")
            wall=float(m["wall_s"])
        refs[case,size]=dict(group="AB" if size==81 else "FG",case=case,domain=size,method="CT-Joint",
            seed="",unit="",request_sha256=inst[case]["request_sha"],outcome="SAFE",stop="exact_certificate",
            winner_dep=row["mapping_id"],opp_code=row["frequency_code"],safe_energy_j=energy,
            exact_energy_j=energy,gap_pct=0.,saving_vs_method_pct=0.,peak_upper_c=float(row["peak_upper_c"]),
            margin_c=float(row["thermal_margin_c"]),min_slack_ms=float(row["min_slack_ms"]),completed=500,
            first_safe_s=row["first_safe_s"],wall_s=wall,certificate_s=row["certificate_s"],
            source=row["source_path"],cpu_scope="archive",certificate=row["cert_scope"])
    return refs


def request_streams(root):
    # Reconstruct only the workload. Scheduling and thermal kernels are never invoked here.
    from evaluator import load_frozen
    unit=load_frozen(root)
    cases={c["id"]:c for c in unit.design.cases()}
    signals={}
    for r in records(HERE.parent/"derived/instances.csv"):
        case=r["instance_id"]
        if case not in {j[0] for j in jobs()}:
            continue
        scenes=unit.design.make_scenes(cases[case])
        unit.verify_stream(scenes,dict(request_stream_sha256=r["request_sha"],scene_order=r["scene_order"].split("/"),
                                      frames_in_execution_order=list(map(int,r["frames_execution_order"].split("/")))))
        signals[case]=scenes
    return signals


def verify_run(uid,files,path,job,ref,scenes):
    receipt=json.loads(files["receipt.json"])
    reservation=json.loads(files["reservation.json"])
    case,size,method,seed=job
    check(reservation["job"]==list(job) and reservation["cap_s"]==120 and
          reservation["runner_sha"]==sha(HERE/"run_formal.py") and
          reservation["config_sha"]==sha(HERE/"formal_experiment_config.csv"),uid+" reservation")
    row=dict(group=ref["group"],case=case,domain=size,method=method,seed=seed,unit=uid,
             request_sha256=ref["request_sha256"],outcome=receipt["state"].upper(),stop=receipt["state"],
             exact_energy_j=ref["exact_energy_j"],wall_s=receipt["elapsed_s"],source=f"archives/{path.name}#{uid}",
             cpu_scope="formal cold single logical CPU",certificate="checked individuals")
    if receipt["state"]!="finished":
        return row,None,[]
    check(hashlib.sha256(files["result.json"]).hexdigest()==receipt["result_sha"],uid+" receipt")
    result=json.loads(files["result.json"])
    idn=result["identity"];s=result["summary"];rule=config(job)
    check((idn["case"],idn["domain"],idn["method"],idn["seed"],idn["request_sha256"])==
          (*job,ref["request_sha256"]) and len(set(idn["allowed"]))==size and
          idn["pool_size"]==int(rule["population"]) and idn["max_generations"]==int(rule["max_generations"]),uid+" identity")
    check(idn["config_sha"]==reservation["config_sha"] and idn["runner_sha"]==reservation["runner_sha"],uid+" hashes")
    opt=ref["exact_energy_j"]
    evaluated={};physical={};schedule_slack={};checks=[]
    counters=Counter();statuses=Counter()
    for line in files["events.jsonl"].splitlines():
        t,e,v=json.loads(line)
        if e=="completion_vector":
            key=tuple(v["key"])
            scene=scenes[key[1]]
            check(key not in schedule_slack and len(v["finish_ns"])==len(scene.requests),uid+" completion vector")
            slacks=[]
            for finish,req in zip(v["finish_ns"],scene.requests,strict=True):
                deadline=scene.start_ns+req.deadline_ns
                check(scene.start_ns+req.release_ns<=finish<=deadline<=scene.service_end_ns,uid+" individual deadline")
                slacks.append(deadline-finish)
            schedule_slack[key]=min(slacks)
        elif e=="physical":
            key=(v["dep"],*v["indices"])
            check(v["request_sha256"]==ref["request_sha256"] and key[0] in idn["allowed"],uid+" replay identity")
            p=v["physical"]
            check(p["required"]==500,uid+" required")
            if p["fully_replayed"]:
                check(p["completed"]==500 and p["scene_rows"][-1]["end_ns"]==10040000000 and
                      len(v["completion_keys"])==4 and all(tuple(k) in schedule_slack for k in v["completion_keys"]),
                      uid+" full-window evidence")
                previous=[30.]*4
                for j,(scene,sr,ckey) in enumerate(zip(scenes,p["scene_rows"],v["completion_keys"],strict=True)):
                    check(tuple(ckey)==(v["dep"],j,v["indices"][j]) and sr["entry_c"]==previous and
                          sr["min_slack_ns"]==schedule_slack[tuple(ckey)] and
                          (sr["scene"],sr["start_ns"],sr["end_ns"])==(scene.name,scene.start_ns,scene.end_ns),
                          uid+" scene identity/inlet/slack")
                    previous=sr["final_c"]
                check(isclose(sum(x["energy_j"] for x in p["scene_rows"]),p["energy_j"],abs_tol=1e-7,rel_tol=0),uid+" energy")
            physical[key]=p
        elif e in ("ga_position","kim_check"):
            key=tuple(v["genome"]) if e=="ga_position" else (v["dep"],*v["opps"])
            z=v["result"];p=physical[key]
            check(z["energy_j"]==p["energy_j"] and z["completed"]==p["completed"] and
                  z["status"]==(p["thermal_status"] if p["fully_replayed"] else "DEADLINE"),uid+" candidate")
            if z["status"]=="SAFE":
                check(max(z["upper"])<=80. and z["slack_ms"]>=0 and z["energy_j"]>=opt-1e-7,uid+" certificate contradicted")
            if not v.get("hit"):
                check(key not in evaluated,uid+" duplicate candidate")
                evaluated[key]=z
                statuses[z["status"]]+=1
            counters["positions"]+=1
            if e=="kim_check":
                checks.append((key,z))
        elif e in ("ga_start","check_start"):
            counters["started"]+=1
    win=s["winner"]
    if win is not None:
        key=tuple(win) if method=="Thermal-GA" else (win[0],*win[1])
        z=evaluated[key];energy=z["energy_j"]
        check(z["status"]=="SAFE",uid+" selected witness")
        if method=="Thermal-GA":
            check(energy==min(w["energy_j"] for w in evaluated.values() if w["status"]=="SAFE"),uid+" GA winner")
        row.update(outcome="SAFE",winner_dep=key[0],opp_code=code(key[1:]),safe_energy_j=energy,
                   gap_pct=max(0,100*(energy-opt)/opt),saving_vs_method_pct=max(0,100*(energy-opt)/energy),
                   peak_lower_c=max(z["lower"]),peak_upper_c=max(z["upper"]),margin_c=80-max(z["upper"]),
                   min_slack_ms=z["slack_ms"],completed=z["completed"])
    else:
        row["outcome"]=checks[0][1]["status"] if method=="Kim-Adapt" and checks else "NO_SAFE_FOUND"
    row.update(stop=s["reason"],first_safe_s=s.get("first_safe_s"),unique_started=counters["started"],
               unique_completed=len(evaluated),safe_evals=statuses["SAFE"],overtemp_evals=statuses["VIOLATION"],
               deadline_evals=statuses["DEADLINE"],unresolved_evals=statuses["UNRESOLVED"])
    diag=result["best_failed_diagnostic"]
    if diag:
        z=diag["result"];key=diag["genome"]
        row.update(diagnostic_dep=key[0],diagnostic_code=code(key[1:]),diagnostic_status=z["status"],
                   diagnostic_energy_j=z["energy_j"],diagnostic_peak_upper_c=max(z["upper"]) if z["upper"] else None,
                   diagnostic_min_slack_ms=z["slack_ms"],diagnostic_completed=z["completed"])
    if method=="Thermal-GA":
        check(len(evaluated)==s["unique_completed"] and counters["started"]==s["unique_started"] and
              statuses==Counter(s["unique_status_counts"]),uid+" GA counts")
        row.update(generations=s["completed_generations"],total_positions=s["positions"],cache_hits=s["hits"])
        return row,None,[]
    info=s["pool"]
    check(len(checks)==len(s["attempts"]) and len(checks)<=int(rule["max_total_checks"]),uid+" fallback count")
    ranking=[(e[0],*e[1]) for e in info["pool"]]
    check([k for k,z in checks]==ranking[:len(checks)],uid+" pool order")
    row.update(unique_deployments=info["unique_deployments"],pool_size=len(ranking),pool_sha256=info["pool_sha256"],
               pool_stop=info["reason"],total_positions=info["counts"]["positions"],checks=len(checks))
    detail=[dict(unit=uid,case=case,domain=size,method=method,seed=seed,rank=i,dep=k[0],opp_code=code(k[1:]),
                 status=z["status"],actual_energy_j=z["energy_j"],peak_upper_c=max(z["upper"]) if z["upper"] else None,
                 min_slack_ms=z["slack_ms"],completed=z["completed"]) for i,(k,z) in enumerate(checks,1)]
    return row,info,detail


def summarize(root):
    OUT.mkdir(exist_ok=True)
    refs=reference_rows(root)
    streams=request_streams(root)
    rows=[];checks=[];pools={};pairs=[]
    for i in range(0,len(jobs()),3):
        path=HERE/"archives"/f"u{i:03d}-u{i+2:03d}.tar.xz"
        group=unpack(path)
        for j in range(i,i+3):
            uid=f"u{j:03d}";job=jobs()[j]
            row,pool,detail=verify_run(uid,group[uid],path,job,refs[job[:2]],streams[job[0]])
            rows.append(row);checks.extend(detail)
            if pool is not None:pools[job]=pool
        a,b,_=rows[-3:]
        case,n,_,seed=jobs()[i]
        x=pools.get((case,n,METHODS[0],seed));y=pools.get((case,n,METHODS[1],seed))
        equal=bool(x and y and x["pool"]==y["pool"] and x["pool_sha256"]==y["pool_sha256"])
        pairs.append(dict(case=case,domain=n,seed=seed,identical_pool=equal,plain_sha=a.get("pool_sha256"),
                          enhanced_sha=b.get("pool_sha256"),plain_outcome=a["outcome"],enhanced_outcome=b["outcome"],
                          enhanced_checks=b.get("checks"),plain_gap_pct=a.get("gap_pct"),enhanced_gap_pct=b.get("gap_pct")))
    check(len(rows)==90 and len(pairs)==30 and len(refs)==6,"matrix size")
    diagnostics=[]
    for r in rows:
        if r.get("diagnostic_status") or r["outcome"]!="SAFE":
            diagnostics.append({k:r.get(k) for k in ("group","case","domain","method","seed","unit","outcome",
                "stop","unique_completed","overtemp_evals","deadline_evals","unresolved_evals",
                "diagnostic_status","diagnostic_dep","diagnostic_code","diagnostic_energy_j",
                "diagnostic_peak_upper_c","diagnostic_min_slack_ms","diagnostic_completed","source")})
    if diagnostics:
        write("non_safe_diagnostics",diagnostics)
    rows.extend(refs.values());write("run_results",rows);write("kim_pairing",pairs);write("kim_checks",checks)
    groups=defaultdict(list)
    for row in rows:groups[row["group"],row["case"],row["domain"],row["method"]].append(row)
    summary=[]
    for (group,case,size,method),rs in groups.items():
        safe=[r for r in rs if r["outcome"]=="SAFE"]
        def stat(field,func):
            values=[float(r[field]) for r in safe if r.get(field) not in (None,"")]
            return func(values) if values else None
        walls=[float(r["wall_s"]) for r in rs if r.get("wall_s") not in (None,"")]
        summary.append(dict(group=group,case=case,domain=size,method=method,n=len(rs),safe=len(safe),
            energy_mean_j=stat("safe_energy_j",mean),energy_min_j=stat("safe_energy_j",min),
            energy_max_j=stat("safe_energy_j",max),gap_mean_pct=stat("gap_pct",mean),gap_max_pct=stat("gap_pct",max),
            margin_min_c=stat("margin_c",min),slack_min_ms=stat("min_slack_ms",min),
            wall_median_s=median(walls) if walls else None,stops=json.dumps(dict(Counter(r["stop"] for r in rs))),
            outcomes=json.dumps(dict(Counter(r["outcome"] for r in rs)))))
    write("comparison_summary",summary)
    for fig,g in (("A","AB"),("G","FG")):
        write("fig"+fig,[{k:r.get(k) for k in ("case","domain","method","seed","unit","outcome","safe_energy_j","exact_energy_j",
               "gap_pct","peak_upper_c","margin_c","min_slack_ms","source")} for r in rows if r["group"]==g])
    for fig,g in (("B","AB"),("F","FG")):
        write("fig"+fig,[{k:r[k] for k in ("case","domain","method","n","safe","outcomes","stops")}
                          for r in summary if r["group"]==g])


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source-root",type=Path,required=True)
    summarize(p.parse_args().source_root.resolve())
