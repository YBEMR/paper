"""Generic scene-count binding of M2's affine join / exact continuous thermal classification."""
from functools import lru_cache
from hashlib import sha256
from time import perf_counter
import numpy as np
from model import OPPS,joint_thermal,encoded

def decode(code,k):
    return tuple((int(code)//(27**(k-1-i)))%27 for i in range(k))

def enumerate_sequences(tables,initial,constrained,check):
    # Same cartesian scene join as the frozen M2 energy_search / joint_search.
    codes=np.zeros(1,dtype=np.int32);temps=np.array(initial)[None,:];energy=np.zeros(1)
    state=np.ones(1,dtype=np.uint8);depth=[]
    for table in tables:
        cs,ts,es,ss=[],[],[],[]
        for i,kernel in enumerate(table):
            check()
            if kernel is None or not len(codes):continue
            if constrained:
                e,t,status=kernel.batch(temps)
                s=np.where((state==2)|(status==joint_thermal.VIOLATION),2,
                           np.where((state==3)|(status!=joint_thermal.SAFE),3,1)).astype(np.uint8)
            else:
                delta=temps-kernel.initial
                e=kernel.energy0+delta@kernel.w
                t=kernel.final0+delta@kernel.F.T
                s=np.zeros(len(codes),dtype=np.uint8)
            cs.append(codes*27+i);ts.append(t);es.append(energy+e);ss.append(s)
        if not cs:
            return np.empty(0,dtype=np.int32),np.empty(0),np.empty(0,dtype=np.uint8),depth+[0]*(len(tables)-len(depth))
        codes,temps,energy,state=np.concatenate(cs),np.concatenate(ts),np.concatenate(es),np.concatenate(ss)
        depth.append(len(codes))
    return codes,energy,state,depth

class Exact:
    def __init__(self,ev,clock,emit):
        self.ev,self.clock,self.emit=ev,clock,emit
        self.best=None;self.best_energy=None;self.first=None
        self.e0=None;self.e0_energy=None;self.e0_complete=False
        self.phase2_complete=False;self.unresolved=0;self.coverage={"energy":0,"thermal":0}
        self.floors={"energy":None,"thermal":None}
        self.kernel=lru_cache(maxsize=4096)(self.compile)
        self.universal_lb=ev.instance.window_ns*1e-9*(ev.platform["power"]["board_W"]+
               sum(min(v) for v in ev.platform["power"]["idle_by_domain_W"].values()))
    def compile(self,j,signature,opp):
        self.clock.check()
        sched=self.ev._schedule(j,signature,opp)
        self.clock.check()
        if not sched.deadline_feasible:return None
        t=perf_counter()
        kw=self.ev.events.thermal_kwargs(self.ev.platform,OPPS[opp],self.ev.ambient,True,"base")
        kernel=joint_thermal.compile_scene(sched.duration_ns*1e-9,sched.active_w,sched.transfer_w,kw)
        self.ev.seconds["kernel_compile_s"]+=perf_counter()-t
        self.ev.counters["kernel_compiles"]+=1
        self.clock.check()
        return kernel
    def verify(self,key,energy):
        result=self.ev.replay(key[0],key[1:])
        self.clock.check()
        assert result.status!="DEADLINE" and abs(result.energy_j-energy)<=1e-7
        if result.status=="SAFE" and (self.best is None or result.energy_j<self.best_energy):
            self.best=key;self.best_energy=result.energy_j
            when=self.clock.elapsed()
            if self.first is None:self.first=when
            self.emit("incumbent",[key,result.energy_j],when)
        return result
    def scan(self,constrained):
        phase="thermal" if constrained else "energy"
        for dep in self.ev.instance.order:
            self.clock.check()
            tables=[]
            for j in range(len(self.ev.scenes)):
                signature=self.ev._signature(dep,j)
                tables.append([self.kernel(j,signature,i) for i in range(27)])
                self.emit("build",dict(dep=dep,scene=j,legal_opps=sum(k is not None for k in tables[-1])))
            before=sum(k.fallback_calls for t in tables for k in t if k is not None)
            t=perf_counter()
            codes,energy,state,depth=enumerate_sequences(tables,self.ev.instance.initial,constrained,self.clock.check)
            self.ev.seconds["query_"+phase+"_s"]+=perf_counter()-t
            self.clock.check()
            after=sum(k.fallback_calls for tb in tables for k in tb if k is not None)
            self.ev.counters["peak_fallback_integrations"]+=after-before
            valid=np.flatnonzero(state==1) if constrained else np.arange(len(codes))
            idx=int(valid[np.argmin(energy[valid])]) if len(valid) else None
            candidate=None
            if idx is not None:
                value=float(energy[idx]);key=(dep,*decode(codes[idx],len(tables)))
                self.floors[phase]=value if self.floors[phase] is None else min(value,self.floors[phase])
                candidate=dict(key=key,energy_j=value)
                if constrained:
                    if self.best is None or value<self.best_energy-1e-9:self.verify(key,value)
                elif self.e0 is None or value<self.e0_energy-1e-9:
                    self.e0,self.e0_energy=key,value
                    self.verify(key,value)
            if constrained:self.unresolved+=int(np.sum(state==3))
            self.coverage[phase]+=1
            self.emit("deployment",dict(phase=phase,dep=dep,completed=self.coverage[phase],candidate=candidate,
                 deadline_valid=len(codes),depth=depth,safe=int(np.sum(state==1)) if constrained else None,
                 unresolved=int(np.sum(state==3)) if constrained else None,
                 code_sha=sha256(codes.tobytes()).hexdigest(),energy_sha=sha256(energy.tobytes()).hexdigest(),
                 status_sha=sha256(state.tobytes()).hexdigest() if constrained else None))
    def run(self,cutoff_type):
        stop="completed";certificate=False;infeasible=False
        try:
            self.scan(False);self.e0_complete=True
            self.emit("energy_complete",dict(key=self.e0,energy_j=self.e0_energy))
            if self.e0 is None:
                certificate=True;infeasible=True
            elif self.verify(self.e0,self.e0_energy).status=="SAFE":
                certificate=True
            else:
                self.scan(True);self.phase2_complete=True
                certificate=self.unresolved==0
                infeasible=certificate and self.best is None
            if certificate:
                self.emit("certificate",dict(domain=len(self.ev.instance.order),minimum_safe_j=self.best_energy,
                       unconstrained_j=self.e0_energy,proven_no_safe=infeasible,unresolved=self.unresolved,
                       lower_bound_j=self.floors["thermal"] if self.phase2_complete else self.floors["energy"],
                       numerical_tolerance_j=1e-7,
                       scope="exact declared concrete diagnostic domain; not the unrestricted partition catalog"))
        except cutoff_type:
            stop="budget_unresolved"
        return dict(winner=self.best,first_safe_s=self.first,reason=stop,certificate=certificate,
             proven_no_safe=infeasible,e0_proven=self.e0_complete,e0_key=self.e0,e0_j=self.e0_energy,
             coverage=self.coverage,domain=len(self.ev.instance.order),unresolved=self.unresolved,
             lower_bound_j=(self.floors["thermal"] if self.phase2_complete and certificate else
                self.floors["energy"] if self.e0_complete and self.floors["energy"] is not None else self.universal_lb),
             cache=self.kernel.cache_info()._asdict())
