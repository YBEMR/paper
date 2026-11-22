"""Seal the actual reservations, including original compressed logs and nested source receipts."""
from hashlib import sha256
import io
import json
from pathlib import Path
import tarfile

HERE=Path(__file__).resolve().parent

def digest(data): return sha256(data).hexdigest()

def archive():
    out=HERE/"archives"
    out.mkdir(exist_ok=True)
    manifest={}
    for folder in sorted((HERE/"units").iterdir()):
        if not folder.is_dir(): continue
        rec=json.loads((folder/"receipt.json").read_bytes())
        target=out/(folder.name+".tar")
        with tarfile.open(target,"w",format=tarfile.USTAR_FORMAT) as tar:
            for n in sorted(["receipt.json",*rec["files"]]):
                data=(folder/n).read_bytes()
                if n in rec["files"] and digest(data)!=rec["files"][n]: raise ValueError(n)
                entry=tarfile.TarInfo(n)
                entry.size=len(data)
                tar.addfile(entry,io.BytesIO(data))
        manifest[folder.name]=dict(sha256=digest(target.read_bytes()),bytes=target.stat().st_size,
                state=rec["state"],freeze=rec["freeze"],members=len(rec["files"])+1)
    (out/"manifest.json").write_bytes((json.dumps(manifest,indent=2)+"\n").encode())
    (out/"trace_gate.json").write_bytes((HERE/"units/trace_gate.json").read_bytes())

if __name__=="__main__": archive()
