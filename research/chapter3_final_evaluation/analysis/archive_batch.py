"""Pack all original formal receipts, logs, schedules and certificates, then verify reconstruction."""
import argparse
import hashlib
import io
import json
import os
import sys
import tarfile
import tempfile
from collections import defaultdict
from pathlib import Path
from audit_results import ROOT,OUT,CASES
from setup_inputs import G2
sys.path.insert(0,str(G2))
from archive import encode,restore_blob
DEST=ROOT/"archive"
BLOCK=524288


def sha(data):
    return hashlib.sha256(data).hexdigest()


def add(tar,name,data):
    info=tarfile.TarInfo(name)
    info.size=len(data)
    tar.addfile(info,io.BytesIO(data))


def verify_archive(name,index,dest=None):
    with tempfile.TemporaryDirectory() as tmp:
        arc=Path(tmp)/"archive"
        total=hashlib.sha256()
        with arc.open("wb") as f:
            for part in index["parts"]:
                data=(DEST/part["name"]).read_bytes()
                assert sha(data)==part["sha256"]
                f.write(data)
                total.update(data)
        assert total.hexdigest()==index["sha256"]
        with tarfile.open(arc,"r:xz") as tar:
            paths=json.load(tar.extractfile("paths.json"))
            by_hash=defaultdict(list)
            for path,entry in paths.items():
                by_hash[entry["sha256"]].append((path,entry["encoding"]))
            for obj in tar:
                if obj.name=="paths.json":
                    continue
                code=obj.name.removeprefix("objects/")
                group=by_hash.pop(code)
                raw=restore_blob(group[0][1],tar.extractfile(obj).read())
                assert sha(raw)==code
                for path,_ in group:
                    if dest is None:
                        assert (OUT/path).read_bytes()==raw,path
                    else:
                        target=(dest/path).resolve()
                        if not target.is_relative_to(dest.resolve()):
                            raise ValueError(path)
                        target.parent.mkdir(parents=True,exist_ok=True)
                        if target.exists() and sha(target.read_bytes())!=code:
                            raise FileExistsError(target)
                        target.write_bytes(raw)
            assert not by_hash and len(paths)==index["files"]


def pack(name,files):
    files=sorted(files)
    paths={}
    objects={}
    with tempfile.TemporaryDirectory() as tmp:
        temp=Path(tmp)
        for p in files:
            data=p.read_bytes()
            code=sha(data)
            if code not in objects:
                method,raw=encode(p,data)
                (temp/code).write_bytes(raw)
                objects[code]=(method,p.suffix)
            paths[p.relative_to(OUT).as_posix()]={"sha256":code,"encoding":objects[code][0]}
        arc=temp/"archive"
        with tarfile.open(arc,"w:xz",preset=4) as tar:
            add(tar,"paths.json",json.dumps(paths,sort_keys=True,separators=(",",":")).encode())
            for code in sorted(objects,key=lambda h:(objects[h][1],h)):
                add(tar,"objects/"+code,(temp/code).read_bytes())
        total=hashlib.sha256()
        parts=[]
        with arc.open("rb") as f:
            while data:=f.read(BLOCK):
                part=f"{name}.{len(parts):04}"
                target=DEST/part
                if target.exists() and target.read_bytes()!=data:
                    raise FileExistsError(target)
                target.write_bytes(data)
                parts.append({"name":part,"sha256":sha(data)})
                total.update(data)
        return dict(files=len(files),objects=len(objects),size=arc.stat().st_size,sha256=total.hexdigest(),parts=parts)


def main():
    if not (OUT/"batch_end.json").exists():
        raise RuntimeError("Batch is open")
    DEST.mkdir(exist_ok=True)
    groups={"batch":[]}
    groups.update({c:[] for c in CASES})
    for p in sorted(OUT.rglob("*")):
        if not p.is_file():
            continue
        rel=p.relative_to(OUT).parts
        name=rel[1].split("_")[0] if rel[0] in ("cells","pools") else "batch"
        groups[name].append(p)
    index={}
    for name,files in groups.items():
        index[name]=pack(name,files)
        verify_archive(name,index[name])
    (DEST/"manifest.json").write_text(json.dumps(index,indent=2)+"\n",encoding="utf8",newline="\n")


if __name__=="__main__":
    if len(sys.argv)==1:
        main()
    elif len(sys.argv)==3 and sys.argv[1]=="restore":
        for name,entry in json.loads((DEST/"manifest.json").read_bytes()).items():
            verify_archive(name,entry,Path(sys.argv[2]))
    else:
        raise SystemExit("Use no arguments to archive, or restore DIRECTORY")
