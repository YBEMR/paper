"""One scientific unit; all substantive stages share one monotonic deadline."""
import argparse
import inspect
import json
import os
import sys
import textwrap
from contextlib import contextmanager
from pathlib import Path
from time import perf_counter as clock, process_time
import psutil

HERE=Path(__file__).resolve().parent
B=Path(os.environ["U3B_SRC"])
ROOT=Path(os.environ["U3A_INPUTS"])
OUT=Path(os.environ["U4_RUNS"])
for k in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMBA_NUM_THREADS","NUMEXPR_NUM_THREADS"):os.environ[k]="1"
os.environ["U3B_RUNS"]=str(OUT)
sys.path.insert(0,str(B))
import worker as old
from fifo import Builder
from eventlog import Journal
import local_search
from guidance import Guidance
u,np=old.u,old.np

class Cutoff(Exception):pass

def genes(code):return tuple((3,v-10) if v>=10 else (2,v) for v in code)

class ListSink(list):
    def __init__(self,ctx,width,name):
        self.ctx,self.width,self.name=ctx,width,name
    def append(self,v):
        if self.name=="actions":
            v=tuple(x.item() if isinstance(x,np.generic) else x for x in v)
        elif self.name=="groups":
            v=json.loads(u.raw(v))
        self.ctx.j.emit("nt_"+self.name,self.width,v)
        # The runner examines its aggregate lists AFTER search. The complete records are on disk.
        if self.name=="beam":super().append(v)

class Unit:
    def __init__(self,obj,method,out,stack,cap):
        self.obj,self.method,self.out,self.stack=obj,method,out,stack
        self.start=clock()
        self.deadline=self.start+cap
        self.j=Journal(out)
        self.best=None
        self.phase="init"
        self.ncert=0
        self.seed=None
        self.seen=set()
        self.stages=[]
        self.attempts=[]
        self.parent_ids={}
        u.save(out/"start.json",dict(start=self.start,cap=cap))
    def elapsed(self):return clock()-self.start
    def check(self):
        if clock()>=self.deadline:raise Cutoff()
    def store(self,name,data):
        self.j.emit("store",name,json.loads(u.raw(data)))
    def checkpoint(self):
        self.j.emit("stages",self.stages)
    @contextmanager
    def time(self,phase):
        before=self.phase
        self.phase=phase
        self.j.emit("begin",phase,self.elapsed())
        try:
            self.check()
            yield
        finally:
            self.j.emit("end",phase,self.elapsed())
            self.phase=before
    def deliver(self,d,tr,config):
        t=self.elapsed()
        m=d["metrics"]
        r=dict(n=self.ncert,phase=self.phase,plan=d["plan_sha256"],status=m["status"],J=m["E_J"],
            bounds=m["E_bounds"],peak=max(m["peak_hi"]),slack=m["min_deadline_slack_ms"],kernel_s=d["cert_s"],t=t)
        self.j.emit("cert",r)
        self.check()
        if m["status"]=="SAFE" and (self.best is None or r["bounds"][1]<self.best["bounds"][0]):
            self.best=r
            self.j.emit("delivered",r,self.elapsed())
            if self.seed is None:self.seed=(config,d,tr)
        return d,tr
    def call(self,config,fn):
        self.check()
        self.ncert+=1
        self.j.emit("cert_start",self.ncert,self.phase,self.elapsed(),u.encoded(config))
        d,tr=fn()
        return self.deliver(d,tr,config)
    def models(self):
        api,fourth,_,self.causal=self.stack
        o=self.obj;label=o["case"]
        inp=HERE/"registration/inputs"/o["input"]
        b=inp.read_bytes()
        assert u.sha(b)==o["input_sha256"]
        fourth.CFG["instances"][label]=[list(o["word"]),1,35,1]
        if self.method!="Q4":
            self.flow=api.Flow(o["word"],35,label,self.out,inp)
            assert u.table(self.flow.p.req)==b
        if self.method not in ("NT10","NT60"):
            self.e=fourth.Engine(label,self.out)
            assert u.table(self.e.p.req)==b and self.e.p.horizon==o["horizon_ticks"]
    def certify(self,state,stage,rank,pred=None):
        assert state.code not in self.seen
        self.seen.add(state.code)
        cfg=genes(state.code)
        self.j.emit("choice",stage,rank,state.code)
        def fn():
            r=self.causal(self.flow,state.code)
            assert r is not None and r["slack"]==state.timing[6]
            return self.e.cert(cfg,r)
        return self.call(cfg,fn)
    def observe_builder(self):
        b=self.b
        original=b.expand
        def observed(p,j,pairs,offsets,local):
            key=p.code
            if key not in self.parent_ids:
                self.parent_ids[key]=len(self.parent_ids)
                self.j.emit("parent",self.parent_ids[key],key)
            ix=self.parent_ids[key]
            for v,q,delta in original(p,j,pairs,offsets,local):
                self.j.emit("q4_action",ix,j,v.pairs[-1],q,delta,v.timing)
                yield v,q,delta
        b.expand=observed
    def observe_nt(self):
        runner=self.stack[2]
        native_builder=runner.builder
        def builder(arm):
            original,progress=native_builder(arm)
            def wrapped(c,m,w,start,deadline,stage):
                for name in ("actions","groups","beam"):
                    stage[name]=ListSink(self,w,name)
                ordered=original(c,m,w,start,deadline,stage)
                self.j.emit("nt_terminals",w,[(x["id"],x["config"]) for x in ordered])
                return ordered
            return wrapped,progress
        runner.builder=builder
        return runner
    def nt(self,fallback=False):
        runner=self.observe_nt()
        native=self.flow.certify
        def certify(code):
            cfg=genes(code)
            return self.call(cfg,lambda:native(code))
        self.flow.certify=certify
        if fallback:
            build,_=runner.builder("NT")
            stage=dict(actions=[],groups=[],beam=[])
            order=build(self.flow,"NT",4,self.start,self.deadline,stage)
            for v in order[:4]:
                d,tr=certify(v["config"])
                if d["metrics"]["status"]=="SAFE":break
        else:
            runner.timed_run(self.flow,"NT",self.out/"nt",max(0,self.deadline-clock()))
    def group(self,init,mode,select,causal):
        cfg,r,d,tr=init
        eng=self.e
        if causal:eng.replay=lambda c:self.causal(self.flow,u.encoded(c))
        self.j.emit("group_seed",d["plan_sha256"],mode,select)
        native_cert=eng.cert
        eng.cert=lambda c,r,b=None:self.call(c,lambda:native_cert(c,r,b))
        source=textwrap.dedent(inspect.getsource(type(eng).candidates))
        marker="    proposed.sort("
        assert source.count(marker)==1
        source=source.replace(marker,'    record("group_proposed", bytes(encode(c)), proposed, scan, eligible)\n'+marker)
        env=dict(type(eng).candidates.__globals__,record=self.j.emit,encode=u.encoded)
        exec(compile(source,"<frozen group candidates + observation>","exec"),env)
        def observe(c,r,mode):
            self.check()
            pool,work=env["candidates"](eng,c,r,mode)
            self.j.emit("group_pool",u.encoded(c),[(u.encoded(x["c"]),x["ids"],x["u"],x["k"]) for x in pool],work)
            return pool,work
        eng.candidates=observe
        result=eng.optimize((cfg,r,d,tr),mode,select)
        self.j.emit("group_rounds",json.loads(u.raw(result["rounds"])),result["final"]["plan_sha256"])
    def native(self):
        # Observe every attempt of the original constructor without changing sort, beam, or tie breaks.
        e=self.e
        source=textwrap.dedent(inspect.getsource(type(e).construct))
        marker="                if nr is None:continue"
        assert source.count(marker)==1
        def emit(c,j,p,q,ext,r):
            if c not in self.parent_ids:
                self.parent_ids[c]=len(self.parent_ids)
                self.j.emit("parent",self.parent_ids[c],u.encoded(c))
            self.j.emit("native_action",self.parent_ids[c],j,p,q,u.encoded(ext),None if r is None else (r["cost"],r["tail"],r["slack"]))
        source=source.replace(marker,"                emit(c,j,pair,q,ext,nr)\n"+marker)
        scope=dict(type(e).construct.__globals__,emit=emit)
        exec(compile(source,"<frozen Q4 + observation>","exec"),scope)
        with self.time("construct"):cr,meta=scope["construct"](e,"quota",4);self.store("base",meta)
        if cr:
            cfg,r=cr
            with self.time("terminal"):d,tr=self.call(cfg,lambda:e.cert(cfg,r))
            if d["metrics"]["status"]=="SAFE":
                with self.time("group"):self.group((cfg,r,d,tr),"adaptive","union",False)
    def integrated(self):
        with self.time("construct"):
            self.b=Builder(self.flow,self.e)
            self.observe_builder()
            top=self.b.base()
            self.store("base",dict(layers=self.b.base_attempts,terminal=[v.code.hex() for v in top]))
        anchor=None
        with self.time("terminal"):
            for i,v in enumerate(top,1):
                d,tr=self.certify(v,"terminal",i)
                if i==1:anchor=(v,d,tr)
                if self.seed:break
        if self.seed is None and self.method!="Base":
            with self.time("repair"):
                if not top:
                    if len(self.b.layers)>2:local_search.backlog(self,True)
                else:
                    if self.method=="Previous":
                        def previous(b,anchor,d,tr):
                            m=d["metrics"];tick=m["peak_tick"][m["hotspot"]]
                            j=min(len(b.types)-1,int(tick//b.e.dur))
                            from types import SimpleNamespace
                            return SimpleNamespace(window=max(0,j-1),observation=dict(peak_tick=tick,peak_window=j+1))
                        local_search.Guidance=previous
                    local_search.thermal_block(self,"oo" if self.method=="Ordinary" else "ho",*anchor)
        if self.seed is None:
            with self.time("fallback"):self.nt(True)
        if self.seed:
            cfg,d,tr=self.seed
            with self.time("group"):
                r=self.causal(self.flow,u.encoded(cfg))
                self.group((cfg,r,d,tr),"adaptive","2",True)
    def paired(self,seedpath,gate):
        with self.time("handoff"):
            plan=u.read(seedpath/"plan.json")
            oldcert=u.read(seedpath/"certificate.json")
            cfg=tuple(tuple(a[:2]) for a in plan["rows"][1::3])
            if gate:
                self.e,init=u.intake(self.obj,seedpath,self.out,self.stack)
                _,r,d,tr=init
            else:
                r=self.causal(self.flow,u.encoded(cfg))
                built=self.e.build(cfg,r)
                assert u.raw(dict(case=self.obj["case"],rows=built["rows"],low=sorted(built["low"])))==u.raw(plan)
                d,tr=self.e.cert(cfg,r,built)
            assert d["plan_sha256"]==seedpath.name and u.raw(d["metrics"])==u.raw(oldcert["metrics"])
            with np.load(seedpath/"trace.npz") as f:assert np.array_equal(tr,f["events"])
            assert d["metrics"]["status"]=="SAFE"
            self.ncert+=1
            self.deliver(d,tr,cfg)
        with self.time("group"):self.group((cfg,r,d,tr),"fixed" if self.method.endswith("Fixed") else "adaptive","2",True)
    def run(self,seed):
        with self.time("model"):self.models()
        if seed:self.paired(seed,self.method.startswith("Gate"))
        elif self.method=="Q4":self.native()
        elif self.method.startswith("NT"):
            with self.time("nt"):self.nt()
        else:self.integrated()

def main():
    p=argparse.ArgumentParser()
    for name in ("case","method","out","cpu","cap"):p.add_argument(name)
    p.add_argument("--seed",type=Path)
    a=p.parse_args()
    psutil.Process().cpu_affinity([int(a.cpu)])
    out=Path(a.out)
    setup=clock();stack=u.stack();old.warm(stack)
    assert psutil.Process().cpu_affinity()==[int(a.cpu)]
    obj=next(o for o in u.read(HERE/"registration/cases.json") if o["id"]==a.case)
    u.save(out/"ready.json",dict(warm_s=clock()-setup,cpu=int(a.cpu)))
    begin=process_time()
    unit=Unit(obj,a.method,out,stack,float(a.cap))
    try:
        unit.run(a.seed);status="natural"
    except Cutoff:status="wall"
    unit.j.emit("return",status,unit.elapsed(),process_time()-begin)
    unit.j.close()
    u.save(out/"finish.json",dict(status=status,wall_s=unit.elapsed(),cpu_s=process_time()-begin))
if __name__=="__main__":main()
