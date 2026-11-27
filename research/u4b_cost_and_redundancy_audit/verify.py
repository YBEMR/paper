"""Read-only delivery verification. Uses the shipped tables and raw timings, never runs a model."""
import csv
import gzip
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

root=Path(__file__).resolve().parent
archive=root/"archive"
meas=root/"measurements"
def read(p):
    return json.loads(p.read_bytes())
def rows(name):
    with (archive/(name+".csv")).open(encoding="utf8") as f:
        return list(csv.DictReader(f))
def lines(name):
    return list(map(json.loads,(meas/(name+".jsonl")).read_bytes().splitlines()))
def check():
    summary=read(meas/"summary.json")
    for rel,digest in summary["sha256"].items():
        assert hashlib.sha256((root/rel).read_bytes()).hexdigest()==digest,rel
    routes=rows("routes")+rows("development_routes")
    assert len({(x["case"],x["method"]) for x in routes})==len(routes)==196
    ph=defaultdict(float)
    for v in rows("phases")+rows("development_phases"):
        ph[v["case"],v["method"]]+=float(v["clipped_wall_s"])
    assert all(abs(ph[x["case"],x["method"]]+float(x["unassigned_s"])-float(x["wall_s"]))<1e-7 for x in routes)
    nt=[x for x in routes if x["case"].startswith("I") and x["method"]=="NT10"]
    assert len(nt)==12 and all(int(x["started"])==0 for x in nt)
    for p in rows("nt_paths"):
        assert int(p["identical_action_prefix"])==int(p["short_actions"])
        assert int(p["identical_beam_prefix"])==int(p["short_beams"])
    pools=json.loads(gzip.decompress((archive/"base_pools.json.gz").read_bytes()))
    for k,v in pools.items():
        assert v["shortlist"]==v["ranked"][:12]
        assert len(set(v["ranked"]))==len(v["ranked"])
    labels=rows("pool_labels")
    assert len(labels)==910 and sum(v["archived_compatible_status"]=="unknown" for v in labels)==849
    joins={(r["case"],r["rank"]):r["config"] for r in labels}
    other=rows("other_batch_coverage")
    assert len(other)==344 and all(joins[r["case"],r["rank"]]==r["config"] for r in other)
    assert sum(bool(json.loads(r["prior_physical_HOT_witnesses"])) for r in other)==324
    assert Counter(r["full_status"] for r in other if r["full_status"])=={"HOT":10,"OUT_OF_MODEL":10}
    for v in rows("terminal_cost"):
        assert not v["strict_ref"] or (int(v["strict_ref"])<int(v["rank"]) and v["status"]=="HOT")
    pairs=defaultdict(dict)
    for r in lines("raw")+lines("delivery"):
        k=(r["case"],r["stage"],r["rep"])
        assert r["mode"] not in pairs[k]
        pairs[k][r["mode"]]=r
    assert len(pairs)==93
    for k,p in pairs.items():
        assert set(p)==({"full","delivery"} if k[1] in ("shortlist","nt1_compact") else {"full","lean","probe"})
        for key in ("ordered_sha256","decision_sha256"):
            assert len({r[key] for r in p.values()})==1
        if k[1]=="shortlist":
            assert p["delivery"]["archived"]==[p["full"]["decision_sha256"]]
    clock=read(archive/"budget.json")
    assert all(x.get("returncode")==0 for x in clock)
    archived=sum(x["charge_s"] for x in clock)
    assert archived<=120 and summary["charged_wall_s"]<=480
    if "--manifest" in sys.argv:
        for line in (root/"SHA256SUMS").read_text().splitlines():
            h,name=line.split("  ",1)
            assert hashlib.sha256((root/name).read_bytes()).hexdigest()==h,name
    print(f"Verified {len(routes)} routes, {len(labels)} terminal candidates, {len(other)} external matches, "
          f"{len(pairs)} paired workloads. Charged {summary['charged_wall_s']:.3f} + {archived:.3f} s.")

if __name__=="__main__":
    check()
