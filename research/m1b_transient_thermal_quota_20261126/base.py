import os
import sys
import json
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parent
M1 = next(p for p in (ROOT.parent/"M1_quota_20261126", ROOT.parent/"m1_transient_thermal_quota_20261126") if (p/"mechanism.py").is_file())
os.environ["NUMBA_CACHE_DIR"] = str(ROOT/".cache")
for var in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS","NUMBA_NUM_THREADS"):
    os.environ[var]="1"
sys.path.insert(0,str(M1))
from mechanism import Case, WINDOW, np, p1, digest
from search import diverse


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save(path,obj):
    p1.put(path,obj)


def check_base():
    manifest=(M1/"SHA256SUMS").read_bytes()
    assert sha256(manifest).hexdigest()=="2127f62d51cf7b8e346e1910b1308592c140107ef803e7cfd78a97177c1e3ac5"
    for line in manifest.decode().splitlines():
        sha,name=line.split("  ",1)
        assert sha256((M1/name).read_bytes()).hexdigest()==sha,name


def window_types(c,j):
    lo,hi=c.release.searchsorted([j*WINDOW,(j+1)*WINDOW])
    t=c.kinds[lo:hi]
    a,b=map(int,np.bincount(t,minlength=2))
    return t,a,b


def materialize(c,history):
    return b"".join(c.extension(*window_types(c,j),*action) for j,action in enumerate(history))
