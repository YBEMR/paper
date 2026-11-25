"""Independent event/thermal replay, stage-wise attribution and paired decision."""
import csv,gzip,json,statistics
from collections import Counter
from c1r_assets import ROOT,C,read,write,digest
from bounded import options,graph,legal_assignment,proxy
from base import Problem,Layout,Access,decode,changes,raw,dynamic_region,table,np
from numerics import rights_check
from audit import thermal

def reliable(first,last):
    return max(0.,1000*(first["lo"]-last["hi"]))

def assess():
    samples=read(ROOT/"samples.json")["cases"]
    histories={r["sample"]:r for r in csv.DictReader((C/"paired.csv").open(encoding="utf8",newline=""))}
    states=read(ROOT/"execution.json");proofs={};per_arm=[];paired=[];candidates=[];findings=[];stages=[]
    for s in samples:
        ident=s["id"];p=Problem(s["case"]);matrices={};src=s["source"];ref=s["prior_metrics"]
        baseline=dict(sha=src,E=ref["E_J"],lo=ref["E_bounds"][0],hi=ref["E_bounds"][1])
        base=decode(json.loads(gzip.decompress((C/"prestates"/(src+".json.gz")).read_bytes())))
        hist=read(C/"replays"/ident/"New"/"arm.json")
        by={};hints=[]
        for variant in ("Full-Hint","Compact-Hint"):
            folder=ROOT/"runs"/ident/variant;r=read(folder/"arm.json");a=r["auxiliary"]
            assert r["source"]==src and a["start"]>0 and a["wall_s"]<=11
            ids=a["config_candidates"];assert ids==hist["auxiliary"]["config_candidates"] and a["selection"]==hist["auxiliary"]["selection"]
            levels=options(p,base[0],ids);edges=graph(p,base[0],levels)
            hb=gzip.decompress((folder/"hint.json.gz").read_bytes());hints.append(digest(hb));hint=json.loads(hb)
            hrows=list(map(tuple,hint["rows"]));hs=[i for i,v in enumerate(hrows) if v!=base[0][i]]
            assert hs==a["hint_support"]==[i for i,z in enumerate(hint["z"]) if z] and a["hint_gain_uJ"]==proxy(p,base[0],hrows)
            assert set(a["hint_cfg"])=={i for i in hs if hrows[i][:2]!=base[0][i][:2]}
            env={i:(l,h) for i,l,h in a.get("envelopes",[])}
            if variant=="Compact-Hint":
                fits=lambda rs:all(-env.get(i,(0,0))[0]<=x[2]-base[0][i][2]<=env.get(i,(0,0))[1] for i,x in enumerate(rs))
                assert a["hint_injected"]==(fits(hrows) and legal_assignment(p,base[0],hrows,ids,levels,edges))
            for entry in a["solves"]:
                if "edits" not in entry:continue
                rs=base[0].copy()
                for i,v in entry["edits"]:rs[i]=tuple(v)
                assert legal_assignment(p,base[0],rs,ids,levels,edges) and proxy(p,base[0],rs)==entry["proxy_gain_uJ"]
                assert variant!="Compact-Hint" or fits(rs)
            forrec=[];visits=r["visits"]
            for c in r["candidates"]:
                k=c["sha"];buf=gzip.decompress((folder/(k+".json.gz")).read_bytes());assert digest(buf)==k
                plan=decode(json.loads(buf));d=changes(p,base,plan);assert raw(d)==raw(c["changes"])
                tags=sorted({tag for tag,j in visits if j==k})
                sf=set(d["config"]);st=sf|set(d["moved"])
                for special in {not t.startswith("core") and t!="source" for t in tags}:
                    f,h=(sf,st) if special else (set(r["core"]["Sf"]),set(r["core"]["St"]))
                    rights_check(p,base,plan,Access(f,h,{},set(),set()),dynamic_region(p,base,h,f,1))
                assert str(sum(Layout(p,plan[0]).components(plan[1]).values()))==c["reference_J"]
                m=c["metrics"];lo,hi=m["E_bounds"]
                with np.load(folder/(k+".npz")) as data:
                    ev=data["events"];finger=digest(ev.tobytes())
                    if k not in proofs:proofs[k]=dict(**thermal(p,plan,ev,m,matrices),trace_sha=finger,metrics_sha=digest(raw(m)))
                    else:assert proofs[k]["trace_sha"]==finger and proofs[k]["metrics_sha"]==digest(raw(m))
                assert c["on_time"] and c["certified_s"]<=30
                groups=sorted({("hint" if t.startswith("hint") else "cp" if t.startswith("cp") else "core" if t.startswith("core") else "source") for t in tags})
                item=dict(sample=ident,case=s["case"],variant=variant,sha=k,E=m["E_J"],lo=lo,hi=hi,status=m["status"],
                     groups=groups,origins=tags,cfg=len(sf),moved=len(d["moved"]),support=len(st),certified_s=c["certified_s"],
                     config_signature=repr([(i,plan[0][i][:2]) for i in sorted(sf)]),reference_J=c["reference_J"])
                if groups!=["source"] and k!=src and reliable(baseline,item)>0 and m["status"]=="SAFE" and len(sf)>=2 and (set(groups)&{"hint","cp"} or r.get("region_source") in ("cp_rights","hint_rights")):
                    item["multi_nonfallback"]=True
                else:item["multi_nonfallback"]=False
                candidates.append(item);forrec.append(item)
            ordered=[baseline];stepg={};pure={}
            for stage in ("hint","cp","core"):
                options_=[v for v in forrec if v["status"]=="SAFE" and stage in v["groups"]]
                b=min([ordered[-1],*options_],key=lambda x:x["hi"])
                pure[stage]=min(options_,key=lambda x:x["hi"])["sha"] if options_ else ""
                stepg[stage]=reliable(ordered[-1],b);ordered.append(b)
                stages.append(dict(sample=ident,variant=variant,stage=stage,returned_safe=len(options_),stage_best=pure[stage],
                                  cumulative_best=b["sha"],cumulative_J=b["E"],lower_J=b["lo"],upper_J=b["hi"],
                                  incremental_gain_lower_mJ=stepg[stage]))
            best=ordered[-1];initial=ordered[0];histrow=histories[ident];times=r.get("offer_s",{})
            ar=dict(sample=ident,case=s["case"],seed=s["seed"],variant=variant,source=src,source_J=ref["E_J"],
                 vars=a["vars"],constraints=a["constraints"],retained=a["retained"],tasks=a["tasks"],hint_cfg=len(a["hint_cfg"]),
                 hint_support=len(hs),hint_gain_uJ=a["hint_gain_uJ"],hint_injected=a["hint_injected"],
                 hint_gain_lower_mJ=stepg["hint"],cp_extra_lower_mJ=stepg["cp"],core_extra_lower_mJ=stepg["core"],
                 final_J=best["E"],final_lo=best["lo"],final_hi=best["hi"],final_sha=best["sha"],
                 net_lower_mJ=reliable(initial,best),region_source=r.get("region_source","ordinary"),fallback=r["fallback"],
                 aux_status="|".join(v["status"] for v in a["solves"]),aux_assignments=sum("edits" in v for v in a["solves"]),
                 select_s=a["select_s"],hint_gen_s=a["hint_gen_s"],graph_s=a["graph_s"],propagate_s=a["propagate_s"],build_s=a["build_s"],
                 aux_solve_s=sum(v.get("wall_s",0) for v in a["solves"]),aux_s=a["wall_s"],
                 hint_evaluate_s=sum(sum(v) for k,v in times.items() if k.startswith("hint")),
                 cp_evaluate_s=sum(sum(v) for k,v in times.items() if k.startswith("cp")),
                 core_evaluate_s=sum(sum(v) for k,v in times.items() if k.startswith("core")),
                 arm_s=r["elapsed_s"],historical_old_J=histrow["old_J"],historical_new_J=histrow["new_J"],
                 multi_nonfallback=sum(v["multi_nonfallback"] for v in forrec))
            per_arm.append(ar);by[variant]=(ar,best,forrec,ordered)
        assert hints[0]==hints[1]
        f,fb,fc,fo=by["Full-Hint"];c,cb,cc,co=by["Compact-Hint"]
        assert fo[1]["sha"]==co[1]["sha"] and fo[1]["hi"]==co[1]["hi"]
        multi=[x for x in cc if x["multi_nonfallback"]];fullcfg={x["config_signature"] for x in fc}
        beyond=[x for x in multi if x["hi"]<min(fb["lo"],co[1]["lo"])]
        mechanism=[x for x in beyond if "cp" in x["groups"] or ("core" in x["groups"] and c["region_source"]=="cp_rights")]
        for x in mechanism:findings.append(dict(sample=ident,case=s["case"],sha=x["sha"],config=x["cfg"],moved=x["moved"],support=x["support"],
                vs_full_lower_mJ=reliable(fb,x),vs_hint_lower_mJ=reliable(co[1],x),vs_source_lower_mJ=reliable(baseline,x),
                groups=x["groups"],new_configuration=x["config_signature"] not in fullcfg))
        paired.append(dict(sample=ident,case=s["case"],source=src,full_sha=fb["sha"],compact_sha=cb["sha"],source_J=ref["E_J"],
                 full_J=fb["E"],compact_J=cb["E"],full_lo=fb["lo"],full_hi=fb["hi"],compact_lo=cb["lo"],compact_hi=cb["hi"],
                 advantage_mJ=1000*(fb["E"]-cb["E"]),win_lower_mJ=reliable(fb,cb),loss_lower_mJ=reliable(cb,fb),
                 result="win" if cb["hi"]<fb["lo"] else "loss" if fb["hi"]<cb["lo"] else "overlap",
                 shared_hint_sha=hints[0],hint_multi=f["hint_cfg"]>=2,full_multi=f["multi_nonfallback"],compact_multi=len(multi),
                 multi_beyond_common_hint_and_full=len(beyond),compact_cp_or_its_core_witnesses=len(mechanism),
                 direct_aux_witnesses=sum("cp" in x["groups"] for x in mechanism),retained=c["retained"],full_vars=f["vars"],compact_vars=c["vars"]))
    table(ROOT/"results.csv",per_arm);table(ROOT/"paired.csv",paired);table(ROOT/"stages.csv",stages);table(ROOT/"candidates.csv",candidates)
    write(ROOT/"certificates.json",proofs);write(ROOT/"witnesses.json",findings)
    d=[x for x in paired if x["case"]=="D3"]
    write(ROOT/"gate.json",dict(correctness=read(ROOT/"validation"/"gate.json")["passed"],certified_records=len(candidates),unique=len(proofs),
        d3_pairs=dict(Counter(x["result"] for x in d)),d3_multi_cases=sum(x["compact_multi"]>0 for x in d),
        d3_incremental_cases=sum(x["compact_cp_or_its_core_witnesses"]>0 for x in d),
        d3_direct_cases=sum(x["direct_aux_witnesses"]>0 for x in d),c2_runs=0,holdout_runs=0))
if __name__=="__main__":assess()
