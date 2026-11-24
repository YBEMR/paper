"""Neighborhoods share the same legal placements, gap controls and full-window scorer."""
import itertools
import math
import random
import time
from collections import defaultdict
import numpy as np
from model import DOM, Invalid, transitions
from heat import evaluate


class Expired(Exception):
    pass


def check(end):
    if time.perf_counter()>=end: raise Expired


def ranges(p,rows,i,opt,moving=(),relative=None):
    u,k=opt
    du=p.dur(i,u,k)
    req=p.req[i//3]
    lo=max(req["release_tick"],5 if k else 0)
    hi=min(req["deadline_tick"],p.horizon-(5 if k else 0))-du
    if i%3 and i-1 not in moving: lo=max(lo,p.finish(i-1,rows[i-1]))
    if i%3!=2 and i+1 not in moving: hi=min(hi,rows[i+1][2]-du)
    intervals=[]
    for j,(w,f,s) in enumerate(rows):
        if i==j or j in moving or DOM[w]!=DOM[u]: continue
        if w!=u and f==k: continue
        gap=5*(f!=k)
        a=s-gap-du+1;b=p.finish(j,rows[j])+gap-1
        if relative is not None and w==u:
            if relative[j][2]<relative[i][2]: lo=max(lo,b+1)
            else: hi=min(hi,a-1)
        if b>=lo and a<=hi: intervals.append((a,b))
    for a,b in sorted(intervals):
        if a>lo and lo<=hi: yield lo,min(hi,a-1)
        lo=max(lo,b+1)
        if lo>hi: break
    if lo<=hi: yield lo,hi


def gridpoints(p,original,i,spans):
    center=original[i][2]
    pts={center}
    pts.update(range(((max(0,center-500)+49)//50)*50,center+501,50))
    return [t for t in sorted(pts,key=lambda t:(abs(t-center),t)) if any(a<=t<=b for a,b in spans)]


def eligible_gaps(p,rows):
    units,_,_=transitions(p,rows,())
    keys=[]
    for d,work in enumerate((sorted(units[0]+units[1]),units[2],units[3])):
        end=k=0
        for s,e,f,i in [*work,(p.horizon,p.horizon,0,-1)]:
            if k and s-end>=5*(1+int(f!=0)) and (f or s-end>5): keys.append((d,i))
            end=max(end,e);k=f
    return keys


def prefer(result,best):
    return best is None or result["E_bounds"][1]<best["E_bounds"][0]


class Tracker:
    def __init__(self,p,end,thermal=True):
        self.p=p;self.end=end;self.start=time.perf_counter();self.thermal=thermal
        self.plan=self.best=self.safe_plan=self.safe=self.hot_plan=self.hot=None
        self.first_safe=None;self.history=[];self.count=0;self.certified=0;self.invalid=0

    def consider(self,plan,force=False):
        check(self.end)
        self.count+=1
        try:
            pred=evaluate(self.p,plan)
            if not force and self.best is not None and pred["E_J"]>self.best["E_bounds"][1]+2e-4:
                return None
            result=evaluate(self.p,plan,cert=True)
            self.certified+=1
        except Invalid:
            self.invalid+=1
            return None
        check(self.end)
        status=result["status"]
        changed=False
        if status=="SAFE" and prefer(result,self.safe):
            self.safe_plan=plan;self.safe=result
            changed=True
            if self.first_safe is None: self.first_safe=time.perf_counter()-self.start
        if status=="HOT" and prefer(result,self.hot):
            self.hot_plan=plan;self.hot=result
            changed=True
        if status=="SAFE" or status=="HOT" and not self.thermal:
            if prefer(result,self.best):
                self.plan=plan;self.best=result
                self.history.append([time.perf_counter()-self.start,result["E_bounds"],status])
                changed=True
        if changed and hasattr(self,"on_change"): self.on_change()
        return result

    def receipt(self):
        return dict(candidates=self.count,certifications=self.certified,nonthermal_fail=self.invalid,
                    first_SAFE_s=self.first_safe,best_by_time=self.history)


def ordinary(p,rows,i,size,rng):
    u,k,t=rows[i]
    neighbors=sorted((j for j in range(p.n) if i!=j),key=lambda j:(
        DOM[rows[j][0]]!=DOM[u],abs(rows[j][2]-t),j))
    return [i]+neighbors[:size-1]


def timing(p,rows,i,opt):
    u,k,t=rows[i]
    end=t+p.dur(i,*opt)
    _,_,edges=transitions(p,rows,(),edges=True)
    direct={v if u0==i else u0 for u0,v in edges if i in (u0,v)}
    if i%3: direct.add(i-1)
    if i%3!=2: direct.add(i+1)
    def key(j):
        s=rows[j][2];e=p.finish(j,rows[j])
        overlaps=DOM[rows[j][0]]==DOM[opt[0]] and s<end+5 and e>t-5
        return (not overlaps,j not in direct,abs(s-end),p.req[j//3]["deadline_tick"]-e,j)
    return sorted((j for j in range(p.n) if j!=i),key=key)


def thermal_order(p,rows,i,hot):
    from scipy.linalg import expm
    # Frozen linearization of the actual violation state. Integrate each earlier
    # active segment's extra heat with the positive affine state transition matrix.
    node=hot["hotspot"]; t=hot["peak_tick"][node]
    events=hot["events"]; adj=np.eye(4)[node]
    scores=np.zeros(p.n)
    units=[sorted((s,p.finish(j,rows[j]),j) for j,(w,k,s) in enumerate(rows) if w==u) for u in range(4)]
    by_end=[len(work)-1 for work in units]
    for row in reversed(events):
        s,e=row[:2]
        if s>=t: continue
        h=(min(e,t)-s)/10000
        A=(-p.G+np.diag(row[6:10]))/p.cap[:,None]
        prop=expm(A*h)
        integral=np.linalg.solve(A.T,(adj@(prop-np.eye(4))).T)
        for u,work in enumerate(units):
            while by_end[u]>=0 and work[by_end[u]][0]>=e: by_end[u]-=1
            if by_end[u]<0: continue
            left,right,j=work[by_end[u]]
            if left<=s and s<right:
                _,k,_=rows[j]
                idle,beta=p.idle[u,k]
                T=(row[14+u]+row[18+u])/2
                q=row[2+u]-idle+(row[6+u]-beta)*(T-35)
                scores[j]+=max(0.,q)*integral[u]/p.cap[u]
        adj=adj@prop
    return sorted((j for j in range(p.n) if j!=i and scores[j]>0),key=lambda j:(-scores[j],j))


def choose_near(points,center,rng):
    points=sorted(set(points),key=lambda x:(abs(x-center),x))
    return rng.choice(points[:min(4,len(points))]) if rng.random()<.8 else rng.choice(points)


def rebuild(p,plan,indices,rng,*,pinned=None,finite=False,origin=None):
    rows=list(plan[0]); low=plan[1]
    original=origin if origin is not None else rows.copy()
    order=list(indices)
    rng.shuffle(order)
    remaining=set(order)
    for i in order:
        remaining.remove(i)
        old=rows[i];opt=old[:2]
        if pinned and i==pinned[0]: opt=pinned[1]
        elif rng.random()<.76:
            choices=sorted(p.options[i],key=lambda nk:p.inc(i,*nk))
            opt=rng.choice(choices if rng.random()<.45 else choices[:max(2,len(choices)//2)])
        spans=list(ranges(p,rows,i,opt,remaining))
        if not spans: return None
        if finite: pts=gridpoints(p,original,i,spans)
        else:
            pts=[]
            for a,b in spans:
                pts.extend((a,b,min(b,max(a,old[2])),rng.randint(a,b)))
        if not pts: return None
        rows[i]=(*opt,choose_near(pts,old[2],rng))
    try: gaps=eligible_gaps(p,rows)
    except Invalid: return None
    low=set(low).intersection(gaps)
    if gaps:
        for key in rng.sample(gaps,rng.randint(0,min(3,len(gaps)))):
            low.symmetric_difference_update([key])
    return rows,frozenset(low)


def eta(p,plan,tracker,*,lft=True):
    """Level slack allocation, then reverse LFT constrained by fixed unit order."""
    rows=list(plan[0])
    fixed=rows.copy()
    for phase in (0,1) if lft else (0,):
        order=sorted(range(p.n),key=lambda i:rows[i][2],reverse=bool(phase))
        for i in order:
            check(tracker.end)
            u,k,t=rows[i]; req=p.req[i//3]
            pred=0 if i%3==0 else p.finish(i-1,rows[i-1])
            chain=range(3*(i//3),3*(i//3)+3)
            fast=[min(p.dur(j,w,f) for w,f in p.options[j] if w==rows[j][0]) for j in chain]
            slack=max(0,req["deadline_tick"]-req["release_tick"]-sum(fast))
            level_limit=req["release_tick"]+sum(fast[:i%3+1])+slack*(i%3+1)//3
            opts=sorted((op for op in p.options[i] if op[0]==u),key=lambda op:p.inc(i,*op))
            for opt in opts:
                spans=list(ranges(p,rows,i,opt,relative=fixed))
                options=[]
                for a,b in spans:
                    a=max(a,pred)
                    if not phase: b=min(b,level_limit-p.dur(i,*opt))
                    if a<=b:
                        s=min(b,max(a,t))
                        if phase: s=(s+b)//2
                        options.append(s)
                if not options: continue
                alt=rows.copy();alt[i]=(*opt,min(options,key=lambda s:abs(s-t)))
                # Full thermal decision for LFT; the chain can retain intermediate
                # legal level allocations even when an individual stage is neutral.
                result=tracker.consider((alt,plan[1]))
                if result and result["status"]=="SAFE": rows=alt
                break
    return rows,plan[1]


def lns(p,plan,tr,rng,mode,orderlog,hot=None):
    current=plan
    current_val=evaluate(p,plan,cert=True)
    orderlog["seed"]=101
    steps=0
    while True:
        check(tr.end);steps+=1
        rows=current[0]
        if mode=="SA":
            size=rng.randint(1,4); i=rng.randrange(p.n)
        else:
            size=rng.choice([2,3,4,5,7,9])
            i=rng.randrange(p.n)
        subset=ordinary(p,rows,i,size,rng) if rng.random()<.55 else [i]+rng.sample([j for j in range(p.n) if j!=i],size-1)
        if steps%3==0:
            subset=list(dict.fromkeys([i,3*(i//3),3*(i//3)+1,3*(i//3)+2,*subset]))[:size]
        orderlog["moves"].append([i,subset])
        alt=rebuild(p,current,subset,rng)
        if alt is None: continue
        result=tr.consider(alt,force=mode=="SA")
        if mode=="SA" and result and result["status"]=="SAFE":
            d=result["E_J"]-current_val["E_J"]
            temp=max(.0002,.025*(1-(time.perf_counter()-tr.start)/(tr.end-tr.start)))
            if d<0 or rng.random()<math.exp(-max(0,d)/temp):
                current,current_val=alt,result
        elif tr.plan is not None: current=tr.plan


def rf(p,plan,group,tr):
    original=plan[0];boundary=p.boundaries[0]
    before=[i for i in range(1,p.n,3) if original[i][2]<boundary]
    after=[i for i in range(1,p.n,3) if original[i][2]>=boundary]
    if not before or not after: return dict(status="SKIP_NO_PAIR")
    a=max(before,key=lambda i:(original[i][2],i));b=min(after,key=lambda i:(original[i][2],i))
    ids=[a,a+1,b,b+1]
    info=dict(stages=ids,status="BOUNDED",complete=False,placements=0)
    info["conditional_lower"]=p.lower(original,set(ids),group=="R")
    def visit(rows,ix):
        check(tr.end)
        if ix==4:
            info["placements"]+=1
            yield rows;return
        i=ids[ix]
        opts=sorted(p.options[i],key=lambda o:(o!=original[i][:2],p.inc(i,*o),o))
        for opt in opts:
            if group=="R" and opt[0]!=original[i][0]: continue
            spans=list(ranges(p,rows,i,opt,set(ids[ix+1:]),original if group=="R" else None))
            for t in gridpoints(p,original,i,spans):
                alt=rows.copy();alt[i]=(*opt,t)
                yield from visit(alt,ix+1)
    # Counted inner enumeration is finite. Prioritize distinct stage schedules, then
    # exhaust idle-policy masks in increasing cardinality across schedules.
    try:
        for card in range(p.n+4):
            any_mask=False
            for rows in visit(original,0):
                gaps=eligible_gaps(p,rows)
                if len(gaps)<card: continue
                any_mask=True
                for mask in itertools.combinations(gaps,card):
                    check(tr.end)
                    tr.consider((rows,frozenset(mask)),force=True)
            if not any_mask:
                info["complete"]=True;info["status"]="EXHAUSTED";break
    except Expired: pass
    return info
