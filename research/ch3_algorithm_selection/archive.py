"""Pack only sealed evidence; do not publish a second copy of the unpacked units."""
from hashlib import sha256
import io
import json
from pathlib import Path
import tarfile

from loads import CFG,HERE


def pack():
    out=HERE/"archives"
    out.mkdir(exist_ok=True)
    manifest={}
    for case in sorted((HERE/"units").iterdir()):
        files={}
        for slot in sorted(case.iterdir()):
            rec=json.loads((slot/"receipt.json").read_bytes())
            for n,h in rec["files"].items():
                if Path(n).name!=n or sha256((slot/n).read_bytes()).hexdigest()!=h:
                    raise ValueError("Seal mismatch: "+str(slot))
            for n in ["receipt.json",*rec["files"]]:
                files[slot.name+"/"+n]=(slot/n).read_bytes()
        target=out/(case.name+".tar")
        with tarfile.open(target,"w",format=tarfile.USTAR_FORMAT) as tar:
            for name,b in sorted(files.items()):
                info=tarfile.TarInfo(name)
                info.size=len(b)
                tar.addfile(info,io.BytesIO(b))
        manifest[target.name]=dict(sha256=sha256(target.read_bytes()).hexdigest(),members=len(files),
                                   units=sum(n.endswith("/receipt.json") for n in files),bytes=target.stat().st_size)
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf8",newline="\n")


if __name__=="__main__":
    pack()
