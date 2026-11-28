"""After all clocks stop, verify every delivery, replay each distinct schedule and losslessly pack it."""
import csv
import gzip
import hashlib
import inspect
import json
import os
import platform
import shutil
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from types import SimpleNamespace

from importlib.util import module_from_spec,spec_from_file_location
from pathlib import Path
spec=spec_from_file_location("integrated_trial",Path(__file__).with_name("trial.py"))
t=module_from_spec(spec)
spec.loader.exec_module(t)
CASES,HERE,FIRST,ROOT,v1,np=t.CASES,t.HERE,t.FIRST,t.ROOT,t.v1,t.np
sys.path.insert(0,str(v1.S/"driver/ch3_integrated_quality_v1"))
import evidence


def load_helpers():
    # The old collection module imports its local run binding. Keep it isolated from solver imports.
    path=FIRST/"collect.py"
    src=path.read_text().replace("from run import HERE,S","")
    ns=dict(__name__="frozen_collection",HERE=HERE,S=ROOT)
    exec(compile(src,str(path),"exec"),ns)
    return SimpleNamespace(**ns)


util=load_helpers()


def csv_out(path,rows):
    assert rows
    with path.open("w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,list(dict.fromkeys(k for row in rows for k in row)),lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def hash_bytes(b):
    return hashlib.sha256(b).hexdigest()


def verify_flow(job):
    case,cpu=job
    started=time.process_time()
    v=v1.initialize(cpu)
    m=v.m
    obj=next(o for o in m.u2.CASES if m.label(o)==case)
    baseline,_=m.build(obj,ROOT/"offline"/case)
    # Reuse an already completed post-clock cold replay on a collection restart.
    # Its files live outside the formal runs; each is checked against the timed outputs below.
    dest=HERE/"results"/case
    dest.mkdir(exist_ok=True,parents=True)
    reg=(v1.S/"nt/research/m1i_generalization/registration/inputs"/obj["input"]).read_bytes()
    assert hash_bytes(reg)==obj["input_sha256"]
    rows,points,phases,layer_rows=[],[],[],[]
    known={}
    late=0
    cells=sorted((ROOT/"raw"/case).glob("r*"))
    assert len(cells)==12
    for d in cells:
        rep,arm,cap=d.name.split("-")
        cap=int(cap)
        rep=int(rep[1:])
        rc=util.read(d/"receipt.json")
        assert rc["cpu"]==cpu and rc["variant"]==arm and rc["method"]=="O" and rc["cap"]==cap
        records={s:util.logs(d/(s+".jsonl")) for s in ("search","refine")}
        assert next(x["request_sha"] for x in records["search"] if "request_sha" in x)==obj["input_sha256"]
        meta=dict(case=case,arm=arm,cap=cap,rep=rep)
        incumbent=None
        seed=None
        first=None
        final=None
        mapid=None
        source=None
        good=hot=0
        for s,events in records.items():
            for e in events:
                if e["event"]!="certificate":continue
                if e["t"]>cap:
                    late+=1
                    continue
                pt=e["point"]
                stage="search/physical" if s=="search" else e["stage"]
                folder=d/stage/"evidence"/obj["case"]/pt["plan"]
                planbytes=(folder/"plan.json").read_bytes()
                assert hash_bytes(planbytes.strip())==pt["plan"]
                plan=json.loads(planbytes)
                cert=util.read(folder/"certificate.json")
                assert m.endpoint(cert)==pt
                cert.pop("cert_s")
                with np.load(folder/"trace.npz") as data:
                    tr=data["events"]
                    assert tr.shape[1]==31 and tr[0,0]==0 and tr[-1,1]==obj["horizon_ticks"]
                    tracehash=hash_bytes(tr.tobytes())
                if pt["plan"] not in known:
                    disk=baseline.out/"evidence"/obj["case"]/pt["plan"]
                    if (disk/"trace.npz").exists():
                        assert hash_bytes((disk/"plan.json").read_bytes().strip())==pt["plan"]
                        cold=util.read(disk/"certificate.json")
                        with np.load(disk/"trace.npz") as data:cold_trace=data["events"]
                    else:
                        cfg=m.genes(plan)
                        r=baseline.replay(cfg)
                        assert r is not None
                        cold,cold_trace=baseline.cert(cfg,r)
                        cold=json.loads(m.raw(cold))
                    del cold["cert_s"]
                    assert cold["plan_sha256"]==pt["plan"]
                    known[pt["plan"]]=(hash_bytes(m.raw(cold)),hash_bytes(cold_trace.tobytes()))
                assert known[pt["plan"]]==(hash_bytes(m.raw(cert)),tracehash)
                hot+=pt["status"]=="HOT"
                if util.strict(pt,incumbent):
                    assert cert["metrics"]["min_deadline_slack_ms"]>=0 and max(cert["metrics"]["peak_hi"])<=80
                    incumbent=pt
                    if first is None:first=e["t"]
                    final=e["t"]
                    mapid=hash_bytes(bytes(a[0] for a in plan["rows"][1::3]))
                    source=stage
                    points.append(dict(**meta,t=e["t"],upper=pt["bounds"][1],J=pt["J"],plan=pt["plan"]))
                good+=1
                if s=="search" and util.strict(pt,seed):seed=pt
        sx=min(rc["charged"],rc["search"]["supervisor_t"],cap-3 if rc["post"] else cap)
        terms=[]
        for info in rc["resources"]:
            stage=info["stage"]
            events=util.logs(d/(stage+"-integrals.jsonl"))
            for i,e in enumerate(events):
                assert e["ordinal"]==i and 0<=e["reused"]<=e["events"]
                if i==0 or arm=="C1":assert e["reused"]==0
                assert e["source"] is None or 0<=e["source"]<i
            counts=Counter()
            for e in events:
                for k in ("events","reused","integrate","identity","checkpoint"):counts[k]+=e.get(k,0)
            cert_s=util.spans(records[stage],"search_cert" if stage=="search" else "dp_cert",sx if stage=="search" else rc["charged"])
            ncert=sum(e["event"]=="certificate" and e["t"]<=cap for e in records[stage])
            assert len(events)>=ncert
            row=dict(**meta,stage=stage,cpu_s=info["cpu_s"],rss_KiB=info["rss_KiB"],integrals=len(events),
                     delivered=ncert,cert_s=cert_s,cache_bytes=max((e["cache_bytes"] for e in events),default=0),
                     **{k:counts[k] for k in ("events","reused","integrate","identity","checkpoint")})
            phases.append(row)
            terms.append(row)
        snaps={(x["width"],x["layer"]):x for x in util.logs(d/"layers.jsonl")}
        for x in snaps.values():layer_rows.append(dict(**meta,**x))
        chosen=next((e for e in records["refine"] if e["event"]=="end" and e.get("task")=="selection"),{})
        assert len(chosen.get("seeds",[]))<=4
        rows.append(dict(**meta,success=int(incumbent is not None),first_s=first,last_s=final,
            J=incumbent["J"] if incumbent else None,lo=incumbent["bounds"][0] if incumbent else None,
            hi=incumbent["bounds"][1] if incumbent else None,plan=incumbent["plan"] if incumbent else None,
            peak_hi=incumbent["peak"] if incumbent else None,slack_ms=incumbent["slack"] if incumbent else None,
            mapping=mapid,source=source,seed_J=seed["J"] if seed else None,nominated=len(chosen.get("seeds",[])),
            hot_started=sum(e["event"]=="map_start" and e["kind"]=="HOT" for e in records["refine"]),
            slots=sum(x.get("slots",0) for x in snaps.values()),predictions=sum(x.get("predict",0) for x in snaps.values()),
            widths="/".join(map(str,sorted({w for w,_ in snaps}))),certs=good,hot=hot,
            charged=rc["charged"],wall=rc["wall"],origin=rc["origin"],cpu=cpu,
            cpu_s=rc["parent_cpu_s"]+sum(x["cpu_s"] for x in terms),rss_KiB=max(x["rss_KiB"] for x in terms),
            cache_bytes=max(x["cache_bytes"] for x in terms),
            **{k:sum(x[k] for x in terms) for k in ("events","reused","integrate","identity","checkpoint","cert_s")}))
        for p in [d/"receipt.json",*d.glob("*.jsonl"),*d.glob("map*/events.jsonl")]:
            output=dest/d.name/p.relative_to(d)
            output.parent.mkdir(parents=True,exist_ok=True)
            output.with_suffix(output.suffix+".gz").write_bytes(gzip.compress(p.read_bytes(),5,mtime=0))
    if (dest/"physical/index.json").exists():
        evidence.verify(dest/"physical")
    else:
        util.pack(case,dest/"physical",obj["case"])
    ix=util.read(dest/"physical/index.json")
    assert set(ix["plans"])==set(known)
    assert all(ix["plans"][k]["trace_sha"]==h[1] for k,h in known.items())
    print("verified",case,len(known),flush=True)
    return rows,points,phases,layer_rows,dict(case=case,distinct=len(known),late=late,offline_cpu=time.process_time()-started)


def main():
    assert len(list((ROOT/"raw").glob("*/*/receipt.json")))==144
    cpus=sorted(os.sched_getaffinity(0))[::2][:6]
    out=HERE/"tables"
    out.mkdir(exist_ok=True)
    from analyze import verify_sources
    from importlib.metadata import version
    checked=verify_sources(v1.S)
    with ProcessPoolExecutor(6) as pool:
        groups=list(pool.map(verify_flow,[(k,cpus[i%6]) for i,k in enumerate(CASES)]))
    all_rows=[r for g in groups for r in g[0]]
    assert len({(r["case"],r["arm"],r["cap"],r["rep"]) for r in all_rows})==144
    assert sum(r["cap"] for r in all_rows)==2160 and sum(r["charged"] for r in all_rows)<=2160
    for cpu in cpus:
        lane=sorted((r["origin"],r["origin"]+r["wall"]) for r in all_rows if r["cpu"]==cpu)
        assert all(a[1]<=b[0] for a,b in zip(lane,lane[1:]))
    objlist=util.read(v1.S/"nt/research/m1i_generalization/registration/cases.json")["cases"]
    for case in CASES:
        i=next(o["index"] for o in objlist if o["ambient"]==35 and o["case"].split("_")[0]==case)
        expected=[]
        for rep in range(1,4):
            for cap in ((10,20) if (i+rep)%2 else (20,10)):
                arms=("C1","C2") if (i+rep+cap//10)%2 else ("C2","C1")
                expected.extend((rep,cap,arm) for arm in arms)
        observed=sorted((r for r in all_rows if r["case"]==case),key=lambda r:r["origin"])
        assert [(r["rep"],r["cap"],r["arm"]) for r in observed]==expected
    for i,name in enumerate(("cells","improvements","phases","layers")):
        csv_out(out/(name+".csv"),[r for g in groups for r in g[i]])
    csv_out(out/"verification.csv",[g[4] for g in groups])
    shutil.copyfile(ROOT/"regression.json",out/"hot_recovery.json")
    t.write_json(out/"execution.json",dict(physical_cores=cpus,runtime=platform.platform(),python=platform.python_version(),
            packages={p:version(p) for p in ("numpy","scipy","numba","llvmlite")},source_blobs=checked,
            formal_cpu_s=sum(r["cpu_s"] for r in all_rows),charged_s=sum(r["charged"] for r in all_rows),
            nominal_s=sum(r["cap"] for r in all_rows),strict_cpu_budget_met=sum(r["cpu_s"] for r in all_rows)<=2160,
            child_cpu_s=sum(p["cpu_s"] for g in groups for p in g[2]),
            supervised_wall_s=sum(r["wall"] for r in all_rows),final_collection_cpu_s=sum(g[4]["offline_cpu"] for g in groups)))


if __name__=="__main__":
    main()
