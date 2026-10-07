"""Extract published plot values, without executing HTML or fitting a model."""
import csv
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

root = Path(__file__).resolve().parent
source = root / "mb-powermon-hailo8-resnet50.html"
match = re.search(r"const rows\s*=\s*(\[.*?\]);", source.read_text(encoding="utf-8"), re.S)
if match is None:
    raise ValueError("Published rows array missing")
rows = json.loads(match.group(1))
assert rows and all(len(row) == 7 for row in rows)
headers = ["timestamp", "c6_power_W", "c6_TS0_C", "c6_TS1_C", "c4_power_W", "c4_TS0_C", "c4_TS1_C"]
with (root / "published_plot_values.csv").open("w", encoding="utf-8", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(headers)
    writer.writerows(rows)
times = [datetime.fromisoformat(row[0]) for row in rows]
assert all(a <= b for a, b in zip(times, times[1:]))
summary = {
    "source": "https://github.com/AlbertaBeef/mb-powermon/blob/main/assets/mb-powermon-hailo8-resnet50.html",
    "retrieved": "2026-09-22",
    "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    "kind": "Published HTML plot values; not original instrument CSV or a new experiment",
    "rows": len(rows),
    "duration_s": (times[-1] - times[0]).total_seconds(),
    "columns": {},
}
for i, name in enumerate(headers[1:], 1):
    values = [row[i] for row in rows if row[i] is not None]
    summary["columns"][name] = {"min": min(values), "max": max(values), "missing": len(rows) - len(values)}
(root / "public_trace_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2, ensure_ascii=False))
