"""Lossless, deterministic event archive. No simulator imports are needed to read it.

One payload stores a clock schedule once for both thermal treatments and all
environments. Workload IDs and absolute nanosecond releases are explicit. A
request pattern holds (stage descriptor, start relative to release) pairs.
Repeated patterns are interned per schedule, including blocking-induced waits.
"""
import base64
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import zlib


VERSION = 1
SHARD_LIMIT = 750_000
RESOURCE_ORDER = {name: i for i, name in enumerate(
    (*("CPU" + str(i) for i in range(8)), "GPU", "DLA0", "DLA1", "XFER")
)}


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _intern(table, key):
    idx = table.get(key)
    if idx is None:
        idx = len(table)
        table[key] = idx
    return idx


def _encode(requests, schedule):
    requests = tuple(requests)
    release = {r.id: int(r.release_ns) for r in requests}
    if len(release) != len(requests) or set(release) != set(schedule.completions_ns):
        raise ValueError("archive requires unique, eventually completed requests")
    descriptors, patterns = {}, {}
    by_request = defaultdict(list)
    previous = None
    for row in schedule.rows:
        order = (row.start_ns, RESOURCE_ORDER[row.resource])
        if previous is not None and order <= previous:
            raise ValueError("dispatcher rows not in canonical order or overlapping simultaneous starts")
        previous = order
        items = by_request[row.request]
        if row.stage_index != len(items):
            raise ValueError("missing or disordered request stage")
        duration = int(row.end_ns) - int(row.start_ns)
        if duration <= 0:
            raise ValueError("nonpositive service time")
        desc = (row.stage, row.resource, duration, float(row.activity_w))
        items.append((_intern(descriptors, desc), int(row.start_ns) - release[row.request]))

    jobs = []
    for req in requests:
        stages = tuple(by_request[req.id])
        if not stages:
            raise ValueError("request has no stages")
        pattern = _intern(patterns, stages)
        finish = int(schedule.completions_ns[req.id])
        jobs.append((req.id, int(req.app), int(req.release_ns), int(req.deadline_ns), finish, pattern))
    return [int(schedule.window_ns), list(descriptors), list(patterns), jobs]


def _decode(payload):
    window, descriptors, patterns, jobs = payload
    requests, rows = [], []
    for rid, app, release, deadline, finish, pattern_id in jobs:
        requests.append(dict(id=rid, app=app, release_ns=release, deadline_ns=deadline, completion_ns=finish))
        for index, (desc, relative) in enumerate(patterns[pattern_id]):
            name, unit, duration, watts = descriptors[desc]
            start = release + relative
            end = start + duration
            rows.append(dict(request=rid, stage=name, stage_index=index, resource=unit,
                             start_ns=start, end_ns=end, activity_w=watts))
        if end != finish:
            raise ValueError("serialized final stage and request completion differ")
    rows.sort(key=lambda r: (r["start_ns"], RESOURCE_ORDER[r["resource"]]))
    return dict(window_ns=window, requests=requests, rows=rows)


class Ledger:
    """Collect compact packets in memory and write them in schedule ID order."""

    def __init__(self):
        self._packets = {}

    def add(self, schedule_id, requests, schedule):
        if not isinstance(schedule_id, str) or not schedule_id or schedule_id in self._packets:
            raise ValueError("schedule ID must be a unique, nonempty string")
        plain = _json_bytes(_encode(requests, schedule))
        compressed = base64.b64encode(zlib.compress(plain, level=6)).decode("ascii")
        self._packets[schedule_id] = _json_bytes([schedule_id, _digest(plain), compressed]) + b"\n"

    def save(self, raw_path):
        target = Path(raw_path) / "ledger"
        target.mkdir(parents=True, exist_ok=True)
        shards = []
        pending = bytearray()
        count = 0

        def flush():
            name = f"events-{len(shards):03d}.jsonl"
            (target / name).write_bytes(pending)
            shards.append(dict(name=name, schedules=count, bytes=len(pending), sha256=_digest(pending)))
            pending.clear()

        for key in sorted(self._packets):
            packet = self._packets[key]
            if len(packet) > SHARD_LIMIT:
                raise ValueError(f"event packet exceeds shard limit: {key}")
            if pending and len(pending) + len(packet) > SHARD_LIMIT:
                flush()
                count = 0
            pending.extend(packet)
            count += 1
        if pending:
            flush()
        manifest = dict(schema=VERSION, encoding="json/deflate-zlib/base64", schedule_count=len(self._packets),
                        shards=shards)
        (target / "manifest.json").write_bytes(json.dumps(manifest, indent=2).encode("ascii") + b"\n")
        return manifest


def iter_schedules(raw_path):
    """Yield (schedule ID, window/requests/rows) and verify both levels of digests."""
    target = Path(raw_path) / "ledger"
    manifest = json.loads((target / "manifest.json").read_bytes())
    if manifest["schema"] != VERSION:
        raise ValueError("unsupported event archive schema")
    seen = set()
    for shard in manifest["shards"]:
        data = (target / shard["name"]).read_bytes()
        lines = data.splitlines()
        if (_digest(data) != shard["sha256"] or len(data) != shard["bytes"]
                or len(lines) != shard["schedules"]):
            raise ValueError(f"event shard failed integrity check: {shard['name']}")
        for line in lines:
            key, checksum, encoded = json.loads(line)
            plain = zlib.decompress(base64.b64decode(encoded, validate=True))
            if key in seen or _digest(plain) != checksum:
                raise ValueError(f"duplicate or corrupt event schedule: {key}")
            seen.add(key)
            yield key, _decode(json.loads(plain))
    if len(seen) != manifest["schedule_count"]:
        raise ValueError("event schedule count mismatch")
