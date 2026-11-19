"""Execute exactly one separately authorized retry using frozen trial code."""
import argparse
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import re
import sys
import time

PLAN = json.loads(Path(__file__).with_name("plan.json").read_bytes())


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def source_trial(snapshot):
    trial = snapshot / "research" / "kim_multidnn_search_trial"
    frozen_bytes = (trial / "freeze.json").read_bytes()
    require(hashlib.sha256(frozen_bytes).hexdigest() == PLAN["freeze_sha256"], "freeze SHA256")
    manifest = json.loads(frozen_bytes)["files"]
    require(len(manifest) == PLAN["frozen_file_count"], "frozen file count")
    for name, digest in manifest.items():
        actual = hashlib.sha256((snapshot / name).read_bytes()).hexdigest()
        require(actual == digest, name)

    jobs = json.loads((trial / "design.json").read_bytes())["jobs"]
    original = next(j for j in jobs if j["id"] == PLAN["original_slot"])
    job = PLAN["retry_slot"]
    require(original == dict(job, id=PLAN["original_slot"]), "retry differs from original slot")
    budget = PLAN["reservation"]
    require(budget["original_s"] + job["cap"] == budget["total_s"] <= budget["overall_cap_s"],
            "reservation exceeds batch ceiling")
    environment = dict(host=platform.platform(), cpu=platform.processor(), python=sys.version,
                       numpy=version("numpy"), numba=version("numba"))
    require(environment == PLAN["environment"], "original runtime fingerprint mismatch")
    return trial


def launch(args, trial):
    pin = args.pin
    require(re.fullmatch(r"[0-9a-f]{40}", pin), "full retry preregistration SHA required")
    sys.path.insert(0, str(trial))
    import supervise

    require(Path(supervise.__file__).resolve().parent == trial, "unexpected supervisor module")
    job = PLAN["retry_slot"]
    raw = args.output.resolve() / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    supervise.RAW = raw
    with (raw / "launch.lock").open("x", encoding="ascii", newline="\n") as lock:
        lock.write(pin + "\n")
        lock.flush()
        os.fsync(lock.fileno())
    ledger = raw / "ledger.jsonl"
    supervise.append(ledger, dict(event="reserve", id=job["id"], cap_s=job["cap"],
                                 original_slot=PLAN["original_slot"],
                                 combined_reserved_s=PLAN["reservation"]["total_s"],
                                 retry_preregistration=pin, unix=time.time()))
    try:
        result = supervise.execute(job, PLAN["original_preregistration"], PLAN["freeze_sha256"])
        supervise.append(ledger, dict(event="close", id=job["id"], status=result["status"],
                                     actual_s=result["process_wall_s"]))
        reason = "TECHNICAL_OR_CORRECTNESS_FAULT" if result["status"] == "FAULT" else "SINGLE_ATTEMPT_SETTLED"
        supervise.write(raw / "stop.json", dict(reason=reason, id=job["id"], status=result["status"]))
    except BaseException as error:
        supervise.write(raw / "stop.json", dict(reason="SUPERVISOR_FAULT", id=job["id"],
                                                detail=repr(error)))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("output", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--pin")
    args = parser.parse_args()
    trial = source_trial(args.snapshot.resolve())
    if args.check:
        print(f"Frozen inputs and runtime verified: {PLAN['frozen_file_count']} files.", flush=True)
    else:
        launch(args, trial)


if __name__ == "__main__":
    main()
