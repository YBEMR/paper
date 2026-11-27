"""Serial per case, parallel across preassigned physical cores, no repeats of completed units."""
import argparse
import csv
import ctypes
import gzip
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys
import time
from eventlog import records

HERE=Path(__file__).resolve().parent
ROOT=Path(os.environ["U4_RUNS"]).resolve()
OLD=Path(os.environ["U3B_SRC"])
read=lambda p:json.loads(p.read_bytes())
def put(p,obj):p.write_text(json.dumps(obj,sort_keys=True),encoding="utf8")
def events(d):
    for p in sorted(d.glob("journal-*.bin")):yield from records(p.read_bytes())
def first_seed(d):
    return next((r[1] for r in events(d) if r[0]=="delivered" and r[2]<=read(d/"receipt.json")["cap"]),None)
def evidence(d,key):
    paths=[p.parent for p in d.rglob("certificate.json") if p.parent.name==key]
    assert paths,key
    return paths[0]
def cores():
    # First hardware thread of each distinct processor core (Windows processor group zero).
    api=ctypes.windll.kernel32.GetLogicalProcessorInformationEx
    n=ctypes.c_ulong()
    api(0,None,ctypes.byref(n))
    b=ctypes.create_string_buffer(n.value);assert api(0,b,ctypes.byref(n))
    data=b.raw;offset=0;out=[]
    while offset<len(data):
        size=int.from_bytes(data[offset+4:offset+8],"little")
        mask=int.from_bytes(data[offset+32:offset+40],"little")
        assert size and mask
        out.append((mask & -mask).bit_length()-1)
        offset+=size
    return out[:4]

def unit(o,method,cpu,cap,seed=None):
    d=ROOT/(o["id"]+"-"+method)
    if (d/"receipt.json").exists():
        rec=read(d/"receipt.json")
        assert rec["status"] in ("natural","wall")
        return d
    d.mkdir(parents=True,exist_ok=False)
    cmd=[sys.executable,"-Bu",str(HERE/"experiment.py"),o["id"],method,str(d),str(cpu),str(cap)]
    if seed:cmd+=["--seed",str(seed)]
    launch=time.perf_counter()
    with (d/"log.txt").open("wb") as log:
        child=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT)
        start=None;killed=False
        while child.poll() is None:
            now=time.perf_counter()
            if start is None:
                try:start=read(d/"start.json")["start"]
                except (FileNotFoundError,PermissionError,json.JSONDecodeError):pass
            if start is not None and now>=start+cap:
                if not (d/"finish.json").exists():
                    child.kill();killed=True
                break
            if start is None and now-launch>150:child.kill();break
            time.sleep(.002)
        rc=child.wait()
    finish=read(d/"finish.json") if (d/"finish.json").exists() else {}
    status="wall" if killed or finish.get("wall_s",0)>cap else finish.get("status","error")
    if not killed and rc:status="error"
    rec=dict(case=o["id"],cohort=o["cohort"],method=method,cpu=cpu,cap=cap,status=status,rc=rc,external_kill=killed,
        process_s=time.perf_counter()-launch,finish=finish,seed=seed.name if seed else None)
    put(d/"receipt.json",rec)
    print(o["id"],method,status,round(rec["process_s"],2),flush=True)
    if status=="error":raise RuntimeError((d/"log.txt").read_text(errors="replace")[-1800:])
    return d

def main():
    p=argparse.ArgumentParser();p.add_argument("mode",choices=["gate","batch"]);args=p.parse_args()
    roster=read(HERE/"registration/cases.json")
    cpus=cores();ROOT.mkdir(exist_ok=True)
    put(ROOT/"affinity.json",cpus)
    if args.mode=="gate":
        rows=list(csv.DictReader((OLD/"tables/routes.csv").open(encoding="utf8")))
        for i,code in enumerate(("A06","C10","C11")):
            obj=next(o for o in roster if o["id"]==code)
            row=next(r for r in rows if r["case"]==code and int(r["repeat"])==1 and r["method"]==("ho" if code=="C10" else "terminal"))
            seed=OLD/"results/physical"/code/row["safe_plan"]
            for method in ("GateFixed","GateAdaptive"):
                d=unit(obj,method,cpus[i%len(cpus)],60,seed)
                ev=list(events(d))
                assert read(d/"receipt.json")["status"]=="natural" and first_seed(d)["plan"]==seed.name
                assert any(r[0]=="group_rounds" for r in ev)
        put(ROOT/"gate.json",dict(status="PASS",cells=6))
        return
    assert read(ROOT/"gate.json")["status"]=="PASS" and len(read(ROOT/"gate_verified.json"))==6
    def lane(index):
        for i in range(index,len(roster),len(cpus)):
            o=roster[i]
            arms=["Q4","Base","Ordinary","Previous","Source","NT10"]
            shift=i%len(arms)
            for m in arms[shift:]+arms[:shift]:unit(o,m,cpus[index],10)
            if o["cohort"]=="independent":unit(o,"NT60",cpus[index],60)
            for method in ("Source","Previous","Ordinary","Base","NT10"):
                d=ROOT/(o["id"]+"-"+method);seed=first_seed(d)
                if seed:
                    path=evidence(d,seed["plan"])
                    for arm in (("PairFixed","PairAdaptive") if i%2==0 else ("PairAdaptive","PairFixed")):unit(o,arm,cpus[index],10,path)
                    break
            else:put(ROOT/(o["id"]+"-no-shared-seed.json"),dict(reason="no causal SAFE within cap"))
    with ThreadPoolExecutor(max_workers=len(cpus)) as ex:
        list(ex.map(lane,range(len(cpus))))
if __name__=="__main__":main()
