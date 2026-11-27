"""One single-core budget per arm and case. Only archived, on-time SAFE improvements count."""
import gzip
import importlib.util
import json
import multiprocessing as mp
import os
import platform
import signal
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/"m5a_mixed_frequency_quota"
RESULT=ROOT/"results"
sys.path.insert(0,str(OLD))
spec=importlib.util.spec_from_file_location("m5a_frozen_driver",OLD/"run.py")
prior=importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
from planner import projections
from planning import generate,hashcode
from suffix import Timing
import gate

METHODS="ACDER"  # R = E double prime
def event_rows(path):
    if not path.exists():return []
    return [json.loads(line) for line in path.read_bytes().splitlines() if line.endswith(b"}")]

def failed_physical(eng,c):
    free=[0,0];old=[0,0];end=[];start=[];posts=[0]*len(c);miss=[]
    for i,b in enumerate(c):
        u=int(b>=10);k=b%10
        s=max(eng.a[i],free[u]+5*(old[u]!=k));free[u]=s+eng.length[eng.types[i],u+2,k]
        old[u]=k;start.append(s);end.append(free[u])
    t=0
    for i in sorted(range(len(c)),key=lambda i:(end[i],i)):
        posts[i]=max(t,end[i]);t=posts[i]+eng.q[i]
        if t>eng.D[i]:miss.append([i,t-eng.D[i]])
    return dict(cfg=c.hex(),pre_starts=eng.ps,main_starts=start,main_ends=end,post_starts=posts,
                missed=miss,device_returns=[v+5*(k!=0) for v,k in zip(free,old)],horizon=eng.p.horizon)

def cell(case,method,cpu,dest,start):
    os.sched_setaffinity(0,{cpu});assert os.sched_getaffinity(0)=={cpu}
    elapsed=lambda:time.perf_counter()-start
    journal=(dest/"events.jsonl").open("w",buffering=1)
    def note(kind,**kw):
        journal.write(json.dumps(dict(t=elapsed(),kind=kind,**kw),default=lambda x:x.tolist(),separators=(",",":"))+"\n")
    eng,(cfg,state,cert,_)=prior.intake(case,dest)
    code=prior.enc(cfg);tm=Timing(eng);seen={code:(state,cert)}
    note("intake",**prior.endpoint(cert))
    def assess(c,meta,role):
        key=hashcode(c)
        if c in seen:
            note("duplicate",cfg=key,role=role,meta=meta);return seen[c]
        clock=elapsed();r=eng.replay(prior.dec(c));dt=elapsed()-clock
        if r is None:
            assert not tm.check(c)[0]
            note("timing_reject",cfg=key,role=role,meta=meta,replay_s=dt)
            seen[c]=(None,None)
        else:
            clock=elapsed();d,_=eng.cert(prior.dec(c),r);ct=elapsed()-clock
            note("certificate",cfg=key,role=role,meta=meta,replay_s=dt,cert_archive_s=ct,kernel_s=d["cert_s"],**prior.endpoint(d))
            seen[c]=(r,d)
        return seen[c]
    for turn in range(3):
        begin=elapsed();ledger=dest/f"turn{turn}.jsonl.gz"
        pool,counts,_=generate(eng,code,state,method,tm,ledger);dt=elapsed()-begin
        note("generation",turn=turn,parent=cert["plan_sha256"],coverage=counts,phase_s=dt,
             proposals=[dict(cfg=hashcode(c),meta=m) for c,m in pool])
        improvements=[]
        for c,m in pool:
            meta=dict(parent=cert["plan_sha256"],turn=turn,**m)
            r,d=assess(c,meta,"search")
            if method=="R":assert r is not None
            if d and d["metrics"]["status"]=="SAFE" and d["metrics"]["E_bounds"][1]<cert["metrics"]["E_bounds"][0]:
                improvements.append((d["metrics"]["E_bounds"][1],d["plan_sha256"],c,r,d,meta))
        if not improvements:
            note("natural",reason="no_strict_improvement",turn=turn);return
        _,_,winner,newstate,newcert,wm=min(improvements,key=lambda a:a[:2])
        note("accepted",turn=turn,meta=wm,**prior.endpoint(newcert))
        if method in "ER":
            for _,_,joint,_,dc,meta in improvements:
                # Always include the accepted result, and every improved candidate with a changed mapping.
                if joint!=winner and meta["mapping"]=="original":continue
                mapping,frequency=projections(eng,code,joint,meta);singles=[]
                for role,p in (("mapping_only",mapping),("frequency_only",frequency)):
                    ids=eng.groups[meta["win"]]
                    r,d=assess(p,dict(parent=cert["plan_sha256"],win=meta["win"],patch=p[ids[0]:ids[-1]+1].hex()),role)
                    if d:result=prior.endpoint(d)
                    else:
                        target=dest/("infeasible-"+hashcode(p)+".json.gz")
                        if not target.exists():
                            with gzip.open(target,"wt",encoding="utf8") as h:json.dump(failed_physical(eng,p),h,separators=(",",":"))
                        result=dict(status="TIMING",detail=target.name)
                    singles.append(dict(role=role,cfg=hashcode(p),**result))
                genuine=len({code,mapping,frequency,joint})==4
                note("factorial",parent=prior.endpoint(cert),joint=prior.endpoint(dc),joint_cfg=hashcode(joint),
                     accepted=joint==winner,genuine=genuine,meta=meta,singles=singles)
        code,state,cert=winner,newstate,newcert
    note("natural",reason="three_rounds")

def lane(idx,cpus):
    cpu=cpus[idx%len(cpus)];case=prior.CODES[idx];os.sched_setaffinity(0,{cpu})
    for method in METHODS[idx:]+METHODS[:idx]:
        folder=RESULT/case/method;folder.mkdir(parents=True,exist_ok=False)
        start=time.perf_counter()
        proc=mp.get_context("fork").Process(target=cell,args=(case,method,cpu,folder,start));proc.start()
        proc.join(timeout=max(0,29.85-(time.perf_counter()-start)))
        if proc.is_alive():proc.kill();proc.join();status="CAP"
        else:status="NATURAL" if proc.exitcode==0 else "ERROR"
        wall=time.perf_counter()-start
        prior.save(folder/"receipt.json",dict(status=status,wall_s=wall,limit_s=30,cpu=cpu,host=platform.node(),rc=proc.exitcode))
        print(case,method,status,round(wall,3),flush=True)
        if status=="ERROR":raise RuntimeError((case,method,proc.exitcode))
def main():
    cpus=prior.CPUS;start=time.perf_counter();signal.alarm(115)
    os.sched_setaffinity(0,{cpus[0]});sys.path.insert(0,str(ROOT.parent/"u2_adaptive_groups"))
    import common_u2
    prior.u2=common_u2;prior.api,prior.fourth,_,prior.state=common_u2.stack()
    special=gate.boundary_edges()
    for case in prior.CODES:
        gate.run_gate(prior,case,RESULT/"gate"/case)
    prior.save(RESULT/"gate"/"receipt.json",dict(wall_s=time.perf_counter()-start+2,prior_startup_reserved_s=2,prior_run="45970842761",core=cpus[0],cpus=cpus,
               host=platform.node(),python=sys.version,special_fixtures=special,source=os.environ.get("GITHUB_SHA"),
               run=os.environ.get("GITHUB_RUN_ID"),versions={k:__import__(k).__version__ for k in ("numpy","scipy","numba")}))
    signal.alarm(0)
    for offset in range(0,4,len(cpus)):
        ps=[]
        for idx in range(offset,min(4,offset+len(cpus))):
            p=mp.get_context("fork").Process(target=lane,args=(idx,cpus));p.start();ps.append(p)
        for p in ps:p.join()
        assert all(p.exitcode==0 for p in ps)
if __name__=="__main__":main()
