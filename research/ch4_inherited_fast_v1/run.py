"""Bounded, from-empty trials of the frozen solver. The expand hook changes only the quota mode."""
import os,sys,time,inspect,json,hashlib
from pathlib import Path
from collections import Counter
from itertools import groupby
from concurrent.futures import ProcessPoolExecutor
S=Path(os.environ.get("FAST_SCRATCH","/tmp/ch4_inherited_v1"))
HERE=Path(__file__).resolve().parent
for name in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS","NUMBA_NUM_THREADS"):os.environ[name]="1"
os.environ.update(U1_NT=str(S/"nt"),U1_FOUR=str(S/"four"),U1_THREE=str(S/"none"),U1_OUT=str(S/"scratch"),
                  GEN=str(S/"nt"),M1G_RAW=str(S/"warm"),NUMBA_CACHE_DIR=str(S/"numba"))
sys.path[:0]=[str(S/"site"),str(S/"driver/ch3_integrated_quality_v3")]
T=time.perf_counter
def write(path,v):
    with path.open("ab",buffering=0) as h:h.write(json.dumps(v,separators=(",",":")).encode()+b"\n")
def revised(fn,replacements,env):
    source=inspect.getsource(fn)
    for a,b in replacements:
        assert source.count(a)==1,(fn.__name__,a)
        source=source.replace(a,b)
    scope=dict(fn.__globals__,**env)
    exec(compile(source,"<frozen "+fn.__name__+" with measurement or budget binding>","exec"),scope)
    return scope[fn.__name__]
class Measured:
    def __init__(self,fn,arm,folder):
        self.folder=folder;self.arm=arm;self.width=0
        self.fn=revised(fn,[
          ('gen = "O" if method == "C2" else method[0]','gen = quota_arm'),
          ('types, a, b = window_types','tic=clock()\n    types, a, b = window_types'),
          ('            pilots = []','            count["generator_s"]+=clock()-tic\n            pilots = []'),
          ('            if gen != "O":','            tcal=clock();prior=count["fifo_s"]\n            if gen != "O":'),
          ('            assert len(set(chosen))','            if gen!="O":count["calibration_s"]+=clock()-tcal-(count["fifo_s"]-prior)\n            count["slots"]+=len(chosen)\n            assert len(set(chosen))'),
          ('                        ledger = c.ledger','                        tt=clock()\n                        ledger = c.ledger'),
          ('                    entries[xy] =','                        ss=clock()-tt;count["fifo_s"]+=ss;count["fifo_calls"]+=1\n                        if xy in pilots:count["pilot_fifo_s"]+=ss;count["pilot_fifo_calls"]+=1\n                    entries[xy] ='),
          ('                if moments:\n','                if moments:\n                    tt=clock()\n'),
          ('                drain =','                    count["heat_s"]+=clock()-tt;count["predict"]+=len(means)+int(rank_thermal and not final)\n                drain ='),
          ('            log["groups"].append','            count["groups"]+=1\n            if count["groups"]%8==0:snap(False,len(pool))\n            log["groups"].append'),
          ('    return pool, True','            tic=clock()\n    return pool, True')],dict(quota_arm=arm,count=Counter(),snap=self.snap))
    def snap(self,complete,pool):
        write(self.folder/"layers.jsonl",dict(width=self.width,layer=self.layer,parents=self.parents,elapsed=T()-self.start,
              complete=complete,legal=pool,**self.fn.__globals__["count"]))
    def __call__(self,c,j,parents,method,start,deadline,log):
        self.layer=j+1;self.parents=len(parents);self.start=T();self.fn.__globals__["count"].clear()
        self.snap(False,0);pool,done=self.fn(c,j,parents,method,start,deadline,log);self.snap(done,len(pool))
        return pool,done
def initialize(cpu):
    os.sched_setaffinity(0,{cpu})
    import online as v
    f=v.f;f.CPU=cpu;f.warm();return v
def cell(v,obj,folder,arm,cap):
    folder.mkdir(parents=True,exist_ok=False)
    f=v.f;api=f.m.RUN[0];meter=Measured(api.e.expand,arm,folder)
    def search():
        api.e.expand=meter
        old=f.m.RUN[2].builder
        def builder(name):
            fn,pr=old(name)
            def watch(c,m,w,*args):
                meter.width=w;return fn(c,m,w,*args)
            return watch,pr
        f.m.RUN[2].builder=builder
        search_fn=revised(f.search,[("ORIGIN+60","ORIGIN+cap"),("limit=[60]","limit=[cap]"),("T()<ORIGIN+55","T()<ORIGIN+cut"),("limit[0]=55;arm_alarm(ORIGIN+55)","limit[0]=cut;arm_alarm(ORIGIN+cut)"),('dest/"search",60','dest/"search",cap')],dict(cap=cap,cut=cap-3))
        search_fn(obj,"integrated",folder)
    def refine(events):
        raw_alarm=f.arm_alarm
        f.arm_alarm=lambda end:raw_alarm(min(end,f.ORIGIN+cap))
        v.refine(obj,folder,events)
    f.ORIGIN=T();rc=f.worker(search,(),f.ORIGIN+cap)
    ev=f.readlog(folder/"search.jsonl");seed=f.best(ev,cap-3);post=None
    if seed and seed["t"]<cap-3 and T()<f.ORIGIN+cap:
        post=f.worker(refine,([x for x in ev if x["t"]<=cap-3],),f.ORIGIN+cap)
    stop=T()-f.ORIGIN
    f.save(folder/"receipt.json",dict(method=arm,cap=cap,cpu=f.CPU,search=rc,post=post,origin=f.ORIGIN,wall=stop,charged=min(stop,cap)))
def lane(args):
    cpu,codes=args;v=initialize(cpu)
    for k in codes:
        o=next(o for o in v.m.u2.CASES if v.m.label(o)==k)
        for r in range(1,4):
            caps=(10,20) if (o["index"]+r)%2 else (20,10)
            for cap in caps:
                arms="NO" if (o["index"]+r+cap//10)%2 else "ON"
                for arm in arms:
                    d=S/"raw"/k/f"r{r}-{arm}-{cap}"
                    if not (d/"receipt.json").exists():cell(v,o,d,arm,cap)
        print("complete",k,flush=True)
def bench(v):
    for k in ("A01","C10"):
        o=next(o for o in v.m.u2.CASES if v.m.label(o)==k)
        api=v.m.RUN[0];flow=v.m.u2.make_flow(api,o,S/"fixed");parent=api.e.initial(flow)
        for rep in range(4):
            for arm in ("NO" if rep%2==0 else "ON"):
                dest=S/"fixed"/k/f"{rep}-{arm}";dest.mkdir(parents=True,exist_ok=True)
                measure=Measured(api.e.expand,arm,dest);measure.width=4
                start=T();measure(flow,0,[parent],"NT",start,start+60,dict(actions=[],groups=[]))
if __name__=="__main__":
    codes=["A01","A02","A03","A04","A05","A06","B07","B08","C09","C10","C11","C12"]
    cpus=sorted(os.sched_getaffinity(0));chosen=cpus[::2][:6]
    # Precompile once before launching independent core lanes.
    v=initialize(chosen[0]);bench(v)
    with ProcessPoolExecutor(len(chosen)) as ex:list(ex.map(lane,[(cpu,codes[i::len(chosen)]) for i,cpu in enumerate(chosen)]))
