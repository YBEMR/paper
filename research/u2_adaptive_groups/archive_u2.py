"""Store every native certificate and lossless full-resolution event array."""
import hashlib
import shutil
import tarfile
import zlib
from common_u2 import *

def package(code,root):
    dst=HERE/"results"/code;dst.mkdir(parents=True,exist_ok=False)
    blocks=root/"event_blocks";blocks.mkdir()
    index=[]
    for path in sorted(root.rglob("*.npz")):
        try:
            with np.load(path,allow_pickle=False) as f:a=f["events"]
        except (OSError,ValueError,EOFError,__import__("zipfile").BadZipFile) as exc:
            index.append(dict(path=path.relative_to(root).as_posix(),partial=str(exc)));continue
        assert a.ndim==2 and a.shape[1]==31 and a.dtype==np.dtype("<f8")
        assert a[0,0]==0 and np.array_equal(a[:-1,1],a[1:,0]) and np.array_equal(a[:-1,18:22],a[1:,14:18])
        keys=[]
        for part in np.split(a,np.searchsorted(a[:,0],np.arange(10000,a[-1,1],10000))):
            b=part.tobytes();k=sha(b);dest=blocks/k
            if not dest.exists():dest.write_bytes(zlib.compress(b,5))
            keys.append(k)
        h=sha(a.tobytes());assert sha(b"".join(zlib.decompress((blocks/k).read_bytes()) for k in keys))==h
        index.append(dict(path=path.relative_to(root).as_posix(),shape=list(a.shape),sha256=h,blocks=keys));path.unlink()
    save(root/"event_index.json",index)
    archive=root.parent/(code+".tar.gz")
    with tarfile.open(archive,"w:gz",compresslevel=1) as tar:tar.add(root,arcname=code)
    parts=[];total=hashlib.sha256()
    with archive.open("rb") as f:
        while b:=f.read(16*1024*1024):
            name=f"physical.tar.gz.part{len(parts):03d}";(dst/name).write_bytes(b);total.update(b)
            parts.append(dict(name=name,bytes=len(b),sha256=sha(b)))
    save(dst/"archive.json",dict(parts=parts,sha256=total.hexdigest(),event_arrays=sum("blocks" in r for r in index),
                                  partial=sum("partial" in r for r in index),blocks=len(list(blocks.iterdir()))))
    preview=[]
    for rep in (1,2,3):
        d=root/f"r{rep}";seed=read(d/"seed.json")
        for method in ("NT","W4","Q4",*LOCAL):
            rows=seed["rows"] if method=="W4" else lines(d/method/"certs.jsonl")
            eligible=seed["rows"]+rows if method in LOCAL else rows
            gain=best(eligible)
            preview.append(dict(rep=rep,method=method,J=gain["J"] if gain else None,seed=seed["J"],fourth_s=seed["fourth_s"],
                status=read(d/method/"receipt.json")["status"] if method!="W4" else seed["status"]))
    save(dst/"preview.json",preview)
    print("ARCHIVED",code,len(index),len(parts),flush=True)
