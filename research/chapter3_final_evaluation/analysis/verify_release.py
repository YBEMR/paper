"""Verify publication completeness without importing a solver or launching a formal job."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[1]


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    return json.loads(p.read_bytes())


def git(*args,**kwargs):
    return subprocess.check_output(["git","-C",str(REPO),*args],**kwargs)


def verify():
    acceptance=read(ROOT/"acceptance.json")
    assert acceptance["physical_cells"]==165 and acceptance["logical_positions"]==174 and acceptance["figures"]==9
    assert read(ROOT/"formal"/"batch_end.json")["outcome"]=="FINISHED"
    paths=[]
    for name,h in acceptance["artifacts"].items():
        p=(ROOT/name).resolve()
        if not p.is_file() or not any(p.is_relative_to(ROOT/d) for d in ("archive","results")) or digest(p)!=h:
            raise ValueError(name)
        paths.append(p)
    for d in ("results","archive"):
        assert {p.resolve() for p in (ROOT/d).rglob("*") if p.is_file()}=={p for p in paths if p.is_relative_to(ROOT/d)}
    with (ROOT/"results"/"logical_positions.csv").open(encoding="utf8",newline="") as f:
        logical=list(csv.DictReader(f))
    assert len(logical)==174 and len({r["id"] for r in logical})==165 and sum(r["reused"]=="1" for r in logical)==9
    for i in range(1,10):
        figs=ROOT/"results"/"figures"
        svg,=figs.glob(f"{i:02}_*.svg")
        png,=figs.glob(f"{i:02}_*.png")
        assert ET.parse(svg).getroot().tag.endswith("}svg") and png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert list(figs.glob(f"{i:02}_*.csv"))
    return sorted([*paths,ROOT/"acceptance.json"])


def commit(paths):
    if (git("branch","--show-current").strip()!=b"codex/chapter3-final-evaluation" or
            git("remote","get-url","origin").strip()!=b"https://github.com/YBEMR/paper.git"):
        raise RuntimeError("Unexpected publication target")
    if git("diff","--cached","--name-only").strip():
        raise RuntimeError("Index already contains a staged change")
    # Only enumerated and hash-verified release files are eligible for this commit.
    names=[p.relative_to(REPO).as_posix() for p in paths]
    payload=b"\0".join(n.encode("utf8") for n in names)+b"\0"
    git("add","--pathspec-from-file=-","--pathspec-file-nul",input=payload)
    staged=set(git("diff","--cached","--name-only","-z").decode().split("\0"))-{""}
    if not staged.issubset(set(names)):
        raise RuntimeError("Index drift")
    if staged:
        git("commit","-m","Archive the final chapter 3 batch, nine figures and audited Chinese results")
    print(git("rev-parse","HEAD").decode().strip(),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--commit",action="store_true")
    args=parser.parse_args()
    files=verify()
    if args.commit:
        commit(files)
    else:
        print(f"Verified {len(files)} release files")
