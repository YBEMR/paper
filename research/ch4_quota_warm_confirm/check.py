"""Offline consistency check, with optional recovery of a complete certified trace."""
import argparse,gzip,hashlib,json,tarfile,zlib
from pathlib import Path
from statistics import median
from analyze import OUT,stats,audit

def sha(b):return hashlib.sha256(b).hexdigest()

def check(restore):
    cells=audit()
    certs=stats.csvrows("certificates")
    steps=stats.csvrows("improvements")
    targets=stats.csvrows("quality_targets")
    assert len(targets)==2*len(cells)
    restored=False
    for case in stats.CASES:
        p=OUT/"physical"/case
        info=json.loads((p/"index.json").read_bytes())
        inp=json.loads((OUT/"inputs"/(case+".json")).read_bytes())
        assert sha(gzip.decompress((OUT/"inputs"/(case+".csv.gz")).read_bytes()))==inp["input_sha256"]
        items={r["plan"] for r in certs if r["case"]==case}
        assert items==set(info["plans"])
        blobs={}
        for part in sorted(p.glob("*.tar")):
            with tarfile.open(part,"r|") as f:
                for member in f:
                    assert member.name not in blobs
                    blobs[member.name]=zlib.decompress(f.extractfile(member).read())
        for key in info["blocks"]:assert sha(blobs["blocks/"+key])==key
        for key,d in info["plans"].items():
            plan=blobs[key+"/plan"];cert=blobs[key+"/certificate"]
            assert sha(plan.strip())==key and sha(plan)==d["plan_sha"] and sha(cert)==d["cert_sha"]
            receipt=json.loads(cert)
            assert receipt["plan_sha256"]==key
            metrics=receipt["metrics"]
            assert metrics["min_deadline_slack_ms"]>=0
            if metrics["status"]=="SAFE":assert max(metrics["peak_hi"])<=80
            buf=b"".join(blobs["blocks/"+k] for k in d["blocks"])
            assert sha(buf)==d["trace_sha"] and len(buf)==8*d["shape"][0]*31 and d["shape"][1]==31
            if restore and [case,key]==restore[:2]:
                import numpy as np
                dest=Path(restore[2]);dest.mkdir(parents=True,exist_ok=False)
                (dest/"plan.json").write_bytes(plan);(dest/"certificate.json").write_bytes(cert)
                np.savez_compressed(dest/"trace.npz",events=np.frombuffer(buf,dtype=np.float64).reshape(d["shape"]))
                restored=True
        ref=[float(r["hi"]) for r in cells if r["case"]==case and r["cap"]=="60" and r["safe"]=="1"]
        for c in (r for r in cells if r["case"]==case):
            def same(r):return all(r[k]==c[k] for k in ("case","arm","rep","cap"))
            issued=sorted((r for r in certs if same(r) and r["status"]=="SAFE"),key=lambda r:float(r["t"]))
            best=None;improved=[]
            for r in issued:
                if best is None or float(r["hi"])<float(best["lo"]):
                    best=r;improved.append((r["plan"],r["t"]))
            assert improved==[(r["plan"],r["t"]) for r in steps if same(r)]
            assert c["plan"]==(best["plan"] if best else "")
            for t in (r for r in targets if same(r)):
                if not ref:
                    assert t["status"]=="no_reference"
                    continue
                limit=median(ref)*(1+float(t["tolerance"]))
                assert limit==float(t["target_hi_J"])
                hits=[r for r in issued if float(r["hi"])<=limit]
                assert t["status"]==("hit" if hits else "above_target" if issued else "no_SAFE")
                assert t["first_hit_s"]==(hits[0]["t"] if hits else "")
    if restore:assert restored
    print(f"Verified {len(cells)} cells, {len(certs)} certified deliveries and {len(targets)} threshold decisions.")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--restore",nargs=3,metavar=("CASE","PLAN_SHA","NEW_DIRECTORY"))
    check(parser.parse_args().restore)
