"""Restore a complete P1 plan, rigorous certificate and physical event array by hash."""
import argparse
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("case")
    parser.add_argument("plan")
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    dest=args.output.resolve()
    dest.mkdir(parents=True,exist_ok=False)
    os.environ["M1G_RAW"]=str(dest)
    from experiment import ROOT,e,inputs,case_for,Calendar,certify_native,np
    src=next(src for _,src in inputs() if src.stem==args.case)
    case=case_for(src)
    with gzip.open(ROOT/"data/certificates"/(args.case+".jsonl.gz"),"rt") as f:
        record=next(r for line in f if (r:=json.loads(line))["plan"]==args.plan)
    if "payload" in record:
        book=Calendar(case.p)
        for i,row in enumerate(record["payload"]["rows"]):
            book.add(i,*row)
        cert=certify_native(case,book,dest)
        folder=dest/"evidence"
    else:
        case.eng.out=dest
        cert,_=case.certify(base64.b64decode(record["config_b64"]))
        folder=dest/"evidence"
    orig=record["certificate"]
    assert cert["plan_sha256"]==record["plan"] and e.p1.raw(cert["metrics"])==e.p1.raw(orig["metrics"])
    with np.load(folder/args.case/args.plan/"trace.npz") as z:
        arr=z["events"]
        assert list(arr.shape)==record["shape"] and hashlib.sha256(arr.tobytes()).hexdigest()==record["event_array_sha256"]
    print(cert["metrics"]["status"],cert["metrics"]["E_J"],"event SHA-256 verified")


if __name__=="__main__":
    main()
