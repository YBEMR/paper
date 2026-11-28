"""Build and verify a lossless, window-block-deduplicated archive of delivered certificates."""
import collections
import csv
import hashlib
import json
import shutil
import sys
import tarfile
import zlib
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"ch3_integrated_quality_v1"))
from evidence import put, verify, read, logs, sha

def delivered(cell,budget):
    for name in ("search","refine","maps"):
        file=cell/(name+".jsonl")
        for e in logs(file):
            if e["t"]>budget or e["event"]!="certificate":
                continue
            if name=="search":
                base=cell/"search/physical"
            elif name=="refine":
                base=cell/e["stage"]
            else:
                base=cell/"visits"/str(e["index"])/e["stage"]
            yield e,base,name

def main(code):
    source=ROOT/"paired_raw"/code
    dest=ROOT/"paired_results"/code
    physical=dest/"physical"
    physical.mkdir(parents=True)
    plans,blocks={},{}
    tar=None
    for cell in sorted(source.iterdir()):
        if not (cell/"receipt.json").is_file():continue
        rc=read(cell/"receipt.json")
        target=dest/cell.name
        target.mkdir()
        for name in ("receipt.json","start.jsonl","native.json","search.jsonl","refine.jsonl","ledger.jsonl","maps.jsonl"):
            if (cell/name).exists():shutil.copyfile(cell/name,target/name)
        with (target/"dp.jsonl").open("wb") as out:
            for path in sorted([*cell.glob("visits/*/events.jsonl"),*cell.glob("map*/events.jsonl")]):
                for item in logs(path):
                    item["origin"]=path.parent.relative_to(cell).as_posix()
                    # Keep each device's full DP statistics in the compressed ledger below.
                    out.write((json.dumps(item,separators=(",",":"))+"\n").encode())
        dp=target/"dp.jsonl"
        compressed=zlib.compress(dp.read_bytes(),3)
        assert zlib.decompress(compressed)==dp.read_bytes()
        dp.with_suffix(".jsonl.z").write_bytes(compressed)
        dp.unlink()
        events=[]
        for e,base,name in delivered(cell,rc["budget"]):
            p=e["point"];key=p["plan"]
            folder=next((base/"evidence").glob("*/"+key))
            plan=(folder/"plan.json").read_bytes()
            cert=(folder/"certificate.json").read_bytes()
            d=json.loads(cert)
            assert sha(plan.strip())==key==d["plan_sha256"] and d["metrics"]["E_bounds"]==p["bounds"]
            assert d["metrics"]["status"]==p["status"] and d["metrics"]["E_J"]==p["J"]
            mapping=sha(bytes(r[0] for r in json.loads(plan)["rows"][1::3]))
            assert e.get("mapping",mapping)==mapping
            events.append(dict(t=e["t"],stage=e.get("stage",name),mapping=mapping,index=e.get("index"),point=p))
            if key in plans:continue
            if tar is None or tar.offset>25_000_000:
                if tar:tar.close()
                tarname="part-%03d.tar"%(len(list(physical.glob("*.tar")))+1)
                tar=tarfile.open(physical/tarname,"w")
            put(tar,key+"/plan",zlib.compress(plan,5))
            put(tar,key+"/certificate",zlib.compress(cert,5))
            with np.load(folder/"trace.npz") as h:a=h["events"]
            assert a.dtype==np.float64 and a.shape[1]==31
            assert a[0,0]==0 and np.all(a[:,1]>a[:,0]) and np.array_equal(a[:-1,1],a[1:,0]) and np.isfinite(a).all()
            keys=[]
            for chunk in np.split(a,np.searchsorted(a[:,0],np.arange(10000,a[-1,1],10000))):
                b=chunk.tobytes();k=sha(b);keys.append(k)
                if k not in blocks:
                    blocks[k]=tarname
                    put(tar,"blocks/"+k,zlib.compress(b,3))
            plans[key]=dict(archive=tarname,plan_sha=sha(plan),cert_sha=sha(cert),blocks=keys,
                            shape=list(a.shape),trace_sha=sha(a.tobytes()),mapping=mapping)
        with (target/"certificates.jsonl").open("w") as file:
            for event in sorted(events,key=lambda r:r["t"]):file.write(json.dumps(event,separators=(",",":"))+"\n")
    if tar:tar.close()
    (physical/"index.json").write_text(json.dumps(dict(plans=plans,blocks=blocks),separators=(",",":"))+"\n")
    verify(physical)

if __name__=="__main__":
    main(sys.argv[1])
