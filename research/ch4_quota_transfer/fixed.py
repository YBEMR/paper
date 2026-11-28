"""Fixed parents from an actual frozen A width-four search, with isolated OPP pairs."""
import hashlib,json,os,sys,time
from collections import Counter
from pathlib import Path
from types import FunctionType,MethodType
from transfer import ROOT,T,m,init,make,emit
import numpy as np


def static(x):
    if isinstance(x,np.ndarray):return [x.dtype.str,list(x.shape),hashlib.sha256(x.tobytes()).hexdigest()]
    if isinstance(x,bytes):return x.hex()
    if isinstance(x,(list,tuple)):return [static(v) for v in x]
    if isinstance(x,np.generic):return x.item()
    return x


def full_profile(obj,cfg,dest):
    e,flow=m.build(obj,dest)
    totals=Counter()
    def watch(fn,k):
        def wrapper(*a,**kw):
            t=T();out=fn(*a,**kw);totals[k]+=T()-t;return out
        return wrapper
    def clone(fn,**updates):
        out=FunctionType(fn.__code__,dict(fn.__globals__,**updates),fn.__name__,fn.__defaults__,fn.__closure__)
        out.__kwdefaults__=fn.__kwdefaults__
        return out
    orig=e.cert.__func__
    ev=orig.__globals__["evaluate"]
    ev=clone(ev,independent_events=watch(ev.__globals__["independent_events"],"events"),integrate=watch(ev.__globals__["integrate"],"integral"))
    class Proxy:
        savez_compressed=staticmethod(watch(np.savez_compressed,"write"))
        def __getattr__(self,k):return getattr(np,k)
    e.cert=MethodType(clone(orig,evaluate=ev,put=watch(orig.__globals__["put"],"write"),np=Proxy()),e)
    e.build=watch(e.build,"events")
    r=e.replay(cfg)
    t=T();d,tr=e.cert(cfg,r);duration=T()-t
    totals["cert_fields"]=duration-sum(totals.values())
    totals["full"]=duration
    return dict(**totals,status=d["metrics"]["status"],plan=d["plan_sha256"])


def main(dest):
    native=init()
    api=m.RUN[0]
    for pos,case in enumerate(("A02","A06","C10","C11")):
        obj=next(o for o in m.u2.CASES if m.label(o)==case)
        c=m.u2.make_flow(api,obj,dest/"input")
        pairs=c.candidates.__func__.__globals__["p1"]
        allpairs=list(pairs.PAIRS)
        parents={}
        expanding=0.
        def capture(c,j,ps,*args):
            nonlocal expanding
            if j in (0,c.windows//2,c.windows-1):parents[j]=ps[0]
            tick=T();result=native(c,j,ps,*args);expanding+=T()-tick
            return result
        api.e.expand=capture
        build,_=m.RUN[2].builder("NT")
        tick=T();term=build(c,"NT",4,tick,tick+300,dict(actions=[],groups=[],beam=[]));build_s=T()-tick
        assert len(parents)==3 and term
        # Neutralize compilation in the diagnostic physical-cost measurements.
        cfg=tuple((3,int(k)-10) if k>=10 else (2,int(k)) for k in term[0]["config"])
        full_profile(obj,cfg,dest/"warm-physical"/case)
        profile=full_profile(obj,cfg,dest/"physical"/case)
        emit(dest/"physical.jsonl",dict(case=case,sort_retain_s=build_s-expanding,build_s=build_s,**profile))
        for j,parent in parents.items():
            emit(dest/"parents.jsonl",dict(case=case,j=j,id=parent["id"],config=parent["config"].hex(),
                f=static(parent["f"]),k=static(parent["k"]),peak=float(parent["peak"]),temperature=parent["temperature"].tolist()))
            for ix,pair in enumerate(allpairs):
                pairs.PAIRS=[pair]
                detail={}
                for rep in (1,2,3):
                    for arm in (("A","B") if (rep+pos+j+ix)%2 else ("B","A")):
                        fine=[]
                        for mode in (("bare","light","fine") if rep%2 else ("fine","light","bare")):
                            note=fine.append if mode=="fine" else lambda x:None
                            fn=make(native,arm,mode,note)
                            log=dict(actions=[],groups=[])
                            tick=T();pool,ok=fn(c,j,[parent],"NT",tick,tick+200,log);elapsed=T()-tick
                            assert ok and len(log["groups"])==1
                            if mode=="fine":
                                timing=dict(fine[-1]);chosen=timing.pop("chosen")
                                emit(dest/"fine.jsonl",dict(case=case,arm=arm,rep=rep,**timing))
                            emit(dest/"probe.jsonl",dict(case=case,arm=arm,rep=rep,j=j,g=pair[0],n=pair[1],mode=mode,elapsed=elapsed))
                        if rep!=1:continue
                        states={}
                        for a in log["actions"]:
                            xy=tuple(a[4:6])
                            ext=c.extension(c.kinds[c.release.searchsorted(j*10000):c.release.searchsorted((j+1)*10000)],
                                *[int(z) for z in np.bincount(c.kinds[c.release.searchsorted(j*10000):c.release.searchsorted((j+1)*10000)],minlength=2)],*pair,*xy)
                            config=parent["config"]+ext
                            right=c.p.horizon if j+1==c.windows else (j+1)*10000
                            ledger=c.ledger(config,j*10000,right,2500,j+1==c.windows,True)
                            digest=hashlib.sha256(json.dumps(static(ledger),sort_keys=True).encode()).hexdigest()
                            state=pool.get(a[6])
                            metrics=None if state is None else [float(state[k]) for k in ("energy","risk","drain","peak")]+[state["temperature"].tolist()]
                            states[xy]=[a[9],digest,metrics]
                            if xy==tuple(chosen[0]):
                                for pass_id in range(3):
                                    measured={}
                                    for mom in ((False,True) if pass_id%2 else (True,False)):
                                        begin=T()
                                        for _ in range(3):res=c.ledger(config,j*10000,right,2500,j+1==c.windows,mom)
                                        measured[mom]=(T()-begin)/3
                                        assert static(res[:8])==static(ledger[:8])
                                    emit(dest/"binning.jsonl",dict(case=case,j=j,g=pair[0],n=pair[1],arm=arm,rep=pass_id,
                                         fifo_no_bins=measured[False],fifo_with_bins=measured[True]))
                        detail[arm]=states
                a,b=detail["A"],detail["B"]
                common=a.keys() & b.keys()
                assert len(a)==len(b) and all(a[x]==b[x] for x in common)
                row=dict(case=case,j=j,g=pair[0],n=pair[1],parent=parent["id"],slots=len(a),common=len(common),
                         union=len(a.keys()|b.keys()),only_A=sorted(a.keys()-b.keys()),only_B=sorted(b.keys()-a.keys()))
                for arm,states in detail.items():
                    valid=[v[2] for v in states.values() if v[2] is not None]
                    row[arm]=dict(quotas=[dict(xy=k,status=v[0],ledger_sha=v[1],metrics=v[2]) for k,v in states.items()],
                                  legal=len(valid),min_energy=min((v[0] for v in valid),default=None),
                                  min_risk=min((v[1] for v in valid),default=None),min_drain=min((v[2] for v in valid),default=None))
                emit(dest/"sets.jsonl",row)
            pairs.PAIRS=allpairs
        print("verified",case,flush=True)
    (ROOT/"fixed_pass.json").write_text(json.dumps(dict(actual_cases=4,groups=360,passes=3)))


if __name__=="__main__":main(Path(sys.argv[1]))
