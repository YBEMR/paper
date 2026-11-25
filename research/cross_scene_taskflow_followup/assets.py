import csv
import gzip
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from fractions import Fraction

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "cross_scene_taskflow_diagnostic"
CFG = json.loads((HERE / "frozen.json").read_bytes())
for var in ("OMP_NUM_THREADS","MKL_NUM_THREADS","OPENBLAS_NUM_THREADS","BLIS_NUM_THREADS",
            "NUMEXPR_NUM_THREADS","NUMBA_NUM_THREADS","VECLIB_MAXIMUM_THREADS"):
    os.environ[var]="1"
os.environ["NUMBA_CACHE_DIR"]=str(Path(tempfile.gettempdir()) / "p1-followup-v11-kernel")
sys.dont_write_bytecode=True
sys.path.insert(0,str(OLD))
DATA=HERE/"results"

def encode(obj):
    return json.dumps(obj,separators=(",",":"),allow_nan=False,ensure_ascii=False).encode()

def digest(data):
    return hashlib.sha256(data).hexdigest()

def write(rel,obj):
    path=DATA/rel
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".tmp")
    tmp.write_bytes(encode(obj)+b"\n")
    tmp.replace(path)

def read(rel):
    return json.loads((DATA/rel).read_bytes())

def tab(rel,rows):
    if not rows: return
    with (DATA/rel).open("w",encoding="utf-8",newline="") as f:
        out=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n")
        out.writeheader();out.writerows(rows)

def plan_obj(case,plan):
    return dict(case=case,rows=plan[0],low=sorted(plan[1]))

def unpack(o):
    return [tuple(r) for r in o["rows"]],frozenset(map(tuple,o["low"]))

def base(case):
    key=CFG["cases"][case]["sha"]
    raw=gzip.decompress((OLD/"logs"/"plans"/(key+".json.gz")).read_bytes())
    obj=json.loads(raw)
    assert obj["case"]==case and digest(encode(obj))==key
    return unpack(obj)

def put_plan(case,plan):
    obj=plan_obj(case,plan); raw=encode(obj);key=digest(raw)
    path=DATA/"plans"/(key+".json.gz")
    if not path.exists():
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(gzip.compress(raw,compresslevel=3,mtime=0))
    return key

def get_plan(key):
    raw=gzip.decompress((DATA/"plans"/(key+".json.gz")).read_bytes())
    assert digest(raw)==key
    return unpack(json.loads(raw))

def valid_c0(m):
    lo,hi=m["E_bounds"]
    return (max(m["peak_hi"])<=100 and min(m["minimum_lo"])>=20 and
            max(m["peak_hi"])-max(m["peak_lo"])<=.001 and (hi-lo)/2<=1e-6)
