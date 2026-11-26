"""Frozen M1-b unfiltered integer sampler, with a boundary-only diagnostic switch."""
from generator import cuts, gridpoints, np


def synthesize(time,planes,points,bal,cost,a,b,k,boundary_only=False):
    xs=np.arange(a+1)
    ts=np.repeat(1.3,2)
    lo,hi,ok=cuts(time,ts,xs,b)
    active=ok&(lo<=hi)
    if not np.any(active):
        return list(points)
    limits=np.r_[ts,np.repeat(80.,len(planes))]
    constraints=np.vstack((time,planes))
    low,high,_=cuts(constraints,limits,xs,b)
    # Search only integer neighbours of interval ends / balance lines.
    # Project the approximate thermal bounds back to the timing interval
    # even when the approximate thermal polygon has no integer interior.
    targets=np.clip(np.array([lo,hi,low,high,bal,(low+high)*.5]),lo,hi)
    targets=targets[:,active]
    y=np.concatenate([np.floor(targets),np.ceil(targets)],axis=0)
    pool=np.unique(gridpoints(xs[active],y,b),axis=0)
    if not len(pool):
        return list(points)
    energy=cost[0]+pool@cost[1:]
    timing=np.max(time[:,0]+pool@time[:,1:].T,axis=1)
    if len(planes) and not boundary_only:
        risk=np.max(planes[:,0]+pool@planes[:,1:].T,axis=1)
        exceed=np.maximum(0,risk-80)
    else:
        risk=timing
        exceed=np.maximum(0,timing-1.3)
    eligible=timing<=1.3+1e-9
    def order(*keys):
        # Primary key appears first in caller.
        return np.lexsort(tuple(reversed((*keys,pool[:,0],pool[:,1]))))
    picked=list(points)
    def take(indices):
        for idx in indices:
            v=tuple(map(int,pool[idx]))
            if eligible[idx] and v not in picked:
                picked.append(v)
                break
    take(order(exceed,energy))
    take(order(risk,energy))
    # Add separated boundary points by farthest-point sampling on the best
    # attainable thermal/time band; then use energy as deterministic tie break.
    while len(picked)<k:
        ds=np.min(np.sum(((pool[:,None,:]-np.array(picked)[None,:,:])/np.array([a,b]))**2,axis=2),axis=1)
        previous=len(picked)
        take(order(exceed,-ds,energy))
        if previous==len(picked):
            break
    return picked[:k]
