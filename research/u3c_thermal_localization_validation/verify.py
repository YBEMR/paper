"""Portable read-only archive check. Run after extracting the complete research folder."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent

def sha(b):
    return hashlib.sha256(b).hexdigest()

def read(p):
    return json.loads(p.read_bytes())

def verify():
    listed={}
    for line in (HERE/"SHA256SUMS").read_text(encoding="utf8").splitlines():
        h,p=line.split("  ",1)
        assert p not in listed and (HERE/p).resolve().is_relative_to(HERE)
        assert sha((HERE/p).read_bytes())==h,p
        listed[p]=h
    actual={p.relative_to(HERE).as_posix() for p in HERE.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.name!="SHA256SUMS"}
    assert set(listed)==actual
    for target in re.findall(r"\]\(([^)]+)\)",(HERE/"REPORT_zh.md").read_text(encoding="utf8")):
        assert target.startswith("https://github.com/YBEMR/paper/") or (HERE/target).exists(),target
    for p in (HERE/"results/pools").glob("*.gz"):
        assert sha(gzip.decompress(p.read_bytes())) in p.name,p
    cases=read(HERE/"registration/cases.json")
    excluded=read(HERE/"registration/exclusions.json")
    assert len(cases)==len({r["word"] for r in cases})==48
    for key,hist in (("word","words"),("input_sha256","input_sha256"),("traffic_sha256","traffic_sha256")):
        vals={r[key] for r in cases}
        assert len(vals)==48 and vals.isdisjoint(excluded[hist])
    for r in cases:
        p=HERE/"registration/inputs"/r["input"]
        assert sha(p.read_bytes())==r["input_sha256"]
        with p.open(encoding="utf8",newline="") as f:
            raw=[tuple(row[k] for k in ("stream","kind","release_tick","deadline_tick")) for row in csv.DictReader(f)]
        assert len(raw)==r["requests"] and sha(json.dumps(raw,separators=(",",":")).encode())==r["traffic_sha256"]
    registry=read(HERE/"tables/verification.json")
    seen=set()
    for p in (HERE/"results/runs").glob("*.json"):
        u=read(p); rec=u["receipt"]; tag=rec["case"]
        k=(tag,rec["method"],rec["repeat"])
        assert k not in seen; seen.add(k)
        assert set(u["parts"].values())<=actual and u["ready"]["affinity"]==[4]
        d=u.get("delivery",u.get("progress",{}))
        for a in d.get("attempts",[]):
            base=HERE/"results/physical"/tag/a["plan"]
            assert sha((base/"plan.json").read_bytes().strip())==a["plan"]
            m=read(base/"certificate.json")["metrics"]
            assert (m["status"],m["E_J"],m["E_bounds"],max(m["peak_hi"]))==(a["status"],a["J"],a["bounds"],a["peak_hi"])
        if rec["status"]=="SAFE":
            assert d["attempts"][-1]["status"]=="SAFE" and rec["wall_s"]<=10
        if tag.startswith("N") and rec["method"]!="terminal": assert tag in registry["triggered"]
    assert len(seen)==registry["routes"]
    print(len(listed),"verified files,",len(seen),"paid routes,",registry["flows"],"independent flows")

if __name__=="__main__":
    verify()
