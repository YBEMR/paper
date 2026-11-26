"""Run the sealed M1-e holdout and its preregistered companions once, from empty beams."""
import hashlib
import json
import os
import platform
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "m1e_thermal_quota_ablation"
DATA = Path(os.environ.setdefault("M1E_OUTPUT", str(HERE / "data"))).resolve()
sys.path.insert(0, str(BASE))
import experiment as frozen

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def cases():
    lock = json.loads((BASE / "holdout_freeze.json").read_bytes())
    assert all(sha(BASE / name) == expected for name, expected in lock["algorithm"].items())
    old = {p.stem.split("_", 1)[1] for p in (BASE / "data/validation_inputs").glob("*.csv")}
    assert len(old) == 8 and len(lock["orders"]) == 6
    for item in lock["orders"]:
        order, n = item["order"], item["size"]
        assert len(order) * 80 == n and order not in old and order.count("L") == order.count("H")
        assert hashlib.sha256((lock["seed"] + order).encode()).hexdigest() == item["sha256"]
        yield "L" + str(n), order

def main():
    import numba, psutil, scipy
    registered = "e548e42bd401e42e3461463e79252b678c62f5f7"
    protocol = HERE / "MECHANISM_PROTOCOL.md"
    assert sha(protocol) == "8ca0028f8e1f6503d3613e83e54bc77c5e97670179c6bf1627e510eb2c2c829b"
    if (DATA / "runs").exists() or (DATA / "launch.json").exists():
        raise FileExistsError("Use a fresh output directory")
    orders = list(cases())
    process = psutil.Process()
    assert len(process.cpu_affinity()) == 1
    frozen.p1.put(DATA / "launch.json", dict(base="149967e99510f53ca10de18b796a084b64c5251e",
        registration=registered, protocol_sha256=sha(protocol), wrapper_sha256=sha(Path(__file__)),
        orders_file_sha256=sha(BASE / "holdout_freeze.json"), python=sys.version,
        platform=platform.platform(), affinity=process.cpu_affinity(), P1=frozen.p1.P1, physical_pins=frozen.p1.PIN,
        numpy=frozen.np.__version__, numba=numba.__version__, scipy=scipy.__version__,
        threads={k:os.environ[k] for k in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMBA_NUM_THREADS","OMP_NUM_THREADS")}))
    warm = frozen.p1.Engine("S32", DATA.parent / ".holdout-warm")
    warm.cert(*warm.construct("quota", 1)[0])
    for i, (label, word) in enumerate(orders):
        c = frozen.reordered(frozen.case_for(label), label, word)
        assert len(c.p.req) == int(label[1:]) and c.windows == len(word)
        budget = frozen.run(c, "HT")
        rotation = frozen.METHODS[i:] + frozen.METHODS[:i]
        for method in rotation:
            if method in ("NC", "NT", "C2", "OC", "OT"):
                frozen.run(c, method, budget)
        frozen.run(c, "BT")

if __name__ == "__main__":
    main()
