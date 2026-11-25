"""Pinned artifacts, environment and byte-preserving receipts."""
import csv,gzip,hashlib,json,os,sys,tempfile,time
from pathlib import Path
from fractions import Fraction as Q

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
OLD=ROOT.parent/"cross_scene_taskflow_diagnostic"
FOLLOW=ROOT.parent/"cross_scene_taskflow_followup"
BASE="5133db0d8d449cbce5c8fe924672eb928f9b74d4"
V1="be641ce06a4f496d2b1f233a09bdfc3776738668"
for item in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","VECLIB_MAXIMUM_THREADS","NUMEXPR_NUM_THREADS","NUMBA_NUM_THREADS","BLIS_NUM_THREADS"):
    os.environ[item]="1"
sys.dont_write_bytecode=True
os.environ["NUMBA_CACHE_DIR"]=str(Path(tempfile.gettempdir())/"domain-joint-thermal-v1")
os.environ["MPLCONFIGDIR"]=str(Path(tempfile.gettempdir())/"domain-joint-mpl-v1")
sys.path[:0]=[str(REPO/".runtime-domain-cpsat"),str(OLD)]
NODES=("CPU1","CPU2","GPU","NPU")
DOM=(0,0,1,2)
MEMBERS=((0,1),(2,),(3,))
TOL=1e-6
def raw(obj):return json.dumps(obj,ensure_ascii=False,allow_nan=False,separators=(",",":"),default=str).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads((ROOT/p).read_bytes())
def save(p,v):
    p=ROOT/p;p.parent.mkdir(exist_ok=True,parents=True)
    tmp=p.with_suffix(p.suffix+".tmp");tmp.write_bytes(raw(v)+b"\n");tmp.replace(p)
def table(p,r):
    p=ROOT/p;p.parent.mkdir(exist_ok=True,parents=True)
    with p.open("w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(r[0]),lineterminator="\n");w.writeheader();w.writerows(r)
def obj(case,plan):return dict(case=case,rows=plan[0],low=sorted(plan[1]))
def decode(o):return [tuple(x) for x in o["rows"]],frozenset(map(tuple,o["low"]))
def archived(case,follow=False):
    if follow:
        with (FOLLOW/"results/summary.csv").open() as f:k=next(r["safe_sha"] for r in csv.DictReader(f) if r["case"]==case)
        plan=FOLLOW/"results/plans"/(k+".json.gz")
    else:
        k=json.loads((OLD/"g3_thermal"/(case+"_G3.json")).read_bytes())["safe_plan"]
        plan=OLD/"logs/plans"/(k+".json.gz")
    o=json.loads(gzip.decompress(plan.read_bytes()));assert sha(raw(o))==k and o["case"]==case
    return k,decode(o)
def store_plan(case,plan):
    data=raw(obj(case,plan));k=sha(data);p=ROOT/"e1/plans"/(k+".json.gz")
    if not p.exists():
        p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(gzip.compress(data,compresslevel=2,mtime=0))
    return k
def load_plan(k):
    data=gzip.decompress((ROOT/"e1/plans"/(k+".json.gz")).read_bytes());assert sha(data)==k
    return decode(json.loads(data))
