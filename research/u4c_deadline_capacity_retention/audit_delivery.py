"""Check disjoint same-core clocks and reconstruct per-layer survival of the actual first seed."""
import csv
import gzip
import json
from collections import defaultdict
from foundation import *
from pack_c import table

def main():
    timings=[];survival=[];lane=defaultdict(list)
    for k in cases():
        root=HOME_C/"results"/k
        physics={rec["certificate"]["plan_sha256"]:u.encoded(x[:2] for x in rec["plan"]["rows"][1::3])
                 for rec in map(json.loads,gzip.decompress((root/"physical/plans.jsonl.gz").read_bytes()).splitlines())}
        control=read(root/"diagnostics/Control-retention.json")
        for p in sorted((root/"runs").glob("*.json")):
            m=p.stem;r=read(p);raw=OUT_C/(k+"-"+m);start=read(raw/"start.json")["start"]
            cohort="initial" if k in FOUR else "check"
            end=start+r["wall_s"];cpu=r["receipt"]["cpu"]
            timings.append(dict(case=k,arm=m,cohort=cohort,cpu=cpu,start_monotonic=start,
                eligible_end=end,cap=r["receipt"]["cap"],external_kill=r["receipt"]["external_kill"],process_s=r["receipt"]["process_s"],
                warm_s=r["warm"]["warm_s"],first_s=r["delivered"][0]["t"] if r["delivered"] else None))
            lane[cpu].append((start,end))
            if r["delivered"] and r["delivered"][0]["phase"]=="terminal":
                cfg=physics[r["delivered"][0]["plan"]].hex()
                rank=lambda v:next((i for i,c in enumerate(v["observed_choices"],1) if cfg.startswith(c)),None)
                own=read(root/"diagnostics"/(m+"-retention.json"))
                survival.append(dict(case=k,arm=m,seed=r["delivered"][0]["plan"],
                    first_absent_in_control=next((x["window"] for x in control if not x["empty_extension"] and rank(x) is None),None),
                    own_ranks=" ".join(str(rank(x)) for x in own),control_ranks=" ".join(str(rank(x)) for x in control)))
    for clocks in lane.values():
        clocks.sort()
        assert all(a[1]<=b[0] for a,b in zip(clocks,clocks[1:]))
    for arms in (["Control"],list(ARMS)):
        subset=[r for r in timings if r["arm"] in arms]
        assert max(r["eligible_end"] for r in subset if r["cohort"]=="initial")<=min(r["start_monotonic"] for r in subset if r["cohort"]=="check")
    table("timing",timings);table("seed_survival",survival)
if __name__=="__main__":main()
