"""Certificate-based, offline paired analysis. No DP, replay, or heat calls."""
import csv
import gzip
import json
import statistics
import tarfile
import zlib
from collections import Counter,defaultdict
from pathlib import Path
from pack import verify
from inventory import ROOT,ARCH,METHODS,read,readcsv,save
A=ROOT/"analysis"
def out(n,values):
    rows=list(values);p=A/n
    with p.open("w",newline="") as f:
        if not rows:return
        w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for row in rows for k in row)),lineterminator="\n")
        w.writeheader();w.writerows(rows)
def lines(p):
    with gzip.open(p,"rb") as f:return [json.loads(line) for line in f if line.endswith(b"}\n")]
def map_rows(p):return [json.loads(l) for l in gzip.open(p,"rb")]
def beats(a,b):
    return bool(a and a["status"]=="SAFE" and (not b or b["status"]!="SAFE" or a["bounds"][1]<b["bounds"][0]))
def best(ps):
    result=None
    for p in ps:
        if beats(p,result):result=p
    return result
def fields(stage,p):
    if p is None:return {stage+"_status":"NO_PHYSICAL"}
    return {stage+"_"+k:p[k] for k in ("plan","status","J","peak","slack","switches","e35")}|{stage+"_lo":p["bounds"][0],stage+"_hi":p["bounds"][1]}
def sign(b,a):
    if beats(b,a):return "win"
    if beats(a,b):return "loss"
    return "tie"
def delta(a,b):return a["J"]-b["J"] if a and b else None
def flat(x):return x if x is not None else {}
def main():
    A.mkdir(exist_ok=True);verify(ARCH/"physical")
    idx=read(ARCH/"physical/index.json")["plans"];budget=[];case_rows=[];runs=[];visits=[];rawjoins=[];hotw=[];allpool=[];pools={};endpoints={}
    certificates={}
    for name in sorted((ARCH/"physical").glob("*.tar")):
        with tarfile.open(name,"r:") as tar:
            for member in tar:
                if member.name.endswith("/cert.z"):
                    d=json.loads(zlib.decompress(tar.extractfile(member).read()))
                    certificates[d["plan_sha256"]]=d
    def check_point(pt):
        cert=certificates[pt["plan"]];m=cert["metrics"]
        assert (pt["status"],pt["J"],pt["e35"],pt["bounds"])==(m["status"],m["E_J"],cert["E35_J"],m["E_bounds"])
        assert pt["peak"]==max(m["peak_hi"]) and pt["switches"]==m["switch_count"] and pt["slack"]==m["min_deadline_slack_ms"]
        assert all(m[k]==v for k,v in pt["energy"].items())
    prior={r["cell"]:r for r in readcsv(ROOT.parent/"m6a_global_frequency_mapping/archive/endpoints.csv") if r["stage"]=="final"}
    stages_detail=[];shared_signatures={};n_verified=0;original_pairings=[];all_mapping_classes=[]
    for root in sorted((ARCH/"identity").iterdir()):
        case=root.name
        audit=read(root/"audit.json");selection=read(root/"selection.json")
        rows=map_rows(root/"mappings.jsonl.gz");calls=map_rows(root/"calls.jsonl.gz")
        original=map_rows(root/"physical.jsonl.gz")
        meta={r["plan"]:r for r in original}
        assert len(meta)==audit["physical"] and len(calls)==audit["selected_calls"]
        byplan={r["plan"]:r for r in calls}
        for m in METHODS:
            local={r["mapping"]:r for r in rows if r["source"]==m};pools[case,m]=local
            bymethod=[r for r in calls if r["source"]==m]
            distinct_phys={r["plan"] for r in bymethod};noms=selection["methods"][m]
            joined=defaultdict(list)
            for r in bymethod:joined[r["mapping"]].append(r)
            for k,vis in joined.items():
                statuses={r["status"] for r in vis}
                if k in local:
                    first_any=min(vis,key=lambda z:(z["first_s"],z["call"]))
                    local[k].update(first_any_s=first_any["first_s"],first_any_width=first_any["width"],
                                    first_any_rank=first_any["beam_rank"],first_any_status=first_any["status"])
                member_plans=sorted({r["plan"] for r in vis})
                all_mapping_classes.append(dict(case=case,source=m,mapping=k,saw_SAFE="SAFE" in statuses,saw_HOT="HOT" in statuses,
                    outcomes=sorted(statuses),only_invalid=k not in local,hot_only=local.get(k,{}).get("hot_only",False),
                    member_configs=[dict(plan=p,config=meta[p]["cfg"],certificate_file_sha=meta[p]["certificate_file_sha256"],
                    trace=meta[p]["event_array_sha256"]) for p in member_plans]))
            u=len(local);hotkeys={k for k,e in local.items() if e["hot_only"]}
            superthreshold=False
            if not hotkeys:assert noms["S"]==noms["H"]
            original_status=Counter(r["status"] for r in bymethod)
            case_rows.append(dict(case=case,source=m,ontime_calls=len(bymethod),physical=len(distinct_phys),valid_maps=u,
                safe_maps=sum(r["local_safe"] for r in local.values()),local_hot_only=sum(not r["local_safe"] for r in local.values()),
                hot_only=len(hotkeys),safe_and_hot=sum(r["local_safe"] and r["local_hot"] for r in local.values()),
                other_side_safe=sum(r["shared_other_safe"] for r in local.values()),k=selection["k"],selected_hot_H=len(set(noms["H"])&hotkeys),
                maps_shared_between_S_H=len(set(noms["H"])&set(noms["S"])),excluded=sum(v for k,v in original_status.items() if k not in ("HOT","SAFE")),
                raw_safe=original_status["SAFE"],raw_hot=original_status["HOT"]))
            modes=[("fair","S"),("fair","H")]+([("offline","ALL")] if case=="C10" else [])
            reference_p=None
            for group,arm in modes:
                p=ARCH/group/case/m/arm;rc=read(p/"receipt.json");records=lines(p/"mapping_events.jsonl.gz")
                assert rc["status"] in ("CAP","NATURAL") and rc["wall_s"]<=rc["limit_s"]
                charged=rc["wall_s"];budget.append(dict(stage=group,case=case,source=m,arm=arm,**rc))
                completed=[e for e in records if e["kind"]=="complete"]
                starts=[e for e in records if e["kind"]=="start"];assert [e["mapping"] for e in starts]==noms[arm][:len(starts)]
                assert [r["mapping"] for r in completed]==noms[arm][:len(completed)]
                if rc["status"]=="NATURAL":assert len(completed)==len(noms[arm])
                stage_rows=[e for e in records if e["kind"]=="stage"]
                pts=[e["point"] for e in stage_rows if e["point"]]
                assert all(e["t"]<=rc["limit_s"] for e in records)
                assert all(r["plan"] in idx for r in pts)
                for phys in pts:check_point(phys)
                for e in stage_rows:
                    if e["point"]:
                        stages_detail.append(dict(case=case,source=m,group=group,arm=arm,slot=e["i"],mapping=e["mapping"],t=e["t"],
                           stage=e["stage"],**{k:v for k,v in e["point"].items() if k not in ("bounds","energy")},**e["point"]["energy"],
                           lo=e["point"]["bounds"][0],hi=e["point"]["bounds"][1]))
                rp=read(p/"P.json")["best"];rb=read(p/"incumbent.json");result=rb["endpoint"];kbest=rb["mapping"]
                assert best(pts)["plan"]==result["plan"]
                ordinary=best(e["point"] for e in stage_rows if e["stage"] in ("ordinary","history"));historical=best(e["point"] for e in stage_rows if e["stage"]=="history")
                assert rp and result and ordinary and historical
                if reference_p is None:reference_p=rp
                else:assert rp["plan"]==reference_p["plan"]
                hist=prior["stage2/"+case+"/"+m]
                endpoints[case,m,arm]=(rp,ordinary,result)
                sig=dict(group=group,case=case,source=m,arm=arm)
                raword=best(e["point"] for e in stage_rows if e["stage"]=="ordinary")
                rawheat=best(e["point"] for e in stage_rows if e["stage"]=="thermal")
                logs=lines(p/"events.jsonl.gz")
                repair_n=sum(e["kind"]=="dp" and e["reserve"]==13 for e in logs)
                restores=sum(r["ordinary"] is not None and r["ordinary"]["status"]=="SAFE" for r in completed if r["hot_only"])
                recovered=sum(r["best"] is not None for r in completed if r["hot_only"])
                flips=sum(r["ordinary"] and r["ordinary"]["status"]=="SAFE" and r["thermal"] is not None and r["thermal"]["status"]=="HOT" or False for r in completed)
                result_row=dict(**sig,limit=rc["limit_s"],wall_s=charged,status=rc["status"],nominated=len(noms[arm]),started=len(starts),
                    completed=len(completed),hot_completed=sum(r["hot_only"] for r in completed),recover_ordinary=restores,
                    recover_final=recovered,safe_to_hot=flips,reserve_calls=repair_n,
                    P=rp["J"],P_plan=rp["plan"],P_delivered_s=completed[0]["t"],historical_cut_s=60,
                    M6a_J=float(hist["J"]),M6a_same=rp["plan"]==hist["plan"],
                    original_best=historical["J"],ordinary_raw_min=flat(raword).get("J"),thermal_raw_min=flat(rawheat).get("J"),
                    ordinary_incumbent=ordinary["J"],final=result["J"],final_plan=result["plan"],winning_map=kbest,
                    winner_hot_only=local[kbest]["hot_only"],thermal_additional_J=delta(ordinary,result),improvement_over_P=delta(rp,result))
                runs.append(result_row)
                for r in completed:
                    key=r["mapping"];l=local[key];o=r["original"];d=r["ordinary"];t=r["thermal"];final=r["best"]
                    assert o["plan"]==l["representative"] and meta[o["plan"]]["event_array_sha256"]==idx[o["plan"]]["trace_sha256"]
                    if d and d["status"] in ("SAFE","HOT"):assert r["guide"]==d["plan"] and r["fallback"] is None
                    assert (final or {}).get("plan")==((best([o,d,t]) or {}).get("plan"))
                    v=dict(**sig,slot=r["i"],mapping=key,original_first_s=l["first_s"],first_width=l["first_width"],first_rank=l["first_rank"],
                        rep_s=l["rep_s"],rep_width=l["rep_width"],rep_rank=l["rep_rank"],local_safe=l["local_safe"],hot_only=l["hot_only"],
                        shared_other_safe=l["shared_other_safe"],history_low_ref=l["low_ref"],fallback=r["fallback"],guide=r["guide"],
                        **fields("original",o),**fields("ordinary",d),**fields("thermal",t),**fields("best",final))
                    sigkey=(case,key)
                    signature=(flat(d).get("plan"),r["guide"],flat(t).get("plan"))
                    if sigkey in shared_signatures:
                        assert shared_signatures[sigkey]==signature
                        n_verified+=1
                    else:shared_signatures[sigkey]=signature
                    visits.append(v)
                    if l["hot_only"] and final:
                        hotw.append(dict(**v,beats_P=beats(final,rp),safe_then_hot=bool(d and d["status"]=="SAFE" and t and t["status"]=="HOT")))
                    if group=="offline":allpool.append((m,key,r,l))
                stage_map={e["mapping"]:e for e in completed}
                if group=="fair":
                    for history in bymethod:
                        k=history["mapping"];x=stage_map.get(k)
                        original_pairings.append(dict(case=case,source=m,arm=arm,call=history["call"],original_plan=history["plan"],
                            original_cfg=history["cfg"],original_status=history["status"],original_J=history["original_J"],
                            mapping=k,nominated=k in noms[arm],completed=x is not None,ordinary_plan=flat(x["ordinary"]).get("plan") if x else None,
                            thermal_plan=flat(x["thermal"]).get("plan") if x else None,final_plan=flat(x["best"]).get("plan") if x else None,
                            final_J=flat(x["best"]).get("J") if x else None))
                if group=="offline":
                    for row in bymethod:
                        k=row["mapping"];r=stage_map.get(k)
                        rawjoins.append(dict(case=case,source=m,call=row["call"],width=row["width"],rank=row["beam_rank"],time=row["first_s"],
                            historical_plan=row["plan"],historical_cfg=row["cfg"],mapping=k,historical_status=row["status"],historical_J=row["original_J"],
                            completed=r is not None,best_J=flat(r["best"]).get("J") if r else None,best_plan=flat(r["best"]).get("plan") if r else None))
    resc=read(ARCH/"gate/receipt.json");budget.append(dict(stage="gate",case="",source="",arm="",**resc))
    out("budget.csv",budget);out("inventory.csv",case_rows);out("cells.csv",runs);out("map_stages.csv",visits);out("energy_stages.csv",stages_detail)
    with gzip.open(A/"all_mapping_statuses.jsonl.gz","wt") as f:
        for row in all_mapping_classes:f.write(json.dumps(row,separators=(",",":"))+"\n")
    out("c10_call_pairs.csv",rawjoins)
    pairs=[];source_effects=[]
    for case in sorted({r["case"] for r in case_rows}):
        line={"case":case}
        for m,short in zip(METHODS,("nt","zhou")):
            p,so,s=endpoints[case,m,"S"];p2,ho,h=endpoints[case,m,"H"]
            assert p["plan"]==p2["plan"]
            local=pools[case,m]; nh=sum(r["hot_only"] for r in local.values())
            source_effects.append(dict(case=case,source=m,has_hot=bool(nh),hot_only=nh,P_J=p["J"],S_J=s["J"],H_J=h["J"],
                 S_gain_J=delta(p,s),S_gain_pct=100*delta(p,s)/p["J"],H_gain_J=delta(s,h),H_gain_pct=100*delta(s,h)/s["J"],
                 S_vs_P=sign(s,p),H_vs_S=sign(h,s),S_thermal_gain_J=delta(so,s),H_thermal_gain_J=delta(ho,h)))
            for tag,pt in (("P",p),("S",s),("H",h)):line[short+"_"+tag]=pt["J"]
            line[short+"_hot_only"]=nh
        for tag in ("P","S","H"):
            left=endpoints[case,"NT","S"][0] if tag=="P" else endpoints[case,"NT",tag][-1]
            right=endpoints[case,"ZQ-Beam","S"][0] if tag=="P" else endpoints[case,"ZQ-Beam",tag][-1]
            line[tag+"_nt_minus_zhou"]=left["J"]-right["J"];line[tag+"_nt_vs_zhou"]=sign(left,right)
            line[tag+"_nt_saving_pct"]=100*delta(right,left)/right["J"]
        pairs.append(line)
    for w in hotw:
        peer=endpoints[w["case"],w["source"],"S"][-1]
        w["beats_equal_budget_safe"]=w["best_hi"]<peer["bounds"][0]
    out("hot_witnesses.csv",hotw);out("pairs.csv",pairs);out("effects.csv",source_effects)
    with gzip.open(A/"historical_pair_results.csv.gz","wt",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(original_pairings[0]),lineterminator="\n");w.writeheader();w.writerows(original_pairings)
    ranks=[];quality=[]
    bestall={m:best(v["best"] for src,_,v,_ in allpool if src==m) for m in METHODS}
    zhou_original=best(v["original"] for src,_,v,_ in allpool if src=="ZQ-Beam")
    for m in METHODS:
        subset=[x for x in allpool if x[0]==m]
        order=sorted(subset,key=lambda x:(x[3]["original_best_J"],x[1]))
        originalrank={x[1]:i for i,x in enumerate(order,1)}
        saferank={x[1]:i for i,x in enumerate(sorted((x for x in subset if x[3]["local_safe"]),key=lambda x:(x[3]["rep_J"],x[1])),1)}
        ordref={x[1]:i for i,x in enumerate(sorted(subset,key=lambda x:(x[3]["low_ref"],x[3]["ref_cfg"],x[1])),1)}
        after=sorted((x for x in subset if x[2]["best"]),key=lambda x:(x[2]["best"]["J"],x[1]))
        finalrank={x[1]:i for i,x in enumerate(after,1)}
        own=endpoints["C10",m,"S"][0];zhou=endpoints["C10","ZQ-Beam","S"][0]
        for _,key,v,l in subset:
            ranks.append(dict(source=m,mapping=key,original_energy_rank=originalrank[key],original_SAFE_rank=saferank.get(key),reference_rank=ordref[key],
                after_SAFE_rank=finalrank.get(key),first_width=l["first_any_width"],first_s=l["first_any_s"],first_beam_rank=l["first_any_rank"],
                first_status=l["first_any_status"],first_in_domain_s=l["first_s"],origin=l["rep_status"],
                rep_plan=l["representative"],rep_J=l["rep_J"],low_ref=l["low_ref"],ordinary_status=flat(v["ordinary"]).get("status"),ordinary_J=flat(v["ordinary"]).get("J"),
                thermal_status=flat(v["thermal"]).get("status"),thermal_J=flat(v["thermal"]).get("J"),final_J=flat(v["best"]).get("J"),final_plan=flat(v["best"]).get("plan"),
                beats_own_P=beats(v["best"],own),beats_Zhou_P=beats(v["best"],zhou),beats_Zhou_full=beats(v["best"],bestall["ZQ-Beam"])))
        for category,group in (("safe", [x for x in subset if x[3]["local_safe"]]),("all",subset),("hot_only",[x for x in subset if x[3]["hot_only"]])):
            bestsafe=best(x[2]["best"] for x in group)
            quality.append(dict(source=m,category=category,n=len(group),recovered=sum(x[2]["best"] is not None for x in group),
                best_ord_raw=flat(best(x[2]["ordinary"] for x in group)).get("J"),best_thermal_raw=flat(best(x[2]["thermal"] for x in group)).get("J"),
                best_ord_inc=flat(best(x[2]["ordinary_best"] for x in group)).get("J"),best_final=flat(bestsafe).get("J"),best_plan=flat(bestsafe).get("plan"),
                beats_native_Zhou=sum(beats(x[2]["best"],zhou_original) for x in group),native_Zhou_J=zhou_original["J"],
                beats_own_P=sum(beats(x[2]["best"],own) for x in group),beats_Zhou_P=sum(beats(x[2]["best"],zhou) for x in group),
                beats_Zhou_full=sum(beats(x[2]["best"],bestall["ZQ-Beam"]) for x in group)))
    out("c10_mapping_ranks.csv",ranks);out("c10_quality.csv",quality)
    costs={stage:sum(r["wall_s"] for r in budget if r["stage"]==stage) for stage in ("gate","offline","fair")}
    assert costs["gate"]<=300 and costs["offline"]<=1200 and costs["fair"]<=5760 and len(runs)==50
    save(A/"verification.json",dict(unique_physical=len(idx),sources=len(case_rows),cells=len(runs),visits=len(visits),calls=sum(r["ontime_calls"] for r in case_rows),
        completed_all=all(r["nominated"]==r["completed"] for r in runs if r["group"]=="offline"),budgets=costs,reported_stages=len(stages_detail),shared_matches=n_verified,
        replay_M6a_matches=sum(r["M6a_same"] for r in runs if r["arm"]=="S"),old_run="85969e8ed78cbab4d693122819ebe866e0721bb7"))
    print(read(A/"verification.json"))
if __name__=="__main__":main()
