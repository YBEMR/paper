"""Matched, equal-flow development statistics. Energy gaps are undefined for failed cells."""
import csv,json,statistics as st
from pathlib import Path
from collections import Counter
HERE=Path(__file__).resolve().parent;tab=HERE/"tables"
def read(name):
    with (tab/(name+".csv")).open(encoding="utf8",newline="") as f:return list(csv.DictReader(f))
def mean(v):return st.mean(v) if v else None
def med(v):return st.median(v) if v else None
def main():
    cells=read("cells");flows=read("flows");paired=read("matched_quality");fixed=read("fixed_work")
    assert len({(r["case"],r["rep"],r["cap"],r["arm"]) for r in cells})==len(cells)==144
    arms=[];pairs=[]
    for cap in ("10","20"):
        subset=[r for r in flows if r["cap"]==cap];shared=[r for r in subset if min(int(r["B_n"]),int(r["C_n"]))>=2]
        for m in "BC":
            rr=[r for r in cells if r["arm"]==m and r["cap"]==cap]
            reliable=[r for r in subset if int(r[m+"_n"])>=2]
            good=[r for r in rr if r["safe"]=="1"]
            d=dict(cap=cap,arm=m,success=len(good),reliable=len(reliable),
               failed=[r["case"] for r in subset if int(r[m+"_n"])<2],
               gap_pct=mean([float(r[m+"_loss_pct"]) for r in reliable]),
               gap_shared_pct=mean([float(r[m+"_loss_pct"]) for r in shared]),common=len(shared),
               first_med_s=med([float(r["first_safe_s"]) for r in good]),final_med_s=med([float(r["best_s"]) for r in good]),
               dp_gain_sum_J=sum(float(r["global_dp_gain_J"]) for r in good),
               dp_improved=sum(float(r["global_dp_gain_J"])>1e-7 for r in good))
            for field in ("generator_s","calibration_s","fifo_s","pilot_fifo_s","heat_s","search_cert_s","dp_returned_s","dp_cert_s","slots","predict","cert_count","total_s","build_s"):
                d[field]=sum(float(r[field]) for r in rr)
            arms.append(d)
        both=[r for r in paired if r["cap"]==cap and r["common_upper"]]
        faster=[float(r["C_s"])<float(r["B_s"]) for r in both]
        prices=[(float(r["C_J"])/float(r["B_J"])-1)*100 for r in shared]
        signs=Counter()
        for case in {r["case"] for r in cells}:
            for rep in ("1","2","3"):
                b,c=[next(r for r in cells if (r["case"],r["rep"],r["cap"],r["arm"])==(case,rep,cap,m)) for m in "BC"]
                if b["safe"]==c["safe"]=="1":
                    signs["C_lower" if float(c["upper"])<float(b["lower"]) else "B_lower" if float(b["upper"])<float(c["lower"]) else "overlap"]+=1
        pairs.append(dict(cap=cap,common=len(shared),C_minus_B_pct=mean(prices),paired_both=len(both),
            faster_C=sum(faster),median_C_minus_B_s=med([float(r["C_s"])-float(r["B_s"]) for r in both]),
            C_meets_B=sum(bool(r["C_meets_B_s"]) for r in both),B_meets_C=sum(bool(r["B_meets_C_s"]) for r in both),**signs))
    micro=[]
    for k in ("A01","C10"):
        for m in "BC":
            group=[r for r in fixed if r["arm"]==m and r["case"]==k];assert len(group)==4
            v={field:med([float(r.get(field) or 0) for r in group]) for field in ("elapsed","slots","predict","fifo_calls","pilot_fifo_calls","calibration_s","fifo_s","pilot_fifo_s","heat_s","generator_s")}
            micro.append(dict(case=k,arm=m,ordinary_fifo_s=v["fifo_s"]-v["pilot_fifo_s"],**v))
    (tab/"decision_metrics.json").write_text(json.dumps(dict(arms=arms,pairs=pairs,fixed=micro),indent=1)+"\n",encoding="utf8")
if __name__=="__main__":main()
