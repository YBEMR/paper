"""Paths and the public diagnostic sample for the M1-j factorial."""
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
I=ROOT.parent/"m1i_generalization"
REG=ROOT/"registration"
DATA=ROOT/"data"
WORK=ROOT/"work"
BASE="85969e8ed78cbab4d693122819ebe866e0721bb7"
METHODS=("NT","NT-S","NC","NC-S")
sys.path.insert(0,str(I))
from design import sha,write_json

def inputs():
    rows=json.loads((I/"registration/cases.json").read_bytes())["cases"]
    cases=[c for c in rows if c["group"] in "ABC" and c["ambient"]==35]
    assert len(cases)==len({c["flow"] for c in cases})==12
    for c in cases:
        assert sha((I/"registration/inputs"/c["input"]).read_bytes())==c["input_sha256"]
    return cases

def write_csv(path,rows,fields=None):
    rows=list(rows)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=fields or list(rows[0]),lineterminator="\n")
        w.writeheader();w.writerows(rows)
