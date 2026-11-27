"""Register first trials, preserve receipts, rotate repeats and enforce the hard deadline."""
import gzip
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from location import simple

HERE=Path(__file__).resolve().parent
OLD=HERE.parent/"u3b_blockage_triggered_quota"
OUT=Path(os.environ["U3B_RUNS"]).resolve()
METHODS=["slack","peak","previous","energy","heat"]

def read(p):
    return json.loads(p.read_bytes())

def write(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(".tmp")
    tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf8")
    tmp.replace(p)

def marker(p):
    try:
        return read(p)
    except (PermissionError,FileNotFoundError):
        return {}

def run(tag,method,repeat):
    folder=OUT/f"{tag}-{method}-{repeat}"
    receipt=folder/"receipt.json"
    if receipt.is_file():
        rec=read(receipt)
        if rec["status"]=="ERROR":
            raise RuntimeError(str(folder))
        return rec
    folder.mkdir(parents=True,exist_ok=False)
    before=time.perf_counter()
    logical=None
    with (folder/"worker.log").open("wb") as log:
        proc=subprocess.Popen([sys.executable,"-B",str(HERE/"online.py"),str(folder),tag,method],
                              stdout=log,stderr=subprocess.STDOUT)
        while True:
            if logical is None:
                logical=marker(folder/"start.json").get("clock")
            if (folder/"finish.json").exists() or proc.poll() is not None:
                break
            now=time.perf_counter()
            if logical is not None and now-logical>=10 or logical is None and now-before>120:
                proc.kill()
                break
            time.sleep(.003)
        code=proc.wait(timeout=30)
    duration=time.perf_counter()-before
    finish=marker(folder/"finish.json")
    delivery=marker(folder/"delivery.json")
    wall=finish.get("wall_s")
    if wall is not None and wall<=10 and delivery and code==0:
        status=delivery["status"]
    elif logical is not None and time.perf_counter()-logical>=10:
        status="WALL"
    else:
        status="ERROR"
    rec=dict(case=tag,method=method,repeat=repeat,status=status,cap_s=10,wall_s=wall,
             process_wall_s=duration,exit_code=code)
    write(receipt,rec)
    print(tag,method,repeat,status,wall,flush=True)
    if status=="ERROR":
        raise RuntimeError((folder/"worker.log").read_text(errors="replace"))
    return rec

def old_development():
    units={}
    for tag in ("oo","ho"):
        p=OLD/f"results/runs/online-C10-{tag}-r1.json"
        u=read(p)
        units[u["location"]["selected_w"]]=(p,u)
    obs=units[4][1]["location"]
    raw=int(obs["heat"]["peak_tick"]//10000)
    keys=obs["ordinary_keys"]
    rows=[]
    for m in METHODS:
        w=obs["selected_w"] if m=="heat" else 1+simple(m,len(keys),raw,keys)
        row=dict(method=m,selected_w=w)
        if w in units:
            path,u=units[w]
            loc=u["location"]
            assert loc["selected_w"]==w
            attempts=u["delivery"]["attempts"]
            pools={}
            for stage in u["delivery"]["stages"]:
                s=stage["stage"]
                source=u["parts"][s+"-pool"]
                pool=json.loads(gzip.decompress((OLD/source).read_bytes()))
                assert all(r["prediction"] is None for r in pool["ranking"])
                pools[s]=dict(source=source,digest=pool["common_digest"],size=pool["size"])
            row.update(kind="read_only_equivalence",source=path.relative_to(OLD).as_posix(),
                anchor=attempts[0]["plan"],status=u["receipt"]["status"],pools=pools,
                local_plans=[a["plan"] for a in attempts if a["stage"]!="terminal"])
        else:
            row.update(kind="new_paid_route",receipt=run("C10",m,1))
        rows.append(row)
    write(OUT/"development.json",rows)

def screen(batch):
    rows=[]
    for obj in batch:
        tag=obj["tag"]
        rec=run(tag,"terminal",1)
        if rec["status"]=="HOT":
            base=read(OUT/f"{tag}-terminal-1/base.json")
            tries=read(OUT/f"{tag}-terminal-1/delivery.json")["attempts"]
            assert 0<len(tries)==len(base["top"])<=12 and all(a["status"]=="HOT" for a in tries)
            rows.append(obj)
    return rows

def main():
    cases=read(HERE/"registration/cases.json")
    seal=read(HERE/"registration/seal.json")
    for p,h in [(HERE/"PROTOCOL.md",seal["protocol_sha256"]),(HERE/"registration/cases.json",seal["cases_sha256"])]:
        assert hashlib.sha256(p.read_bytes()).hexdigest()==h
    assert all(hashlib.sha256((HERE/"registration/inputs"/c["input"]).read_bytes()).hexdigest()==c["input_sha256"] for c in cases)
    old_development()
    first=screen(cases[:24])
    expand=len(first)<4
    write(OUT/"expansion.json",dict(first_trigger=[r["tag"] for r in first],threshold=4,expand=expand))
    triggers=first+(screen(cases[24:]) if expand else [])
    for obj in triggers:
        for repeat in (1,2,3):
            k=(obj["index"]+repeat-1)%5
            results=[run(obj["tag"],m,repeat) for m in METHODS[k:]+METHODS[:k]]
            if repeat==1 and all(r["status"]!="SAFE" for r in results):
                break

if __name__=="__main__":
    main()
