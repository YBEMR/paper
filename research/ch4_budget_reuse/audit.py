"""Verify sealed units, independently reconstruct SAFE curves and check identical evaluator inputs."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tarfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/"research/ch3_algorithm_selection"))
from records import check_selection,make_domain,workload

CFG=json.loads((HERE/"config.json").read_bytes())


def require(ok,msg):
    if not ok: raise ValueError(msg)


def write_csv(name,rows):
    if not rows: return
    path=HERE/"tables"/(name+".csv")
    path.parent.mkdir(exist_ok=True)
    with path.open("w",encoding="utf8",newline="") as f:
        cols=list(dict.fromkeys(k for r in rows for k in r))
        w=csv.DictWriter(f,fieldnames=cols,lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k:json.dumps(v,separators=(",",":")) if isinstance(v,(list,dict)) else v for k,v in r.items()})


def content(slot):
    with tarfile.open(HERE/"archives"/(slot+".tar")) as t:
        files={m.name:t.extractfile(m).read() for m in t if m.isfile()}
    rec=json.loads(files["receipt.json"])
    for n,h in rec["files"].items():
        require(hashlib.sha256(files[n]).hexdigest()==h,slot+" "+n)
    return files,rec


def events(data):
    return map(json.loads,gzip.decompress(data).splitlines())


def project(files):
    # Independent compact representation per evaluator call. Exclude clock/timing fields.
    keys=[];times=[];ends=[];begins=[];types=[]
    for i,(idx,kind,p,start,end,value) in enumerate(events(files["flow.jsonl.gz"])):
        require(i==idx and end>=start,"call identity/clock")
        keys.append(hashlib.sha256(json.dumps([kind,p,value],separators=(",",":")).encode()).digest())
        times.append(end-start);ends.append(end);begins.append(start);types.append(kind)
    return keys,times,ends,begins,types


def ref_table():
    with (ROOT/"research/ch3_algorithm_selection/tables/case_summary.csv").open(encoding="utf8") as f:
        return {(r["load"],int(r["ambient_c"])):float(r["reference_j"]) for r in csv.DictReader(f)
                if r["method"]=="energy_only"}


def analyze_one(slot,files,receipt,domain,ref):
    r=json.loads(files["result.json"])
    req,stream=workload(r["load"])
    role="fixed" if r["fixed"] else "main"
    ident=dict(slot=slot,role=role,load=r["load"],temp=r["temp"],seed=r["seed"],arm=r["arm"])
    check=json.loads(files["reservation.json"])
    require(check["freeze"]==receipt["freeze"] and check["source_hash"]==hashlib.sha256(
            (HERE/"identity.json").read_bytes()).hexdigest(),"execution identity")
    require(r["context"]["stream"]==req and receipt["state"]=="finished" and receipt["wall_s"]<=120,
            "workload or wall cap "+slot)
    row=dict(**ident,startup_s=r["startup_s"],search_end_s=r["search_end_s"],process_s=receipt["wall_s"],
             request_sha256=req,freeze=receipt["freeze"],flow_calls=r["flow_rows"],peak_rss_bytes=r["peak_rss_bytes"],
             peak_cache_array_bytes=r["peak_cache_array_bytes"],peak_cache_entries=r["peak_cache_entries"])
    trace=list(events(files["events.jsonl.gz"]))
    metric_names=("initialization","search_control","candidate_generation","candidate_ranking","allocation_rule",
            "parent_selection","setfreq_control","proxy_lookup","dispatch","deadline_screen","setfreq_thermal",
            "continuous_dispatch","original_continuous","kernel_lookup","kernel_build","affine_query","peak_screen",
            "peak_fallback","peak_certificate_completion","cost_observation","final_integral","final_certificate",
            "logging","trace_io_and_control","closeout")
    cost=[]
    def segment(name,left,right):
        a,b=left; c,d=right
        times={k:c.get(k,0)-a.get(k,0) for k in metric_names}
        counts={k:d.get(k,0)-b.get(k,0) for k in set(d)|set(b)}
        cost.append(dict(**ident,phase=name,accounted_s=sum(times.values()),**times,
                         **{"n_"+k:v for k,v in counts.items()}))
    zero=({}, {})
    segment("whole",zero,r["meter"])
    if r["fixed"]:
        checks=list(events(files["comparison.jsonl.gz"]))
        require(len(checks)==r["summary"]["checked"] and all(v[-1] and v[0]==i for i,v in enumerate(checks)),
                "fixed replay check")
        row.update(verified_calls=len(checks),truncated=r["summary"]["truncated"])
        return row,[],[],cost
    curve=[(t,p[0],p[1]) for t,k,p in trace if k=="incumbent"]
    snapshots={tuple(p[0]):p[1] for t,k,p in trace if k=="incumbent_cost"}
    observed=[]
    allocation=[p for t,k,p in trace if k=="allocation"]
    for t,k,p in trace:
        if k=="candidate" and p[3]=="SAFE" and (not observed or p[4]<observed[-1][1]):
            observed.append((p[0],p[4]))
    require(observed==[(key,e) for _,key,e in curve] and all(t<116 for t,_,_ in curve),"incumbent path")
    refj=ref[r["load"],r["temp"]]
    near=next(((t,key) for t,key,e in curve if e<=refj*1.001),None)
    exact=next((t for t,key,e in curve if abs(e-refj)<=1e-7),None)
    row.update(safe=int(bool(curve)),first_safe_s=curve[0][0] if curve else None,
               near_s=near[0] if near else None,exact_s=exact,best_j=curve[-1][2] if curve else None,
               ref_j=refj,new_lower=int(bool(curve) and curve[-1][2]<refj-1e-7),
               allocation_rounds=len(allocation),changed_fills=sum(p[1]!=p[2] for p in allocation),
               changed_candidate_sets=sum(set(map(tuple,p[1]))!=set(map(tuple,p[2])) for p in allocation),
               replaced_candidates=sum(len(set(map(tuple,p[2]))-set(map(tuple,p[1]))) for p in allocation))
    if curve:
        proof=json.loads(gzip.decompress(files["selection.json.gz"]))
        key=curve[-1][1]; phy=proof["physical"]
        require(phy["energy_j"]==curve[-1][2] and key==r["summary"]["winner"],"winner energy")
        answer=dict(status=phy["thermal_status"],completed=phy["completed"],slack_ms=phy["min_slack_ms"],
                    energy_j=phy["energy_j"],upper=phy["peak_upper_c"],lower=phy["peak_lower_c"])
        case=f"{r['load']}_{r['temp']}C"
        check_selection(proof,dict(job=[case,"extended",r["arm"],r["seed"]],selected_genome=key,selected=answer),
                        dict(ambient_c=r["temp"],request_sha=req),stream,domain)
        row.update(deployment=key[0],stages=proof["stages"],opp_indices=key[1:],peak_upper_c=max(answer["upper"]),
                   min_slack_ms=answer["slack_ms"],completed=answer["completed"],
                   certificate_sha256=receipt["files"]["selection.json.gz"])
    at20=r["boundaries"]["20"];last=r["boundaries"]["116"]
    segment("0_to_20",zero,at20)
    segment("20_to_116",at20,last)
    segment("after_116",last,r["meter"])
    if near:
        snap=snapshots[tuple(near[1])]
        segment("through_target",zero,snap)
        segment("after_target_to_116",snap,last)
    else: segment("target_not_reached",zero,last)
    cps=[]
    for t in CFG["early_s"]:
        hits=[e for when,_,e in curve if when<=t]
        val=hits[-1] if hits else None
        cps.append(dict(**ident,wall_s=t,safe=int(bool(hits)),energy_j=val,
                   target=int(bool(hits) and val<=refj*1.001),exact=int(bool(hits) and abs(val-refj)<=1e-7)))
    improvements=[dict(**ident,time_s=t,energy_j=e,dep=k[0],freq=k[1:]) for t,k,e in curve]
    return row,improvements,cps,cost
