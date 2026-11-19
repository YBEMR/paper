"""Archive completed E0 and fixed-work jobs during the longer benchmark."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
HERE=Path(__file__).resolve().parent
OUT=HERE/"checkpoints"
OUT.mkdir(exist_ok=True)
jobs=["e0-normal","e0-reject","fixed-M1","fixed-M2"]
files=[]
archive=io.BytesIO()
with gzip.GzipFile(fileobj=archive,mode="wb",mtime=0) as gz:
    with tarfile.open(fileobj=gz,mode="w|") as tar:
        for job in jobs:
            base=HERE/"raw"/job
            result=json.loads((base/"result.json").read_bytes())
            assert result["status"]=="PASS"
            for path in sorted(p for p in base.iterdir() if p.is_file()):
                content=path.read_bytes()
                name=path.relative_to(HERE).as_posix()
                info=tarfile.TarInfo(name)
                info.size=len(content)
                tar.addfile(info,io.BytesIO(content))
                files.append(dict(path=name,bytes=len(content),sha256=hashlib.sha256(content).hexdigest()))
packed=archive.getvalue()
(OUT/"e0_fixed.tar.gz").write_bytes(packed)
(OUT/"e0_fixed.json").write_text(json.dumps(dict(jobs=jobs,files=files,
    archive_sha256=hashlib.sha256(packed).hexdigest(),formal_stage="development in progress"),
    indent=2)+"\n",encoding="utf-8")
