"""Constructive baselines. Preserve each native output before common-incumbent selection."""
from bisect import insort
from time import perf_counter
from assets import idle_plan, record
from model import DOM, Invalid, construct
from search import Tracker, Expired, eta


def topological_order(p, variant):
    def priority(i):
        ds = [p.dur(i,*op) for op in p.options[i]]
        es = [p.inc(i,*op) for op in p.options[i]]
        spread = max(ds)-min(ds) if variant=="BFS-time" else max(es)-min(es)
        return (-(spread if variant in ("BFS-time","BFS-energy") else 0), -max(ds),
                p.req[i//3]["release_tick"],i)
    if variant == "DFS-WCET":
        return [i+j for i in sorted(range(0,p.n,3),key=priority) for j in range(3)]
    return [i for level in range(3) for i in sorted(range(level,p.n,3),key=priority)]


def domain_energy(work, horizon, rates):
    """Partial schedule's optimal E35 residency and switching, including the final return."""
    end = old = 0
    total = rates[0]*horizon
    for s,e,k,_,_ in [*work,(horizon,horizon,0,-1,-1)]:
        if s >= end:
            gap=s-end
            extra = (rates[old]-rates[0])*gap + .0015*(k!=old)
            if old and gap >= 5*(1+int(k!=0)):
                extra = min(extra,(rates[old]-rates[0])*5 + .0015*(1+int(k!=0)))
            total += extra
        if e > end:
            total += (rates[k]-rates[0])*(e-max(end,s))
        end=max(end,e)
        old=k
    return total


def list_schedule(p, variant, end):
    calendars=[[] for _ in range(3)]
    rates=[{k:float(v[0])/10000 for (dom,k),v in p.domain_idle.items() if d==dom} for d in range(3)]
    totals=[domain_energy([],p.horizon,rate) for rate in rates]
    rows=[None]*p.n
    for depth,i in enumerate(topological_order(p,variant)):
        if perf_counter()>=end-.5:
            return None, dict(status="TIME_LIMIT",stages=depth)
        req=p.req[i//3]
        ready=req["release_tick"] if i%3==0 else p.finish(i-1,rows[i-1])
        best=None
        for u,k in p.options[i]:
            d=DOM[u]
            work=calendars[d]
            dur=p.dur(i,u,k)
            t=max(ready,5*int(k!=0))
            for s,e,f,v,_ in work:
                if u!=v and k==f:
                    continue
                guard=5*int(k!=f)
                if t+dur+guard<=s:
                    break
                if t<e+guard:
                    t=e+guard
            finish=t+dur
            if finish>req["deadline_tick"] or finish+5*int(k!=0)>p.horizon:
                continue
            trial=work.copy()
            insort(trial,(t,finish,k,u,i))
            power=domain_energy(trial,p.horizon,rates[d])
            rank=(p.inc(i,u,k)+power-totals[d],finish,t,u,k)
            if best is None or rank<best[0]:
                best=(rank,trial,power)
        if best is None:
            return None, dict(status="NO_PLACEMENT",stages=depth,stage=i)
        (_,_,t,u,k),trial,power=best
        calendars[DOM[u]]=trial
        totals[DOM[u]]=power
        rows[i]=(u,k,t)
    return idle_plan(p,rows),dict(status="COMPLETE",stages=p.n)


def native_search(ctx, model, method, end):
    p=ctx.p
    native=[]
    def submit(label, plan, info):
        score=ctx.consider(plan,end,archive=True) if plan is not None else None
        native.append(dict(source=label,**info,score=score))
    if method=="Greedy":
        cfg,depth=model.construct(1,end-1,priced=True)
        from evolution import evolved_plan
        submit("one-step-energy-and-capacity",evolved_plan(p,cfg) if cfg else None,dict(depth=depth))
    elif method=="Adapted-eFLS":
        for variant in ("DFS-WCET","BFS-WCET","BFS-time","BFS-energy"):
            plan,stats=list_schedule(p,variant,end)
            submit(variant,plan,stats)
    elif method=="Adapted-ETA-TS":
        tracker=Tracker(p,end)
        for k in (9,5,3,2,1,0):
            if perf_counter()>=end-1:
                break
            plan=construct(p,"heft",k)
            result=tracker.consider(plan,force=True)
            native.append(dict(source="P1-HEFT",level=k,status=result["status"] if result else "ILLEGAL"))
        if tracker.safe_plan is not None:
            submit("P1-HEFT-native-initial",tracker.safe_plan,dict(status="COMPLETE"))
        base=tracker.safe_plan or ctx.plan
        if base is not None and perf_counter()<end-1:
            origin="P1-HEFT" if tracker.safe_plan is not None else "common-only"
            try:
                eta(p,base,tracker)
            except Expired:
                pass
            submit("P1-level-slack-and-reverse-LFT",tracker.safe_plan,dict(origin=origin,stages=p.n,
                   considered=tracker.count,invalid=tracker.invalid,certified=tracker.certified))
    else:
        raise ValueError(method)
    for item in native:
        record(ctx.folder/"native.jsonl",item)
    return native

