"""Lossless, content-indexed archive and route accounting. No online result is computed here."""
import argparse
from collections import Counter,defaultdict
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import zipfile
import zlib
import numpy as np
import psutil
from batch_control import HERE,ROOT,events,read

DEST=HERE/"results"
def raw(x):
    return json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False,default=lambda v:v.hex() if isinstance(v,bytes) else v.item()).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def put(path,v):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw(v)+b"\n")
def zipped(path,b):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(gzip.compress(b,compresslevel=5,mtime=0))
def keep_part(case,data):
    body=bytes(data)
    rel="journals/"+sha(body)+".jsonl.gz";p=DEST/case/rel
    if not p.exists():zipped(p,body)
    return rel
class Physics:
    def __init__(self,case):
        self.base=DEST/case/"physical"
        self.base.mkdir(parents=True,exist_ok=True)
        self.index={};self.plans={};self.parts=[];self.buf=bytearray()
    def flush(self):
        if self.buf:
            name="events-%03d.bin"%len(self.parts);(self.base/name).write_bytes(self.buf)
            self.parts.append(dict(name=name,bytes=len(self.buf),sha256=sha(self.buf)));self.buf.clear()
    def add(self,folder,obj):
        key=folder.name
        plan=read(folder/"plan.json");cert=read(folder/"certificate.json")
        assert sha(raw(plan))==key==cert["plan_sha256"] and plan["case"]==obj["case"]
        assert len(plan["rows"])==3*obj["requests"]
        with np.load(folder/"trace.npz",allow_pickle=False) as a:tr=a["events"]
        ts=sha(tr.tobytes())
        m=cert["metrics"];lim=m["E_bounds"]
        assert tr.shape[1]==31 and tr.dtype==np.dtype("<f8") and tr[0,0]==0 and tr[-1,1]==obj["horizon_ticks"]
        assert np.all(tr[:,1]>tr[:,0]) and np.array_equal(tr[:-1,1],tr[1:,0]) and np.array_equal(tr[:-1,18:22],tr[1:,14:18])
        ej=float(tr[:,26:30].sum()+.3*tr[-1,1]/10000)
        assert lim[0]<=ej<=lim[1] and lim[0]<=m["E_J"]<=lim[1]
        assert abs(tr[:,22:26].max()-max(m["peak_hi"]))<1e-7 and m["min_deadline_slack_ms"]>=0
        if m["status"]=="SAFE":assert max(m["peak_hi"])<=80
        if m["status"]=="HOT":assert max(m["peak_lo"])>80
        if key in self.plans:
            prev=self.plans[key]
            assert prev["trace_sha256"]==ts and prev["certificate"]["metrics"]==m
            return
        blocks=[]
        for seg in np.split(tr,np.searchsorted(tr[:,0],np.arange(10000,tr[-1,1],10000))):
            data=seg.tobytes();h=sha(data);blocks.append(h)
            if h not in self.index:
                b=zlib.compress(data,5)
                if len(self.buf)+len(b)>8*1024*1024:self.flush()
                self.index[h]=[len(self.parts),len(self.buf),len(b)]
                self.buf.extend(b)
        self.plans[key]=dict(plan=plan,certificate=cert,trace_sha256=ts,shape=tr.shape,blocks=blocks)
    def close(self):
        self.flush()
        zipped(self.base/"plans.jsonl.gz",b"".join(raw(v)+b"\n" for _,v in sorted(self.plans.items())))
        zipped(self.base/"block-index.json.gz",raw(self.index))
        put(self.base/"manifest.json",dict(parts=self.parts,plans=len(self.plans),blocks=len(self.index)))

def pack_unit(folder,physics,obj):
    rec=read(folder/"receipt.json");cap=rec["cap"];case=rec["case"]
    assert rec["status"] in ("wall","natural")
    duration=cap if rec["status"]=="wall" else rec["finish"]["wall_s"]
    counts=Counter();stages=defaultdict(float);begins={};choices=Counter()
    deliveries=[];certs=[];phaseinfo={};chunks=[];data=bytearray();replays=0;begun=0
    for r in events(folder):
        kind=r[0];counts[kind]+=1
        data.extend(raw(r)+b"\n")
        if len(data)>4*1024*1024:chunks.append(keep_part(case,data));data.clear()
        if kind=="begin":
            begins[r[1]]=min(r[2],cap)
            if r[1]=="fallback":phaseinfo["fallback"]=True
        elif kind=="end":
            stages[r[1]]+=max(0,min(r[2],cap)-begins.pop(r[1]))
        elif kind=="cert_start" and r[3]<=cap:begun+=1
        elif kind=="cert" and r[1]["t"]<=cap:
            certs.append(r[1])
            if r[1]["phase"]=="handoff":begun+=1
        elif kind=="delivered" and r[2]<=cap:
            assert r[1]["status"]=="SAFE" and (not deliveries or r[1]["bounds"][1]<deliveries[-1]["bounds"][0])
            deliveries.append(dict(r[1],t=r[2]))
        elif kind=="choice":choices[r[1]]+=1
        elif kind=="q4_action" and ("repair" in begins):replays+=1
        elif kind=="store" and r[1]=="location":phaseinfo["location"]=r[2]
        elif kind=="store" and r[1]=="base":
            b=r[2];phaseinfo["terminal_generated"]=len(b["terminal"]) if "terminal" in b else None
        elif kind=="group_seed":phaseinfo["group_seed"]=r[1]
    if data:chunks.append(keep_part(case,data))
    for phase,start in begins.items():stages[phase]+=max(0,duration-start)
    assert sum(stages.values())<=cap+.01
    expected={r["plan"] for r in certs}|{r["plan"] for r in deliveries}
    found=set();partial=[]
    for ep in folder.rglob("plan.json"):
        e=ep.parent
        try:physics.add(e,obj);found.add(e.name)
        except (OSError,ValueError,EOFError,KeyError,zipfile.BadZipFile) as exc:
            if e.name in expected or rec["status"]!="wall":raise
            partial.append(dict(plan=e.name,files={f.name:sha(f.read_bytes()) for f in e.iterdir() if f.is_file()},reason=type(exc).__name__))
    assert expected<=found,expected-found
    for c in certs:
        m=physics.plans[c["plan"]]["certificate"]["metrics"]
        assert (m["E_J"],m["status"],m["E_bounds"])==(c["J"],c["status"],c["bounds"])
    summary=dict(receipt=rec,warm=read(folder/"ready.json"),journal=chunks,counts=dict(counts),wall_s=duration,
        phases=dict(stages),choices=dict(choices),replays=replays,started_certificates=begun,completed_certificates=len(certs),
        certificates=certs,delivered=deliveries,physical=sorted(found),partial=partial,**phaseinfo)
    put(DEST/case/"runs"/(rec["method"]+".json"),summary)

def pack(case):
    obj=next(o for o in read(HERE/"registration/cases.json") if o["id"]==case)
    folders=sorted(p for p in ROOT.glob(case+"-*") if p.is_dir())
    must={"Q4","Base","Ordinary","Previous","Source","NT10"}
    if obj["cohort"]=="independent":must.add("NT60")
    if case in ("A06","C10","C11"):must.update(["GateFixed","GateAdaptive"])
    if not (ROOT/(case+"-no-shared-seed.json")).exists():must.update(["PairFixed","PairAdaptive"])
    if {p.name.split("-")[1] for p in folders}!=must or not all((p/"receipt.json").exists() for p in folders):return False
    if (DEST/case/"complete.json").exists():return True
    phy=Physics(case)
    for p in folders:pack_unit(p,phy,obj)
    phy.close()
    put(DEST/case/"complete.json",dict(case=case,methods=sorted(must),unique_plans=len(phy.plans)))
    print("archived",case,len(phy.plans),flush=True)
    return True
if __name__=="__main__":
    psutil.Process().cpu_affinity([int(os.environ.get("U4_ARCHIVE_CPU","8"))])
    for o in read(HERE/"registration/cases.json"):pack(o["id"])
