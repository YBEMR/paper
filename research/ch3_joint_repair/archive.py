"""Build lossless per-case archives; verify the original receipts against the stored bytes."""
import argparse
from collections import Counter
import hashlib
from io import BytesIO
import json
from pathlib import Path
import tarfile

from execute_study import CONFIG, HERE, JOBS, digest, dumps, folder, save


def read_unit(path):
    files={p.name:p.read_bytes() for p in path.iterdir() if p.is_file()}
    receipt=json.loads(files["receipt.json"])
    if set(files)-{"receipt.json"} != set(receipt["files"]):
        raise ValueError(f"Unexpected slot members in {path}")
    for name,expected in receipt["files"].items():
        if hashlib.sha256(files[name]).hexdigest()!=expected:
            raise ValueError(f"Corrupt {path/name}")
    return files,receipt


def archive(case,out):
    dest=out/(case+".tar")
    tmp=dest.with_suffix(".part")
    states=Counter()
    members={}
    with tarfile.open(tmp,"w",format=tarfile.USTAR_FORMAT) as tar:
        for job in (j for j in JOBS if j[0]==case):
            path=folder(job)
            files,receipt=read_unit(path)
            if receipt["job"]!=list(job):
                raise ValueError(f"Wrong slot {path}")
            states[receipt["state"]]+=1
            for name,data in sorted(files.items()):
                info=tarfile.TarInfo(path.name+"/"+name)
                info.size=len(data)
                info.mode=0o644
                tar.addfile(info,BytesIO(data))
                members[info.name]=hashlib.sha256(data).hexdigest()
    with tarfile.open(tmp) as tar:
        verified={m.name:hashlib.sha256(tar.extractfile(m).read()).hexdigest() for m in tar}
        if verified!=members or sum(states.values())!=15 or tmp.stat().st_size>=100*1024**2:
            raise ValueError(f"Archive verification failed: {case}")
    if dest.exists():
        if digest(tmp)!=digest(dest):
            raise FileExistsError(f"Existing archive differs: {dest}")
        tmp.unlink()
    else:
        tmp.rename(dest)
    return dict(case=case,file=dest.name,sha256=digest(dest),bytes=dest.stat().st_size,
                members=len(members),states=dict(states))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,default=HERE/"archives")
    args=p.parse_args()
    args.output.mkdir(exist_ok=True,parents=True)
    rows=[archive(c,args.output) for c in CONFIG["cases"]]
    save(args.output/"manifest.json",dict(base=CONFIG["base"],runs=len(JOBS),archives=rows))
    print(dumps({"verified_cases":len(rows),"runs":len(JOBS),"bytes":sum(r["bytes"] for r in rows)}))
