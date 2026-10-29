"""Write-once evidence and immutable progress snapshots; no replacement or retry."""

import hashlib
import json
import os
from pathlib import Path


def _encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def write_once(path, value):
    # Serialize first; a serialization error must not leave an empty final file.
    payload = _encode(value)
    with Path(path).open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


class SnapshotLog:
    """One owner, monotonically numbered files. Any write failure stops the caller."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir()  # Existing logs cannot be resumed implicitly.
        self.sequence = 0

    def append(self, value):
        self.sequence += 1
        record = {"sequence": self.sequence, "record": value,
                  "record_sha256": hashlib.sha256(_encode(value)).hexdigest()}
        path = self.directory / f"{self.sequence:06d}.json"
        write_once(path, record)
        return path


def read_latest_snapshot(directory):
    """Read the last complete snapshot; reject gaps/corruption, never skip them."""
    directory = Path(directory)
    if not directory.exists():
        return None
    files = sorted(directory.glob("*.json"))
    if not files:
        return None
    if [p.name for p in files] != [f"{i:06d}.json" for i in range(1, len(files) + 1)]:
        raise ValueError("PROGRESS_SEQUENCE_GAP")
    latest = json.loads(files[-1].read_bytes())
    if (set(latest) != {"sequence", "record", "record_sha256"}
            or type(latest["sequence"]) is not int or latest["sequence"] != len(files)
            or hashlib.sha256(_encode(latest["record"])).hexdigest() != latest["record_sha256"]):
        raise ValueError("PROGRESS_SNAPSHOT_CORRUPT")
    return latest["record"]


def read_terminal_record(directory, *, exit_code=None):
    """Failure markers dominate. A readable COMPLETE alone never proves success."""
    directory = Path(directory)
    failure = directory / "terminal_failure.json"
    if failure.exists():
        result = json.loads(failure.read_bytes())  # Corrupt failure must not fall back.
        if not isinstance(result, dict) or not str(result.get("state", "")).startswith("STOPPED_"):
            raise ValueError("INVALID_TERMINAL_FAILURE_RECORD")
        return result
    result = json.loads((directory / "batch_result.json").read_bytes())
    if not isinstance(result, dict) or "state" not in result:
        raise ValueError("INVALID_TERMINAL_RECORD")
    if result["state"] == "COMPLETE" and (type(exit_code) is not int or exit_code != 0):
        raise ValueError("COMPLETE_REQUIRES_CONFIRMED_ZERO_EXIT_CODE")
    return result
