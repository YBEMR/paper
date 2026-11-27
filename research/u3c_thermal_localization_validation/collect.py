"""Post-run only: lossless deduplication and independently checked comparison tables."""
import csv
import gzip
import hashlib
import itertools
import json
import os
import shutil
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace
from time import perf_counter
import numpy as np

HERE=Path(__file__).resolve().parent
OLD=HERE.parent/"u3b_blockage_triggered_quota"
TABLES=HERE/"tables"
RESULTS=HERE/"results"
RAW=Path(os.environ["U3B_RUNS"]).resolve()
sys.path.insert(0,str(OLD))
import archive as archive_base
from inspect_results import audit_trace
import worker
from location import simple
from guidance import Guidance
from local_search import anchor_window

read=archive_base.read
sha=archive_base.sha
write=archive_base.write

def table(name,rows,fields):
    TABLES.mkdir(exist_ok=True)
    cols=list(fields) if not rows else list(rows[0])
    with (TABLES/(name+".csv")).open("w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=cols,lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

def part(u,name):
    return json.loads(gzip.decompress((HERE/u["parts"][name]).read_bytes()))

def numbered(items,tag):
    return [r for r in items if r["case"]==tag]

def config_hash(code):
    return sha(bytes.fromhex(code))

def archive_runs():
    archive_base.HERE=HERE
    archive_base.OUT=RESULTS
    for receipt in sorted(RAW.glob("*/receipt.json")):
        folder=receipt.parent
        rec=read(receipt)
        unit=dict(receipt=rec,parts={},evidence=[],fragments=[])
        def fragment(path):
            assert rec["status"]=="WALL",path
            dest=RESULTS/"fragments"/folder.name/path.relative_to(folder)
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(path,dest)
            unit["fragments"].append(dest.relative_to(HERE).as_posix())
        for f in sorted(folder.iterdir()):
            if f.is_dir() or f==receipt or f.name=="worker.log": continue
            if f.suffix==".tmp":
                fragment(f)
                continue
            try:
                if f.name=="base.json":
                    obj=read(f)
                    unit["base_s"]=obj.pop("t")
                    unit["parts"]["base"]=archive_base.block("base",archive_base.raw(obj))
                elif f.name.endswith("-pool.json"):
                    unit["parts"][f.stem]=archive_base.block("rank",archive_base.raw(read(f)))
                elif f.suffix==".gz":
                    body=gzip.decompress(f.read_bytes())
                    json.loads(body)
                    unit["parts"][f.name[:-8]]=archive_base.block("ledger",body)
                else:
                    unit[f.stem]=read(f)
            except (EOFError,OSError,ValueError):
                fragment(f)
        for src in folder.glob("evidence/*/*"):
            names=["certificate.json","plan.json","trace.npz"]
            try:
                c=read(src/names[0])
                assert sha((src/names[1]).read_bytes().strip())==src.name==c["plan_sha256"]
                with zipfile.ZipFile(src/names[2]) as z:
                    assert z.testzip() is None
            except (OSError,EOFError,ValueError,AssertionError,zipfile.BadZipFile):
                for f in src.iterdir(): fragment(f)
                continue
            target=RESULTS/"physical"/rec["case"]/src.name
            target.mkdir(parents=True,exist_ok=True)
            for name in names:
                d=target/name
                if not d.exists():
                    shutil.copyfile(src/name,d)
                elif name=="certificate.json":
                    assert {k:v for k,v in read(d).items() if k!="cert_s"}=={k:v for k,v in c.items() if k!="cert_s"}
                else:
                    assert (src/name).read_bytes()==d.read_bytes()
            unit["evidence"].append(src.name)
        unit["evidence"].sort()
        write(RESULTS/"runs"/(folder.name+".json"),unit)

def collect():
    archive_runs()
    for fn in ("development","expansion"):
        write(RESULTS/(fn+".json"),read(RAW/(fn+".json")))
    reg=HERE/"registration"
    cases=read(reg/"cases.json")
    old_cases=read(OLD/"registration/cases.json")
    objects={c["case"].split("_")[0]:c for c in cases+old_cases}
    units=[read(p) for p in sorted((RESULTS/"runs").glob("*.json"))]
    scans={u["receipt"]["case"]:u for u in units if u["receipt"]["method"]=="terminal"}
    expand=read(RESULTS/"expansion.json")
    assert set(scans)=={c["tag"] for c in cases if c["batch"]==1 or expand["expand"]}
    triggers={k for k,u in scans.items() if u["receipt"]["status"]=="HOT"}
    assert sorted(k for k in triggers if objects[k]["batch"]==1)==sorted(expand["first_trigger"])
    assert expand["expand"]==(len(expand["first_trigger"])<4)
    summaries=[]; attempts=[]; groups=defaultdict(list); by_tag=defaultdict(list)
    source=[]; physical=[]; checks=[]; flow_rows=[]; safe_paths=[]; projections=[]; failures=[]; offline_seconds=0
    stack=worker.u.stack()
    for u in units:
        rec=u["receipt"]; tag=rec["case"]; method=rec["method"]; rep=rec["repeat"]
        assert u["ready"]["affinity"]==[4]
        d=u.get("delivery",u.get("progress",{})); a=d.get("attempts",[])
        parts=u["parts"]
        base=part(u,"base") if "base" in parts else {"top":[],"layers":[]}
        term=[x for x in a if x["stage"]=="terminal"]
        local=[x for x in a if x["stage"]!="terminal"]
        assert [x["config"] for x in term]==[config_hash(v) for v in base["top"][:len(term)]]
        assert len(set(x["config"] for x in a))==len(a)
        assert len(term)<=12 and all(sum(x["stage"]==s for x in local)<=4 for s in ("single","adjacent"))
        assert d.get("local_replays",0)<=14000
        assert all(x["prediction"] is None for x in a)
        complete=rec["status"]!="WALL"
        assert rec["status"]!="ERROR" and (not complete or rec["wall_s"]<=10)
        safe=next((x for x in a if x["status"]=="SAFE"),{})
        assert not safe or safe==a[-1]
        if complete:
            assert (rec["status"]=="SAFE")==bool(safe) and set(u["evidence"])=={x["plan"] for x in a}
        loc=u.get("location",{})
        if method=="terminal":
            assert not local and not loc and d.get("local_replays",0)==0
            if tag in triggers:
                assert len(term)==len(base["top"])>0 and all(x["status"]=="HOT" for x in term)
        else:
            assert tag=="C10" or tag in triggers
            ref=(read(OLD/"results/runs/online-C10-ho-r1.json") if tag=="C10" else scans[tag])
            assert (not complete or [x["plan"] for x in term]==[x["plan"] for x in ref["delivery"]["attempts"] if x["stage"]=="terminal"])
            if "base" in parts:
                reference_base=(json.loads(gzip.decompress((OLD/ref["parts"]["base"]).read_bytes())) if tag=="C10" else part(ref,"base"))
                assert base==reference_base
            if loc:
                assert loc["anchor"]==term[0]["plan"]
                groups[tag,loc["selected_w"]].append(u)
                if method=="heat":
                    heat=loc["heat"]
                    scores=[sum(v[2:]) for v in heat["source_C"][:loc["windows"]]]
                    assert loc["selected_w"]==scores.index(max(scores))+1
                else:
                    assert loc["selected_w"]==1+simple(method,loc["windows"],loc["raw_peak_w"]-1,loc.get("ordinary_keys"))
        seen={x["config"] for x in term}
        for stage in ("single","adjacent"):
            if stage+"-pool" not in parts: continue
            pool=part(u,stage+"-pool")
            ranking=pool["ranking"]
            assert ranking==sorted(ranking,key=lambda r:(r["ordinary"],r["config"]))
            assert all(r["prediction"] is None for r in ranking)
            configs=[bytes.fromhex(v["config"]) for v in ranking]
            assert pool["size"]==len(set(configs)) and pool["common_digest"]==sha(b"".join(sorted(configs)))
            unseen=[sha(c) for c in configs if sha(c) not in seen]
            trial=[x["config"] for x in local if x["stage"]==stage]
            assert trial==unseen[:len(trial)] and len(trial)<=4
            seen.update(trial)
        for x in a:
            attempts.append(dict(case=tag,method=method,repeat=rep,**x))
        by_tag[tag].append(u)
        win=safe if rec["status"]=="SAFE" else {}
        bounds=win.get("bounds") or [None,None]
        counted_replays=sum(len(part(u,key)["attempts"]) for key in parts if key.endswith("-attempts"))
        replay_floor=max(d.get("local_replays",0),counted_replays)
        if complete:
            assert replay_floor==d["local_replays"]
        orphan_cert=len(set(u["evidence"])-{x["plan"] for x in a})
        row=dict(case=tag,method=method,repeat=rep,status=rec["status"],selected_w=loc.get("selected_w"),
                 raw_peak_w=loc.get("raw_peak_w"),anchor=term[0]["plan"] if term else None,
                 base_pool=len(base["top"]),terminal=len(term),local=len(local),replays=replay_floor,
                 counts_censored=not complete,additional_archived_certificates=orphan_cert,
                 wall_s=rec["wall_s"],first_SAFE_delivery_s=rec["wall_s"] if win else None,
                 first_SAFE_evidence_s=win.get("evidence_s"),cpu_s=d.get("cpu_s"),process_wall_s=rec["process_wall_s"],
                 safe_plan=win.get("plan"),J=win.get("J"),J_lo=bounds[0],J_hi=bounds[1],
                 T_lo=win.get("peak_lo"),T_hi=win.get("peak_hi"),slack_ms=win.get("slack_ms"))
        summaries.append(row)
        if not win:
            if rec["status"]=="WALL":
                phase=("base" if "base" not in parts else "terminal" if len(term)<len(base["top"])
                       else "adjacent" if "adjacent-pool" in parts or "single-pool" in parts and len([x for x in local if x["stage"]=="single"])==4
                       else "local_or_location")
            elif rec["status"]=="EMPTY":
                phase="empty_construction"
            elif method=="terminal":
                phase="terminal_exhausted"
            else:
                phase="local_budget_or_candidates_exhausted"
            failures.append(dict(case=tag,method=method,repeat=rep,status=rec["status"],phase_from_last_record=phase,
                last_checkpoint_s=u.get("progress",{}).get("t"),terminal_confirmed=len(term),local_confirmed=len(local),
                replay_lower_bound=replay_floor,extra_full_archives=orphan_cert,partial_files=len(u["fragments"]),
                HOT=sum(x["status"]=="HOT" for x in a),OUT_OF_MODEL=sum(x["status"]=="OUT_OF_MODEL" for x in a),
                UNRESOLVED=sum(x["status"]=="UNRESOLVED" for x in a)))
    for (tag,w),items in groups.items():
        for a,b in itertools.combinations(items,2):
            ra,rb=a["receipt"],b["receipt"]
            def signature(u):
                return [(x["stage"],x["rank"],x["plan"],x["status"]) for x in u.get("delivery",u.get("progress",{})).get("attempts",[])]
            xa,xb=signature(a),signature(b)
            common=set(a["parts"])&set(b["parts"])
            for k in common:
                assert a["parts"][k]==b["parts"][k],(tag,k)
            shared=min(len(xa),len(xb))
            assert xa[:shared]==xb[:shared]
            full="WALL" not in (ra["status"],rb["status"])
            if full:
                assert xa==xb and a["parts"]==b["parts"] and ra["status"]==rb["status"]
            checks.append(dict(case=tag,window=w,left=f'{ra["method"]}/{ra["repeat"]}',right=f'{rb["method"]}/{rb["repeat"]}',
                               common_parts=len(common),common_attempts=shared,complete_match=full))
    for tag,items in sorted(by_tag.items()):
        obj=objects[tag]
        worker.u.REG=stack[0].REG=(OLD/"registration" if tag=="C10" else reg)
        flow=worker.u.make_flow(stack[0],obj,RESULTS)
        eng=stack[1].Engine(obj["case"],RESULTS)
        physdir=RESULTS/"physical"/tag
        if physdir.is_dir():
            for folder in sorted(physdir.iterdir()):
                code,tr=audit_trace(eng,flow,stack[3],folder)
                physical.append(dict(case=tag,plan=folder.name,config=sha(code),events=len(tr),trace_sha256=sha(tr.tobytes())))
        arms=[r for r in numbered(summaries,tag) if r["method"]!="terminal" and r["repeat"]==1]
        if tag in triggers:
            assert {r["method"] for r in arms}=={"heat","slack","peak","previous","energy"}
            reps=3 if any(r["status"]=="SAFE" for r in arms) else 1
            assert len(items)==1+5*reps
            # Only reproduce the selectors from the screening certificate. No candidate search.
            begin=perf_counter()
            key=scans[tag]["delivery"]["attempts"][0]["plan"]
            anchor_dir=physdir/key
            cert=read(anchor_dir/"certificate.json")
            main=read(anchor_dir/"plan.json")["rows"][1::3]
            anchor=SimpleNamespace(code=bytes(k+10*(u==3) for u,k,_ in main))
            builder=worker.Builder(flow,eng)
            _,keys=anchor_window(SimpleNamespace(b=builder,e=eng),anchor)
            with np.load(anchor_dir/"trace.npz",allow_pickle=False) as f:
                heat=Guidance(builder,anchor,cert,f["events"]).observation
            n=len(keys)
            peak=int(heat["peak_tick"]//eng.dur)
            choices={m:1+simple(m,n,peak,keys) for m in ("slack","peak","previous","energy")}
            choices["heat"]=heat["window"]
            for r in arms:
                assert r["selected_w"] is None or r["selected_w"]==choices[r["method"]]
            for j,v in enumerate(heat["source_C"],1):
                source.append(dict(case=tag,window=j,kind="offline_paid_anchor_projection",anchor=key,
                      CPU1=v[0],CPU2=v[1],GPU=v[2],NPU=v[3],GPU_NPU=sum(v[2:]),
                      reference_work_J=(-keys[j-1][2]/eng.scale if j<=n else None),
                      eligible_energy=j<=max(1,min(n,peak)),peak_tick=heat["peak_tick"],
                      peak_node=heat["hotspot"],reconstructed_C=heat["reconstructed_C"],peak_lo=heat["peak_lo"],peak_hi=heat["peak_hi"]))
            elapsed=perf_counter()-begin
            projections.append(dict(case=tag,anchor=key,raw_peak_w=peak+1,**choices,
                       distinct=len(set(choices.values())),projection_wall_s=elapsed))
            offline_seconds+=elapsed
        for r in arms:
            if not r["safe_plan"]: continue
            paths=[read(physdir/k/"plan.json")["rows"][1::3] for k in (r["anchor"],r["safe_plan"])]
            for j,ids in enumerate(eng.groups,1):
                def choices(plan):
                    return [sum(plan[i][0]==3 and eng.kindidx[i]==t for i in ids) for t in (0,1)]
                safe_paths.append(dict(case=tag,method=r["method"],plan=r["safe_plan"],window=j,
                          before_NPU_AB=choices(paths[0]),after_NPU_AB=choices(paths[1]),
                          changed_main_options=sum(paths[0][i][:2]!=paths[1][i][:2] for i in ids)))
        if tag in scans:
            scan=next(x for x in numbered(summaries,tag) if x["method"]=="terminal")
            base=part(scans[tag],"base") if "base" in scans[tag]["parts"] else {"layers":[]}
            row=dict(case=tag,word=obj["word"],batch=obj["batch"],stratum=obj["stratum"],input_sha256=obj["input_sha256"],
                     screen=scan["status"],base_pool=scan["base_pool"],tried=scan["terminal"],wall_s=scan["wall_s"],
                     empty_w=next((r["window"] for r in base["layers"] if r["distinct"]==0),None),
                     triggered=tag in triggers,distinct_windows=len({r["selected_w"] for r in arms if r["selected_w"]}),
                     terminal_SAFE=scan["safe_plan"])
            for m in ("slack","peak","previous","energy","heat"):
                z=next((x for x in arms if x["method"]==m),{})
                row[m+"_w"]=z.get("selected_w");row[m+"_result"]=z.get("status")
            flow_rows.append(row)
    table("flows",flow_rows,[])
    table("failures",failures,["case","method","repeat","status"])
    table("offline_windows",projections,["case","anchor","raw_peak_w","slack","peak","previous","energy","heat","distinct","projection_wall_s"])
    table("routes",summaries,[])
    table("attempts",attempts,[])
    table("physical",physical,[])
    table("matched_pools",checks,["case","window","left","right","common_parts","common_attempts","complete_match"])
    table("heat_sources",source,["case","window","CPU1","CPU2","GPU","NPU","GPU_NPU","peak_tick","peak_node","reconstructed_C"])
    table("safe_paths",safe_paths,["case","method","plan","window","before_NPU_AB","after_NPU_AB","changed_main_options"])
    write(TABLES/"verification.json",dict(flows=len(scans),screen_counts=dict(Counter(u["receipt"]["status"] for u in scans.values())),
          triggered=sorted(triggers),routes=len(units),attempts=len(attempts),physical=len(physical),matched_pairs=len(checks),
          wall_units=[r for r in summaries if r["status"]=="WALL"],offline_anchor_wall_s=offline_seconds,cpu=4,threads=1))
    print(len(units),"routes;",len(physical),"physical plans;",len(checks),"window-matched pairs")

if __name__=="__main__":
    collect()
