"""Reconstruct a published plan and verify all certificate fields and original NPZ bytes."""
import argparse
import csv
import gzip
import io
import json
import os
import tarfile
import zipfile
import zlib
from pathlib import Path
from design import ROOT,REG,sha

def main():
    p=argparse.ArgumentParser()
    p.add_argument("case");p.add_argument("plan");p.add_argument("output",type=Path)
    p.add_argument("--events",type=Path,help="optional original event-block ZIP for this case")
    args=p.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    os.environ["M1G_RAW"]=str(out/"warm")
    from adapter import flow,e,np
    c=flow(next(r for r in json.loads((REG/"cases.json").read_bytes())["cases"] if r["case"]==args.case),out)
    d=ROOT/"data/evidence"/c.label
    with gzip.open(d/"event_index.csv.gz","rt") as f:
        idx=next(r for r in csv.DictReader(f) if r["plan"]==args.plan)
    with tarfile.open(d/"physical.tar.xz") as tar:
        body=tar.extractfile(args.plan+"/plan.json").read();cert_bytes=tar.extractfile(args.plan+"/certificate.json").read()
    assert sha(body)==idx["plan_file_sha256"] and sha(cert_bytes)==idx["certificate_file_sha256"]
    cfg=bytes(k+10*(u==3) for u,k,_ in json.loads(body)["rows"][1::3])
    cert,arr=c.certify(cfg)
    normalize=lambda v:e.p1.raw({k:x for k,x in v.items() if k!="cert_s"})
    assert normalize(cert)==normalize(json.loads(cert_bytes))
    npz=out/"evidence"/c.label/args.plan/"trace.npz"
    assert sha(npz.read_bytes())==idx["npz_file_sha256"] and sha(arr.tobytes())==idx["event_array_sha256"]
    if args.events:
        with zipfile.ZipFile(args.events) as z:
            source=b"".join(zlib.decompress(z.read(k)) for k in idx["segments"].split())
        assert source==arr.tobytes()
    print(c.label,cert["metrics"]["status"],cert["metrics"]["E_J"],"complete certificate and event bytes matched")
if __name__=="__main__":main()
