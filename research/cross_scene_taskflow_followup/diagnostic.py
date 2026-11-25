"""One worker operation. All output paths belong to the follow-up directory."""
import gzip
import json
import math
import subprocess
import time
from collections import Counter
from fractions import Fraction as Q
import numpy as np
from assets import CFG,DATA,HERE,OLD,base,digest,encode,get_plan,plan_obj,put_plan,read,valid_c0,write
from model import Problem,DOM,Invalid,transitions,event_arrays,independent_events
from heat import evaluate
from local_domain import Space,candidates,gap_table,select_targets

def preflight():
    def git(*a): return subprocess.check_output(["git",*a],cwd=HERE)
    base_sha=CFG["base"]
    assert git("rev-parse","HEAD^").decode().strip()==base_sha
    assert git("rev-parse",base_sha+"^").decode().strip()==CFG["prior_freeze"]
    snapshot=json.loads((OLD/"RESULT_SHA256.json").read_bytes())
    assert digest(json.dumps(snapshot["files"],sort_keys=True,separators=(",",":")).encode())==snapshot["snapshot"]
    evidence={}
    inputs=["model.py","profiles.py","heat.py","search.py","mechanism.py","config/p1_frozen.json",
            "config/gpu_profiles.csv","config/cpu_npu_profiles.csv"]
    for case,info in CFG["cases"].items():
        key=info["sha"]
        inputs.extend(["logs/plans/"+key+".json.gz","g3_thermal/"+case+"_G3.json",
                       "certificates/"+key+"_continuous.json.gz","instances/"+case+".csv"])
    for name in inputs:
        raw=(OLD/name).read_bytes()
        assert digest(raw)==snapshot["files"][name]
        oid=git("rev-parse",base_sha+":research/cross_scene_taskflow_diagnostic/"+name).decode().strip()
        import hashlib
        assert hashlib.sha1(("blob "+str(len(raw))+"\0").encode()+raw).hexdigest()==oid
        evidence[name]=dict(sha256=digest(raw),git_blob=oid)
    seeds={}
    for case,info in CFG["cases"].items():
        p=Problem(case);plan=base(case);key=put_plan(case,plan)
        prior=json.loads((OLD/"g3_thermal"/(case+"_G3.json")).read_bytes())
        assert prior["safe_plan"]==key==info["sha"]
        assert prior["safe"]["E_J"]==info["J"]
        cert=evaluate(p,plan,cert=True)
        old=json.loads(gzip.decompress((OLD/"certificates"/(key+"_continuous.json.gz")).read_bytes()))["metrics"]
        assert cert["status"]==old["status"]=="SAFE" and cert["E_bounds"][0]<=info["J"]<=cert["E_bounds"][1]
        assert all(abs(a-b)<1e-9 for a,b in zip(cert["peak_hi"],old["peak_hi"]))
        seeds[case]=dict(sha=key,metrics=cert,requests=len(p.req))
    write("preflight.json",dict(verified=evidence,seeds=seeds,base=base_sha,prior_freeze=CFG["prior_freeze"],
          freeze=git("rev-parse","HEAD").decode().strip(),prior_snapshot=snapshot["snapshot"]))

def select(case,end):
    p=Problem(case)
    write("targets/"+case+".json",select_targets(p,base(case),end))

def target(case,num):
    return read("targets/"+case+".json")["targets"][int(num)]

def search(case,num,end,arm=None):
    p=Problem(case);seed=base(case);rec=target(case,num);i=rec["stage"];op=tuple(rec["opt"])
    ids=read("ablation/groups.json")["groups"][arm] if arm else rec["members"]
    label=f"{case}_{num}" if not arm else arm
    folder="pools/" if not arm else "ablation/pools/"
    space=Space(p,seed,ids,i,op)
    stats=dict(deterministic_placements=0,exhausted=False,visits=0,unique=0,duplicates=0,illegal=0)
    status=Counter();seen=set();pool=[];best_safe=None;min_safe_lower=math.inf
    seedkey=CFG["cases"][case]["sha"]
    stats["domain_sizes"]={str(j):len(rows) for j,rows in space.domains.items()}
    stats["placement_product_before_pairwise_filter"]=math.prod(stats["domain_sizes"].values())
    def snapshot():
        # References use separate roles and never occupy one of the 24 target slots.
        top=[]
        for key,m,plan in pool:
            assert put_plan(case,plan)==key
            top.append(dict(sha=key,metrics=m))
        safe=None
        if best_safe:
            key,m,plan=best_safe
            assert put_plan(case,plan)==key
            safe=dict(sha=key,metrics=m)
        joint=[x["sha"] for x in top]
        for key in [seedkey]+([safe["sha"]] if safe else []):
            if key not in joint:joint.append(key)
        write(folder+label+".json",dict(case=case,target=num,stage=i,opt=op,members=ids,stats=stats,
             all_unique_status=status,top=top,baseline=seedkey,best_pinned_SAFE=safe,
             least_pinned_SAFE_lower=None if min_safe_lower==math.inf else min_safe_lower,
             common_ids=joint,pool_hash=digest(encode(joint)),
             coverage="有限搜索。exhausted 仅表示所选目标、固定邻域及局部起点和空闲控制组合已遍历。"))
    for plan in candidates(p,seed,space,end,stats):
        if time.perf_counter()>=end:break
        stats["visits"]+=1
        key=digest(encode(plan_obj(case,plan)))
        if key in seen:
            stats["duplicates"]+=1;continue
        seen.add(key);stats["unique"]+=1
        try: m=evaluate(p,plan,cert=True)
        except Invalid:
            stats["illegal"]+=1;continue
        status[m["status"]]+=1
        if not valid_c0(m):continue
        item=(key,m,plan)
        if m["status"]=="SAFE":
            min_safe_lower=min(min_safe_lower,m["E_bounds"][0])
            if best_safe is None or (m["E_J"],key)<(best_safe[1]["E_J"],best_safe[0]):best_safe=item
        if len(pool)<24 or (m["E_J"],key)<(pool[-1][1]["E_J"],pool[-1][0]):
            pool.append(item);pool.sort(key=lambda x:(x[1]["E_J"],x[0]));del pool[24:]
    snapshot()

def physical(p,plan):
    rows,low=plan;units,sw,edges=transitions(p,rows,low,edges=True)
    dwell={};baseline=Q(0);activity=Q(0)
    for d,members in enumerate(((0,1),(2,),(3,))):
        old=last=0
        seq=[(b,new) for a,b,dom,k,new in sw if dom==d]+[(p.horizon,0)]
        for end,k in seq:
            ticks=end-last
            if ticks:dwell[d,old]=dwell.get((d,old),0)+ticks
            for u in members:
                b=next(v[0] for (_,w,f),v in p.exact.items() if w==u and f==old)
                baseline+=b*ticks/10000
            last=end;old=k
    for i,(u,k,t) in enumerate(rows):
        idle,_,busy,_=p.exact[p.kinds[i],u,k]
        activity+=(busy-idle)*p.dur(i,u,k)/10000
    switch=Q(15,10000)*len(sw);ext=Q(3,10)*p.horizon/10000
    return dict(edges=edges,switches=sw,low=sorted(low),dwell={f"{d}.{k}":v for (d,k),v in dwell.items()},
                base_J=str(baseline),activity_J=str(activity),switch_J=str(switch),external_J=str(ext),
                nonthermal_J=str(baseline+activity+switch+ext))

def differences(original,actual,orig_phy,phy):
    before=set(map(tuple,orig_phy["edges"]));after=set(map(tuple,phy["edges"]))
    a,b=original[0],actual[0]
    return dict(stages=[[j,list(x),list(y)] for j,(x,y) in enumerate(zip(a,b)) if x!=y],
                config_changes=[j for j,(x,y) in enumerate(zip(a,b)) if x[:2]!=y[:2]],
                added_edges=sorted(after-before),removed_edges=sorted(before-after),
                dwell_changed=orig_phy["dwell"]!=phy["dwell"],control_changed=original[1]!=actual[1])

def certificate(p,key):
    path=f"certificates/{key}.json"
    if (DATA/path).exists():return read(path)
    plan=get_plan(key);seed=base(p.case);phy=physical(p,plan)
    ev,sw,edges=event_arrays(p,*plan)
    real=evaluate(p,plan,cert=True,trace=True);reset=evaluate(p,plan,cert=True,reset=True,trace=True)
    aa=np.asarray(real.pop("events"));bb=np.asarray(reset.pop("events"))
    assert np.array_equal(aa[:,:14],ev) and np.array_equal(bb[:,:14],ev)
    out=DATA/"certificates";out.mkdir(exist_ok=True)
    np.savez_compressed(out/(key+".npz"),events=ev,continuous=aa[:,14:],reset=bb[:,14:])
    obj=dict(sha=key,case=p.case,continuous=real,reset=reset,physical=phy,
             changes_from_G3=differences(seed,plan,physical(p,seed),phy))
    write(path,obj);return obj

def assessment(case,num,arm=None):
    p=Problem(case);label=f"{case}_{num}" if not arm else arm
    f="" if not arm else "ablation/"
    pool=read(f+"pools/"+label+".json")
    keys=pool["common_ids"]
    assert digest(encode(keys))==pool["pool_hash"] and len(keys)==len(set(keys))
    certs={key:certificate(p,key) for key in keys}
    prior={x["sha"]:x["metrics"] for x in pool["top"]}
    safe=pool["best_pinned_SAFE"]
    if safe:prior[safe["sha"]]=safe["metrics"]
    for key,m in prior.items():
        cc=certs[key]["continuous"]
        assert cc["status"]==m["status"] and abs(cc["E_J"]-m["E_J"])<1e-10
    groups={g:[] for g in ("C0","C1","C2")}
    for key,cert in certs.items():
        c=cert["continuous"];r=cert["reset"]
        if valid_c0(c):
            groups["C0"].append(key)
            if c["status"]=="SAFE":groups["C1"].append(key)
            if r["status"]=="SAFE":groups["C2"].append(key)
    for keys0 in groups.values():
        keys0.sort(key=lambda k:(certs[k]["continuous"]["E_J"],k))
    def interval(group):
        return [min(certs[k]["continuous"]["E_bounds"][j] for k in groups[group]) for j in (0,1)]
    gaps={}
    for g in ("C0","C2"):
        if groups["C1"] and groups[g]:
            a,b=interval("C1"),interval(g)
            gaps["C1_minus_"+g]=[max(0.,a[0]-b[1]) if g=="C0" else a[0]-b[1],a[1]-b[0]]
    write(f+"counterfactual/"+label+".json",dict(case=case,target=num,pool_hash=pool["pool_hash"],common_ids=keys,
        ranked=groups,best={g:v[0] if v else None for g,v in groups.items()},gap_bounds_J=gaps,
        point_gaps_J={"C1_minus_"+g:certs[groups["C1"][0]]["continuous"]["E_J"]-
                     certs[groups[g][0]]["continuous"]["E_J"] for g in ("C0","C2") if groups[g] and groups["C1"]},
        C2_only=sorted(set(groups["C2"])-set(groups["C1"])),C1_only=sorted(set(groups["C1"])-set(groups["C2"]))))
