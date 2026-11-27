"""Rebuild only the frozen W4 pools offline and trace original certified configurations."""
import csv
import gzip
import hashlib
import json
from bisect import bisect_left
from itertools import accumulate
from time import perf_counter

from paths_j import DATA, METHODS, WORK, inputs, write_csv, write_json
from analyze_replacement import members, run_records
from retention import e, h, scalar_four
from adapter import builder as frozen_builder, flow


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def targets(runs):
    selected = []
    for tag, run in runs.items():
        repeat = int(tag.split("-", 1)[0][1:])
        ontime = [r for r in run["records"] if r["end_s"] <= 60]
        fixed = [r for r in ontime if r["width"] == 4][:4]
        items = [(f"W4-{i}",r) for i,r in enumerate(fixed,1)]
        safe = [r for r in ontime if r["cert"]["metrics"]["status"]=="SAFE"]
        if safe:
            items.append(("best60",min(safe,key=lambda r:r["cert"]["metrics"]["E_J"])))
        for role, record in items:
            cert=record["cert"]
            selected.append(dict(method=run["method"],repeat=repeat,role=role,tag=tag,width=record["width"],
                                 plan=cert["plan_sha256"],cfg=record["id"],status=cert["metrics"]["status"],
                                 terminal_E_J=cert["metrics"]["E_J"],terminal_peak_C=max(cert["metrics"]["peak_hi"]),
                                 certified_s=record["end_s"]))
    return selected


def encode_targets(case, required):
    out={}
    for name, raw in members(DATA/"evidence"/case/"physical.tar.xz"):
        ident, filename = name.split("/")
        if filename=="plan.json" and ident in required:
            assert digest(raw.strip())==ident
            rows=json.loads(raw)["rows"]
            out[ident]=bytes(k+10*(u==3) for u,k,_ in rows[1::3])
    assert set(out)==required
    return out


def rebuild(item, method, runs, writer):
    base=method.split("-")[0]
    scalar=method.endswith("-S")
    build,_=frozen_builder(base)
    original_expand=build.__globals__["expand"]
    windows=[]
    summaries=[]
    c=flow(item,WORK/"audit"/item["case"]/method)
    def record(c,j,parents,arm,start,deadline,stage):
        pool,ok=original_expand(c,j,parents,arm,start,deadline,stage)
        assert ok
        if j+1==c.windows or not pool:
            return pool,ok
        ordered=sorted(pool.values(),key=lambda s:(round(s["energy"],11),s["config"]))
        comp={s["id"]:i for i,s in enumerate(e.diverse(ordered,False),1)}
        scal={s["id"]:i for i,s in enumerate(scalar_four(ordered,False),1)}
        keys=("energy","drain","risk")
        sorted_vals={k:sorted(round(float(s[k]),11) for s in ordered) for k in keys}
        actual=scal if scalar else comp
        window={}
        for s in ordered:
            ident=s["id"]
            ranks=[bisect_left(sorted_vals[k],round(float(s[k]),11)) for k in keys]
            row=dict(case=item["case"],method=method,window=j+1,id=ident,parent=s["parent"],
                     action="/".join(map(str,s["action"])),reference_E_J=s["energy"],drain_tick=s["drain"],
                     risk=s["risk"],prefix_peak_C=s["peak"],energy_rank=ranks[0],drain_rank=ranks[1],
                     risk_rank=ranks[2],rank_sum=sum(ranks),complementary_seat=comp.get(ident,0),
                     scalar_seat=scal.get(ident,0),actual_seat=actual.get(ident,0))
            if writer["handle"] is None:
                writer["handle"]=csv.DictWriter(writer["file"],fieldnames=list(row),lineterminator="\n")
                writer["handle"].writeheader()
            writer["handle"].writerow(row)
            window[ident]=row
        windows.append(window)
        summaries.append(dict(case=item["case"],method=method,window=j+1,candidates=len(ordered),
                              shared=len(set(comp)&set(scal)),complementary_only=len(set(comp)-set(scal)),
                              scalar_only=len(set(scal)-set(comp)),same_seats=set(comp)==set(scal)))
        return pool,ok
    logged={"actions":[],"groups":[],"beam":[]}
    selection=scalar_four if scalar else e.diverse
    offline=h.with_binding(build,expand=record,diverse=selection)
    terminal=offline(c,base,4,perf_counter(),float("inf"),logged)
    for run in (r for r in runs.values() if r["method"]==method):
        actual=run["search"][0]
        assert actual["width"]==4
        assert actual["beam"]==logged["beam"], (c.label,method,"W4 parent identities")
        n=[r for r in run["records"] if r["width"]==4 and r["end_s"]<=60][:4]
        assert [s["id"] for s in terminal[:len(n)]]==[r["id"] for r in n]
        assert actual["terminal"]==len(terminal)
    return windows,summaries


def detail(item,runs,goals,states,configs):
    cuts=list(accumulate(60 if letter=="L" else 100 for letter in item["word"]))
    rows=[]
    for goal in goals:
        method=goal["method"]
        opposite=method[:-2] if method.endswith("-S") else method+"-S"
        config=configs[goal["plan"]]
        assert digest(config)==goal["cfg"] and len(config)==cuts[-1]
        stage=next(s for s in runs[goal["tag"]]["search"] if s["width"]==goal["width"])
        parent=digest(b"")
        for j,right in enumerate(cuts[:-1]):
            ident=digest(config[:right])
            assert ident in stage["beam"][j], (goal["plan"],goal["width"],j+1)
            def lookup(arm):
                if j>=len(states[arm]):
                    return None,"W4_ended_before_window"
                s=states[arm][j].get(ident)
                if s is not None:
                    assert s["parent"]==parent
                    return s,("kept" if s["actual_seat"] else "pruned_in_pool")
                prev=(j==0 or (parent in states[arm][j-1] and states[arm][j-1][parent]["actual_seat"]!=0))
                return None,("missing_under_kept_parent" if prev else "parent_not_kept")
            here,observed=lookup(method)
            other,alt=lookup(opposite)
            row=dict(case=item["case"],**goal,window=j+1,prefix=ident,parent=parent,
                     source_W4=observed,other_W4=alt,actual_producing_width_kept=True)
            cols=("action","reference_E_J","drain_tick","risk","prefix_peak_C","energy_rank","drain_rank",
                  "risk_rank","rank_sum","complementary_seat","scalar_seat","actual_seat")
            row.update({k:here[k] if here else None for k in cols})
            row["other_actual_seat"]=other["actual_seat"] if other else None
            rows.append(row)
            parent=ident
    return rows


def main():
    dest=DATA/"paths";dest.mkdir(parents=True,exist_ok=True)
    allrows=[];agg=[];lineages=0
    for item in inputs():
        case=item["case"]
        runs=run_records(case)
        goals=targets(runs)
        cfgs=encode_targets(case,{g["plan"] for g in goals})
        states={}
        with gzip.open(dest/(case+"_pools.csv.gz"),"wt",encoding="utf8",newline="") as f:
            writer={"file":f,"handle":None}
            for method in METHODS:
                states[method],summary=rebuild(item,method,runs,writer)
                agg.extend(summary)
        rows=detail(item,runs,goals,states,cfgs)
        lineages+=len(goals)
        allrows.extend(rows)
        print("PATHS",case,len(goals),len(rows),flush=True)
    write_csv(dest/"windows.csv",agg)
    with gzip.open(dest/"lineage.csv.gz","wt",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(allrows[0]),lineterminator="\n")
        w.writeheader();w.writerows(allrows)
    write_json(dest/"verification.json",dict(arm_case_W4_rebuilds=48,compared_online_stages=144,
               certified_targets_with_repeat_and_role=lineages,verified_prefix_links=len(allrows),
               W4_pool_observations=len(agg),candidates=sum(x["candidates"] for x in agg),
               different_sets=sum(not x["same_seats"] for x in agg)))


if __name__=="__main__":
    main()
