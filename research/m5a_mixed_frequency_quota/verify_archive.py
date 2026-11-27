"""Verify manifests and all original event-array hashes from published bytes."""
import hashlib
import io
import json
import tarfile
import zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def sha(b):return hashlib.sha256(b).hexdigest()
def verify(path):
    lines=path.read_text().splitlines()
    for line in lines:
        value,name=line.split("  ",1)
        assert sha((path.parent/name).read_bytes())==value,name
    return len(lines)
if __name__=="__main__":
    source=verify(ROOT/"SOURCE_SHA256SUMS")
    files=verify(ROOT/"archive/SHA256SUMS")
    count=0
    for case in ("A02","A06","C10","C11"):
        with tarfile.open(ROOT/"archive"/(case+".tar.gz"),"r:gz") as tar:
            blocks={};plans={};certs={};index=None
            for obj in tar:
                if not obj.isfile():continue
                b=tar.extractfile(obj).read();name=obj.name
                if name=="events.json":index=json.loads(b)
                elif name.startswith("blocks/"):
                    raw=zlib.decompress(b);key=name.split("/")[1];assert sha(raw)==key;blocks[key]=raw
                elif name.endswith("/plan.json"):
                    key=name.split("/")[0];assert sha(b.strip())==key;plans[key]=json.loads(b)
                elif name.endswith("/certificate.json"):
                    key=name.split("/")[0];certs[key]=json.loads(b);assert certs[key]["plan_sha256"]==key
            assert set(plans)==set(certs)==set(index)
            for key,row in index.items():
                arr=b"".join(blocks[v] for v in row["blocks"])
                assert len(arr)==row["shape"][0]*31*8 and row["shape"][1]==31 and sha(arr)==row["hash"]
            count+=len(index)
            for method in "ABCDE":
                folder=ROOT/"archive/endpoints"/case/method
                key=sha((folder/"plan.json").read_bytes().strip())
                assert key in index and json.loads((folder/"certificate.json").read_bytes())["metrics"]==certs[key]["metrics"]
    print(json.dumps(dict(manifest_sources=source,manifest_archive=files,restored_traces=count)))
