"""Reconstruct and verify endpoints with the frozen physical-evidence reader."""
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PREV = ROOT.parent/"ch3_analytic_quota"
sys.path.insert(0, str(PREV))
import analyze as audit
from analyze import CASES, BUDGETS, cell, plt, table, verdict

TAB = ROOT/"tables"
audit.ROOT, audit.TAB = ROOT, TAB
METHODS = ("anchors", "center")

def compare(cells,c,b1,b2):
    a,b=cells[c,"anchors",b1],cells[c,"center",b2]
    ap,bp=a["pt"],b["pt"]
    delta=bp["J"]-ap["J"] if ap and bp else None
    ac,bc=a["config"],b["config"]
    if ac and bc:assert len(ac)==len(bc)
    am,bm=a["row"]["mapping"],b["row"]["mapping"]
    return dict(case=c,anchors_budget_s=b1,center_budget_s=b2,anchors_J=ap.get("J"),center_J=bp.get("J"),delta_J=delta,
       delta_pct=100*delta/ap["J"] if delta is not None else None,strict=verdict(bp,ap),
       anchors_low_J=a["row"]["low_J"],anchors_high_J=a["row"]["high_J"],
       center_low_J=b["row"]["low_J"],center_high_J=b["row"]["high_J"],
       anchors_peak_upper_C=a["row"]["peak_upper_C"],center_peak_upper_C=b["row"]["peak_upper_C"],
       anchors_min_slack_ms=a["row"]["min_slack_ms"],center_min_slack_ms=b["row"]["min_slack_ms"],
       anchors_plan=ap.get("plan"),center_plan=bp.get("plan"),anchors_mapping=am,center_mapping=bm,
       requests=len(ac) if ac else None,changed_device=sum(x[0]!=y[0] for x,y in zip(ac,bc)) if ac and bc else None,
       same_device_changed_OPP=sum(x[0]==y[0] and x[1]!=y[1] for x,y in zip(ac,bc)) if ac and bc else None,
       anchors_best_map_seen_by_center=(am in b["maps"]) if am else None,
       anchors_best_map_certified_by_center=any(e["mapping"]==am for e in b["certs"]) if am else None,
       center_best_SAFE_J_on_anchors_map=min((e["point"]["J"] for e in b["certs"] if e["mapping"]==am and e["point"]["status"]=="SAFE"),default=None),
       center_best_map_seen_by_anchors=(bm in a["maps"]) if bm else None)

def plot(cells):
    fig,axes=plt.subplots(4,2,figsize=(10,10),layout="constrained")
    for i,c in enumerate(CASES):
        for j,budget in enumerate(BUDGETS):
            ax=axes[i,j]
            for arm,color,linestyle,name in (("anchors","#1b5279","-","Three initial anchors"),("center","#c25b24","--","Balance center only")):
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
            left=cells[c,"anchors",b]["config"];right=cells[c,"center",b]["config"]
            if left is None or right is None:continue
            for i,((u,k),(v,h)) in enumerate(zip(left,right)):
                requests.append(dict(case=c,budget_s=b,request_index=i,anchors_device={2:"GPU",3:"NPU"}[u],anchors_opp=k,
                     center_device={2:"GPU",3:"NPU"}[v],center_opp=h,changed_device=u!=v,
                     changed_opp_on_same_device=u==v and k!=h))
    if requests:table("request_assignments.csv",requests)
    table("checkpoints.csv",[r for z in cells.values() for r in z["cuts"]])
    table("improvements.csv",[r for z in cells.values() for r in z["updates"]])
    plot(cells)
    from summarize import report
    report(cells, rows, pairs, cross)

if __name__=="__main__":main()
