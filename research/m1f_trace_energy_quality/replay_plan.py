"""Rebuild a published physical certificate and verify its event array."""
import argparse
import base64
import gzip
import hashlib
import json
import os
import sys
from pathlib import Path

from long_run import BASE, ROOT, inputs


def archived_record(archive, case, plan):
    with gzip.open(archive, "rt", encoding="utf8") as records:
        for line in records:
            record = json.loads(line)
            if record["case"] == case and record["plan"] == plan:
                return record
    raise ValueError(f"Unknown plan {plan} for {case} in {archive.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=[src.stem for _, src in inputs()])
    parser.add_argument("plan_sha256")
    parser.add_argument("destination", type=Path)
    parser.add_argument("--offline", action="store_true", help="use the diagnostic intervention archive")
    args = parser.parse_args()

    archive = (ROOT / "data/trace/intervention_certificates.jsonl.gz" if args.offline
               else ROOT / "data/quality" / f"{args.case}_certificates.jsonl.gz")
    record = archived_record(archive, args.case, args.plan_sha256)
    destination = args.destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    os.environ["M1E_OUTPUT"] = str(destination)
    sys.path.insert(0, str(BASE))
    import experiment as experiment

    size, order = args.case.split("_")
    label = "L" + size[1:]
    case = experiment.reordered(experiment.case_for(label), label, order)
    certificate, events = case.certify(base64.b64decode(record["config_b64"]))
    if certificate["plan_sha256"] != args.plan_sha256:
        raise ValueError("Replayed plan SHA-256 differs from the archived identity")
    exclude_clock = lambda cert: {key: value for key, value in cert.items() if key != "cert_s"}
    canonical = lambda cert: json.loads(experiment.p1.raw(exclude_clock(cert)))
    if canonical(certificate) != canonical(record["physical_certificate"]):
        raise ValueError("Replayed physical certificate differs from the archived certificate")
    array = experiment.np.asarray(events)
    if list(array.shape) != record["shape"] or hashlib.sha256(array.tobytes()).hexdigest() != record["event_array_sha256"]:
        raise ValueError("Replayed event array differs from the archived array")
    metrics = certificate["metrics"]
    print("status", metrics["status"], "energy_J", metrics["E_J"], "exact_event_array", True)


if __name__ == "__main__":
    main()
