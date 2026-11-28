"""Collect each cutoff-safe delivery, validate physical identities, and pack lossless traces."""
import csv,gzip,hashlib,inspect,json,os,shutil,statistics as st,sys
from collections import Counter,defaultdict
from pathlib import Path
from run import HERE,S
sys.path.insert(0,str(S/"driver/ch3_integrated_quality_v1"))
import evidence
import numpy as np
def read(p):return json.loads(p.read_bytes())
def as_csv(p,rows):
    with p.open("w",encoding="utf8",newline="") as h:
        wr=csv.DictWriter(h,fieldnames=list(dict.fromkeys(k for row in rows for k in row)));wr.writeheader();wr.writerows(rows)
def logs(p):
    return [json.loads(x) for x in p.read_bytes().splitlines() if x.endswith(b"}")] if p.exists() else []
def spans(events,task,stop):
    start=None;out=0.
    for e in events:
        if e["t"]>stop:continue
        if e.get("task")==task and e["event"]=="begin":start=e["t"]
        if start is not None and ((e.get("task")==task and e["event"]=="end") or (task=="search_cert" and e["event"]=="certificate") or (task=="refinement" and e["event"]=="stage_end")):
            out+=e["t"]-start;start=None
    return out+(max(0,stop-start) if start is not None else 0)
def strict(p,old):
    return p["status"]=="SAFE" and (old is None or p["bounds"][1]<old["bounds"][0])
def pack(k,target,label):
    func=inspect.getsource(evidence.pack).split("    # The original physical writers")[0]
    func=func.replace('ROOT/"archive"/case;target=lane/"physical";target.mkdir()','S/"raw"/case;target=output;target.mkdir(exist_ok=True)')
    func=func.replace('read(lane/"lane.json")["case"]','physical_label').replace('(rc["cut"] if filename=="search" else 60)','rc["cap"]')
    ns=dict(evidence.__dict__,S=S,output=target,physical_label=label);exec(func,ns);ns["pack"](k)
def collect():
    output=HERE/"results";output.mkdir(exist_ok=True);tab=HERE/"tables";tab.mkdir(exist_ok=True)
    ref=list(csv.DictReader((HERE.parent/"ch3_integrated_quality_v3/tables/runs.csv").open()))
    ref=[r for r in ref if r["arm"]=="hot"];assert len(ref)==36
    as_csv(tab/"reference60.csv",ref)
    labels={o["case"].split("_")[0]:o for o in read(S/"nt/research/m1i_generalization/registration/cases.json")["cases"] if o["ambient"]==35}
    rows=[];allpts={};layers=[];physical_n=0
    for k,o in labels.items():
        dest=output/k;dest.mkdir(exist_ok=True)
        for d in sorted((S/"raw"/k).glob("r*")):
            rc=read(d/"receipt.json");cap=rc["cap"];arm="B" if rc["method"]=="N" else "C";rep=int(d.name[1])
            sc=logs(d/"search.jsonl");rf=logs(d/"refine.jsonl")
            ev=[dict(e,source=stage) for stage,part in (("search",sc),("dp",rf)) for e in part if e["event"]=="certificate" and e["t"]<=cap]
            best=seed=None;curve=[];winner=None;first=None
            for e in ev:
                pt=e["point"]
                if e["source"]=="search" and strict(pt,seed):seed=pt
                if strict(pt,best):
                    best=pt;winner=e
                    if first is None:first=e["t"]
                    curve.append((e["t"],pt["bounds"][1]))
            selected=next((e for e in rf if e.get("task")=="selection" and e["event"]=="end"),{})
            assert len(selected.get("seeds",[]))<=4
            mapid=None;source=None;local_gain=None
            if best:
                assert best["peak"]<=80 and best["slack"]>=0
                stage="search/physical" if winner["source"]=="search" else winner["stage"]
                dirp=d/stage/"evidence"/o["case"]/best["plan"];plan=read(dirp/"plan.json")
                mapid=hashlib.sha256(bytes(v[0] for v in plan["rows"][1::3])).hexdigest()
                source=stage
                if winner["source"]=="dp":
                    tag=next(e for e in rf if e["event"]=="map_start" and e["rank"]==winner["rank"])
                    seedp=next(e["point"] for e in ev if e["point"]["plan"]==tag["seed"])
                    local_gain=seedp["J"]-best["J"] if seedp["status"]=="SAFE" else None
            prefix=dict(case=k,arm=arm,cap=cap,rep=rep)
            last={}
            for e in logs(d/"layers.jsonl"):last[e["width"],e["layer"]]=e
            sums=Counter();widths=[]
            for (w,j),e in last.items():
                layers.append(dict(**prefix,width=w,layer=j,parents=e["parents"],finished=e["complete"],legal=e["legal"],
                    **{n:e.get(n,0) for n in ("slots","groups","predict","fifo_calls","pilot_fifo_calls","generator_s","calibration_s","fifo_s","pilot_fifo_s","heat_s")}))
                sums.update({n:e.get(n,0) for n in ("slots","predict","generator_s","calibration_s","fifo_s","pilot_fifo_s","heat_s")})
                if w not in widths:widths.append(w)
            sx=min(rc["charged"],rc["search"]["supervisor_t"],cap-3 if rc["post"] else cap)
            dp=[e for file in d.glob("map*/events.jsonl") for e in logs(file) if e["kind"]=="dp" and e["t"]<=cap]
            rows.append(dict(**prefix,safe=int(best is not None),first_safe_s=first,best_s=winner["t"] if winner else None,
                total_s=rc["charged"],supervised_s=rc["wall"],core=rc["cpu"],J=best["J"] if best else None,
                upper=best["bounds"][1] if best else None,lower=best["bounds"][0] if best else None,
                peak=best["peak"] if best else None,slack_ms=best["slack"] if best else None,
                final_plan=best["plan"] if best else None,final_mapping_sha256=mapid,final_source=source,
                rank=winner.get("rank") if winner else None,nominated=len(selected.get("seeds",[])),dp_calls=len(dp),
                construction_best_J=seed["J"] if seed else None,global_dp_gain_J=seed["J"]-best["J"] if best else None,
                within_winning_safe_map_gain_J=local_gain,widths="/".join(map(str,widths)),cert_count=len(ev),
                build_s=spans(sc,"construct",sx),search_cert_s=spans(sc,"search_cert",sx),selection_s=spans(rf,"selection",cap),
                handoff_s=spans(rf,"handoff",rc["charged"]),dp_returned_s=sum(e["elapsed_s"] for e in dp),
                refinement_inclusive_s=spans(rf,"refinement",rc["charged"]),dp_cert_s=spans(rf,"dp_cert",rc["charged"]),**sums))
            allpts[k,arm,cap,rep]=curve
            child=dest/d.name;child.mkdir(exist_ok=True)
            for p in [d/"receipt.json",d/"search.jsonl",d/"refine.jsonl",d/"layers.jsonl",*d.glob("map*/events.jsonl")]:
                if p.exists():
                    out=child/p.relative_to(d);out.parent.mkdir(exist_ok=True);out.with_suffix(out.suffix+".gz").write_bytes(gzip.compress(p.read_bytes(),5,mtime=0))
        pack(k,dest/"physical",o["case"]);physical_n+=len(read(dest/"physical/index.json")["plans"])
        print("verified",k,flush=True)
    assert len(allpts)==len(rows)==144
    as_csv(tab/"cells.csv",rows);as_csv(tab/"layers.csv",layers)
    paired=[]
    for r in rows:
        if r["arm"]!="B":continue
        k,cap,rep=r["case"],r["cap"],r["rep"]
        l,h=[allpts[k,m,cap,rep] for m in "BC"]
        def meet(a,target):return next((t for t,v in a if v<=target+1e-12),None)
        target=max(l[-1][1],h[-1][1]) if l and h else None
        paired.append(dict(case=k,cap=cap,rep=rep,common_upper=target,
                           B_s=meet(l,target) if target else None,C_s=meet(h,target) if target else None,
                           C_meets_B_s=meet(h,l[-1][1]) if l else None,B_meets_C_s=meet(l,h[-1][1]) if h else None))
    as_csv(tab/"matched_quality.csv",paired)
    flow=[]
    for k in labels:
        a=st.median(float(z["J"]) for z in ref if z["case"]==k)
        for cap in (10,20):
            r=dict(case=k,cap=cap,A60_J=a)
            for arm in "BC":
                v=[x for x in rows if (x["case"],x["cap"],x["arm"])==(k,cap,arm) and x["safe"]]
                med=st.median(x["J"] for x in v) if v else None
                r.update({arm+"_n":len(v),arm+"_J":med,arm+"_loss_pct":(med/a-1)*100 if v else None})
            r["C_minus_B_J"]=r["C_J"]-r["B_J"] if r["C_n"] and r["B_n"] else None
            flow.append(r)
    as_csv(tab/"flows.csv",flow)
    fixed=[]
    for p in sorted((S/"fixed").glob("*/*/layers.jsonl")):
        e=logs(p)[-1];rep,arm=p.parent.name.split("-")
        fixed.append(dict(case=p.parent.parent.name,rep=rep,arm={"N":"B","O":"C"}[arm],**e))
    assert len(fixed)==16
    as_csv(tab/"fixed_work.csv",fixed)
    (tab/"inventory.json").write_text(json.dumps(dict(cells=len(rows),unique_physical=physical_n,layer_rows=len(layers),fixed=len(fixed)))+"\n")
if __name__=="__main__":collect()
