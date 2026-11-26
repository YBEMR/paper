"""Pack each case's original certificates, event traces and search logs without loss."""
import argparse
import hashlib
import json
import tarfile
from pathlib import Path

def pack(data, dest):
    dest.mkdir(parents=True, exist_ok=True)
    manifests = []
    for case in sorted((data/"runs").iterdir()):
        assert len(list(case.glob("*/run.json"))) == 7
        evidence = data/"physical/evidence"/case.name
        def action_key(folder):
            plan = json.loads((folder/"plan.json").read_bytes())
            return bytes(k + (10 if u == 3 else 0) for u,k,t in plan["rows"][1::3])
        groups = [("certificates", [p/f for p in sorted(evidence.iterdir(),key=action_key)
                                    for f in ("plan.json","certificate.json","trace.npz")]),
                  ("search", sorted(p for p in case.rglob("*") if p.is_file()))]
        for tag, paths in groups:
            output = dest/f"{case.name}_{tag}.tar.xz"
            with tarfile.open(output, "w:xz", preset=5) as archive:
                for path in paths:
                    info = archive.gettarinfo(str(path),str(path.relative_to(data)))
                    info.mtime = info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    with path.open("rb") as stream:
                        archive.addfile(info, stream)
            with tarfile.open(output) as archive:
                for member, path in zip(archive, paths, strict=True):
                    assert member.name == str(path.relative_to(data))
                    assert archive.extractfile(member).read() == path.read_bytes()
            manifests.append(dict(file=output.name, members=len(paths), bytes=output.stat().st_size,
                                  sha256=hashlib.sha256(output.read_bytes()).hexdigest()))
            print(output.name, output.stat().st_size, flush=True)
    (dest/"manifest.json").write_text(json.dumps(manifests,indent=2)+"\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data",type=Path)
    parser.add_argument("destination",type=Path)
    args=parser.parse_args()
    pack(args.data,args.destination)
