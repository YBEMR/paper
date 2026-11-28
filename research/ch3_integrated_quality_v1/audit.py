"""Audit physical receipts and compare the two complete methods; no scheduling calls."""
import csv
import hashlib
import json
import os
import statistics as st
import tarfile
import zlib
from pathlib import Path
from evidence import verify,logs,read
ROOT=Path(__file__).resolve().parent
ARC=ROOT/"archive";TAB=ROOT/"tables";ARMS=("original","integrated")
def csvout(n,rows):
    with (TAB/n).open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)),lineterminator="\n")
        w.writeheader();w.writerows(rows)
def safe(p):return p is not None and p["status"]=="SAFE"
def better(p,old):return safe(p) and (not safe(old) or p["bounds"][1]<old["bounds"][0])
def incumbent(events):
    winner=None
    for e in events:
        if better(e["point"],winner):winner=e["point"]
    return winner
def describe(p):
    if not p:return dict(status="NO_SAFE")
    return {k:v for k,v in p.items() if k not in ("energy","bounds")}|dict(lower=p["bounds"][0],upper=p["bounds"][1])|p["energy"]
def J(p):return p["J"] if p else None
def median(xs):return st.median(xs) if xs else None
def gain(a,b):return a["J"]-b["J"] if a and b else None
def outcome(left,right):
    if left is None or right is None:return "unpaired"
    return "win" if better(left,right) else "loss" if better(right,left) else "tie"
def summarize(points):
    vals=[p for p in points if safe(p)]
    if not vals:return None
    return dict(status="SAFE",J=median([p["J"] for p in vals]),
                bounds=[median([p["bounds"][k] for p in vals]) for k in (0,1)])
def spans(events,task,limit):
    start=None;total=0
    for e in events:
        if e["t"]>limit:continue
        if e["event"]=="begin" and e.get("task")==task:
            assert start is None;start=e["t"]
        if (e["event"]=="end" and e.get("task")==task) or (task=="search_cert" and e["event"]=="certificate") or (task=="refinement" and e["event"]=="stage_end"):
            if start is not None:total+=e["t"]-start;start=None
    if start is not None:total+=max(0,limit-start)
    return total
def certified_members(p):
    certs={}
    for f in sorted(p.glob("*.tar")):
        with tarfile.open(f,"r:") as t:
            for member in t:
                if member.name.endswith("/certificate"):
                    result=json.loads(zlib.decompress(t.extractfile(member).read()));certs[result["plan_sha256"]]=result
    return certs
def checked(pt,certs):
    d=certs[pt["plan"]];m=d["metrics"]
    assert (m["status"],m["E_J"],m["E_bounds"],d["E35_J"])==(pt["status"],pt["J"],pt["bounds"],pt["e35"])
    assert max(m["peak_hi"])==pt["peak"] and m["min_deadline_slack_ms"]==pt["slack"] and m["switch_count"]==pt["switches"]
    assert all(m[k]==v for k,v in pt["energy"].items())
    if safe(pt):assert pt["slack"]>=0 and pt["peak"]<=80
def main():
    TAB.mkdir(exist_ok=True);rows=[];stage_rows=[];receipts=[];flow_rows=[];rep_rows=[];hist=[];unique=0;coverage={a:0 for a in ARMS};points={}
    hdir=Path(os.environ["GEN"])/"research/m1i_generalization/data"
    with (hdir/"repetitions.csv").open() as f:
        history={(r["case"],int(r["repeat"])):r for r in csv.DictReader(f) if r["regime"]=="60s" and r["method"]=="NT" and r["ambient"]=="35"}
    assert len(history)==36
    for lane in sorted(ARC.glob("*/lane.json")):
        folder=lane.parent;code=folder.name;env=read(lane);label=env["case"]
        verify(folder/"physical");certs=certified_members(folder/"physical");unique+=len(certs)
        assert len(env["order"])==6 and len(set(map(tuple,env["order"])))==6
        assert all(env["order"][2*j][1]!=env["order"][2*j+1][1] for j in range(3))
        used=[]
        for rep,arm in env["order"]:
            path=folder/f"r{rep}-{arm}";rc=read(path/"receipt.json")
            assert rc["host"]==env["warm"]["host"] and rc["cpu"]==env["warm"]["core"] and rc["limit"]==60
            receipts.append(rc);used.append(rc["charged_s"]);assert used[-1]<=60
            cut=rc["cut"];sc=logs(path/"search.jsonl");rf=logs(path/"refine.jsonl")
            candidates=[e for e in sc if e["event"]=="certificate" and e["t"]<=cut]
            first=next((e for e in candidates if safe(e["point"])),None)
            seed=incumbent(candidates);p55=incumbent([e for e in candidates if e["t"]<=55]);current=seed
            assert cut==(55 if arm=="integrated" and first and first["t"]<55 else 60)
            raw_stages={};inc_stages={};when={}
            for e in candidates:checked(e["point"],certs)
            post=[e for e in rf if e["t"]<=60]
            if post:assert arm=="integrated" and cut==55 and first and post[0]["plan"]==seed["plan"]
            for tag in ("ordinary","thermal"):
                stage=[e for e in post if e.get("stage")==tag]
                q=next((e["point"] for e in stage if e["event"]=="certificate"),None)
                if q:
                    checked(q,certs)
                    if better(q,current):current=q
                ends=[e for e in stage if e["event"]=="stage_end"]
                if ends:assert ends[-1]["incumbent"]==current["plan"]
                raw_stages[tag]=q;inc_stages[tag]=current
                when[tag]=next((e["t"] for e in stage if e["event"]=="certificate"),ends[-1]["t"] if ends else None)
            end=rc["charged_s"];sx=min(cut,rc["search_rc"]["supervisor_t"])
            instance=spans(sc,"instance",sx);construct=spans(sc,"construct",sx);s_cert=spans(sc,"search_cert",sx)
            handoff=spans(rf,"handoff",end);p_cert=spans(rf,"dp_cert",end)
            costlog=logs(path/"events.jsonl");dps=[e for e in costlog if e["kind"]=="dp" and e["t"]<=end]
            dp=sum(e["elapsed_s"] for e in dps);other=end-instance-construct-s_cert-handoff-p_cert-dp
            assert other>=-.01,(code,arm,other)
            points[code,rep,arm]=current
            ctx=dict(case=code,rep=rep,version=arm)
            for tag,p,t in (("construction",seed,sx),("ordinary_raw",raw_stages["ordinary"],when["ordinary"]),
                            ("ordinary_incumbent",inc_stages["ordinary"],when["ordinary"]),("thermal_raw",raw_stages["thermal"],when["thermal"]),
                            ("thermal_incumbent",current,when["thermal"]),("final",current,end)):
                if arm=="original" and tag not in ("construction","final"):continue
                label_status="delivered" if t is not None else "stage_not_delivered"
                stage_rows.append(dict(**ctx,stage=tag,t=t,delivery=label_status,**describe(p)))
            all_deliveries=candidates+[e for e in post if e["event"]=="certificate"]
            def delivered(p,events):
                return next((e["t"] for e in events if p and e["point"]["plan"]==p["plan"]),None)
            row=dict(**ctx,first_safe_s=first["t"] if first else None,search_cut=cut,search_ended_s=sx,search_J=J(seed),
                construction_best_delivered_s=delivered(seed,candidates),final_best_delivered_s=delivered(current,all_deliveries),
                ordinary_delivery_s=when["ordinary"],thermal_delivery_s=when["thermal"],
                ordinary_raw_status=raw_stages["ordinary"]["status"] if raw_stages["ordinary"] else None,
                thermal_raw_status=raw_stages["thermal"]["status"] if raw_stages["thermal"] else None,
                at55_J=J(p55),ordinary_J=J(inc_stages["ordinary"]) if arm=="integrated" else None,thermal_J=J(current) if arm=="integrated" else None,
                ordinary_gain_J=gain(seed,inc_stages["ordinary"]) if arm=="integrated" else None,
                thermal_gain_J=gain(inc_stages["ordinary"],current) if arm=="integrated" else None,retained_J=J(current),
                ordinary_delivered=when["ordinary"] is not None,thermal_delivered=when["thermal"] is not None,
                search_certificates=len(candidates),dp_certificates=sum(p is not None for p in raw_stages.values()),dp_calls=len(dps),
                reserve_calls=sum(e["reserve"]==13 for e in dps),delivery_s=end,instance_s=instance,construct_s=construct,
                search_replay_cert_evidence_s=s_cert,handoff_s=handoff,dp_s=dp,refine_cert_evidence_s=p_cert,other_s=other,
                completed_cert_kernel_s=sum(e["kernel_s"] for e in candidates)+sum(e["kernel_s"] for e in post if e.get("task")=="dp_cert" and e["event"]=="end"),
                **describe(current))
            rows.append(row)
            if arm=="original":
                old=history[label,rep];hist.append(dict(case=code,rep=rep,old_60_J=old["SAFE_J"],old_best_at_s=old["best_at_s"],
                    old_hash=old["plan"],new_55_J=J(p55),new_60_J=J(current),native_55_to_60_gain_J=gain(p55,current),old_build_s=old["build_s"]))
        data={v:[points[code,i,v] for i in (1,2,3)] for v in ARMS}
        counts={v:sum(safe(p) for p in data[v]) for v in ARMS}
        med={v:summarize(data[v]) for v in ARMS}
        for v in ARMS:coverage[v]+=counts[v]>=2
        paired=all(n>=2 for n in counts.values());m0,m1=(med[a] for a in ARMS)
        flow=dict(case=code,requests_label=label,original_safe=counts["original"],integrated_safe=counts["integrated"],
                  original_J=J(m0),integrated_J=J(m1),strict=outcome(m1,m0) if paired else "unpaired",
                  gain_J=gain(m0,m1) if paired else None,gain_pct=100*gain(m0,m1)/m0["J"] if paired else None)
        for v in ARMS:
            flow[v+"_median_first_safe_s"]=median([r["first_safe_s"] for r in rows if r["case"]==code and r["version"]==v and r["first_safe_s"] is not None])
            flow[v+"_bounds"]=med[v]["bounds"] if med[v] else None
        flow_rows.append(flow)
        for i in (1,2,3):
            a,b=data["original"][i-1],data["integrated"][i-1]
            rep_rows.append(dict(case=code,rep=i,original_J=J(a),integrated_J=J(b),strict=outcome(b,a),gain_J=gain(a,b),
                gain_pct=100*gain(a,b)/a["J"] if a and b else None))
    assert len(rows)==72 and len(flow_rows)==12 and len(rep_rows)==36
    total=sum(r["charged_s"] for r in receipts);assert total<=4320
    common=[r for r in flow_rows if r["strict"]!="unpaired"]
    wins=sum(r["strict"]=="win" for r in common);avg=st.mean(r["gain_pct"] for r in common) if common else None
    adopt=bool(common and coverage["integrated"]>=coverage["original"] and avg>0 and wins>len(common)/2)
    summary=dict(cells=len(rows),physical=unique,charged_core_s=total,common=len(common),reliable=coverage,
        win=wins,tie=sum(r["strict"]=="tie" for r in common),loss=sum(r["strict"]=="loss" for r in common),
        mean_saving_pct=avg,mean_saving_J=st.mean(r["gain_J"] for r in common) if common else None,adopt=adopt,
        full_success={v:sum(r[v+"_safe"]==3 for r in flow_rows) for v in ARMS},
        warmed_s=sum(read(p)["warm"]["seconds"] for p in ARC.glob("*/lane.json")),
        offline_pack_s=sum(read(p)["offline_s"] for p in ARC.glob("*/archive_receipt.json")),
        preflight_s=read(ARC/"gate/gate.json")["wall_s"],source=receipts[0]["source"],run=receipts[0]["run"])
    decomposition=[]
    for r in rep_rows:
        c,i=r["case"],r["rep"]
        orig=next(v for v in rows if (v["case"],v["rep"],v["version"])==(c,i,"original"))
        inte=next(v for v in rows if (v["case"],v["rep"],v["version"])==(c,i,"integrated"))
        if orig["retained_J"] is None or inte["search_J"] is None:continue
        gap=orig["retained_J"]-inte["search_J"]
        a,b=inte["ordinary_gain_J"],inte["thermal_gain_J"]
        assert abs(gap+a+b-r["gain_J"])<1e-9
        decomposition.append(dict(case=c,rep=i,strict=r["strict"],original60_minus_integrated_search_J=gap,
            ordinary_gain_J=a,thermal_gain_J=b,net_gain_J=r["gain_J"],
            original_55_to_60_gain_J=orig["at55_J"]-orig["retained_J"] if orig["at55_J"] is not None else None))
    csvout("decomposition.csv",decomposition)
    (TAB/"decision.json").write_text(json.dumps(summary,indent=2)+"\n")
    csvout("runs.csv",rows);csvout("flows.csv",flow_rows);csvout("stages.csv",stage_rows);csvout("paired_repeats.csv",rep_rows)
    csvout("timing_receipts.csv",receipts);csvout("historical_diagnostic.csv",hist)
    print(summary)
if __name__=="__main__":main()
