"""Original M2 frequency joins and original continuous SAFE certification, per fixed deployment."""
from functools import lru_cache
from time import perf_counter
from unittest.mock import patch
import numpy as np
from common import search,bind_energy_search

def indices(code):return tuple((int(code)//27**(3-j))%27 for j in range(4))

class FrequencyOracle:
    def __init__(self,ev,clock,folder,emit,cfg):
        self.ev,self.clock,self.folder,self.emit,self.cfg=ev,clock,folder,emit,cfg
        import joint_thermal
        self.jt=joint_thermal
        self.energy_search=bind_energy_search(ev)
        self.kernel=lru_cache(maxsize=cfg["kernel_cache"])(self.compile)
    def compile(self,j,signature,opp):
        self.clock.check();s=self.ev._schedule(j,signature,opp);self.clock.check()
        if not s.deadline_feasible:return None
        t=perf_counter()
        kw=self.ev.events.thermal_kwargs(self.ev.platform,self.ev.opps[opp],self.ev.ambient,True,"base")
        k=self.jt.compile_scene(s.duration_ns*1e-9,s.active_w,s.transfer_w,kw)
        self.ev.seconds["kernel_compile_s"]+=perf_counter()-t
        self.ev.counters["kernel_compiles"]+=1
        self.clock.check();return k
    def evaluate(self,dep,group,baseline=False):
        began=self.clock.elapsed();self.emit("candidate_started",dict(dep=dep,group=group))
        tables=[]
        for j in range(4):
            sig=self.ev._signature(dep,j)
            tables.append([self.kernel(j,sig,i) for i in range(27)])
            self.emit("scene_built",dict(dep=dep,scene=j,legal_opps=[i for i,k in enumerate(tables[-1]) if k is not None]))
        # Original SetFreq on the exact independently initialized scene energies.
        t=perf_counter()
        def observe(d,j,i):
            self.clock.check();self.ev.counters["setfreq_requests"]+=1
            return None if tables[j][i] is None else float(tables[j][i].energy0)
        mapping=search.evaluate_mapping(dep,observe)
        self.ev.seconds["setfreq_lookup_s"]+=perf_counter()-t
        sf=None
        if mapping.valid==4:
            if baseline:
                for j,i in enumerate(mapping.opps):
                    self.clock.check();actual=self.ev.proxy(dep,j,i)
                    assert abs(actual-mapping.scores[j])<=1e-7
            sf=self.ev.replay(dep,mapping.opps);self.clock.check()
        sfrow=dict(indices=mapping.opps,scores=[x if np.isfinite(x) else None for x in mapping.scores],
            valid=mapping.valid,proxy_j=float(sum(mapping.scores)) if mapping.valid==4 else None,
            status=sf.status if sf else "DEADLINE",continuous_j=sf.energy_j if sf else None)
        self.emit("setfreq",dict(dep=dep,**sfrow))
        t=perf_counter();e0,energy,depth=self.energy_search(tables)
        self.ev.seconds["energy_join_s"]+=perf_counter()-t;self.clock.check()
        legal=np.isfinite(energy);assert int(legal.sum())==depth[-1]
        lower=float(np.min(energy[legal])) if legal.any() else None
        e0physical=None;states=None;best=None;certificate=False;no_safe=False;unresolved=0
        if e0 is None:
            certificate=True;no_safe=True
        else:
            e0physical=self.ev.replay(dep,indices(e0["code"]));self.clock.check()
            assert e0physical.status!="DEADLINE" and abs(e0physical.energy_j-energy[e0["code"]])<=1e-7
            if e0physical.status=="SAFE":
                best=e0;certificate=True
            else:
                raw_batch=self.jt.SceneKernel.batch
                def checked_batch(kernel,entries):
                    self.clock.check();before=kernel.fallback_calls
                    value=raw_batch(kernel,entries)
                    self.ev.counters["peak_fallback_integrations"]+=kernel.fallback_calls-before
                    self.ev.counters["screen_entries"]+=len(entries)
                    self.clock.check();return value
                t=perf_counter()
                with patch.object(self.jt.SceneKernel,"batch",checked_batch):
                    best,states,thermal_energy,thermal_depth=self.ev.unit.joint.joint_search(tables)
                self.ev.seconds["thermal_join_s"]+=perf_counter()-t;self.clock.check()
                assert np.array_equal(np.isfinite(thermal_energy),legal) and thermal_depth==depth
                assert not legal.any() or np.max(np.abs(energy[legal]-thermal_energy[legal]))<=1e-7
                unresolved=int(np.sum(states==3));certificate=unresolved==0;no_safe=certificate and best is None
                if best:
                    r=self.ev.replay(dep,indices(best["code"]));self.clock.check()
                    assert r.status=="SAFE" and abs(r.energy_j-energy[best["code"]])<=1e-7
        if best:
            r=self.ev._outcomes[dep,indices(best["code"])]
            minimum=float(np.min(energy[states==1])) if states is not None else lower
            bestrow=dict(dep=dep,indices=indices(best["code"]),energy_j=r.energy_j,peak_upper_c=max(r.upper),slack_ms=r.slack_ms)
        else:minimum=None;bestrow=None
        t=perf_counter()
        arrayfile=dep+".npz"
        values=dict(energy_j=energy)
        if states is not None:values["thermal_status"]=states
        np.savez_compressed(self.folder/arrayfile,**values)
        self.ev.seconds["array_archive_s"]+=perf_counter()-t;self.clock.check()
        row=dict(dep=dep,group=group,certificate=certificate,no_safe=no_safe,best=bestrow,
            exact_scope="all 27^4 scene frequency codes for this deployment only",
            e0=e0,e0_status=e0physical.status if e0physical else "DEADLINE",energy_lower_bound_j=lower,
            safe_minimum_j=minimum,deadline_sequences=int(legal.sum()),depth=depth,
            safe_sequences=int(np.sum(states==1)) if states is not None else None,
            unresolved=unresolved,setfreq=sfrow,arrays=arrayfile,begin_s=began,end_s=self.clock.elapsed(),
            elapsed_s=self.clock.elapsed()-began,cache=self.kernel.cache_info()._asdict())
        self.emit("candidate_complete",row)
        return row
