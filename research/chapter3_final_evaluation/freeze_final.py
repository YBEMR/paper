"""Freeze the tested implementation, receipt archive and explicit roster before starting jobs."""
import hashlib
import io
import json
import os
import platform
import subprocess
import sys
import tarfile
from importlib.metadata import version
from formal_batch import ROOT, roster, write, read, sha
from setup_inputs import G1, G2, g1io


def main():
    target=ROOT/"execution_lock.json"
    if target.exists() or (ROOT/"formal").exists():
        raise FileExistsError("Execution lock or formal batch already exists")
    pf=ROOT/"preflight"/"attempt01"
    gate=read(pf/"passed.json")
    assert gate["status"]=="PASS" and gate["case"]=="S16" and gate["runs"]==11
    parameters=read(pf/"calibration.json")["parameters"]
    repo=ROOT.parents[1]
    env=read(G1/"input_lock.json")
    for name,h in env["solver_runtime_files"]:
        assert sha(g1io.runtime/name)==h,name
    upstream=read(G2/"formal_lock.json")
    for name,h in upstream["files"].items():
        assert sha(G2/name)==h,name
    for row in env["upstream"]:
        if "/instances/" not in row["path"] or row["path"].endswith(("/D1.csv","/D2.csv")):
            assert sha(repo/row["path"])==row["sha256"],row["path"]
    assets={p:sha(p) for p in (G2/"formal_lock.json",G1/"input_lock.json")}
    for folder in (G1,G2,ROOT.parent/"cross_scene_taskflow_diagnostic",ROOT.parent/"domain_joint_optimization_e0_e1",
                   ROOT.parent/"domain_joint_optimization_e2a"):
        for p in folder.glob("*.py"):
            source=subprocess.check_output(["git","-C",str(repo),"show",f"9e8f7f4a:{p.relative_to(repo).as_posix()}"])
            assert hashlib.sha256(source).hexdigest()==sha(p),p
            assets[p]=sha(p)
    for row in env["upstream"]:
        if "/config/" in row["path"]:
            assets[repo/row["path"]]=row["sha256"]
    archive=ROOT/"preflight_s16.tar.xz"
    with tarfile.open(archive,"w:xz") as tar:
        for p in sorted(pf.rglob("*")):
            if p.is_file():
                raw=p.read_bytes()
                info=tarfile.TarInfo(p.relative_to(pf).as_posix())
                info.size=len(raw)
                tar.addfile(info,io.BytesIO(raw))
    with tarfile.open(archive,"r:xz") as tar:
        for info in tar:
            assert tar.extractfile(info).read()==(pf/info.name).read_bytes()
    files=[*ROOT.glob("*.py"),ROOT/"inputs.json",ROOT/"PROTOCOL.md",archive,*sorted((ROOT/"instances").glob("*.csv"))]
    hashes={os.path.relpath(p,ROOT).replace(os.sep,"/"):sha(p) for p in files}
    hashes.update({os.path.relpath(p,ROOT).replace(os.sep,"/"):h for p,h in assets.items()})
    write(target,dict(input_commit="65e05c6ee456db440f5718decbcbd7b1c8e5f90a",files=hashes,parameters=parameters,
          preflight=gate,environment=dict(platform=platform.platform(),python=sys.version,
          packages={n:version(n) for n in ("numpy","numba","scipy","ortools","psutil","sympy")}),roster=roster()))


if __name__=="__main__":
    main()

