"""One contest with a mode-specific incumbent and a shared G2 configuration/refinement protocol."""
import math
import random
from time import perf_counter
import numpy as np
from setup_inputs import g1io
from assets import Q, Layout, read, write, record, assemble, idle_plan
from algorithm import refine, load_at
from feedback import targets, neighborhood
from evaluation import assess_mode, certify_output
from model import independent_events, event_arrays, Invalid
from validation import common_grid
from heat import evaluate
from reference_objective import error_bound
from evolution import evolve, genes
from literature import native_search


class Contest:
    def __init__(self,p,mode,folder,start,charged):
        self.p,self.mode,self.folder=p,mode,folder
        self.start,self.charged=start,charged
        self.best=self.plan=None
        self.calls=0

    def elapsed(self):
        return self.charged+perf_counter()-self.start

    def consider(self,plan,until,archive=False,switches=None):
        if perf_counter()>=until:
            return None
        self.calls+=1
        if archive or self.mode!="T3":
            score=dict(assess_mode(self.p,plan,self.mode,self.folder,switches))
        else:
            a,sw,_=event_arrays(self.p,*plan)
            b,other=independent_events(self.p,*plan)
            x,y=common_grid(a,b)
            if sw!=other or not np.array_equal(x,y):
                raise ValueError("Independent event mismatch")
            m=evaluate(self.p,plan,cert=True)
            score=dict(status=m["status"],eligible=m["status"]=="SAFE",J=m["E_J"],bounds=m["E_bounds"])
        score["in_time"]=perf_counter()<=until
        accepted=score["eligible"] and score["in_time"] and (self.best is None or score["bounds"][1]<self.best["bounds"][0])
        if accepted:
            score["plan"]=g1io.store(self.p,plan)
            self.best=score.copy()
            self.plan=plan
            write(self.folder/"progress.json",dict(elapsed_s=self.elapsed(),best=self.best,assessments=self.calls))
        return score


def configuration(ctx,m,method,seed,phase_end,budget,charged,smoke):
    turn=0
    rounds=max(1,math.ceil((.8*budget-charged)/30))
    while turn<rounds and perf_counter()<phase_end-1.2:
        tick=perf_counter()
        limit=min(phase_end,tick+29.6)
        if limit-tick<1:
            break
        base=genes(ctx.plan)
        before=ctx.best
        if method=="Compact":
            scope=set(range(m.n))
            hint,trace,target,kind=base,[],(),"full"
        else:
            groups=targets(m,base,seed)
            active=[i for i,x in enumerate(groups) if x]
            if not active:
                break
            g=active[turn%len(active)]
            target=groups[g][(turn//len(active))%len(groups[g])]
            kind=("single","group1","group4","group8")[g]
            scope,hint,trace=neighborhood(m,base,target,method,min(m.n,(12,24,32)[turn%3]),min(tick+5,limit-1))
        pool=[]
        def keep(cfg,cost):
            if len(pool)<4:
                pool.append((cfg,cost))
            else:
                pool[-1]=(cfg,cost)
        solver=m.search(base,scope,hint,limit-2,turn+seed,keep)
        judged=[]
        for cfg,_ in reversed(pool):
            if perf_counter()>=limit-.2:
                break
            judged.append(ctx.consider(idle_plan(ctx.p,assemble(ctx.p,cfg)),limit,archive=True))
        delta=[[i,a,b] for i,(a,b) in enumerate(zip(base,genes(ctx.plan))) if a!=b]
        record(ctx.folder/"rounds.jsonl",dict(turn=turn,phase="configuration",target_type=kind,target=target,
               scope=sorted(scope),feedback=trace,before=before,after=ctx.best,real_changes=delta,solver=solver,
               candidates=judged,pool=len(pool),elapsed_s=ctx.elapsed(),round_s=perf_counter()-tick))
        turn+=1
        if smoke or (method=="Compact" and solver["status"]=="EXACT_REFERENCE"):
            break
    return dict(rounds=turn)


def postprocess(ctx,seed,end,budget,smoke=False):
    tick=perf_counter()
    stop=min(end,tick+.20*budget)
    npost=0
    while perf_counter()<stop-2 and npost<math.ceil(.20*budget/30):
        limit=min(stop,perf_counter()+29.6)
        before=ctx.best
        found,stats=refine(ctx.p,ctx.plan,seed,npost,limit-2)
        scores=[]
        for plan,sw,pj in reversed(found):
            if perf_counter()>=limit-.2:
                break
            ref=sum(Layout(ctx.p,plan[0]).components(plan[1]).values())
            if abs(ref-Q(pj,10**12))>error_bound(ctx.p):
                raise ValueError("E2-a reference score differs from independent reconstruction")
            scores.append(ctx.consider(plan,limit,archive=True,switches=sw))
        record(ctx.folder/"rounds.jsonl",dict(phase="timing",turn=npost,before=before,after=ctx.best,
               candidates=scores,solver=stats,elapsed_s=ctx.elapsed()))
        npost+=1
        if smoke:
            break
    return dict(rounds=npost,elapsed_s=perf_counter()-tick,limit_s=.20*budget)


def trial(p,model,case,method,mode,seed,folder,source,start,end,budget,charged,params,smoke=False):
    g1io.OUT=folder/"evidence"
    ctx=Contest(p,mode,folder,start,charged)
    phase_end=end-.20*budget
    seen=set()
    initial_choices=[]
    for item in read(source/"pool.json"):
        key=item.get("plan")
        if key and item["in_time"] and key not in seen:
            seen.add(key)
            plan=load_at(source/"evidence",key)
            score=ctx.consider(plan,phase_end,archive=True)
            if score is not None and score["plan"]!=key:
                raise ValueError("Pool plan hash mismatch")
            initial_choices.append(score)
    write(folder/"initial_choices.json",initial_choices)
    initial=ctx.best
    native=[]
    details={}
    if method in ("Greedy","Adapted-ETA-TS","Adapted-eFLS"):
        native=native_search(ctx,model,method,phase_end-1)
    elif ctx.plan is not None:
        if method in ("Compact","AB","Proposed"):
            details=configuration(ctx,model,method,seed,phase_end,budget,ctx.elapsed(),smoke)
        elif method in ("SA","GA"):
            details=evolve(ctx,model,random.Random(seed),method,phase_end,params,1 if smoke else None)
        else:
            raise ValueError(method)
    conf=ctx.best
    post=postprocess(ctx,seed,end,budget,smoke) if conf else dict(rounds=0,elapsed_s=0,limit_s=.20*budget)
    # Only now may a T0/T1/T2 output receive the actual continuous certificate.
    final=certify_output(p,ctx.best,folder) if ctx.best else None
    result=dict(case=case,method=method,mode=mode,seed=seed,budget_s=budget,initial=initial,
                configuration=conf,selected=ctx.best,final=final,status=final["status"] if final else "NO_SCHEDULE",
                assessments=ctx.calls,native=native,configuration_details=details,post=post,elapsed_s=ctx.elapsed())
    write(folder/"result.json",result)
    return result

