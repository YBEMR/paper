"""One private problem, solver seed and certification cache per numerical run."""
import random
from base import *
from neighborhood import select
from verify_core import check

def seeded(seconds,seed):
    s=solver(seconds);s.parameters.random_seed=seed;s.parameters.num_workers=1
    return s

def cp_candidates(core,current,seed,seconds,alternate):
    m=core.m.clone()
    if alternate:
        pins=core.assignment(current)
        m.add_forbidden_assignments([v for v,x in pins],[[x for v,x in pins]])
        # Diversify only this second call. The first still searches the original full domain.
        m.add(sum(1-core.master.x[i, *current[0][i][:2]] for i in sorted(core.access.sf))>=1)
        m.add(sum(core.master.devs)>=1)
    class Collect(cp.CpSolverSolutionCallback):
        def __init__(self):super().__init__();self.sol=[]
        def on_solution_callback(self):
            self.sol.append((core.plan(self),{k:self.value(v) for k,v in core.parts.items()},core.switches(self)))
            if len(self.sol)>=6:self.stop_search()
    cb=Collect();sl=seeded(seconds,seed)
    sl.parameters.cp_model_presolve=alternate;sl.parameters.max_presolve_iterations=2
    sl.parameters.linearization_level=int(alternate)
    status=sl.solve(m,cb)
    if status==cp.MODEL_INVALID:raise ValueError(sl.response_stats())
    return cb.sol,dict(status=sl.status_name(status),seed=sl.parameters.random_seed,seconds=sl.wall_time,
                        returned=len(cb.sol),callback_cap=6,bound_pJ=sl.best_objective_bound,alternative=alternate,
                        require_config_and_time=alternate)

def rights_check(p,base,alt,access,region):
    rows,low=alt;orig=base[0]
    delta=changes(p,base,alt)
    assert set(delta["config"])<=access.sf and set(delta["moved"])<=access.st
    assert all(abs(rows[i][2]-orig[i][2])<=500 for i in access.st)
    assert access.max_changes is None or len(delta["config"])<=access.max_changes
    for i in delta["config"]:assert rows[i][0] in access.maps.get(i,{orig[i][0]})
    assert access.reorder is None or all((u,min(i,j),max(i,j)) in access.reorder for u,i,j in delta["inversions"])
    lay=Layout(p,rows);assert lay.normalize(low)==low
    for k,sig in lay.flex.items():
        e=region["prior"].get(sig)
        assert e is None or e[0] or (k in low)==e[1]
    return delta

class Engine:
    def __init__(self,case,method,seed):
        self.p=p=Problem(case);self.method=method;self.seed=seed
        self.initial,self.start=archived(case);self.windows=bins(p);self.memo={}
        self.initial_m=evaluate(p,self.start,cert=True);assert self.initial_m["status"]=="SAFE"
        self.memo[self.initial]=self.initial_m
    def step(self,current,iteration,stale,end):
        p=self.p;seed=self.seed;src=key(p,current);t=clock()
        n=len(self.windows);window=(iteration%n+iteration//n+(seed-101))%n
        group,access,trace=select(p,current[0],self.windows,window,iteration,stale,seed,self.method)
        r=dynamic_region(p,current,access.st,access.sf,group);assert r["source"]==src
        core=Core(p,current,sorted(access.st),group,region=r,access=access)
        record=dict(iteration=iteration,window=window,source=src,region=r["identity"],Sf=sorted(access.sf),St=sorted(access.st),
             Sr=None if access.reorder is None else sorted(access.reorder),Sg_eligible_original=sum(v[0] for v in r["prior"].values()),
             cap=access.max_changes,mode=group,anchor=trace["anchor"],operator=trace,blocks=core.blocks,arcs=core.arcs,
             cp_seed=seed,setup_s=clock()-t,solves=[],candidates=[],unreturned=[],uncertified=[])
        options={};best=None
        warm=core.m.clone()
        for v,x in core.assignment(current):warm.add(v==x)
        remaining=end-clock()
        if remaining>.35:
            sl=seeded(min(2.0,remaining-.25),seed);status=sl.solve(warm);record["warm"]=sl.status_name(status)
            if status in (cp.INFEASIBLE,cp.MODEL_INVALID):raise AssertionError(("current infeasible in rebuilt boundary",src,record))
            if status in (cp.OPTIMAL,cp.FEASIBLE):
                assert core.plan(sl)==current
                check(p,current,{k:sl.value(v) for k,v in core.parts.items()},core.switches(sl))
                core.m.clear_hints()
                for j in range(len(core.m.proto.variables)):
                    v=core.m.get_int_var_from_proto_index(j);core.m.add_hint(v,sl.value(v))
        for alternate in (False,True):
            remaining=end-clock()
            seconds=min(6 if alternate else 7,remaining-(1.6 if alternate else 2.5))
            if seconds<.08:
                record["unreturned"].append([alternate,"insufficient remaining time"]);continue
            sols,log=cp_candidates(core,current,seed,seconds,alternate);record["solves"].append(log)
            if not sols:record["unreturned"].append([alternate,log["status"]])
            for plan,parts,sw in sols:
                k=key(p,plan)
                if alternate:
                    assert any(a[:2]!=b[:2] for a,b in zip(plan[0],current[0])) and any(a[2]!=b[2] for a,b in zip(plan[0],current[0]))
                if k in options:continue
                if clock()>=end-.10:
                    record["uncertified"].append([k,"time_limit"]);continue
                exact,err=check(p,plan,parts,sw);delta=rights_check(p,current,plan,access,r)
                m=self.memo.get(k);reused=m is not None
                if not reused:self.memo[k]=m=evaluate(p,plan,cert=True)
                options[k]=True;now=clock()
                record["candidates"].append(dict(sha=k,status=m["status"],bounds=m["E_bounds"],E35=str(sum(exact.values())),
                                      cached=reused,config=len(delta["config"]),moved=len(delta["moved"]),time=now))
                if now>end:continue
                if m["status"]=="SAFE" and m["E_bounds"][1]<self.memo[src]["E_bounds"][0] and (best is None or m["E_bounds"][1]<best[2]["E_bounds"][1]):
                    best=(k,plan,m,delta)
        record["elapsed_s"]=clock()-t
        return record,best

def g3(path,case,seed,start,end):
    from search import Tracker,lns,Expired
    p=Problem(case);k0,base=archived(case);tr=Tracker(p,end-.65,thermal=True);tr.start=start
    # The implementation of lns writes a historical literal seed field. The actual
    # random stream below, its seed and all emitted move choices are recorded.
    w=bins(p);counts=Counter();targets=set();last=None;accepted=0
    with gzip.open(path/"moves.jsonl.gz","wb",compresslevel=2) as move,gzip.open(path/"history.jsonl.gz","wb",compresslevel=2) as log,gzip.open(path/"plans.jsonl.gz","wb",compresslevel=2) as pl:
        class Recorder:
            def append(self,v):
                i,st=v;counts[p.req[i//3]["release_tick"]//2500]+=1;targets.update(st);move.write(raw(v)+b"\n")
        def improve():
            nonlocal last,accepted
            if tr.safe is None:return
            plan=tr.safe_plan;ident=key(p,plan)
            if last and ident==last[0]:return
            stamp=tr.history[-1][0]
            change=changes(p,last[1],plan) if last else None
            log.write(raw(dict(t=stamp,before=last[0] if last else None,after=ident,metrics=components(tr.safe),actual=change))+b"\n")
            pl.write(raw([ident,obj(p.case,plan)])+b"\n");last=(ident,plan);accepted+=1
        tr.on_change=improve;tr.consider(base,force=True)
        try:lns(p,base,tr,random.Random(seed),"G3",dict(moves=Recorder()))
        except Expired:pass
    save(path/"summary.json",dict(case=case,method="G3",seed=seed,initial=k0,final=last[0],metrics=components(tr.safe),
           accepted=accepted-1,windows=counts,stages=len(targets),total_windows=len(w),reach_n=p.n,
           source_method="frozen search.lns / Tracker",attempts=tr.count,independent_certifications=tr.certified,
           prefilter_or_invalid=tr.count-tr.certified,invalid=tr.invalid,elapsed_s=clock()-start,cpu_s=time.process_time()))

def service(conn,case,method,seed,cpu):
    import psutil,traceback
    try:
        proc=psutil.Process();proc.cpu_affinity([cpu]);engine=Engine(case,method,seed)
        conn.send(("ready",engine.initial,engine.start,engine.initial_m,len(engine.windows),engine.p.n))
        while True:
            msg=conn.recv()
            if msg is None:break
            plan,m,idx,stale,end=msg;engine.memo[key(engine.p,plan)]=m
            rec,best=engine.step(plan,idx,stale,end)
            conn.send(("result",rec,best,proc.memory_info().peak_wset,time.process_time()))
    except (EOFError,BrokenPipeError):pass
    except Exception:
        conn.send(("error",traceback.format_exc()))
    finally:conn.close()
