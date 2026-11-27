"""Read M3-a and U2 historical evidence. Preserve canonical physical plan identity."""
import base64
import gzip
import hashlib
import json
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
def raw(obj):
    return json.dumps(obj, separators=(",", ":"), sort_keys=True).encode()

def store(code, record):
    dest = ROOT / "history" / code
    dest.mkdir(exist_ok=True, parents=True)
    assert hashlib.sha256(raw(record["plan"])).hexdigest() == record["certificate"]["plan_sha256"]
    for name in ("plan", "certificate"):
        (dest / (name+".json")).write_bytes(raw(record[name])+b"\n")

def main(audit, u2):
    data = json.loads(gzip.decompress(audit))
    row = min((r for r in data["physical"].values() if r.get("certificate",{}).get("metrics",{}).get("status")=="SAFE"),
              key=lambda r:r["certificate"]["metrics"]["E_J"])
    store("A02",row)
    key = "591f349f4c8c313c414e1e7037e5d90f1ceff767e4f44b3512310c903367d0c6"
    record={}
    with tarfile.open(u2, "r|gz") as tar:
        for member in tar:
            parts=member.name.split("/")
            if len(parts)>2 and parts[-2]==key and parts[-1] in {"plan.json","certificate.json"}:
                record[parts[-1].split(".")[0]]=json.load(tar.extractfile(member))
                if len(record)==2: break
    store("C10",record)

if __name__=="__main__":
    main(Path(sys.argv[1]).read_bytes(), sys.argv[2])
