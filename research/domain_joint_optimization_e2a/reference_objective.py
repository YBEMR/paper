"""Local optional domain paths with frontier propagation and full integer reference energy."""
from dataclasses import dataclass
from itertools import combinations
from assets_e2 import DOM,Q,Layout
from compact import idle_exact
from master import Master,cp

PJ=10**12
SW=1_500_000_000
def activity(p,i,u,k):
    idle,_,busy,_=p.exact[p.kinds[i],u,k]
    return round((busy-idle)*p.dur(i,u,k)*PJ/10000)
def error_bound(p):return Q(3*p.horizon+p.n,2*PJ)

@dataclass
class Access:
    sf:set
    st:set
    maps:dict                # Stage -> allowed devices, omitted means original device only
    reorder:object           # None = all; otherwise (unit, smaller ID, larger ID)
    insert:object            # same convention on a new device
    gaps:object=None         # None = E1 permissions; else subset of (domain,right Stage)
    max_changes:object=None

def default_access(p,rows,ids,g):
    ids=set(ids)
    return Access(ids if g else set(),ids if g else set(),
                  {i:{u for u,k in p.options[i]} for i in ids} if g==3 else {},
                  None if g>=2 else set(),None if g==3 else set())

@dataclass
class Node:
    i:int
    s:object
    e:object
    k:object
    present:object
    lo:int
    hi:int
    fmax:int
    endmax:int
    fixed:bool

class Core:
    def __init__(self,p,seed,ids,group,*,region=None,choices=None,flags=None,access=None,pin=None,objective=True):
        self.p=p;self.base,self.base_low=seed;self.ids=tuple(ids);self.H=H=p.horizon
        self.region=region;self.flags=None if flags is None else set(flags)
        self.access=access or default_access(p,self.base,ids,group)
        assert self.access.sf<=self.access.st<=set(ids)
        self.master=Master(p,self.base,ids,group,choices=choices,pin=pin);self.m=m=self.master.m
        self.prior=region["prior"] if region else {}
        self.layout=Layout(p,self.base) if region else None
        self.baselow=self.layout.normalize(self.base_low) if self.layout else set()
        self.terms={k:[] for k in ("activity","base","switch","external")}
        self.terms["external"].append(H*30_000_000)
        self.outside=set();self.static_sw=[];self.states={};self.by_domain={};self.arcs=0
        self.blocks=[];self.pin=pin
        self.power={key:round(x[0]*PJ/10000) for key,x in idle_exact(p).items()}
        self._rights(group,access is not None)
        for i,(u,k,s) in enumerate(self.base):
            if i not in self.master.opts:self.terms["activity"].append(activity(p,i,u,k))
            else:
                self.terms["activity"].extend(activity(p,i,w,f)*self.master.x[i,w,f] for w,f in self.master.opts[i])
        for d in range(3):self._domain(d,choices)
        self.parts={k:sum(v) for k,v in self.terms.items()};self.total=sum(self.parts.values())
        if objective:m.minimize(self.total)
        self.validation=m.validate()
        if self.validation:raise ValueError(self.validation)
        # Bound independent of mutually exclusive choices, including raw linear objective activity.
        max_rate=max(self.power.values());nodes=len(self.states)
        max_activity=sum(sum(abs(activity(p,i,u,k)) for u,k in self.master.opts[i]) if i in self.master.opts else
                         abs(activity(p,i,*self.base[i][:2])) for i in range(p.n))
        self.int_bound=max_activity+(3+3*nodes)*H*max_rate+SW*(2*p.n+2*nodes+6)+30_000_000*H
        assert self.int_bound<2**62

    def _rights(self,group,custom):
        if not custom:return                 # Original Pj already enforced by Master.
        a=self.access;m=self.m;master=self.master;changed=[]
        for i in self.ids:
            u,k,t=self.base[i]
            if i not in a.st:m.add(master.starts[i]==t)
            for w,f in master.opts[i]:
                x=master.x[i,w,f]
                if (i not in a.sf and (w,f)!=(u,k)) or w not in a.maps.get(i,{u}):m.add(x==0)
                if (w,f)!=(u,k):changed.append(x)
        if a.max_changes is not None:m.add(sum(changed)<=a.max_changes)
        if a.reorder is None and a.insert is None:return
        ids=set(self.ids)
        def at(i,u):
            if i not in ids:return int(self.base[i][0]==u)
            return sum(master.x[i,w,k] for w,k in master.opts[i] if w==u)
        for i in self.ids:
            for j,row in enumerate(self.base):
                if i==j or (j in ids and j<i):continue
                t=self.base[i][2];z=row[2]
                if abs(t-z)>500*(int(i in a.st)+int(j in a.st)):continue
                for u in {w for w,k in master.opts[i]}:
                    perm=a.reorder if self.base[i][0]==row[0]==u else a.insert
                    if perm is None or (u,min(i,j),max(i,j)) in perm:continue
                    right=at(j,u)
                    if isinstance(right,int) and right==0:continue
                    left=at(i,u);ii,jj=sorted((i,j),key=lambda n:(self.base[n][2],n))
                    e=master.ends[ii] if ii in ids else self.p.finish(ii,self.base[ii])
                    s=master.starts[jj] if jj in ids else self.base[jj][2]
                    # When both occupy u enforce reference chronological insertion/order.
                    m.add(e<=s+self.H*(2-left-right))

    def _static(self,d,seq,front,old):
        for s,e,k,i in seq:
            gap=max(0,s-front);h=max(e,front)-max(s,front);down=(d,i) in self.baselow
            sw=[]
            if down:sw.append((front,front+5,d,old,0));self.outside.add((d,i))
            if (0 if down else old)!=k:sw.append((s-5,s,d,0 if down else old,k))
            lowticks=gap-5 if down else 0
            self.terms["base"].append((gap-lowticks)*self.power[d,old]+lowticks*self.power[d,0]+h*self.power[d,k])
            self.terms["switch"].append(SW*len(sw));self.static_sw.extend(sw)
            front=max(front,e);old=k
        return front,old

    def _domain(self,d,choices):
        p=self.p;m=self.m;H=self.H;ids=set(self.ids);moving=[];bounds=[]
        for i in self.ids:
            ops=[(u,k) for u,k in self.master.opts[i] if DOM[u]==d]
            if self.pin is not None and i in self.pin:ops=[op for op in ops if op==tuple(self.pin[i][:2])]
            if not ops:continue
            maxk=max(k for u,k in ops);md=max(p.dur(i,u,k) for u,k in ops)
            if self.pin is not None and i in self.pin:
                u,k,s=self.pin[i];e=s+p.dur(i,u,k);node=Node(i,s,e,k,1,s,s,k,e,True)
            else:
                cand=([r[2] for r in choices[i] if tuple(r[:2]) in ops] if choices is not None else
                      [max(0,self.base[i][2]-500),min(H,self.base[i][2]+500)])
                lo,hi=min(cand),max(cand);present=m.new_bool_var(f"use{d}_{i}")
                m.add(present==sum(self.master.x[i,u,k] for u,k in ops))
                s=m.new_int_var(0,H,"start");e=m.new_int_var(0,H,"end")
                for v,w in [(s,self.master.starts[i]),(e,self.master.ends[i])]:
                    m.add(v==w).only_enforce_if(present);m.add(v==0).only_enforce_if(~present)
                k=m.new_int_var(0,maxk,"opp");m.add(k==sum(f*self.master.x[i,u,f] for u,f in ops))
                node=Node(i,s,e,k,present,lo,hi,maxk,min(H,hi+md),False)
            moving.append(node);bounds.append((node.lo,node.endmax))
        if self.region:
            # Include both the original source and the entire target envelope even for a pinned migration.
            bounds.extend((s,z) for i,u,k,s,b,z in self.region["envelopes"] if DOM[u]==d)
            bounds.extend((sig[2],sig[2]) for sig,(authorized,_) in self.prior.items() if sig[0]==d and authorized)
        seq=sorted((s,p.finish(i,(u,k,s)),k,i) for i,(u,k,s) in enumerate(self.base) if DOM[u]==d and i not in ids)
        seq.append((H,H,0,-1))
        if self.region and not bounds:
            self._static(d,seq,0,0);return
        start=0;end=len(seq)-1
        if self.region:
            lo=min(t for t,e in bounds);hi=max(e for t,e in bounds)
            while start<end and seq[start][0]<lo:start+=1
            frontier=max([0]+[e for s,e,k,i in seq[:start]])
            for j in range(start,end+1):
                s,e,k,i=seq[j]
                if s>hi and s>=frontier:end=j;break
                frontier=max(frontier,e)
        F,K=self._static(d,seq[:start],0,0)
        anchor=seq[end];self._static(d,seq[end+1:],anchor[1],anchor[2])
        fixed=[Node(i,s,e,k,1,s,s,k,e,True) for s,e,k,i in seq[start:end+1]]
        nodes=fixed+moving
        # Pinning can turn mobile rows into known keys; they then join the mandatory chain.
        fixed=sorted((n for n in nodes if n.fixed),key=lambda n:(n.s,n.e,n.k,n.i))
        self.blocks.append(dict(domain=d,prefix=len(seq[:start]),suffix=len(seq[end+1:]),entry=[F,K],
                                exit=[anchor[1],anchor[2]],represented=len(nodes)))
        self.by_domain[d]=nodes
        self._path(d,nodes,fixed,anchor[3],F,K)

    def _path(self,d,nodes,fixed,last,F,K):
        m=self.m;H=self.H;maxk=max(k for h,k in self.power if h==d)
        incoming={n.i:[] for n in nodes};outgoing={n.i:[] for n in nodes};outgoing[None]=[]
        frontier={};previous={};prior_k={}
        for n in nodes:
            i=n.i;pre=m.new_int_var(0,H,"previous_front");a=m.new_int_var(0,maxk,"previous_opp")
            previous[i]=pre;prior_k[i]=a
            f=m.new_int_var(0,H,"front");m.add_max_equality(f,[pre,n.e]);frontier[i]=f
            gap=m.new_int_var(0,H,"gap");m.add_max_equality(gap,[0,n.s-pre])
            h=m.new_int_var(0,H,"new_busy");m.add(h==f-pre-gap)
            early=m.new_bool_var(f"early{d}_{i}")
            diff=m.new_bool_var("changed");m.add(a!=n.k).only_enforce_if(diff);m.add(a==n.k).only_enforce_if(~diff)
            nz=m.new_bool_var("nonzero");m.add(n.k>=1).only_enforce_if(nz);m.add(n.k==0).only_enforce_if(~nz)
            count=m.new_int_var(0,2,"switches");m.add(count==diff).only_enforce_if(~early)
            m.add(count==1+nz).only_enforce_if(early);m.add(a>=1).only_enforce_if(early)
            m.add(gap>=5*count);m.add(gap>=6).only_enforce_if([early,~nz])
            if not n.fixed:
                m.add(pre==0).only_enforce_if(~n.present);m.add(a==0).only_enforce_if(~n.present)
            low=m.new_int_var(0,H,"low_dwell");m.add(low==gap-5).only_enforce_if(early);m.add(low==0).only_enforce_if(~early)
            def charge(freq,ticks):
                cost=m.new_int_var(0,H*max(self.power.values()),"residency_pJ")
                if isinstance(freq,int):m.add(cost==self.power[d,freq]*ticks)
                else:
                    rates=[self.power[d,k] for k in range(maxk+1)]
                    if len(set(rates))==1:
                        m.add(cost==rates[0]*ticks)
                    else:
                        for k,rate in enumerate(rates):
                            z=m.new_bool_var("at_opp");m.add(freq==k).only_enforce_if(z);m.add(freq!=k).only_enforce_if(~z)
                            m.add(cost==rate*ticks).only_enforce_if(z)
                return cost
            self.terms["base"].extend([charge(n.k,h),charge(a,gap-low),self.power[d,0]*low])
            self.terms["switch"].append(SW*count)
            self.states[d,i]=(n,pre,a,early,f,gap,h,count)
            self._gap_rights(d,n,pre,a,early)
        index={n.i:j for j,n in enumerate(fixed)}
        def rank(n):
            return (((n.s*(H+1)+n.e)*10+n.k)*(self.p.n+2)+n.i+1)
        def connect(left,right):
            arc=m.new_bool_var("successor");i=right.i
            outgoing[left.i if left else None].append(arc);incoming[i].append(arc)
            m.add(previous[i]==(frontier[left.i] if left else F)).only_enforce_if(arc)
            m.add(prior_k[i]==(left.k if left else K)).only_enforce_if(arc)
            if left and not (left.fixed and right.fixed) and left.hi>=right.lo:
                m.add(rank(left)<rank(right)).only_enforce_if(arc)
            self.arcs+=1
        for b in nodes:
            if b.lo<=fixed[0].hi:connect(None,b)
            for a in nodes:
                if a.i==b.i or a.i==last or a.lo>b.hi:continue
                if a.fixed and b.fixed:
                    if index.get(b.i)!=index[a.i]+1:continue
                elif any(a.hi<c.lo and c.hi<b.lo for c in fixed):continue
                connect(a,b)
        m.add(sum(outgoing[None])==1)
        for n in nodes:
            m.add(sum(incoming[n.i])==n.present)
            if n.i!=last:m.add(sum(outgoing[n.i])==n.present)

    def _gap_rights(self,d,n,pre,a,early):
        m=self.m;key=(d,n.i)
        if self.flags is not None:
            if key not in self.flags or (self.access.gaps is not None and key not in self.access.gaps):m.add(early==0)
            return
        limited=self.access.gaps is not None and key not in self.access.gaps
        protected=[];carry=[]
        for (dom,start,end,old,k),(variable,low) in self.prior.items():
            if dom!=d or not n.lo<=end<=n.hi or not old:continue
            if limited or not variable:
                protected.append((start,end,old,k,int(not low)))
                if low:carry.append((start,end,old,k))
        def variable(x):return m.new_constant(x) if isinstance(x,int) else x
        fields=[variable(x) for x in (pre,n.s,a,n.k)]
        if protected:m.add_forbidden_assignments([*fields,early],protected)
        if limited:
            if carry:m.add_allowed_assignments(fields,carry).only_enforce_if(early)
            else:m.add(early==0)

    def plan(self,sl):
        return self.master.rows(sl),frozenset(self.outside|{key for key,(_,_,_,b,*_) in self.states.items() if sl.value(b)})
    def switches(self,sl):
        sw=self.static_sw.copy()
        for (d,i),(n,pre,k,early,*_) in self.states.items():
            if not sl.value(n.present):continue
            a,b,t,s=map(sl.value,(k,n.k,pre,n.s))
            if sl.value(early):sw.append((t,t+5,d,a,0));a=0
            if a!=b:sw.append((s-5,s,d,a,b))
        return sorted(sw)
    def assignment(self,plan):
        rows,low=plan
        ans=[(self.master.starts[i],rows[i][2]) for i in self.ids]
        ans.extend((x,int(rows[i][:2]==(u,k))) for (i,u,k),x in self.master.x.items())
        ans.extend((st[3],int(key in low)) for key,st in self.states.items())
        return ans
    def candidates(self,seconds,limit=12,exclude=(),presolve=True):
        """Joint CP incumbents; replay a second call with physical no-goods for alternatives."""
        import time
        from master import solver
        m=self.m.clone()
        for plan in exclude:
            assignment=self.assignment(plan)
            m.add_forbidden_assignments([x for x,v in assignment],[[v for x,v in assignment]])
        core=self
        class Collect(cp.CpSolverSolutionCallback):
            def __init__(self):super().__init__();self.found=[]
            def on_solution_callback(self):
                item=(core.plan(self),{k:self.value(v) for k,v in core.parts.items()},core.switches(self))
                if len(self.found)<limit:self.found.append(item)
                else:self.found[-1]=item
        cb=Collect();sl=solver(seconds)
        sl.parameters.cp_model_presolve=presolve
        sl.parameters.max_presolve_iterations=2
        sl.parameters.linearization_level=1 if presolve else 0
        st=sl.solve(m,cb)
        if st==cp.MODEL_INVALID:raise ValueError(sl.response_stats())
        return cb.found,dict(status=sl.status_name(st),wall_s=sl.wall_time,bound_pJ=sl.best_objective_bound,
                             objective_pJ=sl.objective_value if cb.found else None,branches=sl.num_branches,conflicts=sl.num_conflicts)
