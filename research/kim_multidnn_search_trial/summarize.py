"""Read-only postprocessing. Derive counts from the recorded, within-deadline events."""
import csv
import hashlib
import io
import json
from pathlib import Path
import statistics
import tarfile
import gzip

HERE=Path(__file__).resolve().parent
RAW=HERE/"raw"
OUT=HERE/"results"
OUT.mkdir(exist_ok=True)
def read(path):
    return json.loads(path.read_bytes())
def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
def sha(data):
    return hashlib.sha256(data).hexdigest()
def save_csv(name,rows):
    if not rows:
        return
    with (OUT/name).open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

def collect():
    design=read(HERE/"design.json")
    ledger=[json.loads(line) for line in (RAW/"ledger.jsonl").read_bytes().splitlines()]
    reserved=[r for r in ledger if r["event"]=="reserve"]
    closed=[r for r in ledger if r["event"]=="close"]
    assert len({r["id"] for r in reserved})==len(reserved)
    rows=[]
    checks=[]
    deadlines=[]
    maps={}
    subject=None
    for job in design["jobs"]:
        folder=RAW/job["id"]
        if not (folder/"result.json").is_file():
            continue
        run=read(folder/"result.json")
        subject=run["preregistration"]
        lines=(folder/"events.jsonl").read_bytes().splitlines(keepends=True)
        events=[json.loads(x) for x in lines if x.endswith(b"\n")]
        deadlines.append(dict(id=job['id'],cap_s=job['cap'],process_to_reap_s=run['process_wall_s'],
            supervisor_cut=run['supervisor_cut'],last_raw_event_s=events[-1]['t'] if events else None,
            late_complete_events=sum(x['t']>job['cap'] for x in events),
            incomplete_last_line=bool(lines and not lines[-1].endswith(b'\n')),
            process_over_cap_s=max(0.,run['process_wall_s']-job['cap'])))
        events=[x for x in events if x["t"]<=job["cap"]]
        assert all(r["t"]>=l["t"] for l,r in zip(events,events[1:]))
        full=[x for x in events if x["kind"]=="full_replay"]
        for x in full:
            p=x["choice"]["physical"]
            assert p["fully_replayed"] and p["deadline_ok"] and p["required"]==p["completed"]==500
            assert p["feasible"]==(p["thermal_status"]=="SAFE")
            if p["feasible"]:
                assert max(p["peak_upper_c"])<=80
            assert abs(p["energy_j"]-x["choice"]["predicted_j"])<=1e-7
        stats=run["stats_last_checkpoint"]
        assert stats.get("scene_requests",0)==stats.get("hits",0)+stats.get("misses",0)
        if run["stage"]=="e0":
            checks.append(dict(id=job["id"],status=run["status"],wall_s=run["process_wall_s"],
                verified_policies=len(full),fallback_dispatches=sum(x["kind"]=="policy_fallback" for x in events),
                physical_statuses=[x["choice"]["physical"]["thermal_status"] for x in full],
                fixtures=[x for x in events if x["kind"] in ("fixture","fixture_counters")]))
            continue
        complete=[r for r in events if r["kind"]=="deployment"]
        by_dep={r["deployment"]:r for r in complete if r["phase"]!="fallback"}
        maps[job["id"]]=by_dep
        if run["certificate_scope"]=="catalog":
            assert run["completed"]==81
        best=run["best_safe_j"]
        lb=run["catalog_lower_bound_j"]
        if best is not None and lb is not None:
            assert lb<=best+1e-7
        rows.append(dict(id=job["id"],case=job["case"],stage=job["stage"],method=job["method"],
            status=run["status"],cap_s=job["cap"],wall_s=run["process_wall_s"],
            first_safe_s=run["first_safe_s"],certificate_s=run["certified_s"],scope=run["certificate_scope"],
            best_safe_j=best,lower_bound_catalog_j=lb,gap_j=best-lb if best is not None and lb is not None else None,
            peak_upper_c=run["best_peak_upper_c"],winner=run["best_choice"]["deployment"] if best is not None else None,
            code=run["best_choice"]["code"] if best is not None else None,
            completed=run["completed"],logical_codes=run["complete_logical_codes"],
            legal_codes=run["deadline_legal_covered"],scene_requests=stats.get("scene_requests",0),
            hits=stats.get("hits",0),legal_hits=stats.get("legal_hits",0),deadline_hits=stats.get("deadline_hits",0),
            compiles=stats.get("compiles",0),compile_integrals=stats.get("compile_integrations",0),
            schedule_s=stats.get("schedule_s",0.),compile_s=stats.get("compile_s",0.),key_s=stats.get("key_s",0.),
            affine_search_s=stats.get("affine_search_s",0.),constrained_search_s=stats.get("constrained_search_s",0.),
            envelope_s=stats.get("envelope_s",0.),fallback_integral_s=stats.get("fallback_integral_s",0.),
            screen_entries_completed_batches=stats.get("screen_entries_live",0),
            fallback_integrals_completed_batches=stats.get("fallback_integrals_live",0),
            certificate_replays=len(full),certification_s=stats.get("safe_replay_s",0.),
            policy_fallbacks=sum(x["kind"]=="policy_fallback" for x in events),
            cold_warmup_s=next((x["wall_s"] for x in events if x["kind"]=="cold_warmup"),None),
            archive_check_s=stats.get("archive_check_s",0.),array_io_s=stats.get("array_io_s",0.),
            peak_rss_mib=run["peak_rss_bytes"]/2**20,uncheckpointed_wall_s=run["uncheckpointed_wall_s"],
            comparisons_with_archived_arrays=sum(x["max_archive_error_j"] is not None for x in by_dep.values()),
            max_archive_error_j=max((x["max_archive_error_j"] for x in by_dep.values() if x["max_archive_error_j"] is not None),default=None)))
    paired=[]
    for left in [r for r in rows if r["method"]=="M1"]:
        rid=left["id"].replace("M1","M2")
        right=next((r for r in rows if r["id"]==rid),None)
        if right is None:
            continue
        common=maps[left["id"]].keys() & maps[rid].keys()
        if left["stage"]=="fixed":
            assert len(common)==len(design["fixed_subset"])
        # Identical coefficients and clock arithmetic should give identical energy bytes.
        match=sum(maps[left["id"]][d]["energy_sha256"]==maps[rid][d]["energy_sha256"] for d in common)
        assert match==len(common),(left["id"],match,len(common))
        if left["scope"] and right["scope"] and left["scope"]==right["scope"]:
            assert abs(left["best_safe_j"]-right["best_safe_j"])<=1e-7
        equal_work=bool(left["scope"] and left["scope"]==right["scope"])
        paired.append(dict(case=left["case"],stage=left["stage"],left=left["id"],right=rid,
            common_deployments=len(common),byte_equal_energy_arrays=match,
            coverage_M1=left["completed"],coverage_M2=right["completed"],
            same_certificate=equal_work,compile_count_M1=left["compiles"],compile_count_M2=right["compiles"],
            compile_seconds_M1=left["compile_s"],compile_seconds_M2=right["compile_s"],
            compile_seconds_saved_same_work=left["compile_s"]-right["compile_s"] if equal_work else None,
            compiles_saved_same_work=left["compiles"]-right["compiles"] if equal_work else None,
            saved_work_within_M2_legal_hits=right["legal_hits"],
            total_seconds_saved_same_work=left["wall_s"]-right["wall_s"] if equal_work else None,
            total_speed_ratio_same_work=left["wall_s"]/right["wall_s"] if equal_work else None,
            certificate_seconds_M1=left["certificate_s"],certificate_seconds_M2=right["certificate_s"]))
    save_csv("run_metrics.csv",rows)
    save_csv("paired_comparison.csv",paired)
    write(OUT/"e0.json",checks)
    write(OUT/"deadline_audit.json",deadlines)
    budget=dict(preregistered_sha=subject,reserved_s=sum(x["cap_s"] for x in reserved),
                actual_process_wall_s=sum(x["actual_s"] for x in closed),cap_s=3840,
                reserved_slots=len(reserved),closed_slots=len(closed),stages={})
    for stage in ("e0","fixed","dev","holdout"):
        ids={j["id"] for j in design["jobs"] if j["stage"]==stage}
        budget["stages"][stage]=dict(slots=sum(x["id"] in ids for x in closed),
            reserved_s=sum(x["cap_s"] for x in reserved if x["id"] in ids),
            actual_wall_s=sum(x["actual_s"] for x in closed if x["id"] in ids))
    assert budget["reserved_s"]<=3840
    write(OUT/"budget.json",budget)
    return rows,paired,budget

def seal():
    # Bundle original byte streams and any interrupted final lines/unfinished NPZ verbatim.
    # Reproducible tar metadata; split large bundles for transport only.
    hashes=[]
    for path in sorted(x for x in RAW.rglob("*") if x.is_file()):
        data=path.read_bytes()
        hashes.append(dict(path=path.relative_to(HERE).as_posix(),size=len(data),sha256=sha(data)))
    write(OUT/"raw_sha256.json",hashes)
    for kind in ("logs","arrays"):
        paths=[x for x in hashes if x["path"].endswith(".npz")== (kind=="arrays")]
        if not paths:
            continue
        primary={}
        duplicates={}
        packed=io.BytesIO()
        with gzip.GzipFile(fileobj=packed,mode="wb",mtime=0) as gz:
            with tarfile.open(fileobj=gz,mode="w|") as tar:
                for item in paths:
                    if kind=="arrays" and item["sha256"] in primary:
                        duplicates[item["path"]]=primary[item["sha256"]]
                        continue
                    primary[item["sha256"]]=item["path"]
                    b=(HERE/item["path"]).read_bytes()
                    info=tarfile.TarInfo(item["path"])
                    info.size=len(b)
                    tar.addfile(info,io.BytesIO(b))
        data=packed.getvalue()
        parts=[]
        for i in range(0,len(data),524288):
            name=kind+f".{i//524288:03d}.gz"
            content=data[i:i+524288]
            (OUT/name).write_bytes(content)
            parts.append(dict(name=name,bytes=len(content),sha256=sha(content)))
        write(OUT/(kind+"_index.json"),dict(format="Concatenate chunks in listed order to obtain a tar.gz.",
            files=len(paths),identical_files=duplicates,whole_sha256=sha(data),bytes=len(data),parts=parts))
if __name__=="__main__":
    import sys
    rows,pairs,budget=collect()
    if "--seal" in sys.argv:
        assert (RAW/"stop.json").exists()
        seal()
    print(json.dumps(dict(rows=len(rows),pairs=len(pairs),budget=budget)))
