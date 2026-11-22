"""Run-local adaptation of the registered SceneKernel. Physical labels and full peak bounds survive."""
from collections import Counter, OrderedDict
from dataclasses import asdict
from types import SimpleNamespace
from time import perf_counter

import numpy as np
from physical import Physical


class Evaluation(Physical):
    def __init__(self,root,case,stages,arm,meter,flow,cfg):
        self.m,self.flow,self.cfg,self.arm=meter,flow,cfg,arm
        super().__init__(root,case,stages)
        import joint_thermal
        self.jt=joint_thermal
        self.raw_heat=self.events.evaluate_thermal
        self.events.evaluate_thermal=self.heat
        self.phase="search"
        self.cache=OrderedDict()
        self.known=OrderedDict()
        self.bytes=self.max_bytes=self.max_entries=0
        self.means=Counter()
        self.gate_shapes=set()
        self.post_start=False
        self.seq=0
        self.context=None
        self.current=None

    def identify(self):
        # An index interns this full immutable context within this private run.
        self.context=dict(stream=self.identity,ambient=self.ambient,precision="FP16",leakage=True,
                          variation="base",initial=self.platform["thermal"]["initial_C"],
                          scenes=[(s.index,s.name,s.start_ns,s.service_end_ns,s.end_ns) for s in self.scenes],
                          physical_labels=True,block_s=self.jt.BLOCK_SECONDS,guard_c=self.jt.SCREEN_GUARD_C)

    def signature(self,d,j,i):
        return (j,i,self._signature(d,j))

    def known_add(self,key):
        if key not in self.known:
            self.known[key]=None
            if len(self.known)>self.cfg["known_scene_entries"]:
                self.known.popitem(last=False)

    def put(self,key,obj,size):
        if key in self.cache:
            return
        self.cache[key]=(obj,size)
        self.bytes+=size
        if len(self.cache)>self.cfg["kernel_entries"]:
            _,(_,removed)=self.cache.popitem(last=False)
            self.bytes-=removed
            self.m.counts["cache_evictions"]+=1
        self.max_bytes=max(self.max_bytes,self.bytes)
        self.max_entries=max(self.max_entries,len(self.cache))

    def call(self,kind,args,began,value):
        end=perf_counter()-self.m.start
        self.flow.add([self.seq,kind,args,began,end,value])
        self.seq+=1

    def _make_schedule(self,j,signature,opp):
        with self.m.doing("dispatch"):
            self.m.counts["dispatch_misses"]+=1
            return super()._make_schedule(j,signature,opp)

    def _get_proxy(self,j,signature,opp):
        self.m.counts["proxy_scalar_misses"]+=1
        key=(j,opp,signature)
        if self.arm!="A" and key in self.cache:
            item=self.cache[key][0]
            if item is not None and not hasattr(item,"deadline_feasible"):
                if np.array_equal(item.initial,self.platform["thermal"]["initial_C"]):
                    self.m.counts["proxy_exact_anchor_reuses"]+=1
                    return float(item.base["energy_J"])
        return super()._get_proxy(j,signature,opp)

    def proxy(self,d,j,i):
        began=perf_counter()-self.m.start
        self.m.counts["proxy_requests"]+=1
        self.phase="proxy"
        try:
            with self.m.doing("proxy_lookup"):
                result=super().proxy(d,j,i)
                if self.arm!="A":
                    self.known_add(self.signature(d,j,i))
        finally:
            self.phase="search"
        self.call("proxy",[d,j,i],began,result)
        return result

    def _bound_schedule(self,platform,scene,d,opp):
        j,i=scene.index,self.opp_index[opp]
        if self.phase!="search":
            self.m.counts["nested_bound_schedule"]+=1
            self.current=self.signature(d,j,i) if self.phase=="replay" and self.arm!="A" else None
            return super()._bound_schedule(platform,scene,d,opp)
        began=perf_counter()-self.m.start
        self.m.counts["deadline_requests"]+=1
        with self.m.doing("deadline_screen"):
            key=self.signature(d,j,i)
            item=self.cache.get(key)
            if self.arm!="A" and item and hasattr(item[0],"deadline_feasible"):
                self.m.counts["deadline_reject_hits"]+=1
                self.cache.move_to_end(key)
                sched=item[0]
            else:
                before=self._schedule.cache_info().hits
                sched=super()._bound_schedule(platform,scene,d,opp)
                if not sched.deadline_feasible and self._schedule.cache_info().hits>before:
                    self.m.counts["original_schedule_reject_hits"]+=1
                if self.arm!="A" and not sched.deadline_feasible:
                    self.put(key,SimpleNamespace(deadline_feasible=False,min_slack_ns=sched.min_slack_ns),0)
            if self.arm!="A":
                self.known_add(key)
            if not sched.deadline_feasible:
                self.m.counts["deadline_rejections"]+=1
        self.call("deadline",[d,j,i],began,[bool(sched.deadline_feasible),int(sched.min_slack_ns)])
        return sched

    def cost(self,key):
        """Read-only preview. Unknown contexts and negative entries have no numerical price."""
        signatures=[self.signature(key[0],j,i) for j,i in enumerate(key[1:])]
        if any(k not in self.known for k in signatures):
            return None
        if any(k in self.cache and hasattr(self.cache[k][0],"deadline_feasible") for k in signatures):
            return None
        n=self.m.counts
        if not n["kernel_builds"] or not n["kernel_queries"] or not n["peak_replays"]:
            return None
        cold=sum(k not in self.cache for k in signatures)
        per_query=(self.means["query"]+self.means["peak"])/n["kernel_queries"]
        return cold*self.means["build"]/n["kernel_builds"]+4*per_query,cold

    def replay(self,d,indices):
        began=perf_counter()-self.m.start
        self.m.counts["full_requests"]+=1
        self.phase="replay"
        try:
            with self.m.doing("continuous_dispatch"):
                if self.arm!="A" and self.post_start:
                    with self.m.doing("cost_observation"):
                        quote=self.cost((d,*indices))
                        if quote: self.gate_shapes.add(quote[1])
                out=super().replay(d,indices)
                physical=self._physical[d,tuple(indices)]
        finally:
            self.phase="search"
        self.call("full",[d,list(indices)],began,[asdict(out),physical["scene_rows"]])
        return out

    def heat(self,dt,activity,*,transfer_W,**kw):
        if self.phase!="replay" or self.arm=="A":
            label={"proxy":"setfreq_thermal","replay":"original_continuous"}.get(self.phase,"final_integral")
            with self.m.doing(label):
                self.m.counts[label+"_calls"]+=1
                return self.raw_heat(dt,activity,transfer_W=transfer_W,**kw)
        t=perf_counter()
        with self.m.doing("kernel_lookup"):
            key=self.current
            cached=self.cache.get(key)
            if cached: self.cache.move_to_end(key)
        lookup=perf_counter()-t
        if cached:
            kernel=cached[0]
            self.m.counts["legal_kernel_hits"]+=1
        else:
            t=perf_counter()
            with self.m.doing("kernel_build"):
                jt=self.jt
                class Kernel(jt.SceneKernel):
                    def replay(k,entry,trace=False):
                        record=super(Kernel,k).replay(entry,trace)
                        if not hasattr(k,"base"):
                            k.base=record
                        return record
                kernel=Kernel(dt,activity,transfer_W,kw,jt.BLOCK_SECONDS)
                size=sum(a.nbytes for a in vars(kernel).values() if isinstance(a,np.ndarray))
                self.put(key,kernel,size)
                self.m.counts["kernel_builds"]+=1
                self.m.counts["build_integrations"]+=1+len(kernel.upper)
            self.means["build"]+=perf_counter()-t
        start=perf_counter()
        entry=np.asarray(kw["initial_C"],dtype=float)
        with self.m.doing("affine_query"):
            delta=entry-kernel.initial
            energy=kernel.energy0+delta@kernel.w
            final=kernel.final0+delta@kernel.F.T
            modal=np.ascontiguousarray((delta@kernel.inverse.T).reshape(1,4))
        with self.m.doing("peak_screen"):
            code=self.jt._screen(modal,kernel.u,kernel.left_exp,kernel.right_exp,kernel.upper,
                                 kernel.witness_temp,kernel.witness_exp,kernel.limits)[0]
            self.m.counts["kernel_queries"]+=1
        self.means["query"]+=perf_counter()-start+lookup
        if code==self.jt.NEEDS_REPLAY or not np.array_equal(entry,kernel.initial):
            uncertain=code==self.jt.NEEDS_REPLAY
            label="peak_fallback" if uncertain else "peak_certificate_completion"
            t=perf_counter()
            with self.m.doing(label):
                original=kernel.replay(entry)
                self.m.counts[label+"_calls"]+=1
                self.m.counts["peak_replays"]+=1
            self.means["peak"]+=perf_counter()-t
        else:
            original=kernel.base
            self.m.counts["exact_anchor_queries"]+=1
        with self.m.doing("affine_query"):
            screen={self.jt.SAFE:"SAFE",self.jt.VIOLATION:"VIOLATION",self.jt.UNRESOLVED:"UNRESOLVED"}
            if code!=self.jt.NEEDS_REPLAY and screen[code]!=original["thermal_status"]:
                raise ValueError("Continuous screening classification disagrees")
            if abs(energy-original["energy_J"])>1e-7 or np.max(np.abs(final-original["final_C"]))>1e-7:
                raise ValueError("Affine response disagrees with exact certificate")
            # Preserve the frozen strict-< optimizer's ties. The original peak record already
            # contains identically integrated J and outlet, both checked against the affine query.
            return original

    def certificate(self,key):
        with self.m.doing("final_certificate"):
            self.phase="certificate"
            try:
                if self.arm!="A":
                    # Reintegrate the winner independently. Do not take the previous whole-result hit.
                    from unittest.mock import patch
                    with patch.object(self.events,"time_scene",self._bound_schedule):
                        ref=self.events.replay_sequence(self.platform,self.scenes,key[0],
                            [self.opps[i] for i in key[1:]],self.ambient,leakage=True,variation="base",reset=False)
                    if ref!=self._physical[key[0],tuple(key[1:])]:
                        raise ValueError("Original full-window certificate mismatch")
                return self.evidence(key[0],key[1:])
            finally:
                self.phase="search"

