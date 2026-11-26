"""Publish bit-preserving plan/certificate members, per-run records and event block indices."""
import argparse
import csv
import gzip
import hashlib
import io
import json
import lzma
import sqlite3
import tarfile
import zlib
from pathlib import Path
from design import ROOT,REG,sha,write_json

DATA=ROOT/"data"
WORK=ROOT/"work"

def member(tar,name,body):
    info=tarfile.TarInfo(name);info.size=len(body);info.mode=0o644
    tar.addfile(info,io.BytesIO(body))

def reader(path):
    return sqlite3.connect("file:"+str(path.resolve())+"?mode=ro",uri=True)

def export(case):
    dst=DATA/"evidence"/case
    dst.mkdir(parents=True,exist_ok=True)
    logs=sorted((DATA/"runs"/case).glob("*/run.json.gz"))
    assert len(logs)==12
    calls=0;referenced=set();originals=set()
    with lzma.open(dst/"runs.tar.xz","wb",preset=2) as f,tarfile.open(fileobj=f,mode="w|") as tar:
        for p in logs:
            body=gzip.decompress(p.read_bytes());run=json.loads(body);rr=run["records"]
            calls+=len(rr);referenced.update(r["cert"]["plan_sha256"] for r in rr)
            member(tar,p.parent.name+"/run.json",body)
    dbpath=WORK/"physical"/(case+".sqlite")
    with reader(dbpath) as db,lzma.open(dst/"physical.tar.xz","wb",preset=2) as f,tarfile.open(fileobj=f,mode="w|") as tar:
        with gzip.open(dst/"event_index.csv.gz","wt",newline="") as index:
            w=csv.writer(index,lineterminator="\n")
            w.writerow(["plan","plan_file_sha256","certificate_file_sha256","event_array_sha256","npz_file_sha256","segments"])
            for key,body,cert,event_hash,npz_hash,segs in db.execute("SELECT * FROM plans ORDER BY id"):
                b=zlib.decompress(body);c=zlib.decompress(cert)
                assert sha(b.strip())==key and json.loads(c)["plan_sha256"]==key
                originals.add(key)
                member(tar,key+"/plan.json",b);member(tar,key+"/certificate.json",c)
                w.writerow([key,sha(b),sha(c),event_hash,npz_hash," ".join(json.loads(segs))])
    assert originals==referenced
    # Verify the two lossless archives are readable and complete before publishing the receipt.
    for name,n in (("runs",12),("physical",2*len(originals))):
        with tarfile.open(dst/(name+".tar.xz"),"r|xz") as tar:
            assert sum(1 for _ in tar)==n
    write_json(dst/"receipt.json",dict(case=case,runs=12,certificates=calls,unique_plans=len(originals),
               files={p.name:sha(p.read_bytes()) for p in sorted(dst.iterdir()) if p.name!="receipt.json"}))
    print("EXPORTED",case,calls,len(originals),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("case");export(p.parse_args().case)
