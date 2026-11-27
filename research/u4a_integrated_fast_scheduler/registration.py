"""Outcome-blind roster, fixed physical inputs and historical exclusions."""
import csv
import hashlib
import io
import itertools
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
REG=HERE/"registration"
ROOT=Path(os.environ["U3A_INPUTS"])
OLD=Path(os.environ["U3B_SRC"])
REPO=Path(os.environ["U4_HISTORY"])
def raw(v):return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw(v)+b"\n")
def table(rows):
    buf=io.StringIO(newline="")
    w=csv.DictWriter(buf,fieldnames=rows[0],lineterminator="\n");w.writeheader();w.writerows(rows)
    return buf.getvalue().encode()
def git(*args):return subprocess.check_output(["git","-C",str(REPO),*args])
def main():
    reg=ROOT/"nt/research/m1i_generalization/registration"
    old=json.loads((reg/"cases.json").read_bytes())["cases"]
    indexes=json.loads((OLD/"registration/frozen_sources.json").read_bytes())
    for f in indexes["files"]:
        b=(ROOT/f["tree"]/f["path"]).read_bytes()
        assert sha(b)==f["sha256"]
    hist=list(csv.DictReader(io.StringIO(git("show","b95570f9:research/m1i_generalization/registration/history.csv").decode())))
    words={r["word"] for r in [*hist,*old]}
    traffic={r["traffic_sha256"] for r in [*hist,*old]}
    hashes={r["input_sha256"] for r in old}|{r["source_sha256"] for r in hist}
    scans={}
    for ref in ("b95570f9","96a13920","c9aa84bc","be641ce0","origin/main","origin/research/m5a-mixed-frequency-quota","origin/codex/chapter4-cross-analysis-v5"):
        paths=git("ls-tree","-r","--name-only",ref,"--","research").decode()
        found=set(re.findall(r"(?<![A-Z])([LH]{3,})(?![A-Z])",paths))
        scans[git("rev-parse",ref).decode().strip()]=sorted(found)
        words.update(found)
    sys.path.insert(0,str(ROOT/"four/research/chapter4_cross_analysis_v5/formal_runner/v1/p1"))
    from profiles import requests,CFG
    out=[]
    for obj in old:
        if obj["ambient"]==35:
            o=dict(obj,cohort="development",id=obj["case"].split("_")[0])
            out.append(o)
            (REG/"inputs").mkdir(parents=True,exist_ok=True)
            (REG/"inputs"/o["input"]).write_bytes((reg/"inputs"/o["input"]).read_bytes())
    old_words=sorted(words)
    for i,(group,n,h,start) in enumerate([(g,n,h,s) for g,n,hs in (("regular",8,(4,4)),("regular",10,(5,5)),("unequal",9,(3,6)),("unequal",11,(7,4)),("long",14,(7,7)),("long",18,(9,9))) for h,s in zip(hs,"LH")],1):
        pool=[]
        for comb in itertools.combinations(range(n),h):
            w="".join("H" if j in comb else "L" for j in range(n))
            if w[0]==start and w not in words:pool.append((sha(("U4-a/785cbcf/v1/"+w).encode()),w))
        for key,w in sorted(pool):
            code=f"I{i:02d}";label=f"{code}_{w}_T35"
            CFG["instances"][label]=[list(w),1,35,1]
            rows=requests(label);b=table(rows)
            norm=[tuple(str(r[k]) for k in ("stream","kind","release_tick","deadline_tick")) for r in rows]
            th=sha(json.dumps(norm,separators=(",",":")).encode())
            if sha(b) not in hashes and th not in traffic:break
        else:raise RuntimeError("stratum exhausted")
        assert all(r["deadline_ms"]-r["release_ms"]==300 for r in rows)
        assert len(rows)==w.count("L")*60+w.count("H")*100
        name=label+".csv";(REG/"inputs"/name).write_bytes(b)
        out.append(dict(cohort="independent",group=group,id=code,case=label,input=name,word=w,ambient=35,
            windows=n,requests=len(rows),horizon_ticks=10000*n+3010,input_sha256=sha(b),traffic_sha256=th,selection_sha256=key))
        words.add(w);hashes.add(sha(b));traffic.add(th)
    assert len(out)==len({o["word"] for o in out})==len({o["traffic_sha256"] for o in out})==24
    put(REG/"cases.json",out);put(REG/"history.json",dict(prior_registration=hist,scanned=scans,excluded_words=old_words))
    put(REG/"source_check.json",dict(pins=indexes["pins"],verified_files=len(indexes["files"]),reference_sha256=sha((OLD/"registration/frozen_sources.json").read_bytes())))
if __name__=="__main__":main()
