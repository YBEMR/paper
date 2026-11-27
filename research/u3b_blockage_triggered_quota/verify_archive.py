"""Read-only portable integrity check; no frozen runtime or scientific calls required."""
import gzip
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
def digest(body):
    return hashlib.sha256(body).hexdigest()
def read(path):
    return json.loads(path.read_bytes())
def main():
    listed={}
    for line in (HERE/"SHA256SUMS").read_text(encoding="utf8").splitlines():
        h,name=line.split("  ",1)
        assert name not in listed and (HERE/name).resolve().is_relative_to(HERE)
        assert digest((HERE/name).read_bytes())==h,name
        listed[name]=h
    refs={p.relative_to(HERE).as_posix() for p in HERE.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.name!="SHA256SUMS"}
    assert set(listed)==refs
    for url in re.findall(r"\]\(([^)]+)\)",(HERE/"REPORT_zh.md").read_text(encoding="utf8")):
        assert (HERE/url).exists() or url.startswith("https://github.com/YBEMR/paper/"),url
    for pool in (HERE/"results/pools").iterdir():
        assert digest(gzip.decompress(pool.read_bytes())) in pool.name
    groups=defaultdict(list)
    coverage=set()
    for p in sorted((HERE/"results/runs").glob("*.json")):
        unit=read(p)
        rec=unit["receipt"]
        assert (rec["case"],rec["method"],rec["repeat"]) not in coverage
        coverage.add((rec["case"],rec["method"],rec["repeat"]))
        assert all(ref in refs for ref in unit["parts"].values())
        assert rec["wall_s"]<=rec["cap_s"] and unit["ready"]["affinity"]==[0]
        attempts=unit["delivery"]["attempts"]
        for v in attempts:
            base=HERE/"results/physical"/rec["case"]/v["plan"]
            assert digest((base/"plan.json").read_bytes().strip())==v["plan"]
            metrics=read(base/"certificate.json")["metrics"]
            assert metrics["status"]==v["status"] and abs(metrics["E_J"]-v["J"])<1e-8
        groups[rec["case"],rec["method"]].append((rec["status"],tuple((v["config"],v["plan"],v["status"]) for v in attempts)))
    assert all(len(set(records))==1 for records in groups.values())
    assert len(coverage)==read(HERE/"tables/verification.json")["runs"]
    print(len(refs),"matching file hashes;",len(coverage),"independent completed runs; repeated outcomes and plans agree")
if __name__=="__main__":
    main()
