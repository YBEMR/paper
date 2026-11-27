"""Calculate cohort-specific common-SAFE comparisons from eligible delivered certificates only."""
import csv
import json
from collections import Counter
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
TABLE=HERE/"tables"
ARMS=("Q4","Base","Ordinary","Previous","Source","NT10")
def read(p):return json.loads(p.read_bytes())
def emit(name,rows):
    TABLE.mkdir(exist_ok=True)
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with (TABLE/(name+".csv")).open("w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,keys,lineterminator="\n")
        w.writeheader()
        for r in rows:w.writerow({k:json.dumps(v,separators=(",",":")) if isinstance(v,(dict,list)) else v for k,v in r.items()})
def med(values):
    v=[x for x in values if x is not None];return median(v) if v else None

def main():
    rows=[];matched=[];sums=[];pooled=[];details=[];gains=[];quality=[]
    roster=read(HERE/"registration/cases.json")
    old={r["case"]:r for r in read(HERE/"registration/nt60_previous.json")}
    for obj in roster:
        code=obj["id"];cohort=obj["cohort"]
        root=HERE/"results"/code
        assert (root/"complete.json").exists(),code
        index={}
        for path in sorted((root/"runs").glob("*.json")):
            r=read(path);m=path.stem;certs=r["certificates"];ds=r["delivered"]
            first=ds[0] if ds else {};last=ds[-1] if ds else {}
            b=r.get("location",{});ph=r["phases"]
            row=dict(cohort=cohort,case=code,method=m,stop=r["receipt"]["status"],SAFE=bool(ds),
                first_plan=first.get("plan"),first_J=first.get("J"),first_SAFE_s=first.get("t"),first_phase=first.get("phase"),
                final_plan=last.get("plan"),final_J=last.get("J"),lo=(last.get("bounds") or [None,None])[0],
                hi=(last.get("bounds") or [None,None])[1],final_delivery_s=last.get("t"),return_or_cutoff_s=r["wall_s"],
                final_peak_hi=last.get("peak"),final_slack_ms=last.get("slack"),started_cert=r["started_certificates"],
                completed_cert=len(certs),fallback=int(r.get("fallback",False)),repair=int("repair" in ph),
                ordinary_window=b.get("ordinary_w"),selected_window=b.get("selected_w"),local_replays=r["replays"],
                terminal_cert=sum(c["phase"]=="terminal" for c in certs),local_cert=sum(c["phase"]=="repair" for c in certs),
                fallback_cert=sum(c["phase"]=="fallback" for c in certs),group_cert=sum(c["phase"]=="group" for c in certs),
                completed_kernel_s=sum(c["kernel_s"] for c in certs),cpu_core=r["receipt"]["cpu"],
                model_s=ph.get("model",0),construct_s=ph.get("construct",0),terminal_s=ph.get("terminal",0),
                repair_s=ph.get("repair",0),fallback_s=ph.get("fallback",0),group_s=ph.get("group",0),
                nt_s=ph.get("nt",0),handoff_s=ph.get("handoff",0),setup_warm_s=r["warm"]["warm_s"],
                process_s=r["receipt"]["process_s"])
            if m.startswith(("Gate","Pair")):
                assert row["first_plan"]==r["receipt"]["seed"]
            index[m]=row;rows.append(row)
        for left,right in (("Base","Q4"),("Ordinary","Base"),("Previous","Ordinary"),("Source","Ordinary"),
                           ("Source","Previous"),("Source","Base"),("Source","Q4"),("Source","NT10"),("Previous","NT10"),
                           ("PairAdaptive","PairFixed"),("GateAdaptive","GateFixed")):
            if left not in index or right not in index:continue
            a,b=index[left],index[right]
            common=a["SAFE"] and b["SAFE"]
            if left.startswith(("Gate","Pair")):assert a["first_plan"]==b["first_plan"]
            relation=("win" if a["hi"]<b["lo"] else "loss" if b["hi"]<a["lo"] else "overlap") if common else (
                "only_left" if a["SAFE"] else "only_right" if b["SAFE"] else "neither")
            matched.append(dict(cohort=cohort,case=code,left=left,right=right,relation=relation,common=common,
                       left_J=a["final_J"],right_J=b["final_J"],saving_J=b["final_J"]-a["final_J"] if common else None,
                       saving_pct=100*(b["final_J"]-a["final_J"])/b["final_J"] if common else None,
                       same_plan=(a["final_plan"]==b["final_plan"]) if common else None,
                       first_time_delta_s=a["first_SAFE_s"]-b["first_SAFE_s"] if common else None,
                       delivery_delta_s=a["final_delivery_s"]-b["final_delivery_s"] if common else None))
        a,b,c=(index[m] for m in ("Ordinary","Previous","Source"))
        details.append(dict(cohort=cohort,case=code,ordinary_window=a["selected_window"],previous_window=b["selected_window"],
                   source_window=c["selected_window"],ordinary_safe=a["SAFE"],previous_safe=b["SAFE"],source_safe=c["SAFE"],
                   ordinary_J=a["final_J"],previous_J=b["final_J"],source_J=c["final_J"],
                   ordinary_first_phase=a["first_phase"],previous_first_phase=b["first_phase"],source_first_phase=c["first_phase"],
                   previous_first_s=b["first_SAFE_s"],source_first_s=c["first_SAFE_s"],previous_replays=b["local_replays"],
                   source_replays=c["local_replays"],ordinary_repairs=a["local_cert"],previous_repairs=b["local_cert"],source_repairs=c["local_cert"]))
        fixed=index.get("PairFixed");adapt=index.get("PairAdaptive")
        if fixed:
            assert fixed["first_plan"]==adapt["first_plan"]
            gains.append(dict(cohort=cohort,case=code,seed=adapt["first_plan"],seed_J=adapt["first_J"],
                fixed_J=fixed["final_J"],adaptive_J=adapt["final_J"],fixed_slack=fixed["final_slack_ms"],adaptive_slack=adapt["final_slack_ms"],
                fixed_delivery_s=fixed["final_delivery_s"],adaptive_delivery_s=adapt["final_delivery_s"],
                adaptive_saving_pct=100*(adapt["first_J"]-adapt["final_J"])/adapt["first_J"],
                fixed_saving_pct=100*(fixed["first_J"]-fixed["final_J"])/fixed["first_J"]))
        if cohort=="development":
            hist=old[code]["best"];ref=hist["J"] if hist else None;key=hist["plan"] if hist else None;origin="U2 r1 archived"
        else:
            hist=index["NT60"];ref=hist["final_J"];key=hist["final_plan"];origin="U4-a measured"
        for m in ARMS:
            a=index[m]
            quality.append(dict(cohort=cohort,case=code,method=m,ten_s_J=a["final_J"],NT60_J=ref,NT60_plan=key,NT60_origin=origin,
                gap_vs_NT60_pct=100*(a["final_J"]-ref)/ref if ref and a["SAFE"] else None))
    for cohort in ("development","independent"):
        for m in (*ARMS,"NT60","PairFixed","PairAdaptive"):
            subset=[r for r in rows if r["method"]==m and r["cohort"]==cohort]
            if not subset:continue
            safe=[r for r in subset if r["SAFE"]]
            sums.append(dict(cohort=cohort,method=m,n=len(subset),SAFE=len(safe),median_first_s=med(r["first_SAFE_s"] for r in safe),
                median_delivery_s=med(r["final_delivery_s"] for r in safe),median_return_s=med(r["return_or_cutoff_s"] for r in subset),
                min_slack=min((r["final_slack_ms"] for r in safe),default=None),fallbacks=sum(r["fallback"] for r in subset),
                repairs=sum(r["repair"] for r in subset),certs_started=sum(r["started_cert"] for r in subset),
                certs_done=sum(r["completed_cert"] for r in subset),wall_cuts=sum(r["stop"]=="wall" for r in subset)))
        for left,right in sorted({(r["left"],r["right"]) for r in matched if r["cohort"]==cohort}):
            sel=[r for r in matched if (r["cohort"],r["left"],r["right"])==(cohort,left,right)]
            ss=[r for r in sel if r["common"]];status=Counter(r["relation"] for r in sel)
            pooled.append(dict(cohort=cohort,left=left,right=right,n=len(sel),joint_SAFE=len(ss),wins=status["win"],
                overlap=status["overlap"],losses=status["loss"],only_left=status["only_left"],only_right=status["only_right"],
                neither=status["neither"],mean_saving_pct=sum(r["saving_pct"] for r in ss)/len(ss) if ss else None,
                median_saving_pct=med(r["saving_pct"] for r in ss),identical_plans=sum(r["same_plan"] for r in ss)))
    for k,v in (("routes",rows),("methods",sums),("pairs",matched),("paired_summary",pooled),("locations",details),("groups",gains),("nt60",quality)):
        emit(k,v)
if __name__=="__main__":main()
