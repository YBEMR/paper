"""Frozen imports and local evidence I/O for the M1-c experiment."""
import csv
import gzip
import json
import os
import sys
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("M1C_OUTPUT", ROOT / "data")).resolve()

def sibling(*names):
    return next(ROOT.parent / n for n in names if (ROOT.parent / n / "SHA256SUMS").is_file())

OLD = sibling("M1b_quota_20261126", "m1b_transient_thermal_quota_20261126")
M1 = sibling("M1_quota_20261126", "m1_transient_thermal_quota_20261126")
os.environ["NUMBA_CACHE_DIR"] = str(DATA.parent / ".m1c-cache")
sys.path[:0] = [str(M1), str(OLD)]
from mechanism import Case, digest, np, p1, WINDOW
from base import load, save, materialize, window_types
os.environ["NUMBA_CACHE_DIR"] = str(DATA.parent / ".m1c-cache")
from search import diverse
from generator import load_planes, capacity, synthesize, anchors
from search_b import grouped_means
from time_check import make_filter

CASES = ("L800","L640","L480","L320")
def verify_inputs():
    for root, expected in ((OLD,"e99c5abb649869e7677688da140a60bce1045429032381329fc77ec7b7c750d0"),
                           (M1,"2127f62d51cf7b8e346e1910b1308592c140107ef803e7cfd78a97177c1e3ac5")):
        raw = (root / "SHA256SUMS").read_bytes()
        assert sha256(raw).hexdigest() == expected
        for line in raw.decode().splitlines():
            h, name = line.split("  ",1)
            assert sha256((root/name).read_bytes()).hexdigest() == h, name

def write_rows(path, rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    if not rows:
        return
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path,"wt",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=dict.fromkeys(k for row in rows for k in row))
        w.writeheader()
        w.writerows(rows)

def initial(c):
    return dict(config=b"",id=digest(b""),f=(0,0),k=(0,0),temperature=c.p.initial,
                peak=max(c.p.initial),history=[])
