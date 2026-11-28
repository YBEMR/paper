"""Restore a selected plan, certificate and full 31-column trace from a lane."""
import argparse
import hashlib
import io
import json
import tarfile
import zlib
from pathlib import Path
import numpy as np

def sha(data):return hashlib.sha256(data).hexdigest()

def members(physical,key):
    index=json.loads((physical/"index.json").read_bytes())
    row=index["plans"][key]
    needed={row["archive"]:{key+"/plan",key+"/certificate"}}
    for block in row["blocks"]:
        needed.setdefault(index["blocks"][block],set()).add("blocks/"+block)
    parts={}
    for name,keys in needed.items():
        with tarfile.open(physical/name) as archive:
            for name in keys:
                parts[name]=zlib.decompress(archive.extractfile(name).read())
    plan,cert=parts[key+"/plan"],parts[key+"/certificate"]
    trace=b"".join(parts["blocks/"+b] for b in row["blocks"])
    assert sha(plan.strip())==key and sha(plan)==row["plan_sha"]
    assert sha(cert)==row["cert_sha"] and sha(trace)==row["trace_sha"]
    stream=io.BytesIO()
    np.savez_compressed(stream,events=np.frombuffer(trace,dtype=np.float64).reshape(row["shape"]))
    return {"plan.json":plan,"certificate.json":cert,"trace.npz":stream.getvalue()}

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("physical",type=Path)
    parser.add_argument("plan_sha256")
    parser.add_argument("destination",type=Path)
    args=parser.parse_args()
    files=members(args.physical,args.plan_sha256)
    args.destination.mkdir(parents=True,exist_ok=False)
    for name,data in files.items():(args.destination/name).write_bytes(data)
