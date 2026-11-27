"""Preserve complete candidate journals, accepted plans and certificates in Git."""
import csv
import hashlib
import json
import os
import signal
import tarfile
import time
import zipfile
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parent
tables=ROOT/"tables"
dst=ROOT/"evidence"

def digest(file):
    with file.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()

def run(artifact):
    start=time.monotonic()
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    signal.alarm(145)
    assert digest(artifact)=="86b283d5b9c3126733093cfb851b41963b2ae98d44ae3a46037c188ac6400a8f"
    with (tables/"certifications.csv").open() as f:
        accepted={(r["case"],r["arm"],r["plan"]) for r in csv.DictReader(f)}
    with (tables/"results.csv").open() as f:
        winners={(r["case"],r["arm"],r["plan"]) for r in csv.DictReader(f) if r["plan"]}
    assert len(accepted)==3017
    groups=defaultdict(list)
    held=defaultdict(set)
    with zipfile.ZipFile(artifact) as source:
        for entry in source.infolist():
            if entry.is_dir():continue
            p=Path(entry.filename)
            assert not p.is_absolute() and ".." not in p.parts
            parts=p.parts
            if parts[0]=="formal":
                _,case,arm=parts[:3]
                group=case+"-"+arm
                if "evidence" in parts:
                    key=case,arm,parts[-2]
                    if key not in accepted or (p.name=="trace.npz" and key not in winners):
                        continue
                    held[key].add(p.name)
                elif p.name not in ("candidates.jsonl","journal.jsonl","receipt.json","run.json"):
                    continue
            elif parts[0] in ("gate","offline"):
                group=parts[0]
                if p.name=="trace.npz" and group=="gate":continue
            else:continue
            groups[group].append(entry)
        assert set(held)==accepted and all({"plan.json","certificate.json"}<=files for files in held.values())
        assert all("trace.npz" in held[k] for k in winners)
        dst.mkdir(exist_ok=False)
        manifest={}
        for group,entries in sorted(groups.items()):
            outfile=dst/(group+".tar.gz")
            names={}
            with tarfile.open(outfile,"w:gz",compresslevel=4) as out:
                for entry in sorted(entries,key=lambda e:e.filename):
                    info=tarfile.TarInfo(entry.filename)
                    info.size=entry.file_size
                    with source.open(entry) as f:out.addfile(info,f)
                    names[entry.filename]=entry.CRC
            # Read the output back through gzip and compare every member's CRC
            # with the immutable source archive whose SHA-256 was verified above.
            import zlib
            with tarfile.open(outfile,"r|gz") as out:
                for ent in out:
                    crc=0
                    f=out.extractfile(ent)
                    for block in iter(lambda:f.read(262144),b""):crc=zlib.crc32(block,crc)
                    assert crc==names.pop(ent.name)
            assert not names and outfile.stat().st_size<90*1024*1024
            manifest[outfile.name]=dict(files=len(entries),bytes=outfile.stat().st_size,sha256=digest(outfile))
    elapsed=time.monotonic()-start
    (dst/"manifest.json").write_text(json.dumps(dict(source_run=46011228003,artifact_sha256=digest_string,
        accepted_certificates=len(accepted),selected_trace_paths=len(winners),files=manifest,
        verification="All members read back and compared to source CRC32; source and packages SHA-256",
        elapsed_single_core_s=elapsed,limit_s=145),indent=2)+"\n")
    signal.alarm(0)
if __name__=="__main__":
    import sys
    digest_string="86b283d5b9c3126733093cfb851b41963b2ae98d44ae3a46037c188ac6400a8f"
    run(Path(sys.argv[1]))

