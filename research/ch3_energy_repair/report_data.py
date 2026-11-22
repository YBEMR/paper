"""Verify replay evidence, derive per-run and same-clock paired results from six arms."""
import argparse
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
from itertools import groupby
import json
from pathlib import Path
from statistics import mean, median
import sys
import tarfile

from run import CASES, CFG, HERE, digest, encode


def csv_rows(path):
    with path.open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path,rows):
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,list(dict.fromkeys(k for row in rows for k in row)),lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def average(values):
    values=[v for v in values if v is not None]
    return mean(values) if values else None


def members(tar,slot):
    rec=json.load(tar.extractfile(slot+"/receipt.json"))
    data={n:tar.extractfile(slot+"/"+n).read() for n in rec["files"]}
    for n,b in data.items():
        assert hashlib.sha256(b).hexdigest()==rec["files"][n]
    return rec,data


def read_slot(audit,domain,instance,stream,job,tar,historical,old_row):
    case,method,seed=job
    slot=("extended_" if historical else "")+f"{method}_{seed}"
    rec,files=members(tar,slot)
    identity=[case,"extended",method,seed] if historical else list(job)
    assert rec["job"]==identity
    resv=json.loads(files["reservation.json"])
    assert resv["job"]==identity and resv["inputs"]==rec["inputs"] and resv["core"]==rec["core"]
    if not historical:
        assert all(digest(HERE/n)==h for n,h in rec["inputs"].items())
    row=dict(case=case,ambient_c=float(instance["ambient_c"]),method=method,seed=seed,
             source="f6df387" if historical else "new",receipt=rec["state"],wall_s=rec["elapsed_s"],
             safe=0,energy_j=None,first_safe_s=None,search_s=None)
    if rec["state"]!="finished":
        return row,[],[]
    assert rec["exitcode"]==0
    result=json.loads(gzip.decompress(files["result.json.gz"]))
    assert result["job"]==identity and result["request_sha256"]==instance["request_sha"]
    seen,improvements,repairs={},[],[]
    best=None
    last_t=0
    for line in gzip.decompress(files["events.jsonl.gz"]).splitlines():
        t,kind,v=json.loads(line)
        assert t>=last_t and t<=rec["elapsed_s"]
        last_t=t
        if kind!=("replay" if historical else "candidate"):
            continue
        if historical:
            key,status,energy,slack,_,_,upper,_=v
            parent=None
        else:
            key,action,parent,status,energy,slack,upper,failed_scene,target,proposal=v
        key=tuple(key)
        assert key not in seen and key[0] in domain.order and len(key)==5 and all(0<=i<27 for i in key[1:])
        peak=max(upper) if upper else None
        if status=="SAFE":
            assert peak<=80 and slack>=0 and energy>0
        elif status=="DEADLINE":
            assert energy is None and peak is None and slack<0
        else:
            assert status in ("VIOLATION","UNRESOLVED") and peak>80 and slack>=0
        if parent:
            p=seen[tuple(parent)]
            if p[0]=="VIOLATION":
                if target:
                    assert abs(p[2]-target[2])<1e-7 and 0<=target[0]<4 and 0<=target[1]<4
                repairs.append(dict(case=case,ambient_c=row["ambient_c"],method=method,seed=seed,at_s=t,
                         action=action,parent=encode(parent),child=encode(key),child_status=status,
                         hot_scene=target[0] if target else None,hot_node=target[1] if target else None,
                         choice=(proposal or {}).get("rule","setfreq"),
                         predicted_target_peak_c=(proposal or {}).get("predicted_target_peak_c"),
                         actual_target_peak_c=(proposal or {}).get("actual_target_peak_c"),
                         actual_target_entry_c=(proposal or {}).get("actual_target_entry_c"),
                         parent_peak_c=p[2],child_peak_c=peak,peak_reduction_c=p[2]-peak if peak else None,
                         energy_change_j=energy-p[1] if energy is not None else None))
        seen[key]=(status,energy,peak)
        if status=="SAFE" and (best is None or energy<best):
            best=energy
            improvements.append(dict(case=case,ambient_c=row["ambient_c"],method=method,seed=seed,
                                     t_s=t,energy_j=energy,genome=encode(key)))
    counts=Counter(s[0] for s in seen.values())
    if historical:
        answer=result["selected"]; chosen=result["selected_genome"]
        search_s=result["search_end_s"]
        assert counts==Counter(result["unique_observations"]) and float(old_row["safe_energy_j"])==best
    else:
        answer=result["physical"]; chosen=result["selected"]; search_s=result["search_s"]
        cnt=Counter(result["summary"]["counts"])
        cnt["DEADLINE"]=cnt.pop("screen_deadline",0)
        assert cnt==counts and result["summary"]["unique"]==len(seen)
        assert (result["summary"]["winner"] is not None)==(best is not None)
    if chosen:
        proof=json.loads(gzip.decompress(files["selection.json.gz"]))
        assert proof["request_sha256"]==instance["request_sha"]
        audit.check_selection(proof,dict(job=[case,"extended",method,seed],selected_genome=chosen,
                                         selected=answer),instance,stream,domain)
        if best is not None:
            assert answer["status"]=="SAFE" and abs(answer["energy_j"]-best)<1e-7
        row.update(genome=encode(chosen),stages=encode(proof["stages"]),opps="/".join(proof["opps"]),
                   peak_c=max(answer["upper"]) if answer["upper"] else None,min_slack_ms=answer["slack_ms"])
    assert search_s<=rec["elapsed_s"]
    row.update(safe=int(best is not None),energy_j=best,first_safe_s=improvements[0]["t_s"] if improvements else None,
               best_at_s=improvements[-1]["t_s"] if improvements else None,search_s=search_s,
               tested=len(seen),deadline=counts["DEADLINE"],overheat=counts["VIOLATION"],unresolved=counts["UNRESOLVED"],
               feasible=counts["SAFE"],completed_thermal=len(seen)-counts["DEADLINE"],
               hot_children=len(repairs),hot_to_safe=sum(r["child_status"]=="SAFE" for r in repairs))
    return row,improvements,repairs


def groups(rows,fields):
    key=lambda r:tuple(r[f] for f in fields)
    return [(dict(zip(fields,k)),list(items)) for k,items in groupby(sorted(rows,key=key),key=key)]


def repair_summary(repairs):
    output=[]
    for fields in (["method","ambient_c","choice"],["method","ambient_c"],["method"]):
        for meta,items in groups(repairs,fields):
            completed=[r for r in items if r["child_peak_c"] is not None]
            diagnostic=[r for r in completed if r["actual_target_peak_c"] is not None]
            predicted=[r for r in diagnostic if r["predicted_target_peak_c"] is not None]
            safe=sum(r["child_status"]=="SAFE" for r in items)
            output.append(dict(**meta,attempted=len(items),completed=len(completed),safe=safe,
                               deadline=len(items)-len(completed),repair_pct=100*safe/len(items),
                               different_parents=len({(r["case"],r["seed"],r["parent"]) for r in items}),
                               mean_peak_reduction_c=average(r["peak_reduction_c"] for r in completed),
                               mean_energy_change_j=average(r["energy_change_j"] for r in completed),
                               local_measurements=len(diagnostic),
                               target_resolved=sum(r["actual_target_peak_c"]<=80 for r in diagnostic),
                               unresolved_elsewhere=sum(r["actual_target_peak_c"]<=80 and r["child_status"]!="SAFE"
                                                        for r in diagnostic),
                               mean_abs_prediction_error_c=average(abs(r["predicted_target_peak_c"]-
                                                                       r["actual_target_peak_c"]) for r in predicted)))
    return output


def summaries(rows,curves):
    points=CFG["wall_checkpoints"]
    milestones=[]; anytime=[]; stats=[]; pairs=[]
    for row in rows:
        case,method,seed=row["case"],row["method"],row["seed"]
        chain=curves[case,method,seed]
        for t in points:
            values=[v["energy_j"] for v in chain if v["t_s"]<=t]
            milestones.append(dict(case=case,method=method,seed=seed,ambient_c=row["ambient_c"],t_s=t,
                                   best_safe_j=min(values,default=None)))
    lookup={(r["case"],r["method"],r["seed"],r["t_s"]):r["best_safe_j"] for r in milestones}
    for group in (["case","ambient_c","method"],["ambient_c","method"],["method"]):
        for meta,items in groups(rows,group):
            safe=[r for r in items if r["safe"]]
            tested=sum(r.get("tested",0) for r in items)
            hot=sum(r.get("hot_children",0) for r in items)
            recovered=sum(r.get("hot_to_safe",0) for r in items)
            met=dict(level="case" if "case" in group else "temperature" if "ambient_c" in group else "all",**meta)
            stats.append(dict(**met,n=len(items),safe=len(safe),mean_j=average(r["energy_j"] for r in safe),
                 mean_peak_c=average(r["peak_c"] for r in safe),min_slack_ms=min((r["min_slack_ms"] for r in safe),default=None),
                 first_safe_median_s=median(r["first_safe_s"] for r in safe) if safe else None,
                 search_median_s=median([r["search_s"] for r in items if r["search_s"] is not None] or [0]),
                 wall_median_s=median(r["wall_s"] for r in items),tested=tested,
                 deadline=sum(r.get("deadline",0) for r in items),
                 deadline_pct=100*sum(r.get("deadline",0) for r in items)/tested if tested else None,
                 hot_children=hot,hot_to_safe=recovered,repair_pct=100*recovered/hot if hot else None))
            for t in points:
                values=[lookup[r["case"],r["method"],r["seed"],t] for r in items]
                anytime.append(dict(**met,t_s=t,n=len(items),safe=sum(v is not None for v in values),
                                    mean_safe_j=average(values)))
                if meta["method"]=="directed":
                    for comparator in [*CFG["historical"],"energy_only"]:
                        matched=[(v,lookup[r["case"],comparator,r["seed"],t]) for v,r in zip(values,items)]
                        valid=[(v,b) for v,b in matched if v is not None and b is not None]
                        tol=CFG["energy_tolerance_j"]
                        pairs.append(dict(**met,t_s=t,comparator=comparator,n=len(items),both_safe=len(valid),
                             directed_only=sum(v is not None and b is None for v,b in matched),
                             comparator_only=sum(v is None and b is not None for v,b in matched),
                             win=sum(v<b-tol for v,b in valid),tie=sum(abs(v-b)<=tol for v,b in valid),
                             loss=sum(v>b+tol for v,b in valid),mean_saving_pct=average(100*(b-v)/b for v,b in valid)))
    return dict(run_checkpoints=milestones,summary=stats,anytime=anytime,paired=pairs)


def witness_rows(rows, history):
    results=[]
    for case in CASES:
        old=min((r for r in history.values() if r["case"]==case and r["safe_energy_j"]),
                key=lambda r:float(r["safe_energy_j"]))
        for method in CFG["methods"]:
            group=[r for r in rows if r["case"]==case and r["method"]==method and r["safe"]]
            winner=min(group,key=lambda r:r["energy_j"],default=None)
            previous=float(old["safe_energy_j"])
            results.append(dict(case=case,method=method,prior_all_extended_best_j=previous,
                                prior_method=old["method"],prior_seed=old["seed"],prior_deployment=old["deployment"],
                                new_best_j=winner["energy_j"] if winner else None,
                                new_seed=winner["seed"] if winner else None,new_genome=winner["genome"] if winner else None,
                                improves_prior=int(winner["energy_j"]<previous-CFG["energy_tolerance_j"]) if winner else None))
    return results


def main(root,out):
    sys.path[:0]=[str(root/"research/ch3_cooperative_cuts"),str(root/"research/ch3_final_experiments/p2")]
    import analyze as audit
    from catalog_ext import make_domain
    domain=make_domain(root)
    assert domain.size==4319803
    prior=root/"research/ch3_cooperative_cuts"
    oldrows={(r["case"],r["method"],int(r["seed"])):r for r in csv_rows(prior/"tables/run_results.csv") if r["scope"]=="extended"}
    old_manifest={r["case"]:r for r in json.loads((prior/"archive_manifest.json").read_bytes())["archives"]}
    new_manifest={r["case"]:r for r in json.loads((HERE/"archives/manifest.json").read_bytes())["archives"]}
    instances={r["instance_id"]:r for r in csv_rows(root/"research/ch3_final_experiments/derived/instances.csv")}
    fsm=json.loads((root/"research/kim_case_b_freeze/input.json").read_bytes())["fsm"]
    rows,curves,repairs=[],{},[]
    for case in CASES:
        stream=audit.stream_definition(instances[case],fsm)
        for hist,manifest,folder,methods in ((True,old_manifest,prior/"archives",CFG["historical"]),
                                             (False,new_manifest,HERE/"archives",CFG["methods"])):
            path=folder/(case+".tar")
            assert digest(path)==manifest[case]["sha256"]
            with tarfile.open(path) as tar:
                for method in methods:
                    for seed in CFG["seeds"]:
                        key=(case,method,seed)
                        row,curve,hot=read_slot(audit,domain,instances[case],stream,key,tar,hist,oldrows.get(key))
                        rows.append(row); curves[key]=curve; repairs.extend(hot)
    assert len(rows)==len(curves)==360
    out.mkdir(parents=True,exist_ok=True)
    tables=dict(runs=rows,improvements=[r for v in curves.values() for r in v],repair_events=repairs,
                repair_summary=repair_summary(repairs),
                witnesses=witness_rows(rows,oldrows),
                **summaries(rows,curves))
    for name,table in tables.items():
        write_csv(out/(name+".csv"),table)
    print("runs",len(rows),"safe",sum(r["safe"] for r in rows),"hot children",len(repairs))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--out",type=Path,default=HERE/"tables")
    args=parser.parse_args()
    main(args.root.resolve(),args.out)
