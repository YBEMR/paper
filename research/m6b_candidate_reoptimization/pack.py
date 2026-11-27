"""Post-clock lossless collection of every emitted physical plan, certificate and IEEE temperature trace."""
import hashlib
import io
import json
import tarfile
import time
import zlib
from collections import defaultdict
from pathlib import Path
import numpy as np
from inventory import ARCH,ROOT,sha,raw,save,read
def add(t,name,b):
    m=tarfile.TarInfo(name);m.size=len(b);t.addfile(m,io.BytesIO(b))
def main():
    start=time.perf_counter();phys=ARCH/"physical";phys.mkdir()
    locations=defaultdict(list);cut_files=[]
    for p in sorted(ARCH.glob("**/evidence/*/*/plan.json")):
        if (p.parent/"trace.npz").is_file():locations[p.parent.parent.name,p.parent.name].append(p.parent)
        else:cut_files.append(str(p.relative_to(ARCH)))
    index={};current=None;tar=None;blocks=set();store={};chunk=0;size=0
    for (case,key),copies in sorted(locations.items()):
        if current!=case:
            current=case;chunk=0;blocks=set();size=100_000_000
        if size>38_000_000:
            if tar:tar.close()
            chunk+=1;name=f"{case}-{chunk:02d}.tar";tar=tarfile.open(phys/name,"w");size=0
        p=copies[0];plan=(p/"plan.json").read_bytes();cert=(p/"certificate.json").read_bytes()
        assert sha(plan.strip())==key and read(p/"certificate.json")["plan_sha256"]==key
        try:
            with np.load(p/"trace.npz") as f:a=f["events"]
        except Exception:
            # Incomplete writes are only permissible for unreported, cut-off calls.
            cut_files.append(str(p.relative_to(ARCH)));continue
        assert a.shape[1]==31 and a.dtype==np.float64
        for item,b in (("plan",plan),("cert",cert)):
            packed=zlib.compress(b,6);add(tar,key+"/"+item+".z",packed);size+=len(packed)
        chunks=[]
        for part in np.split(a,np.searchsorted(a[:,0],np.arange(10000,a[-1,1],10000))):
            b=part.tobytes();h=sha(b);chunks.append(h)
            if h not in blocks:
                z=zlib.compress(b,3);add(tar,"blocks/"+h,z);size+=len(z)+512;store[h]=name;blocks.add(h)
        index[key]=dict(case=case,archive=name,plan_file_sha256=sha(plan),certificate_file_sha256=sha(cert),
            trace_sha256=sha(a.tobytes()),shape=list(a.shape),blocks=chunks,
            produced=[str(v.parent.parent.parent.relative_to(ARCH)) for v in copies])
    if tar:tar.close()
    save(phys/"index.json",dict(plans=index,blocks=store,unfinished=cut_files))
    verify(phys)
    for p in ARCH.rglob("mapping_events.jsonl"):
        for line in p.read_bytes().splitlines():
            if not line.endswith(b"}"):continue
            e=json.loads(line)
            if e["kind"]=="stage" and e["point"]:assert e["point"]["plan"] in index
    # Preserve partial line evidence and compress verbose per-layer state ledgers.
    import gzip
    for p in list(ARCH.rglob("events.jsonl"))+list(ARCH.rglob("mapping_events.jsonl")):
        b=p.read_bytes();q=p.with_suffix(p.suffix+".gz");q.write_bytes(gzip.compress(b,compresslevel=5));assert gzip.decompress(q.read_bytes())==b;p.unlink()
    for folder in ARCH.glob("**/evidence"):
        for p in folder.rglob("*"):
            if p.is_file() and p.name in ("plan.json","certificate.json","trace.npz"):p.unlink()
    print("physical",len(index),"archive_seconds",time.perf_counter()-start,flush=True)
def verify(phys):
    idx=read(phys/"index.json");plans=idx["plans"];mapping=idx["blocks"]
    by_case=defaultdict(dict)
    for key,d in plans.items():by_case[d["case"]][key]=d
    for case,items in by_case.items():
        blocks={};physical=set();certs=set()
        for p in sorted(phys.glob(case+"-*.tar")):
            with tarfile.open(p,"r|") as t:
                for m in t:
                    prefix,suffix=m.name.split("/");b=zlib.decompress(t.extractfile(m).read())
                    if prefix=="blocks":
                        assert sha(b)==suffix;blocks[suffix]=b
                    elif suffix=="plan.z":
                        assert sha(b.strip())==prefix and sha(b)==items[prefix]["plan_file_sha256"];physical.add(prefix)
                    else:
                        assert sha(b)==items[prefix]["certificate_file_sha256"] and json.loads(b)["plan_sha256"]==prefix;certs.add(prefix)
        assert physical==certs==set(items)
        for d in items.values():
            h=hashlib.sha256();n=0
            for k in d["blocks"]:h.update(blocks[k]);n+=len(blocks[k])
            assert h.hexdigest()==d["trace_sha256"] and n==d["shape"][0]*31*8
if __name__=="__main__":main()
