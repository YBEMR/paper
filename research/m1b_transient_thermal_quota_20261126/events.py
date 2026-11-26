"""Independently recover clipped P1 events from integer-tick FIFO timing."""
from base import np
from numba import njit


@njit(cache=True)
def span(ends,profiles,count,u,s,e,k,watts,slope,idle_w,left,right):
    if min(e,right)>max(s,left):
        pos=count[u]
        ends[u,pos]=min(e,right)
        profiles[u,pos,0]=watts
        profiles[u,pos,1]=slope
        profiles[u,pos,2]=idle_w
        count[u]+=1


@njit(cache=True)
def build_events(code,kinds,pre,ready,postdur,busy,beta,idle,idleb,starts,finish,post,down,left,right):
    n=len(code)
    ends=np.empty((4,4*n+8),np.int64)
    profiles=np.empty((4,4*n+8,3))
    count=np.zeros(4,np.int64)
    for u in range(2):
        order=np.arange(n) if u==0 else np.argsort(post)
        last=0
        for i in order:
            s=pre[i] if u==0 else post[i]
            e=ready[i] if u==0 else post[i]+postdur[i]
            span(ends,profiles,count,u,last,s,0,idle[u,0],idleb[u,0],idle[u,0],left,right)
            span(ends,profiles,count,u,s,e,0,busy[kinds[i],u,0],beta[kinds[i],u,0],idle[u,0],left,right)
            last=e
        span(ends,profiles,count,u,last,right,0,idle[u,0],idleb[u,0],idle[u,0],left,right)
    for u in (2,3):
        last=0
        old=0
        for i in range(n+1):
            if i<n:
                if (code[i]>=10)!=(u==3):
                    continue
                k=int(code[i])-10*(u==3)
                s=starts[i]
                early=down[i]
            else:
                k=0
                s=right
                early=down[n+u-2]
            mid=0 if early else old
            first=last+5*early
            if early:
                span(ends,profiles,count,u,last,first,old,idle[u,old]+3,idleb[u,old],idle[u,old],left,right)
            change=5*(mid!=k)
            span(ends,profiles,count,u,first,s-change,mid,idle[u,mid],idleb[u,mid],idle[u,mid],left,right)
            if change:
                span(ends,profiles,count,u,s-change,s,mid,idle[u,mid]+3,idleb[u,mid],idle[u,mid],left,right)
            if i<n:
                span(ends,profiles,count,u,s,finish[i],k,busy[kinds[i],u,k],beta[kinds[i],u,k],idle[u,k],left,right)
                last,old=finish[i],k
    assert np.all(count>0)
    result=np.empty((int(count.sum()),14))
    ix=np.zeros(4,np.int64)
    t=left
    num=0
    while t<right:
        e=right
        for u in range(4):
            e=min(e,ends[u,ix[u]])
            for h in range(3):
                result[num,2+4*h+u]=profiles[u,ix[u],h]
        assert e>t
        result[num,0],result[num,1]=t,e
        for u in range(4):
            if ends[u,ix[u]]==e:
                ix[u]+=1
        t=e
        num+=1
    return result[:num]


def suffix_events(c,cfg,l,left):
    return build_events(np.frombuffer(cfg,dtype=np.uint8),c.kinds,c.args[2],c.args[3],c.args[4],
                        c.args[6],c.args[7],c.args[9],c.args[10],l[4],l[5],l[6],l[7],left,c.p.horizon)
