"""Functional checks against frozen records. No M5-a search cell is timed again."""
import csv
import io
import json
import tarfile
from pathlib import Path
import numpy as np

from suffix import Boundary,Timing,full_timing,suffix_feasible
from planning import generate,hashcode
from post_audit import timing as original_audit_timing

def archived_configs(old,case,enc):
    configs={}
    with tarfile.open(old/"archive"/(case+".tar.gz"),"r|gz") as tar:
        for ent in tar:
            if ent.name.endswith("/plan.json"):
                obj=json.load(tar.extractfile(ent))
                configs[ent.name.split("/")[0]]=enc([v[:2] for v in obj["rows"][1::3]])
    return configs
def boundary_edges():
    import types
    eng=types.SimpleNamespace(groups=[[0],[1],[2]])
    t=types.SimpleNamespace(horizon=100,ready=np.array([0,20,40]),limits=np.array([30,60,90]),
                            lengths=np.full((3,13),10,np.int64))
    code=bytes([1,11,2]);s=Boundary(eng,code,{"ends":[15,30,50]},t)
    assert s.limits(0,1)==(15,1,80,2,2)    # empty current device, switched suffix
    assert s.limits(1,2)==(30,1,100,0,None) # empty current and no suffix, exit to zero
    assert s.limits(1,0)==(0,0,50,1,1)     # empty prefix, actual initial low level
    assert s.prove_boundaries()>0
    return 3

def run_gate(m,case,dest):
    eng,(cfg,state,d,_)=m.intake(case,dest,True);parent=m.enc(cfg);tm=Timing(eng)
    bound=Boundary(eng,parent,state,tm);edges=bound.prove_boundaries()
    zero=[bound.inspect(parent,w) for w in range(len(eng.groups))]
    assert all(x["own"] and x["remaining"]>=0 for ys in zero for x in ys)
    assert tm.check(parent)[0]
    old=m.ROOT;archive=old/"archive";plans=archived_configs(old,case,m.enc)
    refs=list(csv.DictReader((old/"diagnostics/rejections.csv").open()))
    refs={r["cfg"]:r for r in refs if r["case"]==case}
    samples=[];watch={};positive=[];tested=set();negative=0
    lengths={(t+".main",dev,k):v for (t,dev,k),v in eng.length.items()}
    for i,r in enumerate(eng.p.req):
        lengths[r["kind"]+".pre",0,0]=eng.p.dur(3*i,0,0)
        lengths[r["kind"]+".post",1,0]=eng.q[i]
    for meth in "ACDE":
        logs=[json.loads(l) for l in (archive/"logs"/case/meth/"events.jsonl").read_bytes().splitlines()]
        for gen in [x for x in logs if x["kind"]=="generation"]:
            base=plans[gen["parent"]]
            for item in gen["proposals"]:
                meta=item["meta"];w=meta["win"];ix=eng.groups[w]
                patch=bytes.fromhex(meta["patch"]);c=base[:ix[0]]+patch+base[ix[-1]+1:]
                key=hashcode(c);assert key==item["cfg"]
                if key not in tested:
                    actual=eng.replay(m.dec(c)) is not None
                    fast=tm.check(c)[0];assert actual==fast,(case,key,"full timing")
                    negative+=int(not actual);tested.add(key)
                if meth=="E":
                    rows=bound.inspect(c,w);assert key in refs and base==parent
                    late,mainlate,_,_=original_audit_timing(c,eng.p.req,lengths)
                    assert late and late[0][0]==int(refs[key]["first_late_request"])
                    assert late[0][0] in mainlate and int(eng.p.req[late[0][0]]["scene"])==w+1
                    assert all(x["own"] for x in rows) and any(x["remaining"]<0 for x in rows)
                    samples.append(dict(cfg=key,win=w,devices=rows,first_late=late[0],frozen_fifo=False))
                    watch[key]=(w,patch)
        for a in [x for x in logs if x["kind"]=="accepted"]:
            meta=a["meta"];w=meta["win"];base=plans[meta["parent"]];c=plans[a["plan"]]
            assert eng.replay(m.dec(c)) is not None
            bs=bound if base==parent else Boundary(eng,base,eng.replay(m.dec(base)),tm)
            rows=bs.inspect(c,w)
            assert all(x["own"] and x["remaining"]>=0 for x in rows)
            assert tm.check(c)[0]
            positive.append(dict(method=meth,plan=a["plan"],cfg=hashcode(c),win=w,devices=rows,on_common_parent=base==parent))
            if base==parent:watch[hashcode(c)]=(w,bytes.fromhex(meta["patch"]))
    assert len(refs)==len(samples)==16
    # All historical SAFE physical plans pass an unchanged suffix for every arrival window.
    for key,c in plans.items():
        r=eng.replay(m.dec(c));assert r is not None and tm.check(c)[0]
        b=Boundary(eng,c,r,tm)
        assert all(x["own"] and x["remaining"]>=0 for win in range(len(eng.groups)) for x in b.inspect(c,win))
    _,_,stages=generate(eng,parent,state,"E",tm,dest/"known_paths.jsonl.gz",watch)
    assert all(stages[v["cfg"]]=="suffix_deadline" for v in samples)
    data=dict(case=case,original_windows=len(zero),boundary_oracle_tests=edges,
              frozen_nominees_compared=len(tested),frozen_nominees_illegal=negative,
              prior_physical_plans=len(plans),old_rejected=samples,old_accepted=positive,
              initial_joint_candidate_provenance=stages)
    m.save(dest/"audit.json",data)
