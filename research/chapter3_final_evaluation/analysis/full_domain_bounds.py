"""Recompute the G1 C1 analytic bound on each frozen, unrestricted P1 instance."""
import csv
import hashlib
import json
import sys
from decimal import Decimal
from math import floor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from setup_inputs import CASES, ROOT, checked_problem
from thermal_bound import PJ, proof, simple_bound


def main():
    lock = json.loads((ROOT / "inputs.json").read_bytes())
    records = []
    proofs = {}
    for case, n in CASES.items():
        frozen = lock["instances"][case]
        raw = (ROOT / "instances" / f"{case}.csv").read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != frozen["sha256"]:
            raise ValueError(f"Frozen instance changed: {case}")
        p = checked_problem(case)
        if (n != frozen["count"] or len(p.req) != n or p.n != 3*n or
                p.horizon != frozen["horizon_ticks"] or p.boundaries != frozen["boundaries"]):
            raise ValueError(f"Instance horizon or task count changed: {case}")
        certificate = proof(p)
        if not certificate["passed"] or any(len(opts) != 13 for opts in p.options[1::3]):
            raise ValueError(f"C1 applicability or main-stage domain failed: {case}")
        # simple_bound minimizes over every p.options entry, including both CPU
        # cores for pre/post. No incumbent, FIFO order or neighborhood is supplied.
        exact = simple_bound(p, "C1")
        lower_pj = floor(PJ * exact)
        records.append(dict(case=case, requests=n, horizon_ticks=p.horizon,
                            instance_sha256=digest, lower_pJ=lower_pj,
                            lower_J=format(Decimal(lower_pj) / Decimal(PJ), ".12f")))
        proofs[case] = dict(certificate, exact_lower_J=str(exact))
    with (HERE / "full_domain_bounds.csv").open("w", encoding="utf8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=records[0], lineterminator="\n")
        w.writeheader()
        w.writerows(records)
    (HERE / "bound_proofs.json").write_text(
        json.dumps(proofs, indent=2) + "\n", encoding="utf8", newline="\n")


if __name__ == "__main__":
    main()
