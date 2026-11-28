"""Post-clock comparisons using only this batch's certified results for its targets."""
import csv,gzip,json,sys
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent
PREV=HERE.parent/"ch4_quota_transfer"
sys.path.insert(0,str(PREV))
import decision as stats
OUT=HERE/"results"
stats.OUT=OUT

def audit():
    cells=stats.csvrows("cells");certs=stats.csvrows("certificates")
    budget=json.loads((OUT/"budget.json").read_bytes())
    assert len(cells)==len({tuple(r[k] for k in ("case","cap","arm","rep")) for r in cells})==60
    assert budget["actual_cpu_s"]<=1500 and budget["preparation_cpu_s"]<=240
    assert sum(int(r["cap"]) for r in cells)==1440
    for c in cells:
        issued=[r for r in certs if all(r[k]==c[k] for k in ("case","cap","arm","rep"))]
        assert int(c["certs"])==len(issued)
        assert all(0<=float(r["t"])<=int(c["cap"]) for r in issued)
        safe=[r for r in issued if r["status"]=="SAFE"]
        assert bool(safe)==bool(int(c["safe"]))
        if safe:
            assert min(float(r["t"]) for r in safe)==float(c["first_s"])
        else:
            assert all(not c[k] for k in ("first_s","last_s","J","lo","hi"))
        assert int(c["generated"])>0 and int(c["evaluated"])>0
    return cells

def compare():
    cells=audit()
    with (PREV/"results/flow_summary.csv").open(encoding="utf8") as f:
        cold=list(csv.DictReader(f))
    # This field is descriptive only; goal and ref_J are computed inside formal() from warm A60.
    stats.HIST={r["case"]:float(r["median_J"]) for r in cold if r["cap"]=="60"}
    stats.formal()
    warm=stats.csvrows("flow_summary")
    cold_warm=[]
    for w in warm:
        old=next(r for r in cold if all(w[k]==r[k] for k in ("case","arm","cap")))
        cold_warm.append(dict(case=w["case"],arm=w["arm"],cap=w["cap"],cold_safe=old["safe"],warm_safe=w["safe"],
                              cold_median_J=old["median_J"],warm_median_J=w["median_J"],
                              cold_median_first_s=old["median_first_success_s"],warm_median_first_s=w["median_first_success_s"]))
    stats.put("cold_warm",cold_warm)
    targets=stats.csvrows("quality_targets")
    summary=[];paired=[]
    for cap in ("10","20","60"):
        for tolerance in ("0","0.01"):
            for case in (*stats.CASES,"all"):
                for arm in "AB" if cap!="60" else "A":
                    rs=[r for r in targets if r["arm"]==arm and r["cap"]==cap and r["tolerance"]==tolerance and case in (r["case"],"all")]
                    hits=[float(r["first_hit_s"]) for r in rs if r["status"]=="hit"]
                    assert len(rs) in (3,12)
                    summary.append(dict(case=case,cap=cap,arm=arm,tolerance=tolerance,runs=len(rs),hits=len(hits),
                               median_hit_s=median(hits) if hits else None,no_safe=sum(r["status"]=="no_SAFE" for r in rs),
                               above_target=sum(r["status"]=="above_target" for r in rs),no_ref=sum(r["status"]=="no_reference" for r in rs)))
            if cap=="60":continue
            for case in stats.CASES:
                for rep in ("1","2","3"):
                    rows={r["arm"]:r for r in targets if (r["case"],r["rep"],r["cap"],r["tolerance"])==(case,rep,cap,tolerance)}
                    a,b=rows["A"],rows["B"]
                    dt=float(b["first_hit_s"])-float(a["first_hit_s"]) if a["status"]==b["status"]=="hit" else None
                    paired.append(dict(case=case,cap=cap,rep=rep,tolerance=tolerance,A_status=a["status"],B_status=b["status"],
                                    A_first_s=a["first_hit_s"],B_first_s=b["first_hit_s"],B_minus_A_s=dt))
    stats.put("target_summary",summary);stats.put("target_pairs",paired)
    detail=[]
    pairs=stats.csvrows("paired_runs")
    for case in stats.CASES:
        for cap in ("10","20"):
            ab={r["arm"]:r for r in warm if r["case"]==case and r["cap"]==cap}
            rs=[r for r in pairs if r["case"]==case and r["cap"]==cap]
            row=dict(case=case,cap=cap,paired_runs=len(rs),both_safe=sum(bool(r["A_J"] and r["B_J"]) for r in rs),
                     B_strict_wins=sum(r["interval_order"]=="B_lower" for r in rs),
                     A_strict_wins=sum(r["interval_order"]=="A_lower" for r in rs),
                     overlaps=sum(r["interval_order"]=="overlap" for r in rs),
                     A_only_safe=sum(r["A_safe"]=="1" and r["B_safe"]=="0" for r in rs),
                     B_only_safe=sum(r["A_safe"]=="0" and r["B_safe"]=="1" for r in rs),
                     neither_safe=sum(r["A_safe"]==r["B_safe"]=="0" for r in rs))
            for a,s in ab.items():
                row.update({a+"_"+k:s[k] for k in ("safe","reliable","median_J","median_first_success_s","gap_ref_pct")})
            a,b=[ab[k]["median_J"] for k in "AB"]
            row["B_vs_A_median_pct"]=100*(float(b)/float(a)-1) if a and b else None
            detail.append(row)
    stats.put("paired_by_flow",detail)

if __name__=="__main__":compare()
