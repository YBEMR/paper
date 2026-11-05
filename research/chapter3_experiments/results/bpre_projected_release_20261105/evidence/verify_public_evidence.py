"""Read-only public-artifact checks. Does not import experiment code or run SAFE."""
from pathlib import Path
import ast
from decimal import Decimal
import hashlib
import json
import time
from datetime import datetime, timezone

root = Path(__file__).resolve().parent
started = datetime.now(timezone.utc).isoformat()
t0 = time.perf_counter()
read = lambda name: json.loads((root / name).read_text(encoding="utf-8"))
expected = {}
for line in (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
    digest, name = line.split("  ", 1)
    expected[name] = digest
actual = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
          for p in root.rglob("*") if p.is_file() and p.name != "SHA256SUMS"}
assert actual == expected, "Public file set or SHA mismatch"
for p in root.rglob("*.json"):
    json.loads(p.read_text(encoding="utf-8"))
for p in root.rglob("*.py"):
    ast.parse(p.read_text(encoding="utf-8"), filename=p.name)
for line in (root / "logs/observations.jsonl").read_text(encoding="utf-8").splitlines():
    json.loads(line)
refs = read("config/frozen_reference.json")
options = read("native/request_000001.response.json")["options"]
assert len(refs["native_options"]) == 23
assert all(options[k] == v for k, v in refs["native_options"].items())
receipts = [read(f"receipts/committed_{i:06d}.json") for i in (1, 2, 3)]
for r in receipts:
    assert r["accepted_safe"] and 0 < r["admission_committed_at_s"] < 600
    assert r["original_vector_length"] == 8887 and r["native_vector_length"] == 8341
    assert r["numeric"]["numeric"]["accepted_numerically"]
    assert r["evaluation"]["state"] == "SAFE"
    assert all(s["complete"] and s["state"] == "SAFE" for s in r["evaluation"]["scenes"].values())
assert Decimal(receipts[-1]["evaluation"]["weighted_energy_J"][1]) < Decimal(receipts[0]["evaluation"]["weighted_energy_J"][0])
assert len(read("code/frozen_source_sha256.json")["source_sha256"]) == 3185
assert read("audit_checks.json")["status"] == "PASS"
print(json.dumps({"status": "PASS", "files_hashed": len(actual),
    "scope": "Public hashes, syntax and stored-evidence consistency only; no SAFE or solver",
    "start_utc": started, "end_utc": datetime.now(timezone.utc).isoformat(),
    "elapsed_seconds": time.perf_counter() - t0}, ensure_ascii=False))
