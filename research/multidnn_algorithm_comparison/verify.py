"""Offline integrity/certificate audit. Does not generate any new search data."""
import gzip
import json
import math
from collections import Counter
from pathlib import Path
from analyze import read,lines,CFG
from run import verify_manifest
from common import Instance,ROOT,HERE,sha,Result,encoded

def validate_physical(p,inst,indices):
    assert p["required"]==inst.required
    if not p["fully_replayed"]:
        assert not p["deadline_ok"] and p["energy_j"] is None
        assert p["thermal_status"]=="NOT_EVALUATED"
        assert p["scene_rows"][-1]["late_ids"]
        return
    assert p["completed"]==inst.required and p["deadline_ok"] and p["min_slack_ms"]>=0
    Result(p["thermal_status"],p["completed"],p["min_slack_ms"],p["energy_j"],
           tuple(p["peak_lower_c"]),tuple(p["peak_upper_c"]),required=inst.required)
    assert len(p["scene_rows"])==len(inst.scenes)==4
    previous=inst.initial
    for j,(s,row) in enumerate(zip(inst.scenes,p["scene_rows"])):
        assert row["scene"]==s.name and row["start_ns"]==s.start_ns
        assert row["end_ns"]==s.start_ns+s.duration_ns
        assert row["required"]==len(s.requests)
        assert row["deadline_ok"] and row["min_slack_ns"]>=0
        assert max(abs(a-b) for a,b in zip(previous,row["entry_c"]))<1e-10
        assert row["opp"]==__import__("search").OPPS[indices[j]]
        previous=row["final_c"]
    assert p["scene_rows"][-1]["end_ns"]==inst.window_ns
    assert abs(math.fsum(s["energy_j"] for s in p["scene_rows"])-p["energy_j"])<1e-8
    assert max(abs(a-b) for a,b in zip(previous,p["final_c"]))<1e-10
    assert abs(min(s["min_slack_ns"] for s in p["scene_rows"])/1e6-p["min_slack_ms"])<1e-10

def main():
    verify_manifest()
    counts=Counter(); cases=[]
    for case in CFG["cases"]:
        inst=Instance(case)
        for seed in CFG["seeds"]:
            for method in CFG["methods"]:
                folder=HERE/"raw"/case/f"{method}_{seed}"
                receipt=read(folder/"receipt.json")
                for name,expected in receipt["files"].items():
                    assert sha(folder/name)==expected,(folder,name)
                reservation=read(folder/"reservation.json")
                assert reservation["execution_commit"]==read(HERE/"environment.json")["execution_commit"]
                assert receipt["core"]==reservation["core"]
                trace=lines(folder/"events.jsonl.gz")
                identity=next(x["data"] for x in trace if x["kind"]=="identity")
                assert identity["identity"]==inst.identity
                assert identity["domain"]==inst.order and len(identity["opps"])==27
                known={}
                for line in lines(folder/"certificates.jsonl.gz"):
                    row=line["data"]
                    assert row["identity"]==inst.identity and row["initial_c"]==inst.initial
                    assert row["ambient_c"]==inst.ambient and row["dep"] in inst.order
                    assert len(row["indices"])==4 and all(0<=i<27 for i in row["indices"])
                    key=(row["dep"],*row["indices"])
                    assert key not in known
                    known[key]=row["physical"]
                    validate_physical(row["physical"],inst,row["indices"])
                    counts["physical_certificates"]+=1
                    counts["physical_"+row["physical"]["thermal_status"]]+=1
                best=None
                for row in trace:
                    if row["kind"]!="incumbent":continue
                    data=row["data"]
                    proof=read(folder/data["proof"])
                    p=proof["physical"]
                    assert p==known[tuple(data["key"])] and p["thermal_status"]=="SAFE"
                    assert proof["identity"]==inst.identity
                    assert proof["stages"]==inst.frozen["deployments"][proof["dep"]]["stages"]
                    requests=[[r["request_id"],r["app_id"],r["release_ns"],r["deadline_ns"]] for r in proof["completions"]]
                    assert requests==inst.stream["requests"]
                    assert len(requests)==inst.required
                    assert min(r["slack_ns"] for r in proof["completions"])/1e6==p["min_slack_ms"]
                    for r in proof["completions"]:
                        assert r["completion_ns"]-r["release_ns"]>=0
                        assert r["deadline_ns"]-r["completion_ns"]==r["slack_ns"]>=0
                    if data["accepted"]:
                        assert row["t_s"]<=CFG["cap_s"]
                        assert best is None or p["energy_j"]<best
                        best=p["energy_j"]
                    counts["incumbent_ledgers"]+=1
                    counts["ledger_requests"]+=len(requests)
                result=read(folder/"result.json") if (folder/"result.json").exists() else None
                if result:
                    assert result["physics_counts"]["unique_replays"]==len(known)
                    assert result["required"]==inst.required
                    assert (result["result"]["energy_j"] if result["result"] else None)==best
                counts["runs"]+=1
                counts[receipt["status"]]+=1
        cases.append(dict(case_id=case,identity=inst.identity,required=inst.required,domain=81))
    assert counts["runs"]==72
    summary=read(HERE/"summary.json")
    assert len(summary["runs"])==72
    assert all(r["gap_pct"] is None or r["gap_pct"]>=-1e-7 for r in summary["runs"])
    result=dict(status="PASS",scope="archived certificates, full incumbent request ledgers, source/input hashes; no new optimizer runs",
                counts=dict(counts),cases=cases)
    (HERE/"verification.json").write_bytes(encoded(result)+b"\n")
    print(json.dumps(result,indent=2))
if __name__=="__main__":
    main()
