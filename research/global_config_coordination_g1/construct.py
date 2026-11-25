"""Fixed CPU constructive search. All ranking costs use exact integer multiples of a rational joule."""
import heapq
import math
from bisect import bisect_left, bisect_right
from functools import lru_cache
from itertools import accumulate
from g1io import *

def reference(p, name):
    scenes,sec,*_ = CFG["instances"][p.case]
    cfg=[]
    for j,r in enumerate(p.req):
        w = r["release_tick"]-int(sec*10000)*r["scene"]
        typ = r["stream"]
        if scenes[r["scene"]]=="L":
            npu = typ=="A1" or (name!="B0" and typ=="A2" and w%2000==250)
            op = (3,0) if npu else (2,int(name=="B0"))
        elif name in ("B0","B1-a"):
            npu = typ=="A1" or (typ=="A2" and w%1000<500)
            op = (3,1) if npu else (2,5 if name=="B0" else 4)
        else:
            joint = name in ("joint","suffix4")
            npu = typ=="A1" or (typ=="A2" and (w%5000 in (250,1750,3750)
                   or (joint and w>=int(sec*10000)-15000 and w%5000==4750)))
            op = (3,0) if npu else (2,4 if joint and w>=int(sec*10000)-10000 else 5)
            if name=="suffix4" and j>=796:
                op = [(2,2),(2,2),(3,0),(2,3)][j-796]
        cfg.append(op)
    return cfg

def assemble(p, cfg):
    rows=[None]*p.n
    end=[0]*4
    freq=[0]*4
    completions=[]
    for j,(u,k) in enumerate(cfg):
        i=3*j
        rows[i]=(0,0,max(end[0],p.req[j]["release_tick"]))
        end[0]=p.finish(i,rows[i])
        rows[i+1]=(u,k,max(end[0],end[u]+5*(freq[u]!=k)))
        end[u]=p.finish(i+1,rows[i+1])
        freq[u]=k
        completions.append((end[u],j))
    for t,j in sorted(completions):
        i=3*j+2
        rows[i]=(1,0,max(t,end[1]))
        end[1]=p.finish(i,rows[i])
    return rows

def idle_plan(p,rows):
    lay=Layout(p,rows)
    return rows,frozenset(key for key in lay.flex if lay.gap_delta(key,35)<0)

class Frontier:
    def __init__(self,p):
        self.p=p
        self.ops = list(p.options[1])
        assert len(self.ops)==13 and all(p.options[i]==tuple(self.ops) for i in range(1,p.n,3))
        release=[r["release_tick"] for r in p.req]
        self.pre=[]
        t=0
        for j,r in enumerate(p.req):
            t=max(t,r["release_tick"])+p.dur(3*j,0,0)
            self.pre.append(t)
        post=[p.dur(3*j+2,1,0) for j in range(len(p.req))]
        sums=[0,*accumulate(post)]
        # In deadline order, jobs released strictly before r_j-3000 have completed
        # by r_j. At main completion, only already released jobs can precede its post.
        self.due=[]
        for j,r in enumerate(p.req):
            left=bisect_left(release,r["release_tick"]-3001)
            def enough(t):
                right=bisect_right(release,t)
                return t+sums[right]-sums[left]<=r["deadline_tick"]
            a,b=r["release_tick"]-1,r["deadline_tick"]+1
            while b-a>1:
                m=(a+b)//2
                if enough(m): a=m
                else: b=m
            self.due.append(a)
        rate={(u,k):(v[0]-p.node_idle[u,0][0])/10000 for (u,k),v in p.node_idle.items()}
        busy={}
        self.duration={}
        for kind in ("A.main","B.main"):
            for u,k in self.ops:
                dur=p.profile[kind,u,k][0]
                self.duration[kind,u,k]=dur
                busy[kind,u,k]=(p.exact[kind,u,k][2]-p.node_idle[u,0][0])*dur/10000
        switch=Q(15,10000)
        self.scale=math.lcm(*(q.denominator for q in [*rate.values(),*busy.values(),switch]))
        self.busy={key:int(v*self.scale) for key,v in busy.items()}
        self.rate={key:int(v*self.scale) for key,v in rate.items()}
        self.switch=int(switch*self.scale)
        self.base=(sum(p.node_idle[u,0][0] for u in range(4))+Q(3,10))*p.horizon/10000
        self.base+=sum((p.exact[p.kinds[i],u,0][2]-p.node_idle[u,0][0])*p.dur(i,u,0)/10000
                       for i in range(p.n) if i%3!=1 for u in [int(i%3==2)])
        # Relax the next 16 main jobs against separate GPU/NPU capacities.
        self.duals=[]
        for j in range(len(p.req)+1):
            stop=min(j+16,len(p.req))
            horizon=p.req[stop-1]["deadline_tick"] if j<stop else p.horizon
            terms=[]
            for a,b in [(0,0),(1,0),(0,1),(4,0),(0,4),(1,1)]:
                # Multipliers of 0.25 W, expressed on the same exact tick scale.
                prices=(a*self.scale//40000,b*self.scale//40000)
                bound=sum(min(self.busy[p.kinds[3*h+1],u,k]+prices[u-2]*self.duration[p.kinds[3*h+1],u,k]
                              for u,k in self.ops) for h in range(j,stop))
                terms.append((*prices,bound))
            self.duals.append((horizon,terms))

    def gap(self,u,old,k,length):
        hold=self.rate[u,old]*length+self.switch*(old!=k)
        if old and length>=5*(1+(k!=0)):
            early=self.rate[u,old]*5+self.switch*(1+(k!=0))
            return min(hold,early)
        return hold

    def advance(self,j,state,u,k,limit=None):
        g,n,fg,fn=state
        end,old=(g,fg) if u==2 else (n,fn)
        start=max(self.pre[j],end+5*(old!=k))
        kind=self.p.kinds[3*j+1]
        z=start+self.duration[kind,u,k]
        if z>(self.due[j] if limit is None else limit):
            return None
        nxt=(z,n,k,fn) if u==2 else (g,z,fg,k)
        return nxt,self.gap(u,old,k,start-end)+self.busy[kind,u,k]

    def tail(self,state):
        g,n,fg,fn=state
        return sum(self.gap(u,f,0,self.p.horizon-t) for u,f,t in [(2,fg,g),(3,fn,n)])

    def price(self,j,state):
        horizon,duals=self.duals[j]
        g,n,_,_=state
        return max(b-a*max(0,horizon-g)-c*max(0,horizon-n) for a,c,b in duals)

    def search(self,width,priced,endtime):
        states={(0,0,0,0):(0,None)}
        for j in range(len(self.p.req)):
            expanded={}
            for index,(state,(cost,history)) in enumerate(states.items()):
                if index%32==0 and perf_counter()>=endtime:
                    return None,j
                for u,k in self.ops:
                    step=self.advance(j,state,u,k)
                    if step is None: continue
                    nxt,inc=step
                    val=inc+cost
                    if nxt not in expanded or val<expanded[nxt][0]:
                        expanded[nxt]=(val,(history,(u,k)))
            if not expanded: return None,j
            final=j+1==len(self.p.req)
            def rank(item):
                state,(v,_)=item
                more=self.tail(state) if final else self.price(j+1,state) if priced else 0
                return (v+more,v,state)
            states=dict(heapq.nsmallest(width,expanded.items(),key=rank))
        state,(cost,history)=min(states.items(),key=rank)
        cfg=[]
        while history:
            history,op=history
            cfg.append(op)
        plan=idle_plan(self.p,assemble(self.p,cfg[::-1]))
        assert self.base+Q(cost+self.tail(state),self.scale)==sum(Layout(self.p,plan[0]).components(plan[1]).values())
        return plan,len(cfg)
