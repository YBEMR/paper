"""Offline analysis of certified end points, timed delivery and paired mapping identities."""
import csv
import io
import json
import statistics
import sys
import tarfile
import zlib
from collections import Counter
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"ch3_mapping_first_nested"))
from restore_plan import members
TAB=ROOT/"tables"
CASES=("A02","A06","C10","C11")
METHODS=("fit","analytic")
BUDGETS=(60,600)
CUTS=(10,30,60,180,300,600)
def read(p):return json.loads(p.read_bytes())
def lines(p):return [json.loads(b) for b in p.read_bytes().splitlines() if b.endswith(b"}")] if p.exists() else []
def load_csv(p):
    with p.open(encoding="utf-8") as stream:return list(csv.DictReader(stream))
def table(name,rows):
    with (TAB/name).open("w",newline="") as stream:
        w=csv.DictWriter(stream,fieldnames=rows[0],lineterminator="\n")
        w.writeheader();w.writerows(rows)
def verdict(a,b):
    if not a or not b:return "unpaired"
    return "win" if a["bounds"][1]<b["bounds"][0] else "loss" if b["bounds"][1]<a["bounds"][0] else "overlap"
def spans(events,task,end):
    total=0.;start=None
    for e in events:
        if e["t"]>end:continue
        if e.get("task")==task and e["event"]=="begin":start=e["t"]
        if (e.get("task")==task and e["event"]=="end" or task=="search_cert" and e["event"]=="certificate") and start is not None:
            total+=e["t"]-start;start=None
    return total+(end-start if start is not None else 0.)

def cell(code,arm,budget,bundle):
    ctx=dict(case=code,arm=arm,budget_s=budget)
    folder=ROOT/"paired_results"/code/f"{arm}-{budget}"
    rc=read(folder/"receipt.json");assert rc["status"] in ("deadline","natural")
    assert (rc["code"],rc["arm"],rc["budget"])==(code,arm,budget)
    search=lines(folder/"search.jsonl");post=lines(folder/"refine.jsonl")
    certs=lines(folder/"certificates.jsonl")
    first=next((e["t"] for e in certs if e["point"]["status"]=="SAFE"),None)
    cutoff=budget-5 if first is not None and first<budget-5 else budget
    certs=[e for e in certs if e["t"]<=(cutoff if e["stage"]=="search" else budget)]
    best=None;updates=[]
    for e in certs:
        p=e["point"]
        if p["status"]=="SAFE":
            assert p["slack"]>=0 and p["peak"]<=80
            if best is None or verdict(p,best["point"])=="win":
                best=e
                updates.append(dict(**ctx,t=e["t"],J=p["J"],mapping=e["mapping"],plan=p["plan"],stage=e["stage"]))
    cuts=[]
    for t in CUTS:
        if t>budget:continue
        event=next((r for r in reversed(updates) if r["t"]<=t),{})
        cuts.append(dict(**ctx,t=t,best_SAFE_J=event.get("J"),plan=event.get("plan")))
    statuses=Counter(e["point"]["status"] for e in certs)
    dp=[json.loads(b) for b in zlib.decompress((folder/"dp.jsonl.z").read_bytes()).splitlines()]
    native=read(folder/"native.json") if (folder/"native.json").is_file() else {}
    stop=min(rc["charged_s"],cutoff,native.get("search",{}).get("supervisor_t",cutoff))
    clocks={k+"_s":spans(search,k,stop) for k in ("instance","construct","search_cert")}
    clocks.update({k+"_s":spans(post,k,rc["charged_s"]) for k in ("selection","handoff","dp_cert")})
    for thermal,name in ((False,"ordinary_DP_s"),(True,"thermal_DP_s")):
        clocks[name]=sum(r["elapsed_s"] for r in dp if r["kind"]=="dp" and r["thermal"]==thermal)
    clocks["other_s"]=rc["charged_s"]-sum(clocks.values())
    assert clocks["other_s"]>=-.05
    ledger=lines(folder/"ledger.jsonl")
    maps={e["mapping"] for e in ledger if e["event"]=="full_mapping"}|{e["mapping"] for e in certs}
    pt=best["point"] if best else {}
    config=None
    if best:
        files=members(folder.parent/"physical",pt["plan"])
        config=[r[:2] for r in json.loads(files["plan.json"])["rows"][1::3]]
        for name,data in files.items():
            h=tarfile.TarInfo(f"{code}/{arm}-{budget}/{name}");h.size=len(data)
            bundle.addfile(h,io.BytesIO(data))
    row=dict(**ctx,host=rc["host"],core=rc["core"],charged_s=rc["charged_s"],supervisor_s=rc["supervisor_s"],
             stop=rc["status"],first_safe_s=first,best_s=best["t"] if best else None,final_J=pt.get("J"),
             low_J=(pt.get("bounds") or [None,None])[0],high_J=(pt.get("bounds") or [None,None])[1],
             peak_upper_C=pt.get("peak"),min_slack_ms=pt.get("slack"),switches=pt.get("switches"),plan=pt.get("plan"),
             mapping=best["mapping"] if best else None,best_stage=best["stage"] if best else None,
             seen_maps=len(maps),certified_maps=len({e["mapping"] for e in certs}),SAFE=statuses["SAFE"],HOT=statuses["HOT"],
             OUT_OF_MODEL=statuses["OUT_OF_MODEL"],UNRESOLVED=statuses["UNRESOLVED"],
             timing_failed_closed_calls=sum(e["event"]=="timing_failure" for e in ledger),
             dp_no_path=sum(r["kind"]=="dp" and any(not dev["finite"] for dev in r["stats"]) for r in dp),
             dp_bad_post=sum(r["kind"]=="illegal_post" for r in dp),**clocks)
    return dict(row=row,updates=updates,cuts=cuts,pt=pt,maps=maps,certs=certs,config=config)

def compare(cells,c,b1,b2):
    a,b=cells[c,"fit",b1],cells[c,"analytic",b2]
    ap,bp=a["pt"],b["pt"]
    delta=bp["J"]-ap["J"] if ap and bp else None
    ac,bc=a["config"],b["config"]
    if ac and bc:assert len(ac)==len(bc)
    am,bm=a["row"]["mapping"],b["row"]["mapping"]
    return dict(case=c,fit_budget_s=b1,analytic_budget_s=b2,fit_J=ap.get("J"),analytic_J=bp.get("J"),delta_J=delta,
       delta_pct=100*delta/ap["J"] if delta is not None else None,strict=verdict(bp,ap),
       fit_plan=ap.get("plan"),analytic_plan=bp.get("plan"),fit_mapping=am,analytic_mapping=bm,
       requests=len(ac) if ac else None,changed_device=sum(x[0]!=y[0] for x,y in zip(ac,bc)) if ac and bc else None,
       same_device_changed_OPP=sum(x[0]==y[0] and x[1]!=y[1] for x,y in zip(ac,bc)) if ac and bc else None,
       fit_best_map_seen_by_analytic=(am in b["maps"]) if am else None,
       fit_best_map_certified_by_analytic=any(e["mapping"]==am for e in b["certs"]) if am else None,
       analytic_best_SAFE_J_on_fit_map=min((e["point"]["J"] for e in b["certs"] if e["mapping"]==am and e["point"]["status"]=="SAFE"),default=None),
       analytic_best_map_seen_by_fit=(bm in a["maps"]) if bm else None)

def plot(cells):
    fig,axes=plt.subplots(4,2,figsize=(10,10),layout="constrained")
    for i,c in enumerate(CASES):
        for j,budget in enumerate(BUDGETS):
            ax=axes[i,j]
            for arm,color,linestyle,name in (("fit","#1b5279","-","Three-point fit"),("analytic","#c25b24","--","Analytic cost")):
                events=cells[c,arm,budget]["updates"]
                xs=[ev["t"] for ev in events];ys=[ev["J"] for ev in events]
                if xs:
                    ax.step(xs+[budget],ys+[ys[-1]],where="post",color=color,linestyle=linestyle,label=name)
                    ax.scatter(xs[:1],ys[:1],s=12,color=color)
                else:ax.plot([],[],color=color,label=name+" (no SAFE)")
            ax.set_xlim(0,budget);ax.ticklabel_format(axis="y",useOffset=False)
            ax.set_title(f"{c}  |  {budget} s");ax.set_ylabel("Best SAFE energy (J)")
            if i==3:ax.set_xlabel("End-to-end time (s)")
            ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.savefig(ROOT/"energy_vs_time.png",dpi=165);plt.close(fig)

def main():
    TAB.mkdir(exist_ok=True)
    with tarfile.open(ROOT/"final_evidence.tar.gz","w:gz") as bundle:
        cells={(c,a,b):cell(c,a,b,bundle) for c in CASES for a in METHODS for b in BUDGETS}
    rows=[z["row"] for z in cells.values()]
    assert len(rows)==16 and sum(r["charged_s"] for r in rows)<=5280
    assert all(len({(r["host"],r["core"]) for r in rows if r["case"]==c})==1 for c in CASES)
    pairs=[compare(cells,c,b,b) for c in CASES for b in BUDGETS]
    cross=[compare(cells,c,60,600) for c in CASES]
    table("cells.csv",rows);table("pairs.csv",pairs);table("long_vs_short.csv",cross)
    requests=[]
    for c in CASES:
        for b in BUDGETS:
            left=cells[c,"fit",b]["config"];right=cells[c,"analytic",b]["config"]
            if left is None or right is None:continue
            for i,((u,k),(v,h)) in enumerate(zip(left,right)):
                requests.append(dict(case=c,budget_s=b,request_index=i,fit_device={2:"GPU",3:"NPU"}[u],fit_opp=k,
                     analytic_device={2:"GPU",3:"NPU"}[v],analytic_opp=h,changed_device=u!=v,
                     changed_opp_on_same_device=u==v and k!=h))
    if requests:table("request_assignments.csv",requests)
    table("checkpoints.csv",[r for z in cells.values() for r in z["cuts"]])
    table("improvements.csv",[r for z in cells.values() for r in z["updates"]])
    plot(cells)
    from decision import report
    report(cells,rows,pairs,cross)

if __name__=="__main__":main()
