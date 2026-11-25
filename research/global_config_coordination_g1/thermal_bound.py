"""Exact algebra for the temperature barrier, scalar comparison and objective coefficients."""
from g1io import *
from math import floor

T=tuple(map(Q,("42.5","42.5","42.0","40.9")))
B=tuple(map(Q,(".002",".002",".0039",".003")))
PJ=10**12

def solve_linear(matrix,rhs):
    rows=[list(map(Q,row))+[Q(v)] for row,v in zip(matrix,rhs)]
    for i in range(len(rows)):
        pos=next(j for j in range(i,len(rows)) if rows[j][i])
        rows[i],rows[pos]=rows[pos],rows[i]
        div=rows[i][i]
        rows[i]=[v/div for v in rows[i]]
        for j in range(len(rows)):
            if j!=i:
                mul=rows[j][i]
                rows[j]=[v-mul*w for v,w in zip(rows[j],rows[i])]
    return [r[-1] for r in rows]

def proof(p,temps=T,betas=B):
    G=CFG["G"]
    idle=[p.node_idle[u,0] for u in range(4)]
    mat=[[Q(G[u][v])-int(u==v)*idle[u][1] for v in range(4)] for u in range(4)]
    ini=solve_linear(mat,[sum(G[u])*p.ta+idle[u][0]-35*idle[u][1] for u in range(4)])
    assert max(abs(float(a)-b) for a,b in zip(ini,p.initial))<1e-10
    net=[]; slopes=[]; activities=[]; net_idle=[]
    for u,t in enumerate(temps):
        assert all(G[u][v]<=0 for v in range(4) if u!=v)
        assert p.c>0 and CFG["C"][u]>0 and G[u][u]>betas[u]>=0
        data=[x for (_,w,_),x in p.exact.items() if u==w]
        conduct=sum(G[u][v]*(temps[v]-p.ta) for v in range(4))
        powers=[z+s*(t-35) for b,l,h,g in data for z,s in ((b,l),(h,g))]
        net.append(min(powers)-conduct)
        net_idle.append(min(b+l*(t-35) for b,l,h,g in data)-conduct)
        slopes.append(min(s for b,l,h,g in data for s in (l,g))-betas[u])
        activities.append(min(h-b+(g-l)*(deg-35) for b,l,h,g in data for deg in (20,100,t)))
    passed=all(x>=0 for x in [*net,*net_idle,*slopes,*activities,*[x-y for x,y in zip(ini,temps)]])
    return dict(passed=passed,initial=list(map(str,ini)),barrier_net_W=list(map(str,net)),
                idle_barrier_net_W=list(map(str,net_idle)),slope_margin=list(map(str,slopes)),
                min_busy_minus_idle=list(map(str,activities)))

def latest_finish(p,i):
    req=p.req[i//3]
    return min(p.horizon,req["deadline_tick"]-sum(min(p.dur(j,u,k) for u,k in p.options[j])
               for j in range(i+1,3*(i//3)+3)))

def rates(p,method):
    temps=(35,)*4 if method=="C0" else T
    from common import MEMBERS
    return {(d,k):sum(p.node_idle[u,k][0]+(temps[u]-35)*p.node_idle[u,k][1] for u in MEMBERS[d])/10000
            for d,k in p.domain_idle}

def activity_terms(p,i,u,k,method):
    t=35 if method=="C0" else T[u]
    b,l,h,g=p.exact[p.kinds[i],u,k]
    energy=(h-b+(t-35)*(g-l))*p.dur(i,u,k)/10000
    dt=Q(p.horizon-latest_finish(p,i),10000)
    weight=B[u]*dt/(CFG["C"][u]*p.c+(CFG["G"][u][u]-B[u])*dt)
    return energy, (energy*weight if method=="C1" else Q(0))

def simple_bound(p,method):
    rate=rates(p,method)
    fixed=Q(3*p.horizon,100000)+sum(min(v for (d,_),v in rate.items() if d==dom)*p.horizon for dom in range(3))
    return fixed+sum(min(sum(activity_terms(p,i,u,k,method)) for u,k in opts) for i,opts in enumerate(p.options))

def exact_parts(p,plan,method):
    rows,low=plan
    lay=Layout(p,rows)
    sw=lay.switches(low)
    rate=rates(p,method)
    base=0
    for d in range(3):
        t=k=0
        for z,nxt in [(e,b) for _,e,dom,_,b in sw if d==dom]+[(p.horizon,0)]:
            base+=(z-t)*rate[d,k]
            t,k=z,nxt
    terms=[activity_terms(p,i,u,k,method) for i,(u,k,_) in enumerate(rows)]
    return dict(base=base,activity=sum(a for a,_ in terms),thermal=sum(b for _,b in terms),
                switch=Q(15*len(sw),10000),external=Q(3*p.horizon,100000))
