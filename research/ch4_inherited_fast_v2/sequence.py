"""Recover only delivered candidates in order. Keep archive answers outside the evaluator."""
import gzip
import hashlib
import json
import tarfile
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIRST = HERE.parent/"ch4_inherited_fast_v1"
CASES = ("A01","A05","C10","C12")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def recover(case):
    root = FIRST/"results"/case
    folder = root/"r1-O-20"
    ordered = []
    for stage in ("search","refine"):
        for line in gzip.decompress((folder/(stage+".jsonl.gz")).read_bytes()).splitlines():
            if not line.endswith(b"}"):
                continue
            event = json.loads(line)
            if event["event"] == "certificate" and event["t"] <= 20:
                ordered.append((event["t"],stage,event["point"]["plan"],event.get("stage")))
    ordered.sort()
    assert len(ordered) == dict(zip(CASES,(59,44,30,15)))[case]
    ix = json.loads((root/"physical/index.json").read_bytes())["plans"]
    keys = {key for _,_,key,_ in ordered}
    cfg, truth = {}, {k:{"trace":ix[k]["trace_sha"]} for k in keys}
    for filename in {ix[key]["archive"] for key in keys}:
        with tarfile.open(root/"physical"/filename,"r|") as archive:
            for member in archive:
                key, kind = member.name.split("/")
                if key not in keys:
                    continue
                data = zlib.decompress(archive.extractfile(member).read())
                if kind == "plan":
                    assert sha(data.strip()) == key
                    cfg[key] = tuple(tuple(row[:2]) for row in json.loads(data)["rows"][1::3])
                elif kind == "certificate":
                    assert sha(data) == ix[key]["cert_sha"]
                    d = json.loads(data)
                    del d["cert_s"]
                    truth[key]["certificate"] = sha(json.dumps(d,sort_keys=True,separators=(",",":")).encode())
    return ordered, cfg, truth
