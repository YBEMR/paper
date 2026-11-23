"""Manifest of this experiment only; hashes all raw data and derived artifacts."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
DEST=HERE/"artifact_manifest.json"
def digest(p):
    return sha256(p.read_bytes()).hexdigest()
def included():
    names=subprocess.check_output(["git","ls-files","--cached","--others","--exclude-standard","--",
                                  HERE.relative_to(ROOT).as_posix()],cwd=ROOT,text=True).splitlines()
    return sorted({ROOT/name for name in names if ROOT/name!=DEST})
def main(check):
    if check:
        data=json.loads(DEST.read_bytes())
        for relative,expected in data["sha256"].items():
            assert digest(ROOT/relative)==expected,relative
        actual={p.relative_to(ROOT).as_posix() for p in included()}
        assert actual==set(data["sha256"])
        print("PASS",len(actual),"artifact hashes")
        return
    verification=json.loads((HERE/"verification.json").read_bytes())
    assert verification["status"]=="PASS" and verification["counts"]["runs"]==72
    assert not list((HERE/"raw").rglob("*.jsonl")),"uncompressed unfinished run"
    paths=included()
    data=dict(execution_commit=json.loads((HERE/"environment.json").read_bytes())["execution_commit"],
              source_reference="45b14f99bdb9324eedd6469609400a4ee92ed656",
              files=len(paths),bytes=sum(p.stat().st_size for p in paths),
              sha256={p.relative_to(ROOT).as_posix():digest(p) for p in paths})
    DEST.write_text(json.dumps(data,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(len(paths),"files;",data["bytes"],"bytes")
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--verify",action="store_true")
    main(parser.parse_args().verify)
