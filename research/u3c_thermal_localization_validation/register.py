"""Freeze both cohorts without building or certifying any schedule."""
import csv
import hashlib
import itertools
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PARENT = "785cbcf78f17a48cd23567251418f8ef4a59e55c"
OLD = HERE.parent / "u3b_blockage_triggered_quota"
REG = HERE / "registration"
INPUTS = Path(os.environ["U3A_INPUTS"]).resolve()
NT = INPUTS / "nt/research"
sys.path.insert(0, str(NT / "m1i_generalization"))
sys.path.insert(0, str(NT / "m1_transient_thermal_quota_20261126/frozen/p1"))
from design import BASE, csv_bytes, sha
from profiles import CFG, requests


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2)+"\n").encode())


def register():
    old_manifest = json.loads((OLD / "registration/frozen_sources.json").read_bytes())
    for item in old_manifest["files"]:
        body = (INPUTS / item["tree"] / item["path"]).read_bytes()
        assert sha(body) == item["sha256"], item
    history = list(csv.DictReader(git("show", PARENT+":research/m1i_generalization/registration/history.csv").decode().splitlines()))
    excluded = {e["word"] for e in history}
    raw_hashes = {e["source_sha256"] for e in history}
    streams = {e["traffic_sha256"] for e in history}
    roots = [OLD/"registration/cases.json", NT/"m1i_generalization/registration/cases.json"]
    for file in roots:
        items = json.loads(file.read_bytes())
        for r in items if isinstance(items, list) else items["cases"]:
            excluded.add(r["word"])
            raw_hashes.add(r["input_sha256"])
            streams.add(r["traffic_sha256"])
    paths = git("ls-tree","-r","--name-only",PARENT,"research").decode()
    excluded.update(re.findall(r"(?<![A-Za-z])([LH]{4,})(?![A-Za-z])", paths))
    write_json(REG/"exclusions.json", dict(parent=PARENT, words=sorted(excluded),
               input_sha256=sorted(raw_hashes), traffic_sha256=sorted(streams), prior_records=history))
    strata = [(n//2,n//2,s) for n in (6,8,10) for s in "LH"]
    strata += [(5,3,""),(3,5,"")] + [(n//2,n//2,s) for n in (12,16) for s in "LH"]
    selected = []
    for nL,nH,first in strata:
        n = nL+nH
        words = []
        for places in itertools.combinations(range(n),nH):
            word = "".join("H" if i in places else "L" for i in range(n))
            if word.startswith(first) and word not in excluded:
                h = sha(f"M1-i/{BASE}/v1/{nL}/{nH}/{word}".encode())
                words.append((h,word))
        assert len(words)>=4,(nL,nH,first,len(words))
        selected.append(sorted(words)[:4])
    cases = []
    (REG/"inputs").mkdir(parents=True,exist_ok=True)
    for wave in (1,2):
        for s,choices in enumerate(selected):
            for h,w in choices[(wave-1)*2:wave*2]:
                idx = len(cases)
                tag = f"N{idx+1:02d}"
                label = f"{tag}_{w}_T35"
                CFG["instances"][label] = [list(w),1,35,1]
                rows = requests(label)
                body = csv_bytes(rows)
                traffic = [tuple(str(r[k]) for k in ("stream","kind","release_tick","deadline_tick")) for r in rows]
                th = sha(json.dumps(traffic,separators=(",",":")).encode())
                assert sha(body) not in raw_hashes and th not in streams and w not in excluded
                raw_hashes.add(sha(body)); streams.add(th); excluded.add(w)
                name = f"{tag}_{w}.csv"
                (REG/"inputs"/name).write_bytes(body)
                cases.append(dict(case=label,tag=tag,index=idx,batch=wave,stratum=s+1,
                        word=w,ambient=35,input=name,input_sha256=sha(body),traffic_sha256=th,
                        requests=len(rows),windows=len(w),horizon_ticks=len(w)*10000+3010,selection_sha256=h))
    write_json(REG/"cases.json", cases)
    write_json(REG/"seal.json", dict(cases_sha256=sha((REG/"cases.json").read_bytes()),
               exclusions_sha256=sha((REG/"exclusions.json").read_bytes()),protocol_sha256=sha((HERE/"PROTOCOL.md").read_bytes()),
               frozen_files=len(old_manifest["files"]),old_manifest_sha256=sha((OLD/"registration/frozen_sources.json").read_bytes())))
    print(len(cases),"sealed, sources checked",len(old_manifest["files"]))

if __name__ == "__main__":
    register()
