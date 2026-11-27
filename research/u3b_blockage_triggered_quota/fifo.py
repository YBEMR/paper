"""Complete release-order replay of each prefix. Integer reference scoring matches frozen Q4."""
from dataclasses import dataclass
from itertools import product

import numpy as np
from numba import njit

PAIRS = list(product(range(10),range(3)))
OFFSETS = [(0,0)]+[(x,y) for k in (1,-1,2,-2) for x,y in ((k,0),(0,k),(k,-k))]

@njit(cache=True)
def timing(config, kinds, ready, deadlines, post_length, lengths, energy, rates, switch, horizon, boundary):
    n=len(config)
    finish=np.zeros(2,np.int64)
    levels=np.zeros(2,np.int64)
    ends=np.empty(n,np.int64)
    cost=0
    for i in range(n):
        u=int(config[i]>=10)
        level=int(config[i])-10*u
        old=levels[u]
        start=max(ready[i],finish[u]+5*(old!=level))
        gap=start-finish[u]
        hold=rates[u,old]*gap+switch*(old!=level)
        drop=rates[u,old]*5+switch*(1+(level!=0))
        early=old>0 and gap>=5*(1+(level!=0)) and drop<hold
        cost+=energy[kinds[i],u,level]+(drop if early else hold)
        finish[u]=start+lengths[kinds[i],u,level]
        ends[i]=finish[u]
        levels[u]=level
    tail=0
    tail_late=0
    for u in range(2):
        old=levels[u]
        gap=horizon-finish[u]
        hold=rates[u,old]*gap+switch*(old!=0)
        drop=rates[u,old]*5+switch
        tail+=min(hold,drop) if old>0 and gap>=5 else hold
        tail_late=max(tail_late,5*(old!=0)-gap)
    slack=10**9
    backlog=0
    post=0
    for i in np.argsort(ends,kind="mergesort"):
        post=max(ends[i],post)+post_length[i]
        backlog+=int(post>boundary)
        slack=min(slack,deadlines[i]-post)
    late=max(0,-slack,tail_late,post-horizon)
    return finish[0],finish[1],levels[0],levels[1],cost,tail,slack,backlog,post,late

@dataclass(slots=True)
class State:
    code: bytes
    timing: tuple
    pairs: tuple
    @property
    def ordinary(self):
        f,g,_,_,cost,tail,_,backlog,post,late=self.timing
        return late,backlog,cost+tail,max(f,g,post),self.code

class Builder:
    def __init__(self,flow,engine):
        self.e=engine
        self.flow=flow
        self.journal=[]
        self.replays=0
        self.closed=False
        E=engine
        lengths=np.zeros((2,2,10),dtype=np.int64)
        energy=np.zeros_like(lengths)
        rates=np.zeros((2,10),dtype=np.int64)
        for i,kind in enumerate("AB"):
            for unit,level in [(u,k) for u,count in ((2,10),(3,3)) for k in range(count)]:
                lengths[i,unit-2,level]=E.length[kind,unit,level]
                energy[i,unit-2,level]=E.inc[kind,unit,level]
                rates[unit-2,level]=E.rate[unit,level]
        assert (int(np.max(energy))*E.n+int(np.max(rates))*2*E.p.horizon+2*E.n*E.sw)<2**63
        self.args=(flow.kinds,np.array(E.a),np.array(E.D),np.array(E.q),lengths,energy,rates,E.sw,E.p.horizon)
        self.types=[flow.kinds[ids] for ids in E.groups]
        self.counts=[tuple(int(sum(t==k)) for k in (0,1)) for t in self.types]
        self.root=State(b"",(0,)*10,())
        self.layers=[[self.root]]
        self.ext_cache={}
        self.base_attempts=[]
    def expand(self,parent,j,pairs,offsets,local):
        E=self.e
        a,b=self.counts[j]
        f,g,k,l=parent.timing[:4]
        for pair in pairs:
            x,y=E.quota(dict(f=(f,g),k=(k,l)),j,pair,(a,b))
            for dx,dy in offsets:
                q=(x+dx,y+dy)
                if not (0<=q[0]<=a and 0<=q[1]<=b):
                    continue
                if local and self.replays>=14000:
                    self.closed=True
                    return
                key=(j,pair,q)
                ext=self.ext_cache.get(key)
                if ext is None:
                    ext=self.flow.extension(self.types[j],a,b,*pair,*q)
                    self.ext_cache[key]=ext
                cfg=parent.code+ext
                result=timing(np.frombuffer(cfg,np.uint8),*self.args,(j+1)*E.dur)
                if local:
                    self.replays+=1
                yield State(cfg,result,parent.pairs+(pair,)),q,(dx,dy)
    def base(self):
        for j in range(len(self.types)):
            states={}
            trials=0
            for parent in self.layers[-1]:
                for v,_,_ in self.expand(parent,j,PAIRS,[(0,0)],False):
                    trials+=1
                    if v.timing[-1]==0:
                        states.setdefault(v.code,v)
            last=j+1==len(self.types)
            scores=sorted(states.values(),key=lambda v:(v.timing[4]+(v.timing[5] if last else 0),v.code))
            self.layers.append(scores[:4])
            self.base_attempts.append(dict(window=j+1,trials=trials,distinct=len(scores),
                retained=[v.code.hex() for v in scores[:4]]))
            if not scores or last:
                return scores[:12]

def unique(states):
    by_code={}
    for v in states:
        by_code.setdefault(v.code,v)
    return list(by_code.values())

