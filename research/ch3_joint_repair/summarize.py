"""Audit raw units and rebuild paired/anytime results. No scheduling or thermal solver."""
import argparse
from collections import Counter, defaultdict
import csv
import gzip
from hashlib import sha256
from itertools import groupby
import json
from math import isfinite
from pathlib import Path
from statistics import mean, median
import sys
import tarfile

from execute_study import CONFIG, HERE, JOBS, digest, dumps, inputs

TOL = CONFIG["energy_tolerance_j"]
METHODS = CONFIG["reuse"] + CONFIG["new"]


def require(ok, what):
    if not ok:
        raise ValueError(what)


def read_csv(path):
    with path.open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows):
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fields,lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def decoded(data):
    return json.loads(gzip.decompress(data))


def events(files):
    for line in gzip.decompress(files["events.jsonl.gz"]).splitlines():
        yield json.loads(line)


def cases_archives(folder, case, accepted):
    with tarfile.open(folder/(case+".tar"),"r:") as tar:
        groups=defaultdict(dict)
        for member in tar:
            slot, name=member.name.split("/")
            if slot not in accepted:
                continue
            require(member.isfile() and name not in groups[slot],"Invalid archive member")
            groups[slot][name]=member
        require(set(accepted)==set(groups),f"Missing unit in {case}")
        for slot, group in groups.items():
            yield accepted[slot],{name:tar.extractfile(member).read() for name,member in group.items()}


def ledger(job, files, domain, new):
    case,method,seed=job
    best=float("inf")
    curve, visited, ancestry, true_slots=[],{}, {}, {}
    status, actions, anchors=Counter(),Counter(),Counter()
    mechanism=Counter()
    prior=-1.
    proposed={}
    prefix=[]
    for time,kind,v in events(files):
        require(time>=prior, "Nonmonotonic trace")
        prior=time
        if new and kind=="parent":
            key=tuple(v[0])
            require(key in visited and visited[key][0]==v[1] and
                    (v[1]=="SAFE" or method!="safe_parent" and v[1]=="VIOLATION"),"Illegal expansion state")
            anchors[v[1]]+=1
        elif new and kind=="repair":
            p,block,options=v
            require(len(block)==(1 if method=="single" else 2) and len(options)<=CONFIG["proposals_per_block"], "Repair size")
            for dep,energy,excess,changed in options:
                require(1<=changed<=len(block) and energy>=0 and excess>=0,"Bad repair candidate")
                before=domain._decode(domain.raw(p[0]))
                after=domain._decode(domain.raw(dep))
                shifts=[len(domain.cuts[a][b[0]])-len(domain.cuts[a][old[0]]) for a,(old,b) in enumerate(zip(before,after))]
                require(all(shifts[a]==0 and before[a][0]==after[a][0] for a in range(4) if a not in block),"Block changed outside network")
                stable=[a for a in range(4) if a not in block and before[a][0]]
                require(len({before[a][1]^after[a][1] for a in stable})<=1,"Fixed binding changed")
                edits=min(sum(old[0]!=new_shape or (bool(old[0]) and old[1]!=(bit^swap))
                              for old,(new_shape,bit) in zip(before,after)) for swap in (0,1))
                require(1<=edits<=changed,"Physical edit count disagrees with raw changes")
                transfer=min(shifts)<0 and max(shifts)>0
                proposed[p[0],dep]=bool(transfer)
                mechanism["joint_changes_offered"]+=edits>1
                mechanism["quota_transfers_offered"]+=transfer
                mechanism["structure_offers"]+=1
        elif kind=="replay":
            genome,state,energy,slack,done,lo,hi,late=v[:8]
            key=tuple(genome)
            require(key not in visited and time<=CONFIG["accept_s"]+1e-6 and key[0] in domain.order and
                    len(key)==5 and all(type(i) is int and 0<=i<27 for i in key[1:]),"Invalid admitted replay")
            if state=="DEADLINE":
                require(energy is None and lo is None and hi is None and slack<0 and late>0,"Incomplete deadline prefix")
            else:
                require(done==500 and isfinite(energy) and energy>=0 and slack>=0 and not late,"Invalid full replay")
                require(len(lo)==len(hi)==4 and all(isfinite(x) and isfinite(y) and x<=y for x,y in zip(lo,hi)),"Peak bounds")
                cert="VIOLATION" if max(lo)>80 else "SAFE" if max(hi)<=80 else "UNRESOLVED"
                require(state==cert,"Thermal classification")
            visited[key]=(state,energy)
            if (new or method in ("full","no_heat")) and len(prefix)<2:
                require(key[0]==("A","C")[len(prefix)],"Different common initialization")
                prefix.append((list(key),time))
            status[state]+=1
            if new:
                action,raw_parent=v[8:]
                parent=tuple(raw_parent) if raw_parent else None
                if parent is not None:
                    require(parent in visited and parent!=key,"Missing parent")
                ancestry[key]=(action,parent,time,slack,max(hi) if hi else None)
                actions[action]+=1
                true_slots[key]=bool(parent and proposed.get((parent[0],key[0])))
            if state=="SAFE" and energy<best:
                best=energy
                curve.append((time,energy,key))
    return curve,status,visited,ancestry,true_slots,anchors,actions,mechanism,prefix


def unit_row(job, files, domain, instance, stream, audit, code_hashes, new):
    case,method,seed=job
    receipt=json.loads(files["receipt.json"])
    reservation=json.loads(files["reservation.json"])
    require(set(files)-{"receipt.json"}==set(receipt["files"]) and all(
        sha256(files[n]).hexdigest()==h for n,h in receipt["files"].items()),"Raw slot digest mismatch")
    raw_job=list(job) if new else [case,"extended",method,seed]
    require(receipt["job"]==reservation["job"]==raw_job and receipt["inputs"]==reservation["inputs"],"Run identity")
    if new:
        require(receipt["inputs"]==code_hashes and reservation["cap"]==CONFIG["cap_s"],"Frozen execution code drift")
    row=dict(case=case,ambient_c=float(instance["ambient_c"]),seed=seed,method=method,source="new" if new else "archived",
             wall_s=receipt["elapsed_s"],receipt=receipt["state"],safe=0,
             request_sha256=instance["request_sha"],receipt_sha256=sha256(files["receipt.json"]).hexdigest())
    if receipt["state"]!="finished":
        return row,[],None,[]
    res=decoded(files["result.json.gz"])
    require(res["job"]==raw_job and res["request_sha256"]==instance["request_sha"],"Workload mismatch")
    curve,stats,visited,edges,transfers,anchors,actions,mechanism,prefix=ledger(job,files,domain,new)
    require(res["safe"]==bool(curve) and (not curve or res["selected"]["energy_j"]==curve[-1][1]),"Winner energy mismatch")
    if new:
        require(dict(stats)==res["summary"]["statuses"] and len(visited)==res["summary"]["unique_physical"] and
                (not curve or list(curve[-1][2])==res["summary"]["winner"]==res["selected_genome"]),
                "New run counters/winner drift")
        recorded=[(t,v[1],tuple(v[0])) for t,k,v in events(files) if k=="incumbent"]
        require(recorded==curve,"Incumbent and replay logs disagree")
    else:
        verified=audit.audit_run(files,(case,"extended",method,seed),instance,stream,domain)
        require(verified["safety"]==int(bool(curve)),"Historical audit drift")
    row.update(safe=int(bool(curve)),search_s=res["search_end_s"],first_safe_s=curve[0][0] if curve else None,
               best_first_hit_s=curve[-1][0] if curve else None,stop=res["summary"]["reason"],
               safe_energy_j=curve[-1][1] if curve else None,replay_count=len(visited),
               counts=dumps(dict(stats)),hot_parent_visits=anchors["VIOLATION"] if new else None,
               parent_visits=sum(anchors.values()) if new else None,
               common_AC_done_s=prefix[-1][1] if len(prefix)==2 else None,
               common_AC_genomes=dumps([k for k,t in prefix]) if len(prefix)==2 else None)
    if new:
        row.update(mechanism,actions=dumps(dict(actions)),**res["summary"]["counts"])
    steps=[]
    if res["selected_genome"] is None:
        require(not visited,"Missing selection")
        return row,curve,None,steps
    key=tuple(res["selected_genome"])
    if new and curve:
        pos=key
        path=Counter()
        while pos is not None:
            action,parent,when,slack,peak=edges[pos]
            path[action]+=1
            if transfers[pos]:
                path["quota_transfer"]+=1
            if visited[pos][0]=="VIOLATION":
                path["hot_intermediate"]+=1
            layout=domain._decode(domain.raw(pos[0]))
            cuts=[domain.cuts[a][index] for a,(index,bit) in enumerate(layout)]
            steps.append(dict(case=case,method=method,seed=seed,discovered_s=when,action=action,
                         deployment=pos[0],parent_dep=parent[0] if parent else None,
                         opp_indices=dumps(pos[1:]),cuts=dumps(cuts),resident_slots=dumps([len(c) for c in cuts]),
                         physical_binding=dumps([bit if index else None for index,bit in layout]),
                         quota_transferred=int(transfers[pos]),status=visited[pos][0],actual_j=visited[pos][1],
                         min_slack_ms=slack,peak_upper_c=peak))
            pos=parent
        steps.reverse()
        for index,step in enumerate(steps):
            step["depth"]=index
        row.update(winning_path=dumps(dict(path)),winner_path_quota_transfer=path["quota_transfer"],
                   winner_path_overtemp=path["hot_intermediate"])
    proof=decoded(files["selection.json.gz"])
    fixture=dict(res,job=[case,"extended",method,seed])
    stages=audit.check_selection(proof,fixture,instance,stream,domain)
    selected=res["selected"]
    peak=max(selected["upper"]) if selected["upper"] else None
    row.update(selected_status=selected["status"],actual_energy_j=selected["energy_j"],deployment=key[0],
               stages=dumps(stages),opp_indices=dumps(key[1:]),frequency="/".join(proof["opps"]),
               peak_upper_c=peak,margin_c=80-peak if peak is not None else None,
               min_slack_ms=selected["slack_ms"],completed=selected["completed"],
               selection_sha256=sha256(files["selection.json.gz"]).hexdigest())
    return row,curve,proof,steps


def compare(rows, curves):
    index={(r["case"],r["method"],r["seed"]):r for r in rows}
    pairs, sampled, milestones=[],[],[]
    for r in rows:
        case,m,k=r["case"],r["method"],r["seed"]
        seq=curves[case,m,k]
        kim=index[case,"Kim-Adapt+SAFE",k]
        ref=kim.get("safe_energy_j")
        hit=next((t for t,e,_ in seq if ref is not None and e<=ref*(1+CONFIG["near_kim_gap_pct"]/100)+TOL),None)
        match=next((t for t,e,_ in seq if ref is not None and e<=ref+TOL),None)
        milestones.append(dict(case=case,ambient_c=r["ambient_c"],method=m,seed=k,first_safe_s=r.get("first_safe_s"),
                               kim_final_j=ref,within_0p1pct_kim_s=hit,match_or_beat_kim_s=match,
                               kim_search_s=kim.get("search_s"),best_first_hit_s=r.get("best_first_hit_s")))
        for budget in CONFIG["anytime_s"]:
            last=next(((t,e) for t,e,_ in reversed(seq) if t<=budget),None)
            sampled.append(dict(case=case,ambient_c=r["ambient_c"],seed=k,method=m,budget_s=budget,
                         safe=int(last is not None),best_safe_j=last[1] if last else None,
                         gap_to_final_kim_pct=100*(last[1]/ref-1) if last and ref is not None else None,
                         within_0p1pct_kim=int(hit is not None and hit<=budget) if ref is not None else None))
        if m=="joint":
            continue
        j=index[case,"joint",k]
        both=r["safe"] and j["safe"]
        delta=j["safe_energy_j"]-r["safe_energy_j"] if both else None
        pairs.append(dict(case=case,ambient_c=r["ambient_c"],seed=k,comparator=m,joint_safe=j["safe"],
                 comparator_safe=r["safe"],joint_j=j.get("safe_energy_j"),comparator_j=r.get("safe_energy_j"),
                 gap_j=delta,gap_pct=100*delta/r["safe_energy_j"] if both else None,
                 relation=("lower" if delta < -TOL else "higher" if delta>TOL else "tie") if both else "unpaired"))
    return pairs,sampled,milestones


def grouped(rows, fields):
    key=lambda r: tuple(r[f] for f in fields)
    for values,group in groupby(sorted(rows,key=key),key=key):
        yield dict(zip(fields,values)),list(group)


def aggregate(pairs,rows,sampled):
    comp=[]
    for fields in (["comparator"],["ambient_c","comparator"],["case","comparator"]):
        for label,g in grouped(pairs,fields):
            a=[r["gap_pct"] for r in g if r["gap_pct"] is not None]
            counts=Counter(r["relation"] for r in g)
            comp.append(dict(group="/".join(fields),**label,n=len(g),paired=len(a),joint_lower=counts["lower"],
                             tie=counts["tie"],joint_higher=counts["higher"],mean_gap_pct=mean(a) if a else None,
                             median_gap_pct=median(a) if a else None))
    def stat(g,k,fn):
        vals=[r[k] for r in g if r.get(k) is not None]
        return fn(vals) if vals else None
    cases=[]
    for label,g in grouped(rows,["case","ambient_c","method"]):
        safe=[r for r in g if r["safe"]]
        cases.append(dict(**label,runs=len(g),safe=len(safe),mean_safe_j=stat(safe,"safe_energy_j",mean),
             min_safe_j=stat(safe,"safe_energy_j",min),mean_peak_upper_c=stat(safe,"peak_upper_c",mean),
             min_margin_c=stat(safe,"margin_c",min),min_deadline_slack_ms=stat(safe,"min_slack_ms",min),
             median_search_s=stat(g,"search_s",median),median_first_safe_s=stat(g,"first_safe_s",median)))
    timepoints=[]
    for label,g in grouped(sampled,["method","budget_s"]):
        safe=[r for r in g if r["safe"]]
        timepoints.append(dict(**label,n=len(g),safe=len(safe),within_threshold=sum(r["within_0p1pct_kim"] or 0 for r in g),
                  paired_kim_reference=sum(r["within_0p1pct_kim"] is not None for r in g),
                  conditional_mean_gap_pct=stat(safe,"gap_to_final_kim_pct",mean),
                  conditional_median_gap_pct=stat(safe,"gap_to_final_kim_pct",median)))
    return comp,cases,timepoints


def time_pairs(milestones):
    lookup={(r["case"],r["seed"],r["method"]):r for r in milestones}
    records=[]
    for r in milestones:
        if r["method"]=="joint":
            continue
        joint=lookup[r["case"],r["seed"],"joint"]
        for metric in ("first_safe_s","within_0p1pct_kim_s","match_or_beat_kim_s"):
            a,b=joint[metric],r[metric]
            records.append(dict(case=r["case"],ambient_c=r["ambient_c"],seed=r["seed"],comparator=r["method"],
                event=metric,joint_time_s=a,other_time_s=b,joint_hit=int(a is not None),other_hit=int(b is not None),
                other_minus_joint_s=b-a if a is not None and b is not None else None))
    result=[]
    for fields in (["event","comparator"],["ambient_c","event","comparator"]):
        for label,g in grouped(records,fields):
            deltas=[v["other_minus_joint_s"] for v in g if v["other_minus_joint_s"] is not None]
            result.append(dict(group="/".join(fields),**label,n=len(g),joint_hits=sum(r["joint_hit"] for r in g),
                other_hits=sum(r["other_hit"] for r in g),both_hit=len(deltas),
                joint_earlier=sum(d>0 for d in deltas),other_earlier=sum(d<0 for d in deltas),
                median_other_minus_joint_s=median(deltas) if deltas else None))
    return result


def main(root, new_archives, out):
    base=root/"research/ch3_cooperative_cuts"
    sys.path[:0]=[str(base),str(root/"research/ch3_final_experiments/p2")]
    import analyze as audit
    from catalog_ext import make_domain
    domain=make_domain(root)
    code_hashes=inputs(root)
    require(domain.size==CONFIG["catalog"],"Deployment count drift")
    instances={r["instance_id"]:r for r in read_csv(root/"research/ch3_final_experiments/derived/instances.csv")}
    fsm=json.loads((root/"research/kim_case_b_freeze/input.json").read_bytes())["fsm"]
    rows,curves,export,winning_paths=[],{},{},[]
    for new,folder,manifest_path in [(False,base/"archives",base/"archive_manifest.json"),
                                    (True,new_archives,new_archives/"manifest.json")]:
        manifest=json.loads(manifest_path.read_bytes())
        require({v["case"] for v in manifest["archives"]}==set(CONFIG["cases"]),"Archive matrix mismatch")
        for v in manifest["archives"]:
            case=v["case"]
            require(digest(folder/(case+".tar"))==v["sha256"],f"Archive SHA mismatch: {case}")
            methods=CONFIG["new"] if new else CONFIG["reuse"]
            names={("" if new else "extended_")+f"{m}_{k}":(case,m,k) for m in methods for k in CONFIG["seeds"]}
            inst=instances[case]
            stream=audit.stream_definition(inst,fsm)
            for job,files in cases_archives(folder,case,names):
                row,curve,proof,steps=unit_row(job,files,domain,inst,stream,audit,code_hashes,new)
                require(job not in curves,"Duplicate row")
                rows.append(row)
                curves[job]=curve
                winning_paths.extend(steps)
                if job[1]=="joint" and proof and row["safe"] and (case not in export or
                        row["safe_energy_j"]<export[case]["safe_upper_bound_j"]):
                    code=0
                    for i in proof["indices"]:
                        code=27*code+i
                    export[case]=dict(case=case,ambient_c=row["ambient_c"],scope="extended",domain_count=domain.size,
                        request_sha256=row["request_sha256"],inputs_manifest_sha256=digest(HERE/"inputs.json"),seed=job[2],
                        dep=proof["dep"],stages=proof["stages"],indices=proof["indices"],ordered_opps=proof["opps"],
                        opp_code=code,safe_upper_bound_j=row["safe_energy_j"],peak_upper_c=row["peak_upper_c"],
                        min_slack_ms=row["min_slack_ms"],selection_sha256=row["selection_sha256"],
                        evidence=f"archives/{case}.tar#joint_{job[2]}/selection.json.gz")
    require(len(rows)==len(curves)==420,"Incomplete 12 x 7 x 5 matrix")
    for _,group in grouped(rows,["case","seed"]):
        prefixes={r["common_AC_genomes"] for r in group if r.get("common_AC_genomes")}
        require(len(prefixes)<=1,"Common-prefix genomes differ across batches")
    rows.sort(key=lambda r:(CONFIG["cases"].index(r["case"]),METHODS.index(r["method"]),r["seed"]))
    pairs,sampled,milestones=compare(rows,curves)
    comp,cases,timepoints=aggregate(pairs,rows,sampled)
    trace=[dict(case=c,method=m,seed=k,time_s=t,best_safe_j=e,deployment=g[0],opp_indices=dumps(g[1:]))
           for (c,m,k),curve in sorted(curves.items()) for t,e,g in curve]
    tables=dict(run_results=rows,case_summary=cases,paired_runs=pairs,paired_summary=comp,improvements=trace,
                time_checkpoints=sampled,anytime_summary=timepoints,time_to_target=milestones,
                paired_time_summary=time_pairs(milestones),winning_paths=winning_paths)
    out.mkdir(parents=True,exist_ok=True)
    for name,data in tables.items():
        write_csv(out/(name+".csv"),data)
    (out/"m2_incumbents.jsonl").write_text("".join(dumps(export[c])+"\n" for c in sorted(export)),encoding="utf8",newline="\n")
    record=dict(base=CONFIG["base"],new_runs=len(JOBS),reused_runs=len(rows)-len(JOBS),final_safe=sum(r["safe"] for r in rows),
                statuses=dict(Counter(r["receipt"] for r in rows)),incumbent_events=len(trace),
                raw_archive_hashes_verified=24,table_sha256={p.name:digest(p) for p in sorted(out.iterdir())
                if p.name in {n+".csv" for n in tables}|{"m2_incumbents.jsonl"}})
    (out/"audit.json").write_text(json.dumps(record,indent=2)+"\n",encoding="utf8",newline="\n")
    print(dumps(record))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-root",required=True,type=Path)
    p.add_argument("--archives",type=Path,default=HERE/"archives")
    p.add_argument("--output",type=Path,default=HERE/"tables")
    args=p.parse_args()
    main(args.source_root.resolve(),args.archives,args.output)
