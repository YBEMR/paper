"""Full-domain mode. Reuse E2-a frontier, union-of-occupation, gap and canonical order encoding."""
from collections import Counter
from math import floor
from g1io import *
from full_master import FullMaster
from master import solver, cp
from reference_objective import Core, Node
from thermal_bound import PJ, rates, activity_terms

class Full(Core):
    def __init__(self,p,seed,method,choices=None,objective=True):
        self.p=p
        self.H=p.horizon
        self.base,self.base_low=seed
        self.ids=tuple(range(p.n))
        self.master=FullMaster(p,self.base,self.ids,3,choices=choices)
        self.m=m=self.master.m
        self.states={}
        self.by_domain={}
        self.arcs=0
        self.static_sw=[]
        self.outside=set()
        self.terms={k:[] for k in ("activity","thermal","base","switch","external")}
        self.terms["external"]=[p.horizon*30_000_000]
        self.power={k:floor(PJ*v) for k,v in rates(p,method).items()}
        for (i,u,k),var in self.master.x.items():
            active,thermal=activity_terms(p,i,u,k,method)
            self.terms["activity"].append(floor(PJ*active)*var)
            self.terms["thermal"].append(floor(PJ*thermal)*var)
        self.domain_stats=[]
        for d in range(3):
            H=self.H
            tail=Node(-1,H,H,0,1,H,H,0,H,True)
            nodes=[tail]
            for i in self.ids:
                ops=[(u,k) for u,k in self.master.opts[i] if common.DOM[u]==d]
                if not ops: continue
                lo,finish=self.master.windows[i]
                hi=max(min(finish,H-5*(k!=0))-p.dur(i,u,k) for u,k in ops)
                lo=min(max(lo,5*(k!=0)) for u,k in ops)
                if choices is not None:
                    times=[z for u,k,z in choices[i] if (u,k) in ops]
                    lo,hi=max(lo,min(times)),min(hi,max(times))
                present=m.new_bool_var(f"use{d}_{i}")
                m.add(present==sum(self.master.x[i,u,k] for u,k in ops))
                s=m.new_int_var(0,H,"start")
                e=m.new_int_var(0,H,"end")
                for v,w in [(s,self.master.starts[i]),(e,self.master.ends[i])]:
                    m.add(v==w).only_enforce_if(present)
                    m.add(v==0).only_enforce_if(~present)
                mx=max(k for u,k in ops)
                freq=m.new_int_var(0,mx,"opp")
                m.add(freq==sum(k*self.master.x[i,u,k] for u,k in ops))
                nodes.append(Node(i,s,e,freq,present,lo,hi,mx,finish,False))
            self.by_domain[d]=nodes
            before=self.arcs
            self._path(d,nodes,[tail],-1,0,0)
            self.domain_stats.append(dict(domain=d,nodes=len(nodes),arcs=self.arcs-before))
        self.parts={k:sum(arr) for k,arr in self.terms.items()}
        self.total=sum(self.parts.values())
        if objective:
            m.minimize(self.total)
        for key,(_,_,_,bit,*_) in self.states.items():
            m.add_hint(bit,int(key in self.base_low))
        err=m.validate()
        if err: raise ValueError(err)

    def _gap_rights(self,*args):
        # The inherited path permits every physically distinct legal option.
        pass

    def stats(self):
        proto=self.m.Proto()
        return dict(variables=len(proto.variables),constraints=len(proto.constraints),domain_paths=self.domain_stats,
                    constraint_types=dict(Counter(c.WhichOneof("constraint") for c in proto.constraints)),
                    configuration_literals=len(self.master.x),objective_terms={k:len(v) for k,v in self.terms.items()})

    def forbid(self,plan):
        vs,vals=zip(*self.assignment(plan))
        self.m.add_forbidden_assignments(vs,[vals])
