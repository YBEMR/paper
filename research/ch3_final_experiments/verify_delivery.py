"""Check exported tables, trace identities, figure formats and the original input digests."""
import csv
import hashlib
import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parent
source=Path(sys.argv[1])
def table(name):
    with (ROOT/"derived"/(name+".csv")).open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))
def sha(path):
    with path.open("rb") as f: return hashlib.file_digest(f,"sha256").hexdigest()
inventory=table("evidence_inventory")
for f in inventory: assert sha(source/f["path"])==f["sha256"],f["path"]
cases=table("instances");m=table("coverage_matrix")
assert len(cases)==12 and len({x["request_sha"] for x in cases})==4
assert len(m)==len({(x["instance_id"],x["method_id"]) for x in m})==108
a=table("figAB_method_comparison");fg=table("figFG_matched_pressure")
assert len(a)==len(fg)==48
assert sum(bool(x["energy_j"]) for x in a)==4 and sum(bool(x["energy_j"]) for x in fg)==7
assert all(not x["energy_j"] for x in a+fg if x["method_id"]!="CT-Joint")
d=table("reset_confusion");p=table("pressure_classification")
assert len(p)==12 and all(int(x["safe"])+int(x["overtemp"])+int(x["unresolved"])==int(x["deadline_legal"]) for x in p)
assert len(table("candidate_diagnostics"))==int(d[-1]["false_accept"])==4707
e=table("ablation_results");assert len(e)==4
for x in e:
    assert abs(float(x["delta_pct"])-100*(1-float(x["best_safe_j"])/float(x["reference_j"])))<1e-10
    assert x["status"]=="SAFE"
    if x["peak_upper_c"]:assert float(x["peak_upper_c"])<=80
g=table("classification")
assert len(g)==212 and all(sum(int(x[k]) for k in ["safe","deadline_failed","overtemp","unresolved"])==27**4 for x in g)
for letter in "CDE":
    stem=ROOT/"figures"/("fig"+letter)
    assert stem.with_suffix(".png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert stem.with_suffix(".pdf").read_bytes().startswith(b"%PDF")
    assert ET.parse(stem.with_suffix(".svg")).getroot().tag.endswith("svg")
out=dict(status="PASS",result_commit=inventory[0]["commit"],inputs_sha256_rechecked=len(inventory),
         instances=len(cases),coverage_rows=len(m),complete_grids=len(g),pressure_units=len(p),false_accepts=4707,
         figures_verified=["C","D","E"],formats=["SVG","PDF","PNG"],new_scientific_calls=0)
(ROOT/"audit/validation.json").write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8",newline="\n")
print(json.dumps(out))
