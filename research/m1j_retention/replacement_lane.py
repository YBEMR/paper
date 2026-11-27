"""Execute and preserve one immutable M1-j lane on its dedicated Linux runner."""
import json
import os
import platform
import sys
from pathlib import Path

from batch_j import DATA, THREADS, WORK, inputs, lane, verify, write_json


def main():
    index = int(sys.argv[1])
    if index not in range(6):
        raise ValueError(index)
    verify()
    (WORK / "events").mkdir(parents=True, exist_ok=True)
    core = max(os.sched_getaffinity(0))
    cpu = Path("/proc/cpuinfo").read_text().split("model name", 1)[-1].splitlines()[0].lstrip(" :\t")
    write_json(DATA / "environment" / f"host{index}.json",
               dict(lane=index, cpu=cpu, core=core, platform=platform.platform(),
                    run_id=os.environ.get("GITHUB_RUN_ID"), job=os.environ.get("GITHUB_JOB"),
                    image=os.environ.get("ImageVersion"), run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT"),
                    python=sys.version, initial_affinity=sorted(os.sched_getaffinity(0))))
    for key in THREADS:
        os.environ[key] = "1"
    lane(index, core)
    # Reuse the lossless frozen exporters with only their input/output roots rebound.
    import export_evidence
    import event_files
    export_evidence.DATA, export_evidence.WORK = DATA, WORK
    event_files.ROOT = DATA.parent
    for row in inputs():
        if row["index"] % 6 == index:
            case = row["case"]
            export_evidence.export(case)
            event_files.export(case, WORK / "volumes")


if __name__ == "__main__":
    main()
