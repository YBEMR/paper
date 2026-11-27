"""Copy two historical plans by immutable identity; no scheduler calls."""
import hashlib
import json
import os
import tarfile
from pathlib import Path

out = Path(__file__).resolve().parent / "history"
out.mkdir(exist_ok=True)
def recover(code, key, tar):
    target = out / code
    target.mkdir()
    for ent in tar:
        parts = ent.name.split("/")
        if len(parts) >= 2 and parts[-2] == key and parts[-1] in {"plan.json", "certificate.json"}:
            data = tar.extractfile(ent).read()
            (target / parts[-1]).write_bytes(data)
            if all((target / n).exists() for n in ("plan.json", "certificate.json")):
                break
    assert hashlib.sha256((target / "plan.json").read_bytes().strip()).hexdigest() == key
    assert json.loads((target / "certificate.json").read_bytes())["metrics"]["status"] == "SAFE"
if __name__ == "__main__":
    import sys, time
    t = time.perf_counter()
    with tarfile.open(sys.argv[1], "r|gz") as a:
        recover("A06", "86977c7a44a85dabaf60deb0a839afdf7e88608051f621a0f9dc9e1248f51901", a)
    with tarfile.open(sys.argv[2], "r|xz") as a:
        recover("C11", "80afa7c4a045d3c16623e4073ffeb4115c25c2d2d37bd59f5b9504a5649cd928", a)
    (out / "recovery_time.json").write_text(json.dumps({"wall_s":time.perf_counter()-t,"cpu_s":time.process_time()}))
