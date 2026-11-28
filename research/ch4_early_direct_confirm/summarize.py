"""Report denominators and paired times with positive savings for the early route."""
import json
from statistics import mean,median
from collections import Counter
from compare import read,OUT
def vals(rows,k):return [float(r[k]) for r in rows if r.get(k) not in ("",None)]
def med(v):return median(v) if v else None
def main():
    cells,flows,pairs,ep,slots,trades=[read(k) for k in ("cells","flow_summary","paired","early_events","mapping_slots","search_tradeoffs")]
    reliable={c for c in {r["case"] for r in flows} if all(r["reliable"]=="1" for r in flows if r["case"]==c)}
    f={arm:{r["case"]:r for r in flows if r["arm"]==arm} for arm in "ABR"}
    result={}
    for arm in "ABR":
        part=[r for r in cells if r["arm"]==arm]
        result[arm]=dict(safe=sum(map(int,(r["safe"] for r in part))),reliable=sum(int(r["reliable"]) for r in f[arm].values()),
            first_median=med(vals(part,"first")),ref_gap=mean(float(f[arm][c]["gap_percent"]) for c in reliable) if reliable else None,
            strict=sum(int(r["strict"]) for r in f[arm].values()),tolerance=sum(int(r["tolerance"]) for r in f[arm].values()),
            tail_completed=sum(vals(part,"tail_finished")),generated=sum(vals(part,"generated")),search_certs=sum(vals(part,"search_certs")))
    result["pairs"]={}
    for key in ("strict","tolerance"):
        x=vals(pairs,key+"_B_minus_A_s")
        result["pairs"][key]=dict(counts=Counter(p[key+"_which"] for p in pairs),median_B_minus_A_s=med(x),B_earlier=sum(v<0 for v in x),A_earlier=sum(v>0 for v in x))
    diffs={c:100*(float(f["B"][c]["median_J"])/float(f["A"][c]["median_J"])-1) for c in sorted(reliable)}
    result["energy"]=dict(wins=Counter(p["interval_winner"] for p in pairs),by_flow_pct=diffs,mean_pct=mean(diffs.values()) if diffs else None)
    result["early"]=dict(triggered=len(ep),finished=sum(vals(ep,"stage_complete")),improved=len(vals(ep,"strict_gain_J")),median_s=med(vals(ep,"occupied_s")),
            direct_gains_J=vals(ep,"strict_gain_J"),after_resume_certs=sum(vals(ep,"remaining_search_certs")),all_resumed_more=sum(x>0 for x in vals(ep,"remaining_search_certs")),
            matched_instant_better=sum(x<0 for x in vals(trades,"B_minus_A_at_early_J")),max_slots=max(Counter((r["arm"],r["case"],r["rep"]) for r in slots).values()))
    (OUT/"summary.json").write_bytes((json.dumps(result,indent=2)+"\n").encode("utf8"))
    print(json.dumps(result,indent=2))
if __name__=="__main__":main()
