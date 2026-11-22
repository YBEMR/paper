"""Package byte-exact original records in one deterministic TAR per condition."""
import hashlib
import io
import json
import tarfile
from run import CASES, CFG, HERE, JOBS, digest, folder, write


def pack(out):
    out.mkdir(exist_ok=True)
    entries = []
    for case in CASES:
        path = out/(case+".tar")
        tmp = path.with_suffix(".part")
        expected = {}
        with tarfile.open(tmp,"w",format=tarfile.USTAR_FORMAT) as tar:
            for job in [j for j in JOBS if j[0]==case]:
                source = folder(job)
                rec = json.loads((source/"receipt.json").read_bytes())
                assert rec["job"]==list(job) and set(rec["files"])|{"receipt.json"}=={p.name for p in source.iterdir()}
                for name in sorted([*rec["files"],"receipt.json"]):
                    data = (source/name).read_bytes()
                    sha = hashlib.sha256(data).hexdigest()
                    assert name=="receipt.json" or sha==rec["files"][name]
                    info = tarfile.TarInfo(source.name+"/"+name)
                    info.size = len(data)
                    tar.addfile(info,io.BytesIO(data))
                    expected[info.name] = sha
        with tarfile.open(tmp) as tar:
            assert {m.name:hashlib.sha256(tar.extractfile(m).read()).hexdigest() for m in tar}==expected
        assert tmp.stat().st_size<100*1024**2
        if path.exists() and digest(tmp)!=digest(path):
            raise RuntimeError(f"Different case archive already exists: {case}")
        tmp.replace(path)
        entries.append(dict(case=case,file=path.name,bytes=path.stat().st_size,sha256=digest(path),members=len(expected)))
    write(out/"manifest.json",dict(subject=CFG["base"],runs=len(JOBS),archives=entries))


if __name__=="__main__":
    pack(HERE/"archives")
