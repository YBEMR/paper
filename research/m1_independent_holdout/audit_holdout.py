"""Audit the registered holdout; recover both budgets and incremental decisions."""
import csv
import gzip
import json
from collections import Counter, defaultdict
from functools import lru_cache
from itertools import groupby
from statistics import mean, median

from run_holdout import BASE, DATA, HERE, cases, frozen, sha
from analyze import comparison, physical, read, summarize, verify_stage

METHODS = ("HT", "NT", "OT", "NC", "C2", "OC", "BT")
PAIRS = (("NC","NT"), ("OT","NT"), ("C2","NT"), ("OC","NT"), ("NT","HT"),
         ("C2","HT"), ("C2","OT"), ("OT","HT"), ("OC","OT"), ("OC","HT"))

def write_csv(name,rows):
    with (DATA/name).open("w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

def check_case(label,word,audit):
    name = "V"+label[1:]+"_"+word
    input_path = DATA/"validation_inputs"/(name+".csv")
    original_bytes=input_path.read_bytes()
    c=frozen.reordered(frozen.case_for(label),label,word)
    assert c.label==name and input_path.read_bytes()==original_bytes
    n=int(label[1:])
    assert len(c.p.req)==n and all(r["deadline_ms"]-r["release_ms"]==300 for r in c.p.req)
    assert len(c.p.initial)==4
    folder=DATA/"runs"/name
    assert set(p.name for p in folder.iterdir())==set(METHODS)
    budget=read(folder/"HT/run.json")["records"][3]["end_s"]

    @lru_cache(None)
    def ext(j,g,npu,x,y):
        return c.extension(*frozen.window_types(c,j),g,npu,x,y)
    @lru_cache(None)
    def backgrounds(j,cfg):
        state=frozen.initial(c)
        if cfg:
            data=c.ledger(cfg,(j-1)*frozen.WINDOW,j*frozen.WINDOW,2500,False,False)
            state.update(f=tuple(map(int,data[2])),k=tuple(map(int,data[3])))
        options=defaultdict(set)
        for action,_ in c.candidates(j,state):
            options[action[:2]].add(action[2:])
        return options,state
    @lru_cache(None)
    def geometry(j,cfg,g,npu):
        _,s=backgrounds(j,cfg)
        _,a,b=frozen.window_types(c,j)
        planes=frozen.load_planes(c,j,s,g,npu,a,b)
        center=c.eng.quota(s,j,(g,npu),(a,b))
        points,_=frozen.anchors(planes,center,a,b)
        return planes,points

    metrics=[]; calls=[]; matches=[]; paired=[]
    physical_plans={}; fixed_groups={}; fixed_ids={}; fixed_beams={}
    for method in METHODS:
        run=read(folder/method/"run.json")
        rec=run["records"]
        assert (run["case"],run["method"])==(name,method)
        assert run["budget_s"]==(None if method in ("HT","BT") else budget)
        assert len(rec)>=4 and len({r["id"] for r in rec})==len(rec)
        assert all(r["width"]==4 for r in rec[:4])
        assert all(a["end_s"]<=b["start_s"] for a,b in zip(rec,rec[1:]))
        if method in ("BT","HT"):
            assert len(rec)==4 and run["stop"]=="fixed_four"
        stages=[]; seen=set()
        for i,s in enumerate(run["stages"]):
            assert s["width"]==4*2**i
            with gzip.open(folder/method/f"w{s['width']}.json.gz","rt") as f:
                stage=json.load(f)
            assert all(s[k]==stage[k] for k in s)
            volumes,ids=verify_stage(c,method,stage,geometry,ext,backgrounds,audit)
            if i==0:
                actions=groupby(stage["actions"],key=lambda r:(r[0],r[1],r[2],r[3]))
                fixed_groups[method]={}
                for group,(key,rows) in zip(stage["groups"],actions,strict=True):
                    assert key==tuple(group[k] for k in ("window","parent","g","n"))
                    fixed_groups[method][key]=(group["slots"],group["calibration"],tuple((r[4],r[5]) for r in rows))
                fixed_ids[method]=set(ids)
                fixed_beams[method]=stage["beam"]
            actual=[(r["rank"],r["id"]) for r in rec if r["width"]==s["width"]]
            order=[(rank,key) for rank,key in enumerate(ids,1) if key not in seen]
            assert actual==order[:len(actual)]
            seen.update(key for _,key in actual)
            stages.append(dict(**s,volumes=volumes,ids=ids))
        for i,r in enumerate(rec,1):
            cert=r["cert"]; plan=cert["plan_sha256"]; m=cert["metrics"]
            raw=read(DATA/"physical/evidence"/name/plan/"certificate.json")
            assert {k:v for k,v in cert.items() if k!="cert_s"}=={k:v for k,v in raw.items() if k!="cert_s"}
            if plan not in physical_plans:
                physical_plans[plan]=physical(name,dict(plan=plan,id=r["id"]),n,c.p.horizon)
            assert physical_plans[plan][0]==r["id"]
            calls.append(dict(case=name,method=method,call=i,width=r["width"],rank=r["rank"],id=r["id"],
                plan=plan,status=m["status"],E_J=m["E_J"],E_lo=m["E_bounds"][0],E_hi=m["E_bounds"][1],
                peak_hi_C=max(m["peak_hi"]),deadline_slack_ms=m["min_deadline_slack_ms"],ref_E=r["ref_E"],
                predicted_peak_C=r["prediction"],start_s=r["start_s"],end_s=r["end_s"],cert_s=r["cert_s"],
                within_common_budget=r["end_s"]<=budget if method!="BT" else None))
        for mode in (("fixed",) if method=="BT" else ("fixed","time")):
            m=summarize(run,stages,mode,budget,c.windows)
            cut=m["observed_s"]
            def span(t0,t1):
                return max(0.,min(t1,cut)-max(0.,t0))
            build_s=sum(span(s["ready_s"]-s["build_s"],s["ready_s"]) for s in stages)
            cert_s=sum(span(r["start_s"],r["end_s"]) for r in rec)
            other_s=cut-build_s-cert_s
            assert other_s>=-1e-8 and m["uncertified_terminal"]>=0
            m.update(service_requests=n,build_and_rank_s=build_s,cert_and_write_s=cert_s,
                     other_control_s=other_s,stop=run["stop"])
            metrics.append(m)
    audit["unique_physical_plans"]+=len(physical_plans)
    lookup={(r["method"],r["mode"]):r for r in metrics}
    for A,B in PAIRS+(("NT","BT"),("BT","HT")):
        for mode in (("fixed",) if "BT" in (A,B) else ("fixed","time")):
            paired.append(comparison(lookup[A,mode],lookup[B,mode]))
    for A,B in (("NC","NT"),("OT","NT"),("NT","HT"),("NT","BT"),("BT","HT"),("OC","C2")):
        x,y=fixed_groups[A],fixed_groups[B]
        common=x.keys()&y.keys(); assert common
        ident=sum(x[k][2]==y[k][2] for k in common)
        for k in common:
            assert x[k][0]==y[k][0]
            if A in ("NC","NT","BT") and B in ("NT","HT","BT"):
                assert x[k][1]==y[k][1]
        if (A,B) in (("NC","NT"),("OC","C2")):
            assert ident==len(common)
        if (A,B)==("OC","C2"):
            assert fixed_beams[A]==fixed_beams[B] and fixed_ids[A]==fixed_ids[B]
        a,b=fixed_ids[A],fixed_ids[B]
        first=next((j for j,(u,v) in enumerate(zip(fixed_beams[A],fixed_beams[B]),1) if u!=v),None)
        matches.append(dict(case=name,base=A,other=B,shared_parent_frequency_groups=len(common),
            base_groups=len(x),other_groups=len(y),equal_slots=len(common),identical_proposals=ident,
            first_different_beam_window=first,base_pool=len(a),other_pool=len(b),intersection=len(a&b)))
    print("verified",name,len(physical_plans),flush=True)
    return metrics,calls,matches,paired

def assessments(pairs):
    groups=defaultdict(list)
    for p in pairs:
        groups[p["base"],p["other"],p["mode"]].append(p)
    out={}
    for key,ps in groups.items():
        counts=Counter(p["result"] for p in ps)
        rates=[p["saving_pct"] for p in ps if p["saving_pct"] is not None]
        out[key]=dict(base=key[0],other=key[1],mode=key[2],cases=len(ps),
            **{k:counts[k] for k in ("win","tie","loss","only_base","only_other","neither")},
            paired_SAFE=len(rates),mean_pct=mean(rates) if rates else None,median_pct=median(rates) if rates else None)
    return out

def decisions(groups):
    def coverage(g):
        return g["only_other"]-g["only_base"]
    def increment(A,B):
        f,t=(groups[A,B,mode] for mode in ("fixed","time"))
        return min(coverage(f),coverage(t))>=0 and (max(coverage(f),coverage(t))>0 or
                  (t["win"]>t["loss"] and f["win"]>=f["loss"]))
    # Verbatim inequalities of M1-e analyze.py's passed() applied to the new six.
    h_checks={}
    for A,mode,strict in (("NT","fixed",True),("NT","time",True),("C2","time",False)):
        g=groups[A,"HT",mode]
        h_checks[A+"_"+mode]=coverage(g)>=0 and (g["win"]>g["loss"] if strict else g["win"]>=g["loss"])
    simpler="NT" if increment("OT","NT") else "OT"
    keep_H=all(h_checks.values())
    selected="HT" if keep_H and increment(simpler,"HT") else simpler
    return dict(HT_original_conditions=h_checks,HT_original_pass=keep_H,
                NT_increment_over_OT=increment("OT","NT"),simpler_finalist=simpler,
                HT_increment_over_simpler=increment(simpler,"HT"),selected=selected)

def main():
    registration=read(DATA/"launch.json")
    assert registration["wrapper_sha256"]==sha(HERE/"run_holdout.py")
    assert registration["protocol_sha256"]==sha(HERE/"MECHANISM_PROTOCOL.md")
    assert registration["orders_file_sha256"]==sha(BASE/"holdout_freeze.json")
    audit=Counter(); metrics=[]; calls=[]; matches=[]; pairs=[]
    for case,order in cases():
        m,c,k,p=check_case(case,order,audit)
        metrics.extend(m); calls.extend(c); matches.extend(k); pairs.extend(p)
    assert len(metrics)==78 and len([r for r in metrics if r["mode"]=="fixed"])==42
    assert all(r["completed"]==4 for r in metrics if r["mode"]=="fixed")
    assert len(pairs)==132
    counts=assessments(pairs)
    for name,rows in (("results.csv",metrics),("certifications.csv",calls),("same_parent.csv",matches),
                      ("paired.csv",pairs),("mechanisms.csv",list(counts.values()))):
        write_csv(name,rows)
    frozen.p1.put(DATA/"decision.json",decisions(counts))
    frozen.p1.put(DATA/"verification.json",dict(audit,inputs=6,independent_runs=42,fixed_rows=42,
                  time_rows=36,actual_certifications=len(calls),pair_rows=len(pairs)))
if __name__=="__main__":
    main()
