"""One-shot, single-thread call ledger. Child processes are killed at the outer wall limit."""
import os
for name in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","BLIS_NUM_THREADS","NUMEXPR_NUM_THREADS",
             "VECLIB_MAXIMUM_THREADS","NUMBA_NUM_THREADS"):
    os.environ[name]="1"
import argparse
import csv
import gzip
import hashlib
import json
import platform
import random_order as random
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from fractions import Fraction as Q

from profiles import CFG, ROOT, IDS, dump, git, table

FOLDERS={"common":"g1_initial","HEFT":"g1_initial","ETA":"g1_initial","SA":"g1_initial",
         "G2":"g2_unconstrained","G3":"g3_thermal","RF":"local_rf","G4_targets":"g4_mechanism",
         "G4_group":"g4_mechanism","pilot":"pilot_comparison","G0":"preflight","audit":"logs"}


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic(path,obj):
    path=ROOT/path
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj,ensure_ascii=False,default=str,allow_nan=False)+"\n",encoding="utf-8")
    tmp.replace(path)


def packed(path,data):
    path=ROOT/path
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():
        raw=json.dumps(data,separators=(",",":"),ensure_ascii=False,default=str,allow_nan=False).encode()
        tmp=path.with_suffix(".tmp")
        tmp.write_bytes(gzip.compress(raw,compresslevel=3,mtime=0));tmp.replace(path)


def unpack(path):
    return json.loads(gzip.decompress((ROOT/path).read_bytes()))


def planid(p,plan):
    if plan is None: return None
    rows,low=plan
    obj=dict(case=p.case,rows=rows,low=sorted(low))
    key=hashlib.sha256(json.dumps(obj,separators=(",",":")).encode()).hexdigest()
    packed("logs/plans/"+key+".json.gz",obj)
    return key


def loadplan(key):
    x=unpack("logs/plans/"+key+".json.gz")
    return [tuple(r) for r in x["rows"]],frozenset(tuple(r) for r in x["low"])


def recpath(case,method,suffix=""):
    return FOLDERS[method]+"/"+case+"_"+method+("_"+suffix if suffix else "")+".json"


def fetch(case,method,suffix=""):
    path=ROOT/recpath(case,method,suffix)
    return json.loads(path.read_bytes()) if path.exists() else {}


def hydrate(p,plan,expected):
    from heat import evaluate
    from model import event_arrays,independent_events
    import numpy as np
    key=planid(p,plan)
    real=evaluate(p,plan,cert=True,trace=True)
    a,sw,edges=event_arrays(p,*plan)
    b,sw2=independent_events(p,*plan)
    if not np.array_equal(a,b) or sw!=sw2 or expected and (
       real["status"]!=expected["status"] or abs(real["E_J"]-expected["E_J"])>1e-8):
        raise ValueError("independent replay discrepancy "+key)
    reset=evaluate(p,plan,cert=True,trace=True,reset=True)
    for kind,result in (("continuous",real),("reset",reset)):
        events=result.pop("events")
        packed("certificates/"+key+"_"+kind+".json.gz",dict(case=p.case,schedule=key,
               fields="start_tick,end_tick,p35[4],slope[4],idle35[4],start_C[4],end_C[4],continuous_max_upper_C[4],node_J[4],roundoff_K",
               events=events,metrics=result))
    packed("certificates/"+key+"_schedule.json.gz",dict(case=p.case,units=CFG["nodes"],
        stage_fields=["stage","request","unit","opp","start_tick","end_tick"],
        rows=[[i,i//3,u,k,t,p.finish(i,r)] for i,r in enumerate(plan[0]) for u,k,t in [r]],
        idle_low_before=sorted(plan[1]),switch_fields=["start_tick","end_tick","domain","old","new"],
        switches=sw,resource_edges=edges,domains=["CPU","GPU","NPU"]))
    return key,real,reset


def worker(case,method,suffix,end,params):
    from heat import evaluate
    from model import Problem, Invalid, construct
    from search import Expired,Tracker,check,eta,lns,rf
    import mechanism
    if method=="G0":
        import preflight
        preflight.run(lambda p,pl,c:hydrate(p,pl,c)[0])
        return
    if method=="audit":
        import report
        report.audit(end)
        return
    p=Problem(case); rng=random.Random(101)
    tr=Tracker(p,end,thermal=method!="G2" and not (method=="RF" and suffix.endswith("0")))
    tr.start=params["start"]
    path=recpath(case,method,suffix)
    info={}; orderlog=dict(seed=101,random_neighbor_seed=102,moves=[])
    nonthermal=None; common=fetch(case,"common")
    source=params.get("init") or common.get("safe_plan") or common.get("fallback")
    base=loadplan(source) if source else None
    def receipt(status):
        obj=dict(case=case,method=method,arm=suffix,status=status,initial=source,
                 elapsed_s=time.perf_counter()-params["start"],limit_s=CFG["budgets_s"][method],
                 best_plan=planid(p,tr.plan),best=tr.best,safe_plan=planid(p,tr.safe_plan),safe=tr.safe,
                 hot_plan=planid(p,tr.hot_plan),hot=tr.hot,fallback=planid(p,nonthermal),
                 lower=p.cached_lb,**tr.receipt(),**info)
        atomic(path,obj)
    p.cached_lb=p.lower()
    tr.on_change=lambda:receipt("CHECKPOINT")
    try:
        if method=="common":
            modes=[("reference",9),("alternate",5),*(("heft",k) for k in (9,5,3,2,1,0))]
            if case=="D0": modes.insert(0,("low",0))
            info["constructors"]=[]
            for name,k in modes:
                check(end);pl=construct(p,name,k)
                ans=tr.consider(pl,force=True)
                if ans and nonthermal is None: nonthermal=pl
                info["constructors"].append([name,k,ans and ans["status"],ans and ans["E_J"]])
        elif method=="G4_targets":
            info["checked"],info["blocked"]=mechanism.screen(p,base,end)
        elif method=="G4_group":
            info.update(mechanism.compare(p,base,params["target"],suffix.split("_")[-1],tr,orderlog))
        else:
            if base is not None: tr.consider(base,force=True)
            if method=="HEFT":
                for k in (9,5,3,2,1,0):
                    check(end);tr.consider(construct(p,"heft",k),force=True)
            elif base is None: info["reason"]="NO_LEGAL_INITIAL"
            elif method=="ETA": eta(p,base,tr)
            elif method in ("G2","G3","SA"): lns(p,base,tr,rng,method,orderlog)
            elif method=="RF": info["search"]=rf(p,base,suffix[0],tr)
            elif method=="pilot": mechanism.pilot(p,base,suffix,params["targets"],tr,orderlog)
    except Expired: info["search_time_limit"]=True
    orderlog["streams"]=random.records()
    if orderlog["moves"] or any(x["draw_count"] for x in orderlog["streams"]):
        packed("logs/orders/"+Path(path).stem+".json.gz",orderlog)
    receipt("COMPLETED")


class Batch:
    def __init__(self):
        self.start=time.perf_counter()
        self.ledger=ROOT/"logs/calls.jsonl"
        self.ledger.parent.mkdir(parents=True,exist_ok=True)
        self.ledger.open("x").close()
        self.caps=0
        self.count={}
        self.save_event(dict(event="freeze",utc=now(),commit=git("rev-parse","HEAD").decode().strip(),
                             wall_s=18000,method_sum_cap_s=16620))
    def save_event(self,row):
        with self.ledger.open("a",encoding="utf-8") as stream:
            stream.write(json.dumps(row,ensure_ascii=False,default=str)+"\n")
    def call(self,case,method,suffix="",**params):
        cap=CFG["budgets_s"][method]
        maxima=dict(G0=1,common=7,HEFT=7,ETA=7,SA=7,G2=7,G3=7,RF=24,G4_targets=6,G4_group=84,pilot=18,audit=1)
        self.count[method]=1+self.count.get(method,0)
        if self.count[method]>maxima[method] or self.caps+cap>16620: raise RuntimeError("budget allocation")
        self.caps+=cap
        start=time.perf_counter()
        limit=min(cap,18000-(start-self.start))
        if limit<=0: raise RuntimeError("global deadline")
        self.save_event(dict(event="begin",case=case,method=method,arm=suffix,utc=now(),budget_s=cap,elapsed_s=start-self.start))
        print(case,method,suffix,flush=True)
        params["start"]=start
        parfile=ROOT/"logs/current_call.json"
        atomic("logs/current_call.json",params)
        args=[sys.executable,str(ROOT/"execution.py"),"worker",case,method,suffix,str(start+limit-min(2.,limit*.04))]
        try:
            proc=subprocess.run(args,cwd=ROOT,capture_output=True,timeout=max(.01,limit-(time.perf_counter()-start)))
            state="OK" if proc.returncode==0 else "ERROR"
            err=proc.stderr.decode(errors="replace")
        except subprocess.TimeoutExpired:
            state="TIME_LIMIT";err=""
        elapsed=time.perf_counter()-start
        self.save_event(dict(event="end",case=case,method=method,arm=suffix,utc=now(),actual_s=elapsed,state=state,error=err))
        if state=="ERROR" or method in ("G0","audit") and state!="OK":
            raise RuntimeError(f"{method} {state} {err[-2000:]}")
        return fetch(case,method,suffix)


def experiment(batch,case):
    def call(m,s="",**kw): return batch.call(case,m,s,**kw)
    com=call("common")
    g1=[com]+[call(m) for m in ("HEFT","ETA","SA")]
    g2=call("G2"); g3=call("G3")
    pool=[r for r in [*g1,g3] if r.get("safe")]
    best=min(pool,key=lambda r:r["safe"]["E_bounds"][1]) if pool else None
    local=[]
    if case!="D0" and com.get("safe_plan"):
        for s in ("R0","Rtheta","F0","Ftheta"): local.append(call("RF",s,init=com["safe_plan"]))
    traces=[r for r in [*g1,g2,g3,*local] if r.get("hot")]
    # A verified hot complete schedule at lower energy than the best known SAFE,
    # or a changed main with positive reference saving in a fully legal hot witness.
    clue=[]
    if best:
        from model import Problem
        p=Problem(case)
        orig=loadplan(best["safe_plan"])[0]
        for r in traces:
            hotrows=loadplan(r["hot_plan"])[0]
            positives=[i for i in range(1,p.n,3) if hotrows[i][:2]!=orig[i][:2] and
                  p.inc(i,*hotrows[i][:2])<p.inc(i,*orig[i][:2])]
            if r["hot"]["E_bounds"][1]<best["safe"]["E_bounds"][0] or positives:
                clue.append(dict(hot=r["hot_plan"],against=best["safe_plan"],positive_changed_mains=positives))
    gate=dict(case=case,common_SAFE=bool(com.get("safe")),mechanism_seed=best and best["safe_plan"],
              hot_clues=clue,g4_records=[],matched_positive=False)
    if best and clue and case!="D0":
        screening=call("G4_targets",init=best["safe_plan"])
        records=screening.get("blocked",[])
        for n,target in enumerate(records):
            group={g:call("G4_group",f"{n}_{g}",init=best["safe_plan"],target=target)
                   for g in ("B0","B1","B2","B3","B4a","B4b","B5")}
            # Ordinary groups can always retain the original full SAFE energy.
            def comparator(r):
                return min(best["safe"]["E_bounds"][0],r["safe"]["E_bounds"][0] if r.get("safe") else math.inf)
            winners=[]
            for name in ("B3","B5"):
                test=group[name];common_n=group["B3"].get("common_extra_count",0)
                members=test.get("members_final",test.get("members",[]))
                delta=loadplan(test["safe_plan"])[0] if test.get("safe_plan") else []
                therm=set(group["B2"].get("members",[])[1:]) | set(group["B3"].get("members",[])[1+common_n//2:])
                timing=set(group["B1"].get("members",[])[1:])
                changed={j for j in members[1:] if delta and delta[j]!=orig[j]}
                if (test.get("safe") and common_n>=2 and len(members)==common_n+1 and test.get("heat_evidence")
                    and changed & therm and changed & timing and
                    test["safe"]["E_bounds"][1]<min(comparator(group[g]) for g in ("B1","B4a","B4b"))):
                    winners.append(name)
            positive=bool(winners)
            gate["g4_records"].append(dict(target=target["stage"],positive=positive,winners=winners))
            gate["matched_positive"] |= positive
        if gate["matched_positive"]:
            for arm in ("LNS","AB","DELTA"): call("pilot",arm,init=best["safe_plan"],targets=records)
    dump("logs/gate_"+case+".json",gate)
    return gate


def main():
    # Refuse accidental reruns and code drift before any experimental work.
    if git("status","--porcelain","--untracked-files=all","--",".").strip():
        raise RuntimeError("unfrozen diagnostic tree")
    batch=Batch()
    try:
        batch.call("ALL","G0")
        dev=[experiment(batch,c) for c in IDS if c.startswith("D")]
        dev_pass=any(g["matched_positive"] for g in dev)
        dump("logs/development_gate.json",dict(holdout_open=dev_pass,frozen_commit=git("rev-parse","HEAD").decode().strip()))
        if dev_pass:
            for c in IDS:
                if c.startswith("H"): experiment(batch,c)
    except Exception as exc:
        dump("logs/stop.json",dict(reason=str(exc),utc=now()))
        print(str(exc),flush=True)
    batch.call("ALL","audit")
    hashes={path.relative_to(ROOT).as_posix():hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(ROOT.rglob("*")) if path.is_file() and "__pycache__" not in path.parts
            and path.name!="RESULT_SHA256.json"}
    dump("RESULT_SHA256.json",dict(algorithm="sha256",files=hashes,
         snapshot=hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(",",":")).encode()).hexdigest()))


if __name__=="__main__":
    import math
    if sys.argv[1:2]==["worker"]:
        _,_,case,method,suffix,end=sys.argv
        worker(case,method,suffix,float(end),json.loads((ROOT/"logs/current_call.json").read_bytes()))
    elif sys.argv[1:]==["batch"]: main()
    else: raise SystemExit("usage: python execution.py batch")
