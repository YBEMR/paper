"""Preserve every formal event and receipt in portable three-method tar.xz archives."""
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile

from run_formal import HERE, jobs


def add(archive,name,data):
    info=tarfile.TarInfo(name=name)
    info.size=len(data)
    info.mode=0o644
    archive.addfile(info,io.BytesIO(data))


def pack_batch(first):
    base=HERE/"runs"
    units=[f"u{i:03d}" for i in range(first,first+3)]
    if any(not (base/u/"receipt.json").exists() for u in units):
        return
    dest=HERE/"archives"/f"{units[0]}-{units[-1]}.tar.xz"
    if dest.exists():
        return
    tmp=dest.with_suffix(".partial")
    manifests={}
    with tarfile.open(tmp,"w:xz",preset=4) as archive:
        for unit in units:
            src=base/unit
            for file in sorted(src.iterdir()):
                if file.name not in {"console.txt","events.jsonl.gz","receipt.json","reservation.json","result.json"}:
                    raise ValueError(file)
                name=f"{unit}/{file.name}"
                data=file.read_bytes()
                if file.name=="events.jsonl.gz":
                    try:
                        data=gzip.decompress(data)
                        name=name[:-3]
                    except (EOFError,OSError):
                        if json.loads((src/"receipt.json").read_bytes())["state"]=="finished":
                            raise
                manifests[name]=hashlib.sha256(data).hexdigest()
                add(archive,name,data)
        add(archive,"member_sha256.json",(json.dumps(manifests,indent=2)+"\n").encode())
    with tarfile.open(tmp) as archive:
        for name,expected in manifests.items():
            if hashlib.sha256(archive.extractfile(name).read()).hexdigest()!=expected:
                raise ValueError(name)
    os.replace(tmp,dest)


if __name__=="__main__":
    (HERE/"archives").mkdir(exist_ok=True)
    for first in range(0,len(jobs()),3):
        pack_batch(first)
