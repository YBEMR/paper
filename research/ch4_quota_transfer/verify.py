"""Validate the published archive without invoking a solver; optionally restore a plan."""
import argparse,csv,gzip,hashlib,json,tarfile,zlib
from pathlib import Path
from decision import CASES,OUT,csvrows

def digest(data):
    return hashlib.sha256(data).hexdigest()

def verify(export=None):
    cells=csvrows("cells")
    certs=csvrows("certificates")
    account=json.loads((OUT/"budget.json").read_bytes())
    assert len(cells)==60 and len(certs)==sum(int(r["certs"]) for r in cells)
    assert sum(int(r["cap"]) for r in cells)==account["nominal_issued_s"]==1440
    assert account["actual_cpu_s"]<=1500 and account["diagnostic_cpu_s"]<=120
    assert len(csvrows("fixed_groups"))==360 and len(csvrows("fixed_pairs"))==1080
    assert len(csvrows("quality_targets"))==120
    n=0
    for case in CASES:
        inp=json.loads((OUT/"inputs"/(case+".json")).read_bytes())
        assert digest(gzip.decompress((OUT/"inputs"/(case+".csv.gz")).read_bytes()))==inp["input_sha256"]
        p=OUT/"physical"/case
        info=json.loads((p/"index.json").read_bytes())
        blobs={}
        for part in sorted(p.glob("*.tar")):
            with tarfile.open(part,"r|") as tar:
                for m in tar:
                    assert m.name not in blobs
                    blobs[m.name]=zlib.decompress(tar.extractfile(m).read())
        issued={r["plan"] for r in certs if r["case"]==case}
        assert issued==set(info["plans"])
        for key in info["blocks"]:assert digest(blobs["blocks/"+key])==key
        for key,d in info["plans"].items():
            plan=blobs[key+"/plan"]; certificate=blobs[key+"/certificate"]
            assert digest(plan)==d["plan_sha"] and digest(plan.strip())==key
            assert digest(certificate)==d["cert_sha"] and json.loads(certificate)["plan_sha256"]==key
            data=b"".join(blobs["blocks/"+k] for k in d["blocks"])
            assert digest(data)==d["trace_sha"] and len(data)==8*d["shape"][0]*31 and d["shape"][1]==31
            if export and (case,key)==tuple(export[:2]):
                import numpy as np
                dest=Path(export[2]);dest.mkdir(parents=True,exist_ok=False)
                (dest/"plan.json").write_bytes(plan)
                (dest/"certificate.json").write_bytes(certificate)
                np.savez_compressed(dest/"trace.npz",events=np.frombuffer(data,dtype=np.float64).reshape(d["shape"]))
            n+=1
        for cell in (r for r in cells if r["case"]==case):
            delivered=[r for r in certs if all(r[k]==cell[k] for k in ("case","arm","cap","rep"))]
            assert all(float(r["t"])<=float(cell["cap"]) for r in delivered)
            first=min((float(r["t"]) for r in delivered if r["status"]=="SAFE"),default=None)
            assert bool(int(cell["safe"]))==(first is not None)
            assert (first is None and not cell["first_s"]) or first==float(cell["first_s"])
            if not cell["safe"]=="1":assert not any(cell[k] for k in ("J","lo","hi","last_s"))
    assert n==account["unique_physical"]
    if export:assert any(r["case"]==export[0] and r["plan"]==export[1] for r in certs)
    print(f"{len(cells)} runs, {len(certs)} on-time certificates, {n} distinct physical plans verified")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--restore",nargs=3,metavar=("CASE","PLAN_SHA","NEW_DIRECTORY"))
    verify(parser.parse_args().restore)
