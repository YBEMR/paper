"""Audit archived curves and repeat stability independently of the aggregation pass."""
import csv
import gzip
import io
import itertools
import json
import statistics
import tarfile
from pathlib import Path
from analyze import DATA,readcsv,write
from design import ROOT,REG,METHODS,sha,write_json

def main():
    cases=json.loads((REG/"cases.json").read_bytes())["cases"]
    rot=readcsv(REG/"rotation.csv")
    marks={(r["case"],r["method"],int(r["repeat"]),r["regime"]):r for r in readcsv(DATA/"repetitions.csv")}
    changes=readcsv(DATA/"improvements.csv")
    by={}
    for r in changes:by.setdefault((r["case"],r["method"],int(r["repeat"])),[]).append(r)
    stable=[];unique=0;calls=0;volume_bytes=0;physical_plans=0;total_steps=0
    frozen=sha((REG/"source_hashes.json").read_bytes())
    env=[json.loads(f.read_bytes()) for f in sorted((DATA/"environment").glob("lane*.json"))]
    assert len(env)==8 and len({r["core"] for r in env})==8
    assert all(set(r["threads"].values())=={"1"} and r["verified_manifest"]==frozen for r in env)
    for c in cases:
        case=c["case"];dst=DATA/"evidence"/case
        receipt=json.loads((dst/"receipt.json").read_bytes())
        for name,digest in receipt["files"].items():assert sha((dst/name).read_bytes())==digest
        event=json.loads((dst/"event_volume.json").read_bytes())
        assert event["verified_unique_plans"]==receipt["unique_plans"]
        volume_bytes+=event["bytes"]
        with gzip.open(dst/"event_index.csv.gz","rt") as f:
            index={r["plan"]:r for r in csv.DictReader(f)}
        assert len(index)==receipt["unique_plans"];physical_plans+=len(index)
        with tarfile.open(dst/"runs.tar.xz") as tar:
            assert len(tar.getnames())==12
            for m in METHODS:
                fix=[];winners=[];energy=[];fc=[];suffix=[]
                for rep in (1,2,3):
                    key=case,m,rep
                    run=json.load(tar.extractfile(f"r{rep}-{m}/run.json"))
                    records=run["records"];calls+=len(records)
                    ips=[i for i,r in enumerate(records) if r["end_s"]<=60]
                    assert ips==list(range(len(ips)))
                    assert all(r["cert"]["plan_sha256"] in index for r in records)
                    fixed=[r for r in records if r["width"]==4 and r["end_s"]<=60][:4]
                    assert [r["rank"] for r in fixed]==list(range(1,1+len(fixed)))
                    fix.append(tuple(r["cert"]["plan_sha256"] for r in fixed));fc.append(len(fixed))
                    expected=[];current=None
                    for r in records:
                        cert=r["cert"];v=cert["metrics"]
                        if v["status"]=="SAFE" and r["end_s"]<=60 and (current is None or v["E_J"]<current):
                            current=v["E_J"];expected.append((r["end_s"],current,cert["plan_sha256"]))
                    seen=[(float(r["t_s"]),float(r["E_J"]),r["plan"]) for r in by.get(key,[])]
                    assert expected==seen;total_steps+=len(seen)
                    for cut in ("W4/K4","10s","30s","60s"):
                        sample=fixed if cut=="W4/K4" else [r for r in records if r["end_s"]<=float(cut[:-1])]
                        safe=[r for r in sample if r["cert"]["metrics"]["status"]=="SAFE"]
                        cached=marks[(*key,cut)]
                        assert int(cached["certs"])==len(sample) and int(cached["SAFE_calls"])==len(safe)
                        if safe:
                            best=min(safe,key=lambda r:r["cert"]["metrics"]["E_J"])
                            assert cached["plan"]==best["cert"]["plan_sha256"]
                            assert float(cached["first_SAFE_s"])==safe[0]["end_s"]
                            assert float(cached["SAFE_J"])==best["cert"]["metrics"]["E_J"]
                        else:assert not cached["plan"] and not cached["SAFE_J"]
                    winners.append(marks[(*key,"60s")]["plan"] or "NO_SAFE")
                    if current is not None:energy.append(current)
                stable.append(dict(case=case,group=c["group"],ambient=c["ambient"],method=m,
                           fixed_four_every_time=all(n==4 for n in fc),same_fixed_plan_list=len(set(fix))==1,
                           same_60s_winner_or_failure=len(set(winners))==1,success_60s=len(energy),
                           min_SAFE_J=min(energy) if energy else None,median_SAFE_J=statistics.median(energy) if energy else None,
                           max_SAFE_J=max(energy) if energy else None))
    summary=json.loads((DATA/"batch_receipt.json").read_bytes())
    assert calls==summary["issued_certificates"] and total_steps==summary["incumbent_steps"]
    assert len(marks)==768 and len(rot)==192
    write(DATA/"repeat_stability.csv",stable)
    write_json(DATA/"verification.json",dict(physical_plans=physical_plans,checked_certificates=calls,
        checked_checkpoints=len(marks),checked_improvements=total_steps,case_methods=len(stable),
        exact_W4_lists_across_three=sum(r["same_fixed_plan_list"] for r in stable),
        same_60s_winner_or_failure=sum(r["same_60s_winner_or_failure"] for r in stable),
        total_original_event_volume_bytes=volume_bytes,thread_sets_checked=len(env)))
if __name__=="__main__":main()
