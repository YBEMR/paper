"""Synchronous bounded displacement propagation and an exact-on-objectives submodel."""
from c1r_assets import C
from support import pairs,cp
from base import np,clock

def options(p,rows,ids):
    return [sorted(f for a,f in p.options[i] if a==u) if i in ids else [k] for i,(u,k,t) in enumerate(rows)]

def bounds(p,rows,i,f):
    u,_,t=rows[i];r=p.req[i//3];d=p.dur(i,u,f)
    lo=max(t-500,r["release_tick"],5 if f else 0)
    hi=min(t+500,r["deadline_tick"]-d)
    if f:hi=min(hi,p.horizon-5-d)
    return lo,hi

def graph(p,rows,levels):
    # Kinds retain the exact conditional constraints in the solver.
    edges=[(i-1,i,"chain") for i in range(1,len(rows)) if i%3]
    edges.extend((i,j,"unit" if same else "cpu") for i,j,same in pairs(p,rows,levels))
    return edges

def residuals(p,rows,levels,edges):
    weights=[]
    for i,j,kind in edges:
        choices=[p.dur(i,rows[i][0],a)+5*(kind!="chain" and a!=b)
                 for a in levels[i] for b in levels[j] if kind!="cpu" or a!=b]
        assert choices
        weights.append(max(choices)+rows[i][2]-rows[j][2])
    return np.asarray(weights,dtype=np.int64)

def propagate(p,rows,levels,edges):
    t=np.array([r[2] for r in rows]);boundsets=[[bounds(p,rows,i,k) for k in fs] for i,fs in enumerate(levels)]
    lower=np.maximum(0,[max(v[0] for v in vs)-t[i] for i,vs in enumerate(boundsets)])
    upper=np.maximum(0,[t[i]-min(v[1] for v in vs) for i,vs in enumerate(boundsets)])
    src=np.asarray([i for i,j,k in edges],dtype=int);dst=np.asarray([j for i,j,k in edges],dtype=int)
    pressure=residuals(p,rows,levels,edges)
    early=np.zeros(len(rows),dtype=np.int64);late=early.copy()
    for _ in range(24):
        a=upper.copy();b=lower.copy()
        np.maximum.at(b,dst,late[src]+pressure)
        np.maximum.at(a,src,early[dst]+pressure)
        early=np.minimum(a,500);late=np.minimum(b,500)
    return early.tolist(),late.tolist()

def constant_or_add(m,expr):
    if isinstance(expr,bool):
        if not expr:m.add_bool_or([])
    else:m.add(expr)

def legal_assignment(p,base,rows,ids,levels,edges):
    if len(rows)!=len(base) or sum(a!=b for a,b in zip(base,rows))>24:return False
    for i,((u,k,t),(v,f,s)) in enumerate(zip(base,rows)):
        if v!=u or f not in levels[i] or (i not in ids and f!=k):return False
        lo,hi=bounds(p,base,i,f)
        if not lo<=s<=hi:return False
    for i,j,kind in edges:
        u,f,t=rows[i];g=rows[j][1]
        if kind=="cpu" and f==g:continue
        if t+p.dur(i,u,f)+5*(kind!="chain" and f!=g)>rows[j][2]:return False
    return True

def proxy(p,rows,plan):
    def rate(i,u,k):
        return round(10**6*(p.exact[p.kinds[i],u,k][2]-p.exact[p.kinds[i],u,0][0])*p.dur(i,u,k)/10000)
    return sum(rate(i,u,k)-rate(i,u,b[1]) for i,((u,k,t),b) in enumerate(zip(rows,plan)) if k!=b[1])

class CompactModel:
    def __init__(self,p,rows,ids,levels,edges,early,late):
        self.rows=rows;self.p=p;self.m=m=cp.CpModel()
        self.starts=[];self.ends=[];self.levels=[];self.x={};self.z=[];self.dev=[];gains=[]
        self.retained=[i for i in range(len(rows)) if i in ids or early[i] or late[i]]
        for i,(u,k,t) in enumerate(rows):
            fs=levels[i]
            if i not in ids and not early[i] and not late[i]:
                self.starts.append(t);self.ends.append(t+p.dur(i,u,k));self.levels.append(k)
                self.z.append(0);self.dev.append(0);continue
            r=p.req[i//3];lo=max(t-early[i],r["release_tick"]);hi=min(t+late[i],r["deadline_tick"]-min(p.dur(i,u,f) for f in fs))
            assert lo<=t<=hi
            s=m.new_int_var(lo,hi,"s") if lo!=hi else t
            if isinstance(s,int):dt=0
            else:
                dt=m.new_int_var(0,max(early[i],late[i]),"dt");m.add_abs_equality(dt,s-t)
            if len(fs)>1:
                xs=self.x[i]={f:m.new_bool_var("opp") for f in fs};m.add_exactly_one(xs.values())
                freq=m.new_int_var(min(fs),max(fs),"f");m.add(freq==sum(f*v for f,v in xs.items()))
                dur=sum(p.dur(i,u,f)*v for f,v in xs.items());end=s+dur
                rate=lambda f:round(10**6*(p.exact[p.kinds[i],u,f][2]-p.exact[p.kinds[i],u,0][0])*p.dur(i,u,f)/10000)
                gains.extend((rate(k)-rate(f))*v for f,v in xs.items());changed=1-xs[k]
                for f,v in xs.items():
                    if f:
                        if not isinstance(s,int) or s<5:m.add(s>=5).only_enforce_if(v)
                        m.add(end<=p.horizon-5).only_enforce_if(v)
            else:
                freq=k;end=s+p.dur(i,u,k);changed=0
                if k:
                    constant_or_add(m,s>=5);constant_or_add(m,end<=p.horizon-5)
            constant_or_add(m,end<=r["deadline_tick"])
            if isinstance(dt,int) and isinstance(changed,int):z=0
            else:
                z=m.new_bool_var("z");m.add(dt<=500*z);m.add(z>=changed);m.add(z<=dt+changed)
            self.starts.append(s);self.ends.append(end);self.levels.append(freq);self.z.append(z);self.dev.append(dt)
        for i,j,kind in edges:
            end=self.ends[i];start=self.starts[j]
            if kind!="cpu":constant_or_add(m,end<=start)
            if kind=="chain":continue
            a,b=self.levels[i],self.levels[j]
            if isinstance(a,int) and isinstance(b,int):
                if a!=b:constant_or_add(m,end+5<=start)
            else:
                diff=m.new_bool_var("different");m.add(a!=b).only_enforce_if(diff);m.add(a==b).only_enforce_if(~diff)
                m.add(end+5<=start).only_enforce_if(diff)
        m.add(sum(self.z)<=24);self.gain=sum(gains)
        m.maximize(self.gain*300025-sum(self.z)*12001-sum(self.dev))
        assert not m.validate(),m.validate()

    def hint(self,rows):
        self.m.clear_hints()
        for i,((u,k,t),(_,old,ot)) in enumerate(zip(rows,self.rows)):
            for var,value in ((self.starts[i],t),(self.z[i],int(k!=old or t!=ot)),(self.dev[i],abs(t-ot))):
                if isinstance(var,int):assert var==value
                else:self.m.add_hint(var,value)
            if i in self.x:
                self.m.add_hint(self.levels[i],k)
                for f,x in self.x[i].items():self.m.add_hint(x,int(k==f))

    def decode(self,solver):
        return [(u,solver.value(self.levels[i]) if i in self.x else k,solver.value(self.starts[i]))
                for i,(u,k,t) in enumerate(self.rows)]
