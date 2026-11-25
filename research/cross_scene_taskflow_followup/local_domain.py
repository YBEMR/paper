"""Finite time/resource domain with immutable control in physically unchanged gaps."""
from collections import deque
from itertools import combinations
from time import perf_counter
from fractions import Fraction as Q
import random
from assets import CFG
from model import DOM, Invalid, transitions
from search import ranges,gridpoints,timing,ordinary
from mechanism import targets

def gap_table(p,rows):
    units,sw,_=transitions(p,rows,())
    gaps={}
    for d,work in enumerate((sorted(units[0]+units[1]),units[2],units[3])):
        end=old=0
        for s,e,k,i in [*work,(p.horizon,p.horizon,0,-1)]:
            if old and s-end>=5*(1+int(k!=0)) and (k or s-end>5):
                gaps[(d,i)]=(d,end,s,old,k)
            end=max(end,e);old=k
    return gaps

def controls(p,rows,old_by_signature):
    new=gap_table(p,rows)
    fixed=frozenset(key for key,sig in new.items() if old_by_signature.get(sig,False))
    free=tuple(key for key,sig in new.items() if sig not in old_by_signature)
    return fixed,free

def compatible(p,i,a,j,b):
    u,k,t=a;w,f,s=b
    e=p.finish(i,a);z=p.finish(j,b)
    if i//3==j//3 and (i+1==j and e>s or j+1==i and z>t):
        return False
    if DOM[u]!=DOM[w] or (u!=w and k==f): return True
    guard=5*(k!=f)
    return e+guard<=s or z+guard<=t

class Space:
    def __init__(self,p,base,ids,i,opt):
        self.p=p;self.rows=base[0];self.ids=tuple(ids);self.i=i
        self.domains={}
        for j in ids:
            choices=[]
            for o in ([opt] if j==i else p.options[j]):
                spans=list(ranges(p,self.rows,j,o,set(ids)-{j}))
                for t in gridpoints(p,self.rows,j,spans): choices.append((*o,t))
            self.domains[j]=sorted(choices,key=lambda a:(p.inc(j,*a[:2]),abs(a[2]-self.rows[j][2]),a))
        self.order=sorted(ids,key=lambda j:(j!=i,len(self.domains[j]),j))
    def assignments(self,rng=None,deadline=float("inf")):
        rows=self.rows.copy(); order=self.order.copy()
        if rng and len(order)>1:
            tail=order[1:];rng.shuffle(tail);order=[order[0],*tail]
        def walk(depth):
            if perf_counter()>=deadline: return
            if depth==len(order):
                yield rows.copy();return
            j=order[depth]
            dom=self.domains[j]
            if rng: dom=rng.sample(dom,len(dom))
            for a in dom:
                if perf_counter()>=deadline: return
                if all(compatible(self.p,j,a,h,rows[h]) for h in order[:depth]):
                    rows[j]=a
                    yield from walk(depth+1)
        return walk(0)

def positive_options(p,rows):
    # Preserve the pre-existing best-saving configuration for each request, and
    # enumerate less aggressive positive alternatives so all timing classes can enter.
    old={i:tuple(opt) for i,opt,gain in targets(p,rows)}
    ranked=[]
    for i in range(1,p.n,3):
        u,k,t=rows[i]
        def activity(o):
            w,f=o
            b,_,q,_=p.exact[p.kinds[i],w,f]
            return (q-b)*p.compute[p.kinds[i],w,f]/1000
        for opt in p.options[i]:
            if opt[0]==u and opt[1]>=k: continue
            gain=activity((u,k))-activity(opt)
            if gain>0: ranked.append((i,opt,gain))
    ranked.sort(key=lambda a:(-a[2],abs(rows[a[0]][2]-p.boundaries[0]),a[0],a[1]))
    assert set(old)=={i for i,o,g in ranked}
    return ranked

def blockers(p,rows,i,opt):
    u,k=opt;d=p.dur(i,u,k);t0=rows[i][2];req=p.req[i//3]
    allowed=[(max(req["release_tick"],5 if k else 0),min(req["deadline_tick"],p.horizon-5*(k!=0))-d)]
    points=gridpoints(p,rows,i,allowed)
    near=[j for j,(w,f,s) in enumerate(rows) if j!=i and
          (j in (i-1,i+1) or DOM[w]==DOM[u] and s<t0+500+d+5 and p.finish(j,rows[j])>t0-505)]
    return [(t,tuple(j for j in near if not compatible(p,i,(*opt,t),j,rows[j]))) for t in points]

def make_groups(p,rows,i,opt,raw):
    ranking=timing(p,rows,i,opt)
    closest=ordinary(p,rows,i,5,None)[1:]
    def group(required,variant):
        ids=list(dict.fromkeys([i,*required]))
        partners=[j+1 for j in required if j%3==1]+[i+1]
        fill=(partners+ranking+closest if variant==0 else ranking+partners+closest)
        return tuple(dict.fromkeys(ids+fill))[:5]
    groups=[]
    for t,blocking in sorted(raw,key=lambda a:(len(a[1]),abs(rows[i][2]-a[0]),a[0])):
        if len(blocking)>4: continue
        for v in (0,1):
            g=group(blocking,v)
            if g not in groups: groups.append(g)
    return groups or [group([],0)]

def select_targets(p,base,end):
    rows=base[0];ranked=positive_options(p,rows)
    frozen=[];used=set();screen_cache={};stats={}
    def classify(i,o):
        key=(i,o)
        if key in screen_cache: return screen_cache[key]
        raw=blockers(p,rows,i,o); typ="unclassified"
        if any(not block for _,block in raw):
            typ="solo"
        elif any(set(block)<={i+1} for _,block in raw):
            pair=Space(p,base,[i,i+1],i,o)
            if next(pair.assignments(deadline=end),None) is not None: typ="post"
        if typ=="unclassified" and raw and all(any(j not in (i-1,i+1) for j in block) for _,block in raw):
            typ="competitor_required"
        screen_cache[key]=(typ,raw)
        return typ,raw
    def examine(item,require_witness):
        i,o,gain=item;typ,raw=classify(i,o)
        groups=make_groups(p,rows,i,o,raw)
        first=None
        for ids in groups[:8]:
            space=Space(p,base,ids,i,o)
            w=next(space.assignments(deadline=min(end,perf_counter()+.08)),None)
            if w is not None:
                first=w;break
            if perf_counter()>=end: break
        if first is None and require_witness: return None
        if first is None: ids=groups[0]
        return dict(case=p.case,stage=i,request=i//3,old=rows[i],opt=o,reference_gain_J=str(gain),
            category=typ,members=ids,blocking_by_target_start_tick=raw,
            solo_hold_start_ranges=list(ranges(p,rows,i,o)),witness_edits=None if first is None else
            [[j,*first[j]] for j in ids if first[j]!=rows[j]])
    for typ in ("solo","post","competitor_required"):
        stop=end-1.6
        for rank,item in enumerate(ranked):
            if perf_counter()>=stop:break
            i,o,g=item
            if i in used or classify(i,o)[0]!=typ: continue
            found=examine(item,True)
            if found is not None:
                found["selection"]="coverage";found["rank"]=rank+1
                frozen.append(found);used.add(i);break
    for rank,item in enumerate(ranked):
        if len(frozen)>=CFG["target_cap"]:break
        if item[0] not in used:
            found=examine(item,False)
            found["selection"]="gain_fill";found["rank"]=rank+1
            frozen.append(found);used.add(item[0])
    return dict(targets=frozen,ranked=[(i,o,str(g)) for i,o,g in ranked],
                classified_count=len(screen_cache),cutoff=perf_counter()>=end-1.6)

def masks(keys):
    for count in range(len(keys)+1):
        yield from combinations(keys,count)

def candidates(p,base,space,end,stats):
    # Interleave new placements, affected-gap alternatives and random restarts.
    old={sig:key in base[1] for key,sig in gap_table(p,base[0]).items()}
    rng=random.Random(101);queue=deque();done=False;step=0
    seq=space.assignments(deadline=end)
    while perf_counter()<end:
        step+=1
        if queue and (done or step%3==0):
            rows,fixed,maskgen=queue.popleft()
            mask=next(maskgen,None)
            if mask is not None:
                queue.append((rows,fixed,maskgen))
                yield rows,fixed.union(mask)
            continue
        if done:break
        if step%4==0:
            rs=next(space.assignments(rng,min(end,perf_counter()+.04)),None)
            if rs is not None:
                fixed,keys=controls(p,rs,old)
                yield rs,fixed.union(k for k in keys if rng.random()<.5)
            continue
        rs=next(seq,None)
        if rs is None:
            done=perf_counter()<end
            if not done: return
            continue
        stats["deterministic_placements"]+=1
        fixed,keys=controls(p,rs,old);it=masks(keys);next(it)
        if keys:queue.append((rs,fixed,it))
        yield rs,fixed
    stats["exhausted"]=done and not queue and perf_counter()<end
