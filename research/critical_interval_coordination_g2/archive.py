"""Lossless evidence transport. Restore original paths and verify all original file hashes."""
import argparse, gzip, hashlib, io, json, os, tarfile, tempfile, zipfile
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
def digest(b):return hashlib.sha256(b).hexdigest()
def encode(p,b):
    if p.suffix==".npz":
        with zipfile.ZipFile(io.BytesIO(b)) as z:
            assert z.namelist()==["events.npy"]
            raw=z.read("events.npy")
        if restore_blob("npz",raw)==b:return "npz",raw
    return "raw",b
def restore_blob(encoding,b):
    if encoding=="raw":return b
    assert encoding=="npz"
    buf=io.BytesIO();np.savez_compressed(buf,events=np.load(io.BytesIO(b),allow_pickle=False))
    return buf.getvalue()
def safe_path(folder,name):
    p=(folder/name).resolve()
    if not p.is_relative_to(folder.resolve()):raise ValueError(name)
    return p
def pack(label,paths):
    dest=ROOT/"archive";dest.mkdir(exist_ok=True)
    final=dest/(label+".tar.xz")
    if final.exists():raise FileExistsError(final)
    with tempfile.TemporaryDirectory(dir=dest) as tmp:
        tmp=Path(tmp);index={};blobs={}
        for p in sorted(set(paths)):
            if p.is_dir():continue
            assert p.relative_to(ROOT).parts[0] in ("runs","engineering","evidence")
            assert p.suffix in (".json",".npz",".gz",".jsonl",".log")
            data=p.read_bytes();h=digest(data);name=p.relative_to(ROOT).as_posix()
            if h not in blobs:
                encoding,raw=encode(p,data);(tmp/h).write_bytes(raw)
                blobs[h]=(encoding,p.suffix, name)
            index[name]={"sha256":h,"encoding":blobs[h][0]}
        f=tmp/"payload"
        with tarfile.open(f,"w:xz",preset=4) as tar:
            def add(name,b):
                info=tarfile.TarInfo(name);info.size=len(b);tar.addfile(info,io.BytesIO(b))
            add("index.json",json.dumps(index,sort_keys=True,separators=(",",":")).encode())
            for h in sorted(blobs,key=lambda k:blobs[k]):
                add("objects/"+h,(tmp/h).read_bytes())
        verify(f)
        data=f.read_bytes()
        info=dict(group=label,paths=len(index),objects=len(blobs),size=len(data),sha256=digest(data))
        if len(data)<=524288:
            os.replace(f,final)
        else:
            parts=[]
            for i in range(0,len(data),524288):
                chunk=data[i:i+524288];name=label+f".part{i//524288:04d}"
                target=dest/name
                if target.exists() and digest(target.read_bytes())!=digest(chunk):raise FileExistsError(target)
                target.write_bytes(chunk);parts.append(dict(name=name,sha256=digest(chunk)))
            (dest/(label+".index.json")).write_text(json.dumps(dict(**info,parts=parts),indent=2)+"\n",encoding="utf8",newline="\n")
    return info
def verify(archive,dest=None):
    if archive.name.endswith(".index.json"):
        spec=json.loads(archive.read_bytes())
        with tempfile.TemporaryDirectory() as tmp:
            stream=Path(tmp)/"payload.tar.xz";whole=hashlib.sha256()
            with stream.open("wb") as out:
                for item in spec["parts"]:
                    chunk=safe_path(archive.parent,item["name"]).read_bytes()
                    assert digest(chunk)==item["sha256"]
                    out.write(chunk);whole.update(chunk)
            assert whole.hexdigest()==spec["sha256"]
            return verify(stream,dest)
    with tarfile.open(archive,"r:xz") as tar:
        index=json.load(tar.extractfile("index.json"));by_hash={}
        for n,v in index.items():by_hash.setdefault(v["sha256"],[]).append((n,v["encoding"]))
        for member in tar:
            if member.name=="index.json":continue
            h=member.name.removeprefix("objects/");entries=by_hash.pop(h)
            b=restore_blob(entries[0][1],tar.extractfile(member).read())
            if digest(b)!=h:raise ValueError(member.name)
            if dest is not None:
                for name,_ in entries:
                    p=safe_path(dest,name);p.parent.mkdir(parents=True,exist_ok=True)
                    if p.exists() and digest(p.read_bytes())!=h:raise FileExistsError(p)
                    p.write_bytes(b)
        assert not by_hash
def group(label):
    if label=="preflight":
        return [*list((ROOT/"engineering").rglob("*")),*list((ROOT/"evidence").rglob("*"))]
    if label=="initialization":
        dirs=[ROOT/"runs"/("init_"+case) for case in ("S32","S80","D1","D2","D3")]
    else:
        kind,case=label.split("_")
        assert kind in ("main","strong") and case in ("S32","S80","D1","D2","D3")
        dirs=list((ROOT/"runs").glob(kind+"_"+case+"_*"))
        assert len(dirs)==(9 if kind=="main" else 2)
    assert all((d/"receipt.json").exists() for d in dirs)
    return [p for d in dirs for p in d.rglob("*")]
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("action",choices=("pack","verify","restore"));parser.add_argument("name")
    parser.add_argument("dest",nargs="?",type=Path);a=parser.parse_args()
    if a.action=="pack":print(json.dumps(pack(a.name,group(a.name))))
    elif a.action=="verify":verify(Path(a.name))
    elif a.dest:verify(Path(a.name),a.dest)
    else:parser.error("restore needs an output directory")
