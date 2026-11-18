"""Run correctness tests only; emit auditable gate for the frozen value run."""
import hashlib
import json
import platform
import sys
from pathlib import Path
import numpy
import scipy
import physics_checks
import solver_checks
import workload_checks

ROOT = Path(__file__).resolve().parent
FROZEN = ["verify.py","run_v1.py","workload.py","physics.py","solvers.py","inputs.json",
          "physics_checks.py","solver_checks.py","workload_checks.py","protocol.md",
          "input_protocol.md","../chapter3_experiments/config_v01.json"]


def verify(out):
    evidence = dict(workload=workload_checks.checks(), physics=physics_checks.checks(),
                    solver=solver_checks.run(), passed=True, python=sys.version,
                    platform=platform.platform(), numpy=numpy.__version__, scipy=scipy.__version__,
                    sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FROZEN})
    out.write_text(json.dumps(evidence,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")


if __name__ == "__main__":
    verify(Path(sys.argv[1]))

