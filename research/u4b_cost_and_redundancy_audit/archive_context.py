"""Read already published sibling results and join by exact ordered candidate identities."""
import csv
import gzip
import json
from collections import Counter
from pathlib import Path
from archive_audit import A, OUT, LAB, FOCUS, sha, read, table, ledger

def verify_sources_and_nt():
    b=LAB/"U3b_worktree/research/u3b_blockage_triggered_quota"
    source=read(b/"registration/frozen_sources.json"); checked=Counter()
    for v in source["files"]:
        f=LAB/"U3a_inputs"/v["tree"]/v["path"]
        assert sha(f.read_bytes())==v["sha256"]
        checked[v["tree"]]+=1
    assert source["pins"]==read(A/"registration/source_check.json")["pins"]
    (OUT/"verified_frozen_inputs.json").write_text(json.dumps(dict(counts=checked,pins=source["pins"],
                                  manifest_sha256=sha((b/"registration/frozen_sources.json").read_bytes())),indent=1)+"\n")
    work=[]
    for folder in sorted((A/"results").glob("I*")):
        for m in ("NT10","NT60"):
            run=read(folder/"runs"/(m+".json")); groups={}
            for e in ledger(folder,run):
                if e[0]=="delivered" and e[2]<=run["receipt"]["cap"]:
                    break
                if e[0]=="nt_actions":
                    j,_,_,_,_,_,h,pilot,_,status=e[2][:10]
                    k=(e[1],j)
                    if k not in groups:
                        groups[k]=[set(),Counter()]
                    seen,c=groups[k]
                    c.update(attempts=1,repeat_code=int(h in seen),generator_duplicate=int(status=="duplicate"),
                             timing_reject=int(status=="timing"),pilot=int(pilot))
                    seen.add(h)
            for (w,j),(seen,counts) in groups.items():
                work.append(dict(case=folder.name,method=m,width=w,window=j,unique=len(seen),**counts))
    table("nt_candidate_identity",work)

def context():
    def csvrows(name):
        with (OUT/(name+".csv")).open(encoding="utf8") as f:
            return list(csv.DictReader(f))
    other=LAB/"U4b_worktree/research/u4b_prefix_quota_diagnostic"
    manifest={}
    def load(p):
        buf=p.read_bytes()
        manifest[str(p.relative_to(other)).replace("\\","/")]=sha(buf)
        return json.loads(buf)
    pools=json.loads(gzip.decompress((OUT/"base_pools.json.gz").read_bytes()))
    evidence=[]; boundary=[]
    for case in sorted(FOCUS):
        p=other/"offline"/case
        old=load(p/"audit.json"); term=load(p/"terminal_evidence.json")
        assert [v["config"] for v in term["complete"]]==pools[case]["ranked"]
        extra={v["rank"]:v for v in load(p/"residual.json")} if (p/"residual.json").exists() else {}
        for v in term["complete"]:
            matches=v["matches"]; code=bytes.fromhex(v["config"])
            proofs=term["proofs"]; rank=v["rank"]
            assert all(code.startswith(bytes.fromhex(proofs[h]["settled_action"])) for h in matches)
            assert not (matches and rank in extra)
            r=extra.get(rank)
            evidence.append(dict(case=case,rank=rank,config=sha(code),prior_physical_HOT_witnesses=matches,
                                 full_certificate=(r or {}).get("plan"),full_status=r["metrics"]["status"] if r else "",
                                 source=(r or {}).get("origin"),outside_current_run=True))
        first=old["first_loss"]
        boundary.append(dict(case=case,last_layer=old["layers"][-1]["window"],legal=old["terminal_distinct"],
                             pool_proved=sum(bool(v["matches"]) for v in term["complete"]),
                             extra_statuses=dict(Counter(r["metrics"]["status"] for r in extra.values())),
                             long_reference_final_plan=old["NT60"],first_loss_window=first["window"],
                             loss=first["loss"],parent_present=first["actual_parent"],violation_ticks=first["late"]))
    (OUT/"other_batch_sources.json").write_text(json.dumps(dict(commit="c6d1a32f0dc378b80130a8280aca1b7dd9dd5773",
                                                  sha256=manifest),indent=1)+"\n")
    table("other_batch_coverage",evidence);table("other_batch_path",boundary)
    old=read(A/"registration/nt60_previous.json")
    hist=[]
    for r in old:
        case=r["case"]; cur=read(A/"results"/case/"runs/NT10.json")
        hist.append(dict(case=case,previous_first_s=r["first"]["t"],previous_plan=r["first"]["plan"],
                         previous_archive=r["archive_sha256"],current_NT10_first_s=(cur["delivered"] or [{}])[0].get("t"),
                         current_NT10_plan=(cur["delivered"] or [{}])[0].get("plan"),
                         current_started=cur["started_certificates"],current_actions=cur["counts"].get("nt_actions",0)))
    table("development_timing_context",hist)
    # Post hoc description independent of the strict observable similarity threshold.
    ids={(x["case"],int(x["rank"])):x for x in csvrows("terminal_identities")}
    metrics=[]
    for p in csvrows("terminal_pairs"):
        c=p["case"]; a=ids[c,int(p["rank"])]; b=ids[c,int(p["earlier_rank"])]
        load_a=json.loads(a["gpu_npu_work_ticks"]); load_b=json.loads(b["gpu_npu_work_ticks"])
        metrics.append(dict(case=c,rank=p["rank"],earlier_rank=p["earlier_rank"],
                            same_hot_region=p["same_peak_window"]==p["same_hotspot"]=="True",
                            peak_delta_K=abs(float(p["delta_peak_C"])),
                            max_main_work_difference_in_window_fraction=max(abs(x-y)/10000 for i,j in zip(load_a,load_b)
                                for x,y in zip(i,j)),full_events_equal=a["events"]==b["events"],
                            full_trajectory_equal=a["trajectory"]==b["trajectory"]))
    table("observed_heat_and_load",metrics)
