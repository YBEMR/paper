"""Independent cutoff, artifact and physics checks for the replacement record."""
import csv
import gzip
import hashlib
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

from paths_j import DATA, METHODS, REG, ROOT, WORK, inputs, write_csv, write_json
from analyze_replacement import CUTS, file_hash, members, run_records
from audit_replacement_paths import encode_targets
from adapter import flow


def main():
    volumes=Path(sys.argv[1])
    cases=inputs()
    with (DATA/"repetitions.csv").open() as f:
        marks={(r["case"],r["method"],int(r["repeat"]),r["regime"]):r for r in csv.DictReader(f)}
    medians={}
    with (DATA/"medians.csv").open() as f:
        for r in csv.DictReader(f):
            medians[r["case"],r["method"],r["regime"]]=r
    sample_rows=[];vols=[];stable=[]
    counts=Counter()
    event_hosts=[]
    for i in range(6):
        host=json.loads((DATA/"environment"/f"host{i}.json").read_bytes())
        lane=json.loads((DATA/"environment"/f"lane{i}.json").read_bytes())
        assert host["run_id"]=="45928467468" and host["run_attempt"]=="1"
        assert host["lane"]==lane["lane"]==i and host["core"]==lane["core"]
        assert lane["manifest"]==file_hash(REG/"hashes.json") and set(lane["threads"].values())=={"1"}
        event_hosts.append(host["cpu"])
    for item in cases:
        case=item["case"]
        volume=json.loads((DATA/"evidence"/case/"event_volume.json").read_bytes())
        path=volumes/volume["filename"]
        assert path.stat().st_size==volume["bytes"] and file_hash(path)==volume["sha256"]
        vols.append(dict(case=case,**volume))
        runs=run_records(case)
        catalog={}
        for name,body in members(DATA/"evidence"/case/"physical.tar.xz"):
            if name.endswith("/certificate.json"):
                cert=json.loads(body);cert.pop("cert_s")
                catalog[name.split("/")[0]]=cert
        for method in METHODS:
            fixed_ids=[];final_ids=[]
            for repeat in (1,2,3):
                run=runs[f"r{repeat}-{method}"];records=run["records"]
                for r in records:
                    cert=dict(r["cert"]);cert.pop("cert_s")
                    assert cert==catalog[cert["plan_sha256"]]
                counts["trajectories"]+=1
                counts["calls"]+=len(records)
                counts["late"]+=sum(r["end_s"]>60 for r in records)
                fixed=[r for r in records if r["width"]==4 and r["end_s"]<=60][:4]
                fixed_ids.append(tuple(r["id"] for r in fixed))
                for cut in CUTS:
                    ready=fixed if cut=="W4/K4" else [r for r in records if r["end_s"]<=float(cut[:-1])]
                    safe=[r for r in ready if r["cert"]["metrics"]["status"]=="SAFE"]
                    mark=marks[case,method,repeat,cut]
                    assert int(mark["certs"])==len(ready) and int(mark["SAFE_calls"])==len(safe)
                    counts["checkpoints"]+=1
                    if safe:
                        opt=min(safe,key=lambda r:r["cert"]["metrics"]["E_J"])
                        assert opt["cert"]["plan_sha256"]==mark["plan"]
                        assert opt["cert"]["metrics"]["E_J"]==float(mark["SAFE_J"])
                        assert safe[0]["end_s"]==float(mark["first_SAFE_s"])
                    else:
                        assert not mark["SAFE_J"] and not mark["plan"]
                    if cut=="60s":
                        final_ids.append(mark["plan"] or "NO_SAFE")
            for cut in CUTS:
                vals=[float(r["SAFE_J"]) for n in (1,2,3) if (r:=marks[case,method,n,cut])["SAFE_J"]]
                m=medians[case,method,cut]
                assert int(m["n_SAFE"])==len(vals) and (m["reliable"]=="True")==(len(vals)>=2)
                assert (float(m["SAFE_J"]) if vals else None)==(statistics.median(vals) if vals else None)
            stable.append(dict(case=case,method=method,same_fixed_ids=len(set(fixed_ids))==1,
                               same_60s_result=len(set(final_ids))==1))
        # One original plan per flow, selected by status on a fixed rotation, then original slot order.
        flat=[r for method in METHODS for rep in (1,2,3) for r in runs[f"r{rep}-{method}"]["records"]]
        status=("SAFE","HOT","OUT_OF_MODEL")[item["index"]%3]
        chosen=next((r for r in flat if r["cert"]["metrics"]["status"]==status),flat[0])
        old=chosen["cert"];ident=old["plan_sha256"]
        cfg=encode_targets(case,{ident})[ident]
        obj=flow(item,WORK/"sample-replay"/case)
        new,_=obj.certify(cfg)
        assert new["plan_sha256"]==ident and old["metrics"]["status"]==new["metrics"]["status"]
        def diff(field):
            return abs(old["metrics"][field]-new["metrics"][field])
        delta_peak=max(abs(a-b) for a,b in zip(old["metrics"]["peak_hi"],new["metrics"]["peak_hi"]))
        assert diff("E_J")<1e-8 and delta_peak<1e-8 and diff("min_deadline_slack_ms")<1e-10
        sample_rows.append(dict(case=case,plan=ident,status=old["metrics"]["status"],energy_abs_diff_J=diff("E_J"),
                           peak_abs_diff_C=delta_peak,slack_abs_diff_ms=diff("min_deadline_slack_ms")))
    assert counts["trajectories"]==144 and counts["checkpoints"]==576
    receipt=json.loads((DATA/"batch_receipt.json").read_bytes())
    assert all(receipt[k]==counts[k] for k in ("trajectories","calls","late","checkpoints"))
    write_csv(DATA/"event_volumes.csv",vols)
    write_csv(DATA/"sample_replay.csv",sample_rows)
    write_csv(DATA/"repeat_stability.csv",stable)
    write_json(DATA/"verification.json",dict(**counts,physical_replays=len(sample_rows),event_volumes=len(vols),
               event_volume_bytes=sum(v["bytes"] for v in vols),worker_models=sorted(set(event_hosts)),
               same_fixed_ids=sum(r["same_fixed_ids"] for r in stable),same_60s_result=sum(r["same_60s_result"] for r in stable)))


if __name__=="__main__":
    main()
