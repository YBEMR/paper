"""Passive four-node response applied to measured source energies and window work changes."""
import numpy as np
from scipy.linalg import expm
from numba import njit

@njit(cache=True)
def work(config, kinds, ready, lengths, busy, idle, dur, bins):
    out=np.zeros((bins,4))
    f=np.zeros(2,np.int64)
    levels=np.zeros(2,np.int64)
    for i in range(len(config)):
        u=int(config[i]>=10)
        k=int(config[i])-10*u
        s=max(ready[i],f[u]+5*(levels[u]!=k))
        end=s+lengths[kinds[i],u,k]
        f[u]=end
        levels[u]=k
        while s<end:
            j=s//dur
            stop=min(end,(j+1)*dur)
            out[j,2+u]+=(stop-s)/10000*(busy[kinds[i],2+u,k]-idle[2+u,0])
            s=stop
    return out

class Guidance:
    def __init__(self,b,anchor,cert,trace):
        self.b=b
        self.duration=b.e.dur
        n=len(b.types)
        self.edges=np.array([*range(0,(n+1)*self.duration,self.duration),b.e.p.horizon])
        self.work_args=(b.flow.kinds,b.args[1],b.args[4],b.flow.args[6],b.flow.args[9],self.duration,n+1)
        baseline=self.activity(anchor)
        m=cert["metrics"]
        node=m["hotspot"]
        peak=float(m["peak_tick"][node])
        p=b.e.p
        A=-p.G/p.cap[:,None]
        # Spectral form of the physical passive kernel. Integral between arbitrary event times.
        vals,vec=np.linalg.eig(A)
        inv=np.linalg.inv(vec)@np.diag(1/p.cap)
        def kernels(left,right,target):
            left=np.minimum(left,target)
            right=np.minimum(right,target)
            h=(np.exp(np.outer((target-left)/10000,vals))-np.exp(np.outer((target-right)/10000,vals)))/vals
            return np.einsum("ik,tk,kj->tij",vec,h,inv).real
        power=trace[:,26:30]*10000/(trace[:,1]-trace[:,0])[:,None]
        parts=[]
        for l,r in zip(self.edges[:-1],self.edges[1:]):
            a=np.maximum(trace[:,0],l)
            z=np.minimum(trace[:,1],min(r,peak))
            mask=z>a
            K=kernels(a[mask],z[mask],peak)
            parts.append((K[:,node,:]*power[mask]).sum(axis=0))
        parts=np.array(parts)
        initial=35+(expm(A*peak/10000)@(p.initial-35))[node]
        self.window=int(np.argmax(parts[:n,2:].sum(axis=1)))
        self.observation=dict(nodes=list(__import__("model").NAMES),hotspot=node,peak_tick=peak,
            peak_lo=m["peak_lo"][node],peak_hi=m["peak_hi"][node],source_C=parts.tolist(),
            passive_initial_C=initial,reconstructed_C=initial+parts.sum(),window=self.window+1)
        # Exactly aligned observed endpoint temperatures with interpolation only inside one event.
        self.times=np.unique(np.r_[self.edges,m["peak_tick"]])
        self.base_T=np.column_stack([np.interp(self.times,np.r_[0,trace[:,1]],np.r_[trace[0,14+u],trace[:,18+u]]) for u in range(4)])
        self.K=np.array([kernels(self.edges[:-1],self.edges[1:],t) for t in self.times])
        self.base_power=baseline/(np.diff(self.edges)[:,None]/10000)
    def activity(self,state):
        return work(np.frombuffer(state.code,np.uint8),*self.work_args)
    def predict(self,state):
        delta=self.activity(state)/(np.diff(self.edges)[:,None]/10000)-self.base_power
        return float(np.max(self.base_T+np.einsum("twij,wj->ti",self.K,delta)))

