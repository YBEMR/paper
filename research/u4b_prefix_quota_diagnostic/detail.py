"""Audit the full terminal pool, local-repair journals and replay each reference SAFE."""
from collections import Counter,defaultdict
import gzip
import json

import psutil
from shared import *

def detail(k,stack):
    obj=cases()[k];root=A/"results"/k;dest=HERE/"offline"/k
    audit=read(dest/"audit.json");certs=read(dest/"certificates.json")
    inp=A/"registration/inputs"/obj["input"];api,_,_,causal=stack
    flow=api.Flow(obj["word"],35,obj["case"],RAW,inp);e=flow.eng;b=Builder(flow,e);ns=limits(b)
    phys=root/"physical";block=trace_reader(phys)
    plans={r["certificate"]["plan_sha256"]:r for r in map(json.loads,gzip.decompress((phys/"plans.jsonl.gz").read_bytes()).splitlines())}
    def physical(key):
        r=plans[key];data=b"".join(block(h) for h in r["blocks"])
        assert sha(data)==r["trace_sha256"]
        return np.frombuffer(data,"<f8").reshape(r["shape"])
    def config(key):return u.encoded(row[:2] for row in plans[key]["plan"]["rows"][1::3])
    safe=audit["NT60"];cfg=config(safe);state=causal(flow,cfg);built=e.build(src.genes(cfg),state)
    tr=physical(safe)
    assert np.array_equal(built["ev"],tr[:,:14]) and sha(u.raw(dict(case=obj["case"],rows=built["rows"],low=sorted(built["low"]))))==safe
    from heat import integrate
    p=e.p
    result=integrate(built["ev"],p.initial,p.G,p.cap,float(p.ta),np.empty(0,np.int64),True)
    assert np.array_equal(result[10],tr[:,14:]) and max(result[2])<=80 and state["slack"]>=0
    put(dest/"safe_reference.json",dict(plan=safe,trace_sha256=plans[safe]["trace_sha256"],certificate=plans[safe]["certificate"]["metrics"],
                                        full_replay_equal=True,config=cfg.hex(),windows=audit["path"]))
    # Save an ordered index of every actual local repair attempt. Parent + pair + quota recovers the full bytes.
    for method in ("Ordinary","Previous","Source"):
        run=read(root/f"runs/{method}.json");records=[];parents={};stage=None;stored=[];retained=defaultdict(set)
        for a in events(root,run):
            tag=a[0]
            if tag=="begin":stage=a[1]
            if tag=="parent":parents[a[1]]=a[2]
            if stage!="repair":continue
            if tag=="q4_action":
                _,pid,j,pair,q,d,t=a
                records.append([pid,j+1,pair,q,d,t])
                retained[j].add(pid)
            elif tag=="store":stored.append(a[1:])
            elif tag=="end":stage=None
        body=dict(frozen_journals=run["journal"],observed_parent={p:parents[p] for p in {x[0] for x in records}},
                  columns=["parent","window","frequency_pair","quota","delta","timing"],attempts=records,
                  parents_expanded={j+1:sorted(v) for j,v in retained.items()},stored_rankings=stored,
                  choices=run["choices"],stop=run["receipt"]["status"])
        (dest/(method+"_repair.json.gz")).write_bytes(gzip.compress(u.raw(body),compresslevel=5,mtime=0))
    proofs={}
    for a in certs:
        if a["method"]=="Q4" or not a["proof"]:continue
        w=a["proof"];h=w["events_sha256"]
        if h not in proofs:proofs[h]=(a["plan"],w,physical(a["plan"])[:w["rows"],:14].copy())
    firsts={}
    for h,(key,w,ev) in proofs.items():
        code=config(key);prefix=settled_key(code,w["tick"],b)
        n=len(prefix);front=[sum(bytes.fromhex(c).startswith(prefix) for c in l["retained"]) for l in audit["layers"]]
        allj=next((j+1 for j,l in enumerate(audit["layers"]) if l["retained"] and front[j]==len(l["retained"])),None)
        firsts[h]=dict(witness=w,source=key,settled_action=prefix.hex(),earliest_all_beam_share=allj,
                       retained_sharing_by_window=front,base_evidence=any(a["method"]=="Base" and a["phase"]=="terminal" and a["proof"] and a["proof"]["events_sha256"]==h for a in certs))
    terminal=[]
    with gzip.open(dest/"legal_pools.jsonl.gz","rb") as rows:
        for s in rows:
            j,rank,code,t=json.loads(s)
            if j!=len(ns):continue
            c=bytes.fromhex(code);r=causal(flow,c)
            assert r is not None and r["slack"]==t[6]
            ev=e.build(src.genes(c),r)["ev"]
            matches=[]
            for h,(key,w,source) in proofs.items():
                if len(ev)>=len(source) and np.array_equal(ev[:len(source)],source):matches.append(h)
            terminal.append(dict(rank=rank,config=code,matches=matches))
    put(dest/"terminal_evidence.json",dict(proofs=firsts,complete=terminal))
    print("extended",k,len(terminal),len(proofs),flush=True)

if __name__=="__main__":
    psutil.Process().cpu_affinity([8]);stack=u.stack()
    for k in FOCUS:
        if not (HERE/"offline"/k/"terminal_evidence.json").exists():detail(k,stack)
