from base import np
from numba import njit


@njit(cache=True)
def optimistic(points,kinds,ready,deadlines,post,initial_f,initial_k,g,n,durations):
    a=np.sum(kinds==0)
    b=len(kinds)-a
    valid=np.ones(len(points),np.bool_)
    for h,(x,y) in enumerate(points):
        fg,fn=initial_f[0],initial_f[1]
        kg,kn=initial_k[0],initial_k[1]
        seen_a=seen_b=0
        for i,t in enumerate(kinds):
            if t==0:
                use_n=((seen_a+1)*x)//a>(seen_a*x)//a
                seen_a+=1
            else:
                use_n=((seen_b+1)*y)//b>(seen_b*y)//b
                seen_b+=1
            if use_n:
                fn=max(ready[i],fn+5*(kn!=n))+durations[t,3,n]
                kn=n
                end=fn
            else:
                fg=max(ready[i],fg+5*(kg!=g))+durations[t,2,g]
                kg=g
                end=fg
            if end+post[i]>deadlines[i]:
                valid[h]=False
                break
    return valid


def make_filter(c,parent,j,g,n,counters):
    lo,hi=c.release.searchsorted([j*10000,(j+1)*10000])
    def evaluate(points):
        mask=optimistic(points,c.kinds[lo:hi],c.args[3][lo:hi],c.args[5][lo:hi],c.args[4][lo:hi],
                        np.asarray(parent["f"]),np.asarray(parent["k"]),g,n,c.args[8])
        counters["cheap_time_points"]+=len(points)
        counters["cheap_time_pass"]+=int(mask.sum())
        return mask
    return evaluate
