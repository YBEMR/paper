"""Summarize previously delivered evidence only. No solver imports."""
import csv, gzip, json
from pathlib import Path
from statistics import median
from collections import Counter, defaultdict

OUT=Path(__file__).resolve().parent/"results"
CASES=("A02","A06","C10","C11")
HIST=dict(zip(CASES,[27.643950874800698,46.09106505570687,57.9068489201513,73.62270289955578]))

def put(name,rows):
    with (OUT/(name+".csv")).open("w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,list(dict.fromkeys(k for r in rows for k in r)),lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

def csvrows(name):
    with (OUT/(name+".csv")).open(encoding="utf8") as f:return list(csv.DictReader(f))

def diag(name,folder="diag1"):
    with gzip.open(OUT/"diagnostic"/folder/(name+".jsonl.gz"),"rt") as f:
        return [json.loads(s) for s in f if s.endswith("\n")]

def med(values):
    x=[float(v) for v in values if v not in (None,"")]
    return median(x) if x else None

def pct(a,b):
    return 100*(a/b-1) if a is not None and b else None

def fixed():
    keys=("case","j","g","n")
    rows=[]
    for r in diag("sets"):
        row={k:r[k] for k in (*keys,"parent","slots","union","common")}
        row.update(jaccard=r["common"]/r["union"],common_per_slot=r["common"]/r["slots"])
        for a in "AB":
            row["only_"+a]=json.dumps(r["only_"+a],separators=(",",":"))
            row.update({a+"_"+k:v for k,v in r[a].items() if k!="quotas"})
        rows.append(row)
    put("fixed_groups",rows)
    fine=diag("fine")
    ids=(*keys,"rep","arm")
    idx=lambda r:tuple(r[k] for k in ids)
    bare={idx(r):r["elapsed"] for r in diag("probe") if r["mode"]=="bare"}
    assert len(rows)==360 and len(bare)==len(fine)==2160
    pairs={}; components=defaultdict(Counter)
    for r in fine:
        case,j,g,n,rep,a=idx(r)
        out=pairs.setdefault((case,j,g,n,rep),{k:r[k] for k in (*keys,"rep")})
        out[a+"_gen_s"]=r["common_gen"]+r["center"]+r["slice"]
        out[a+"_exp_s"]=bare[idx(r)]
        for k in ("common_gen","center","slice","replay","heat","extension","other_eval","total"):
            components[(case,a)][k]+=r[k]
    put("fixed_pairs",list(pairs.values()))
    put("fixed_components",[dict(case=c,arm=a,**tot) for (c,a),tot in components.items()])
    per=[]
    for case in CASES:
        for rep in (1,2,3):
            rs=[r for r in pairs.values() if r["case"]==case and r["rep"]==rep]
            totals={k:sum(r[k] for r in rs) for k in ("A_gen_s","B_gen_s","A_exp_s","B_exp_s")}
            per.append(dict(case=case,rep=rep,groups=len(rs),**totals,
                      gen_change_pct=pct(totals["B_gen_s"],totals["A_gen_s"]),exp_change_pct=pct(totals["B_exp_s"],totals["A_exp_s"])))
    put("fixed_repeats",per)
    put("physical_cost",diag("physical"))
    bins=diag("binning")
    brow=[]
    for case in CASES:
        for a in "AB":
            rs=[r for r in bins if r["case"]==case and r["arm"]==a]
            off=sum(r["fifo_no_bins"] for r in rs); on=sum(r["fifo_with_bins"] for r in rs)
            brow.append(dict(case=case,arm=a,pairs=len(rs),no_bins_s=off,with_bins_s=on,marginal_s=on-off))
    put("binning_cost",brow)
    put("counter_overhead",diag("probe","diag_probe2"))

def formal():
    cells=csvrows("cells"); cert=csvrows("certificates")
    assert len(cells)==len({(r["case"],r["arm"],r["cap"],r["rep"]) for r in cells})==60
    targets=[]; flows=[]; pairs=[]; summary=[]; costs=[]
    for case in CASES:
        data=[r for r in cells if r["case"]==case]
        ref=[r for r in data if r["cap"]=="60"]
        goal=med(r["hi"] for r in ref); energy=med(r["J"] for r in ref)
        for cap in ("10","20","60"):
            for a in ("A","B") if cap!="60" else ("A",):
                rs=[r for r in data if r["cap"]==cap and r["arm"]==a]
                safe=sum(int(r["safe"]) for r in rs)
                J=med(r["J"] for r in rs)
                flows.append(dict(case=case,cap=cap,arm=a,runs=len(rs),safe=safe,reliable=int(safe>=2),median_J=J,
                      ref_safe=sum(int(r["safe"]) for r in ref),ref_J=energy,ref_hi=goal,historical_J=HIST[case],
                      ref_history_change_pct=pct(energy,HIST[case]),gap_ref_pct=pct(J,energy),
                      median_first_success_s=med(r["first_s"] for r in rs),median_last_success_s=med(r["last_s"] for r in rs)))
                for r in rs:
                    delivered=[c for c in cert if all(c[k]==r[k] for k in ("case","cap","rep","arm")) and c["status"]=="SAFE"]
                    for tolerance in (0,.01):
                        threshold=None if goal is None else goal*(1+tolerance)
                        hit=[float(c["t"]) for c in delivered if threshold is not None and float(c["hi"])<=threshold]
                        targets.append(dict(case=case,cap=cap,arm=a,rep=r["rep"],tolerance=tolerance,target_hi_J=threshold,
                               first_hit_s=min(hit,default=None),status="no_reference" if goal is None else "hit" if hit else "no_SAFE" if not delivered else "above_target"))
            if cap=="60":continue
            for rep in ("1","2","3"):
                ab={r["arm"]:r for r in data if r["cap"]==cap and r["rep"]==rep}
                a,b=ab["A"],ab["B"]
                order=None
                if a["J"] and b["J"]:
                    order="B_lower" if float(b["hi"])<float(a["lo"]) else "A_lower" if float(a["hi"])<float(b["lo"]) else "overlap"
                row=dict(case=case,cap=cap,rep=rep,interval_order=order,change_pct=pct(med([b["J"]]),med([a["J"]])))
                for arm,r in ab.items():row.update({arm+"_"+k:r[k] for k in ("safe","J","lo","hi","first_s","last_s")})
                pairs.append(row)
    for cap in ("10","20","60"):
        for a in ("A","B") if cap!="60" else ("A",):
            fs=[r for r in flows if r["cap"]==cap and r["arm"]==a]
            rs=[r for r in cells if r["cap"]==cap and r["arm"]==a]
            gaps=[r["gap_ref_pct"] for r in fs if r["reliable"] and r["ref_safe"]>=2]
            bvs=[]
            for r in fs:
                if cap=="60" or not r["reliable"]:continue
                other=next(f for f in flows if f["case"]==r["case"] and f["cap"]==cap and f["arm"]!=a)
                if other["reliable"]:bvs.append(pct(r["median_J"] if a=="B" else other["median_J"],other["median_J"] if a=="B" else r["median_J"]))
            ts=[r for r in targets if r["cap"]==cap and r["arm"]==a]
            summary.append(dict(cap=cap,arm=a,safe=sum(f["safe"] for f in fs),runs=len(rs),reliable=sum(f["reliable"] for f in fs),
                          common_reliable=len(bvs),mean_B_vs_A_pct=sum(bvs)/len(bvs) if bvs else None,max_B_vs_A_pct=max(bvs,default=None),
                          relative_reference_n=len(gaps),mean_gap_ref_pct=sum(gaps)/len(gaps) if gaps else None,
                          exact_hits=sum(t["status"]=="hit" and not t["tolerance"] for t in ts),
                          relaxed_hits=sum(t["status"]=="hit" and t["tolerance"]>0 for t in ts)))
            keys=("generated","evaluated","legal","propagations","complete_layers","certs","hot_certs","maps","dp_calls","completed_maps","hot_nominated","hot_recovered")
            sums={k:sum(int(r[k]) for r in rs) for k in keys}
            sums.update({k:sum(float(r[k]) for r in rs) for k in ("charged","wall","cpu_s","before_search_s","instance_s","construct_s","search_cert_s","selection_s","handoff_s","dp_s","dp_cert_s","other_s")})
            costs.append(dict(cap=cap,arm=a,max_width=max(int(r["width"]) for r in rs),**sums))
    for name,rows in (("flow_summary",flows),("paired_runs",pairs),("quality_targets",targets),("method_summary",summary),("formal_costs",costs)):put(name,rows)

if __name__=="__main__":
    fixed()
    formal()
