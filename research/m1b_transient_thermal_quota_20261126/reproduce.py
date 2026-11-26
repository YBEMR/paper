"""Reproduce into a new directory alongside a verified copy of the M1 base."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination",type=Path)
    args=parser.parse_args()
    src=Path(__file__).resolve().parent
    baseline=next(p for p in (src.parent/"m1_transient_thermal_quota_20261126",src.parent/"M1_quota_20261126") if (p/"SHA256SUMS").exists())
    dest=args.destination.resolve()
    if dest.is_relative_to(src) or dest.is_relative_to(baseline):
        parser.error("choose a new independent directory")
    dest.mkdir(parents=True,exist_ok=False)
    old=dest/baseline.name
    files=[s.split("  ",1)[1] for s in (baseline/"SHA256SUMS").read_text(encoding="utf-8").splitlines()]
    for name in [*files,"SHA256SUMS"]:
        target=old/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(baseline/name,target)
    work=dest/src.name
    selected=[*src.glob("*.py"),*src.glob("*.md"),*src.glob("versions/*/*.py"),*src.glob("data/*lock.json")]
    for path in selected:
        target=work/path.relative_to(src)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,target)
    for name in ("diagnose","check_diagnostic","search_b","recovered","check_recovered","attribution","polish","screened","audit","figure"):
        subprocess.run([sys.executable,"-B","-u",str(work/(name+".py"))],cwd=work,check=True)
    for path in (src/"data/search").glob("*/*/result.json"):
        def plans(p):
            return [(v["plan"],v["status"]) for v in json.loads(p.read_text())["certificates"]]
        assert plans(path)==plans(work/path.relative_to(src)),path
    print("Reproduced the terminal plan identities and statuses of all search arms.")


if __name__=="__main__":
    main()
