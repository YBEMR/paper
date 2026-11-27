"""Recompute measurement tables and check identities. Does not import or run a solver."""
from collections import Counter
import hashlib
import json
from pathlib import Path
from statistics import median

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"measurements"
def lines(name):return [json.loads(v) for v in (OUT/name).read_bytes().splitlines()]
def read(path):return json.loads(path.read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def group(rows,base,other,guard):
    by={(r["case"],r["rep"],r["mode"]):r for r in rows}
    assert len(by)==len(rows)
    pairs=[(r,by[r["case"],r["rep"],other]) for r in rows if r["mode"]==base]
    assert all(all(a[k]==b[k] for k in guard) for a,b in pairs)
    for a,b in pairs:
        assert a["start_order"]==b["start_order"]
    out=dict(pairs=len(pairs),cases=sorted(set(a["case"] for a,b in pairs)),modes={})
    for mode in {r["mode"] for r in rows}:
        work=[r for r in rows if r["mode"]==mode]
        out["modes"][mode]={k:sum(x[k] for x in work) for k in ("wall_s","cpu_s")}
        if "work" in work[0]:out["modes"][mode]["work"]=sum(x["work"] for x in work)
        if "physical_bytes" in work[0]:out["modes"][mode]["physical_bytes"]=sum(x["physical_bytes"] for x in work)
    d=[b["wall_s"]-a["wall_s"] for a,b in pairs]
    out["paired"]=dict(full_first=sum(a["start_order"]==base for a,b in pairs),
        less=sum(v<0 for v in d),median_delta_wall_s=median(d),min_delta_wall_s=min(d),max_delta_wall_s=max(d),
        median_ratio=median(b["wall_s"]/a["wall_s"] for a,b in pairs))
    probes=[r for r in rows if r["mode"]=="probe"]
    if probes:
        assert len(probes)==len(pairs)
        for r in probes:
            assert all(r[k]==by[r["case"],r["rep"],base][k] for k in guard)
        weights=Counter();calls=Counter()
        for r in probes:
            weights.update(r["exclusive_wall_s"]);calls.update(r["probe_calls"])
            weights["residual"]+=r["residual_wall_s"]
        total=out["modes"]["probe"]["wall_s"]
        assert abs(sum(weights.values())-total)<1e-7
        out["probe"]=dict(wall_s=dict(weights),share={k:v/total for k,v in weights.items()},calls=dict(calls),
                          ratio_to_full=total/out["modes"][base]["wall_s"])
    return out

def main():
    raw=lines("raw.jsonl");supp=lines("delivery.jsonl");keys=lines("propagation.jsonl")
    assert len(raw)==243 and len(supp)==24 and len(keys)==2
    data={}
    for stage,num in (("quick",24),("nt1",24),("nt2",9),("certificate",24)):
        r=group([v for v in raw if v["stage"]==stage],"full","lean",
                ("work","ordered_sha256","decision_sha256","observed_states_sha256"))
        assert r["pairs"]==num
        data[stage]=r
    for stage in ("shortlist","nt1_compact"):
        check=("ordered_sha256","decision_sha256","first_delivered_rank") if stage=="shortlist" else (
               "ordered_sha256","actions_sha256","decision_sha256")
        data[stage]=group([v for v in supp if v["stage"]==stage],"full","delivery",check)
    assert all(v["rc"]==0 or v["attempt"]<=3 for v in read(OUT/"budget.json"))
    charges=sum(v["charged_s"] for v in read(OUT/"budget.json"))
    assert charges<=480
    keyrows=[{k:v for k,v in x.items() if k!="verified_stage"} for x in keys]
    for x in keys:
        original=next(v for v in supp if v["case"]==x["case"] and v["stage"]=="nt1_compact" and v["mode"]=="full")
        assert x["verified_stage"]["actions_sha256"]==original["actions_sha256"]
    # Cross-check each selected plan/trace against the archive-linked identity ledger.
    inputs=lines("inputs.jsonl")
    for x in raw:
        if x["stage"]=="certificate":
            expect=next(s for s in inputs if s["case"]==x["case"])
            assert x["decision_sha256"]==expect["cert_plan"]
            assert x["observed_states_sha256"]==expect["archive_trace_sha256"]
    hashes={str(p.relative_to(ROOT)).replace("\\","/"):sha(p) for p in
            [*sorted(OUT.glob("*.jsonl")),*sorted(OUT.glob("environment-*.json")),OUT/"budget.json",
             ROOT/"benchmark.py",ROOT/"benchmark_delivery.py",ROOT/"benchmark_budget.py",
             *sorted(ROOT.glob("PROTOCOL*.md"))]}
    result=dict(comparisons=data,propagation=keyrows,charged_wall_s=charges,sha256=hashes)
    (OUT/"summary.json").write_bytes((json.dumps(result,indent=1,sort_keys=True)+"\n").encode())
    print("verified",len(raw),len(supp),len(keys),round(charges,6))

if __name__=="__main__":main()
