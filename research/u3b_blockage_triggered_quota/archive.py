"""Losslessly address shared ledgers and unique physical executions after independent runs."""
import gzip
import hashlib
import json
import os
import shutil
from pathlib import Path

HERE=Path(__file__).resolve().parent
OUT=HERE/"results"
RUNS=Path(os.environ["U3B_RUNS"])
def read(p):
    return json.loads(p.read_bytes())
def raw(v):
    return json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def sha(b):
    return hashlib.sha256(b).hexdigest()
def write(p,data):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_bytes(raw(data)+b"\n")
def block(name,body):
    den=OUT/"pools"
    den.mkdir(parents=True,exist_ok=True)
    path=den/(name+"-"+sha(body)+".json.gz")
    if not path.exists():
        path.write_bytes(gzip.compress(body,compresslevel=6,mtime=0))
    return path.relative_to(HERE).as_posix()

def main():
    for receipt in sorted(RUNS.glob("*/receipt.json")):
        folder=receipt.parent
        rec=read(receipt)
        unit=dict(receipt=rec,parts={},evidence=[])
        for f in sorted(folder.glob("*.json*")):
            if f.name=="receipt.json":
                continue
            if f.name=="base.json":
                b=read(f)
                unit["base_s"]=b.pop("t")
                unit["parts"]["base"]=block("base",raw(b))
            elif f.name.endswith("-pool.json"):
                unit["parts"][f.stem]=block("rank",raw(read(f)))
            elif f.name.endswith(".gz"):
                unit["parts"][f.name[:-8]]=block("ledger",gzip.decompress(f.read_bytes()))
            else:
                unit[f.stem]=read(f)
        for cert in folder.glob("evidence/*/*/certificate.json"):
            physical=cert.parent
            dst=OUT/"physical"/rec["case"]/physical.name
            dst.mkdir(parents=True,exist_ok=True)
            if (dst/"certificate.json").exists():
                for fn in ("trace.npz","plan.json"):
                    assert sha((physical/fn).read_bytes())==sha((dst/fn).read_bytes())
                a,b=read(cert),read(dst/"certificate.json")
                assert {k:v for k,v in a.items() if k!="cert_s"}=={k:v for k,v in b.items() if k!="cert_s"}
            else:
                for fn in ("certificate.json","plan.json","trace.npz"):
                    shutil.copyfile(physical/fn,dst/fn)
            unit["evidence"].append(physical.name)
        unit["evidence"].sort()
        write(OUT/"runs"/(folder.name+".json"),unit)
if __name__=="__main__":
    main()
