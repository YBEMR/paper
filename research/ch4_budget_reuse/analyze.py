"""Rebuild the tables from sealed archives and apply only the frozen engineering gates."""
from collections import Counter
from hashlib import sha256
import json
from statistics import median

from audit import CFG,HERE,ROOT,analyze_one,content,events,make_domain,project,ref_table,require,write_csv

def comparison(arm,base,rows,at):
    v=[r for r in rows if r["arm"]==arm and r["role"]=="main"]
    pairs=[];cases=[]
    for a in v:
        b=next(r for r in rows if r["role"]=="main" and r["arm"]==base and
               (r["load"],r["temp"],r["seed"])==(a["load"],a["temp"],a["seed"]))
        x,y=at[a["slot"],20],at[b["slot"],20]
        ratio=a["near_s"]/b["near_s"] if a["near_s"] is not None and b["near_s"] is not None else None
        pairs.append(dict(test=arm,baseline=base,load=a["load"],temp=a["temp"],seed=a["seed"],
                target_ratio=ratio,t_test=a["near_s"],t_base=b["near_s"],
                safe20_test=x["safe"],safe20_base=y["safe"],hit20_test=x["target"],hit20_base=y["target"],
                j20_test=x["energy_j"],j20_base=y["energy_j"],safe116_test=a["safe"],safe116_base=b["safe"],
                final_test=a["best_j"],final_base=b["best_j"],
                final_protected=(not b["safe"] or (a["safe"] and a["best_j"]<=b["best_j"]+1e-7))))
    for l,t in CFG["cases"]:
        subset=[r for r in pairs if r["load"]==l and r["temp"]==t]
        ratios=[r["target_ratio"] for r in subset if r["target_ratio"] is not None]
        aa=[r["j20_test"] for r in subset if r["j20_test"] is not None]
        bb=[r["j20_base"] for r in subset if r["j20_base"] is not None]
        paired_energy=len(aa)==len(bb)==len(subset)==3
        cases.append(dict(test=arm,baseline=base,load=l,temp=t,n=len(subset),ratio_pairs=len(ratios),
            case_median_ratio=median(ratios) if len(ratios)==3 else None,
            hit20_test=sum(r["hit20_test"] for r in subset),hit20_base=sum(r["hit20_base"] for r in subset),
            all_three_better20=paired_energy and all(r["j20_test"]<r["j20_base"]-1e-7 for r in subset),
            delta20_median_j=median(aa)-median(bb) if paired_energy else None,
            median20_nonworse=paired_energy and median(aa)<=median(bb)+1e-7))
    ratios=[r["target_ratio"] for r in pairs if r["target_ratio"] is not None]
    all_hit=len(ratios)==9
    guard=(sum(r["hit20_test"] for r in pairs)>=sum(r["hit20_base"] for r in pairs) and
           sum(r["safe116_test"] for r in pairs)>=sum(r["safe116_base"] for r in pairs) and
           all(r["final_protected"] for r in pairs))
    time=bool(guard and all_hit and median(ratios)<=.9 and all(c["case_median_ratio"]<=1.1 for c in cases))
    quality=bool(guard and any(c["all_three_better20"] for c in cases) and all(c["median20_nonworse"] for c in cases))
    return pairs,cases,dict(test=arm,baseline=base,n=len(pairs),joint_hits=len(ratios),
          median_ratio=median(ratios) if all_hit else None,protected=bool(guard),time_pass=time,
          quality_pass=quality,adopt=time or quality)

def main():
    manifest=json.loads((HERE/"archives/manifest.json").read_bytes())
    gate=json.loads((HERE/"archives/trace_gate.json").read_bytes())
    arms="ABC" if gate["C_enabled"] else "AB"
    require(len(manifest)==len(arms)*9+2,"Incomplete reservations")
    domain=make_domain(ROOT)
    rows=[];cps=[];improvements=[];costs=[];prefix={};audit=[];fixed_rows=[];amort=[]
    references=ref_table()
    caches=[];identities=[]
    for slot,meta in manifest.items():
        require(sha256((HERE/"archives"/(slot+".tar")).read_bytes()).hexdigest()==meta["sha256"],"Archive "+slot)
        files,receipt=content(slot)
        rr,ii,cc,co=analyze_one(slot,files,receipt,domain,references)
        rows.append(rr);improvements.extend(ii);cps.extend(cc);costs.extend(co)
        result=json.loads(files["result.json"])
        for cache,stats in result["lru"].items():
            caches.append(dict(slot=slot,cache=cache,**stats))
        cnt=result["meter"][1]
        caches.append(dict(slot=slot,cache="M2",maxsize=CFG["kernel_entries"] if rr["arm"]!="A" else 0,
            legal_hits=cnt.get("legal_kernel_hits",0),reject_hits=cnt.get("deadline_reject_hits",0),
            builds=cnt.get("kernel_builds",0),queries=cnt.get("kernel_queries",0),
            fallback=cnt.get("peak_fallback_calls",0),peak_completion=cnt.get("peak_certificate_completion_calls",0),
            anchor_reuses=cnt.get("exact_anchor_queries",0),proxy_anchor=cnt.get("proxy_exact_anchor_reuses",0),
            evictions=cnt.get("cache_evictions",0),peak_entries=result["peak_cache_entries"],
            peak_array_bytes=result["peak_cache_array_bytes"],peak_process_rss_bytes=result["peak_rss_bytes"]))
        pin=json.loads((HERE/"identity.json").read_bytes())
        reservation=json.loads(files["reservation.json"])
        baseline_config=json.loads((ROOT/"research/ch3_energy_repair/config.json").read_bytes())
        identities.append(dict(slot=slot,freeze=receipt["freeze"],base=CFG["base"],core=reservation["core"],
                concurrency=reservation["concurrent"],cap_s=120,search_accept_s=116 if rr["role"]=="main" else None,
                request_sha256=rr["request_sha256"],source_manifest_sha256=reservation["source_hash"],
                catalog_sha256=pin["research/ch3_cooperative_cuts/catalog_manifest.json"],
                platform_sha256=pin["research/kim_synthetic_platform_v1/platform.json"],
                energy_only_sha256=pin["research/ch3_energy_repair/optimizer.py"],domain_size=4319803,
                physical_labels=True,kernel_LRU=128 if rr["arm"]!="A" else 0,
                proposals=baseline_config["proposals"] if rr["role"]=="main" else None,
                additional_SetFreq=rr["role"]=="main",hot_period=baseline_config["hot_period"] if rr["role"]=="main" else None))
        prefix[slot]=project(files)
        require(rr["flow_calls"]==len(prefix[slot][0]),"Flow count")
        if rr["role"]=="fixed":
            for seq,kind,params,src_end,ended,ok in events(files["comparison.jsonl.gz"]):
                fixed_rows.append(dict(arm=rr["arm"],seq=seq,kind=kind,args=params,source_end_s=src_end,
                                       returned_s=ended,all_fields_equal=int(ok)))
    physics_keys={r["freeze"] for r in rows}
    require(len(physics_keys)==1,"Mixed execution versions")
    at={(r["slot"],r["wall_s"]):r for r in cps}
    pairs=[];cases=[];decisions=[]
    for arm,base in ([("B","A"),("C","B"),("C","A")] if gate["C_enabled"] else [("B","A")]):
        pp,cc,dd=comparison(arm,base,rows,at)
        pairs+=pp;cases+=cc;decisions.append(dd)
    main={r["slot"]:r for r in rows if r["role"]=="main"}
    for slot,row in main.items():
        if row["arm"]!="A": continue
        other=slot[:-1]+"B"
        ak,ac,ae,_,types=prefix[slot]
        bk,bc,be,_,_=prefix[other]
        n=min(len(ak),len(bk))
        require(ak[:n]==bk[:n],"A/B search evaluator order or physical values drift: "+slot)
        audit.append(dict(slot=slot,comparison=other,common_calls=n,a_calls=len(ak),b_calls=len(bk),
                          all_common_call_parameters_and_answers_equal=True))
        for i,phase in [(n,"common_search_prefix"),
                      (sum(t<=row["near_s"] for t in ae[:n]) if row["near_s"] is not None else n,"through_A_target")]:
            amort.append(dict(source=slot,phase=phase,calls=i,original_top_eval_s=sum(ac[:i]),
                         m2_top_eval_s=sum(bc[:i]),original_last_end_s=ae[i-1] if i else None,
                         m2_last_end_s=be[i-1] if i else None))
    if gate["C_enabled"]:
        for slot,r in main.items():
            if r["arm"]!="C": continue
            other=slot[:-1]+"B"
            a,b=prefix[slot][0],prefix[other][0]
            n=min(len(a),len(b))
            i=next((i for i in range(n) if a[i]!=b[i]),n)
            audit.append(dict(slot=slot,comparison=other,common_calls=i,a_calls=len(a),b_calls=len(b),
                              all_common_call_parameters_and_answers_equal=i==n))
            if not r["changed_fills"]:
                require(i==n,"C changed the evaluator stream without a changed allocation: "+slot)
    first="original_30_20261121_A"
    a=prefix[first+"_trace"];b=prefix[first[:-1]+"B_trace"];source=prefix[first]
    n=gate["expected"]
    require(a[0]==b[0]==source[0][:n] and n==sum(t<=20 for t in source[2]),"Fixed flow differs")
    firstfull=next(i for i,k in enumerate(a[4]) if k=="full")
    cumulative=0;last_negative=None
    for i,(aa,bb) in enumerate(zip(a[1],b[1])):
        cumulative+=aa-bb
        if i>=firstfull and cumulative<0: last_negative=i
    breakeven=firstfull if last_negative is None else last_negative+1
    for phase,i in [("fixed_all",n),("fixed_through_A_target",sum(t<=main[first]["near_s"] for t in source[2][:n])
                          if main[first]["near_s"] is not None else n)]:
        amort.append(dict(source=first,phase=phase,calls=i,original_top_eval_s=sum(a[1][:i]),
                         m2_top_eval_s=sum(b[1][:i]),original_last_end_s=a[2][i-1],m2_last_end_s=b[2][i-1],
                         sustained_break_even_call_in_full_prefix=breakeven if breakeven<n else None))
    fixed_work=[]
    for arm,tr in zip("AB",(a,b)):
        for kind in ("proxy","deadline","full"):
            indices=[i for i,k in enumerate(tr[4]) if k==kind]
            fixed_work.append(dict(arm=arm,kind=kind,completed=len(indices),
                evaluator_call_s=sum(tr[1][i] for i in indices),
                through_A_target_calls=sum(source[2][i]<=main[first]["near_s"] for i in indices)
                    if main[first]["near_s"] is not None else None))
    summaries=[]
    for l,t in CFG["cases"]:
        for arm in arms:
            subset=[r for r in main.values() if (r["load"],r["temp"],r["arm"])==(l,t,arm)]
            near=[r["near_s"] for r in subset if r["near_s"] is not None]
            summaries.append(dict(load=l,temp=t,arm=arm,n=len(subset),safe=sum(r["safe"] for r in subset),
                    target_hits=len(near),target_median_if_all_s=median(near) if len(near)==3 else None,
                    first_safe_median_if_all_s=median(r["first_safe_s"] for r in subset) if all(r["safe"] for r in subset) else None,
                    exact_hits=sum(r["exact_s"] is not None for r in subset),**{
                        f"target_by_{time}s":sum(at[r["slot"],time]["target"] for r in subset) for time in (5,10,20,116)}))
    for name,table in [("runs",rows),("case_summary",summaries),("improvements",improvements),
                       ("checkpoints",cps),("exclusive_costs",costs),("adoption",decisions),
                       ("paired",pairs),("case_gates",cases),("fixed_agreement",fixed_rows),("fixed_work",fixed_work),
                       ("amortization",amort),("matched_flow_check",audit),("cache_stats",caches),("actual_run_config",identities)]:
        write_csv(name,table)
    print(len(main),"main;",n,"fixed calls per evaluator;",decisions)

if __name__=="__main__": main()
