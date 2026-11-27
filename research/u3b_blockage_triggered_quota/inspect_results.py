"""Read-only scientific audit. Rebuild event ledgers but do not search or integrate."""
import csv
import gzip
import hashlib
import io
import json
import os
import platform
import subprocess
import sys
import tarfile
from pathlib import Path
from time import perf_counter

import numpy as np
import worker as w
from archive import HERE, OUT, read, sha, write

TABLES=HERE/"tables"
def rows(name,records):
    with (TABLES/(name+".csv")).open("w",encoding="utf8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(records[0]),lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
def part(unit,name):
    return json.loads(gzip.decompress((HERE/unit["parts"][name]).read_bytes()))
def physical(case,plan):
    return OUT/"physical"/case/plan

def historical_nt(h):
    # Original recorded NT lane, earliest safe and ten-second cut, with no new NT calls.
    start=perf_counter()
    results=[]
    for old in h["cases"]:
        case=old["case"]
        dest=w.INPUTS/"u2/research/u2_adaptive_groups/results"/case
        meta=read(dest/"archive.json")
        parts=[(dest/p["name"]).read_bytes() for p in meta["parts"]]
        assert all(sha(v)==p["sha256"] for v,p in zip(parts,meta["parts"]))
        combined=b"".join(parts)
        assert sha(combined)==meta["sha256"]
        with tarfile.open(fileobj=io.BytesIO(combined),mode="r|gz") as tar:
            for item in tar:
                if item.name==case+"/r1/NT/certs.jsonl":
                    calls=[json.loads(line) for line in tar.extractfile(item) if line.strip().endswith(b"}")]
                    break
            else:
                raise ValueError(case)
        safe=[v for v in calls if v["status"]=="SAFE"]
        first=next(iter(safe),{})
        bounded=[v for v in safe if v["t"]<=10]
        best=min(bounded,key=lambda r:r["J"]) if bounded else {}
        results.append(dict(case=case,first_safe_s=first.get("t"),first_width=first.get("width"),
            first_safe_J=first.get("J"),first_plan=first.get("plan"),safe_by_10s=bool(best),
            best_by_10s_J=best.get("J"),best_by_10s_plan=best.get("plan"),archive_sha256=meta["sha256"]))
    rows("historical_nt",results)
    return perf_counter()-start

def audit_trace(engine,flow,causal,folder):
    cert=read(folder/"certificate.json")
    m=cert["metrics"]
    plan=read(folder/"plan.json")
    code=bytes(k+10*(u==3) for u,k,_ in plan["rows"][1::3])
    assert sha((folder/"plan.json").read_bytes().strip())==cert["plan_sha256"]==folder.name
    assert len(code)==engine.n
    state=causal(flow,code)
    assert state is not None
    build=engine.build(tuple((3,x-10) if x>=10 else (2,x) for x in code),state)
    assert [list(v) for v in build["rows"]]==plan["rows"] and sorted(state["low"])==sorted(map(tuple,plan["low"]))
    with np.load(folder/"trace.npz",allow_pickle=False) as a:
        tr=a["events"]
    assert np.array_equal(tr[:,:14],build["ev"]) and tr[0,0]==0 and tr[-1,1]==flow.p.horizon
    assert np.all(tr[:,1]>tr[:,0]) and np.array_equal(tr[1:,0],tr[:-1,1])
    assert np.array_equal(tr[1:,14:18],tr[:-1,18:22])
    assert np.allclose(tr[:,22:26].max(axis=0),m["peak_hi"],rtol=0,atol=1e-8)
    total=tr[:,26:30].sum()+.3*flow.p.horizon/10000
    assert m["E_bounds"][0]<=total<=m["E_bounds"][1] and abs(total-m["E_J"])<1e-7
    assert m["min_deadline_slack_ms"]>=0 and (max(m["peak_hi"])<=80 if m["status"]=="SAFE" else max(m["peak_lo"])>80)
    return code,tr

def main():
    start=perf_counter()
    runs=[read(p) for p in sorted((OUT/"runs").glob("*.json"))]
    old=read(TABLES/"historical.json")
    prev={r["case"]:r for r in old["cases"]}
    case_rows=[]
    attempts=[]
    summary=[]
    for u in runs:
        rec=u["receipt"]
        case=rec["case"]
        hist=prev[case]
        base=part(u,"base")
        old_dir=Path(os.environ["U3A_ARCHIVE"])/"results"/case
        old_raw=json.loads(gzip.decompress((old_dir/"raw_pool.json.gz").read_bytes()))
        assert [l["retained"] for l in base["layers"]]==[l["retained"] for l in old_raw]
        assert hist["top12"]==[sha(bytes.fromhex(s)) for s in base["top"]]
        entered=u["delivery"]["attempts"]
        for a in entered:
            if a["stage"]=="terminal":
                k=a["rank"]-1
                assert a["config"]==hist["top12"][k]
                assert (a["plan"],a["status"])==(hist["archive_attempts"][k]["plan"],hist["archive_attempts"][k]["status"])
            else:
                pool=part(u,a["stage"]+"-pool")
                assert a["config"] in {sha(bytes.fromhex(v["config"])) for v in pool["ranking"]}
            attempts.append(dict(route=rec["label"],**a))
        safe=[v for v in entered if v["status"]=="SAFE"]
        assert len(safe)<=1 and (not safe or entered[-1]==safe[0])
        assert (rec["status"]=="SAFE")==bool(safe) and 0<u["finish"]["wall_s"]<=rec["cap_s"]
        assert len(entered)==len({a["config"] for a in entered}) and len(entered)<=20
        assert u["delivery"]["local_replays"]<=14000 and set(u["evidence"])=={a["plan"] for a in entered}
        last=safe[0] if safe else {}
        summary.append(dict(case=case,method=rec["method"],repeat=rec["repeat"],status=rec["status"],
            wall_s=rec["wall_s"],kernel_ready_s=u["ready"]["warm_s"],process_s=rec["process_wall_s"],cpu=u["ready"]["affinity"][0],
            terminal=sum(a["stage"]=="terminal" for a in entered),local=sum(a["stage"]!="terminal" for a in entered),
            local_replays=u["delivery"]["local_replays"],safe_plan=last.get("plan"),first_SAFE_evidence_s=last.get("evidence_s"),
            safe_J=last.get("J"),peak_hi=last.get("peak_hi"),slack_ms=last.get("slack_ms")))
        if rec["method"]=="terminal" and rec["repeat"]==1:
            case_rows.append(dict(case=case,role="development" if case in ("B07","C10") else "known_witness" if case in ("A06","C11") else "regression",
                input_sha256=hist["input"]["input_sha256"],requests=hist["input"]["requests"],windows=hist["input"]["windows"],
                offline_first=hist["first_safe"],online_status=rec["status"],online_attempts=len(entered),online_first=last.get("rank"),
                same_first_safe=hist["first_safe"]==last.get("rank"),safe_plan=last.get("plan"),wall_s=rec["wall_s"]))
    assert len(case_rows)==12 and all(v["same_first_safe"] for v in case_rows)
    rows("cases",case_rows)
    rows("routes",summary)
    rows("attempts",attempts)
    stack=w.u.stack()
    identities=[]
    for case,hist in prev.items():
        obj=hist["input"]
        flow=w.u.make_flow(stack[0],obj,OUT)
        eng=stack[1].Engine(obj["case"],OUT)
        for folder in sorted((OUT/"physical"/case).iterdir()):
            code,tr=audit_trace(eng,flow,stack[3],folder)
            identities.append(dict(case=case,plan=folder.name,config=sha(code),trace_sha256=sha(tr.tobytes()),events=len(tr)))
    rows("physical",identities)
    source=list((OUT/"runs").glob("online-C10-*-r1.json"))
    cells={p.name.split("-")[2]:read(p) for p in source}
    common=[]
    for locator in "oh":
        base=cells[locator+"o"]
        hot=cells[locator+"h"]
        for stage in ("single","adjacent"):
            if stage+"-pool" not in base["parts"] or stage+"-pool" not in hot["parts"]:
                continue
            a,b=[part(r,stage+"-pool") for r in (base,hot)]
            assert a["common_digest"]==b["common_digest"] and a["size"]==b["size"]
            assert [x["config"] for x in a["ranking"]]==[x["config"] for x in sorted(b["ranking"],key=lambda r:(r["ordinary"],r["config"]))]
            common.append(dict(locator=locator,stage=stage,window=base["location"]["selected_w"],size=a["size"],digest=a["common_digest"]))
    rows("matched_pools",common)
    nt_time=historical_nt(old)
    write(TABLES/"verification.json",dict(runs=len(runs),certificates=len(identities),attempts=len(attempts),
        verified_pool_pairs=len(common),historical_reachability_wall_s=old["wall_s"],nt_extract_wall_s=nt_time,
        check_wall_s_including_nt=perf_counter()-start,platform=platform.platform(),python=sys.version))
if __name__=="__main__":
    main()
