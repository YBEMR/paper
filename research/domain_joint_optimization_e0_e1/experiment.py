import gzip,heapq,itertools,math,random,time
from collections import Counter
import numpy as np
from common import *
from compact import Layout,permissions
from master import Master,cp,solver
from bounds import relaxation
from inputs import restore
from model import Problem
from heat import evaluate

def ordered_masks(layout,fixed,free,deg):
    delta={k:layout.gap_delta(k,deg) for k in free}
    cheapest=fixed.union(k for k,v in delta.items() if v<0)
    pairs=sorted((abs(v),k) for k,v in delta.items());yield cheapest,Q(0)
    if not pairs:return
    queue=[(pairs[0][0],0,1)]
    while queue:
        val,j,mask=heapq.heappop(queue)
        yield cheapest.symmetric_difference(pairs[h][1] for h in range(j+1) if mask>>h&1),val
        if j+1<len(pairs):
            w=pairs[j+1][0];bit=1<<(j+1)
            heapq.heappush(queue,(val+w,j+1,mask|bit))
            heapq.heappush(queue,(val-pairs[j][0]+w,j+1,(mask^(1<<j))|bit))

def run(region_name,g,end):
    r=restore(read("regions.json")["regions"][region_name]);p=Problem(r["case"])
    seed=archived(p.case)[1];lay0=Layout(p,seed[0]);base=(seed[0],lay0.normalize(seed[1]));ids=r["ids"]
    master=Master(p,base[0],ids,g)
    bound=relaxation(p,base,r,g,master);L=bound["lb"];rng=random.Random(101)
    name=region_name+"_P"+str(g);folder=ROOT/"e1/logs";folder.mkdir(parents=True,exist_ok=True)
    seen=set();counts=Counter();inc=None;incplan=None;ik=None;safe_bounds={};unresolved=[]
    best35=None;rounds=0;start=end-295;calls=0
    def consider(lay,low,proxy):
        nonlocal inc,incplan,ik,best35,calls
        low=lay.normalize(low);plan=(lay.rows,low)
        identity=sha(raw(obj(p.case,plan)))
        if identity in seen:return
        seen.add(identity);m=evaluate(p,plan,cert=True)
        calls+=1;counts[m["status"]]+=1
        edits=[[i,*lay.rows[i]] for i in ids if lay.rows[i]!=base[0][i]]
        log.write(raw([identity,edits,sorted(low-base[1]),sorted(base[1]-low),str(proxy),m["status"],m["E_bounds"],m["peak_C"]])+b"\n")
        if best35 is None or proxy<best35:best35=proxy
        if m["status"]=="SAFE":
            assert L<=m["E_bounds"][1],(name,"lower bound exceeds SAFE energy",L,m)
            safe_bounds[identity]=m["E_bounds"][0]
            if inc is None or m["E_bounds"][1]<inc["E_bounds"][0]:
                inc,incplan=m,plan;ik=store_plan(p.case,plan)
                hist.write(raw([calls,time.perf_counter()-start,ik,m["E_bounds"]])+b"\n")
        elif m["status"]=="UNRESOLVED":unresolved.append(max(L,m["E_bounds"][0]) if max(m["peak_hi"])<=100 and min(m["minimum_lo"])>=20 else L)

    with gzip.open(folder/(name+"_candidates.jsonl.gz"),"wb",compresslevel=2) as log,gzip.open(folder/(name+"_solver.jsonl.gz"),"wb",compresslevel=2) as slog,(folder/(name+"_incumbents.jsonl")).open("wb") as hist:
        consider(lay0,base[1],sum(lay0.components(base[1]).values()))
        finished=False;proof_id=None;unseen=L;reason="TIME_LIMIT";proxy_opt=None
        if g==0:
            fixed,free=permissions(lay0,r);zero=sum(lay0.components(fixed).values())
            dd={k:lay0.gap_delta(k,35) for k in free}
            proxy_opt=zero+sum(min(0,v) for v in dd.values())
            cheapest40=sum(lay0.components(fixed,40).values())+sum(min(0,lay0.gap_delta(k,40)) for k in free)
            for low,excess in ordered_masks(lay0,fixed,free,40):
                unseen=max(L,float(cheapest40+excess)+bound["residual"]-1e-8) if bound["residual"] is not None else L
                if unseen>=inc["E_bounds"][1]:reason="REMAINDER_DOMINATED";finished=True;break
                if time.perf_counter()>=end:break
                consider(lay0,low,zero+sum(dd[k] for k in low-fixed))
            else:unseen=float("inf");finished=True;reason="EXHAUSTED"
            L=min([unseen,*safe_bounds.values(),*unresolved])
            if finished and all(v>=inc["E_bounds"][1] for k,v in safe_bounds.items() if k!=ik) and all(v>=inc["E_bounds"][1] for v in unresolved):
                proof_id=ik
        else:
            # Reference energy is exact at the completion layer. CP integer scores
            # only order proposals. No score or internal solver bound prunes the true problem.
            coef={}
            for i in ids:
                for u,k in master.opts[i]:
                    b,_,v,_=p.exact[p.kinds[i],u,k]
                    coef[i,u,k]=math.floor((v-b)*p.dur(i,u,k)*10**9/10000)
            while time.perf_counter()<end-.12:
                rounds+=1;m=master.m.clone();typ=rounds%6
                # Entire domain remains covered by L, including all unvisited starts.
                movable=set(ids if typ in (0,1,2) else rng.sample(ids,min(len(ids),1+(rounds//6)%4)))
                score=[];magnitude=0
                for i in ids:
                    if i not in movable:
                        u,k,t=incplan[0][i];m.add(master.x[i,u,k]==1);m.add(master.starts[i]==t)
                    jitter=0 if rounds==1 else rng.choice((0,4000,50000,300000,1200000))
                    for u,k in master.opts[i]:
                        coeff=coef[i,u,k]+(rng.randint(0,jitter) if jitter else 0)
                        score.append(coeff*master.x[i,u,k]);magnitude+=abs(coeff)
                    weight=0 if rounds==1 else rng.choice((0,25,500,2500,10000))
                    direction=rng.choice((-1,0,1))
                    term=master.devs[ids.index(i)] if direction==0 else direction*master.starts[i]
                    score.append(weight*term);magnitude+=weight*p.horizon
                assert magnitude<2**61
                m.minimize(sum(score))
                sl=solver(min(3.0,max(.02,end-time.perf_counter()-.12)))
                st=sl.solve(m);label=sl.status_name(st)
                slog.write(raw([rounds,label,sl.wall_time,sl.objective_value if st in (cp.OPTIMAL,cp.FEASIBLE) else None,
                    sl.best_objective_bound,sorted(movable),magnitude])+b"\n")
                if st==cp.MODEL_INVALID:raise ValueError(sl.response_stats())
                if st not in (cp.FEASIBLE,cp.OPTIMAL):continue
                rows=master.rows(sl);layout=Layout(p,rows);fixed,free=permissions(layout,r)
                hold=sum(layout.components(fixed).values());delta={k:layout.gap_delta(k,35) for k in free}
                energy_low=fixed.union(k for k,v in delta.items() if v<0)
                copy_low=fixed.union(set(free)&set(incplan[1]))
                rand_low=fixed.union(k for k in free if rng.random()<.5)
                near=sorted(free,key=lambda k:abs(delta[k]))[:3]
                alternatives=[energy_low,copy_low,rand_low,*(energy_low.symmetric_difference([k]) for k in near)]
                for low in dict.fromkeys(alternatives):
                    if time.perf_counter()>=end:break
                    consider(layout,low,hold+sum(delta[k] for k in low-fixed))
    save("e1/logs/"+name+".json",dict(region=region_name,group=g,LB=L,own_plan=ik,own=inc,counts=counts,
        bound=bound,unseen_LB=None if not math.isfinite(unseen) else unseen,unresolved=len(unresolved),
        true_optimum_identity=proof_id,termination=reason,independent_candidates=calls,CP_solves=rounds,
        E35_best_visited=str(best35),E35_exact_optimum=str(proxy_opt) if proxy_opt is not None else None,
        solver_score="floor(1e9*reference activity J) plus disclosed search perturbations; no true energy pruning",
        score_floor_error_J=len(ids)/1e9,seed=101,initial=sha(raw(obj(p.case,base))),best_components35=Layout(p,incplan[0]).components(incplan[1])))
