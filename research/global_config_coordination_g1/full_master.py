"""CP-SAT interval master. Fixed rows are compiled into exact unions of start ranges."""
import math
from ortools.sat.python import cp_model as cp
from common import DOM

def subtract(a,b,blocked):
    out=[]
    for l,r in sorted(blocked):
        if r<a:continue
        if l>b:break
        if a<l:out.append((a,l-1))
        a=max(a,r+1)
        if a>b:break
    if a<=b:out.append((a,b))
    return out

class FullMaster:
    def __init__(self,p,base,ids,group,choices=None,pin=None):
        self.p=p;self.base=base;self.ids=tuple(ids);self.group=group
        self.m=m=cp.CpModel();self.x={};self.starts={};self.ends={};self.mode={};self.opts={}
        self.terms=[];self.devs=[];units={};freq={};dom={};ivs=[[] for _ in range(4)]
        self.windows={}
        for i in ids:
            root=3*(i//3)
            shortest=lambda j:min(p.dur(j,u,k) for u,k in p.options[j])
            earliest=p.req[i//3]["release_tick"]+sum(shortest(j) for j in range(root,i))
            latest=min(p.horizon,p.req[i//3]["deadline_tick"]-sum(shortest(j) for j in range(i+1,root+3)))
            self.windows[i]=(earliest,latest)
        moving=set(ids);fixed=[(j,*r,p.finish(j,r)) for j,r in enumerate(base) if j not in moving]
        for i in ids:
            old,level,t0=base[i];req=p.req[i//3]
            s=m.new_int_var(0,p.horizon,f"s{i}");e=m.new_int_var(0,p.horizon,f"e{i}")
            self.starts[i]=s;self.ends[i]=e
            options=list(p.options[i]) if choices is None else sorted({tuple(r[:2]) for r in choices[i]})
            ops=[];variables=[]
            for u,k in options:
                if (group<3 and u!=old) or (group==0 and k!=level):continue
                length=p.dur(i,u,k)
                start_floor, finish_cap = self.windows[i]
                lo=max(start_floor,5*(k!=0))
                hi=min(finish_cap-length,p.horizon-length-5*(k!=0))
                if i%3 and i-1 not in moving:lo=max(lo,p.finish(i-1,base[i-1]))
                if i%3!=2 and i+1 not in moving:hi=min(hi,base[i+1][2]-length)
                blocked=[]
                for j,w,f,t,z in fixed:
                    if DOM[u]!=DOM[w] or (u!=w and k==f):continue
                    g=5*(k!=f)
                    if group<=1 and u==w:
                        if base[j][2]<t0:lo=max(lo,z+g)
                        else:hi=min(hi,t-g-length)
                    if t-g-length+1<=hi and z+g-1>=lo:blocked.append((t-g-length+1,z+g-1))
                intervals=subtract(lo,hi,blocked)
                if choices is not None:
                    points=sorted({r[2] for r in choices[i] if tuple(r[:2])==(u,k) and any(l<=r[2]<=h for l,h in intervals)})
                    intervals=[(t,t) for t in points]
                if not intervals:continue
                v=m.new_bool_var(f"x{i}_{u}_{k}");self.x[i,u,k]=v
                m.add_linear_expression_in_domain(s,cp.Domain.from_intervals(intervals)).only_enforce_if(v)
                ivs[u].append(m.new_optional_interval_var(s,length,e,v,f"I{i}_{u}_{k}"))
                ops.append((u,k));variables.append(v)
            self.opts[i]=ops
            if not ops:m.add_bool_or([]);continue
            m.add_exactly_one(variables)
            units[i]=m.new_int_var(0,3,f"u{i}");freq[i]=m.new_int_var(0,9,f"k{i}");dom[i]=m.new_int_var(0,2,f"d{i}")
            for var,col in [(units[i],[u for u,k in ops]),(freq[i],[k for u,k in ops]),(dom[i],[DOM[u] for u,k in ops])]:
                m.add(var==sum(v*c for v,c in zip(variables,col)))
            q=m.new_int_var(0,len(ops)-1,f"m{i}");m.add(q==sum(j*v for j,v in enumerate(variables)));self.mode[i]=q
            if pin and i in pin:
                u,k,t=pin[i];m.add(s==t)
                if (i,u,k) in self.x:m.add(self.x[i,u,k]==1)
                else:m.add_bool_or([])
            d=m.new_int_var(0,p.horizon,f"delta{i}");m.add_abs_equality(d,s-t0);self.devs.append(d)
            m.add_hint(s,t0)
            for op,v in zip(ops,variables):m.add_hint(v,int(op==(old,level)))
        for arr in ivs:
            if arr:m.add_no_overlap(arr)
        for ix,i in enumerate(ids):
            if i%3 and i-1 in moving:m.add(self.ends[i-1]<=self.starts[i])
            if i not in units:continue
            for j in ids[ix+1:]:
                if j not in units:continue
                a=self.starts[i];b=self.starts[j]
                if group<=1 and base[i][0]==base[j][0]:
                    if base[i][2]<base[j][2]:m.add(self.ends[i]<=b)
                    else:m.add(self.ends[j]<=a)
                if not {DOM[u] for u,k in self.opts[i]} & {DOM[u] for u,k in self.opts[j]}:continue
                same=m.new_bool_var("same_domain");m.add(dom[i]==dom[j]).only_enforce_if(same);m.add(dom[i]!=dom[j]).only_enforce_if(~same)
                diff=m.new_bool_var("different_opp");m.add(freq[i]!=freq[j]).only_enforce_if(diff);m.add(freq[i]==freq[j]).only_enforce_if(~diff)
                ahead=m.new_bool_var("start_order");m.add(a<=b).only_enforce_if(ahead);m.add(a>b).only_enforce_if(~ahead)
                m.add(self.ends[i]+5<=b).only_enforce_if([same,diff,ahead])
                m.add(self.ends[j]+5<=a).only_enforce_if([same,diff,~ahead])
    def rows(self,solver):
        rs=self.base.copy()
        for i in self.ids:
            u,k=self.opts[i][solver.value(self.mode[i])];rs[i]=(u,k,solver.value(self.starts[i]))
        return rs
