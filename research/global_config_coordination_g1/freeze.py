"""Lock input bytes, upstream Git provenance and generated request tables before production."""
import hashlib
import importlib.metadata as metadata
import platform
import subprocess
from g1io import *

PINS={"P1":"be641ce06a4f496d2b1f233a09bdfc3776738668","E1":"57feace657d4ecd495df3b1211ec42161cfee763",
      "E2a":"d313094505db8eb1114b0d5859210b058f7bfa76"}
def git(*args):
    return subprocess.check_output(["git",*args],cwd=REPO)
def lock():
    selected={
        "P1":[P1/n for n in ("model.py","heat.py","profiles.py","mechanism.py","search.py","random_order.py",
                      "config/p1_frozen.json","config/cpu_npu_profiles.csv","config/gpu_profiles.csv",
                      "instances/D1.csv","instances/D2.csv","instances/D3.csv")],
        "E1":[*[(E1/n) for n in ("common.py","compact.py","master.py","inputs.py","validation.py","e0/equivalence.csv")],
              *[(common.FOLLOW/n) for n in ("assets.py","local_domain.py","diagnostic.py","frozen.json")]],
        "E2a":[E2/n for n in ("assets_e2.py","reference_objective.py","verify_core.py","validation/finite.csv")]}
    locked=[]
    for src,paths in selected.items():
        for path in paths:
            rel=path.relative_to(REPO).as_posix()
            blob=git("rev-parse",PINS[src]+":"+rel).decode().strip()
            byt=path.read_bytes()
            assert byt==git("cat-file","blob",blob),rel
            locked.append(dict(path=rel,commit=PINS[src],git_blob=blob,sha256=sha(byt)))
    for name in SIZES:instance_csv(name)
    for n in ("D1","D2","D3"):
        with (P1/"instances"/(n+".csv")).open(encoding="utf8",newline="") as f:old=list(csv.DictReader(f))
        assert old==[{k:str(v) for k,v in row.items()} for row in problem(n).req]
    rt=[(p.relative_to(runtime).as_posix(),sha(p.read_bytes())) for p in sorted(runtime.rglob("*"))
        if p.is_file() and p.suffix in (".py",".pyd",".dll") and "__pycache__" not in p.parts]
    write(HERE/"input_lock.json",dict(pins=PINS,upstream=locked,
          new_instances={x.name:sha(x.read_bytes()) for x in sorted((HERE/"instances").glob("*.csv"))},
          python=platform.python_version(),packages={k:metadata.version(k) for k in ("ortools","numba","numpy","protobuf","pandas")},
          solver_runtime_files=rt))
if __name__=="__main__":lock()
