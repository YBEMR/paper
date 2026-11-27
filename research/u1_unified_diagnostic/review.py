"""Offline diagnostics on the archived run. No method, constructor or solver is imported."""
import csv
import gzip
import hashlib
import json
import shutil
import tarfile
import tempfile
import zlib
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent
DEST=HERE/"results"
CODES=("A03","A06","C10","C12")
PRIMARY=("NT","Proposed","Q4")
def read(p): return json.loads(p.read_bytes())
def sha(b): return hashlib.sha256(b).hexdigest()
def write(name,rows,fields):
    with (DEST/name).open("w",newline="",encoding="utf-8") as fp:
        writer=csv.DictWriter(fp,fieldnames=fields,lineterminator="\n")
        writer.writeheader();writer.writerows(rows)

def review(work):
    archive=work/"physical.tar.gz"
    desc=read(DEST/"archive.json")
    total=hashlib.sha256()
    with archive.open("wb") as out:
        for entry in desc["parts"]:
            b=(DEST/entry["name"]).read_bytes()
            assert len(b)==entry["bytes"] and sha(b)==entry["sha256"]
            total.update(b);out.write(b)
    assert total.hexdigest()==desc["archive_sha256"]
    with tarfile.open(archive,"r:gz") as tar:
        tar.extractall(work,filter="data")
    root=work/"evidence"
    index={r["path"]:r for r in read(root/"event_index.json")}
    verified=set()
    written_traces=set()
    for name,r in index.items():
        if "partial" in r:continue
        h=hashlib.sha256()
        size=0
        for key in r["blocks"]:
            data=zlib.decompress((root/"event_blocks"/key).read_bytes())
            if key not in verified:assert sha(data)==key;verified.add(key)
            h.update(data);size+=len(data)
        assert h.hexdigest()==r["sha256"] and size==np.prod(r["shape"])*8
        written_traces.add(name)

    def lines(path):
        return [json.loads(s) for s in path.read_bytes().splitlines() if s.endswith(b"}")] if path.is_file() else []
    def body(code,method,key):
        folder=root/"cells"/code/method
        if method in ("NT","Q4"):
            base=folder/"search/physical" if method=="NT" else folder
            d=next((base/"evidence").glob("*/"+key))
            p=read(d/"plan.json");c=read(d/"certificate.json");event=d/"trace.npz"
        else:
            d=folder/"evidence"
            p=json.loads(gzip.decompress((d/"plans"/(key+".json.gz")).read_bytes()))
            c=read(d/"certificates"/(key+".json"));event=d/"certificates"/(key+".npz")
        assert event.relative_to(root).as_posix() in written_traces and c["metrics"]["E_bounds"][0]<=c["metrics"]["E_J"]<=c["metrics"]["E_bounds"][1]
        return p,c
    with (DEST/"curves.csv").open() as f:
        cuts={(r["case"],r["method"],int(r["cut_s"])):r for r in csv.DictReader(f)}
    assert len(cuts)==64
    summary=[];steps=[];deltas=[];feedback=[];checks=0;rounds=[];pools=[];q4rounds=[];interfaces=[];seeds=[]
    fig,axes=plt.subplots(2,2,figsize=(10,6.5))
    styles=dict(NT=("#1754a3","-"),Proposed=("#d16a20","--"),Q4=("#15825e","-."),**{"NT+AB":("#7864ae",":"),"NT+Proposed":("#bc3868","--")})
    for code,ax in zip(CODES,axes.flat):
        dirs=root/"cells"/code
        witness=read(root/"interface"/code/"witness.json")
        # Request release times and scene IDs come from the registered CSV, not inferred from execution times.
        import os
        reg=Path(os.environ["U1_NT"])/"research/m1i_generalization/registration"
        item=next(i for i in read(reg/"cases.json")["cases"] if i["case"].startswith(code+"_"))
        with (reg/"inputs"/item["input"]).open() as f:scene=[int(r["scene"]) for r in csv.DictReader(f)]
        for method in PRIMARY:
            a=read(root/"interface"/code/method/"audit.json")
            f=a["physical"]
            interfaces.append(dict(case=code,method=method,requests=len(scene),csv_sha256=f["req"],horizon_ticks=f["horizon"],events=f["segments"],trace_sha256=f["trace"],switches=len(f["switches"]) if isinstance(f["switches"],list) else f["switches"],E_J=f["E_J"],status=f["status"],idle_differences=a["default_idle_differences"],plan_sha256=a["archived_plan"]))
        for method in PRIMARY+(("NT+AB","NT+Proposed") if code in ("A03","C12") else ()):
            d=dirs/method
            receipt=read(d/"receipt.json")
            own=lines(d/"certificates.jsonl")
            prefix=[dict(r,origin="NT") for r in lines(dirs/"NT/certificates.jsonl") if r["t"]<=60] if method.startswith("NT+") else []
            stream=prefix+[dict(r,origin=method) for r in own]
            keys=set()
            for r in own:
                if r["plan"] in keys:continue
                _,cert=body(code,method,r["plan"]);keys.add(r["plan"])
                assert cert["metrics"]["status"]==r["status"] and cert["metrics"]["E_J"]==r["J"]
                checks+=1
            best=None;trace=[];first=None
            for r in stream:
                if r["t"]>180 or r["status"]!="SAFE":continue
                if first is None:first=r["t"]
                if best is None or r["bounds"][1]<best["bounds"][0]:
                    best=r;trace.append(r);steps.append(dict(case=code,method=method,t=r["t"],J=r["J"],plan=r["plan"],origin=r["origin"]))
            for budget in (10,30,60,180):
                at=[r for r in trace if r["t"]<=budget]
                reported=cuts[code,method,budget]
                assert (at[-1]["plan"] if at else "")==reported["plan"]
                assert (at[-1]["J"] if at else None)==(float(reported["J"]) if reported["J"] else None)
            if trace:
                x=[r["t"] for r in trace]+[180];y=[r["J"] for r in trace]+[trace[-1]["J"]]
                color,ls=styles[method];ax.step(x,y,where="post",label=method,color=color,linestyle=ls,lw=1.9)
                ax.plot(x[0],y[0],".",color=color)
            total=receipt.get("total_charged_s")
            stages=lines(d/"rounds.jsonl")
            if (d/"pool/pool.json").exists():
                for a in read(d/"pool/pool.json"):
                    pools.append(dict(case=code,method=method,generator=a["generator"],width=a.get("width"),depth=a.get("depth"),requests=len(scene),in_time=a.get("in_time"),plan=a.get("plan")))
            if (d/"optimization.json").exists():
                for a in read(d/"optimization.json").get("rounds",[]):
                    q4rounds.append(dict(case=code,turn=a["turn"],scanned=a.get("scan"),legal=a.get("legal"),pool=a.get("pool_size"),accepted=a.get("accepted"),
                        stop=a.get("stop"),checked=json.dumps([{k:v for k,v in x.items() if k in ("ref_rank","plan","status","ids","new_opp")} for x in a.get("evaluated",[])])))
            stats=dict(case=code,method=method,status=receipt["status"],charged_s=total,new_time_s=receipt.get("wall_observed_s"),
                       first_SAFE_s=first,J=best["J"] if best else None,own_calls=len(own),statuses=json.dumps(dict(Counter(r["status"] for r in own))),
                       conf_rounds=sum(z["phase"]=="configuration" for z in stages),post_rounds=sum(z["phase"]=="timing" for z in stages),
                       feedback_steps=sum(len(z.get("feedback",[])) for z in stages))
            if best:
                p,cert=body(code,best["origin"],best["plan"]);m=cert["metrics"]
                stats.update(peak_hi=max(m["peak_hi"]),slack_ms=m["min_deadline_slack_ms"],bounds=m["E_bounds"],switches=m["switch_count"])
            for z in stages:
                target={i for i,op in z.get("target",[])}
                target_scenes={scene[i] for i in target}
                actual={i for i,_,_ in z.get("real_changes",[])}
                rounds.append(dict(case=code,method=method,turn=z["turn"],phase=z["phase"],target=json.dumps(sorted(target)),open=len(z.get("scope",[])),
                                      solver=z.get("solver",{}).get("status"),actual=json.dumps(sorted(actual)),elapsed_s=z.get("elapsed_s")))
                for f in z.get("feedback",[]):
                    idx=f.get("selected")
                    feedback.append(dict(case=code,method=method,turn=z["turn"],target=sorted(target),target_scenes=sorted(target_scenes),victim=f["victim"],
                        selected=idx,scene=scene[idx] if idx is not None else None,other_scene=scene[idx] not in target_scenes if idx is not None else None,
                        really_changed=idx in actual if idx is not None else None,virtual_op=f.get("virtual_op"),before_violation=f["total_violation"],after_violation=f.get("after_violation")))
            if method.startswith("NT+") and best and (root/"seeds"/(code+".json")).exists():
                seed=read(root/"seeds"/(code+".json"));before=seed["plan"];after=p
                changes=[i for i,(a,b) in enumerate(zip(before["rows"][1::3],after["rows"][1::3])) if a[:2]!=b[:2]]
                timing=sum(a[2]!=b[2] for a,b in zip(before["rows"],after["rows"]))
                lows=len(set(map(tuple,before["low"]))^set(map(tuple,after["low"])))
                stats.update(seed_J=seed["J"],saving_J=seed["J"]-best["J"],changed_config=len(changes),changed_start=timing,changed_low=lows)
                native=read(d/"seed_identity.json") if (d/"seed_identity.json").exists() else {}
                if native:
                    initial,cert0=body(code,method,native["native"])
                    seed_ref,ntcert=body(code,"NT",seed["key"])
                    assert initial==seed_ref==before and cert0["metrics"]==ntcert["metrics"]
                    trace0=next((dirs/"NT/search/physical/evidence").glob("*/"+seed["key"])).joinpath("trace.npz")
                    e1=index[trace0.relative_to(root).as_posix()]
                    e2=index[(d/"evidence/certificates"/(native["native"]+".npz")).relative_to(root).as_posix()]
                    assert e1["sha256"]==e2["sha256"]
                    seeds.append(dict(case=code,method=method,NT_sha256=seed["key"],chapter3_sha256=native["native"],trace_sha256=e1["sha256"],J=seed["J"],first_available_s=seed["t"],charged_s=60))
                for i in changes:deltas.append(dict(case=code,method=method,request=i,scene=scene[i],old=before["rows"][3*i+1][:2],new=after["rows"][3*i+1][:2]))
            summary.append(stats)
        ax.set(title=f"{code} · {item['requests']} requests",xlabel="Elapsed time (s)",ylabel="Certified SAFE energy (J)",xlim=(0,180))
        ax.grid(alpha=.2);ax.ticklabel_format(style="plain",useOffset=False,axis="y")
    handles={}
    for ax in axes.flat:
        hs,ls=ax.get_legend_handles_labels();handles.update(zip(ls,hs))
    fig.legend(handles.values(),handles.keys(),loc="lower center",ncol=len(handles),frameon=False)
    fig.tight_layout(rect=(0,.05,1,1));fig.savefig(DEST/"quality.png",dpi=165);plt.close(fig)
    write("interfaces.csv",interfaces,["case","method","requests","csv_sha256","horizon_ticks","events","trace_sha256","switches","E_J","status","idle_differences","plan_sha256"])
    write("pools.csv",pools,["case","method","generator","width","depth","requests","in_time","plan"])
    write("q4_rounds.csv",q4rounds,["case","turn","scanned","legal","pool","accepted","stop","checked"])
    write("seeds.csv",seeds,["case","method","NT_sha256","chapter3_sha256","trace_sha256","J","first_available_s","charged_s"])
    write("routes.csv",summary,list(dict.fromkeys(k for r in summary for k in r)))
    write("improvements.csv",steps,["case","method","t","J","plan","origin"])
    write("changes.csv",deltas,["case","method","request","scene","old","new"])
    write("feedback.csv",feedback,["case","method","turn","target","target_scenes","victim","selected","scene","other_scene","really_changed","virtual_op","before_violation","after_violation"])
    write("rounds.csv",rounds,["case","method","turn","phase","target","open","solver","actual","elapsed_s"])
    summary_check=dict(cells=len(summary),certified_unique_within_cells=checks,traces=len(written_traces),blocks=len(verified),
        partial_traces=len(index)-len(written_traces),incumbents=len(steps),archive_sha256=desc["archive_sha256"])
    (DEST/"review.json").write_text(json.dumps(summary_check,indent=2)+"\n")
    print(summary_check)

if __name__=="__main__":
    with tempfile.TemporaryDirectory() as folder:review(Path(folder))
