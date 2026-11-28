"""Read-only classification of failures, first complete schedules, nominations and deliveries."""
import csv,gzip,json,tarfile,zlib
from collections import Counter,defaultdict
from summary import OUT,stats,cases,indexed,key,load_log

def first_time(rows):return min((float(r["t"]) for r in rows),default=None)

def explain_failure(cell,search,layers,windows,issued):
    if cell["safe"]=="1":return "delivered_SAFE"
    if cell["stop"] in ("cpu_guard","fault"):return cell["stop"]
    closed=[e for e in search if e["event"]=="end" and e.get("task")=="construct"]
    positive=[e for e in closed if e["terminals"]]
    starts=sum(e["event"]=="begin" and e.get("task")=="search_cert" for e in search)
    complete=len(issued)
    if not positive:
        empty=any(e["complete"] and e["valid"]==0 for e in layers)
        if empty and closed:return "no_legal_pool_on_explored_beam"
        return "construction_incomplete"
    if starts>complete:return "certification_cutoff"
    # Only claim that *every* returned candidate was HOT when a complete single
    # terminal pool was exhausted. In all other cases keep the untested remainder explicit.
    if complete and all(e["status"]=="HOT" for e in issued):
        if len(positive)==1 and len({r["plan"] for r in issued})==positive[0]["terminals"]:
            return "all_returned_terminals_certified_HOT"
        return "tested_HOT_other_terminals_unresolved"
    if not complete:return "terminal_ready_no_certificate_delivered"
    return "no_SAFE_other_status"

def track():
    cells=stats.csvrows("cells")
    cert=indexed(stats.csvrows("certificates"));curves=indexed(stats.csvrows("improvements"))
    targets=indexed(stats.csvrows("quality_targets"));maps=indexed(stats.csvrows("maps"))
    windows={c:json.loads((OUT/"inputs"/(c+".json")).read_bytes())["windows"] for c in cases()}
    timing=[];failures=[];map_work=[];pools=[];sources={}
    for cell in cells:
        k=key(cell);ident={n:cell[n] for n in ("case","cap","arm","rep")}
        cap=int(cell["cap"]);split=cap-(5 if cap==60 else 3)
        cut=split if cell["first_s"] and float(cell["first_s"])<split else cap
        sc=[e for e in load_log(cell,"search.jsonl") if e["t"]<=cut]
        rf=[e for e in load_log(cell,"refine.jsonl") if e["t"]<=cap]
        layers=load_log(cell,"layers.jsonl")
        ledger=[e for e in load_log(cell,"ledger.jsonl") if e["t"]<=cut]
        issued=[e for e in cert[k] if e["stage"]=="search/physical"]
        certified_safe=[e for e in issued if e["status"]=="SAFE"]
        seeds=maps[k];nm={e["mapping"] for e in seeds}
        started={e["rank"] for e in rf if e["event"]=="map_start"}
        done={int(e["rank"]) for e in seeds if e["finished"]=="1"}
        tuning=[e for e in rf if e["event"]=="begin" and e.get("task")=="refinement"]
        ranked={e["plan"]:e for e in issued}
        improved=[r for r in curves[k] if r["stage"].endswith("/direct")]
        full=[e for e in sc if e.get("task")=="construct" and e["event"]=="end" and e["terminals"]>0]
        beg=None
        for e in sc:
            if e.get("task")!="construct":continue
            if e["event"]=="begin":beg=e
            elif e["event"]=="end" and beg is not None:
                pools.append(dict(**ident,width=e["width"],start_s=beg["t"],end_s=e["t"],elapsed_s=e["t"]-beg["t"],terminals=e["terminals"]))
                beg=None
        if beg:pools.append(dict(**ident,width=beg["width"],start_s=beg["t"],end_s=None,elapsed_s=None,terminals=None))
        cause=explain_failure(cell,sc,layers,windows[cell["case"]],issued)
        fail=dict(**ident,reason=cause,stop=cell["stop"],windows=windows[cell["case"]],
                  deepest_completed_layer=max((e["j"]+1 for e in layers if e["complete"]),default=0),
                  deepest_logged_layer=max((e["j"]+1 for e in layers),default=0),
                  completed_empty_layer=any(e["complete"] and e["valid"]==0 for e in layers),
                  received_terminal_pools=len(full),first_terminal_pool_size=full[0]["terminals"] if full else None,
                  search_cert_started=sum(e.get("task")=="search_cert" and e["event"]=="begin" for e in sc),
                  search_cert_delivered=len(issued),tested_HOT=sum(r["status"]=="HOT" for r in issued),
                  last_search_event=sc[-1]["event"] if sc else None,last_search_task=sc[-1].get("task") if sc else None)
        fail["open_construct_at_cut"]=beg is not None
        fail["open_cert_at_cut"]=fail["search_cert_started"]>len(issued)
        fail["all_observed_certificates_HOT"]=bool(issued) and all(r["status"]=="HOT" for r in issued)
        certified_ids={e["candidate"] for e in sc if e["event"]=="certificate"}
        fail["distinct_certified_candidates"]=len(certified_ids)
        fail["unverified_in_only_returned_pool"]=full[0]["terminals"]-len(certified_ids) if len(full)==1 else None
        if cause!="delivered_SAFE":failures.append(fail)
        postlocal=[]
        for e in seeds:
            rank=int(e["rank"])
            ev=[x for x in rf if x.get("rank")==rank]
            dp=load_log(cell,f"map{rank}/events.jsonl")
            dp=[x for x in dp if x["kind"]=="dp" and x["t"]<=cap]
            stage=f"map{rank}/direct";ps=[r for r in cert[k] if r["stage"]==stage]
            seed=ranked[e["seed"]]
            better=[p for p in ps if p["status"]=="SAFE" and (seed["status"]!="SAFE" or float(p["hi"])<float(seed["lo"]))]
            postlocal.extend(better)
            map_work.append(dict(**ident,rank=rank,seed=e["seed"],mapping=e["mapping"],seed_status=seed["status"],seed_J=seed["J"],
                nomination_complete_s=first_time(x for x in rf if x.get("task")=="selection" and x["event"]=="end"),
                map_start_s=first_time(x for x in ev if x["event"]=="map_start"),
                direct_start_s=first_time(x for x in ev if x.get("task")=="refinement" and x["event"]=="begin"),
                dp_first_return_s=first_time(dp),dp_returns=len(dp),first_cert_s=first_time(ps),first_local_improvement_s=first_time(better),
                direct_end_s=first_time(x for x in ev if x["event"]=="stage_end"),finished=int(rank in done),
                nominated_unstarted=int(rank not in started),started_unfinished=int(rank in started and rank not in done),recovered=e["recovered"]))
        point=issued[0] if issued else {};tars={r["tolerance"]:r for r in targets[k]}
        best=min(certified_safe,key=lambda r:float(r["hi"]),default={})
        row=dict(**ident,stop=cause,split_s=split,first_full_mapping_attempt_s=first_time(e for e in ledger if e["event"]=="full_mapping"),
            first_completed_terminal_pool_s=first_time(full),first_pool_size=full[0]["terminals"] if full else None,
            first_search_cert_s=point.get("t"),first_search_plan=point.get("plan"),first_search_mapping=point.get("mapping"),
            first_search_status=point.get("status"),first_search_J=point.get("J"),first_safe_s=cell["first_s"],
            best_search_J=best.get("J"),best_search_plan=best.get("plan"),best_search_mapping=best.get("mapping"),
            selection_start_s=first_time(e for e in rf if e.get("task")=="selection" and e["event"]=="begin"),
            direct_start_s=first_time(tuning),first_direct_local_improvement_s=first_time(postlocal),first_direct_global_improvement_s=first_time(improved),
            last_improvement_s=cell["last_s"],final_J=cell["J"],exact_hit_s=tars["0"]["first_hit_s"],relaxed_hit_s=tars["0.01"]["first_hit_s"],
            generated=cell["generated"],evaluated=cell["evaluated"],legal=cell["legal"],construct_s=cell["construct_s"],
            evaluated_per_construct_s=int(cell["evaluated"])/float(cell["construct_s"]) if float(cell["construct_s"]) else None,
            nominated=len(seeds),started=len(started),finished=len(done),started_unfinished=len(started-done),
            nominated_unstarted=len(seeds)-len(started),unreturned_direct=sum(e["rank"] not in done for e in tuning),
            search_certificates=len(issued),last_layer=fail["deepest_completed_layer"])
        timing.append(row); sources[k]=(point,nm,{r["mapping"] for r in issued})
    stats.put("stage_timing",timing);stats.put("map_timing",map_work);stats.put("failures",failures);stats.put("construction_passes",pools)
    paired_paths(sources,timing)
    phase_summary=[]
    for case in [*cases(),"all"]:
        for cap in ("10","20","60"):
            for arm in ("A","B") if cap!="60" else ("A",):
                rs=[r for r in timing if case in (r["case"],"all") and r["cap"]==cap and r["arm"]==arm]
                pre=[r for r in rs if r["first_safe_s"] and float(r["first_safe_s"])<r["split_s"]]
                dps=[r for r in rs if r["direct_start_s"] is not None]
                phase_summary.append(dict(case=case,cap=cap,arm=arm,runs=len(rs),safe_before_split=len(pre),
                    direct_started_runs=len(dps),direct_improved_runs=sum(r["first_direct_global_improvement_s"] is not None for r in rs),
                    median_first_terminal_s=stats.med(r["first_completed_terminal_pool_s"] for r in rs),
                    median_tune_start_s=stats.med(r["direct_start_s"] for r in rs),
                    median_available_after_tune_start_s=stats.med(float(cap)-r["direct_start_s"] for r in dps),
                    median_first_safe_to_selection_s=stats.med(r["selection_start_s"]-float(r["first_safe_s"]) for r in pre if r["selection_start_s"] is not None),
                    median_first_tune_improvement_s=stats.med(r["first_direct_global_improvement_s"] for r in rs),
                    median_best_search_J=stats.med(r["best_search_J"] for r in rs),
                    median_final_J=stats.med(r["final_J"] for r in rs),
                    nominated=sum(r["nominated"] for r in rs),started=sum(r["started"] for r in rs),finished=sum(r["finished"] for r in rs),
                    unfinished_map_runs=sum(r["started_unfinished"]>0 for r in rs),
                    nominated_unstarted=sum(r["nominated_unstarted"] for r in rs),
                    evaluated_per_construct_s=sum(int(r["evaluated"]) for r in rs)/sum(float(r["construct_s"]) for r in rs)))
    stats.put("phase_summary",phase_summary)
    # Stronger than matching device assignment: the complete certified input
    # schedule to the deterministic direct optimizer must be byte-identical.
    completed_seed_outputs=defaultdict(list)
    for m in map_work:
        if not m["finished"]:continue
        for c in cert[key(m)]:
            if c["stage"]==f"map{m['rank']}/direct" and c["status"]=="SAFE":
                completed_seed_outputs[(m["case"],m["seed"])].append((m,c))
    witnesses=[]
    for m in map_work:
        if m["finished"] or m["cap"]=="60":continue
        for goal in targets[key(m)]:
            if goal["status"]!="above_target":continue
            eligible=[(other,r) for other,r in completed_seed_outputs[(m["case"],m["seed"])]
                      if key(other)!=key(m) and float(r["hi"])<=float(goal["target_hi_J"])]
            if not eligible:continue
            other,r=min(eligible,key=lambda a:(float(a[1]["hi"]),key(a[0])))
            witnesses.append(dict(case=m["case"],arm=m["arm"],cap=m["cap"],rep=m["rep"],rank=m["rank"],
                seed=m["seed"],mapping=m["mapping"],tolerance=goal["tolerance"],target_hi_J=goal["target_hi_J"],
                map_started=m["map_start_s"] is not None,direct_started=m["direct_start_s"] is not None,
                reference_arm=other["arm"],reference_cap=other["cap"],reference_rep=other["rep"],reference_rank=other["rank"],
                reference_plan=r["plan"],reference_hi_J=r["hi"],reference_delivery_s=r["t"]))
    with (OUT/"unfinished_seed_witnesses.csv").open("w",encoding="utf8",newline="") as f:
        columns="case arm cap rep rank seed mapping tolerance target_hi_J map_started direct_started reference_arm reference_cap reference_rep reference_rank reference_plan reference_hi_J reference_delivery_s".split()
        writer=csv.DictWriter(f,columns,lineterminator="\n");writer.writeheader();writer.writerows(witnesses)
    counts=Counter((r["cap"],r["arm"],r["reason"]) for r in failures)
    stats.put("failure_summary",[dict(cap=k[0],arm=k[1],reason=k[2],runs=v) for k,v in sorted(counts.items())])

def paired_paths(sources,timing):
    out=[]
    for case in cases():
        with gzip.open(OUT/"inputs"/(case+".csv.gz"),"rt",newline="") as f:req=list(csv.DictReader(f))
        w=[int(r["release_tick"])//10000+1 for r in req]
        keys={r["first_search_plan"] for r in timing if r["case"]==case and r["first_search_plan"]}
        configs={}
        for part in (OUT/"physical"/case).glob("*.tar"):
            with tarfile.open(part,"r|") as t:
                for member in t:
                    key,tag=member.name.split("/")
                    if tag=="plan" and key in keys:
                        rows=json.loads(zlib.decompress(t.extractfile(member).read()))["rows"][1::3]
                        configs[key]=[tuple(r[:2]) for r in rows]
                        assert len(rows)==len(w)
        for cap in ("10","20"):
            for rep in ("1","2","3"):
                a,ma,ca=sources[(case,cap,rep,"A")]
                b,mb,cb=sources[(case,cap,rep,"B")]
                row=dict(case=case,cap=cap,rep=rep,A_first_plan=a.get("plan"),B_first_plan=b.get("plan"),
                    A_first_mapping=a.get("mapping"),B_first_mapping=b.get("mapping"),A_certified_maps=len(ca),B_certified_maps=len(cb),
                    shared_certified_maps=len(ca&cb),A_nominated=len(ma),B_nominated=len(mb),shared_nominations=len(ma&mb))
                if a and b:
                    x,y=configs[a["plan"]],configs[b["plan"]]
                    def quota(cfg):
                        return Counter((j,r["kind"],action[0]) for j,r,action in zip(w,req,cfg))
                    q1,q2=quota(x),quota(y);diff={k[0] for k in q1.keys()|q2.keys() if q1[k]!=q2[k]}
                    row.update(first_action_diff_window=next((j for j,p,q in zip(w,x,y) if p!=q),None),
                        first_device_diff_window=next((j for j,p,q in zip(w,x,y) if p[0]!=q[0]),None),
                        first_type_quota_diff_window=min(diff,default=None),type_quota_different_windows=len(diff),
                        different_device_requests=sum(p[0]!=q[0] for p,q in zip(x,y)),different_actions=sum(p!=q for p,q in zip(x,y)))
                out.append(row)
    stats.put("path_pairs",out)

if __name__=="__main__":track()
