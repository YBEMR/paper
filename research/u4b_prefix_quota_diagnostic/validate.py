"""Read-only inventory, cutoff accounting and identity checks against the committed evidence."""
import csv
import gzip
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path

root=Path(__file__).resolve().parent
def load(p):return json.loads(p.read_bytes())
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
    entries=(root/"SHA256SUMS").read_text(encoding="utf8").splitlines()
    named=set()
    for entry in entries:
        h,name=entry.split("  ",1)
        p=root/name
        assert p.resolve().is_relative_to(root) and name not in named and sha(p.read_bytes())==h,name
        named.add(name)
    refs=load(root/"sources.json")
    checked=Counter()
    with (root/"tables/routes.csv").open(encoding="utf8",newline="") as f:rows=list(csv.DictReader(f))
    assert len(rows)==72 and len({(r["case"],r["arm"]) for r in rows})==72
    for k in refs["inputs"]:
        base=root/"results"/k
        rec=load(base/"verified.json");checked["physical"]+=rec["physical"];checked["proofs"]+=len(rec["proofs"])
        for h,v in rec["proofs"].items():
            data=gzip.decompress((base/"proofs"/(h+".f64.gz")).read_bytes())
            assert sha(data)==v["trace_sha256"] and len(data)==8*31*v["rows"]
        finals=[]
        for m in "RPDCH":
            r=load(base/f"runs/{m}.json");checked["routes"]+=1
            assert r["receipt"]["cap"]==10 and r["receipt"]["status"] in ("wall","natural")
            assert all(c["t"]<=10 for c in r["certificates"]+r["delivered"])
            assert all(c["status"]=="SAFE" and c["slack"]>=0 and struct.unpack("<d",bytes.fromhex(c["peak"]))[0]<=80 for c in r["delivered"])
            table=next(row for row in rows if (row["case"],row["arm"])==(k,m))
            assert int(table["SAFE"])==bool(r["delivered"]) and int(table["cert_done"])==len(r["certificates"])
            if r["delivered"]:
                final=r["delivered"][-1]
                assert table["plan"]==final["plan"]
                assert float(table["peak_hi_C"])==struct.unpack("<d",bytes.fromhex(final["peak"]))[0]
            checked["open"]+=rec["by_route"][m].get("open_exact",0)
            for j in r["journal"]:
                assert sha(gzip.decompress((base/j).read_bytes()))==Path(j).name.split(".")[0]
            if m in "CH":finals.append(table["plan"])
        assert finals[0]==finals[1]
    for p in (root/"offline").glob("*/audit.json"):
        a=load(p);d=p.parent
        assert load(d/"safe_reference.json")["full_replay_equal"]
        pool=load(d/"terminal_evidence.json")["complete"]
        assert len(pool)==a["terminal_distinct"] and all(z["rank"]==i+1 for i,z in enumerate(pool))
        residual=load(d/"residual.json")
        assert [z["rank"] for z in residual]==[z["rank"] for z in pool if not z["matches"]]
        checked["terminal"]+=len(pool);checked["residual"]+=len(residual)
    budget=sum(b["charged_s"] for b in load(root/"offline_budget.json"))
    assert budget<=600 and checked==dict(physical=65,proofs=37,routes=60,open=595,terminal=344,residual=20)
    print(dict(checked),f"offline charged {budget:.3f} s",len(named),"file digests verified")
if __name__=="__main__":main()
