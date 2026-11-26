"""Validate each issued certificate; preserve original plan/certificate JSON and measured run records."""
import argparse
import csv
import gzip
import hashlib
import json
import os
import shutil
import tarfile
from pathlib import Path
import numpy as np
from batch import ROOT,RAW
os.environ.setdefault("M1G_RAW",str(ROOT/"audit_work"))
from framework import METHODS,e,inputs
from pool_audit import dump

DATA=ROOT/"data"
CUTS=("W4/K4","10s","30s","60s")


def read(path):
    return json.loads(path.read_bytes())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def span(start,end,cut):
    return max(0.,min(cut,end)-start)


def case_evidence(index):
    phase,src=inputs()[index];case=src.stem;n=int(case.split("_")[0][1:])
    lane=RAW/f"lane{index%7}/engine"
    assert (lane/"validation_inputs"/src.name).read_bytes().splitlines()==src.read_bytes().splitlines()
    env=read(lane/"environment.json")
    assert env["protocol_sha256"]==sha((ROOT/"PROTOCOL.md").read_bytes())
    assert env["implementation_sha256"]==sha((ROOT/"framework.py").read_bytes())
    dest=DATA/"evidence"/case
    dest.mkdir(parents=True,exist_ok=True)
    outputs={key:[] for key in ("calls","improvements","checkpoints","stages","traces")}
    meta={}
    with tarfile.open(dest/"plans-and-certificates.tar.xz","w:xz",preset=2) as physical, tarfile.open(dest/"runs.tar.xz","w:xz",preset=2) as runs, tarfile.open(dest/"W4-search.tar","w") as searches:
        for method in METHODS:
            folder=lane/"runs"/case/method
            runs.add(folder/"run.json",arcname=method+"/run.json",recursive=False)
            searches.add(folder/"w4.json.gz",arcname=method+"/w4.json.gz",recursive=False)
            run=read(folder/"run.json")
            assert run["method"]==method and run["case"]==case and run["budget_s"]==60 and run["wall_s"]>=60
            rows=run["records"];stages=run["stages"]
            assert len(rows)>=4 and all(r["width"]==4 for r in rows[:4]) and [r["rank"] for r in rows[:4]]==[1,2,3,4]
            assert all(a["end_s"]<=b["start_s"] for a,b in zip(rows,rows[1:]))
            assert len({r["id"] for r in rows})==len(rows)
            for s in stages:
                outputs["stages"].append(dict(case=case,method=method,**s))
            changes=[];best=None
            for k,r in enumerate(rows,1):
                cert=r["cert"];m=cert["metrics"];pid=cert["plan_sha256"]
                if pid not in meta:
                    f=lane/"physical/evidence"/case/pid
                    body=(f/"plan.json").read_bytes()
                    assert sha(body.strip())==pid
                    plan=json.loads(body)
                    assert plan["case"]==case and len(plan["rows"])==3*n
                    cfg=bytes(k+(10 if u==3 else 0) for u,k,_ in plan["rows"][1::3])
                    original=read(f/"certificate.json")
                    assert original["plan_sha256"]==pid
                    with np.load(f/"trace.npz",allow_pickle=False) as z:
                        ar=z["events"]
                    assert ar.shape[1]==31 and ar[0,0]==0 and ar[-1,1]==n//80*10000+3010
                    assert np.all(ar[:,1]>ar[:,0]) and np.array_equal(ar[1:,0],ar[:-1,1])
                    assert np.max(np.abs(ar[1:,14:18]-ar[:-1,18:22]))<1e-10
                    assert np.max(np.abs(ar[:,22:26].max(axis=0)-m["peak_hi"]))<1e-7
                    assert abs(ar[:,26:30].sum()+m["external_J"]-m["E_J"])<1e-8
                    assert abs(original["E35_J"]+m["temperature_J"]-m["E_J"])<1e-8
                    assert m["min_deadline_slack_ms"]>=0 and m["E_bounds"][0]<=m["E_J"]<=m["E_bounds"][1]
                    if m["status"]=="SAFE":
                        assert max(m["peak_hi"])<=80 and min(m["minimum_lo"])>=20
                    signature=sha(e.p1.raw({k:v for k,v in original.items() if k!="cert_s"}))
                    meta[pid]=signature,sha(cfg)
                    for name in ("plan.json","certificate.json"):
                        physical.add(f/name,arcname=pid+"/"+name,recursive=False)
                    outputs["traces"].append(dict(case=case,plan=pid,rows=len(ar),columns=ar.shape[1],
                         plan_file_sha256=sha(body),certificate_file_sha256=sha((f/"certificate.json").read_bytes()),
                         event_array_sha256=sha(ar.tobytes()),npz_file_sha256=sha((f/"trace.npz").read_bytes())))
                assert meta[pid]==(sha(e.p1.raw({k:v for k,v in cert.items() if k!="cert_s"})),r["id"])
                t=r["end_s"]
                if t<=60 and m["status"]=="SAFE" and (best is None or m["E_J"]<best["cert"]["metrics"]["E_J"]):
                    best=r;changes.append((k,r))
                    outputs["improvements"].append(dict(phase=phase,case=case,method=method,t_s=t,call=k,width=r["width"],
                                               plan=pid,E_J=m["E_J"],peak_C=max(m["peak_hi"])))
                outputs["calls"].append(dict(case=case,method=method,call=k,width=r["width"],rank=r["rank"],start_s=r["start_s"],
                    end_s=t,cert_write_s=r["cert_s"],continuous_s=cert["cert_s"],on_time=t<=60,plan=pid,
                    config=r["id"],status=m["status"],E_J=m["E_J"],lo=m["E_bounds"][0],hi=m["E_bounds"][1],
                    peak_C=max(m["peak_hi"]),slack_ms=m["min_deadline_slack_ms"],prediction=r["prediction"]))
            for regime in CUTS:
                fixed=regime=="W4/K4"
                t=rows[3]["end_s"] if fixed else float(regime[:-1])
                done=rows[:4] if fixed else [r for r in rows if r["end_s"]<=t]
                safe=[r for r in done if r["cert"]["metrics"]["status"]=="SAFE"]
                opt=min(safe,key=lambda r:r["cert"]["metrics"]["E_J"]) if safe else {}
                cert=opt.get("cert",{});metrics=cert.get("metrics",{})
                build=sum(span(s["ready_s"]-s["build_s"],s["ready_s"],t) for s in stages)
                ct=sum(span(r["start_s"],r["end_s"],t) for r in rows)
                assert build+ct<=t+1e-6
                outputs["checkpoints"].append(dict(phase=phase,case=case,method=method,regime=regime,elapsed_s=t,actual_stop_s=run["wall_s"],
                    stop_reason=run["stop"],completed=len(done),SAFE=len(safe),first_SAFE_s=safe[0]["end_s"] if safe else None,
                    SAFE_J=metrics.get("E_J"),lo=metrics.get("E_bounds",[None,None])[0],hi=metrics.get("E_bounds",[None,None])[1],
                    peak_C=max(metrics["peak_hi"]) if metrics else None,slack_ms=metrics.get("min_deadline_slack_ms"),
                    plan=cert.get("plan_sha256"),best_at_s=opt.get("end_s"),best_width=opt.get("width"),
                    build_sort_s=build,cert_write_s=ct,other_s=t-build-ct,
                    improvements=sum(r["end_s"]<=t for _,r in changes),terminal_W4=stages[0]["terminal"],
                    ready_widths="/".join(str(s["width"]) for s in stages if s["ready_s"]<=t and s["terminal"])))
    for name,rows in outputs.items():
        dump(dest/(name+".csv.gz"),rows)
    # Literal NPZ evidence for the four fixed certifications of every method and all anytime incumbents.
    selected=set(r["plan"] for r in outputs["calls"] if r["call"]<=4)
    selected.update(r["plan"] for r in outputs["improvements"])
    # Partition on complete NPZ members for convenient git transport and selective retrieval.
    chunk=0;size=0;tar=None
    try:
        for pid in sorted(selected):
            path=lane/"physical/evidence"/case/pid/"trace.npz"
            if tar is None or size+path.stat().st_size>1_800_000:
                if tar is not None:
                    tar.close()
                chunk+=1;size=0
                tar=tarfile.open(dest/f"selected-events-{chunk:02d}.tar","w")
            tar.add(path,arcname=pid+"/trace.npz",recursive=False)
            size+=path.stat().st_size
    finally:
        if tar is not None:
            tar.close()
    print("VERIFIED",case,len(meta),len(outputs["calls"]),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("index",type=int)
    case_evidence(p.parse_args().index)
