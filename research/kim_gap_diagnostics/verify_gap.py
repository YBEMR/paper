"""Audit archived arrays, full physical certificates, request ledgers and frozen provenance.

No dispatch, candidate generation, thermal integration or search reruns.
"""
from collections import Counter
import math
import numpy as np
from analyze_gap import HERE,ROOT,CFG,CASES,read,lines
from common import verify_freeze,sha,make_domain,loads,search,encoded

def check_physical(p,case,indices):
    assert p["required"]==p["completed"]==500 and p["deadline_ok"] and p["fully_replayed"]
    assert p["min_slack_ms"]>=0 and len(p["scene_rows"])==4
    search.Result(p["thermal_status"],p["completed"],p["min_slack_ms"],p["energy_j"],tuple(p["peak_lower_c"]),tuple(p["peak_upper_c"]))
    previous=[30.]*4;end=0
    for j,row in enumerate(p["scene_rows"]):
        assert row["start_ns"]==end and row["opp"]==search.OPPS[indices[j]]
        assert row["entry_c"]==previous and row["deadline_ok"] and row["min_slack_ns"]>=0
        previous=row["final_c"];end=row["end_ns"]
    assert end==10040000000 and previous==p["final_c"]
    assert abs(math.fsum(r["energy_j"] for r in p["scene_rows"])-p["energy_j"])<=1e-8
    assert min(r["min_slack_ns"] for r in p["scene_rows"])*1e-6==p["min_slack_ms"] or abs(min(r["min_slack_ns"] for r in p["scene_rows"])*1e-6-p["min_slack_ms"])<1e-10

def main():
    verify_freeze();domain=make_domain(ROOT);assert domain.size==4319803
    env=read(HERE/"environment.json");counts=Counter();coverage=[]
    pools=read(HERE/"inputs/candidates.json")
    for case in CASES:
        stream=read(ROOT/"research/ch3_algorithm_selection/streams"/(case["load"]+".json"))
        assert loads.verify(stream,loads.CFG["loads"][case["load"]])==case["request_sha"]
        for phase in CFG["phases"]:
            folder=HERE/"raw"/case["case_id"]/phase
            receipt=read(folder/"receipt.json");reservation=read(folder/"reservation.json")
            for name,value in receipt["files"].items():assert sha(folder/name)==value,(folder,name)
            assert reservation["execution_commit"]==env["execution_commit"] and reservation["manifest_sha"]==env["manifest_sha"]==sha(HERE/"execution_manifest.json")
            assert receipt["status"]=="finished" and receipt["total_wall_s"]<=120
            trace=lines(folder/"events.jsonl.gz");raw=read(folder/"result.json")
            identity=next(r["data"] for r in trace if r["kind"]=="identity")
            assert identity["case"]==case and identity["request_sha"]==case["request_sha"] and identity["domain"]==domain.size
            assert identity["initial_c"]==[30.]*4 and identity["ambient_c"]==case["ambient_c"]
            assert any(r["kind"]=="historical_regression" and r["data"]["status"]=="PASS" for r in trace)
            known={}
            for r in lines(folder/"physical.jsonl.gz"):
                assert r["dep"] in domain.order and len(r["indices"])==4 and all(0<=i<27 for i in r["indices"])
                check_physical(r["physical"],case,r["indices"])
                key=(r["dep"],*r["indices"]);assert key not in known;known[key]=r["physical"]
                counts["physical_records"]+=1;counts["physical_"+r["physical"]["thermal_status"]]+=1
            accepted=[]
            for r in trace:
                if r["kind"]!="safe_witness":continue
                w=r["data"];proof=read(folder/w["proof"]);p=proof["physical"]
                assert p==known[w["dep"],*w["indices"]] and p["thermal_status"]=="SAFE"
                assert proof["stages"]==domain.stages(w["dep"]) and proof["request_sha256"]==case["request_sha"]
                assert proof["ambient_c"]==case["ambient_c"] and p["energy_j"]==w["energy_j"]
                for app,chain in proof["stages"].items():domain.rules.check_chain(app,chain)
                assert [[q["request_id"],q["app_id"],q["release_ns"],q["deadline_ns"]] for q in proof["completions"]]==stream
                for q in proof["completions"]:
                    assert q["completion_ns"]>=q["release_ns"]
                    assert q["deadline_ns"]-q["completion_ns"]==q["slack_ns"]>=0
                assert min(q["slack_ns"] for q in proof["completions"])/1e6==p["min_slack_ms"]
                if w["accepted"]:assert w["t_s"]<=120;accepted.append(w)
                counts["safe_ledgers"]+=1;counts["completion_rows"]+=len(proof["completions"])
            assert raw["best"]==min(accepted,key=lambda r:r["energy_j"])
            assert raw["counters"]["unique_replays"]==len(known)
            completed=[r["data"] for r in trace if r["kind"]=="candidate_complete"]
            assert completed==raw["completed"]
            pool=[dict(dep=case["dep"],group="fixed")] if phase=="fixed_frequency" else pools[case["dep"]]
            assert [r["dep"] for r in completed]==[p["dep"] for p in pool[:len(completed)]]
            assert raw["not_completed"]==[p["dep"] for p in pool[len(completed):]]
            for row in completed:
                assert row["end_s"]<=116 and row["arrays"]==row["dep"]+".npz"
                with np.load(folder/row["arrays"],allow_pickle=False) as arrays:
                    energy=arrays["energy_j"];assert energy.shape==(27**4,)
                    legal=np.isfinite(energy)
                    assert int(legal.sum())==row["deadline_sequences"]==row["depth"][-1]
                    if legal.any():assert float(np.min(energy[legal]))==row["energy_lower_bound_j"]
                    states=arrays["thermal_status"] if "thermal_status" in arrays else None
                    if states is not None:
                        assert np.array_equal(states!=0,legal) and set(np.unique(states))<={0,1,2,3}
                        assert int(np.sum(states==1))==row["safe_sequences"] and int(np.sum(states==3))==row["unresolved"]
                    if row["certificate"]:
                        if row["best"]:
                            best=row["best"];key=(best["dep"],*best["indices"]);p=known[key]
                            code=sum(i*27**(3-j) for j,i in enumerate(best["indices"]))
                            assert p["thermal_status"]=="SAFE" and abs(p["energy_j"]-energy[code])<=1e-7
                            target=float(np.min(energy[states==1])) if states is not None else float(np.min(energy[legal]))
                            assert abs(p["energy_j"]-target)<=1e-7
                        else:
                            assert row["no_safe"] and (not legal.any() or (states is not None and not np.any((states==1)|(states==3))))
                        counts["fixed_deployment_optimality_certificates"]+=1
                    counts["frequency_arrays"]+=1;counts["deadline_feasible_sequences"]+=row["deadline_sequences"]
            coverage.append(dict(case_id=case["case_id"],phase=phase,completed=len(completed),planned=len(pool),reason=raw["reason"]))
            counts["runs"]+=1
    assert counts["runs"]==12
    attribution=read(HERE/"frequency_attribution.json")
    assert attribution["max_proxy_reconstruction_error_j"]<=1e-7
    result=dict(status="PASS",counts=dict(counts),coverage=coverage,
        scope="frozen hashes, raw receipts, archived frequency arrays, complete continuous certificates and 500-request ledgers. No extra optimizer or thermal evaluations.",
        global_domain_optimum_certified=False)
    (HERE/"verification.json").write_bytes(encoded(result)+b"\n")
    print(result)
if __name__=="__main__":main()
