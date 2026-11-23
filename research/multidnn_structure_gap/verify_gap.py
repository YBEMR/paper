"""Offline source/input/archive and certificate checks; no new physical evaluations."""
from collections import Counter
import json
import math
from analyze_gap import read,lines,CFG,HERE
from run_gap import verify_freeze
from model import Instance,Result,sha,encoded,OPPS
from topology import validate_graph

def validate_physical(p,inst,indices):
    assert p["required"]==inst.required
    if not p["fully_replayed"]:
        assert not p["deadline_ok"] and p["energy_j"] is None and p["thermal_status"]=="NOT_EVALUATED"
        assert p["scene_rows"][-1]["late_ids"]
        return
    assert p["completed"]==inst.required and p["deadline_ok"] and p["min_slack_ms"]>=0
    Result(p["thermal_status"],p["completed"],p["min_slack_ms"],p["energy_j"],
           tuple(p["peak_lower_c"]),tuple(p["peak_upper_c"]),required=inst.required)
    assert len(p["scene_rows"])==len(inst.scenes)
    previous=inst.initial
    for j,(s,row) in enumerate(zip(inst.scenes,p["scene_rows"])):
        assert row["scene"]==s.name and row["start_ns"]==s.start_ns and row["end_ns"]==s.start_ns+s.duration_ns
        assert row["required"]==len(s.requests) and row["deadline_ok"] and row["min_slack_ns"]>=0
        assert max(abs(a-b) for a,b in zip(previous,row["entry_c"]))<1e-10
        assert row["opp"]==OPPS[indices[j]]
        previous=row["final_c"]
    assert p["scene_rows"][-1]["end_ns"]==inst.window_ns
    assert abs(math.fsum(s["energy_j"] for s in p["scene_rows"])-p["energy_j"])<1e-8
    assert max(abs(a-b) for a,b in zip(previous,p["final_c"]))<1e-10
    assert abs(min(s["min_slack_ns"] for s in p["scene_rows"])/1e6-p["min_slack_ms"])<1e-10

def main():
    verify_freeze();counts=Counter();case_rows=[]
    env=read(HERE/"environment.json")
    for p in (HERE/"inputs/graphs").glob("*.json"):validate_graph(read(p))
    for case in CFG["main_cases"]:
        inst=Instance(case)
        for dep in inst.domain["deployments"].values():
            slots=0
            for app,chain in dep["stages"].items():
                end=0;graph=inst.graphs[inst.case["models"][int(app)]]
                for device,lo,hi in chain:
                    assert lo==end and hi>=lo and device in ("GPU","DLA0","DLA1")
                    end=hi+1;slots+=device.startswith("DLA")
                assert end==len(graph["ops"])
            assert slots==dep["resident_dla_stages"]<=4
        jobs=[("M2-reference",0)]+[("Kim-Anytime+SAFE",s) for s in CFG["kim_seeds"]]
        for method,seed in jobs:
            folder=HERE/"raw"/case/f"{method}_{seed}"
            receipt=read(folder/"receipt.json");reservation=read(folder/"reservation.json")
            for name,value in receipt["files"].items():assert sha(folder/name)==value,(folder,name)
            assert reservation["execution_commit"]==env["execution_commit"]
            assert reservation["manifest_sha256"]==env["source_manifest_sha"]==sha(HERE/"execution_manifest.json")
            trace=lines(folder/"events.jsonl.gz")
            assert all(a["t_s"]<=b["t_s"] for a,b in zip(trace,trace[1:]))
            ident=next(r["data"] for r in trace if r["kind"]=="identity")
            assert ident["instance_sha"]==inst.identity and ident["domain_count"]==len(inst.order)
            assert ident["opps"]==list(OPPS) and ident["case"]==inst.case
            assert ident["domain_sha"]==sha(HERE/inst.case["domain_file"])
            assert ident["core"]==reservation["core"]
            known={}
            for r in lines(folder/"physical.jsonl.gz"):
                assert r["identity"]==inst.identity and r["dep"] in inst.order
                assert len(r["indices"])==len(inst.scenes) and all(0<=i<27 for i in r["indices"])
                key=(r["dep"],*r["indices"]);assert key not in known
                known[key]=r["physical"];validate_physical(r["physical"],inst,r["indices"])
                counts["physical_records"]+=1;counts["physical_"+r["physical"]["thermal_status"]]+=1
            best=None
            for r in trace:
                if r["kind"]!="incumbent":continue
                data=r["data"];proof=read(folder/data["proof"]);p=proof["physical"]
                assert p==known[tuple(data["key"])] and p["thermal_status"]=="SAFE"
                assert p["energy_j"]==data["energy_j"] and proof["identity"]==inst.identity
                assert proof["stages"]==inst.domain["deployments"][proof["dep"]]["stages"]
                assert [[q["request_id"],q["app_id"],q["release_ns"],q["deadline_ns"]] for q in proof["completions"]]==inst.stream["requests"]
                assert len(proof["completions"])==inst.required
                for q in proof["completions"]:
                    assert q["completion_ns"]>=q["release_ns"]
                    assert q["deadline_ns"]-q["completion_ns"]==q["slack_ns"]>=0
                assert min(q["slack_ns"] for q in proof["completions"])/1e6==p["min_slack_ms"]
                if data["accepted"]:
                    assert r["t_s"]<=CFG["cap_s"] and (best is None or p["energy_j"]<best)
                    best=p["energy_j"]
                counts["safe_request_ledgers"]+=1;counts["ledger_requests"]+=inst.required
            result=read(folder/"result.json") if (folder/"result.json").exists() else None
            if result:
                assert result["counts"]["unique_replays"]==len(known)
                assert result["required"]==inst.required
                assert (result["result"]["energy_j"] if result["result"] else None)==best
                if method=="M2-reference":
                    summary=result["summary"]
                    for phase in ("energy","thermal"):
                        deployments=[r["data"] for r in trace if r["kind"]=="deployment" and r["data"]["phase"]==phase]
                        assert [r["dep"] for r in deployments]==inst.order[:summary["coverage"][phase]]
                        assert [r["completed"] for r in deployments]==list(range(1,len(deployments)+1))
                    if summary["certificate"]:
                        cert=next(r for r in trace if r["kind"]=="certificate")
                        assert cert["t_s"]<=CFG["cap_s"] and summary["coverage"]["energy"]==len(inst.order)
                        assert summary["e0_proven"]
                        e0=known.get(tuple(summary["e0_key"])) if summary["e0_key"] else None
                        if e0 and e0["thermal_status"]!="SAFE":
                            assert summary["coverage"]["thermal"]==len(inst.order) and summary["unresolved"]==0
                        if best is not None:assert abs(best-cert["data"]["lower_bound_j"])<=1e-7
                        counts["exact_certificates"]+=1
                    else:counts["exact_pending"]+=1
            counts["runs"]+=1;counts[receipt["status"]]+=1
        case_rows.append(dict(case_id=case,identity=inst.identity,required=inst.required,domain=len(inst.order)))
    assert counts["runs"]==32
    assert sorted(p.name for p in (HERE/"raw").iterdir())==sorted(CFG["main_cases"])
    summary=read(HERE/"summary.json");assert len(summary["runs"])==32
    for r in summary["runs"]:
        if r.get("gap_pct") is not None:
            assert r["certified_optimum_j"] is not None and r["gap_pct"]>=-1e-6
    result=dict(status="PASS",scope="frozen source/input hashes; raw receipts; continuous certificate consistency; all SAFE incumbent request ledgers; enumerated coverage. No new optimization or hardware validation.",
        counts=dict(counts),cases=case_rows,unexecuted_holdout=CFG["unopened_holdout"])
    (HERE/"verification.json").write_bytes(encoded(result)+b"\n")
    print(json.dumps(result,indent=2))
if __name__=="__main__":main()
