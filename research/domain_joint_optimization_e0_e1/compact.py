"""Configuration intervals, frontier recurrence, exact residency costs and independent event compiler."""
from collections import Counter
from bisect import bisect_right
from fractions import Fraction as Q
import numpy as np
from common import DOM,MEMBERS

class Illegal(ValueError):pass

def idle_exact(p):
    if not hasattr(p,"domain_idle"):
        p.node_idle={(u,k):v[:2] for (name,u,k),v in p.exact.items()}
        p.domain_idle={(d,k):tuple(sum(p.node_idle[u,k][a] for u in members) for a in (0,1))
                       for d,members in enumerate(MEMBERS) for u,k in p.node_idle if u==members[0]}
    return p.domain_idle

class Layout:
    def __init__(self,p,rows):
        idle_exact(p)
        self.p=p;self.rows=rows;self.by_unit=[[] for _ in range(4)]
        self.gaps={};self.flex={};self.work=[[] for _ in range(3)]
        if len(rows)!=p.n:raise Illegal("stage count")
        for i,(u,k,s) in enumerate(rows):
            if type(s)!=int or s<0 or (u,k) not in p.options[i]:raise Illegal("time or option")
            e=p.finish(i,rows[i]);r=p.req[i//3]
            if e>p.horizon or (i%3==0 and s<r["release_tick"]) or (i%3==2 and e>r["deadline_tick"]):raise Illegal("window")
            if i%3 and s<p.finish(i-1,rows[i-1]):raise Illegal("precedence")
            self.by_unit[u].append((s,e,k,i))
        for seq in self.by_unit:
            seq.sort()
            if any(a[1]>b[0] for a,b in zip(seq,seq[1:])):raise Illegal("unit overlap")
        for d,units in enumerate(MEMBERS):
            seq=sorted(z for u in units for z in self.by_unit[u]);self.work[d]=seq
            front=old=0;owners=()
            for s,e,k,i in [*seq,(p.horizon,p.horizon,0,-1)]:
                if s<front:
                    if k!=old:raise Illegal("mixed shared OPP")
                else:
                    if s-front<5*(k!=old):raise Illegal("transition gap")
                    key=(d,i);sig=(d,front,s,old,k)
                    self.gaps[key]=(sig,owners)
                    if old and s-front>=5*(1+int(k!=0)) and (k or s-front>5):self.flex[key]=sig
                    old=k
                if e>front:front=e;owners=(i,)
                elif e==front:owners=(*owners,i)
    def normalize(self,low):
        for key in low:
            if key in self.gaps:
                (_,a,b,old,k),_=self.gaps[key]
                if old and b-a<5*(1+int(k!=0)):raise Illegal("early-low gap")
        return frozenset(k for k in low if k in self.flex)
    def switches(self,low):
        low=self.normalize(low);sw=[]
        for key,(sig,_) in self.gaps.items():
            d,a,b,old,k=sig
            if key in low:
                sw.append((a,a+5,d,old,0));old=0
            if old!=k:sw.append((b-5,b,d,old,k))
        return sorted(sw)
    def components(self,low,deg=35):
        p=self.p;sw=self.switches(low);dwell=Counter()
        for d in range(3):
            cur=last=0
            for end,new in [(b,n) for a,b,h,k,n in sw if h==d]+[(p.horizon,0)]:
                dwell[d,cur]+=end-last;last=end;cur=new
        times=Counter()
        for i,(u,k,s) in enumerate(self.rows):times[p.kinds[i],u,k]+=p.dur(i,u,k)
        base=sum((p.domain_idle[key][0]+(deg-35)*p.domain_idle[key][1])*t for key,t in dwell.items())/10000
        act=Q(0)
        for key,t in times.items():
            b,l,v,g=p.exact[key];act+=(v-b+(deg-35)*(g-l))*t/10000
        return dict(base=base,activity=act,switch=Q(15*len(sw),10000),external=Q(3*p.horizon,100000))
    def gap_delta(self,key,deg):
        d,a,b,old,k=self.flex[key];idle=self.p.domain_idle
        watts=lambda f:idle[d,f][0]+(deg-35)*idle[d,f][1]
        # After the first down-switch completes, old OPP is replaced by L until the
        # original hold-mode switch completes (or until next start when K=old).
        ticks=b-a-5
        extra=1+int(k!=0)-int(k!=old)
        return (watts(0)-watts(old))*ticks/10000+Q(15*extra,10000)
    def events(self,low):
        p=self.p;sw=self.switches(low);cuts={0,p.horizon,*p.boundaries}
        runs=[[] for _ in range(3)]
        for d in range(3):
            tail=cur=0
            for a,b,h,k,f in sw:
                if h!=d:continue
                if tail<a:runs[d].append((tail,a,cur,False))
                runs[d].append((a,b,k,True));cuts.update((a,b));tail=b;cur=f
            if tail<p.horizon:runs[d].append((tail,p.horizon,cur,False))
        for work in self.by_unit:
            for s,e,k,i in work:cuts.update((s,e))
        pts=sorted(cuts);out=np.empty((len(pts)-1,14));ix=[0]*4;di=[0]*3
        for j,(s,e) in enumerate(zip(pts,pts[1:])):
            out[j,:2]=s,e
            for d in range(3):
                while runs[d][di[d]][1]<=s:di[d]+=1
            for u,seq in enumerate(self.by_unit):
                d=DOM[u];_,_,k,switch=runs[d][di[d]]
                while ix[u]<len(seq) and seq[ix[u]][1]<=s:ix[u]+=1
                b,v=p.idle[u,k];out[j,10+u]=b
                if ix[u]<len(seq) and seq[ix[u]][0]<=s:
                    _,_,freq,i=seq[ix[u]]
                    if freq!=k or switch:raise Illegal("inconsistent frontier state")
                    _,b,v=p.profile[p.kinds[i],u,k]
                out[j,2+u]=b+(1.5 if d==0 else 3)*switch;out[j,6+u]=v
        return out

def permissions(layout,region):
    prior=region["prior"];free=[];fixed=set()
    for key,sig in layout.flex.items():
        entry=prior.get(sig)
        if entry is None or entry[0]:free.append(key)
        elif entry[1]:fixed.add(key)
    return frozenset(fixed),tuple(sorted(free))
