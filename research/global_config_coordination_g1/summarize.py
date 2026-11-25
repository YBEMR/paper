"""Read-only analysis of the frozen run, including evidence integrity and interval comparisons."""
import csv
import gzip
import hashlib
import json
from collections import Counter
from fractions import Fraction as Q
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"results"
def read(path):return json.loads(path.read_bytes())
def rows(path):return [json.loads(l) for l in path.read_bytes().splitlines()] if path.exists() else []
def csvout(name,records):
    if not records:return
    cols=list(dict.fromkeys(k for row in records for k in row))
    with (ROOT/name).open("w",newline="",encoding="utf-8") as f:
        cw=csv.DictWriter(f,fieldnames=cols,lineterminator="\n")
        cw.writeheader()
        cw.writerows(records)
def sha(b):return hashlib.sha256(b).hexdigest()
def details(c):
    m=c["metrics"]
    return dict(status=m["status"],SAFE_J=m["E_J"] if m["status"]=="SAFE" else "",E_lo=m["E_bounds"][0],E_hi=m["E_bounds"][1],
                E35_J=c["E35_J"],peak_lower_C=max(m["peak_lo"]),peak_upper_C=max(m["peak_hi"]),deadline_margin_ms=m["min_deadline_slack_ms"],
                activity_J=m["activity_J"],residency_J=m["base_J"],switch_J=m["switch_J"],temperature_J=m["temperature_J"],common_J=m["external_J"],
                switches=m["switch_count"],configuration_counts=json.dumps(c["configuration_counts"],separators=(",",":")))
def main():
    jobs=rows(OUT/"jobs.jsonl")
    refs=rows(OUT/"references.jsonl")
    auto=rows(OUT/"construction.jsonl")
    certs={p.stem:read(p) for p in (OUT/"certificates").glob("*.json")}
    for k,c in certs.items():
        assert c["plan"]==k and sha(gzip.decompress((OUT/"plans"/(k+".json.gz")).read_bytes()))==k
        assert (OUT/"certificates"/(k+".npz")).is_file()
        m=c["metrics"]
        assert m["E_bounds"][0]<=m["E_J"]<=m["E_bounds"][1]
        import numpy as np
        with np.load(OUT/"certificates"/(k+".npz"),allow_pickle=False) as archive:
            tr=archive["events"]
        assert tr.ndim==2 and tr.shape[1]==31 and tr[0,0]==0 and np.all(tr[:,1]>tr[:,0])
        assert np.array_equal(tr[:-1,1],tr[1:,0])
        assert np.allclose(tr[:,26:30].sum(axis=0),m["energy_by_node_J"],atol=1e-10,rtol=1e-11)
        assert abs(tr[-1,1]*.3/10000-m["external_J"])<1e-13
        assert abs(sum(m["energy_by_node_J"])+m["external_J"]-m["E_J"])<1e-10
        if m["status"]=="SAFE":
            assert max(m["peak_hi"])<=80 and min(m["minimum_lo"])>=20
        assert abs(sum(m[a] for a in ("activity_J","base_J","switch_J","temperature_J","external_J"))-m["E_J"])<1e-8
    csvout("references.csv",[dict(case=r["case"],reference=r["name"],idle=r["idle"],plan=r["plan"],**details(certs[r["plan"]]),
                     target_E35_J=r.get("target",""),absolute_error_J=r.get("absolute_error","")) for r in refs])
    csvout("construction.csv",[dict(**{k:r[k] for k in ("case","width","priced","depth","time_s","status")},
               plan=r.get("plan",""),**{k:v for k,v in details(certs[r["plan"]]).items() if k!="status"}) if "plan" in r else r for r in auto])
    summary=[]; seeds={}; extra=rows(OUT/"suffix.jsonl")
    for path in sorted((OUT/"seeds").glob("*.json")):
        case=path.stem;s=read(path);k=s["plan"];seeds[case]=s
        extra_safe=[r for r in extra if case=="D3" and r["status"]=="SAFE"]
        case_best=min([k,*[r["plan"] for r in extra_safe]],key=lambda z:certs[z]["metrics"]["E_bounds"][1])
        summary.append(dict(case=case,role="common_seed",plan=k,source=s.get("name","width "+str(s.get("width",""))),
                        priced=s.get("priced",""),idle=s.get("idle","optimal"),best_including_diagnostic=case_best,**details(certs[k])))
    csvout("baselines.csv",summary)
    cp=[];snap=[];candidate_log=[]
    budgets={"S16":900,"S32":1800,"S80":3600}
    for case,tmax in budgets.items():
        for method in ("C0","C1"):
            folder=OUT/"cp"/case/method
            if not folder.is_dir() or not any((j["job"],j["case"],j["method"])==("cp",case,method) for j in jobs):continue
            tline=rows(folder/"timeline.jsonl")
            assert tline
            seed=seeds[case]["plan"]
            seed_m=certs[seed]["metrics"]
            latest=tline[-1]
            best=latest["plan"];m=certs[best]["metrics"];assert m["status"]=="SAFE"
            lower=Q(latest["global_lower_exact_J"])
            assert float(lower)<=m["E_bounds"][1]
            stat=read(folder/"model.json") if (folder/"model.json").exists() else {}
            slices=rows(folder/"slices.jsonl");candidates=rows(folder/"candidates.jsonl");pending=rows(folder/"pending.jsonl")
            # Independently replay the four-way lower-bound coverage from raw logs.
            from math import floor
            audit_bound=Q(tline[0]["global_lower_exact_J"])
            audit_upper=Q.from_float(seed_m["E_bounds"][1])
            known={}
            marked=[t for t in tline if t["event"]=="partition_bound"]
            for ix,slice_ in enumerate(slices):
                assert slice_["cutoff_pJ"]==floor(audit_upper*10**12)
                cover=[audit_upper,*known.values()]
                if slice_["status"]!="INFEASIBLE":
                    cover.append(Q(floor(slice_["CP_bound_pJ"]),10**12))
                audit_bound=max(audit_bound,min(cover))
                assert audit_bound==Q(marked[ix]["global_lower_exact_J"])
                for candidate in (c for c in candidates if c["slice"]==slice_["slice"]):
                    key=candidate["plan"]
                    exact=Q(candidate["full_reference_J"])
                    assert Q(candidate["encoded_pJ"],10**12)<=exact
                    contribution=exact
                    if candidate["status"]=="SAFE":
                        lo,hi=map(Q.from_float,candidate["bounds"])
                        contribution=max(exact,lo)
                        audit_upper=min(audit_upper,hi)
                    known[key]=contribution
            if (folder/"completion.json").exists():
                assert audit_bound==lower and audit_upper==Q.from_float(m["E_bounds"][1])
            entry=next(j for j in jobs if (j["job"],j["case"],j["method"])==("cp",case,method))
            real_improvement=best!=seed and m["E_bounds"][1]<seed_m["E_bounds"][0]
            unique={r["plan"]:r["status"] for r in candidates}
            counts=Counter(unique.values())
            gap=m["E_bounds"][1]-float(lower)
            values=dict(case=case,method=method,budget_s=tmax,common_seed=seed,plan=best,**details(certs[best]),
                        delta_J=seed_m["E_J"]-m["E_J"],strict=real_improvement,
                        gain_lower_J=(seed_m["E_bounds"][0]-m["E_bounds"][1] if best!=seed else 0),
                        gain_upper_J=(seed_m["E_bounds"][1]-m["E_bounds"][0] if best!=seed else 0),
                        lower_J=float(lower),lower_exact_J=str(lower),gap_J=gap,gap_pct_of_upper=100*gap/m["E_bounds"][1],
                        elapsed_s=entry["elapsed_s"],worker_status=entry["status"],build_s=stat.get("build_s",""),
                        solve_s=sum(s["solve_s"] for s in slices),assessment_archive_s=sum(s["assessment_archive_s"] for s in slices),
                        slices=len(slices),branches=sum(s["branches"] for s in slices),conflicts=sum(s["conflicts"] for s in slices),
                        callbacks=sum(s["callback_count"] for s in slices),retained=sum(s["retained"] for s in slices),
                        evaluated=len(candidates),unique=len(unique),SAFE=counts["SAFE"],HOT=counts["HOT"],
                        unresolved=sum(v for k,v in counts.items() if k not in ("SAFE","HOT")),pending=len(pending),
                        status_counts=json.dumps(dict(Counter(s["status"] for s in slices))),variables=stat.get("variables",""),
                        constraints=stat.get("constraints",""),arcs=sum(d["arcs"] for d in stat.get("domain_paths",[])))
            cp.append(values)
            item={"case":case,"method":method,"initial_SAFE_J":seed_m["E_J"]}
            for t in (180,900,1800,3600):
                at=[z for z in tline if z["elapsed_s"]<=t]
                k=at[-1]["plan"] if at else seed
                item[f"best_SAFE_{t}s_J"]=certs[k]["metrics"]["E_J"] if t<=tmax else ""
            snap.append(item)
            for c in candidates:candidate_log.append(dict(case=case,method=method,**c))
    csvout("summary.csv",cp);csvout("checkpoints.csv",snap);csvout("candidates.csv",candidate_log)
    changes=[]
    for row in cp:
        original,best=[json.loads(gzip.decompress((OUT/"plans"/(row[k]+".json.gz")).read_bytes())) for k in ("common_seed","plan")]
        for i,(a,b) in enumerate(zip(original["rows"],best["rows"])):
            if a!=b:
                changes.append(dict(case=row["case"],method=row["method"],kind="stage",request=i//3,stage=("pre","main","post")[i%3],
                               stage_id=i,old_unit=a[0],old_opp=a[1],old_tick=a[2],new_unit=b[0],new_opp=b[1],new_tick=b[2]))
        old_low,new_low=({tuple(v) for v in obj["low"]} for obj in (original,best))
        for dom,right in sorted(old_low^new_low):
            changes.append(dict(case=row["case"],method=row["method"],kind="idle",domain=dom,right_stage=right,
                                old_early=(dom,right) in old_low,new_early=(dom,right) in new_low))
    csvout("schedule_differences.csv",changes)
    csvout("suffix.csv",extra)
    print(json.dumps(dict(seeds={k:s["E_J"] for k,s in seeds.items()},summary=[(c["case"],c["method"],c["SAFE_J"],c["lower_J"],c["evaluated"]) for c in cp],
                        unique_certificates=len(certs),jobs=len(jobs))))
if __name__=="__main__":main()
