"""Read-only registration and rank-key audit. Run from any directory with Python 3.9+."""
import ast
import csv
import hashlib
import itertools
import json
from bisect import bisect_left
from collections import Counter
from fractions import Fraction
from math import ceil, floor
from pathlib import Path

J = Path(__file__).resolve().parent
I = J.parent / "m1i_generalization"
REPO = J.parents[1]
ARMS = ("NT", "NT-S", "NC", "NC-S")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def selector_function(path, name):
    # Load just the actual selector body. Importing the search framework would load P1.
    syntax = ast.parse(path.read_bytes())
    fn, = (node for node in syntax.body if isinstance(node, ast.FunctionDef) and node.name == name)
    context = {"bisect_left": bisect_left}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(path), "exec"), context)
    return context[name]


def check_registration():
    cases = json.loads((J / "registration/cases.json").read_bytes())
    previous = json.loads((I / "registration/cases.json").read_bytes())["cases"]
    assert cases == [c for c in previous if c["group"] in ("A", "B", "C") and c["ambient"] == 35]
    assert len(cases) == len({c["input_sha256"] for c in cases}) == 12
    with (J / "registration/rotation.csv").open(newline="", encoding="utf8") as f:
        slots = list(csv.DictReader(f))
    assert len(slots) == 144
    for c in cases:
        raw = (I / "registration/inputs" / c["input"]).read_bytes()
        assert sha(raw) == c["input_sha256"]
        rows = list(csv.DictReader(raw.decode().splitlines()))
        assert len(rows) == c["requests"]
        for row in rows:
            release, deadline = Fraction(row["release_ms"]), Fraction(row["deadline_ms"])
            assert deadline - release == 300
            assert int(row["release_tick"]) == ceil(10 * release)
            assert int(row["deadline_tick"]) == floor(10 * deadline)
        for repeat in range(3):
            start = (c["index"] + repeat) % len(ARMS)
            expected = ARMS[start:] + ARMS[:start]
            group = [s for s in slots if s["case"] == c["case"] and int(s["repeat"]) == repeat + 1]
            assert tuple(s["method"] for s in group) == expected
            assert [int(s["position"]) for s in group] == [1, 2, 3, 4]
            assert all(int(s["lane"]) == c["index"] % 6 for s in group)
    return len(cases), len(slots), sum(c["requests"] for c in cases)


def check_selectors():
    frozen_path = REPO / "research/m1_transient_thermal_quota_20261126/search.py"
    scalar_path = J / "retention.py"
    manifest = json.loads((J / "registration/hashes.json").read_bytes())
    for path in (frozen_path, scalar_path):
        assert sha(path.read_bytes()) == manifest[path.relative_to(REPO).as_posix()]
    complementary = selector_function(frozen_path, "diverse")
    scalar = selector_function(scalar_path, "scalar_four")
    metrics = ("energy", "drain", "risk")
    counts = Counter()
    # Eight ordinal corners, plus two ties at and inside the rounding precision.
    values = list(itertools.product((0., 1.), repeat=3)) + [(0., 0., 0.), (1e-13, 1., 1.)]
    states = [dict(zip(metrics, v), config=bytes([i]), id=i) for i, v in enumerate(values)]
    for size in range(1, len(states) + 1):
        for pool in itertools.combinations(states, size):
            def val(s, k):
                return round(s[k], 11)

            def sum_key(s):
                ranks = sum(val(t, k) < val(s, k) for t in pool for k in metrics)
                return ranks, val(s, "energy"), s["config"]

            ordered = sorted(pool, key=lambda s: (val(s, "energy"), s["config"]))
            expected = sorted(pool, key=sum_key)[:4]
            assert scalar(ordered, False) == expected
            remain = list(ordered)
            seats = []
            for metric in metrics:
                winner = min(remain, key=lambda s: (val(s, metric), val(s, "energy"), s["config"]))
                seats.append(winner)
                remain.remove(winner)
                if not remain:
                    break
            if remain:
                seats.append(min(remain, key=sum_key))
            assert complementary(ordered, False) == seats
            counts["pools"] += 1
            counts["different_four_sets"] += {s["id"] for s in seats} != {s["id"] for s in expected}
    return dict(counts)


if __name__ == "__main__":
    cases, slots, requests = check_registration()
    print(json.dumps(dict(cases=cases, registered_slots=slots, input_requests=requests,
                          synthetic=check_selectors(), timed_searches_started=0), indent=2))
