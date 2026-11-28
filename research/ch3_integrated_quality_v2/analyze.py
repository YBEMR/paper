"""Verify the certificates, mapping identities and online decisions, then form paired tables."""
import collections
import hashlib
import json
import statistics as st
import sys
import tarfile
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent/"ch3_integrated_quality_v1"))
import audit as old
from evidence import logs, read, verify

ARC = ROOT/"archive"
TAB = ROOT/"tables"
ARMS = ("single", "multi")
old.TAB = TAB


def map_ids(folder):
    ids = {}
    for p in sorted(folder.glob("*.tar")):
        with tarfile.open(p) as stream:
            for member in stream:
                if member.name.endswith("/plan"):
                    plan = json.loads(zlib.decompress(stream.extractfile(member).read()))
                    devices = bytes(row[0] for row in plan["rows"][1::3])
                    ids[member.name.split("/")[0]] = hashlib.sha256(devices).hexdigest()
    return ids


def timed_events(events, limit, kind):
    return [e for e in events if e["event"]==kind and e["t"]<=limit]


def summarize_cell(folder, label, rep, arm, env, certs, ids):
    path = folder/f"r{rep}-{arm}"
    rc = read(path/"receipt.json")
    assert rc["rep"]==rep and rc["case"]==label and rc["version"]==("integrated" if arm=="single" else "multi")
    assert rc["host"]==env["warm"]["host"] and rc["cpu"]==env["warm"]["core"] and rc["source"]==env["source"]
    cutoff,end=rc["cut"],rc["charged_s"]
    assert 0<end<=60 and rc["limit"]==60
    sc,rf=logs(path/"search.jsonl"),logs(path/"refine.jsonl")
    candidates=timed_events(sc,cutoff,"certificate")
    post=[e for e in rf if e["t"]<=60]
    for e in candidates+timed_events(post,60,"certificate"):
        old.checked(e["point"],certs)
    safe=[e for e in candidates if old.safe(e["point"])]
    first=safe[0]["t"] if safe else None
    assert cutoff==(55 if first is not None and first<55 else 60)
    seed=old.incumbent(candidates)
    global_best=seed
    best_time=next((e["t"] for e in safe if e["point"]==seed),None)
    best_rank=1 if seed else None
    ctx=dict(case=folder.name,rep=rep,version=arm)
    pool={}
    for e in safe:
        p=e["point"]; key=ids[p["plan"]]
        order=(p["bounds"][1],e["t"],p["plan"])
        if key not in pool or order<pool[key][0]:
            pool[key]=(order,p)
    ranking=sorted(pool,key=lambda k:pool[k][0])
    nominated=[]
    sel=next((e for e in post if e["event"]=="end" and e["task"]=="selection"),None)
    if seed and cutoff==55:
        first_key=ids[seed["plan"]]
        if arm=="single":
            nominated=[seed]
        elif sel:
            nominated=[seed]+[pool[k][1] for k in ranking if k!=first_key][:3]
            assert sel["pool_size"]==len(pool) and sel["seeds"]==[p["plan"] for p in nominated]
            assert {r["mapping"]:r["plan"] for r in sel["representatives"]}=={k:v[1]["plan"] for k,v in pool.items()}
    universe=[dict(**ctx,mapping=k,lowest_upper_plan=pool[k][1]["plan"],upper=pool[k][0][0],
                   pool_rank=i,nomination=next((j for j,n in enumerate(nominated,1) if ids[n["plan"]]==k),None))
              for i,k in enumerate(ranking,1)]
    maps=[];stages=[];anchor=None;anchor_t=None
    for rank,initial in enumerate(nominated,1):
        local=initial;mapping=ids[local["plan"]]
        ev=[e for e in post if e.get("rank",1)==rank]
        started=next((e["t"] for e in ev if e["event"]=="begin" and e["task"]=="handoff"),None)
        by_stage={};complete=False
        for tag in ("ordinary","thermal"):
            rr=[e for e in ev if e.get("stage","").split("/")[-1]==tag]
            pred=local
            proposals=timed_events(rr,60,"certificate")
            assert len(proposals)<=1
            candidate=proposals[0] if proposals else None
            if candidate:
                p=candidate["point"]
                assert ids[p["plan"]]==mapping
                if old.better(p,local):
                    local=p
                    if old.better(local,global_best):
                        global_best=local;best_rank=rank;best_time=candidate["t"]
                if arm=="multi":
                    assert candidate["local_best"]==local["plan"] and candidate["global_best"]==global_best["plan"]
            ends=timed_events(rr,60,"stage_end")
            assert len(ends)<=1
            if ends:
                assert ends[0]["incumbent"]==local["plan"]
            if tag=="thermal" and ends:
                complete=True
                if rank==1:
                    anchor=global_best;anchor_t=ends[0]["t"]
            by_stage[tag]=local
            stages.append(dict(**ctx,rank=rank,mapping=mapping,stage=tag,finished=bool(ends),
                stage_end_s=ends[0]["t"] if ends else None,raw_delivery_s=candidate["t"] if candidate else None,
                raw_status=candidate["point"]["status"] if candidate else None,
                raw_plan=candidate["point"]["plan"] if candidate else None,raw_J=candidate["point"]["J"] if candidate else None,
                retained_plan=local["plan"],retained_J=local["J"],gain_J=old.gain(pred,local)))
        for e in timed_events(ev,60,"map_end"):
            assert complete and e["local_best"]==local["plan"] and e["global_best"]==global_best["plan"]
        maps.append(dict(**ctx,rank=rank,mapping=mapping,started_s=started,complete=complete,seed_plan=initial["plan"],
            seed_J=initial["J"],seed_upper=initial["bounds"][1],ordinary_J=by_stage["ordinary"]["J"],
            ordinary_upper=by_stage["ordinary"]["bounds"][1],ordinary_gain_J=old.gain(initial,by_stage["ordinary"]),
            thermal_gain_J=old.gain(by_stage["ordinary"],local),**old.describe(local)))
    for key,field in (("seed_upper","seed_rank"),("ordinary_upper","ordinary_rank"),("upper","final_rank")):
        for i,entry in enumerate(sorted(maps,key=lambda r:(r[key],r["rank"])),1):
            entry[field]=i
    for entry in maps:
        entry["final_chosen"]=entry["rank"]==best_rank
    sx=min(cutoff,rc["search_rc"]["supervisor_t"])
    dp_events=[e for p in [path/"events.jsonl",*sorted(path.glob("map*/events.jsonl"))]
               for e in logs(p) if e["kind"]=="dp" and e["t"]<=end]
    dp=sum(e["elapsed_s"] for e in dp_events)
    costs=dict(instance_s=old.spans(sc,"instance",sx),construct_s=old.spans(sc,"construct",sx),
        search_cert_evidence_s=old.spans(sc,"search_cert",sx),selection_s=old.spans(post,"selection",end),
        handoff_s=old.spans(post,"handoff",end),dp_s=dp,dp_cert_evidence_s=old.spans(post,"dp_cert",end))
    costs["other_s"]=end-sum(costs.values())
    assert costs["other_s"]>=-.01
    row=dict(**ctx,host=rc["host"],core=rc["cpu"],source=rc["source"],run=rc["run"],charged_s=end,
        supervisor_s=rc["wall_including_supervision"],cut_s=cutoff,first_safe_s=first,construction_J=old.J(seed),
        search_end_s=sx,search_certs=len(candidates),safe_search_certs=len(safe),distinct_maps=len(pool),
        nominated=len(maps),started=sum(r["started_s"] is not None for r in maps),completed=sum(r["complete"] for r in maps),
        anchor_J=old.J(anchor),anchor_plan=anchor["plan"] if anchor else None,anchor_s=anchor_t,
        extra_J=old.gain(anchor,global_best),strict_extra=bool(anchor and old.better(global_best,anchor)),
        best_rank=best_rank,best_mapping=ids[global_best["plan"]] if global_best else None,
        final_best_delivered_s=best_time,dp_calls=len(dp_events),reserve_calls=sum(e["reserve"]==13 for e in dp_events),
        **costs,**old.describe(global_best))
    return row,maps,stages,universe,global_best


def main():
    start=time.perf_counter()
    TAB.mkdir(exist_ok=True)
    rows=[];maps=[];stages=[];pool=[];flows=[];pairs=[];physical=0
    for lane in sorted(ARC.glob("*/lane.json")):
        folder=lane.parent;env=read(lane);phys=folder/"physical"
        verify(phys)
        certs=old.certified_members(phys);ids=map_ids(phys)
        assert set(certs)==set(ids);physical+=len(ids)
        points={}
        assert set(map(tuple,env["order"]))=={(i,a) for i in (1,2,3) for a in ARMS}
        for i in (0,2,4):
            assert env["order"][i][1]!=env["order"][i+1][1]
        assert env["order"][0][1]==env["order"][4][1]!=env["order"][2][1]
        for i,a in env["order"]:
            row,mm,ss,pp,pt=summarize_cell(folder,env["case"],i,a,env,certs,ids)
            rows.append(row);maps+=mm;stages+=ss;pool+=pp;points[i,a]=pt
        for i in (1,2,3):
            a,b=(points[i,v] for v in ARMS)
            pairs.append(dict(case=folder.name,rep=i,single_J=old.J(a),multi_J=old.J(b),strict=old.outcome(b,a),gain_J=old.gain(a,b)))
        sub=[r for r in rows if r["case"]==folder.name]
        reliable=[sum(old.safe(points[i,a]) for i in (1,2,3)) for a in ARMS]
        a,b=(old.summarize([points[i,k] for i in (1,2,3)]) for k in ARMS)
        common=min(reliable)>=2
        extra=[r for r in sub if r["version"]=="multi" and r["strict_extra"]]
        flows.append(dict(case=folder.name,single_safe=reliable[0],multi_safe=reliable[1],single_J=old.J(a),multi_J=old.J(b),
            single_bounds=a["bounds"] if a else None,multi_bounds=b["bounds"] if b else None,
            strict=old.outcome(b,a) if common else "unpaired",gain_J=old.gain(a,b) if common else None,
            gain_pct=100*old.gain(a,b)/a["J"] if common else None,additional_wins=len(extra),
            same_winning_mapping=max(collections.Counter(r["best_mapping"] for r in extra).values(),default=0),
            median_extra_J=old.median([r["extra_J"] for r in sub if r["version"]=="multi" and r["extra_J"] is not None])))
    assert len(rows)==72 and len(flows)==12 and len(pairs)==36 and len({r["source"] for r in rows})==1
    total=sum(r["charged_s"] for r in rows);assert total<=4320
    common=[r for r in flows if r["strict"]!="unpaired"]
    reliable={a:sum(r[a+"_safe"]>=2 for r in flows) for a in ARMS}
    pct=st.mean(r["gain_pct"] for r in common) if common else None
    repeated=sum(r["additional_wins"]>=2 for r in flows)
    summary=dict(reliable=reliable,common=len(common),mean_pct=pct,
        mean_J=st.mean(r["gain_J"] for r in common) if common else None,
        outcomes=dict(collections.Counter(r["strict"] for r in flows)),rep_outcomes=dict(collections.Counter(r["strict"] for r in pairs)),
        repeatable_flows=repeated,charged_s=total,physical=physical,source=rows[0]["source"],run=rows[0]["run"],
        adopt=bool(common and pct>0 and reliable["multi"]>=reliable["single"] and repeated),
        gate_s=read(ARC/"gate/gate.json")["wall_s"],warm_s=sum(read(p)["warm"]["seconds"] for p in ARC.glob("*/lane.json")),
        offline_pack_s=sum(read(p)["offline_s"] for p in ARC.glob("*/archive_receipt.json")))
    for name,values in (("runs",rows),("mappings",maps),("stages",stages),("safe_pool",pool),("flows",flows),("paired_repeats",pairs)):
        old.csvout(name+".csv",values)
    summary["audit_s"]=time.perf_counter()-start
    (TAB/"decision.json").write_text(json.dumps(summary,indent=2)+"\n")
    return summary,rows,maps,flows
