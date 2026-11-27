"""Offline verification of hashes, identities, time receipts and all physical traces."""
import csv
import hashlib
import json
import tarfile
import zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_bytes())
def manifest(p):
    for line in p.read_text().splitlines():
        expected,name=line.split("  ",1);assert sha((p.parent/name).read_bytes())==expected,name
def main():
    arc=ROOT/"archive";manifest(arc/"SHA256SUMS");manifest(ROOT/"SOURCE_SHA256SUMS")
    stats=read(arc/"audit.json");count=0;receipts=0
    for case in ("A02","A06","C10","C11"):
        config_ids=set()
        with tarfile.open(arc/(case+".tar.gz"),"r|gz") as tar:
            traces={};blocks={};plans={};certs={}
            for ent in tar:
                b=tar.extractfile(ent).read();n=ent.name
                if n=="events.json":traces=json.loads(b)
                elif n.startswith("blocks/"):
                    key=n.split("/")[1];blocks[key]=zlib.decompress(b);assert sha(blocks[key])==key
                elif n.endswith("/plan.json"):
                    plan=json.loads(b);key=sha(b.strip());assert key==n.split("/")[0];plans[key]=plan
                    config_ids.add(sha(bytes(k+10*(u==3) for u,k,s in plan["rows"][1::3])))
                elif n.endswith("/certificate.json"):
                    d=json.loads(b);certs[d["plan_sha256"]]=d
            assert set(plans)==set(certs)==set(traces)
            for r in traces.values():
                data=b"".join(blocks[k] for k in r["blocks"])
                assert sha(data)==r["hash"] and r["shape"][1]==31 and len(data)==r["shape"][0]*31*8
            count+=len(traces)
        for m in "ACDER":
            log=arc/"logs"/case/m;rc=read(log/"receipt.json")
            assert rc["limit_s"]==30 and rc["status"] in ("NATURAL","CAP");receipts+=1
            p=arc/"endpoints"/case/m
            key=sha((p/"plan.json").read_bytes().strip());assert key in plans
            assert read(p/"certificate.json")["metrics"]==certs[key]["metrics"]
        for v in read(arc/"witnesses.json"):
            if v["case"]!=case:continue
            assert v["parent"]["plan"] in plans and v["joint"]["plan"] in plans
            for s in v["singles"]:
                if s["status"]=="TIMING":
                    assert (arc/"logs"/case/v["method"]/s["detail"]).is_file()
                else:assert s["plan"] in plans and s["cfg"] in config_ids
    assert receipts==stats["cells"]==20 and count==sum(stats["restored_plans"].values())
    print(json.dumps(dict(verified_cells=receipts,restored_traces=count,total_scientific_core_s=stats["total_core_s_upper"])))
if __name__=="__main__":main()
