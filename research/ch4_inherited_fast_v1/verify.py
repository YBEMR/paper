"""Verify delivered evidence offline, separately from every budgeted call."""
import gzip
import hashlib
import json
import platform
import statistics
import tarfile
import zlib
from collections import Counter, defaultdict
from importlib.metadata import version
from pathlib import Path

from run import HERE, S
from summarize import read
import numpy as np


def sha(data):
    return hashlib.sha256(data).hexdigest()


def events(path):
    if not path.exists():
        return []
    lines = gzip.decompress(path.read_bytes()).splitlines()
    return [json.loads(line) for line in lines if line.endswith(b"}")]


def verify_case(case, horizon):
    folder = HERE / "results" / case / "physical"
    index = json.loads((folder / "index.json").read_bytes())
    parts, plans, certs = {}, {}, {}
    for archive in folder.glob("*.tar"):
        with tarfile.open(archive, "r|") as bundle:
            for item in bundle:
                key, kind = item.name.split("/")
                data = zlib.decompress(bundle.extractfile(item).read())
                if key == "blocks":
                    assert sha(data) == kind
                    parts[kind] = data
                elif kind == "plan":
                    assert sha(data.strip()) == key
                    plans[key] = json.loads(data)
                else:
                    assert sha(data) == index["plans"][key]["cert_sha"]
                    certs[key] = json.loads(data)["metrics"]
    assert set(plans) == set(certs) == set(index["plans"])
    maps = {}
    for key, item in index["plans"].items():
        data = b"".join(parts[part] for part in item["blocks"])
        assert sha(data) == item["trace_sha"]
        trace = np.frombuffer(data, dtype=np.float64).reshape(item["shape"])
        assert trace.shape[1] == 31 and np.isfinite(trace).all()
        assert trace[0, 0] == 0 and trace[-1, 1] == horizon
        assert np.all(trace[:, 1] > trace[:, 0])
        assert np.array_equal(trace[:-1, 1], trace[1:, 0])
        assert np.array_equal(trace[:-1, 18:22], trace[1:, 14:18])
        m = certs[key]
        assert m["min_deadline_slack_ms"] >= 0
        assert abs(m["external_J"] - .3*horizon/10000) < 1e-10
        energy = float(trace[:, 26:30].sum()) + m["external_J"]
        assert m["E_bounds"][0] <= energy <= m["E_bounds"][1]
        if m["status"] == "SAFE":
            assert max(m["peak_hi"]) <= 80
        maps[key] = sha(bytes(row[0] for row in plans[key]["rows"][1::3]))
    return maps, certs


def main():
    registration = S / "nt/research/m1i_generalization/registration"
    flows = [x for x in json.loads((registration / "cases.json").read_bytes())["cases"] if x["ambient"] == 35]
    lanes, cpu_for, physical, statuses = defaultdict(list), {}, {}, Counter()
    late = 0
    teardown = []
    cells = read("cells")
    expected = {(o["case"].split("_")[0], a, str(c), str(r)) for o in flows
                for a in "BC" for c in (10, 20) for r in range(1, 4)}
    assert len(cells) == len(expected) == 144
    assert {(r["case"], r["arm"], r["cap"], r["rep"]) for r in cells} == expected
    for o in flows:
        case = o["case"].split("_")[0]
        assert sha((registration/"inputs"/o["input"]).read_bytes()) == o["input_sha256"]
        maps, certs = verify_case(case, o["horizon_ticks"])
        seen = set()
        physical[case] = len(maps)
        for row in (r for r in cells if r["case"] == case):
            cap = int(row["cap"])
            arm = {"B": "N", "C": "O"}[row["arm"]]
            folder = HERE / "results" / case / f"r{row['rep']}-{arm}-{cap}"
            receipt = json.loads(gzip.decompress((folder/"receipt.json.gz").read_bytes()))
            cpu = receipt["cpu"]
            assert cpu_for.setdefault(case, cpu) == cpu
            started = receipt["origin"]
            lanes[cpu].append((started, started + receipt["wall"]))
            teardown.append(max(0, receipt["wall"] - cap))
            assert receipt["method"] == arm and receipt["cap"] == cap
            search = events(folder/"search.jsonl.gz")
            refine = events(folder/"refine.jsonl.gz")
            assert next(e["request_sha"] for e in search if "request_sha" in e) == o["input_sha256"]
            received = [e for e in search + refine if e["event"] == "certificate"]
            late += sum(e["t"] > cap for e in received)
            received = [e for e in received if e["t"] <= cap]
            assert len(received) == int(row["cert_count"])
            for e in received:
                pt = e["point"]
                key = pt["plan"]
                m = certs[key]
                assert pt["status"] == m["status"] and pt["bounds"] == m["E_bounds"] and pt["J"] == m["E_J"]
                seen.add(key)
                statuses[pt["status"]] += 1
            safe = [e for e in received if e["point"]["status"] == "SAFE"]
            assert bool(safe) == bool(int(row["safe"]))
            if not safe:
                continue
            assert float(row["first_safe_s"]) == safe[0]["t"]
            best = safe[0]
            for e in safe[1:]:
                if e["point"]["bounds"][1] < best["point"]["bounds"][0]:
                    best = e
            key = best["point"]["plan"]
            assert key == row["final_plan"] and best["t"] == float(row["best_s"])
            assert maps[key] == row["final_mapping_sha256"]
            if best.get("rank"):
                seed = next(e["seed"] for e in refine if e["event"] == "map_start" and e["rank"] == best["rank"])
                assert maps[seed] == maps[key]
        assert seen == set(maps)
    for lane in lanes.values():
        lane.sort()
        assert all(a[1] <= b[0] for a,b in zip(lane,lane[1:]))
    for case in ("A01","C10"):
        for rep in range(4):
            samples = [r for r in read("fixed_work") if r["case"] == case and r["rep"] == str(rep)]
            assert len(samples) == 2 and all(r["complete"] == "True" and r["parents"] == "1" for r in samples)
            assert len({(r["slots"], r["groups"]) for r in samples}) == 1
    result = dict(unique_physical=physical, delivered=dict(statuses), excluded_after_cutoff=late,
                  median_supervisor_overhang_s=statistics.median(teardown),max_supervisor_overhang_s=max(teardown),
                  cores_by_case=cpu_for, runtime=platform.platform(), python=platform.python_version(),
                  packages={p:version(p) for p in ("numpy","scipy","numba","llvmlite","psutil")})
    (HERE/"tables/verification.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
