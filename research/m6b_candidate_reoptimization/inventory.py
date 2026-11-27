"""Recover the on-time half-open physical census from the immutable M1-i archives."""
import csv
import gzip
import hashlib
import json
import os
import tarfile
from collections import Counter,defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parent
ARCH=ROOT/"archive"
SCR=Path(os.environ["U1_OUT"])/"m6b_inputs"
GEN=Path(os.environ["GEN"])/"research/m1i_generalization/data"
METHODS=("NT","ZQ-Beam")
FIX=[(4,0,27,0),(4,0,27,0),(5,0,25,1),(5,0,26,1),(2,0,20,0),(3,0,0,20),
     (4,1,31,0),(3,0,31,0),(0,0,24,0),(0,0,25,0),(0,0,27,0),(0,0,25,0)]
def raw(o):return json.dumps(o,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(",",":")).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_bytes())
def save(p,o):
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+".tmp");tmp.write_bytes(raw(o)+b"\n");tmp.replace(p)
def readcsv(p):
    with p.open(newline="") as f:return list(csv.DictReader(f))
def gzrows(p,rows):
    p.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(p,"wb",compresslevel=3) as f:
        for r in rows:f.write(raw(r)+b"\n")
def physical(d):return {k:v for k,v in d.items() if k!="cert_s"}
def get_map(b):return sha(bytes(x>=10 for x in b))
def label(obj):return obj["case"].split("_")[0]
def material(code):return SCR/code
def min_ref(r):return (r["ref"],r["cfg"],r["plan"])
def rank(r):return (r["low_ref"],r["ref_cfg"],r["mapping"])
def fixture_cfg(flow):
    import numpy as np
    parts=[]
    for w,(g,n,a,b) in enumerate(FIX):
        ix=np.nonzero(flow.release//10000==w)[0];k=flow.kinds[ix]
        parts.append(bytes(flow.extension(k,int((k==0).sum()),int((k==1).sum()),g,n,a,b)))
    return b"".join(parts)
def census(obj,seeds,fixture_hash=None):
    case=obj["case"];code=label(obj);src=GEN/"evidence"/case
    ledger=ARCH/"identity"/code;dest=material(code);dest.mkdir(parents=True)
    receipt=read(src/"receipt.json");aud={}
    for name in ("runs.tar.xz","physical.tar.xz","event_index.csv.gz"):
        aud[name]=sha((src/name).read_bytes());assert aud[name]==receipt["files"][name]
    with gzip.open(src/"event_index.csv.gz","rt") as f:index={r["plan"]:r for r in csv.DictReader(f)}
    selected=[];expected={};fixture_all=[]
    with tarfile.open(src/"runs.tar.xz","r|xz") as arc:
        for ent in arc:
            role=ent.name.split("/")[0];wanted=role in ("r1-NT","r1-ZQ-Beam")
            if not wanted and not fixture_hash:continue
            run=json.load(arc.extractfile(ent));method=run["method"]
            for no,v in enumerate(run["records"],1):
                cert=v["cert"];p=cert["plan_sha256"]
                if fixture_hash and v["id"]==fixture_hash:
                    fixture_all.append(dict(run=role,method=method,call=no,plan=p,end=v["end_s"],width=v["width"],rank=v["rank"],eligible=wanted and v["end_s"]<=60))
                if not wanted or v["end_s"]>60:continue
                canon=sha(raw(physical(cert)));assert expected.setdefault(p,canon)==canon
                selected.append(dict(source=method,call=no,plan=p,cfg=v["id"],status=cert["metrics"]["status"],
                    original_J=cert["metrics"]["E_J"],ref=cert["E35_J"],first_s=v["end_s"],start_s=v["start_s"],
                    width=v["width"],beam_rank=v["rank"],call_certificate_sha=sha(raw(cert)),physical_fields_sha=canon))
    wanted=set(expected);cfgs={};cert_seen=set()
    with tarfile.open(src/"physical.tar.xz","r|xz") as arc:
        for member in arc:
            p,n=member.name.split("/")
            if p not in wanted:continue
            b=arc.extractfile(member).read();key="plan_file_sha256" if n=="plan.json" else "certificate_file_sha256"
            assert sha(b)==index[p][key]
            if n=="plan.json":
                assert sha(b.strip())==p
                plan=json.loads(b);assert plan["case"]==case
                cfg=bytes(k+10*(u==3) for u,k,_ in plan["rows"][1::3]);cfgs[p]=cfg
            else:
                d=json.loads(b);assert p==d["plan_sha256"] and sha(raw(physical(d)))==expected[p];cert_seen.add(p)
            (dest/(p+"-"+n)).write_bytes(b)
    assert set(cfgs)==cert_seen==wanted
    gzrows(ledger/"physical.jsonl.gz",(dict(**index[p],cfg_hex=b.hex(),mapping=get_map(b),cfg=sha(b)) for p,b in sorted(cfgs.items())))
    maps={};ref_source={};status_sets=defaultdict(set)
    for r in selected:
        p=r["plan"];b=cfgs[p];assert sha(b)==r["cfg"]
        r["mapping"]=get_map(b);status_sets[r["mapping"]].add(r["status"])
    gzrows(ledger/"calls.jsonl.gz",selected)
    fallback={}
    for row in selected:
        if row["status"] in ("SAFE","HOT"):
            m=row["mapping"]
            if m not in fallback or min_ref(row)<min_ref(fallback[m]):fallback[m]=row
    for method in METHODS:
        rows=[r for r in selected if r["source"]==method];groups=defaultdict(list)
        physical_rows={}
        for r in rows:physical_rows.setdefault(r["plan"],r)
        for row in physical_rows.values():groups[row["mapping"]].append(row)
        entries=[]
        for m,members in groups.items():
            valid=[r for r in members if r["status"] in ("SAFE","HOT")]
            if not valid:continue
            safes=[r for r in valid if r["status"]=="SAFE"]
            hots=[r for r in valid if r["status"]=="HOT"]
            rep=min(safes,key=lambda r:(r["original_J"],r["cfg"],r["plan"])) if safes else min(hots,key=min_ref)
            if any(r["plan"]==seeds[method] for r in members):rep=next(r for r in members if r["plan"]==seeds[method])
            low=min(valid,key=min_ref);first=min(valid,key=lambda r:r["first_s"])
            entries.append(dict(mapping=m,source=method,local_safe=bool(safes),local_hot=bool(hots),
                hot_only=bool(hots) and "SAFE" not in status_sets[m],shared_other_safe=not safes and "SAFE" in status_sets[m],
                low_ref=low["ref"],ref_cfg=low["cfg"],representative=rep["plan"],rep_J=rep["original_J"],rep_status=rep["status"],
                rep_cfg=rep["cfg"],fallback=fallback[m]["plan"],rep_trace=index[rep["plan"]]["event_array_sha256"],
                original_best_J=min(r["original_J"] for r in valid),first_s=first["first_s"],first_width=first["width"],
                first_rank=first["beam_rank"],rep_s=rep["first_s"],rep_width=rep["width"],rep_rank=rep["beam_rank"],
                plans=[r["plan"] for r in members],hist_ranks=[r["beam_rank"] for r in members]))
        maps[method]=sorted(entries,key=rank)
    gzrows(ledger/"mappings.jsonl.gz",[r for m in METHODS for r in maps[m]])
    k=min(16,*[sum(e["local_safe"] for e in maps[m]) for m in METHODS]);assert k>=1
    selection={}
    for m in METHODS:
        entries=maps[m];seed=next(e for e in entries if e["representative"]==seeds[m])
        s=[e for e in entries if e["local_safe"] and e!=seed];h=[e for e in entries if e["hot_only"]]
        nh=min(len(h),(k-1)//2)
        sel={"S":[seed,*s[:k-1]],"H":[seed,*sorted(s[:k-1-nh]+h[:nh],key=rank)],
             "ALL":[seed,*[e for e in entries if e!=seed]]}
        assert len(sel["S"])==len(sel["H"])==k and (h or sel["S"]==sel["H"])
        selection[m]={arm:[e["mapping"] for e in options] for arm,options in sel.items()}
    save(ledger/"selection.json",dict(k=k,methods=selection))
    traceids={p:{name:idx[name] for name in ("event_array_sha256","npz_file_sha256")} for p,idx in index.items() if p in wanted}
    save(dest/"traces.json",traceids)
    findings=dict(case=code,files=aud,selected_calls=len(selected),physical=len(wanted),valid_maps={m:len(a) for m,a in maps.items()},
        status={m:dict(Counter(r["status"] for r in selected if r["source"]==m)) for m in METHODS},k=k)
    save(ledger/"audit.json",findings)
    if fixture_hash:save(ARCH/"fixture_identity.json",dict(cfg=fixture_hash,all_calls=fixture_all))
    print("inventory",code,findings["selected_calls"],findings["valid_maps"],k,flush=True)
