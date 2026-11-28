"""Audit only delivered certificates and matched fourth-position opportunity costs."""
import csv
import hashlib
import json
import statistics as st
import sys
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"ch3_integrated_quality_v2"))
from analyze import map_ids
import audit as q
from evidence import read,logs,verify
ARC=ROOT/"archive";TAB=ROOT/"tables"
ARMS=("multi","hot")


def examine(folder,meta,rep,arm,certs,ids):
    cell=folder/f"r{rep}-{arm}"
    rc=read(cell/"receipt.json")
    assert rc["version"]==arm and rc["rep"]==rep and rc["source"]==meta["source"]
    assert rc["host"]==meta["warm"]["host"] and rc["cpu"]==meta["warm"]["core"] and rc["limit"]==60
    end=rc["charged_s"];cut=rc["cut"];assert end<=60
    sc=logs(cell/"search.jsonl");rf=[e for e in logs(cell/"refine.jsonl") if e["t"]<=60]
    events=[e for e in sc if e["event"]=="certificate" and e["t"]<=cut]
    reg={};hot={};safe={};ident=[]
    ctx=dict(case=folder.name,rep=rep,arm=arm)
    for e in events:
        p=e["point"];q.checked(p,certs);k=p["plan"];mid=ids[k]
        if p["status"] not in ("SAFE","HOT"):continue
        order=(p["bounds"][1],e["t"],k)
        reg[k]=p
        group=safe if q.safe(p) else hot
        if mid not in group or order<group[mid]:group[mid]=order
    only={k:v for k,v in hot.items() if k not in safe}
    for typ,pool in (("SAFE",safe),("HOT-only",only)):
        for k,order in pool.items():
            ident.append(dict(**ctx,mapping=k,category=typ,representative=order[2],upper=order[0],
                representative_s=order[1],also_hot=k in safe and k in hot))
    seed=q.incumbent(events);current=seed
    first=next((e["t"] for e in events if q.safe(e["point"])),None)
    assert cut==(55 if first is not None and first<55 else 60)
    delivered=next((e["t"] for e in events if seed and e["point"]==seed),None)
    fourth=None;chosen_hot=None;selected=[];stages=[];witness=None;fourth_result=None
    selection=next((e for e in rf if e.get("task")=="selection" and e["event"]=="end"),None)
    if seed and cut==55:
        ordered=[seed["plan"]]+[v[2] for k,v in sorted(safe.items(),key=lambda kv:kv[1]) if k!=ids[seed["plan"]]][:3]
        fourth=ordered[3] if len(ordered)>3 else None
        lowest=min(only.values(),default=None)
        if lowest and lowest[0]<seed["bounds"][0]:
            chosen_hot=lowest[2]
        if selection:
            if arm=="hot" and chosen_hot:
                selected=list(enumerate(ordered[:3],1))+[(4,chosen_hot)]
            else:selected=list(enumerate(ordered,1))
            assert selection["seeds"]==[k for _,k in selected]
            if arm=="hot":
                assert selection["hot_only"]==len(only) and selection["eligible"]==bool(chosen_hot)
                assert selection["displaced"]==(reg[fourth] if fourth else None)
    completions=0;started=0;before4=None;ordinary=None;thermal=None;hot_start=None
    best_rank=1 if seed else None;hot_delivery=None;local_four_complete=False
    byrank={}
    for i,key in selected:
        origin=reg[key];is_hot=origin["status"]=="HOT"
        assert not is_hot or (arm=="hot" and i==4 and ids[key] in only)
        local=None if is_hot else origin
        ev=[e for e in rf if e.get("rank")==i]
        began=next((e for e in ev if e["event"]=="map_start"),None)
        if began:
            assert began["seed"]==key;started+=1
        if i==4:before4=current
        if is_hot and began:hot_start=began["t"]
        guide=key
        for stage in ("ordinary","thermal"):
            ss=[e for e in ev if e.get("stage")==f"map{i}/{stage}"]
            beg=next((e for e in ss if e.get("task")=="refinement" and e["event"]=="begin"),None)
            if is_hot and beg:assert beg["guide"]==guide
            candidate=next((e for e in ss if e["event"]=="certificate"),None)
            pt=candidate["point"] if candidate else None
            if pt:
                q.checked(pt,certs)
                assert ids[pt["plan"]]==ids[key]
                if q.better(pt,local):
                    local=pt
                    if q.better(pt,current):
                        current=pt;delivered=candidate["t"];best_rank=i
                        if is_hot:witness=current;hot_delivery=delivered
                assert candidate["local_best"]==(local["plan"] if local else None) and candidate["global_best"]==current["plan"]
                if is_hot and stage=="ordinary" and pt["status"] in ("SAFE","HOT"):
                    guide=pt["plan"]
            done=next((e for e in ss if e["event"]=="stage_end"),None)
            if done:
                assert done["incumbent"]==(local["plan"] if local else None)
            if stage=="thermal" and done:
                completions+=1
                if i==4:local_four_complete=True
            if is_hot:
                if stage=="ordinary":ordinary=pt
                else:thermal=pt
            stages.append(dict(**ctx,rank=i,seed=key,seed_status=origin["status"],seed_J=origin["J"],mapping=ids[key],
                stage=stage,started=beg is not None,completed=done is not None,
                raw_status=pt["status"] if pt else None,raw_plan=pt["plan"] if pt else None,raw_J=q.J(pt),
                raw_peak=pt["peak"] if pt else None,t=candidate["t"] if candidate else None,
                local_plan=local["plan"] if local else None,global_plan=current["plan"],global_J=current["J"]))
        if i==4:fourth_result=local
        byrank[i]=local
    if current:assert q.safe(current) and current["slack"]>=0 and current["peak"]<=80
    if before4 is None and selected and len(selected)<4 and completions==len(selected):before4=current
    sx=min(cut,rc["search_rc"]["supervisor_t"])
    dps=[e for p in cell.glob("map*/events.jsonl") for e in logs(p) if e["kind"]=="dp" and e["t"]<=60]
    times=dict(instance_s=q.spans(sc,"instance",sx),construct_s=q.spans(sc,"construct",sx),
        search_cert_s=q.spans(sc,"search_cert",sx),selection_s=q.spans(rf,"selection",end),handoff_s=q.spans(rf,"handoff",end),
        dp_s=sum(e["elapsed_s"] for e in dps),dp_cert_s=q.spans(rf,"dp_cert",end))
    times["other_s"]=end-sum(times.values());assert times["other_s"]>=-.01
    nominated_hot=any(reg[k]["status"]=="HOT" for _,k in selected)
    row=dict(**ctx,host=rc["host"],core=rc["cpu"],search_cut_s=cut,charged_s=end,supervisor_s=rc["wall_including_supervision"],
        first_safe_s=first,final_best_s=delivered,construction_J=q.J(seed),safe_maps=len(safe),hot_only=len(only),shared=len(set(safe)&set(hot)),
        online_eligible=bool(chosen_hot),hot_nominated=nominated_hot,hot_started=hot_start is not None,
        nominal_safe4=fourth,eligible_plan=chosen_hot,hot_mapping=ids[chosen_hot] if nominated_hot else None,
        nominated=len(selected),started=started,complete=completions,dp_calls=len(dps),reserve_calls=sum(e["reserve"]==13 for e in dps),
        pre4_plan=before4["plan"] if before4 else None,pre4_J=q.J(before4),fourth_seed=next((k for i,k in selected if i==4),None),
        fourth_best=fourth_result["plan"] if fourth_result else None,fourth_best_J=q.J(fourth_result),fourth_completed=local_four_complete,
        extra_J=q.gain(before4,current),ordinary_status=ordinary["status"] if ordinary else None,thermal_status=thermal["status"] if thermal else None,
        recovered=bool(q.safe(ordinary) or q.safe(thermal)),hot_win=witness is not None,hot_win_s=hot_delivery,best_rank=best_rank,
        source=rc["source"],run=rc["run"],**q.describe(current),**times)
    return row,stages,ident,current,fourth_result,before4


def main():
    import time
    start=time.perf_counter();TAB.mkdir(exist_ok=True);q.TAB=TAB
    rows=[];stages=[];identity=[];flows=[];pairs=[];opportunities=[];wits=[];physical=0
    for lane in sorted(ARC.glob("*/lane.json")):
        folder=lane.parent;meta=read(lane);phys=folder/"physical"
        verify(phys);ids=map_ids(phys);certs=q.certified_members(phys);assert set(ids)==set(certs)
        physical+=len(ids);saved={}
        order=meta["order"];assert set(map(tuple,order))=={(i,a) for i in (1,2,3) for a in ARMS}
        assert order[0][1]==order[4][1]!=order[2][1] and all(order[i][1]!=order[i+1][1] for i in (0,2,4))
        for i,a in order:
            row,ss,identity_rows,p,fourth,before=examine(folder,meta,i,a,certs,ids)
            rows.append(row);stages+=ss;identity+=identity_rows;saved[i,a]=(row,p,fourth,before)
            if row["hot_nominated"]:wits.append(row)
        for i in (1,2,3):
            c,cp,c4,_=saved[i,"multi"];h,hp,_,h3=saved[i,"hot"]
            pairs.append(dict(case=folder.name,rep=i,current_J=q.J(cp),new_J=q.J(hp),strict=q.outcome(hp,cp),gain_J=q.gain(cp,hp)))
            if h["hot_nominated"]:
                matched=c["fourth_seed"]==h["nominal_safe4"] and bool(h["nominal_safe4"]) and c["fourth_completed"]
                potential=q.gain(h3,c4) if matched and q.better(c4,h3) else 0 if matched and h3 else None
                missed=q.gain(hp,c4) if matched and q.better(c4,hp) else 0 if matched and hp else None
                opportunities.append(dict(case=folder.name,rep=i,matched=matched,displaced_plan=h["nominal_safe4"],
                    control_fourth_plan=c["fourth_seed"],control_fourth_endpoint=c["fourth_best"],
                    same_pre4=c["pre4_plan"]==h["pre4_plan"],pre4_J=q.J(h3),counterfactual_fourth_J=q.J(c4) if matched else None,
                    forgone_positive_gain_J=potential,loss_after_hot_J=missed,hot_final_J=q.J(hp)))
        vals=[[saved[i,a][1] for i in (1,2,3)] for a in ARMS]
        n0,n1=[sum(q.safe(p) for p in v) for v in vals];p0,p1=map(q.summarize,vals)
        common=min(n0,n1)>=2
        winners=[saved[i,"hot"][0] for i in (1,2,3) if saved[i,"hot"][0]["hot_win"]]
        flows.append(dict(case=folder.name,current_safe=n0,new_safe=n1,current_J=q.J(p0),new_J=q.J(p1),
            current_bounds=p0["bounds"] if p0 else None,new_bounds=p1["bounds"] if p1 else None,
            gain_J=q.gain(p0,p1) if common else None,gain_pct=100*q.gain(p0,p1)/p0["J"] if common else None,
            strict=q.outcome(p1,p0) if common else "unpaired",online_nominations=sum(saved[i,"hot"][0]["hot_nominated"] for i in (1,2,3)),
            hot_wins=len(winners),same_mapping=max(Counter(r["hot_mapping"] for r in winners).values(),default=0)))
    assert len(rows)==72 and len(flows)==12 and len(pairs)==36 and len({r["source"] for r in rows})==1
    total=sum(r["charged_s"] for r in rows);assert total<=4320
    for name,items in (("runs",rows),("stages",stages),("mapping_identity",identity),("paired",pairs),("flows",flows),
                       ("hot_witnesses",wits),("fourth_opportunity",opportunities)):
        q.csvout(name+".csv",items)
    common=[r for r in flows if r["strict"]!="unpaired"]
    rel=[sum(r[k]>=2 for r in flows) for k in ("current_safe","new_safe")]
    pct=st.mean(r["gain_pct"] for r in common) if common else None
    repeated=[r["case"] for r in flows if r["hot_wins"]>=2]
    summ=dict(coverage=rel,common=len(common),mean_pct=pct,mean_J=st.mean(r["gain_J"] for r in common) if common else None,
        repeatable=repeated,loss_flows=[r["case"] for r in flows if r["strict"]=="loss"],
        outcomes=dict(Counter(r["strict"] for r in flows)),paired=dict(Counter(r["strict"] for r in pairs)),
        charged_s=total,physical=physical,source=rows[0]["source"],run=rows[0]["run"],
        warm_s=sum(read(p)["warm"]["seconds"] for p in ARC.glob("*/lane.json")),
        pack_s=sum(read(p)["offline_s"] for p in ARC.glob("*/archive_receipt.json")),audit_s=time.perf_counter()-start)
    (TAB/"decision.json").write_text(json.dumps(summ,indent=2)+"\n")
    return summ,rows,flows,wits,opportunities
