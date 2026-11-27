"""Check external inputs against committed Git trees; materialize registration and incident evidence."""
import importlib.metadata
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from archive import HERE, OUT, RUNS, read, sha, write

def main():
    old=Path(os.environ["U3A_ARCHIVE"])
    sys.path.insert(0,str(old))
    from prepare_inputs import PINS,FILTERS,git_blob
    inputdir=Path(os.environ["U3A_INPUTS"])
    gitrepo=Path(sys.argv[1])
    dst=HERE/"registration"
    blobs=[]
    for name,ref in PINS.items():
        lines=subprocess.check_output(["git","-C",str(gitrepo),"ls-tree","-r",ref,"--","research"],encoding="utf8").splitlines()
        for line in lines:
            meta,path=line.split("\t",1)
            if re.match(FILTERS[name],path):
                b=(inputdir/name/path).read_bytes()
                digest=git_blob(b)
                assert digest==meta.split()[-1]
                blobs.append(dict(tree=name,path=path,git_blob=digest,sha256=sha(b)))
    write(dst/"frozen_sources.json",dict(pins=PINS,files=blobs))
    cases=read(old/"registration/cases.json")
    assert len(cases)==12
    write(dst/"cases.json",cases)
    for r in cases:
        b=(inputdir/"nt/research/m1i_generalization/registration/inputs"/r["input"]).read_bytes()
        assert sha(b)==r["input_sha256"] and b==(old/"registration/inputs"/r["input"]).read_bytes()
        f=dst/"inputs"/r["input"]
        f.parent.mkdir(exist_ok=True)
        f.write_bytes(b)
    incidents=[]
    for f in RUNS.glob("*/incident.json"):
        incidents.append(dict(label=f.parent.name,detail=read(f),start=read(f.parent/"start.json"),
            ready=read(f.parent/"ready.json"),files=sorted(p.name for p in f.parent.iterdir()),worker_log=(f.parent/"worker.log").read_text()))
    write(OUT/"incidents.json",incidents)
    write(dst/"environment.json",dict(packages={n:importlib.metadata.version(n) for n in ("numpy","numba","scipy","psutil")},
        registration_commit="1b11c4a3bdff2006a3b2926b6ff797250ec50ad1",
        first_scientific_worker_commit="0d579a8",affinity=[0],math_threads=1,inputs=len(cases),
        registered_wall_s=10,extra_replay_cap=14000,extra_cert_cap=8,terminal_cert_cap=12,
        dependency_cache="checked code and device template; no case plans or certification labels supplied to workers"))
if __name__=="__main__":
    main()
