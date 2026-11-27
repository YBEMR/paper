"""Lossless event blocks and original scientific records in bounded Git objects."""
import csv
import hashlib
import io
import json
import os
import shutil
import tarfile
import zlib
from pathlib import Path

import numpy as np
from interface import CASES, HERE, OUT, raw, read, save, sha

def compact():
    # Store unchanged numerical event arrays by contiguous one-second blocks.
    blobs=OUT/"event_blocks"
    blobs.mkdir(exist_ok=True)
    index=[]
    for p in sorted(OUT.rglob("*.npz")):
        try:
            with np.load(p,allow_pickle=False) as f:
                a=f["events"]
        except Exception as exc:
            index.append(dict(path=p.relative_to(OUT).as_posix(),partial=str(exc)))
            continue
        assert a.dtype==np.float64 and a.ndim==2 and a.shape[1]==31 and a[0,0]==0
        assert np.array_equal(a[:-1,1],a[1:,0]) and np.array_equal(a[:-1,18:22],a[1:,14:18])
        keys=[]
        for part in np.split(a,np.searchsorted(a[:,0],np.arange(10000,a[-1,1],10000))):
            data=part.tobytes();key=sha(data);dst=blobs/key
            if not dst.exists(): dst.write_bytes(zlib.compress(data,5))
            keys.append(key)
        assert sha(b"".join(zlib.decompress((blobs/k).read_bytes()) for k in keys))==sha(a.tobytes())
        index.append(dict(path=p.relative_to(OUT).as_posix(),shape=a.shape,sha256=sha(a.tobytes()),blocks=keys))
        p.unlink()
    save(OUT/"event_index.json",index)

def main():
    import tempfile
    compact()
    dest=HERE/"results"
    dest.mkdir(exist_ok=True)
    for name in ("curves.csv","environment.json","interface/gate.json","interface/source_hashes.json"):
        p=OUT/name
        if p.is_file():
            shutil.copyfile(p,dest/p.name)
    public={}
    for code in CASES:
        records={}
        for method in ("NT","Q4","Proposed","NT+AB","NT+Proposed"):
            folder=OUT/"cells"/code/method
            if not folder.exists():continue
            records[method]={}
            for name in ("receipt.json","finished.json","widths.jsonl","rounds.jsonl","optimization.json","construction.json","seed_identity.json","result.json","pool/pool.json"):
                p=folder/name
                if p.exists():
                    records[method][name]=[json.loads(line) for line in p.read_bytes().splitlines()] if p.suffix==".jsonl" else read(p)
        public[code]=records
        for method in ("NT","Proposed","Q4"):
            p=OUT/"interface"/code/method/"audit.json"
            if p.exists():public[code]["interface_"+method]=read(p)
    save(dest/"details.json",public)
    archive=Path(tempfile.gettempdir())/"u1-physical.tar.gz"
    with tarfile.open(archive,"w:gz",compresslevel=2) as tar:
        tar.add(OUT,arcname="evidence")
    names=[]
    h=hashlib.sha256()
    with archive.open("rb") as f:
        while block:=f.read(16*1024*1024):
            name=f"physical.tar.gz.part{len(names):03d}"
            (dest/name).write_bytes(block);names.append(dict(name=name,sha256=sha(block),bytes=len(block)));h.update(block)
    save(dest/"archive.json",dict(parts=names,archive_sha256=h.hexdigest(),dtype="<f8",columns=31))
    print("PACKED",len(names),sum(n["bytes"] for n in names),flush=True)

if __name__=="__main__":
    main()
