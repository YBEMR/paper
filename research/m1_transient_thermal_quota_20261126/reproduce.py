"""Reproduce in a NEW directory, leaving the delivered certificates intact."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination",type=Path,help="New output directory (must not exist)")
    args=parser.parse_args()
    src=Path(__file__).resolve().parent
    dest=args.destination.resolve()
    if dest.is_relative_to(src):
        parser.error("choose a new directory outside the delivered experiment")
    dest.mkdir(parents=True,exist_ok=False)
    work=dest/src.name
    work.mkdir()
    for name in ("ch4_original_experiments.zip","ch4_thermal_evidence.zip"):
        shutil.copyfile(src.parent/name,dest/name)
    for name in ("prepare.py","ledger.py","mechanism.py","e0.py","search.py","finish_batch.py",
                 "audit_results.py","evidence_figure.py","versions/v1/search.py","诊断任务书.md","改进轮任务书.md",
                 "data/protocol_lock.json","data/revision_lock.json"):
        (work/name).parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(src/name,work/name)
    env=dict(os.environ,PYTHONPATH=str(work))
    for cmd in (["prepare.py"],["e0.py"],["versions/v1/search.py","--cases","L640","L800"],
                ["finish_batch.py"],["audit_results.py"],["evidence_figure.py"]):
        subprocess.run([sys.executable,"-B","-u",*cmd],cwd=work,env=env,check=True)
    for origin in src.glob("data/e1*/*/*/result.json"):
        rel=origin.relative_to(src)
        records=[json.loads(p.read_text())["certificates"] for p in (origin,work/rel)]
        signature=lambda rr:[(v["rank"],v["plan"],v["status"]) for v in rr]
        assert signature(records[0])==signature(records[1]),rel
    print("All terminal plan identities, ranks and statuses matched.")


if __name__=="__main__":
    main()
