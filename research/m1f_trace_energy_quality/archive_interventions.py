"""Archive and cross-check physical certificates for all timing-feasible offline controls."""
import argparse
import base64
import csv
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
from long_run import ROOT

TRACE = ROOT / "data/trace"


def expected_plans():
    plans = set()
    for filename in ("one_window_intervention.csv", "prefix_suffix.csv", "mapping_frequency.csv"):
        with (TRACE / filename).open() as source:
            for row in csv.DictReader(source):
                if row["plan"]:
                    plans.add((row["case"], row["plan"]))
    return plans


def collect(roots):
    records = {}
    for root in roots:
        for file in sorted(root.glob("evidence/*/*/certificate.json")):
            certificate = json.loads(file.read_bytes())
            case, plan = file.parts[-3:-1]
            body = file.with_name("plan.json").read_bytes().strip()
            assert hashlib.sha256(body).hexdigest() == plan == certificate["plan_sha256"]
            physical_plan = json.loads(body)
            assert physical_plan["case"] == case
            config = bytes(k + (10 if device == 3 else 0) for device, k, _ in physical_plan["rows"][1::3])
            with np.load(file.with_name("trace.npz"), allow_pickle=False) as trace:
                array = trace["events"]
            row = dict(case=case, plan=plan, config_b64=base64.b64encode(config).decode(),
                       physical_certificate=certificate, shape=list(array.shape),
                       event_array_sha256=hashlib.sha256(array.tobytes()).hexdigest())
            if (case, plan) in records:
                assert records[case, plan]["event_array_sha256"] == row["event_array_sha256"]
            else:
                records[case, plan] = row
    assert set(records) == expected_plans()
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", type=Path, default=ROOT / "diagnostic_raw/offline")
    parser.add_argument("--factors", type=Path, default=ROOT / "diagnostic_raw/factor_checks")
    args = parser.parse_args()
    records = collect((args.prefix, args.factors))
    with gzip.open(TRACE / "intervention_certificates.jsonl.gz", "wt", encoding="utf8") as out:
        for key in sorted(records):
            out.write(json.dumps(records[key], separators=(",", ":")) + "\n")
    print("Certified offline plans", len(records))


if __name__ == "__main__":
    main()
