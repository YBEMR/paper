"""Run the conditional paired extension, then the four frozen light-case comparisons."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
if __name__=="__main__":
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    for record in json.loads((ROOT/"data/protocol_lock.json").read_text(encoding="utf-8-sig")):
        path = ROOT/record["file"]
        if path.name=="search.py":
            path = ROOT/"versions/v1/search.py"
        assert hashlib.sha256(path.read_bytes()).hexdigest()==record["Hash"].lower()
    for script,arguments in [
        ("search.py",["--improved","--out","data/e1b","--cases","L640","L800"]),
        ("versions/v1/search.py",["--cases","L320","L480"]),
        ("search.py",["--improved","--out","data/e1b","--cases","L320","L480"]),
    ]:
        subprocess.run([sys.executable,"-B","-u",str(ROOT/script),*arguments],cwd=ROOT,env=env,check=True)
