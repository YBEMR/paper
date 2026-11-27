"""Exact integer timing tests for a fixed downstream sequence, in 0.1 ms ticks."""
import numpy as np
from numba import njit

@njit(cache=True)
def full_timing(code, ready, deadlines, post_dur, lengths, horizon):
    """Two FIFO devices, then merge by (completion time, original request index)."""
    n=len(code)
    queue=np.empty((2,n),np.int64)
    ends=np.empty(n,np.int64)
    size=np.zeros(2,np.int64)
    free=np.zeros(2,np.int64)
    old=np.zeros(2,np.int64)
    for i in range(n):
        dev=int(code[i]>=10);k=int(code[i])%10
        free[dev]=max(ready[i],free[dev]+5*(old[dev]!=k))+lengths[i,code[i]]
        ends[i]=free[dev];old[dev]=k
        queue[dev,size[dev]]=i;size[dev]+=1
    for dev in range(2):
        if free[dev]+5*(old[dev]!=0)>horizon:return False,-2,free[dev]+5*(old[dev]!=0)-horizon
    pointer=np.zeros(2,np.int64);post=0
    for unused in range(n):
        if pointer[0]==size[0]:dev=1
        elif pointer[1]==size[1]:dev=0
        else:
            a=queue[0,pointer[0]];b=queue[1,pointer[1]]
            dev=int(ends[b]<ends[a] or (ends[a]==ends[b] and b<a))
        i=queue[dev,pointer[dev]];pointer[dev]+=1
        post=max(post,ends[i])+post_dur[i]
        if post>deadlines[i]:return False,i,post-deadlines[i]
    return post<=horizon,-1,max(0,post-horizon)

@njit(cache=True)
def suffix_feasible(ids, parent, ready, limits, lengths, horizon, tick, last):
    """Independent forward oracle, including every downstream release and domain exit."""
    for i in ids:
        k=int(parent[i])%10
        tick=max(ready[i],tick+5*(last!=k))+lengths[i,parent[i]]
        if tick>limits[i]:return False
        last=k
    return tick+5*(last!=0)<=horizon

class Timing:
    def __init__(self,eng):
        self.ready=np.array(eng.a,np.int64)
        self.deadlines=np.array(eng.D,np.int64)
        self.q=np.array(eng.q,np.int64)
        self.limits=self.deadlines-self.q
        self.horizon=int(eng.p.horizon)
        profile=np.array([[eng.length[t,2+int(k>=10),k%10] for k in range(13)] for t in "AB"],np.int64)
        self.lengths=profile[np.array(eng.kindidx)]
    def check(self,code):
        return full_timing(np.frombuffer(code,np.uint8),self.ready,self.deadlines,self.q,self.lengths,self.horizon)

class Boundary:
    def __init__(self,eng,code,state,timing):
        self.parent=np.frombuffer(code,np.uint8);self.t=timing;self.eng=eng
        self.ends=state["ends"]
        self.ids=[np.flatnonzero((self.parent>=10)==dev) for dev in range(2)]
        self.latest=np.empty(len(code),np.int64)
        for ids in self.ids:
            bound=timing.horizon;next_k=0
            for i in reversed(ids):
                k=int(self.parent[i])%10
                self.latest[i]=min(timing.limits[i],bound-5*(k!=next_k))
                bound=self.latest[i]-timing.lengths[i,self.parent[i]];next_k=k
    def limits(self,dev,win):
        ids=self.ids[dev];w=self.eng.groups[win]
        a,b=np.searchsorted(ids,[w[0],w[-1]+1])
        prev=int(ids[a-1]) if a else None
        nxt=int(ids[b]) if b<len(ids) else None
        old=int(self.parent[prev])%10 if prev is not None else 0
        start=self.ends[prev] if prev is not None else 0
        before=self.latest[nxt]-self.t.lengths[nxt,self.parent[nxt]] if nxt is not None else self.t.horizon
        target=int(self.parent[nxt])%10 if nxt is not None else 0
        return int(start),old,int(before),target,nxt
    def inspect(self,code,win):
        rows=[];w=self.eng.groups[win]
        for dev in range(2):
            t,k,base,target,nxt=self.limits(dev,win)
            own=True
            for i in w:
                if (code[i]>=10)!=dev:continue
                new=code[i]%10
                t=max(self.t.ready[i],t+5*(k!=new))+self.t.lengths[i,code[i]]
                k=new;own &= (t<=self.t.limits[i])
            cap=base-5*(k!=target)
            rows.append(dict(device=dev+2,own=bool(own),finish=int(t),suffix_cap=int(cap),
                             remaining=int(cap-t),last_freq=k,next_freq=target,next_task=nxt))
        return rows
    def prove_boundaries(self):
        tested=0
        for win in range(len(self.eng.groups)):
            for dev in range(2):
                _,_,cap,target,nxt=self.limits(dev,win)
                ids=self.ids[dev]
                suffix=ids[np.searchsorted(ids,self.eng.groups[win][-1]+1):]
                for last in range(3 if dev else 10):
                    threshold=cap-5*(last!=target)
                    # Forward feasibility is monotone in entry time. Verify the exact integer cutoff.
                    for tick in sorted(set([max(0,threshold),max(0,threshold+1)])):
                        ok=suffix_feasible(suffix,self.parent,self.t.ready,self.t.limits,self.t.lengths,self.t.horizon,tick,last)
                        assert ok==(tick<=threshold),(dev,win,last,tick,threshold,nxt)
                        tested+=1
        return tested
