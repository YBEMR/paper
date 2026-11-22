"""Rebuild recorded SAFE trajectories, certify raw ledgers, and audit that Kim selection stayed unchanged."""
from collections import Counter
from contextlib import contextmanager
import csv
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import random
import sys
import tarfile

from loads import CFG, HERE, GRID, verify

ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT/"research/ch3_cooperative_cuts"), str(ROOT/"research/ch3_final_experiments/p2")]
from analyze import check_selection
from catalog_ext import make_domain
import search


def require(test, why):
    if not test:
        raise ValueError(why)


def csv_table(name, rows):
    path = HERE/"tables"/(name+".csv")
    path.parent.mkdir(exist_ok=True)
    with path.open("w", newline="", encoding="utf8") as f:
        out=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n")
        out.writeheader()
        for r in rows:
            out.writerow({k:json.dumps(v,separators=(",",":")) if isinstance(v,(dict,list)) else v for k,v in r.items()})


def read_table(path):
    with path.open(newline="",encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


@contextmanager
def open_slot(load,temp,seed,method,from_archives):
    case = f"{load}_{temp}C"
    slot = f"{method}_{seed}"
    folder = HERE/"units"/case/slot
    if folder.is_dir() and not from_archives:
        yield lambda file:(folder/file).read_bytes()
    else:
        with tarfile.open(HERE/"archives"/(case+".tar")) as tar:
            yield lambda file:tar.extractfile(slot+"/"+file).read()


@lru_cache(maxsize=3)
def workload(load):
    spec = CFG["loads"][load]
    jobs = json.loads((HERE/"streams"/f"{load}.json").read_bytes())
    digest = verify(jobs,spec)
    stream = []
    start = 0
    for j,frames in enumerate(spec["frames"]):
        service_end = start+frames*GRID
        stream.append((f"sc{j}",{i:(a,r,d) for i,a,r,d in jobs if start<=r<service_end},
                       start,service_end,service_end+(j==3)*GRID))
        start = service_end
    return digest,stream


def historical_generations(temp,seed):
    path=ROOT/"research/ch3_cooperative_cuts/archives"/f"forward_flat_{temp}C.tar"
    with tarfile.open(path) as tar:
        data=tar.extractfile(f"extended_Kim-Adapt+SAFE_{seed}/events.jsonl.gz").read()
    return [p for _,k,p in map(json.loads,gzip.decompress(data).splitlines()) if k=="kim_generation"]


def audit_kim(events, domain, load, temp, seed, summary):
    rng = random.Random(seed)
    anchors = ["A","C"]+random.Random(seed).sample([d for d in domain.legacy_ids if d not in ("A","C")],6)
    pop = anchors+[rng.choice(domain.order) for _ in range(CFG["population"]-len(anchors))]
    proxy, pool, checked = {}, {}, set()
    gens, target, tail = [], None, None
    for _,kind,p in events:
        if kind=="scene_proxy":
            proxy[tuple(p[:3])] = p[3]
        elif kind=="initial_population":
            require(p==pop,"Kim initial population")
        elif kind=="kim_generation":
            require(target is None and p[0]==len(gens) and p[1]==pop,"Kim selection/gen order")
            for dep in pop:
                if dep not in pool:
                    pool[dep]=search.evaluate_mapping(dep,lambda d,j,i:proxy[d,j,i])
            evaluated=[pool[dep] for dep in pop]
            require(p[2]==[m.valid for m in evaluated],"Kim validity")
            gens.append(p)
            target=next((c for c in search.ranked(pool.values(),domain) if c.dep not in checked),None)
            pop=[domain.child(search.lexicase(evaluated,rng),search.lexicase(evaluated,rng),rng,Counter())
                 for _ in range(len(pop))]
        elif kind=="kim_ranked":
            require(target is None,"Missing generation certification")
            # Ranking can include completed mappings from the final partial generation.
            for dep,opps,scores,total in p:
                m=search.evaluate_mapping(dep,lambda d,j,i:proxy[d,j,i])
                require(list(m.opps)==opps and list(m.scores)==scores,"Final proxy mapping")
                pool[dep]=m
            ranked=search.ranked(pool.values(),domain)
            require([m.dep for m in ranked]==[row[0] for row in p],"Final proxy order")
            tail=iter([m for m in ranked if m.dep not in checked])
        elif kind=="kim_check":
            phase,key,out = p
            expected=next(tail) if phase=="tail" else target
            require(expected is not None and key==[expected.dep,*expected.opps] and key[0] not in checked,
                    "Kim did not check highest untested valid mapping")
            require(phase=="tail" or phase==len(gens)-1,"Kim generation check time")
            checked.add(key[0])
            target=None
    require(len(gens)==summary["completed_generations"] and len(checked)==summary["checked"],"Kim counts")
    shared=None
    if load=="original":
        hist=historical_generations(temp,seed)
        shared=min(len(hist),len(gens))
        require(shared>0 and hist[:shared]==gens[:shared],"Historic Kim genetic path drift")
    return dict(generations=len(gens),checks=len(checked),original_matched_generations=shared)


def read_run(job,domain,from_archives=False):
    load,temp,seed,method=job
    with open_slot(*job,from_archives) as fetch:
        receipt=json.loads(fetch("receipt.json"))
        require(receipt["job"]==list(job),"Slot mismatch")
        files={n:fetch(n) for n in receipt["files"]}
    for n,raw in files.items():
        require(hashlib.sha256(raw).hexdigest()==receipt["files"][n],"Sealed member "+n)
    reservation=json.loads(files["reservation.json"])
    require(reservation["job"]==list(job) and reservation["core"]==receipt["core"],"Reservation identity")
    for n,h in reservation["inputs"].items():
        require(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h,"Source hash "+n)
    result=json.loads(gzip.decompress(files["result.json.gz"])) if "result.json.gz" in files else None
    digest,stream=workload(load)
    row=dict(load=load,ambient_c=temp,seed=seed,method=method,receipt=receipt["status"],core=receipt["core"],
             wall_s=receipt["wall_s"],request_sha256=digest,SAFE=0,energy_j=None,peak_upper_c=None,
             min_slack_ms=None,first_SAFE_s=None,best_hit_s=None,search_end_s=None,dep=None,cuts=None,
             opp_indices=None,opps=None,completed=None,stop=None,generations=None,checks=None,
             original_matched_generations=None,proof_sha256=None,parent_selections=None,hot_parent_selections=None,
             winner_hot_ancestor=None,winner_path=None)
    if result is None:
        require(receipt["status"]!="finished","Missing result")
        return row,[],None
    events=list(map(json.loads,gzip.decompress(files["events.jsonl.gz"]).splitlines()))
    summary=result["summary"]
    key=result["key"]
    require(result["job"]==list(job) and result["request_sha"]==digest,"Wrong load")
    require(events[0][1]=="identity" and events[0][2]["stream"]==digest and
            events[0][2]["domain"]==CFG["domain"],"Wrong search domain")
    curve=[(t,p[1],p[0]) for t,k,p in events if k=="incumbent"]
    require(all(0<t<CFG["admit_s"] for t,e,k in curve) and
            all(t2>=t and e2<e for (t,e,_),(t2,e2,_) in zip(curve,curve[1:])),"Invalid anytime ledger")
    reconstructed=[]
    for when,kind,p in events:
        if method=="kim_anytime" and kind=="kim_check":
            key_test,status,energy=p[1],p[2]["status"],p[2]["energy_j"]
        elif method=="joint" and kind=="replay":
            key_test,status,energy=p[0],p[1],p[2]
        elif method.startswith("energy_") and kind=="candidate":
            key_test,status,energy=p[0],p[3],p[4]
        else:
            continue
        if status=="SAFE" and (not reconstructed or energy<reconstructed[-1][0]):
            reconstructed.append((energy,key_test))
    require(reconstructed==[(e,k) for _,e,k in curve],"Incumbent curve differs from all certified candidates")
    row.update(search_end_s=result["search_end_s"],stop=summary.get("reason",summary.get("stop")))
    require(row["search_end_s"]<=row["wall_s"]<=CFG["cap_s"],"Run outside wall budget")
    if method=="kim_anytime":
        row.update(audit_kim(events,domain,load,temp,seed,summary))
    if method!="kim_anytime":
        kind="replay" if method=="joint" else "candidate"
        proposals=[p for _,k,p in events if k==kind]
        if method=="joint":
            lineage={tuple(p[0]):(p[1],p[8],p[9]) for p in proposals}
        else:
            lineage={tuple(p[0]):(p[3],p[1],p[2]) for p in proposals}
        parents=[tuple(p[0]) for _,k,p in events if k=="parent"]
        row.update(parent_selections=len(parents),hot_parent_selections=sum(lineage[k][0]=="VIOLATION" for k in parents))
        if method=="energy_safe_parent":
            require(all(lineage[k][0]=="SAFE" for k in parents),"Unsafe parent in ablation")
        if key:
            path=[]
            seen=set()
            current=key
            while current is not None:
                k=tuple(current)
                require(k not in seen,"Cycle in winning path")
                seen.add(k)
                status,action,current=lineage[k]
                path.append([list(k),action,status])
            row.update(winner_hot_ancestor=int(any(step[2]=="VIOLATION" for step in path[1:])),
                       winner_path=list(reversed(path)))
    if not key:
        require(not curve,"Lost SAFE incumbent")
        return row,curve,None
    proof=json.loads(gzip.decompress(files["selection.json.gz"]))
    a=result["result"]
    require(curve and curve[-1][2]==key and curve[-1][1]==a["energy_j"] and a["status"]=="SAFE",
            "Selected certificate differs from incumbent")
    require(curve[0][0]==summary["first_safe_s"],"First SAFE mismatch")
    case=f"{load}_{temp}C"
    check_selection(proof,dict(job=[case,"extended",method,seed],selected_genome=key,selected=a),
                    dict(ambient_c=temp,request_sha=digest),stream,domain)
    sha=receipt["files"]["selection.json.gz"]
    row.update(SAFE=1,energy_j=a["energy_j"],peak_upper_c=max(a["upper"]),min_slack_ms=a["slack_ms"],
               completed=a["completed"],first_SAFE_s=curve[0][0],best_hit_s=curve[-1][0],dep=key[0],
               cuts=proof["stages"],opp_indices=key[1:],opps=proof["opps"],proof_sha256=sha)
    return row,curve,proof
