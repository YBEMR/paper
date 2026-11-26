"""Join measured receipts and all ten method pairs; never impute energy for a failed search."""
from collections import Counter,defaultdict
from itertools import combinations
from statistics import mean,median
import csv
import gzip
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data"
METHODS=("NT","NC","ZQ-Beam","LQ-Beam","C2")
CUTS=("W4/K4","10s","30s","60s")


def rows(path):
    opener=gzip.open if path.suffix==".gz" else open
    with opener(path,"rt",newline="",encoding="utf8") as f:
        return list(csv.DictReader(f))


def write(path,records):
    opener=gzip.open if path.suffix==".gz" else open
    with opener(path,"wt",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]),lineterminator="\n")
        w.writeheader();w.writerows(records)


def main():
    folders=sorted((DATA/"evidence").glob("V*"))
    assert len(folders)==14
    out={}
    for name in ("checkpoints","calls","stages","improvements"):
        out[name]=[r for d in folders for r in rows(d/(name+".csv.gz"))]
        write(DATA/(name+(".csv.gz" if name=="calls" else ".csv")),out[name])
    marks=out["checkpoints"]
    lookup={(r["case"],r["method"],r["regime"]):r for r in marks}
    assert len(lookup)==len(marks)==280
    pairs=[]
    for d in folders:
        for regime in CUTS:
            for a,b in combinations(METHODS,2):
                x=lookup[d.name,a,regime];y=lookup[d.name,b,regime]
                pct=None
                if x["SAFE_J"] and y["SAFE_J"]:
                    verdict="win" if float(x["hi"])<float(y["lo"]) else "loss" if float(y["hi"])<float(x["lo"]) else "tie"
                    pct=100*(float(y["SAFE_J"])-float(x["SAFE_J"]))/float(y["SAFE_J"])
                else:
                    verdict="only_left" if x["SAFE_J"] else "only_right" if y["SAFE_J"] else "neither"
                pairs.append(dict(phase=x["phase"],case=d.name,regime=regime,left=a,right=b,left_SAFE_J=x["SAFE_J"],
                                  right_SAFE_J=y["SAFE_J"],result=verdict,saving_pct=pct))
    write(DATA/"paired.csv",pairs)
    combined=[];coverage=[]
    for group in ("all","development8","former_holdout6"):
        for regime in CUTS:
            for a,b in combinations(METHODS,2):
                sub=[p for p in pairs if p["regime"]==regime and p["left"]==a and p["right"]==b and (group=="all" or p["phase"]==group)]
                counts=Counter(p["result"] for p in sub)
                vals=[p["saving_pct"] for p in sub if p["saving_pct"] is not None]
                combined.append(dict(sample=group,regime=regime,left=a,right=b,
                    **{key:counts[key] for key in ("win","tie","loss","only_left","only_right","neither")},
                    paired=len(vals),mean_saving=mean(vals) if vals else None,median_saving=median(vals) if vals else None))
            for m in METHODS:
                sub=[x for x in marks if x["regime"]==regime and x["method"]==m and (group=="all" or x["phase"]==group)]
                safe=[x for x in sub if x["SAFE_J"]]
                coverage.append(dict(sample=group,regime=regime,method=m,SAFE=len(safe),n=len(sub),rate=len(safe)/len(sub),
                         completed=sum(int(x["completed"]) for x in sub),safe_calls=sum(int(x["SAFE"]) for x in sub),
                         median_first_SAFE_s=median(float(x["first_SAFE_s"]) for x in safe) if safe else None,
                         median_elapsed_s=median(float(x["elapsed_s"]) for x in sub),
                         median_build_sort_s=median(float(x["build_sort_s"]) for x in sub),
                         median_cert_write_s=median(float(x["cert_write_s"]) for x in sub)))
    write(DATA/"summary.csv",combined);write(DATA/"coverage.csv",coverage)
    decisions=[p for d in folders for p in rows(DATA/"pools"/d.name/"comparisons.csv.gz")]
    seat_stats=[]
    for scope in ("parent","actual_pool"):
        for a,b in combinations(METHODS[:4],2):
            sub=[p for p in decisions if (p["scope"],p["left"],p["right"])==(scope,a,b)]
            seat_stats.append(dict(scope=scope,left=a,right=b,pools=len(sub),first_two_changed=0,
                         **{k:sum(p[k]=="True" for p in sub) for k in ("comparable3","changed3","comparable4","changed4","changed_set","change_from_third_exclusion","change_from_composite_risk")}))
    write(DATA/"seat_summary.csv",seat_stats)
    parents=[r for d in folders for r in rows(DATA/"pools"/d.name/"generation.csv.gz")]
    wider=[r for d in folders for r in rows(DATA/"pools"/d.name/"all_width_parent_fingerprints.csv.gz")]
    wst=[r for d in folders for r in rows(DATA/"pools"/d.name/"all_width_stages.csv.gz")]
    import os
    raw=Path(os.environ.get("M1H_OUTPUT",ROOT/"raw"))
    environments=[json.loads(f.read_bytes()) for f in sorted(raw.glob("lane*/engine/environment.json"))]
    assert len(environments)==len({r["core"] for r in environments})==7
    (DATA/"environment.json").write_text(json.dumps(environments,indent=2)+"\n")
    receipt=dict(runs=70,budget_core_s=4200,checkpoints=len(marks),pair_rows=len(pairs),actual_calls=len(out["calls"]),
                 timely_calls=sum(r["on_time"]=="True" for r in out["calls"]),incumbent_updates=len(out["improvements"]),
                 unique_case_plans=sum(len(rows(d/"traces.csv.gz")) for d in folders),
                 actual_wall_sum_s=sum(float(r["actual_stop_s"]) for r in marks if r["regime"]=="60s"),
                 W4_distinct_parent_windows=len(parents),W4_shared_parent_windows=sum("/" in r["observed"] for r in parents),
                 W4_proposals=sum(int(r["candidates"]) for r in parents),W4_valid=sum(int(r["valid"]) for r in parents),
                 W4_timing_reject=sum(int(r["timing"]) for r in parents),W4_duplicate=sum(int(r["duplicate"]) for r in parents),
                 all_width_unique_parent_windows=len(wider),all_width_shared_by_at_least_two=sum(int(r["distinct_methods"])>=2 for r in wider),
                 all_width_stage_records=len(wst),all_width_open_pools=sum(int(r["complete_open"]) for r in wst),
                 all_width_terminal_pools=sum(int(r["complete_terminal"]) for r in wst))
    (DATA/"audit.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(receipt)


if __name__=="__main__":
    main()
