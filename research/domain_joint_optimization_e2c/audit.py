"""Verify physical schedules and thermal traces, then compare only frozen, timed receipts."""
import csv,gzip,json
from collections import Counter
from samples import ROOT,read,write,digest
from support import Problem
from base import decode,key,changes,Layout,np,transitions,raw,Access,dynamic_region,table
from numerics import rights_check
from validation import common_grid
from scipy.linalg import expm

def thermal(p,plan,events,metric,matrices):
    lay=Layout(p,plan[0]);assert transitions(p,*plan)[1]==lay.switches(plan[1])
    a,b=common_grid(lay.events(plan[1]),events[:,:14]);assert np.array_equal(a,b)
    assert events.shape[1]==31 and events[0,0]==0 and events[-1,1]==p.horizon
    assert np.array_equal(events[:-1,1],events[1:,0]) and np.all(events[:,1]>events[:,0])
    x=np.r_[p.initial,0.,1.];err=0.
    for row in events:
        l,r=row[:2];q=row[2:6];slope=row[6:10];k=(r-l,*q,*slope)
        if k not in matrices:
            A=np.zeros((6,6));A[:4,:4]=(-p.G+np.diag(slope))/p.cap[:,None]
            A[:4,5]=(p.G@np.full(4,p.ta)+q-35*slope)/p.cap;A[4,:4]=slope;A[4,5]=sum(q)-35*sum(slope)+.3
            matrices[k]=expm(A*((r-l)/10000))
        x=matrices[k]@x;err=max(err,max(abs(x[:4]-row[18:22])))
    lo,hi=metric["E_bounds"];assert lo<=x[4]<=hi and err<1e-7
    assert metric["min_deadline_slack_ms"]>=-1e-9
    if metric["status"]=="SAFE":assert max(metric["peak_hi"])<=80 and min(metric["minimum_lo"])>=20
    assert max(abs(np.maximum(np.max(events[:,22:26],axis=0),p.initial)-metric["peak_hi"]))<1e-7
    return dict(expm_J=x[4],temperature_endpoint_error_K=err,status=metric["status"])

def run():
    samples=read(ROOT/"samples.json")["cases"];paired=[];detail=[];proofs={};stage=[]
    for case in ("D1","D2","D3"):
        p=Problem(case);matrices={}
        for s in (v for v in samples if v["case"]==case):
            src=s["source"];base=decode(json.loads(gzip.decompress((ROOT/"prestates"/(src+".json.gz")).read_bytes())))
            methods={}
            for name in ("Old","New"):
                folder=ROOT/"replays"/s["id"]/name;arm=read(folder/"arm.json");assert arm["status"] in ("COMPLETE","TIME_LIMIT")
                records=[];aux=arm["auxiliary"];core=arm["core"]
                for x in aux.get("assignments",[]):
                    rows=base[0].copy()
                    for i,r in x["changed"]:rows[i]=tuple(r)
                    sf=set(x["Sf"]);st=set(x["St"]);lay=Layout(p,rows);transitions(p,rows,set())
                    assert st=={i for i in range(p.n) if rows[i]!=base[0][i]} and len(st)<=24
                    assert sf=={i for i in st if rows[i][:2]!=base[0][i][:2]} and len(sf)<=12
                    assert all(rows[i][0]==base[0][i][0] and abs(rows[i][2]-base[0][i][2])<=500 for i in st)
                    assert not changes(p,base,(rows,frozenset()))["inversions"]
                regions={}
                for c in arm["candidates"]:
                    k=c["sha"];packed=gzip.decompress((folder/(k+".json.gz")).read_bytes());assert digest(packed)==k
                    plan=decode(json.loads(packed));delta=changes(p,base,plan);assert raw(c["changes"])==raw(delta)
                    cfg=delta["config"];moved=delta["moved"];union=set(cfg)|set(moved)
                    assert set(c["support"])==union and len(union)<=24 and len(cfg)<=12
                    if c["origin"].startswith("aux"):
                        sf=set(cfg);st=union
                    else:sf=set(core["Sf"]);st=set(core["St"])
                    regkey=tuple(sorted(sf)),tuple(sorted(st))
                    if regkey not in regions:regions[regkey]=dynamic_region(p,base,st,sf,1)
                    rights_check(p,base,plan,Access(sf,st,{},set(),set()),regions[regkey])
                    assert str(sum(Layout(p,plan[0]).components(plan[1]).values()))==c["reference_J"]
                    certfile=folder/(k+".npz")
                    fingerprint=digest(certfile.read_bytes())
                    if k not in proofs:
                        with np.load(certfile) as evidence:
                            proof=thermal(p,plan,evidence["events"],c["metrics"],matrices)
                            trace_hash=digest(evidence["events"].tobytes())
                        proofs[k]=dict(**proof,trace_sha256=trace_hash,metrics_sha256=digest(raw(c["metrics"])))
                    else:
                        with np.load(certfile) as evidence:assert digest(evidence["events"].tobytes())==proofs[k]["trace_sha256"]
                        assert digest(raw(c["metrics"]))==proofs[k]["metrics_sha256"]
                    m=c["metrics"];joint=bool(cfg and moved);eligible=c["on_time"] and c["certified_s"]<=30
                    origins=[a for a,h in arm["visits"] if h==k];aux_origin=any(a.startswith("aux") for a in origins)
                    item=dict(sample=s["id"],case=case,method=name,sha=k,origin=c["origin"],aux_direct=aux_origin,
                       on_time=eligible,status=m["status"],support=len(union),config=len(cfg),shift=len(moved),joint=joint,
                       config_signature=repr([(i,plan[0][i][:2]) for i in cfg]),target_changed=c["primary_changed"],
                       target_recovered=c["original_proposal_recovered"],E_J=m["E_J"],lo=m["E_bounds"][0],hi=m["E_bounds"][1],
                       peak_hi_C=max(m["peak_hi"]),time_s=c["certified_s"],reference_J=c["reference_J"],trace_file_sha256=fingerprint)
                    detail.append(item)
                    if eligible:records.append(item)
                # The already certified pre-state is a common reference even on an interrupted arm.
                ref=dict(sha=src,lo=s["prior_metrics"]["E_bounds"][0],hi=s["prior_metrics"]["E_bounds"][1],E_J=s["prior_metrics"]["E_J"])
                safe=[z for z in records if z["status"]=="SAFE"]
                best=min([ref,*safe],key=lambda z:z["hi"])
                methods[name]=(records,best,arm)
                stage.append(dict(sample=s["id"],method=name,status=arm["status"],elapsed_s=arm["elapsed_s"],
                     fallback=arm["fallback"],aux_status="|".join(v["status"] for v in aux.get("solves",[])),
                     unique_certified=len(records),joint=sum(z["joint"] for z in records),best_J=best["E_J"],
                     actual_supports=sorted({z["support"] for z in records if z["joint"]}),
                     exact_target_recovered=any(z["target_recovered"] for z in records),
                     main_changed_alternative=any(z["target_changed"] and not z["target_recovered"] for z in records),
                     primary_unchanged_joint=any(z["joint"] and not z["target_changed"] for z in records)))
            old,ob,oa=methods["Old"];new,nb,na=methods["New"];old_cfg={z["config_signature"] for z in old}
            old_ids={z["sha"] for z in old};src_lo=s["prior_metrics"]["E_bounds"][0]
            novel=[z for z in new if z["joint"] and z["sha"] not in old_ids]
            novel_cfg=[z for z in novel if z["config_signature"] not in old_cfg]
            supported=[z for z in novel_cfg if z["aux_direct"] or na["fallback"] is False]
            strict=[z for z in supported if z["status"]=="SAFE" and z["hi"]<min(src_lo,ob["lo"])]
            direct=[z for z in strict if z["aux_direct"]]
            witness=min(strict,key=lambda z:z["hi"]) if strict else None
            paired.append(dict(sample=s["id"],case=case,seed=s["seed"],iteration=s["iteration"],source=src,primary=s["primary"],
                source_J=s["prior_metrics"]["E_J"],old_id=ob["sha"],new_id=nb["sha"],old_J=ob["E_J"],new_J=nb["E_J"],
                old_lo=ob["lo"],old_hi=ob["hi"],new_lo=nb["lo"],new_hi=nb["hi"],
                delta_mJ=1000*(ob["E_J"]-nb["E_J"]),result="win" if nb["hi"]<ob["lo"] else "loss" if ob["hi"]<nb["lo"] else "overlap",
                old_fallback=oa["fallback"],new_fallback=na["fallback"],old_joint=sum(z["joint"] for z in old),new_joint=sum(z["joint"] for z in new),
                novel_joint=len(novel),novel_config=len(novel_cfg),new_supported=len(supported),strict_witnesses=len(strict),direct_witnesses=len(direct),
                witnesses_better_than_source=sum(z["status"]=="SAFE" and z["hi"]<src_lo for z in supported),
                witness=witness["sha"] if witness else "",witness_gain_lower_mJ=1000*(min(src_lo,ob["lo"])-witness["hi"]) if witness else 0,
                primary_exact_in_witness=any(z["target_recovered"] for z in strict),
                primary_other_in_witness=any(z["target_changed"] and not z["target_recovered"] for z in strict),
                primary_unchanged_in_witness=any(not z["target_changed"] for z in strict)))
        write(ROOT/"audit_progress.json",dict(through=case,unique=len(proofs)))
    table(ROOT/"paired.csv",paired);table(ROOT/"candidates.csv",detail);table(ROOT/"arms.csv",stage)
    write(ROOT/"thermal_replay.json",proofs)
    cases={c:dict(pairs=sum(z["case"]==c for z in paired),
           witnesses=sum(z["case"]==c and bool(z["strict_witnesses"]) for z in paired),
           supported=sum(z["case"]==c and bool(z["new_supported"]) for z in paired),
           direct=sum(z["case"]==c and bool(z["direct_witnesses"]) for z in paired)) for c in ("D1","D2","D3")}
    write(ROOT/"gate.json",dict(cases=cases,verified_schedules=len(proofs),
           paired=len(paired),timed_candidate_records=len(detail),correctness="PASS",
           differential_witness=any(z["strict_witnesses"] for z in paired),c2_authorized=False,c2_started=False))
