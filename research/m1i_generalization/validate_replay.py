"""Independently replay one predetermined issued certificate per registered condition."""
import argparse
import csv
import gzip
import json
import os
import tarfile
import zipfile
import zlib
from pathlib import Path
from design import ROOT,REG,METHODS,sha,write_json

def main(volumes):
    out=ROOT/"work"/"final_replay"
    os.environ["M1G_RAW"]=str(out/"warm")
    from adapter import flow,e,np
    records=[]
    for item in json.loads((REG/"cases.json").read_bytes())["cases"]:
        case=item["case"];d=ROOT/"data/evidence"/case;target=METHODS[item["index"]%4]
        with tarfile.open(d/"runs.tar.xz") as t:
            run=json.load(t.extractfile("r1-"+target+"/run.json"))
        if not run["records"]:
            records.append(dict(case=case,method=target,result="NO_ISSUED_CERTIFICATE"));continue
        cert=run["records"][0]["cert"];pid=cert["plan_sha256"]
        with tarfile.open(d/"physical.tar.xz") as t:
            body=t.extractfile(pid+"/plan.json").read()
        assert sha(body.strip())==pid
        with gzip.open(d/"event_index.csv.gz","rt") as f:idx=next(r for r in csv.DictReader(f) if r["plan"]==pid)
        c=flow(item,out)
        cfg=bytes(k+10*(u==3) for u,k,_ in json.loads(body)["rows"][1::3])
        rebuilt,arr=c.certify(cfg)
        norm=lambda v:e.p1.raw({k:x for k,x in v.items() if k!="cert_s"})
        assert norm(cert)==norm(rebuilt)
        file=out/"evidence"/case/pid/"trace.npz"
        assert sha(file.read_bytes())==idx["npz_file_sha256"]
        with zipfile.ZipFile(volumes/(case+".zip")) as z:
            assert arr.tobytes()==b"".join(zlib.decompress(z.read(k)) for k in idx["segments"].split())
        records.append(dict(case=case,method=target,rep=1,call=1,plan=pid,status=cert["metrics"]["status"],
                            E_J=cert["metrics"]["E_J"],npz_sha256=idx["npz_file_sha256"],result="BITWISE_MATCH"))
    write_json(ROOT/"data"/"replay_receipt.json",records)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("volumes",type=Path);main(p.parse_args().volumes)
