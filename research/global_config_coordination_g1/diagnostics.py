"""D3 suffix verification: exact frontier DP vs a separate depth-first configuration enumerator."""
from construct import *
from collections import Counter

def suffix_check(p,front,n):
    base=reference(p,"joint")
    start=len(base)-n
    state=(0,0,0,0)
    prefix=0
    for j,(u,k) in enumerate(base[:start]):
        state,add=front.advance(j,state,u,k,p.horizon)
        prefix+=add
    root=state
    due=[r["deadline_tick"]-p.dur(3*j+2,1,0) for j,r in enumerate(p.req)]
    cheap=[min(front.busy[p.kinds[3*j+1],u,k] for u,k in front.ops) for j in range(start,len(base))]
    remain=[sum(cheap[h:]) for h in range(n+1)]
    # A real feasible incumbent bounds the minimum. The relaxation only ignores post contention.
    seeds=[base,reference(p,"suffix4")]
    seedcost,winning=min((sum(Layout(p,rows).components(idle_plan(p,rows)[1]).values()),tuple(cfg[start:]))
                        for cfg in seeds for rows in [assemble(p,cfg)])
    upper=(seedcost-front.base)*front.scale-prefix
    assert upper.denominator==1
    upper=int(upper)
    # Account for each gap by explicitly charging the old state until each switch completion.
    def direct_gap(u,old,k,g):
        extra=front.rate[u,old]
        keep=g*extra+int(old!=k)*front.switch
        if old==0 or g<5*(1+int(k!=0)): return keep
        return min(keep,5*extra+(g-5)*front.rate[u,0]+(1+int(k!=0))*front.switch)
    def oracle_children(j,state):
        for u,k in front.ops:
            a=u-2
            end,level=state[a],state[a+2]
            s=max(front.pre[j],end+5*int(level!=k))
            z=s+p.profile[p.kinds[3*j+1],u,k][0]
            if z>due[j]: continue
            nxt=list(state)
            nxt[a],nxt[a+2]=z,k
            add=direct_gap(u,level,k,s-end)+front.busy[p.kinds[3*j+1],u,k]
            yield add,tuple(nxt),(u,k)
    counters=Counter()
    incumbent=upper
    best=winning
    def dfs(h,state,cost,path):
        nonlocal incumbent,best
        # Every presently nonzero domain must pay at least one switch before H.
        lb=cost+remain[h]+front.switch*sum(k!=0 for k in state[2:])
        if lb>=incumbent:
            counters["bound_pruned"]+=1
            return
        counters["visited"]+=1
        if h==n:
            tail=sum(direct_gap(u,state[u],0,p.horizon-state[u-2]) for u in (2,3))
            if cost+tail<incumbent:
                incumbent,best=cost+tail,path
            return
        for inc,nxt,op in sorted(oracle_children(start+h,state)):
            dfs(h+1,nxt,cost+inc,(*path,op))
    dfs(0,root,0,())
    # Independent layer recurrence, using the original incumbent only.
    states={root:0}
    widths=[]
    for h in range(n):
        layer={}
        for st,cost in states.items():
            for u,k in front.ops:
                ans=front.advance(start+h,st,u,k,due[start+h])
                if ans is None: continue
                nxt,inc=ans
                tot=cost+inc
                if tot+remain[h+1]+front.switch*sum(v!=0 for v in nxt[2:])>upper: continue
                if nxt not in layer or tot<layer[nxt]:layer[nxt]=tot
        states=layer
        widths.append(len(states))
    dp=min(cost+front.tail(st) for st,cost in states.items())
    assert dp==incumbent
    plan=idle_plan(p,assemble(p,base[:start]+list(best)))
    key,cert=assess(p,plan)
    target=front.base+Q(prefix+dp,front.scale)
    assert Q(cert["exact_E35_J"])==target
    return dict(n=n,options=13,domain=13**n,dp_widths=widths,dfs=dict(counters),
                exact_E35_J=str(target),E35_J=float(target),plan=key,status=cert["metrics"]["status"])
