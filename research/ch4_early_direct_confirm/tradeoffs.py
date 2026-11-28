"""Compare actually reached mappings and best delivered energy at the early delivery time."""
from compare import read,write
def main():
    certs,steps,slots,cells,episodes=[read(name) for name in ("certificates","steps","mapping_slots","cells","early_events")]
    result=[]
    for b in (r for r in cells if r["arm"]=="B"):
        def rows(table,arm):return [r for r in table if r["arm"]==arm and r["case"]==b["case"] and r["rep"]==b["rep"]]
        def before(items,t):return next((r for r in reversed(items) if t is not None and float(r["t"])<=t),{})
        a=rows(cells,"A")[0]
        ae,be=rows(steps,"A"),rows(steps,"B")
        ev=next(iter(rows(episodes,"B")),{})
        direct=next((r for r in rows(certs,"B") if r["stream"]=="early"),{})
        ts=float(direct["t"]) if direct else None
        x,y=before(ae,ts),before(be,ts)
        sa=[r for r in rows(certs,"A") if r["stream"]=="search"]
        sb=[r for r in rows(certs,"B") if r["stream"]=="search"]
        lcp=0
        for one,two in zip(sa,sb):
            if one["plan"]!=two["plan"]:break
            lcp+=1
        a_map=ae[-1]["mapping"] if ae else None
        bmaps=set(r["mapping"] for r in sb)
        bslots=rows(slots,"B")
        result.append(dict(case=b["case"],rep=b["rep"],triggered=b["triggered"],early_receipt_s=ts,
             A_J_at_B_early=x.get("J"),B_J_at_B_early=y.get("J"),B_minus_A_at_early_J=float(y["J"])-float(x["J"]) if x and y else None,
             B_early_strict_gain_J=ev.get("strict_gain_J"),A_final_stage=a["final_stage"],B_final_stage=b["final_stage"],
             common_raw_certificate_prefix=lcp,A_raw_certs=len(sa),B_raw_certs=len(sb),B_certs_after_resume=b["search_after_resume"],
             A_generated=a["generated"],B_generated=b["generated"],A_final_mapping=a_map,A_final_mapping_raw_seen_by_B=int(a_map in bmaps) if a_map else None,
             A_final_mapping_nominated_by_B=int(any(r["mapping"]==a_map for r in bslots)) if a_map else None,
             A_final_mapping_optimized_by_B=int(any(r["mapping"]==a_map and r["finished"]=="1" for r in bslots)) if a_map else None))
    write("search_tradeoffs",result)
if __name__=="__main__":main()
