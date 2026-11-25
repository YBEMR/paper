"""Pinned historical sources and pre-outcome sample selection for E2-c1-r."""
from pathlib import Path
import sys,subprocess,json,hashlib,gzip
ROOT=Path(__file__).resolve().parent
C=ROOT.parent/"domain_joint_optimization_e2c"
REPO=ROOT.parents[1]
BASE="b32f92114afc26fc90f86f2f6b74c4db6d2876bc"
BLOB="2d5f956a3f0e722e36b7c62c7adbbdcce047859b"
sys.path.insert(0,str(C))
from samples import read,write,digest

def git(*args):
    return subprocess.check_output(["git",*args],cwd=REPO)

def select_samples():
    assert git("rev-parse",BASE+":research/domain_joint_optimization_e2c/support.py").decode().strip()==BLOB
    assert git("hash-object",str(C/"support.py")).decode().strip()==BLOB
    m=read(C/"snapshot.json");historical=read(C/"samples.json")
    cases=[z for z in historical["cases"] if z["case"]=="D3" or z["id"] in ("D1_102_first","D2_103_last")]
    assert len(cases)==len({s["source"] for s in cases})==11
    files={}
    for rel in ["support.py","samples.py","structure.py","replay.py","audit.py","paired.csv","arms.csv","samples.json","structure.json","manifest.json"]:
        files[rel]=m["files"][rel]
    for z in cases:
        f="prestates/"+z["source"]+".json.gz";files[f]=m["files"][f]
        assert digest(gzip.decompress((C/f).read_bytes()))==z["source"]
        for method in ("Old","New"):
            f="replays/"+z["id"]+"/"+method+"/arm.json";files[f]=m["files"][f]
    for f,v in files.items():assert digest((C/f).read_bytes())==v
    write(ROOT/"samples.json",dict(base=BASE,support_blob=BLOB,cases=cases,files=files,structures=historical["structural"]))
if __name__=="__main__":select_samples()
