"""Finish the registered serial batch and its offline audit across reconnections."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from time import sleep

from pending_cells import ActiveSupervisor, before_deadline
from recover_26300 import execute
from windows_26300 import STAGE, run_step


def finish(repo, run, out):
    formal = run / STAGE / "formal"
    closure = formal / "batch_end.json"
    while not closure.is_file():
        active = [p for p in (formal / "cells").iterdir()
                  if not (p / "receipt.json").exists() and before_deadline(p)]
        if active:
            sleep(25)
            continue
        try:
            run_step("one", repo, run)
        except ActiveSupervisor:
            sleep(10)
    while True:
        try:
            execute(repo, run)
            break
        except ActiveSupervisor:
            sleep(10)
    if not out.exists():
        auditor = Path(__file__).with_name("analyze_windows_builds.py")
        subprocess.run([sys.executable, "-B", "-u", str(auditor), "--repo", str(repo), "--run", str(run),
                        "--out", str(out)], check=True)
    audit = json.loads((out / "audit.json").read_bytes())
    print(f"Certified {audit['audited_CD']}/24 endpoints, {audit['complete_pairs']}/12 pairs", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("repo", "run", "out"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    finish(args.repo.resolve(), args.run.resolve(), args.out.resolve())
