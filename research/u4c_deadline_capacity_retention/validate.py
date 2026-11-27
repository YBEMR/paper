"""Read-only digest, time-budget, certification-identity and coverage verification."""
import csv
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path
root=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_bytes())
def rows(name):
    with (root/"tables"/(name+".csv")).open(encoding="utf8",newline="") as f:return list(csv.DictReader(f))
def main():
    listed={}
    for line in (root/"SHA256SUMS").read_text(encoding="utf8").splitlines():
        h,n=line.split("  ",1);p=root/n
        assert p.resolve().is_relative_to(root) and n not in listed and hashlib.sha256(p.read_bytes()).hexdigest()==h,n
        listed[n]=h
    trace_count=0;physical=0;proofs=0;checks=0;cover=Counter()
    table={(r["case"],r["arm"]):r for r in rows("routes")}
    for p in sorted((root/"results").glob("*/verified.json")):
        v=read(p);k=p.parent.name;physical+=v["physical"];proofs+=len(v["proofs"])
        checks+=sum(a.get("open_exact",0) for a in v["by_route"].values())
        physics={z["certificate"]["plan_sha256"]:z["certificate"]["metrics"] for z in map(json.loads,gzip.decompress((p.parent/"physical/plans.jsonl.gz").read_bytes()).splitlines())}
        assert len(physics)==v["physical"]
        for f in (p.parent/"runs").glob("*.json"):
            run=read(f);r=table[k,f.stem];d=run["delivered"];trace_count+=1
            assert run["receipt"]["cap"]==10 and 0<run["wall_s"]<=10 and int(r["SAFE"])==bool(d)
            for c in run["certificates"]:
                assert c["t"]<=10 and physics[c["plan"]]["status"]==c["status"] and physics[c["plan"]]["E_J"]==c["J"]
            if d:
                assert d[-1]["plan"]==r["plan"]
                assert all(z["t"]<=10 and z["status"]=="SAFE" and z["slack"]>=0 and max(physics[z["plan"]]["peak_hi"])<=80 for z in d)
                cover[f.stem]+=1
    assert (trace_count,physical,proofs,checks)==(72,233,63,614)
    assert dict(cover)==dict(Control=8,Parent=11,Margin=9,Small=9,BlockedSmall=11,BlockedMix=10)
    records=[read(p) for p in (root/"offline").glob("*/window_*.json")]
    assert len(records)==9 and sum(len(z["minimum_candidates"]) for z in records)==18
    assert all(c["cert"]["status"]=="SAFE" for z in records for c in z["minimum_candidates"])
    assert not read(root/"joint_decision.json")["eligible"]
    cpu=sum(z["charge"] for z in read(root/"offline_budget.json"));assert cpu<600
    print(len(listed),"verified files;",trace_count,"timed runs;",physical,"online physical schedules;",round(cpu,3),"offline charged seconds")
if __name__=="__main__":main()
