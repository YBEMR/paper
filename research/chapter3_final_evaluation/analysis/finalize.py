"""After the last receipt is sealed, audit the submitted endpoints and build the paper materials."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
OUT=ROOT/"formal"


def main(wait):
    while not (OUT/"batch_end.json").is_file():
        if not wait:
            raise RuntimeError("Formal jobs are still active")
        time.sleep(30)
    closure=json.loads((OUT/"batch_end.json").read_bytes())
    if closure["outcome"]!="FINISHED":
        raise RuntimeError("Batch interrupted; inspect original receipts")
    # Import heavy numerical and rendering libraries only after workers exit.
    import audit_results as audit
    import archive_batch
    import figures
    import historical_exchange
    import thermal_and_mechanism as tm
    import write_report
    audit.collect()
    tm.thermal()
    tm.paired_mechanism()
    historical_exchange.main()
    figures.main()
    archive_batch.main()
    write_report.main()
    figures_out=audit.RESULTS/"figures"
    for i in range(1,10):
        for ext in ("csv","svg","png"):
            if not any(p.stat().st_size for p in figures_out.glob(f"{i:02}_*.{ext}")):
                raise RuntimeError(f"Figure {i} missing {ext}")
    artifacts={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
        for d in (audit.RESULTS,ROOT/"archive") for p in sorted(d.rglob("*")) if p.is_file()}
    result=dict(subject=json.loads((ROOT/"publication_freeze.json").read_bytes())["remote_protocol_commit"],
                physical_cells=165,physical_attempts=closure.get("physical_attempts_including_interrupted",165),
                logical_positions=174,figures=9,artifacts=artifacts)
    (ROOT/"acceptance.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf8",newline="\n")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--wait",action="store_true")
    args=parser.parse_args()
    try:
        main(args.wait)
    except BaseException:
        traceback.print_exc()
        raise
