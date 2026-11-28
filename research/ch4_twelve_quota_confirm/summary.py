"""Statistics for all registered cells; all performance comparisons use concurrent evidence."""
import csv
import gzip
import inspect
import json
import sys
from collections import Counter,defaultdict
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
OUT=HERE/"results"
PREV=HERE.parent/"ch4_quota_transfer"
sys.path.insert(0,str(PREV))
import decision as stats
stats.OUT=OUT

def cases():
    return sorted(json.loads((OUT/"accounts"/"registration.json").read_bytes())["cases"])
def key(r):
    return tuple(r[k] for k in ("case","cap","rep","arm"))
def indexed(rows):
    index=defaultdict(list)
    for r in rows:index[key(r)].append(r)
    return index
def med(seq):return stats.med(seq)
def load_log(cell,name):
    path=OUT/"logs"/cell["case"]/f"r{cell['rep']}-{cell['arm']}-{cell['cap']}"/(name+".gz")
    if not path.exists():return []
    with gzip.open(path,"rt",encoding="utf8") as f:
        return [json.loads(line) for line in f if line.endswith("\n")]

def calculate():
    stats.CASES=cases()
    hist=HERE.parent/"ch3_direct_thermal_final/results/60/tables/median_pairs.csv"
    with hist.open(encoding="utf8") as f:
        stats.HIST={r["case"]:float(r["B_J"]) if r["B_J"] else None for r in csv.DictReader(f)}
    src=inspect.getsource(stats.formal)
    assert src.count("})==60")==1
    ns={}
    exec(src.replace("})==60","})==180"),stats.__dict__,ns)
    ns["formal"]()
    pairs=stats.csvrows("paired_runs")
    first=[]
    for p in pairs:
        a,b=p["A_first_s"],p["B_first_s"]
        outcome="neither";saving=rel=None
        if a and b:
            saving=float(a)-float(b);rel=100*saving/float(a)
            outcome="B_earlier" if saving>0 else "A_earlier" if saving<0 else "tie"
        elif a:outcome="A_only"
        elif b:outcome="B_only"
        first.append(dict(case=p["case"],cap=p["cap"],rep=p["rep"],A_first_s=a,B_first_s=b,
                          outcome=outcome,saved_s=saving,saved_pct=rel,energy_order=p["interval_order"]))
    stats.put("first_safe_pairs",first)
    aggregates=[]
    for case in [*stats.CASES,"all"]:
        for cap in ("10","20"):
            rs=[r for r in first if r["cap"]==cap and case in (r["case"],"all")]
            ct=Counter(r["outcome"] for r in rs);energy=Counter(r["energy_order"] for r in rs)
            aggregates.append(dict(case=case,cap=cap,all_pairs=len(rs),common=sum(ct[k] for k in ("A_earlier","B_earlier","tie")),
                A_earlier=ct["A_earlier"],B_earlier=ct["B_earlier"],tie=ct["tie"],A_only=ct["A_only"],B_only=ct["B_only"],
                neither=ct["neither"],median_saved_s=med(r["saved_s"] for r in rs),median_saved_pct=med(r["saved_pct"] for r in rs),
                A_lower_J=energy["A_lower"],B_lower_J=energy["B_lower"],overlap_J=energy["overlap"]))
    stats.put("first_safe_summary",aggregates)
    cells=stats.csvrows("cells"); certs=indexed(stats.csvrows("certificates"))
    targets=stats.csvrows("quality_targets")
    for t in targets:
        limit=float(t["target_hi_J"]) if t["target_hi_J"] else None
        hits=sorted((r for r in certs[key(t)] if r["status"]=="SAFE" and limit is not None and float(r["hi"])<=limit),key=lambda r:float(r["t"]))
        assert bool(hits)==(t["status"]=="hit")
        if hits:assert hits[0]["t"]==t["first_hit_s"]
        t.update(first_hit_stage=hits[0]["stage"] if hits else None,first_hit_plan=hits[0]["plan"] if hits else None,
                 qualifying_search=sum(r["stage"]=="search/physical" for r in hits),
                 qualifying_direct=sum(r["stage"].endswith("/direct") for r in hits))
    stats.put("quality_targets",targets)
    hit_pairs=[];hit_sum=[];source_sum=[]
    for case in [*stats.CASES,"all"]:
        for cap in ("10","20","60"):
            for tol in ("0","0.01"):
                rows=[r for r in targets if case in (r["case"],"all") and r["cap"]==cap and r["tolerance"]==tol]
                for arm in ("A","B") if cap!="60" else ("A",):
                    rs=[r for r in rows if r["arm"]==arm];ct=Counter(r["status"] for r in rs)
                    search=sum(r["first_hit_stage"]=="search/physical" for r in rs)
                    direct=sum((r["first_hit_stage"] or "").endswith("/direct") for r in rs)
                    assert search+direct==ct["hit"]
                    source_sum.append(dict(case=case,cap=cap,arm=arm,tolerance=tol,runs=len(rs),hits=ct["hit"],
                        first_from_search=search,first_from_direct=direct,all_search_deliveries=sum(r["qualifying_search"] for r in rs),
                        all_direct_deliveries=sum(r["qualifying_direct"] for r in rs),median_hit_s=med(r["first_hit_s"] for r in rs),
                        no_safe=ct["no_SAFE"],above_target=ct["above_target"],no_reference=ct["no_reference"]))
                if cap=="60":continue
                paired=defaultdict(dict)
                for r in rows:paired[(r["case"],r["rep"])][r["arm"]]=r
                here=[]
                for (code,rep),ab in paired.items():
                    a,b=ab["A"],ab["B"]
                    x,y=a["first_hit_s"],b["first_hit_s"]
                    outcome="both" if x and y else "A_only" if x else "B_only" if y else "neither"
                    row=dict(case=code,cap=cap,rep=rep,tolerance=tol,A_status=a["status"],B_status=b["status"],
                             A_first_s=x,B_first_s=y,outcome=outcome,B_minus_A_s=float(y)-float(x) if x and y else None)
                    here.append(row)
                if case!="all":hit_pairs.extend(here)
                ct=Counter(r["outcome"] for r in here)
                hit_sum.append(dict(case=case,cap=cap,tolerance=tol,pairs=len(here),both=ct["both"],A_only=ct["A_only"],
                                    B_only=ct["B_only"],neither=ct["neither"],paired_B_minus_A_median_s=med(r["B_minus_A_s"] for r in here)))
    stats.put("target_pairs",hit_pairs);stats.put("target_pair_summary",hit_sum);stats.put("target_stages",source_sum)
    flows=stats.csvrows("flow_summary"); comparison=[]
    for case in stats.CASES:
        for cap in ("10","20"):
            a,b=(next(r for r in flows if (r["case"],r["cap"],r["arm"])==(case,cap,arm)) for arm in "AB")
            aj,bj=a["median_J"],b["median_J"]
            comparison.append(dict(case=case,cap=cap,A_safe=a["safe"],B_safe=b["safe"],A_J=aj,B_J=bj,
                     A60_J=a["ref_J"],ref_safe=a["ref_safe"],reliable_pair=int(a["reliable"]==b["reliable"]=="1"),
                     B_vs_A_pct=100*(float(bj)/float(aj)-1) if aj and bj else None,
                     A_vs_A60_pct=a["gap_ref_pct"],B_vs_A60_pct=b["gap_ref_pct"],
                     A_first_s=a["median_first_success_s"],B_first_s=b["median_first_success_s"]))
    stats.put("flow_pairs",comparison)
    dev={"A02","A06","C10","C11"};all_cases=set(stats.CASES)
    cohorts=[]
    for name,group in (("all",all_cases),("development",dev),("other_registered",all_cases-dev)):
        for cap in ("10","20"):
            fs=[r for r in comparison if r["case"] in group and r["cap"]==cap]
            common=[r for r in fs if r["reliable_pair"]]
            ps=[r for r in first if r["case"] in group and r["cap"]==cap]
            ds=[r["B_vs_A_pct"] for r in common]
            row=dict(cohort=name,cap=cap,registered=len(group),pairs=len(ps),common_reliable=len(common),
                mean_B_vs_A_pct=sum(ds)/len(ds) if ds else None,max_B_vs_A_pct=max(ds,default=None),
                paired_first_n=sum(r["saved_s"] is not None for r in ps),B_earlier=sum(r["outcome"]=="B_earlier" for r in ps),
                median_saved_first_s=med(r["saved_s"] for r in ps),median_saved_first_pct=med(r["saved_pct"] for r in ps))
            for arm in "AB":
                gaps=[float(r[arm+"_vs_A60_pct"]) for r in fs if int(r[arm+"_safe"])>=2 and int(r["ref_safe"])>=2]
                row[arm+"_safe"]=sum(int(r[arm+"_safe"]) for r in fs)
                row[arm+"_reliable"]=sum(int(r[arm+"_safe"])>=2 for r in fs)
                row[arm+"_ref_n"]=len(gaps)
                row[arm+"_mean_gap_ref_pct"]=sum(gaps)/len(gaps) if gaps else None
            cohorts.append(row)
    stats.put("cohorts",cohorts)
    return cells,certs,targets

if __name__=="__main__":calculate()
