"""Integer-tick execution ledger. A decision is (unit, OPP index, start tick) per stage."""
import bisect
import csv
from collections import defaultdict
from fractions import Fraction as Q
from functools import lru_cache
import numpy as np
from profiles import CFG, ROOT, requests

DOM = (0, 0, 1, 2)
NAMES = CFG["nodes"]
SW = 5


class Invalid(ValueError):
    pass


class Problem:
    def __init__(self, case):
        self.case = case
        self.req = requests(case)
        scenes, seconds, self.ta, self.c, *_ = CFG["instances"][case]
        self.boundaries = [i*seconds*10000 for i in range(1,len(scenes))]
        self.horizon = len(scenes)*seconds*10000+3010
        self.kinds = [r["kind"]+"."+s for r in self.req for s in ("pre","main","post")]
        self.n = len(self.kinds)
        self.options = []
        self.profile = {}
        self.compute = {}
        self.idle = {}
        self.exact = {}
        for file, gpu in [("gpu_profiles",True),("cpu_npu_profiles",False)]:
            with (ROOT / "config" / (file+".csv")).open() as stream:
                for row in csv.DictReader(stream):
                    units = [2] if gpu else [3] if row["domain"]=="npu" else [0,1]
                    for u in units:
                        k = int(row["k"])
                        duration = int(row["max_ticks" if gpu and case=="H2" else "ticks"])
                        self.compute[row["stage"],u,k] = Q(row["max_compute_ms" if gpu and case=="H2" else "compute_ms"])
                        values = tuple(Q(row[key]) for key in ("idle_W","idle_slope","busy_W","busy_slope"))
                        self.exact[row["stage"],u,k]=values
                        self.idle[u,k] = tuple(map(float,values[:2]))
                        self.profile[row["stage"],u,k] = (duration,*map(float,values[2:]))
        for stage in self.kinds:
            self.options.append(tuple((u,k) for kind,u,k in self.profile if kind==stage))
        self.cap = np.array(CFG["C"],float)*self.c
        self.G = np.array(CFG["G"],float)
        self.idle35 = np.array([self.idle[u,0][0] for u in range(4)])
        self.idle_beta = np.array([self.idle[u,0][1] for u in range(4)])
        self.initial = np.linalg.solve(self.G-np.diag(self.idle_beta),
                                      self.G@np.full(4,self.ta) + self.idle35 - 35*self.idle_beta)

    def dur(self,i,u,k):
        return self.profile[self.kinds[i],u,k][0]

    def inc(self,i,u,k):
        base,_,busy,_=self.exact[self.kinds[i],u,k]
        return float(busy-base)*self.dur(i,u,k)/10000

    def bounds(self,i,rows):
        r=self.req[i//3]
        left=r["release_tick"] if i%3==0 else self.finish(i-1,rows[i-1])
        right=r["deadline_tick"] if i%3==2 else rows[i+1][2]
        return left,right

    def finish(self,i,row):
        u,k,t=row
        return t+self.dur(i,u,k)

    def lower(self,rows=None,mobile=(),keep_unit=False):
        lows={}
        for u in range(4):
            lows[u]=min(vals[0]+vals[1]*(t-35)
                            for (kind,unit,k),vals in self.exact.items() if unit==u for t in (20,100))
        base=sum(lows.values())*self.horizon/10000
        activity=Q(0)
        for i,opts in enumerate(self.options):
            if rows is not None:
                if i not in mobile: opts=[rows[i][:2]]
                elif keep_unit: opts=[op for op in opts if op[0]==rows[i][0]]
            def bound(opt):
                u,k=opt
                b,s,p,v=self.exact[self.kinds[i],u,k]
                return min(p-b+(v-s)*(t-35) for t in (20,100))*self.dur(i,u,k)/10000
            activity+=min(map(bound,opts))
        external=Q(3,10)*self.horizon/10000
        return dict(base=str(base),increment=str(activity),external=str(external),total=str(base+activity+external))


def transitions(p, rows, low, *, edges=False):
    if len(rows)!=p.n:
        raise Invalid("missing stage")
    units=[[] for _ in range(4)]
    for i,(u,k,t) in enumerate(rows):
        if type(t)!=int or (u,k) not in p.options[i]:
            raise Invalid("grid or unsupported OPP")
        e=p.finish(i,rows[i])
        if i%3==0 and t<p.req[i//3]["release_tick"] or i%3 and t<p.finish(i-1,rows[i-1]):
            raise Invalid("release or dependency")
        if i%3==2 and e>p.req[i//3]["deadline_tick"] or e>p.horizon:
            raise Invalid("deadline")
        units[u].append((t,e,k,i))
    links=[]
    for unit in units:
        unit.sort()
        for a,b in zip(unit,unit[1:]):
            if a[1]>b[0]:
                raise Invalid("unit overlap")
            if edges:
                links.append([a[3],b[3]])
    sw=[]
    for dom,work in enumerate((sorted(units[0]+units[1]),units[2],units[3])):
        end,old=0,0
        for t,e,k,i in [*work,(p.horizon,p.horizon,0,-1)]:
            if t<end:
                if old!=k:
                    raise Invalid("CPU frequency overlap")
            else:
                down=(dom,i) in low and old!=0
                count=int(down)+int((0 if down else old)!=k)
                if t-end<SW*count:
                    raise Invalid("switch gap")
                if down:
                    sw.append((end,end+SW,dom,old,0))
                    old=0
                if k!=old:
                    sw.append((t-SW,t,dom,old,k))
                old=k
            end=max(end,e)
    return units,sorted(sw),links


def event_arrays(p,rows,low):
    units,switches,edges=transitions(p,rows,low,edges=True)
    # At each tick stop old operation, finish switches, then start new work/switches.
    actions=defaultdict(list)
    actions[0]; actions[p.horizon]
    for t in p.boundaries:
        actions[t]
    for u,work in enumerate(units):
        for t,e,k,i in work:
            actions[t].append((3,u,i))
            actions[e].append((0,u,i))
    for t,e,d,a,b in switches:
        actions[t].append((2,d,b))
        actions[e].append((1,d,b))
    active=[-1]*4
    freq=[0]*3
    switch=[False]*3
    times=sorted(actions)
    output=np.empty((len(times)-1,14))
    for h,t in enumerate(times[:-1]):
        for kind,u,i in sorted(actions[t]):
            if kind==0: active[u]=-1
            elif kind==1: switch[u]=False;freq[u]=i
            elif kind==2: switch[u]=True
            else: active[u]=i
        output[h,:2]=(t,times[h+1])
        for u,i in enumerate(active):
            d=DOM[u]; k=freq[d]
            b,v=p.idle[u,k]
            output[h,10+u]=b
            if i>=0:
                if rows[i][1]!=k or switch[d]:
                    raise Invalid("event OPP")
                _,b,v=p.profile[p.kinds[i],u,k]
            if switch[d]: b+=1.5 if d==0 else 3.0
            output[h,2+u]=b
            output[h,6+u]=v
    return output,switches,edges


def independent_events(p,rows,low):
    """Rebuild node-wise occupied intervals and domain gap policies; no primary event sweep."""
    if len(rows)!=p.n: raise Invalid("incomplete")
    spans=[[] for _ in range(4)]
    for i,(u,k,s) in enumerate(rows):
        if (u,k) not in p.options[i] or type(s)!=int: raise Invalid("illegal row")
        a,z=p.bounds(i,rows)
        e=p.finish(i,rows[i])
        if s<a or e>z or e>p.horizon: raise Invalid("timing")
        spans[u].append((s,e,k,i))
    for work in spans:
        work.sort()
        if any(a[1]>b[0] for a,b in zip(work,work[1:])): raise Invalid("overlap")
    states=[]
    independent_sw=[]
    for d,members in enumerate(((0,1),(2,),(3,))):
        ordered=sorted(x for u in members for x in spans[u])
        # Build uninterrupted busy components. Adjacent different frequencies cannot switch for free.
        blocks=[]
        for s,e,k,i in ordered:
            if blocks and s<blocks[-1][1]:
                if k!=blocks[-1][2]: raise Invalid("shared domain")
                blocks[-1][1]=max(e,blocks[-1][1])
            else: blocks.append([s,e,k,i])
        seg=[]
        last=old=0
        for s,e,k,i in blocks+[[p.horizon,p.horizon,0,-1]]:
            early=(d,i) in low and old>0
            mid=0 if early else old
            left=last+SW*early
            right=s-SW*(mid!=k)
            if left>right: raise Invalid("DVFS")
            if early:
                seg.append((last,left,old,True))
                independent_sw.append((last,left,d,old,0))
            if left<right: seg.append((left,right,mid,False))
            if mid!=k:
                seg.append((right,s,mid,True))
                independent_sw.append((right,s,d,mid,k))
            if s<e: seg.append((s,e,k,False))
            last,old=e,k
        states.append(seg)
    times=sorted({0,p.horizon,*p.boundaries,*[t for unit in spans for span in unit for t in span[:2]],
                  *[t for seg in states for span in seg for t in span[:2]]})
    work_ix=[0]*4
    domain_ix=[0]*3
    events=[]
    for s,end in zip(times,times[1:]):
        for d in range(3):
            while states[d][domain_ix[d]][1]<=s: domain_ix[d]+=1
        b=[];v=[];idle=[]
        for u,work in enumerate(spans):
            while work_ix[u]<len(work) and work[work_ix[u]][1]<=s: work_ix[u]+=1
            _,_,k,sw=states[DOM[u]][domain_ix[DOM[u]]]
            q,beta=p.idle[u,k]
            idle.append(q)
            if work_ix[u]<len(work) and work[work_ix[u]][0]<=s:
                _,_,kk,i=work[work_ix[u]]
                if kk!=k or sw: raise Invalid("busy switch")
                _,q,beta=p.profile[p.kinds[i],u,k]
            b.append(q+(1.5 if u<2 else 3)*sw);v.append(beta)
        events.append((s,end,*b,*v,*idle))
    return np.array(events),sorted(independent_sw)


def construct(p,mode,level=9):
    """100-ms route quotas and release-aware upward-rank/EFT insertion for independent chains."""
    rows=[None]*p.n
    calendars=[[] for _ in range(4)]
    counts=defaultdict(int)
    order=sorted(range(len(p.req)),key=lambda j:(p.req[j]["release_ms"],
                -sum(min(p.dur(3*j+a,u,k) for u,k in p.options[3*j+a] if (u>=2)==(a==1))
                      for a in range(3)),j))
    for j in order:
        req=p.req[j]; typ=req["kind"]; block=req["release_tick"]//1000
        pos=counts[block,typ];counts[block,typ]+=1
        for a in range(3):
            i=3*j+a
            r=req["release_tick"] if a==0 else p.finish(i-1,rows[i-1])
            if a!=1: op=[(0,2),(1,2)] if mode=="reference_high" else [(0,0),(1,0)]
            elif mode=="low": op=[(2 if typ=="A" else 3,0)]
            elif mode in ("reference","reference_high"):
                op=[(2,9)] if pos<(2 if typ=="A" else 5) else [(3,2)]
            elif mode=="alternate":
                op=[(2,5)] if typ=="B" or pos==0 else [(3,2)]
            else: op=[(2,level),(3,min(2,level))]
            choices=[]
            for u,k in op:
                work=calendars[u]
                t=max(r,5 if k else 0)
                length=p.dur(i,u,k)
                # Constant unit OPP in each constructive route. Insert into earliest available gap.
                ix=bisect.bisect_right(work,(t,10**12))
                if ix: t=max(t,work[ix-1][1])
                while ix<len(work) and t+length>work[ix][0]:
                    t=max(t,work[ix][1]);ix+=1
                choices.append((t+length,t,u,k,ix))
            end,t,u,k,ix=min(choices)
            rows[i]=(u,k,t)
            calendars[u].insert(ix,(t,end))
    return rows,frozenset()
