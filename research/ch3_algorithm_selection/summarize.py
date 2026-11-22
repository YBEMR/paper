"""Rebuild time targets, censored successes, paired comparisons and verified M2 witnesses."""
import argparse
from collections import defaultdict
import json
from statistics import mean, median

from records import CFG, HERE, ROOT, csv_table, make_domain, read_run, read_table

TOL = 1e-7


def finite(values, func):
    items=[x for x in values if x is not None]
    return func(items) if items else None


def grouped(rows, fields):
    groups=defaultdict(list)
    for r in rows:
        groups[tuple(r[f] for f in fields)].append(r)
    return groups


def summarize(include_ablation,from_archives=False):
    if from_archives:
        from hashlib import sha256
        manifest=json.loads((HERE/"archives/manifest.json").read_bytes())
        for load in CFG["loads"]:
            for temp in CFG["temperatures"]:
                name=f"{load}_{temp}C.tar"
                if sha256((HERE/"archives"/name).read_bytes()).hexdigest()!=manifest[name]["sha256"]:
                    raise ValueError("Archive checksum mismatch: "+name)
    domain=make_domain(ROOT)
    rows,curves,proofs=[],{},{}
    for load in CFG["loads"]:
        for temp in CFG["temperatures"]:
            for seed in CFG["seeds"]:
                for method in CFG["main"]+(["energy_safe_parent"] if include_ablation else []):
                    job=(load,temp,seed,method)
                    row,curve,proof=read_run(job,domain,from_archives)
                    rows.append(row)
                    curves[job]=curve
                    proofs[job]=proof
    groups=grouped([r for r in rows if r["method"] in CFG["main"]],["load","ambient_c"])
    refs={k:finite((r["energy_j"] for r in v),min) for k,v in groups.items()}
    checkpoints,improvements=[],[]
    for r in rows:
        load,temp,seed,method=(r[n] for n in ("load","ambient_c","seed","method"))
        ref=refs[load,temp]
        curve=curves[load,temp,seed,method]
        identity=dict(load=load,ambient_c=temp,method=method,seed=seed)
        def gap(e):
            return 100*(e/ref-1) if ref is not None and e is not None else None
        r.update(reference_j=ref,gap_pct=gap(r["energy_j"]),
                 near_s=next((t for t,e,_ in curve if ref and e<=ref*1.001+TOL),None),
                 exact_s=next((t for t,e,_ in curve if ref and e<=ref+TOL),None))
        for t,e,key in curve:
            improvements.append(dict(**identity,time_s=t,best_SAFE_j=e,gap_pct=gap(e),deployment=key[0],
                                     opp_indices=key[1:]))
        for t in CFG["checkpoints_s"]:
            reached=[e for when,e,_ in curve if when<=t]
            e=reached[-1] if reached else None
            checkpoints.append(dict(**identity,wall_deadline_s=t,SAFE=int(e is not None),best_SAFE_j=e,
                                    gap_pct=gap(e),near=int(r["near_s"] is not None and r["near_s"]<=t),
                                    exact=int(r["exact_s"] is not None and r["exact_s"]<=t)))
    csv_table("runs",rows)
    csv_table("improvements",improvements)
    csv_table("checkpoints",checkpoints)
    checkpoint_summary=[]
    for (l,t,m,cut),v in grouped(checkpoints,["load","ambient_c","method","wall_deadline_s"]).items():
        checkpoint_summary.append(dict(load=l,ambient_c=t,method=m,wall_deadline_s=cut,n=len(v),
                safe=sum(i["SAFE"] for i in v),near=sum(i["near"] for i in v),exact=sum(i["exact"] for i in v),
                median_SAFE_j=finite((i["best_SAFE_j"] for i in v),median),
                median_gap_pct=finite((i["gap_pct"] for i in v),median)))
    csv_table("checkpoint_summary",checkpoint_summary)
    summary=[]
    for (l,t,m),v in grouped(rows,["load","ambient_c","method"]).items():
        def stat(col, f=median):
            return finite((x[col] for x in v),f)
        summary.append(dict(load=l,ambient_c=t,method=m,n=len(v),safe=sum(x["SAFE"] for x in v),
                   reference_j=refs[l,t],energy_min_j=stat("energy_j",min),energy_median_j=stat("energy_j"),
                   energy_max_j=stat("energy_j",max),median_gap_pct=stat("gap_pct"),
                   worst_peak_c=stat("peak_upper_c",max),least_slack_ms=stat("min_slack_ms",min),
                   median_first_SAFE_s=stat("first_SAFE_s"),near_hits=sum(x["near_s"] is not None for x in v),
                   median_near_hit_s=stat("near_s"),exact_hits=sum(x["exact_s"] is not None for x in v),
                   median_exact_hit_s=stat("exact_s"),median_search_end_s=stat("search_end_s"),
                   median_process_s=stat("wall_s")))
    csv_table("case_summary",summary)
    pooled=[]
    for (m,),v in grouped(rows,["method"]).items():
        def stat(col):
            return finite((x[col] for x in v),median)
        h=[x for x in checkpoints if x["method"]==m and x["wall_deadline_s"]==20]
        pooled.append(dict(method=m,n=len(v),safe=sum(x["SAFE"] for x in v),
                first_SAFE_median_s=stat("first_SAFE_s"),near_hits=sum(x["near_s"] is not None for x in v),
                near_median_among_hits_s=stat("near_s"),exact_hits=sum(x["exact_s"] is not None for x in v),
                exact_median_among_hits_s=stat("exact_s"),mean_normalized_gap_pct=finite((x["gap_pct"] for x in v),mean),
                safe_by_20s=sum(x["SAFE"] for x in h),near_by_20s=sum(x["near"] for x in h),
                exact_by_20s=sum(x["exact"] for x in h),search_end_median_s=stat("search_end_s"),
                process_end_median_s=stat("wall_s"),hot_ancestor_runs=(
                    sum(x["winner_hot_ancestor"] or 0 for x in v) if m!="kim_anytime" else None)))
    csv_table("method_summary",pooled)
    pairs=[]
    byjob={(r["load"],r["ambient_c"],r["seed"],r["method"]):r for r in rows}
    contrasts=[("energy_only","kim_anytime"),("joint","kim_anytime"),("energy_only","joint")]
    if include_ablation:
        contrasts.append(("energy_only","energy_safe_parent"))
    for a,b in contrasts:
        for (l,t,s,m),p in byjob.items():
            if m!=a: continue
            q=byjob[l,t,s,b]
            both=p["SAFE"] and q["SAFE"]
            gap=(p["energy_j"]-q["energy_j"]) if both else None
            pairs.append(dict(load=l,ambient_c=t,seed=s,method=a,comparator=b,
                        both_SAFE=int(both),difference_j=gap,relative_saving_pct=-100*gap/q["energy_j"] if both else None,
                        result=("tie" if abs(gap)<=TOL else "lower" if gap<0 else "higher") if both else "unpaired",
                        near_lead_s=q["near_s"]-p["near_s"] if None not in (q["near_s"],p["near_s"]) else None))
    csv_table("paired",pairs)
    history=read_table(ROOT/"research/ch3_joint_repair/tables/run_results.csv")
    historical=[]
    for r in history:
        temp=int(float(r["ambient_c"]))
        if r["method"]!="Kim-Adapt+SAFE" or r["case"]!=f"forward_flat_{temp}C" or temp not in CFG["temperatures"] or int(r["seed"]) not in CFG["seeds"]:
            continue
        historical.append({k:r[k] for k in ("case","ambient_c","seed","method","safe","actual_energy_j",
             "first_safe_s","search_s","wall_s","peak_upper_c","min_slack_ms","deployment","request_sha256","selection_sha256")})
    csv_table("historical_kim_original",historical)
    # One certified upper bound per load/temp, deterministic tie breaking. No use of historic 81-domain bound.
    with (HERE/"tables/m2_incumbents.jsonl").open("w",encoding="utf8",newline="\n") as f:
        for (l,t),v in groups.items():
            choices=sorted((r for r in v if r["SAFE"]),key=lambda r:(r["energy_j"],r["seed"],r["method"]))
            if not choices: continue
            r=choices[0]; key=(l,t,r["seed"],r["method"]); proof=proofs[key]; phy=proof["physical"]
            archive=f"archives/{l}_{t}C.tar"
            member=f"{r['method']}_{r['seed']}/selection.json.gz"
            indices=r["opp_indices"]
            f.write(json.dumps(dict(case=f"{l}_{t}C",load=l,ambient_c=t,scope="extended",domain_count=domain.size,
                request_sha256=r["request_sha256"],catalog_sha256=domain_digest(),platform_sha256=platform_digest(),
                inputs_manifest_sha256=input_digest(),method=r["method"],seed=r["seed"],dep=r["dep"],stages=r["cuts"],
                indices=indices,ordered_opps=r["opps"],opp_code=sum(i*27**(3-j) for j,i in enumerate(indices)),
                safe_upper_bound_j=r["energy_j"],peak_upper_c=max(phy["peak_upper_c"]),node_peak_upper_c=phy["peak_upper_c"],
                min_slack_ms=r["min_slack_ms"],completed=r["completed"],status="SAFE",feasible_upper_bound_only=True,
                evidence=archive+"#"+member,selection_sha256=r["proof_sha256"]),
                separators=(",",":"))+"\n")
    print(f"{len(rows)} runs, {sum(r['SAFE'] for r in rows)} certified, {len(improvements)} improvements")


def input_digest():
    from hashlib import sha256
    return sha256((ROOT/"research/ch3_joint_repair/inputs.json").read_bytes()).hexdigest()


def domain_digest():
    from hashlib import sha256
    return sha256((ROOT/"research/ch3_cooperative_cuts/catalog_manifest.json").read_bytes()).hexdigest()


def platform_digest():
    from hashlib import sha256
    return sha256((ROOT/"research/kim_synthetic_platform_v1/platform.json").read_bytes()).hexdigest()


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--ablation",action="store_true")
    parser.add_argument("--from-archives",action="store_true")
    args=parser.parse_args()
    summarize(args.ablation,args.from_archives)
