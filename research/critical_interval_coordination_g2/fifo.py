"""Conditional two-front FIFO model with exact post constraints and integer reference energy."""
from bisect import bisect_left
from dataclasses import dataclass
from heapq import nsmallest
from time import perf_counter
from assets import Frontier, Q

@dataclass(frozen=True,slots=True)
class State:
    fronts:tuple
    events:tuple
    cost:int

EMPTY=State((0,0,0,0),((),()),0)

class Compact:
    def __init__(self,p):
        self.p=p
        self.f=f=Frontier(p)
        self.ops=tuple(f.ops)
        self.n=len(p.req)
        self.q=tuple(p.dur(3*i+2,1,0) for i in range(self.n))
        self.d=tuple(r["deadline_tick"] for r in p.req)
        self.maxq=max(self.q)
        assert min(f.duration.values())>=2*self.maxq
        self.busy=[{op:f.busy[p.kinds[3*i+1],*op] for op in self.ops} for i in range(self.n)]
        self.dt=[{op:f.duration[p.kinds[3*i+1],*op] for op in self.ops} for i in range(self.n)]
        self.minimum=[min(v.values()) for v in self.busy]

    def step(self,s,i,op):
        f=self.f;u,k=op;a=u-2;other=1-a
        last=s.fronts[a];old=s.fronts[2+a]
        start=max(f.pre[i],last+5*(old!=k))
        end=start+self.dt[i][op]
        if end+self.q[i]>self.d[i] or end+5*(k!=0)>self.p.horizon:return None
        hist=s.events[other]
        for at in range(bisect_left(hist,(end-self.maxq+1,-1)),len(hist)):
            t,j=hist[at]
            if t>=end+self.maxq:break
            prior,after=(j,i) if (t,j)<(end,i) else (i,j)
            if min(t,end)+self.q[prior]+self.q[after]>self.d[after]:return None
        fronts=list(s.fronts);fronts[a]=end;fronts[2+a]=k
        ev=list(s.events);ev[a]=ev[a]+((end,i),)
        return State(tuple(fronts),tuple(ev),s.cost+self.busy[i][op]+f.gap(u,old,k,start-last))

    def replay(self,cfg):
        s=EMPTY
        for i,op in enumerate(cfg):
            s=self.step(s,i,op)
            if s is None:return None
        return s

    def score(self,s):return s.cost+self.f.tail(s.fronts)
    def joules(self,s):return self.f.base+Q(self.score(s),self.f.scale)

    def construct(self,width,until,priced=True):
        states=[(EMPTY,())]
        for i in range(self.n):
            expanded={}
            for s,path in states:
                if perf_counter()>=until:return None,i
                for op in self.ops:
                    nxt=self.step(s,i,op)
                    if nxt is None:continue
                    # This merging is only a beam heuristic. Exact DFS never merges histories.
                    key=nxt.fronts
                    if key not in expanded or nxt.cost<expanded[key][0].cost:
                        expanded[key]=(nxt,path+(op,))
            if not expanded:return None,i
            def rank(item):
                n=item[0]
                future=self.f.tail(n.fronts) if i+1==self.n else self.f.price(i+1,n.fronts) if priced else 0
                return n.cost+future,n.cost,n.fronts
            states=nsmallest(width,expanded.values(),key=rank)
        return states[0][1],self.n

    def search(self,base,opened,hint,until,rotate,on_candidate):
        # Each leaf reconstructs the complete FIFO stream. Fixed prefixes are visited once.
        allowed=[self.ops if i in opened else (base[i],) for i in range(self.n)]
        suffix=[0]*(self.n+1)
        for i in reversed(range(self.n)):
            suffix[i]=suffix[i+1]+min(self.busy[i][op] for op in allowed[i])
        first=self.replay(base);assert first is not None
        bound=self.score(first); lower=self.f.base+Q(suffix[0],self.f.scale)
        path=list(base);nodes=0;leaves=0;expired=False
        def visit(i,s):
            nonlocal nodes,leaves,bound,expired
            while True:
                nodes+=1
                if perf_counter()>=until:expired=True;return
                if s.cost+suffix[i]>bound:return
                if i==self.n:
                    leaves+=1;v=self.score(s)
                    if v<=bound and path!=list(base):
                        bound=v;on_candidate(tuple(path),v)
                    return
                if len(allowed[i])>1:break
                path[i]=base[i];s=self.step(s,i,base[i])
                if s is None:return
                i+=1
            options=[]
            for k,op in enumerate(self.ops):
                n=self.step(s,i,op)
                if n is not None:
                    options.append(((op!=hint[i],n.cost+self.f.price(i+1,n.fronts),op!=base[i],(k+rotate)%13),op,n))
            for _,op,n in sorted(options):
                if expired:return
                path[i]=op;visit(i+1,n)
        visit(0,EMPTY)
        return dict(nodes=nodes,leaves=leaves,status="TIME_LIMIT" if expired else "EXACT_REFERENCE",
                    reference_lower_J=str(lower),best_reference_J=str(self.f.base+Q(bound,self.f.scale)))
