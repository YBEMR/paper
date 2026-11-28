"""Restore only primary device IDs and run a strictly budgeted 12-stream gate."""
import os
import signal
import time

START = time.perf_counter()
os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
signal.setitimer(signal.ITIMER_REAL, 119)

import csv
import hashlib
import json
import platform
import tarfile
import zlib
from pathlib import Path
from solver import ROOT, f, m, evaluate

DEST = ROOT / "stage1"
HISTORY = ROOT.parent / "ch3_integrated_quality_v3"


def project():
    catalog = {name.removeprefix("./"): sha for sha, name in
               (line.split("  ", 1) for line in (HISTORY / "SHA256SUMS").read_text().splitlines())}

    def verify(path):
        with path.open("rb") as stream:
            assert hashlib.file_digest(stream, "sha256").hexdigest() == catalog[path.relative_to(HISTORY).as_posix()]

    table = HISTORY / "tables/runs.csv"
    verify(table)
    with table.open() as stream:
        rows = [r for r in csv.DictReader(stream) if r["arm"] == "hot" and r["rep"] == "1"]
    assert len(rows) == len({r["case"] for r in rows}) == 12
    for row in rows:
        code, key = row["case"], row["plan"]
        path = HISTORY / "archive" / code / "physical"
        verify(path / "index.json")
        index = f.read(path / "index.json")["plans"][key]
        arch = path / index["archive"]
        verify(arch)
        with tarfile.open(arch) as archive:
            def unpack(name):
                return zlib.decompress(archive.extractfile(key + "/" + name).read())
            body, cert = unpack("plan"), unpack("certificate")
        assert f.digest(body.strip()) == key and f.digest(body) == index["plan_sha"]
        assert f.digest(cert) == index["cert_sha"]
        p = m.endpoint(json.loads(cert))
        assert p["status"] == "SAFE" and p["plan"] == key and p["J"] == float(row["J"])
        mapping = bytes(r[0] for r in json.loads(body)["rows"][1::3])
        f.save(DEST / "history" / (code + ".json"), dict(point=p, mapping_sha=f.digest(mapping),
               trace_sha=index["trace_sha"], certificate_sha=index["cert_sha"], archive=arch.name, rep=1))
        (DEST / "inputs").mkdir(exist_ok=True)
        (DEST / "inputs" / (code + ".bin")).write_bytes(mapping)


def main():
    DEST.mkdir()
    f.save(DEST / "environment.json", dict(source=os.environ["GITHUB_SHA"], run=os.environ["GITHUB_RUN_ID"],
           host=platform.node(), core=list(os.sched_getaffinity(0)), limit_s=120))
    project()
    # Includes imports, archive projection, stack initialization, JIT and evidence writes.
    m.RUN = m.u2.stack()
    m.CLOCK = START
    for obj in m.u2.CASES:
        code = m.label(obj)
        folder = DEST / "cases" / code
        folder.mkdir(parents=True)
        begin = time.perf_counter()
        eng, flow = m.build(obj, folder)
        mapping = (DEST / "inputs" / (code + ".bin")).read_bytes()
        def emit(stage, point, reason):
            f.save(folder / (stage + ".json"), dict(stage=stage, point=point, reason=reason,
                   mapping_sha=f.digest(mapping), elapsed_s=time.perf_counter()-begin))
        evaluate(eng, flow, mapping, folder, emit)
    f.save(DEST / "receipt.json", dict(elapsed_s=time.perf_counter()-START, limit_s=120, cases=12))
    signal.setitimer(signal.ITIMER_REAL, 0)


if __name__ == "__main__":
    main()
