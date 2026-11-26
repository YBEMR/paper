"""Run in a fresh output folder, check all deterministic terminal plan identities."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("new_directory",type=Path)
    args=cli.parse_args()
    root=Path(__file__).resolve().parent
    dest=args.new_directory.resolve()
    if dest==root or dest.is_relative_to(root):
        cli.error("use a new directory outside the archived experiment")
    dest.mkdir(parents=True,exist_ok=False)
    data=dest/"data"
    env=dict(os.environ,M1C_OUTPUT=str(data),PYTHONDONTWRITEBYTECODE="1")
    for cmd in (("history_check.py",),("run.py","search"),("guarded.py",),("run.py","ordinary"),
                ("extensions.py",),("pool_check.py",),("validate_run.py",)):
        subprocess.run([sys.executable,"-B","-u",str(root/cmd[0]),*cmd[1:]],env=env,check=True)
    def identities(path):
        return [(v["plan"],v["status"]) for v in json.loads(path.read_bytes())["certificates"]]
    for file in (root/"data/search").glob("*/*/result.json"):
        assert identities(file)==identities(data/file.relative_to(root/"data")),file
    print("All from-empty terminal plan identities and statuses match. Wall-clock cutoffs are machine-dependent.")

if __name__=="__main__":
    main()
