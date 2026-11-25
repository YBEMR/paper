"""Read-only exact matching of proposed and AB rounds that share the same predecessor and target."""
from analyze import ROOT,RUNS,lines,save,compare
def main():
    pairs=[]
    for folder in sorted(RUNS.glob("*_Proposed_*")):
        other=folder.with_name(folder.name.replace("_Proposed_","_AB_"))
        if not all((d/"receipt.json").exists() for d in (folder,other)):continue
        def key(r):
            return (r["turn"],r["before"]["plan"],tuple((j,tuple(v)) for j,v in r["target"]),len(r["scope"]))
        ab={key(r):r for r in lines(other/"rounds.jsonl") if r["phase"]=="configuration"}
        for p in lines(folder/"rounds.jsonl"):
            if p["phase"]!="configuration" or key(p) not in ab:continue
            a=ab[key(p)];picked={f["selected"] for f in p["feedback"] if f["selected"] is not None}
            actual={j for j,old,new in p["real_changes"] if old!=new}
            result=folder.name.split("_")
            pairs.append(dict(batch=result[0],case=result[1],seed=result[-1],turn=p["turn"],common_predecessor=p["before"]["plan"],
                         target_class=p["target_type"],target_ids=" ".join(str(j) for j,v in p["target"]),size=len(p["scope"]),
                         exchanged_into_scope=" ".join(map(str,sorted(set(p["scope"])-set(a["scope"])))),
                         realized_extra_compensators=" ".join(map(str,sorted((picked & actual)-set(a["scope"])))),
                         ab_status=a["solver"]["status"],pro_status=p["solver"]["status"],
                         ab_after=a["after"]["J"],pro_after=p["after"]["J"],difference_J=a["after"]["J"]-p["after"]["J"],
                         interval_verdict=compare(a["after"],p["after"])))
    save("matched_rounds.csv",pairs)
if __name__=="__main__":main()
