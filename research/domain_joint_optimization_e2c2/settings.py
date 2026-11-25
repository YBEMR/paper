"""Shared one-shot design and Windows-safe receipt writer."""
import hashlib
import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
COMPACT = ROOT.parent / "domain_joint_optimization_e2c_compact"
sys.path.insert(0, str(COMPACT))
for name in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS","NUMBA_NUM_THREADS","NUMEXPR_NUM_THREADS","BLIS_NUM_THREADS"):
    os.environ[name] = "1"
METHODS = ("G3", "Hybrid-Generic", "Hybrid-Old", "Hybrid-New")
SEEDS = (101, 102, 103)
INITIAL = "409a58b6369bd26171c4691447604f1dca4cec1cee72df26372a63eef73e4dc6"
BASE = "82821ae54b8a4e9b9f83ce5930c93aea2a204086"
clock = time.perf_counter

def read(path):
    return json.loads(path.read_bytes())

def write(path, data):
    path.parent.mkdir(exist_ok=True, parents=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    tmp.write_bytes((json.dumps(data, ensure_ascii=False, allow_nan=False, default=str, separators=(",",":"))+"\n").encode())
    for i in range(16):
        try:
            os.replace(tmp,path)
            return
        except PermissionError:
            if i==15: raise
            time.sleep(.004)

def sha(b):
    return hashlib.sha256(b).hexdigest()

def design(cpus):
    return [dict(method=METHODS[(j+i)%4], seed=seed, cpu=cpus[(n%len(cpus)+n//len(cpus))%len(cpus)],
                 wave=n//len(cpus)+1)
            for n,(i,j,seed) in enumerate((i,j,s) for i,s in enumerate(SEEDS) for j in range(4))]
