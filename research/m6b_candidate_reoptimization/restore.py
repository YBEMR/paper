"""Restore one SHA-identified full physical schedule and its 31-column trace without simulation."""
import argparse
import hashlib
import json
import tarfile
import zlib
from collections import defaultdict
from pathlib import Path
import numpy as np
def restore(physical,plan,dest):
    with (physical/"index.json").open() as f:index=json.load(f)
    d=index["plans"][plan];wanted=defaultdict(set)
    for k in d["blocks"]:wanted[index["blocks"][k]].add("blocks/"+k)
    wanted[d["archive"]].update((plan+"/plan.z",plan+"/cert.z"))
    found={}
    for name,keys in wanted.items():
        with tarfile.open(physical/name,"r:") as tar:
            for key in keys:
                b=zlib.decompress(tar.extractfile(key).read())
                if key.startswith("blocks/"):assert hashlib.sha256(b).hexdigest()==key[7:]
                found[key]=b
    bodies=[found[plan+"/plan.z"],found[plan+"/cert.z"]]
    data=b"".join(found["blocks/"+key] for key in d["blocks"])
    for b,k in zip([*bodies,data],("plan_file_sha256","certificate_file_sha256","trace_sha256")):
        assert hashlib.sha256(b).hexdigest()==d[k]
    ar=np.frombuffer(data,dtype=np.float64).reshape(d["shape"]);assert ar.shape[1]==31
    dest.mkdir(parents=True,exist_ok=False)
    (dest/"plan.json").write_bytes(bodies[0]);(dest/"certificate.json").write_bytes(bodies[1])
    np.savez_compressed(dest/"trace.npz",events=ar)
    print(plan,dest,ar.shape)
if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan");parser.add_argument("destination",type=Path)
    parser.add_argument("--physical",type=Path,default=Path(__file__).resolve().parent/"archive/physical")
    args=parser.parse_args();restore(args.physical,args.plan,args.destination)
