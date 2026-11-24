"""Compose frozen M2 affine kernels over actual GPU busy/idle intervals."""
from pathlib import Path
import sys
from dataclasses import asdict
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'research/multidnn_diagnostics'))
from instance import Instance,events
import joint_thermal as thermal

class Kernel:
    def __init__(self,inst,scene,dep,opp,mode,schedule):
        self.dep=dep;self.opp=opp;self.mode=mode;self.scene=scene;self.schedule=schedule
        self.initial=np.full(4,30.);self.parts=[];self.offsets=[];self.seconds=scene.duration_ns*1e-9
        levels=np.full(len(schedule.duration_ns),opp[1],dtype='<U1')
        if mode=='idle_zero':levels[schedule.active_w[:,1]==0]='L'
        edges=np.r_[0,np.flatnonzero(levels[1:]!=levels[:-1])+1,len(levels)]
        start=0.;F=np.eye(4);b=self.initial.copy();w=np.zeros(4);e=0.
        for a,z in zip(edges,edges[1:]):
            kw=events.thermal_kwargs(inst.platform,opp[0]+levels[a]+opp[2],inst.ambient,True,'base')
            kw['initial_C']=self.initial.tolist()
            k=thermal.compile_scene(schedule.duration_ns[a:z]*1e-9,schedule.active_w[a:z],schedule.transfer_w[a:z],kw)
            self.offsets.append(start);self.parts.append(k);start+=k.dt.sum()
            e+=k.energy0+(b-k.initial)@k.w;w+=F.T@k.w
            b=k.final0+k.F@(b-k.initial);F=k.F@F
        self.F=F;self.final0=b;self.w=w;self.energy0=e
        assert abs(start-self.seconds)<1e-8
    def affine(self,T):
        d=np.asarray(T)-self.initial
        return self.energy0+d@self.w,self.final0+d@self.F.T
    def batch_safe(self,T):
        T=np.asarray(T);status=np.ones(len(T),dtype=np.int8);state=T.copy()
        for k in self.parts:
            active=np.flatnonzero(status==1)
            if not len(active):break
            _,end,s=k.batch(state[active]);state[active]=end;status[active]=s
        return status
    def replay(self,T,trace=False):
        state=np.array(T);lo=state.copy();hi=state.copy()
        totals={x:np.zeros(4) for x in ['idle_J','activity_J','leakage_J']}
        totals.update(energy_J=0.,common_J=0.,transfer_J=0.)
        times=[];temps=[];parts=[]
        for off,k in zip(self.offsets,self.parts):
            out=k.replay(state,trace=trace)
            for key in totals:totals[key]+=out[key]
            lo=np.maximum(lo,out['peak_lower_C']);hi=np.maximum(hi,out['peak_upper_C'])
            parts.append(dict(start_s=off,end_s=off+k.dt.sum(),entry_C=state.tolist(),final_C=out['final_C'],
                peak_lower_C=out['peak_lower_C'],peak_upper_C=out['peak_upper_C'],energy_J=out['energy_J']))
            if trace:times.extend((off+out['trace_time_s']).tolist());temps.extend(out['trace_C'].tolist())
            state=np.array(out['final_C'])
        e,end=self.affine(np.array(T))
        assert abs(e-totals['energy_J'])<1e-7 and np.max(np.abs(end-state))<1e-7
        p={k:(v.tolist() if isinstance(v,np.ndarray) else float(v)) for k,v in totals.items()}
        p.update(entry_C=list(T),final_C=state.tolist(),peak_lower_C=lo.tolist(),peak_upper_C=hi.tolist(),parts=parts,
            thermal_status='VIOLATION' if max(lo)>80 else 'SAFE' if max(hi)<=80 else 'UNRESOLVED')
        return p,times,temps

class Table:
    def __init__(self,inst,check):self.inst=inst;self.check=check;self.cache={};self.schedules={};self.calls=0;self.hits=0
    def get(self,j,dep,opp,mode):
        self.check();scene=self.inst.scenes[j]
        active=sorted({q.app for q in scene.requests})
        signature=tuple((a,tuple(map(tuple,self.inst.frozen['deployments'][dep]['stages'][str(a)]))) for a in active)
        key=(j,signature,opp)
        if key not in self.schedules:self.schedules[key]=events.time_scene(self.inst.platform,scene,dep,opp)
        schedule=self.schedules[key]
        if not schedule.deadline_feasible:return None
        kkey=key+(mode,)
        if kkey not in self.cache:self.cache[kkey]=Kernel(self.inst,scene,dep,opp,mode,schedule);self.calls+=1
        else:self.hits+=1
        return self.cache[kkey]

def certificate(inst,tables,indices):
    T=inst.initial;total=0.;peak=np.array(T);ledger=[];rows=[];scenes=[];times=[];temps=[]
    for j,i in enumerate(indices):
        k=tables[j][i];assert k is not None
        p,t,v=k.replay(T,True);T=p['final_C'];total+=p['energy_J'];peak=np.maximum(peak,p['peak_upper_C'])
        scene=inst.scenes[j];sched=k.schedule
        ledger.extend(dict(id=q.id,app=q.app,release_ns=q.release_ns+scene.start_ns,deadline_ns=q.deadline_ns+scene.start_ns,
            completion_ns=sched.completions_ns[q.id]+scene.start_ns) for q in scene.requests)
        rows.extend(dict(asdict(r),start_ns=r.start_ns+scene.start_ns,end_ns=r.end_ns+scene.start_ns) for r in sched.rows)
        scenes.append(dict(index=j,scene=scene.name,path='D038' if i<27 else 'D040',opp=events.OPPS[i%27],**p,
            start_ns=scene.start_ns,end_ns=scene.end_ns,min_slack_ms=sched.min_slack_ns/1e6))
        times.extend((np.array(t)+scene.start_ns*1e-9).tolist());temps.extend(v)
    assert len(ledger)==len({q['id'] for q in ledger})==inst.required==500
    deadline=all(q['completion_ns']<=q['deadline_ns'] for q in ledger)
    return dict(energy_J=total,peak_c=float(max(peak)),peak_by_node_C=peak.tolist(),deadline_ok=deadline,
        min_slack_ms=min(q['deadline_ns']-q['completion_ns'] for q in ledger)/1e6,
        SAFE=deadline and all(s['thermal_status']=='SAFE' for s in scenes),scenes=scenes,ledger=ledger,rows=rows),np.array(times),np.array(temps)
