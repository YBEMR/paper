"""Integer-tick FIFO timing and clipped sufficient statistics of P1 event powers."""
import numpy as np
from numba import njit


@njit(cache=True)
def add_span(mom, left, width, upper, node, start, end, power, slope):
    if not len(mom):
        return
    lo = max(start, left)
    hi = min(end, upper)
    while lo < hi:
        j = (lo-left)//width
        stop = min(hi, left+(j+1)*width)
        mom[j,node] += (stop-lo)*power
        mom[j,node+4] += (stop-lo)*slope
        lo = stop


@njit(cache=True)
def fifo(config, release, kinds, pre_start, ready, post_dur, deadlines,
         busy, beta, dur, idle, idle_beta, horizon, left, right, width, closed, moments, causal):
    # config encodes (GPU OPP=0..9, NPU OPP=10..12).
    n = len(config)
    f = np.zeros(2, np.int64)
    k = np.zeros(2, np.int64)
    starts = np.empty(n, np.int64)
    ends = np.empty(n, np.int64)
    posts = np.empty(n, np.int64)
    down = np.zeros(n+2, np.int8)
    bins = (right-left+width-1)//width if moments else 0
    mom = np.zeros((bins,8))
    cumulative = 0.0  # joules above low-OPP idle, plus transitions
    for i in range(n):
        code = config[i]
        j = int(code >= 10)
        u = j+2
        new = code - 10*j
        old = k[j]
        last = f[j]
        s = max(ready[i],last+5*(old!=new))
        z = s+dur[kinds[i],u,new]
        starts[i],ends[i] = s,z
        # A gap open at an earlier decision epoch has already held the old OPP.
        decision = (release[i]//10000)*10000 if causal else 0
        extra = idle[u,old]-idle[u,0]
        hold = extra*(s-last) + 15*(old!=new)
        drop = extra*5 + 15*(1+(new!=0))
        early = old>0 and last>=decision and s-last>=5*(1+(new!=0)) and drop < hold-1.e-10
        down[i] = early
        cumulative += min(hold,drop) if early else hold
        low_end = last+5*early
        mid = 0 if early else old
        change = mid!=new
        # mom stores deviations from each node's lowest-OPP idle.
        if early:
            add_span(mom,left,width,right,u,last,low_end,extra+3,idle_beta[u,old]-idle_beta[u,0])
        add_span(mom,left,width,right,u,low_end,s,idle[u,mid]-idle[u,0],idle_beta[u,mid]-idle_beta[u,0])
        if change:
            add_span(mom,left,width,right,u,s-5,s,3.,0.)
        t = kinds[i]
        add_span(mom,left,width,right,u,s,z,busy[t,u,new]-idle[u,0],beta[t,u,new]-idle_beta[u,0])
        add_span(mom,left,width,right,0,pre_start[i],ready[i],busy[t,0,0]-idle[0,0],beta[t,0,0]-idle_beta[0,0])
        cumulative += (z-s)*(busy[t,u,new]-idle[u,0]) + (ready[i]-pre_start[i])*(busy[t,0,0]-idle[0,0])
        f[j],k[j] = z,new

    # Stable finish order breaks ties by request ID exactly as original replay.
    post_end = 0
    slack = 10**9
    for i in np.argsort(ends,kind='mergesort'):
        s = max(post_end,ends[i])
        posts[i] = s
        post_end = s+post_dur[i]
        slack = min(slack,deadlines[i]-post_end)
        t = kinds[i]
        add_span(mom,left,width,right,1,s,post_end,busy[t,1,0]-idle[1,0],beta[t,1,0]-idle_beta[1,0])
        cumulative += post_dur[i]*(busy[t,1,0]-idle[1,0])
    for j in range(2):
        u = j+2
        last,old = f[j],k[j]
        extra = idle[u,old]-idle[u,0]
        db = idle_beta[u,old]-idle_beta[u,0]
        if closed and old:
            decision = (release[n-1]//10000)*10000 if causal else 0
            early = last>=decision and horizon-last>=5 and extra*5+15 < extra*(horizon-last)+15-1.e-10
            down[n+j] = early
            switch_start = last if early else horizon-5
            add_span(mom,left,width,right,u,last,switch_start+5,extra,db)
            add_span(mom,left,width,right,u,switch_start,switch_start+5,3.,0.)
            cumulative += extra*(switch_start+5-last) + 15
        else:
            add_span(mom,left,width,right,u,last,right,extra,db)
            cumulative += max(right-last,0)*extra
    feasible = slack>=0 and post_end<=horizon and max(f[0]+5*(k[0]!=0),f[1]+5*(k[1]!=0))<=horizon
    for j in range(bins):
        dt = min(width,right-left-j*width)
        for u in range(4):
            mom[j,u] = mom[j,u]/dt + idle[u,0]
            mom[j,u+4] = mom[j,u+4]/dt + idle_beta[u,0]
    return feasible, cumulative/10000, f, k, starts, ends, posts, down, mom, slack
