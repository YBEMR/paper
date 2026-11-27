"""Preserve partially written evidence at a hard stop, separate from certificate inventory."""
import gzip
import hashlib
import json
import os
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=Path(os.environ["U4_RUNS"])
def main():
    for f in (HERE/"results").glob("*/runs/*.json"):
        run=json.loads(f.read_bytes())
        for part in run["partial"]:
            folder=ROOT/(run["receipt"]["case"]+"-"+run["receipt"]["method"])
            candidates=[p.parent for p in folder.rglob("plan.json") if p.parent.name==part["plan"]]
            assert len(candidates)==1
            dest=f.parent.parent/"cutoff_fragments"/(f.stem+"-"+part["plan"])
            dest.mkdir(parents=True,exist_ok=True)
            for k,h in part["files"].items():
                body=(candidates[0]/k).read_bytes()
                assert hashlib.sha256(body).hexdigest()==h
                (dest/(k+".fragment.gz")).write_bytes(gzip.compress(body,mtime=0))
if __name__=="__main__":main()
