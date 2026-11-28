"""Lossless post-clock storage for all delivered proposals, including thermal rejections."""
import argparse
import hashlib
import io
import json
import tarfile
import time
import zlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_bytes())
def logs(p):
    return [json.loads(b) for b in p.read_bytes().splitlines() if b.endswith(b"}")] if p.exists() else []
def put(t,name,data):
    h=tarfile.TarInfo(name);h.size=len(data);t.addfile(h,io.BytesIO(data))
def pack(case):
    started=time.perf_counter();lane=ROOT/"archive"/case;target=lane/"physical";target.mkdir()
    label=read(lane/"lane.json")["case"];plans={};blocks={};chunk=0;tar=None
    for cell in sorted(lane.glob("r*-*")):
        rc=read(cell/"receipt.json")
        for filename in ("search","refine"):
            for r in logs(cell/(filename+".jsonl")):
                if r["event"]!="certificate":continue
                pt=r["point"];key=pt["plan"]
                if r["t"]>(rc["cut"] if filename=="search" else 60):continue
                stage="search/physical" if filename=="search" else r["stage"]
                path=cell/stage/"evidence"/label/key
                p=(path/"plan.json").read_bytes();c=(path/"certificate.json").read_bytes()
                cert=json.loads(c)
                assert sha(p.strip())==key==cert["plan_sha256"] and cert["metrics"]["E_J"]==pt["J"] and cert["metrics"]["E_bounds"]==pt["bounds"]
                if key in plans:continue
                if tar is None or tar.offset>35_000_000:
                    if tar:tar.close()
                    chunk+=1;name=f"part-{chunk:03d}.tar";tar=tarfile.open(target/name,"w")
                put(tar,key+"/plan",zlib.compress(p,5));put(tar,key+"/certificate",zlib.compress(c,5))
                with np.load(path/"trace.npz") as f:a=f["events"]
                assert a.shape[1]==31 and a.dtype==np.float64
                parts=[]
                for component in np.split(a,np.searchsorted(a[:,0],np.arange(10000,a[-1,1],10000))):
                    b=component.tobytes();k=sha(b);parts.append(k)
                    if k not in blocks:
                        put(tar,"blocks/"+k,zlib.compress(b,3));blocks[k]=name
                plans[key]=dict(archive=name,plan_sha=sha(p),cert_sha=sha(c),blocks=parts,shape=list(a.shape),trace_sha=sha(a.tobytes()))
    if tar:tar.close()
    (target/"index.json").write_text(json.dumps(dict(plans=plans,blocks=blocks),separators=(",",":"))+"\n")
    verify(target)
    # The original physical writers ran inside every timed cell. Drop their local
    # staging copies only after the delivered objects have a verified archive.
    for cell in lane.glob("r*-*"):
        for p in cell.glob("**/evidence/*/*/*"):
            if p.is_file() and p.name in ("plan.json","certificate.json","trace.npz"):p.unlink()
        # Native statistics may be large. The complete caller ledger remains available.
        for p in cell.glob("search/run.json"):
            data=p.read_bytes();q=p.with_suffix(".json.z");q.write_bytes(zlib.compress(data,3));assert zlib.decompress(q.read_bytes())==data;p.unlink()
    (lane/"archive_receipt.json").write_text(json.dumps(dict(unique=len(plans),blocks=len(blocks),offline_s=time.perf_counter()-started))+"\n")
def verify(target):
    ix=read(target/"index.json");plans=ix["plans"];blocks={};seen=set();certs=set()
    for p in sorted(target.glob("*.tar")):
        with tarfile.open(p,"r|") as t:
            for m in t:
                k,n=m.name.split("/");b=zlib.decompress(t.extractfile(m).read())
                if k=="blocks":
                    assert sha(b)==n and ix["blocks"][n]==p.name;blocks[n]=b
                elif n=="plan":
                    assert sha(b.strip())==k and sha(b)==plans[k]["plan_sha"];seen.add(k)
                else:
                    assert json.loads(b)["plan_sha256"]==k and sha(b)==plans[k]["cert_sha"];certs.add(k)
    assert seen==certs==set(plans)
    for d in plans.values():
        h=hashlib.sha256();n=0
        for k in d["blocks"]:b=blocks[k];h.update(b);n+=len(b)
        assert h.hexdigest()==d["trace_sha"] and n==d["shape"][0]*31*8
def restore(case,key,dest):
    p=ROOT/"archive"/case/"physical";ix=read(p/"index.json");d=ix["plans"][key];parts={}
    names={d["archive"],*[ix["blocks"][k] for k in d["blocks"]]};keys={"blocks/"+k for k in d["blocks"]}|{key+"/plan",key+"/certificate"}
    for name in names:
        with tarfile.open(p/name,"r|") as t:
            for m in t:
                if m.name in keys:parts[m.name]=zlib.decompress(t.extractfile(m).read())
    data=b"".join(parts["blocks/"+k] for k in d["blocks"])
    assert sha(data)==d["trace_sha"] and sha(parts[key+"/plan"].strip())==key and sha(parts[key+"/certificate"])==d["cert_sha"]
    dest.mkdir(parents=True,exist_ok=False)
    for n in ("plan","certificate"):(dest/(n+".json")).write_bytes(parts[key+"/"+n])
    np.savez_compressed(dest/"trace.npz",events=np.frombuffer(data,dtype=np.float64).reshape(d["shape"]))
if __name__=="__main__":
    import sys
    if len(sys.argv)==2:pack(sys.argv[1])
    else:restore(sys.argv[1],sys.argv[2],Path(sys.argv[3]))
