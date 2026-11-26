"""Export the original event arrays by unique one-second blocks, with no numerical encoding changes."""
import argparse
import csv
import gzip
import hashlib
import io
import json
import sqlite3
import zipfile
import zlib
from pathlib import Path
import numpy as np
from design import ROOT,sha,write_json

def export(case,destination):
    destination.mkdir(parents=True,exist_ok=True)
    out=destination/(case+".zip")
    sql=ROOT/"work/events"/(case+".sqlite")
    index=ROOT/"data/evidence"/case/"event_index.csv.gz"
    rows=list(csv.DictReader(gzip.open(index,"rt")))
    keys={k for r in rows for k in r["segments"].split()}
    with sqlite3.connect("file:"+str(sql.resolve())+"?mode=ro",uri=True) as db,zipfile.ZipFile(out,"w",allowZip64=True) as z:
        n=0
        for raw_key,compressed in db.execute("SELECT id,payload FROM chunks ORDER BY id"):
            assert hashlib.sha256(zlib.decompress(compressed)).digest()==raw_key
            z.writestr(raw_key.hex(),compressed)
            n+=1
        assert n==len(keys)
    with zipfile.ZipFile(out) as z:
        assert set(z.namelist())==keys
        # Every unique plan is checked; the deterministic NPZ writer is spot-checked per case.
        for i,row in enumerate(rows):
            digest=hashlib.sha256()
            if i==0:parts=[]
            for key in row["segments"].split():
                segment=zlib.decompress(z.read(key))
                digest.update(segment)
                if i==0:parts.append(segment)
            assert digest.hexdigest()==row["event_array_sha256"]
            if i==0:
                arr=np.frombuffer(b"".join(parts),dtype=np.float64).reshape(-1,31)
                f=io.BytesIO();np.savez_compressed(f,events=arr)
                assert sha(f.getvalue())==row["npz_file_sha256"]
    with out.open("rb") as f:digest=hashlib.file_digest(f,"sha256").hexdigest()
    write_json(ROOT/"data/evidence"/case/"event_volume.json",dict(filename=out.name,bytes=out.stat().st_size,
                sha256=digest,verified_unique_plans=len(rows),distinct_event_blocks=len(keys)))
    print("EVENT_VOLUME",case,out.stat().st_size,len(keys),flush=True)
def restore(case, directory, plan, output):
    index=ROOT/"data/evidence"/case/"event_index.csv.gz"
    with gzip.open(index,"rt") as f:
        row=next(r for r in csv.DictReader(f) if r["plan"]==plan)
    with zipfile.ZipFile(directory/(case+".zip")) as z:
        parts=[]
        for key in row["segments"].split():
            payload=zlib.decompress(z.read(key))
            assert sha(payload)==key
            parts.append(payload)
    body=b"".join(parts)
    assert sha(body)==row["event_array_sha256"]
    arr=np.frombuffer(body,dtype=np.float64).reshape(-1,31)
    f=io.BytesIO();np.savez_compressed(f,events=arr)
    compressed=f.getvalue()
    assert sha(compressed)==row["npz_file_sha256"],"use the registered NumPy/zlib environment for identical NPZ bytes"
    with output.open("xb") as target:target.write(compressed)
    print("restored verified original NPZ",output)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("case");p.add_argument("destination",type=Path)
    p.add_argument("--restore",metavar="PLAN");p.add_argument("--out",type=Path)
    a=p.parse_args()
    if a.restore:
        if not a.out:p.error("--restore requires --out")
        restore(a.case,a.destination,a.restore,a.out)
    else:export(a.case,a.destination)
