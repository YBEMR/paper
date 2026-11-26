"""Verify physical evidence and publish the entire anytime staircase and three cuts."""
import base64
import csv
import gzip
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from statistics import mean,median
import numpy as np
from long_run import ROOT, OUT, METHODS, inputs

DEST=ROOT/"data/quality"
CUTS=(10,30,60)
def read(path):return json.loads(path.read_bytes())
def write(name,rows):
    with (DEST/name).open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n");w.writeheader();w.writerows(rows)
def sha(b):return hashlib.sha256(b).hexdigest()

def verify(data,tag,case,n,rec,meta,certout):
    cert=rec["cert"];m=cert["metrics"];plan=cert["plan_sha256"]
    if plan not in meta:
        folder=data/"physical/evidence"/case/plan
        payload=(folder/"plan.json").read_bytes().strip()
        assert sha(payload)==plan
        obj=json.loads(payload);assert obj["case"]==case and len(obj["rows"])==3*n
        cfg=bytes(k+(10 if u==3 else 0) for u,k,t in obj["rows"][1::3])
        assert sha(cfg)==rec["id"]
        rawcert=read(folder/"certificate.json")
        with np.load(folder/"trace.npz",allow_pickle=False) as z: arr=z["events"]
        assert arr.shape[1]==31 and arr[0,0]==0 and arr[-1,1]==n//80*10000+3010
        assert np.array_equal(arr[1:,0],arr[:-1,1]) and np.all(arr[:,1]>arr[:,0])
        assert np.max(abs(arr[1:,14:18]-arr[:-1,18:22]))<1e-10
        assert abs(arr[:,26:30].sum()+m["external_J"]-m["E_J"])<1e-8
        assert max(abs(arr[:,22:26].max(axis=0)-m["peak_hi"]))<1e-7
        assert m["min_deadline_slack_ms"]>=0 and m["E_bounds"][0]<=m["E_J"]<=m["E_bounds"][1]
        if m["status"]=="SAFE":assert max(m["peak_hi"])<=80 and min(m["minimum_lo"])>=20
        assert abs(m["temperature_J"]+cert["E35_J"]-m["E_J"])<1e-8
        key=sha(json.dumps({k:v for k,v in rawcert.items() if k!="cert_s"},sort_keys=True).encode())
        meta[plan]=(key,sha(cfg))
        certout.write(json.dumps(dict(case=case,plan=plan,config_b64=base64.b64encode(cfg).decode(),
                physical_certificate=rawcert,event_array_sha256=sha(arr.tobytes(order="C")),shape=arr.shape),separators=(",",":"))+"\n")
    other=sha(json.dumps({k:v for k,v in cert.items() if k!="cert_s"},sort_keys=True).encode())
    assert meta[plan]==(other,rec["id"])

def main():
    DEST.mkdir(parents=True,exist_ok=True)
    allcalls=[];marks=[];steps=[];phases=[];totalplans=0;lanes=[]
    for lane in range(7):
        d=read(OUT/f"lane{lane}/data/setup.json");assert d["lane"]==lane
        lanes.append(d)
    assert len({d["core"] for d in lanes})==7
    assert {d["protocol_sha256"] for d in lanes}=={sha((ROOT/"PROTOCOL.md").read_bytes())}
    (DEST/"environment.json").write_text(json.dumps(lanes,indent=2)+"\n")
    for i,(phase,src) in enumerate(inputs()):
        case=src.stem;size=int(case[1:].split("_")[0]); lane=i%7
        data=OUT/f"lane{lane}/data";meta={}
        assert (data/"validation_inputs"/src.name).read_bytes().splitlines()==src.read_bytes().splitlines()
        with gzip.open(DEST/(case+"_certificates.jsonl.gz"),"wt",encoding="utf8") as certout:
            for method in METHODS:
                run=read(data/"runs"/case/method/"run.json")
                rr=run["records"]; assert run["budget_s"]==60. and run["wall_s"]>=60.
                assert all(a["end_s"]<=b["start_s"] for a,b in zip(rr,rr[1:]))
                assert len({r["id"] for r in rr})==len(rr)
                best=None;changes=[]
                for s in run["stages"]:
                    phases.append(dict(case=case,method=method,**s))
                for k,r in enumerate(rr,1):
                    verify(data,phase,case,size,r,meta,certout)
                    cert=r["cert"];m=cert["metrics"];tm=r["end_s"]
                    changed=m["status"]=="SAFE" and (best is None or m["E_J"]<best["cert"]["metrics"]["E_J"])
                    if changed and tm<=60:
                        best=r;changes.append((k,r))
                        steps.append(dict(phase=phase,case=case,method=method,t_s=tm,call=k,width=r["width"],
                            plan=cert["plan_sha256"],E_J=m["E_J"],peak_C=max(m["peak_hi"])))
                    allcalls.append(dict(phase=phase,case=case,method=method,call=k,width=r["width"],rank=r["rank"],
                        start_s=r["start_s"],end_s=tm,cert_s=r["cert_s"],cert_compute_s=cert["cert_s"],on_time=tm<=60,
                        config=r["id"],plan=cert["plan_sha256"],status=m["status"],E_J=m["E_J"],lo=m["E_bounds"][0],hi=m["E_bounds"][1],
                        peak_C=max(m["peak_hi"]),min_slack_ms=m["min_deadline_slack_ms"],pred_peak_C=r["prediction"],
                        incumbent_J=best["cert"]["metrics"]["E_J"] if best else None))
                for t in CUTS:
                    done=[r for r in rr if r["end_s"]<=t]
                    gained=[(k,r) for k,r in changes if r["end_s"]<=t]
                    b=gained[-1][1] if gained else {};cert=b.get("cert",{}); m=cert.get("metrics",{})
                    def span(a,b):return max(0.,min(t,b)-a)
                    build=sum(span(s["ready_s"]-s["build_s"],s["ready_s"]) for s in run["stages"])
                    ct=sum(span(r["start_s"],r["end_s"]) for r in rr)
                    assert build+ct<=t+1e-7
                    marks.append(dict(phase=phase,case=case,method=method,budget_s=t,requests=size,
                        completed=len(done),SAFE=sum(r["cert"]["metrics"]["status"]=="SAFE" for r in done),
                        first_SAFE_s=gained[0][1]["end_s"] if gained else None,best_at_s=b.get("end_s"),
                        best_call=gained[-1][0] if gained else None,improvements=len(gained),
                        SAFE_J=m.get("E_J"),lo=m.get("E_bounds",[None,None])[0],hi=m.get("E_bounds",[None,None])[1],
                        peak_C=max(m["peak_hi"]) if m else None,min_slack_ms=m.get("min_deadline_slack_ms"),
                        plan=cert.get("plan_sha256"),best_width=b.get("width"),build_sort_s=build,cert_write_s=ct,
                        other_s=t-build-ct,ready_widths="/".join(str(s["width"]) for s in run["stages"] if s["terminal"] and s["ready_s"]<=t),
                        actual_stop_s=run["wall_s"],stop=run["stop"]))
        totalplans+=len(meta)
        print("quality audit",case,len(meta),flush=True)
    write("checkpoints.csv",marks);write("improvements.csv",steps);write("stages.csv",phases)
    with gzip.open(DEST/"all_calls.csv.gz","wt",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(allcalls[0]),lineterminator="\n");w.writeheader();w.writerows(allcalls)
    pairs=[];stats=[]
    lookup={(r["case"],r["method"],r["budget_s"]):r for r in marks}
    for phase,src in inputs():
        for t in CUTS:
            nt=lookup[src.stem,"NT",t]
            for base in ("NC","OT","C2"):
                b=lookup[src.stem,base,t];a,e=b["SAFE_J"],nt["SAFE_J"]
                if a is None or e is None:
                    verdict="neither" if a is e else "only_NT" if a is None else "only_base";pct=None
                else:
                    verdict="win" if nt["hi"]<b["lo"] else "loss" if b["hi"]<nt["lo"] else "tie"
                    pct=100*(a-e)/a
                pairs.append(dict(phase=phase,case=src.stem,budget_s=t,base=base,base_SAFE_J=a,NT_SAFE_J=e,result=verdict,saving_pct=pct))
    for group in ("all","development8","former_holdout6"):
        for base in ("NC","OT","C2"):
            for t in CUTS:
                ps=[p for p in pairs if p["base"]==base and p["budget_s"]==t and (group=="all" or p["phase"]==group)]
                ct=Counter(p["result"] for p in ps)
                rates=[p["saving_pct"] for p in ps if p["saving_pct"] is not None]
                stats.append(dict(sample=group,base=base,budget_s=t,**{v:ct[v] for v in ("win","tie","loss","only_NT","only_base","neither")},
                                  paired=len(rates),mean_saving_pct=mean(rates) if rates else None,median_saving_pct=median(rates) if rates else None))
    write("paired.csv",pairs);write("summary.csv",stats)
    (DEST/"audit.json").write_text(json.dumps(dict(runs=56,checkpoints=len(marks),actual_calls=len(allcalls),timely_calls=sum(r["on_time"] for r in allcalls),
                              unique_case_plans=totalplans,incumbent_updates=len(steps)),indent=2)+"\n")
if __name__=="__main__":main()
