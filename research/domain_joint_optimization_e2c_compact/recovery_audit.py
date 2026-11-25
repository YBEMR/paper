"""Audit every completed timed result and separately certify the two saved interrupted hints."""
import csv,gzip,json,time,subprocess,sys
from datetime import datetime,timezone
from c1r_assets import ROOT,C,read,write,digest
from bounded import options,graph,propagate,legal_assignment,CompactModel,proxy
from support import SupportModel
from base import Problem,decode,Layout,Access,dynamic_region,changes,raw,obj,evaluate,np,table
from numerics import rights_check
from compact import permissions
from audit import thermal
import review

def rows(name):
    with (ROOT/name).open(encoding="utf8",newline="") as f:return list(csv.DictReader(f))

def audit():
    st=read(ROOT/"execution.json");assert st["status"] in ("AWAITING_AUDIT","AUDIT_STOP") and len(st["groups"])==22
    all_cases=read(ROOT/"samples.json")["cases"]
    no_terminal={st["incident"]}
    no_new={g["sample"] for g in st["groups"] if g.get("hard_stop")}
    completed=[v for v in all_cases if v["id"] not in no_terminal|no_new]
    for v in completed:
        for var in ("Full-Hint","Compact-Hint"):
            r=read(ROOT/"runs"/v["id"]/var/"arm.json");assert r["status"] in ("COMPLETE","TIME_LIMIT") and r["auxiliary"]["solves"]
    review.assess(completed)
    for s in all_cases:
        if s["id"] in no_terminal|no_new:inspect_saved(st,s,s["id"] in no_new)
    gate=read(ROOT/"gate.json");gate.update(planned_pairs=11,complete_pairs=11-len(no_terminal),d3_complete_pairs=9-len(no_terminal),
        d3_unresolved=len(no_terminal),interrupted=st["incident"],budget_only=sorted(no_new),ranked_interrupted=False,additional_search_calls=0)
    gate["d3_pairs"]["overlap"]=gate["d3_pairs"].get("overlap",0)+len(no_new);write(ROOT/"gate.json",gate)

def inspect_saved(st,s,exhausted):
    case=s["id"];folder=ROOT/"incident";diag=folder/("offline_hint_"+case);diag.mkdir(exist_ok=True);p=Problem(s["case"])
    base=decode(json.loads(gzip.decompress((C/"prestates"/(s["source"]+".json.gz")).read_bytes())))
    bufs=[gzip.decompress((ROOT/"runs"/case/group/"hint.json.gz").read_bytes()) for group in ("Full-Hint","Compact-Hint")]
    assert bufs[0]==bufs[1]
    hint=json.loads(bufs[0]);h=list(map(tuple,hint["rows"]));cfg=hint["config"];support=[i for i,v in enumerate(hint["z"]) if v]
    assert cfg==[i for i in range(p.n) if base[0][i][:2]!=h[i][:2]]
    assert support==[i for i in range(p.n) if base[0][i]!=h[i]] and proxy(p,base[0],h)==hint["proxy_gain_uJ"]
    historical=read(C/"replays"/case/"New"/"arm.json");ids=historical["auxiliary"]["config_candidates"]
    lv=options(p,base[0],ids);edges=graph(p,base[0],lv);early,late=propagate(p,base[0],lv,edges)
    assert legal_assignment(p,base[0],h,ids,lv,edges)
    f=SupportModel(p,base[0],ids);k=CompactModel(p,base[0],ids,lv,edges,early,late)
    rights=Access(set(cfg),set(support),{},set(),set());region=dynamic_region(p,base,rights.st,rights.sf,1)
    lay=Layout(p,h);fixed,free=permissions(lay,region);mats={};evidence=[]
    for name,low in (("preserve",fixed|{g for g in free if region["prior"].get(lay.flex[g],(False,False))[1]}),
                     ("reference",fixed|{g for g in free if lay.gap_delta(g,35)<0})):
        plan=(h,frozenset(low));rights_check(p,base,plan,rights,region)
        buf=raw(obj(p.case,plan));sha=digest(buf);(diag/(sha+".json.gz")).write_bytes(gzip.compress(buf,mtime=0))
        m=evaluate(p,plan,cert=True,trace=True);ev=np.asarray(m.pop("events"));proof=thermal(p,plan,ev,m,mats)
        np.savez_compressed(diag/(sha+".npz"),events=ev)
        evidence.append(dict(policy=name,sha=sha,metrics=m,proof=proof))
    best=min([s["prior_metrics"],*[e["metrics"] for e in evidence if e["metrics"]["status"]=="SAFE"]],key=lambda m:m["E_bounds"][1])
    metadata=dict(sample=case,hints_identical=True,hint_digest=digest(bufs[0]),hint_cfg=cfg,hint_support=support,proxy_gain_uJ=hint["proxy_gain_uJ"],
        size_source="offline structural reconstruction without solving",full=[len(f.m.proto.variables),len(f.m.proto.constraints),p.n],
        compact=[len(k.m.proto.variables),len(k.m.proto.constraints),len(k.retained)],
        compact_hint_inside=all(-early[i]<=r[2]-base[0][i][2]<=late[i] for i,r in enumerate(h)),offline=evidence,
        offline_only_gain_lower_mJ=max(0,1000*(s["prior_metrics"]["E_bounds"][0]-best["E_bounds"][1])),
        before_aux_solve=True,replayed_arms=0,ranked=False)
    write(diag/"receipt.json",metadata)
    arms=rows("results.csv");pairs=rows("paired.csv");stages=rows("stages.csv")
    for collection in (arms,pairs,stages):
        for r in collection:r.setdefault("observation","TIMED")
    histpair=next(x for x in csv.DictReader((C/"paired.csv").open(encoding="utf8",newline="")) if x["sample"]==case)
    for var,size in (("Full-Hint",metadata["full"]),("Compact-Hint",metadata["compact"])):
        group=next(g for g in st["groups"] if g["sample"]==case and g["method"]==var)
        rec={k:"" for k in arms[0]};rec.update(sample=case,case=s["case"],seed=s["seed"],variant=var,source=s["source"],source_J=s["prior_metrics"]["E_J"],
             vars=size[0],constraints=size[1],retained=size[2],tasks=p.n,hint_cfg=len(cfg),hint_support=len(support),hint_gain_uJ=hint["proxy_gain_uJ"],
             aux_status="INTERRUPTED_BEFORE_SOLVE",aux_assignments=0,historical_old_J=histpair["old_J"],historical_new_J=histpair["new_J"],
             observation="INTERRUPTED_SIZE_OFFLINE_NO_RANK")
        if exhausted:
            actual=read(ROOT/"runs"/case/var/"arm.json");aa=actual["auxiliary"]
            assert actual["status"]=="TIME_LIMIT" and not actual["candidates"] and not aa["solves"]
            rec.update(observation="BUDGET_INCUMBENT_SIZE_OFFLINE",aux_status="HINT_CERTIFICATION_DEADLINE_BEFORE_CP",
                region_source=actual["region_source"],fallback=actual["fallback"],final_J=s["prior_metrics"]["E_J"],
                final_lo=s["prior_metrics"]["E_bounds"][0],final_hi=s["prior_metrics"]["E_bounds"][1],final_sha=s["source"],
                hint_gain_lower_mJ=0,cp_extra_lower_mJ=0,core_extra_lower_mJ=0,multi_nonfallback=0,net_lower_mJ=0,
                aux_s=aa["wall_s"],select_s=aa["select_s"],hint_gen_s=aa["hint_gen_s"],arm_s=group["charged_s"])
        arms.append(rec)
        for label in ("hint","cp","core"):
            item={k:"" for k in stages[0]};item.update(sample=case,variant=var,stage=label,observation=rec["observation"])
            if exhausted:item.update(returned_safe=0,cumulative_best=s["source"],cumulative_J=rec["final_J"],lower_J=rec["final_lo"],upper_J=rec["final_hi"],incremental_gain_lower_mJ=0)
            stages.append(item)
    item={k:"" for k in pairs[0]};item.update(sample=case,case=s["case"],source=s["source"],source_J=s["prior_metrics"]["E_J"],
        result="unresolved",shared_hint_sha=metadata["hint_digest"],hint_multi=len(cfg)>=2,retained=len(k.retained),full_vars=metadata["full"][0],
        compact_vars=metadata["compact"][0],observation="INTERRUPTED_NO_RANK")
    if exhausted:item.update(result="overlap",observation="BUDGET_INCUMBENT_SIZE_OFFLINE",full_J=rec["final_J"],compact_J=rec["final_J"],
        full_lo=rec["final_lo"],compact_lo=rec["final_lo"],full_hi=rec["final_hi"],compact_hi=rec["final_hi"],full_sha=s["source"],compact_sha=s["source"],
        advantage_mJ=0,win_lower_mJ=0,loss_lower_mJ=0,full_multi=0,compact_multi=0,multi_beyond_common_hint_and_full=0,compact_cp_or_its_core_witnesses=0,direct_aux_witnesses=0)
    pairs.append(item)
    table(ROOT/"results.csv",arms);table(ROOT/"paired.csv",pairs);table(ROOT/"stages.csv",stages)

if __name__=="__main__":
    if len(sys.argv)>1:audit()
    else:
        st=read(ROOT/"execution.json");t=time.perf_counter()
        logfile=ROOT/"logs"/("review.txt" if st["status"]!="AUDIT_STOP" else "review_with_budget_endpoints.txt")
        with logfile.open("wb") as f:
            q=subprocess.run([sys.executable,"-B",__file__,"audit"],stdout=f,stderr=subprocess.STDOUT,
                timeout=min(200,535-st["ancillary_s"]))
        dt=time.perf_counter()-t;st["phases"][logfile.stem]=dt;st["ancillary_s"]+=dt;st["numerical_s"]+=dt
        st.update(status="COMPLETE" if q.returncode==0 else "AUDIT_STOP",end=datetime.now(timezone.utc).isoformat())
        write(ROOT/"execution.json",st)
        assert st["ancillary_s"]<=540 and st["replay_s"]<=660 and st["numerical_s"]<=1200
        if q.returncode:raise RuntimeError(logfile.read_text(errors="replace")[-2000:])
        print("independent verification complete",dt)
