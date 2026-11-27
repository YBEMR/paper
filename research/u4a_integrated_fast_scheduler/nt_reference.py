"""Read the already completed NT60 development references without invoking a solver."""
import csv
import gzip
import hashlib
import io
import json
import os
import tarfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
def main():
    refs=[]
    for folder in sorted((Path(os.environ["U3A_INPUTS"])/"u2/research/u2_adaptive_groups/results").glob("[ABC][0-9][0-9]")):
        info=json.loads((folder/"archive.json").read_bytes())
        parts=[]
        for p in info["parts"]:
            b=(folder/p["name"]).read_bytes()
            assert len(b)==p["bytes"] and hashlib.sha256(b).hexdigest()==p["sha256"]
            parts.append(b)
        blob=b"".join(parts)
        assert hashlib.sha256(blob).hexdigest()==info["sha256"]
        with tarfile.open(fileobj=io.BytesIO(gzip.decompress(blob)),mode="r:") as tar:
            code=folder.name
            calls=[json.loads(s) for s in tar.extractfile(f"{code}/r1/NT/certs.jsonl").read().splitlines() if s.endswith(b"}")]
            eligible=[r for r in calls if r["status"]=="SAFE" and r["t"]<=60]
            best=None
            for r in eligible:
                if best is None or r["bounds"][1]<best["bounds"][0]:best=r
            ref=dict(case=code,archive_sha256=info["sha256"],origin="U2 r1 NT",first=eligible[0] if eligible else None,best=best)
            if best:
                key=best["plan"]
                f=next(n for n in tar.getnames() if n.startswith(f"{code}/r1/NT/search/physical/evidence/") and n.endswith(f"/{key}/certificate.json"))
                cert=json.load(tar.extractfile(f));plan=tar.extractfile(f.replace("certificate.json","plan.json")).read()
                assert cert["plan_sha256"]==hashlib.sha256(plan.strip()).hexdigest()==key
                assert cert["metrics"]["E_J"]==best["J"] and cert["metrics"]["status"]=="SAFE"
                ref["certificate_member"]=f
            refs.append(ref)
    assert len(refs)==12
    (HERE/"registration/nt60_previous.json").write_bytes((json.dumps(refs,sort_keys=True,indent=2)+"\n").encode())
if __name__=="__main__":main()
