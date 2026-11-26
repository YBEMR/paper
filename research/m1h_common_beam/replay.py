"""Rebuild one P1 event file and compare it with the SHA-256 of the original .npz."""
import argparse
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("case");parser.add_argument("plan");parser.add_argument("output",type=Path)
    args=parser.parse_args()
    dest=args.output.resolve();dest.mkdir(parents=True,exist_ok=False)
    os.environ["M1G_RAW"]=str(dest)
    from framework import case_for,e,inputs,np
    case=case_for(next(p for _,p in inputs() if p.stem==args.case))
    evidence=ROOT/"data/evidence"/args.case
    with tarfile.open(evidence/"plans-and-certificates.tar.xz","r:xz") as src:
        body=src.extractfile(args.plan+"/plan.json").read()
        original=json.loads(src.extractfile(args.plan+"/certificate.json").read())
    assert hashlib.sha256(body.strip()).hexdigest()==args.plan
    cfg=bytes(k+10*(u==3) for u,k,_ in json.loads(body)["rows"][1::3])
    case.eng.out=dest
    new,ar=case.certify(cfg)
    assert new["plan_sha256"]==args.plan
    assert e.p1.raw({k:v for k,v in new.items() if k!="cert_s"})==e.p1.raw({k:v for k,v in original.items() if k!="cert_s"})
    with gzip.open(evidence/"traces.csv.gz","rt") as f:
        row=next(r for r in csv.DictReader(f) if r["plan"]==args.plan)
    assert hashlib.sha256(np.asarray(ar).tobytes()).hexdigest()==row["event_array_sha256"]
    npz=dest/"evidence"/args.case/args.plan/"trace.npz"
    exact=hashlib.sha256(npz.read_bytes()).hexdigest()==row["npz_file_sha256"]
    print(new["metrics"]["status"],new["metrics"]["E_J"],"event array matched; original NPZ byte match",exact)
    if not exact:
        raise ValueError("Compressed file differs; check the recorded environment")

if __name__=="__main__":
    main()
