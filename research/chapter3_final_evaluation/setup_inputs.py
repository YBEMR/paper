"""Materialize P1 request tables and verify pinned source identities before any formal search."""
import csv
import hashlib
import io
import json
from fractions import Fraction
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
RESEARCH = ROOT.parent
G2 = RESEARCH / "critical_interval_coordination_g2"
G1 = RESEARCH / "global_config_coordination_g1"
P1 = RESEARCH / "cross_scene_taskflow_diagnostic"
sys.path.insert(0, str(G2))
from assets import g1io, problem
from profiles import CFG, requests

PINS = {"P1": "be641ce06a4f496d2b1f233a09bdfc3776738668", "E1": "57feace657d4ecd495df3b1211ec42161cfee763",
        "E2a": "d313094505db8eb1114b0d5859210b058f7bfa76", "G1": "315ae008a6f5f740fc3130e52dbf1ce9ab80f14b",
        "G2": "b3614617d665831d28e6ee7e5054222fc07834a0"}
CASES = {"S32": 32, "S80": 80, "D1": 160, "D2": 160, "F1": 120, "F2": 130}
for name, scenes in (("F1", list("LMH")), ("F2", list("HLH"))):
    CFG["instances"][name] = [scenes, Fraction(1, 2), 35, 1]

def sha(data):
    return hashlib.sha256(data).hexdigest()

def serialized(name):
    rows = requests(name)
    assert len(rows) == CASES[name]
    out = io.StringIO(newline="")
    w = csv.DictWriter(out, fieldnames=rows[0], lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return out.getvalue().encode()

def checked_problem(name):
    if name != "S16":
        assert serialized(name) == (ROOT/"instances"/(name+".csv")).read_bytes()
    p = problem(name)
    assert p.ta == 35 and p.c == 1 and all(r["deadline_ms"]-r["release_ms"] == 300 for r in p.req)
    return p

def main():
    dest = ROOT/"instances"
    dest.mkdir(exist_ok=True)
    lock = json.loads((G1/"input_lock.json").read_bytes())
    for r in lock["upstream"]:
        # Only model assets and development inputs; no D3 or holdout workloads are run.
        if "/instances/" not in r["path"] or r["path"].endswith(("/D1.csv", "/D2.csv")):
            assert sha((RESEARCH.parent/r["path"]).read_bytes()) == r["sha256"], r["path"]
    frozen = json.loads((G2/"formal_lock.json").read_bytes())
    for name, digest in frozen["files"].items():
        assert sha((G2/name).read_bytes()) == digest, name
    rows = {}
    for name in CASES:
        path = dest/(name+".csv")
        data = serialized(name)
        if path.exists():
            assert path.read_bytes() == data
        else:
            path.write_bytes(data)
        p = checked_problem(name)
        if name in ("S32", "S80", "D1", "D2"):
            old = (G1 if name.startswith("S") else P1)/"instances"/path.name
            assert old.read_bytes() == data
        rows[name] = {"sha256": sha(data), "count": len(p.req), "boundaries": p.boundaries,
                      "horizon_ticks": p.horizon, "scenes": CFG["instances"][name][0],
                      "counts_by_scene": [sum(r["scene"] == i for r in p.req) for i in range(len(p.boundaries)+1)]}
    payload = {"commits": PINS, "G2_tree": "d221149fd064bdfb56fe39c2b166a01c9a80d9b1",
               "G1_input_lock": sha((G1/"input_lock.json").read_bytes()), "instances": rows}
    (ROOT/"inputs.json").write_text(json.dumps(payload, indent=2)+"\n", encoding="utf8", newline="\n")
    print(json.dumps(rows))

if __name__ == "__main__":
    main()
