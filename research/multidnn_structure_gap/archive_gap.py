"""Manifest for only Git-eligible task artifacts; ignored PDFs never bypass policy."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
PREFIX=HERE.relative_to(ROOT).as_posix()+"/"
TARGET=HERE/"archive_manifest.json"

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main(check):
    files=subprocess.check_output(["git","ls-files","--cached","--others","--exclude-standard",PREFIX],cwd=ROOT,text=True).splitlines()
    files=sorted(set(files)-{TARGET.relative_to(ROOT).as_posix()})
    assert files and all(p.startswith(PREFIX) for p in files)
    entries={p:dict(sha256=sha(ROOT/p),bytes=(ROOT/p).stat().st_size) for p in files}
    if check:
        old=json.loads(TARGET.read_bytes());assert old["files"]==entries
        print("archive manifest PASS:",len(entries),"files")
    else:
        data=dict(scope="all tracked or non-ignored artifacts in this study only",files=entries,
                  execution_commit=json.loads((HERE/"environment.json").read_bytes())["execution_commit"])
        TARGET.write_bytes((json.dumps(data,indent=2)+"\n").encode())
        print("archived",len(entries),"files",sum(v["bytes"] for v in entries.values()),"bytes")
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--check",action="store_true");a=p.parse_args();main(a.check)
