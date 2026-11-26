"""Summarize certified anytime incumbents, with three timing repeats per case."""
import csv
import gzip
import itertools
import json
import statistics
from collections import Counter
from pathlib import Path
from design import ROOT,REG,METHODS,write_json

DATA=ROOT/"data"
CUTS=("W4/K4","10s","30s","60s")
MED=statistics.median

def readcsv(path):
    with path.open(newline="") as f:return list(csv.DictReader(f))

def write(path,rows,fields=None):
    rows=list(rows)
    if fields is None:fields=list(rows[0])
    path.parent.mkdir(parents=True,exist_ok=True)
    op=gzip.open if path.suffix==".gz" else open
    with op(path,"wt",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator="\n");w.writeheader();w.writerows(rows)

def med(rows,key):
    values=[r[key] for r in rows if r[key] is not None]
    return MED(values) if values else None

def overlap(a,b,t):
    return max(0.,min(b,t)-a)

def one(c,slot,result):
    rr=result["records"];st=result["stages"];wall=result["wall_s"]
    assert result["case"]==c["case"] and result["method"]==slot["method"] and result["budget_s"]==60.
    assert all(r["start_s"]<60.001 for r in rr)
    assert all(a["end_s"]<=b["start_s"] for a,b in zip(rr,rr[1:]))
    assert wall>=60 or result["stop"]=="no_legal_pool"
    ctx=dict(group=c["group"],case=c["case"],flow=c["flow"],ambient=c["ambient"],requests=c["requests"],
             method=slot["method"],repeat=int(slot["repeat"]))
    calls=[];changes=[];marks=[]
    for i,r in enumerate(rr,1):
        m=r["cert"]["metrics"];en=m["E_J"];p=r["cert"]["plan_sha256"];end=r["end_s"]
        row=dict(**ctx,call=i,t_s=end,start_s=r["start_s"],width=r["width"],rank=r["rank"],config=r["id"],plan=p,
                 status=m["status"],E_J=en,lo=m["E_bounds"][0],hi=m["E_bounds"][1],
                 peak_C=max(m["peak_hi"]),slack_ms=m["min_deadline_slack_ms"],prediction_C=r["prediction"],
                 cert_write_s=r["cert_s"],continuous_s=r["cert"]["cert_s"],ontime=end<=60)
        calls.append(row)
        if end<=60 and m["status"]=="SAFE" and (not changes or en<changes[-1]["E_J"]):
            changes.append(row)
    for regime in CUTS:
        if regime=="W4/K4":
            complete=[r for r in calls if r["width"]==4 and r["ontime"]][:4]
            cut=(complete[-1]["t_s"] if len(complete)==4 else min(60,st[1]["start_s"] if len(st)>1 else wall))
        else:
            cut=float(regime[:-1]);complete=[r for r in calls if r["t_s"]<=cut]
        counts=Counter(r["status"] for r in complete)
        safe=[r for r in complete if r["status"]=="SAFE"]
        opt=min(safe,key=lambda r:r["E_J"]) if safe else {}
        build=sum(overlap(s["ready_s"]-s["build_s"],s["ready_s"],cut) for s in st)
        cert=sum(overlap(r["start_s"],r["t_s"],cut) for r in calls)
        used=min(wall,cut)
        assert build+cert<=used+1e-5
        outcome="SAFE" if safe else ("NO_LEGAL_POOL" if not complete and result["stop"]=="no_legal_pool" and wall<=cut else
                "NO_COMPLETED_CERT" if not complete else "+".join(sorted(counts)))
        marks.append(dict(**ctx,regime=regime,cut_s=cut,elapsed_s=used,wall_s=wall,outcome=outcome,stop=result["stop"],
                          last_window=st[-1]["last_window"]["window"],W4_terminal=st[0]["terminal"],certs=len(complete),
                          SAFE_calls=counts["SAFE"],HOT_calls=counts["HOT"],out_of_model=counts["OUT_OF_MODEL"],
                          unresolved=counts["UNRESOLVED"],min_cert_peak_C=min((r["peak_C"] for r in complete),default=None),
                          min_cert_slack_ms=min((r["slack_ms"] for r in complete),default=None),first_SAFE_s=safe[0]["t_s"] if safe else None,
                          SAFE_J=opt.get("E_J"),lo=opt.get("lo"),hi=opt.get("hi"),peak_C=opt.get("peak_C"),
                          slack_ms=opt.get("slack_ms"),plan=opt.get("plan"),best_at_s=opt.get("t_s"),best_width=opt.get("width"),
                          build_s=build,cert_write_s=cert,other_s=max(0,used-build-cert)))
    levels=[dict(**ctx,width=s["width"],start_s=s["start_s"],ready_s=s["ready_s"],build_s=s["build_s"],
                 terminal=s["terminal"],last_window=s["last_window"]["window"],complete=s["last_window"]["complete"],
                 proposals=sum(full["action_counts"].values()),valid=full["action_counts"].get("valid",0),
                 timing=full["action_counts"].get("timing",0),duplicate=full["action_counts"].get("duplicate",0))
            for s,full in zip(st,result["search"],strict=True)]
    return marks,calls,changes,levels

def compare(a,b,okay):
    if not (okay(a) and okay(b)):
        return ("only_left" if okay(a) else "only_right" if okay(b) else "neither"),None
    assert a["SAFE_J"] is not None and b["SAFE_J"] is not None
    result="win" if a["hi"]<b["lo"] else "loss" if b["hi"]<a["lo"] else "tie"
    return result,100*(b["SAFE_J"]-a["SAFE_J"])/b["SAFE_J"]

def pair_rows(rows,columns,okay):
    idx={tuple(r[k] for k in columns)+(r["method"],):r for r in rows}
    out=[]
    for common in dict.fromkeys(tuple(r[k] for k in columns) for r in rows):
        for a,b in itertools.combinations(METHODS,2):
            x,y=idx[common+(a,)],idx[common+(b,)]
            outcome,pct=compare(x,y,okay)
            out.append(dict(**dict(zip(columns,common)),left=a,right=b,left_E_J=x["SAFE_J"],right_E_J=y["SAFE_J"],
                            result=outcome,saving_pct=pct))
    return out

def main():
    cases=json.loads((REG/"cases.json").read_bytes())["cases"]
    rot=readcsv(REG/"rotation.csv")
    lookup={r["case"]:r for r in cases}
    marks=[];calls=[];changes=[];levels=[]
    for slot in rot:
        c=lookup[slot["case"]];tag=f"r{slot['repeat']}-{slot['method']}"
        f=DATA/"runs"/c["case"]/tag/"run.json.gz"
        if f.exists():
            result=json.loads(gzip.decompress(f.read_bytes()))
        else:
            import tarfile
            with tarfile.open(DATA/"evidence"/c["case"]/"runs.tar.xz") as tar:
                result=json.load(tar.extractfile(tag+"/run.json"))
        parts=one(c,slot,result)
        for acc,part in zip((marks,calls,changes,levels),parts):acc.extend(part)
    write(DATA/"repetitions.csv",marks);write(DATA/"calls.csv.gz",calls)
    write(DATA/"improvements.csv",changes);write(DATA/"stages.csv",levels)
    medians=[]
    for c,m,cut in itertools.product(cases,METHODS,CUTS):
        sub=[r for r in marks if (r["case"],r["method"],r["regime"])==(c["case"],m,cut)]
        assert len(sub)==3
        n=sum(r["SAFE_J"] is not None for r in sub)
        medians.append(dict(group=c["group"],case=c["case"],flow=c["flow"],ambient=c["ambient"],requests=c["requests"],
                            windows=c["windows"],method=m,regime=cut,n_SAFE=n,reliable=n>=2,
                            **{k:med(sub,k) for k in ("SAFE_J","lo","hi","peak_C","slack_ms","first_SAFE_s","best_at_s",
                                                      "min_cert_peak_C","min_cert_slack_ms","certs","SAFE_calls","elapsed_s","build_s","cert_write_s")}))
    write(DATA/"medians.csv",medians)
    cols=["group","case","flow","ambient","regime"]
    paired=pair_rows(medians,cols,lambda r:r["reliable"])
    write(DATA/"paired_cases.csv",paired)
    repeated=pair_rows(marks,cols+["repeat"],lambda r:r["SAFE_J"] is not None)
    write(DATA/"paired_repeats.csv",repeated)
    groups={"A":lambda r:r["group"]=="A","B":lambda r:r["group"]=="B","C":lambda r:r["group"]=="C",
            "ABC35":lambda r:r["ambient"]==35,"D25":lambda r:r["group"]=="D" and r["ambient"]==25,
            "D45":lambda r:r["group"]=="D" and r["ambient"]==45}
    counts=[];summary=[]
    for g,accept in groups.items():
        for cut in CUTS:
            for m in METHODS:
                sub=[x for x in medians if accept(x) and x["regime"]==cut and x["method"]==m]
                counts.append(dict(group=g,regime=cut,method=m,flows=len(sub),at_least_one=sum(x["n_SAFE"]>=1 for x in sub),
                            at_least_two=sum(x["n_SAFE"]>=2 for x in sub),all_three=sum(x["n_SAFE"]==3 for x in sub),
                            **{k:med(sub,k) for k in ("first_SAFE_s","certs","build_s","cert_write_s")}))
            for a,b in itertools.combinations(METHODS,2):
                sub=[x for x in paired if accept(x) and (x["regime"],x["left"],x["right"])==(cut,a,b)]
                cnt=Counter(x["result"] for x in sub)
                vals=[x["saving_pct"] for x in sub if x["saving_pct"] is not None]
                summary.append(dict(group=g,regime=cut,left=a,right=b,flows=len(sub),paired=len(vals),
                               **{k:cnt[k] for k in ("win","tie","loss","only_left","only_right","neither")},
                               mean_saving=statistics.mean(vals) if vals else None,median_saving=MED(vals) if vals else None))
    write(DATA/"group_coverage.csv",counts);write(DATA/"group_pairs.csv",summary)
    thermal=[];flows={c["flow"] for c in cases if c["group"]=="D"}
    for flow_id,m,cut in itertools.product(sorted(flows),METHODS,CUTS):
        sub={x["ambient"]:x for x in medians if (x["flow"],x["method"],x["regime"])==(flow_id,m,cut)}
        base=sub[35]
        for t,r in sorted(sub.items()):
            dE=r["SAFE_J"]-base["SAFE_J"] if r["reliable"] and base["reliable"] else None
            thermal.append(dict(flow=flow_id,windows=r["windows"],requests=r["requests"],method=m,regime=cut,ambient=t,
                          success=r["n_SAFE"],SAFE_J=r["SAFE_J"],peak_C=r["peak_C"],slack_ms=r["slack_ms"],first_SAFE_s=r["first_SAFE_s"],
                          delta_J_vs35=dE,delta_pct_vs35=(100*dE/base["SAFE_J"]) if dE is not None else None))
    write(DATA/"ambient_paired.csv",thermal)
    final=[r for r in marks if r["regime"]=="60s"]
    assert len(final)==192 and len(marks)==768 and len(medians)==256 and len(paired)==384 and len(repeated)==1152
    write_json(DATA/"batch_receipt.json",dict(runs=len(final),registered_core_s=60*len(final),
              measured_wall_sum_s=sum(r["wall_s"] for r in final),ranked_elapsed_s=sum(r["elapsed_s"] for r in final),
              ontime_certificates=sum(r["ontime"] for r in calls),issued_certificates=len(calls),incumbent_steps=len(changes),
              conditions=len(cases),independent_flows=len({i["flow"] for i in cases}),repeat_checkpoints=len(marks),
              fixed_under_four=sum(r["certs"]<4 for r in marks if r["regime"]=="W4/K4"),
              stops=dict(Counter(r["stop"] for r in final)),statuses=dict(Counter(r["status"] for r in calls)),
              ontime_statuses=dict(Counter(r["status"] for r in calls if r["ontime"]))))
if __name__=="__main__":main()
