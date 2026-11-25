"""Current-schedule precedence graph, support projection and decision permissions."""
import heapq,itertools,random
from base import *

def projection(p,rows,edits,permutation=None):
    n=p.n;opts=[edits.get(i,r[:2]) for i,r in enumerate(rows)]
    dur=[p.dur(i,*op) for i,op in enumerate(opts)]
    pred=[{} for _ in rows];out=[[] for _ in rows]
    def edge(i,j,sep,kind):
        weight=dur[i]+sep
        if i not in pred[j] or pred[j][i][0]<weight:pred[j][i]=(weight,kind)
    units=unit_lists(rows)
    if permutation:
        u,seq=permutation;units[u]=seq
    for i in range(n):
        if i%3:edge(i-1,i,0,"request")
    for seq in units:
        for i,j in zip(seq,seq[1:]):edge(i,j,5*(opts[i][1]!=opts[j][1]),"unit")
    # Both CPU cores keep their own trial order. Each older job of a given OPP on
    # one core finishes before the most recent such job on that core.
    latest=[{},{}];position={i:r for seq in units[:2] for r,i in enumerate(seq)}
    for i in sorted(units[0]+units[1],key=lambda i:(rows[i][2],p.finish(i,rows[i]),rows[i][1],i)):
        u,k=opts[i]
        for f,j in latest[1-u].items():
            if k!=f:edge(j,i,5,"shared_trial")
        if k not in latest[u] or position[i]>position[latest[u][k]]:latest[u][k]=i
    indegree=[len(v) for v in pred]
    for j in range(n):
        for i,(w,kind) in pred[j].items():out[i].append((j,w,kind))
    todo=[(rows[i][2],i) for i in range(n) if not indegree[i]];heapq.heapify(todo)
    order=[];L=[];U=[];parent=[None]*n;child=[None]*n
    for i,(_,k) in enumerate(opts):
        req=p.req[i//3];s=rows[i][2];L.append(max(req["release_tick"],s-500,5*(k!=0)))
        U.append(min(req["deadline_tick"]-dur[i],s+500,p.horizon-dur[i]-5*(k!=0)))
    while todo:
        _,i=heapq.heappop(todo);order.append(i)
        for j,w,kind in out[i]:
            if L[i]+w>L[j]:L[j]=L[i]+w;parent[j]=(i,kind,w)
            indegree[j]-=1
            if not indegree[j]:heapq.heappush(todo,(rows[j][2],j))
    if len(order)<n:
        return dict(feasible=False,cycle=True,gap=None,path=[],edges=[],support=sorted(edits))
    for i in reversed(order):
        for j,w,kind in out[i]:
            if U[j]-w<U[i]:U[i]=U[j]-w;child[i]=(j,kind,w)
    worst=max(range(n),key=lambda i:(L[i]-U[i],-i))
    if L[worst]>U[worst]:
        path=[worst];edges=[];i=worst
        while parent[i]:
            j,kind,w=parent[i];edges.insert(0,[j,i,kind,w]);path.insert(0,j);i=j
        j=worst
        while child[j]:
            t,kind,w=child[j];edges.append([j,t,kind,w]);path.append(t);j=t
        return dict(feasible=False,cycle=False,gap=L[worst]-U[worst],at=worst,L=L[worst],U=U[worst],
                    path=path,edges=edges,support=sorted(set(path)|set(edits)))
    placed=[0]*n
    for i in order:
        placed[i]=max([L[i],min(rows[i][2],U[i])]+[placed[j]+w for j,(w,kind) in pred[i].items()])
        assert placed[i]<=U[i]
    transitions(p,[(*opts[i],placed[i]) for i in range(n)],set())
    return dict(feasible=True,cycle=False,gap=0,path=[],edges=[],support=sorted(set(edits)|{i for i in order if placed[i]!=rows[i][2]}),
                placements=[[i,s] for i,s in enumerate(placed) if s!=rows[i][2]])

def proposals(p,rows):
    # Static per-kind profile, independent of current energies or certification.
    if not hasattr(p,"proposal_cost"):
        p.proposal_cost={(kind,u,k):float((v[2]-p.exact[kind,u,0][0])*p.profile[kind,u,k][0]/10000)
                         for (kind,u,k),v in p.exact.items()}
    ranked=[]
    for i,(u,k,s) in enumerate(rows):
        cost=lambda f:p.proposal_cost[p.kinds[i],u,f]
        choices=sorted((f for w,f in p.options[i] if w==u and f!=k),key=lambda f:(cost(f),f))
        if choices:ranked.append((cost(k)-cost(choices[0]),i,(u,choices[0])))
    return sorted(ranked,key=lambda x:(-x[0],x[1]))

def generic(p,rows,active,w,it,stale,rng):
    pool=active[w];main=[i for i in pool if i%3==1]
    anchor=rng.choice(main or pool);u,k,t=rows[anchor]
    nearby=sorted(range(p.n),key=lambda i:(abs(rows[i][2]-t),i))
    kind=(it//4+it%4+int(stale>=4))%3
    if kind==0:order=nearby                       # Time-window mixture
    elif kind==1:order=sorted(nearby,key=lambda i:DOM[rows[i][0]]!=DOM[u])
    else:
        first=[i for i in nearby if i%3==1][:5]
        order=list(dict.fromkeys([i for j in first for i in (j,j-1,j+1)]+nearby))
    sf=set([anchor]+order[:5+(it%3)])
    # Expand St independently beyond the configuration-release neighborhood. Include
    # nearby external chain members and resource competitors whose configurations stay fixed.
    relatives=[i for j in sorted(sf) for i in range(3*(j//3),3*(j//3)+3)]
    candidates=list(dict.fromkeys([*sorted(sf),*relatives,*nearby]))
    st=set(candidates[:min(24,max(len(sf)+5,13))])
    return sf,st,dict(operator=["window","resource_overlap","request_chain"][kind],anchor=anchor,
                      targets=[],conditional=[],compensation=[],released=[],fallback=False)

def coordinate(p,rows,active,w,it,stale,seed,phase):
    ranked=proposals(p,rows);local=set(active[w])
    inwin=[r for r in ranked if r[1] in local]
    if not inwin:return None
    positive=[r for r in inwin if r[0]>0];pool=positive or inwin
    width=min(len(pool),max(1,2+it//len(active)+int(stale>=4)))
    primary=pool[((seed-101)+it//len(active)+int(stale>=4))%width]
    around={i for x in (w-1,w,w+1) for i in active.get(x,[])}
    # Locality tie-break favors auxiliaries on the other side of a shared bottleneck.
    auxiliaries=[z for z in ranked if z[0]>0 and z[1] in around and z[1]!=primary[1]]
    auxiliaries.sort(key=lambda z:(abs(rows[z[1]][2]-rows[primary[1]][2])//500,-z[0],z[1]))
    pool=[primary]+auxiliaries[:7];singles={i:projection(p,rows,{i:op}) for _,i,op in pool}
    chosen=[primary];union=set(singles[primary[1]]["support"])
    rest=pool[1:]
    while len(chosen)<3 and rest:
        overlap=lambda z:len(union.intersection(singles[z[1]]["support"]))
        pick=max(rest,key=lambda z:(overlap(z),z[0],-z[1]))
        if not overlap(pick):break
        chosen.append(pick);rest.remove(pick);union.update(singles[pick[1]]["support"])
    attempts=[];units=unit_lists(rows)
    def rating(result):return (int(result["cycle"]),result.get("gap") or 0,len(result["support"]))
    while chosen:
        target={i:op for _,i,op in chosen};edits=target.copy();r=projection(p,rows,edits)
        initial=r.copy();trials=[];sr=set();comps=[];released_nodes=set()
        if not r["feasible"] and not r["cycle"]:
            # Rank speed-up options by recovered ticks, including energy-increasing ones.
            for _ in range(2):
                options=[]
                for i in r["path"]:
                    if i in edits:continue
                    u,k=rows[i][:2];old=p.dur(i,u,k)
                    best=min((op for op in p.options[i] if op[0]==u),key=lambda op:(p.dur(i,*op),op))
                    if p.dur(i,*best)<old:options.append((old-p.dur(i,*best),i,best))
                wins=[]
                for dt,i,op in sorted(options,key=lambda z:(-z[0],z[1]))[:3]:
                    trial=projection(p,rows,{**edits,i:op});trials.append(["speed",i,op,trial["gap"],trial["cycle"]])
                    wins.append((rating(trial),i,op,trial))
                if not wins:break
                _,i,op,test=min(wins,key=lambda x:(x[0],x[1]))
                if rating(test)>=rating(r):break
                edits[i]=op;comps.append(i);r=test
                if r["feasible"]:break
        # Choose contiguous crossing ranges from a conditional resource path.
        if phase==2:
            edges=(r["edges"] or initial["edges"])
            # With a feasible fixed-order projection, look at the actual tight
            # resource neighbors around each target as optional crossings.
            probes=[(i,j) for i,j,typ,_ in edges if typ=="unit"]
            if not probes:
                for i in target:
                    work=units[rows[i][0]];a=work.index(i)
                    if a:probes.append((work[a-1],i))
                    if a+1<len(work):probes.append((i,work[a+1]))
            best=None
            for left,right in probes[:4]:
                for i,sign in [(left,1),(right,-1)]:
                    u=rows[i][0];work=units[u];a=work.index(i)
                    for length in (1,2,3):
                        b=a+sign*length
                        if not 0<=b<len(work) or abs(rows[work[b]][2]-rows[i][2])>1000:continue
                        crossed=work[min(a,b):max(a,b)+1];seq=work.copy();seq.pop(a);seq.insert(b,i)
                        rr=projection(p,rows,edits,(u,seq));trials.append(["order",i,work[b],rr["gap"],rr["cycle"]])
                        if rr["cycle"]:continue
                        pairs={(u,min(i,j),max(i,j)) for j in crossed if j!=i}
                        score=(rating(rr),length,i,work[b])
                        if best is None or score<best[0]:best=(score,pairs,rr,crossed)
            if best:
                _,sr,test,crossed=best;released_nodes=set(crossed)
                if not r["feasible"] and rating(test)<rating(r):r=test
        support=set(r["support"])|set(edits)|released_nodes
        # Unresolved path may still be passed to CP, explicitly labeled as conditional.
        if not r["feasible"]:
            for i in r["path"]:
                if len(comps)>=3:break
                if i not in edits and any(u==rows[i][0] and p.dur(i,u,k)<p.dur(i,*rows[i][:2]) for u,k in p.options[i]):
                    comps.append(i)
        sf=set(edits)|set(comps)
        attempts.append(dict(targets=sorted(target.items()),count=len(support),initial=initial,final=r,trials=trials))
        if len(sf)<=12 and len(support)<=24:
            return sf,support,dict(operator="configuration_support",anchor=primary[1],targets=sorted(target.items()),
                      auxiliary=[z[1] for z in pool[1:]],conditional=attempts,compensation=comps,released=sorted(sr),fallback=False,
                      singleton_support={i:s["support"] for i,s in singles.items()})
        chosen.pop()
    return set(),set(),dict(conditional=attempts)

def select(p,rows,active,w,it,stale,seed,method):
    mode=(1,1,2,3)[it%4]
    if method=="CP-FO" or (method=="Proposed-NoOrder" and mode==2):mode=1
    rng=random.Random(seed*1000003+it*101+min(stale,16))
    coord=method.startswith("Proposed") and mode!=3
    result=coordinate(p,rows,active,w,it,stale,seed,mode) if coord else None
    if result and result[0]:sf,st,log=result
    else:
        sf,st,log=generic(p,rows,active,w,it,stale,rng)
        if coord:log.update(fallback=True,conditional=result[2]["conditional"] if result else [])
    if mode==1:reorder=set()
    elif log["operator"]=="configuration_support":reorder=set(map(tuple,log["released"]))
    else:reorder=None
    maps={i:{u for u,k in p.options[i]} for i in sf} if mode==3 else {}
    rights=Access(sf,st,maps,reorder,None if mode==3 else set(),None,1 if method=="Proposed-Single" else None)
    assert sf<=st and len(sf)<=12 and len(st)<=24
    return mode,rights,log
