"""Production jobs. The parent enforces each deadline; immediate receipts survive a timeout."""
import math
import os
from collections import Counter
from construct import *
from full_cp import Full,cp,solver
from thermal_bound import PJ,exact_parts,simple_bound
from diagnostics import suffix_check

REFS={("B0","hold"):(49.086003096,5.1e-10),("B1-a","hold"):(46.952210277,5.1e-10),
      ("B1-b","hold"):(45.455626019,5.1e-10),("joint","hold"):(45.058877597,5.1e-10),
      ("joint","optimal"):(45.051708031,5.1e-10),("suffix4","optimal"):(45.037736,1e-6)}

def ref_job(case):
    p=problem(case)
    names=["B0","B1-a","B1-b"]+(["joint","suffix4"] if case=="D3" else [])
    for name in names:
        rows=assemble(p,reference(p,name))
        for idle in ("hold","optimal"):
            plan=(rows,frozenset()) if idle=="hold" else idle_plan(p,rows)
            # Save the raw constructor before any checker can reject it.
            attempted=raw(common.obj(p.case,plan))
            write(OUT/"last_reference.json",dict(case=case,reference=name,idle=idle,raw_sha=sha(attempted)))
            try:
                k,c=assess(p,plan)
            except Exception:
                write(OUT/"ref_failure_plan.json",json.loads(attempted))
                raise
            pair=(name,idle)
            row=dict(case=case,name=name,idle=idle,plan=k,E35_J=c["E35_J"],status=c["metrics"]["status"],
                     E_J=c["metrics"]["E_J"],E_bounds=c["metrics"]["E_bounds"])
            if case=="D3" and pair in REFS:
                want,tol=REFS[pair]
                row.update(target=want,absolute_error=abs(want-c["E35_J"]),tolerance=tol)
            record(OUT/"references.jsonl",row)
            if "target" in row:assert row["absolute_error"]<=row["tolerance"],row
    return p

def lines(path):
    return [json.loads(l) for l in path.read_bytes().splitlines()] if path.exists() else []

def baseline(case,deadline):
    p=problem(case)
    if case in SIZES:ref_job(case)
    entries=[r for r in lines(OUT/"references.jsonl") if r["case"]==case and r["status"]=="SAFE"]
    assert entries
    f=Frontier(p)
    jobs=[(1,False)]+[(w,v) for w in (64,256,1024) for v in (False,True)]
    for idx,(width,price) in enumerate(jobs):
        t=perf_counter()
        stop=t+max(0,deadline-t-1.0)/(len(jobs)-idx)
        plan,depth=f.search(width,price,stop-.18)
        row=dict(case=case,width=width,priced=price,depth=depth,time_s=perf_counter()-t)
        if plan is not None:
            k,c=assess(p,plan)
            row.update(plan=k,E35_J=c["E35_J"],E_J=c["metrics"]["E_J"],E_bounds=c["metrics"]["E_bounds"],status=c["metrics"]["status"])
            if row["status"]=="SAFE":entries.append(row)
        else:row["status"]="TIME_LIMIT" if perf_counter()>=stop-.25 else "NO_SURVIVING_STATE"
        row["time_s"]=perf_counter()-t
        record(OUT/"construction.jsonl",row)
    best=min(entries,key=lambda r:(r["E_bounds"][1],r["plan"]))
    write(OUT/"seeds"/(case+".json"),best)

def compare_suffix():
    p=problem("D3")
    f=Frontier(p)
    for n in (4,10,12):
        t=perf_counter()
        result=suffix_check(p,f,n)
        record(OUT/"suffix.jsonl",dict(seconds=perf_counter()-t,**result))

def cp_job(case,method,deadline,started):
    p=problem(case)
    folder=OUT/"cp"/case/method
    seed=read(OUT/"seeds"/(case+".json"))
    best_key=key=seed["plan"]
    initial=load(key)
    upper=Q.from_float(seed["E_bounds"][1])
    floor_bound=simple_bound(p,method)
    bound=floor_bound
    evaluated={}
    history=[]
    def checkpoint(tag):
        item=dict(event=tag,elapsed_s=perf_counter()-started,plan=best_key,upper_J=float(upper),
                  global_lower_exact_J=str(bound),global_lower_J=float(bound),evaluated=len(evaluated))
        record(folder/"timeline.jsonl",item)
    checkpoint("common_seed")
    t=perf_counter()
    core=Full(p,initial,method)
    build_s=perf_counter()-t
    write(folder/"model.json",dict(build_s=build_s,**core.stats()))
    seedcert=read(OUT/"certificates"/(key+".json"))
    assert sum(exact_parts(p,initial,method).values())<=Q.from_float(seedcert["metrics"]["E_bounds"][0])
    iteration=0
    while perf_counter()<deadline-1.5:
        iteration+=1
        # Unsearched complement, outside the most restrictive cutoff, has true energy >= U.
        cut=math.floor(upper*PJ)
        core.m.add(core.total<=cut)
        items=[]
        class Collect(cp.CpSolverSolutionCallback):
            def __init__(self):
                super().__init__()
                self.count=0
            def on_solution_callback(self):
                self.count+=1
                plan=core.plan(self)
                item=(plan,core.switches(self),self.value(core.total))
                if len(items)<12:items.append(item)
                else:items[-1]=item
        cb=Collect()
        sec=min(60,deadline-perf_counter()-1.2)
        if sec<=0:break
        sl=solver(sec)
        # Fixed schedule of search policies, identical for both methods.
        sl.parameters.max_presolve_iterations=2
        sl.parameters.cp_model_presolve=(iteration%3!=2)
        sl.parameters.linearization_level=int(sl.parameters.cp_model_presolve)
        sl.parameters.search_branching=(cp.HINT_SEARCH if iteration%3==1 else cp.AUTOMATIC_SEARCH)
        t=perf_counter()
        st=sl.solve(core.m,cb)
        solving=perf_counter()-t
        if st==cp.MODEL_INVALID: raise ValueError(sl.response_stats())
        residual=Q(math.floor(sl.best_objective_bound),PJ) if st!=cp.INFEASIBLE else None
        # The solver bound refers to the domain at the START of this slice.
        cover=[upper,*evaluated.values()]
        if residual is not None:cover.append(residual)
        bound=max(bound,min(cover))
        checkpoint("partition_bound")
        t=perf_counter()
        certified=0
        for plan,sw,score in items:
            if perf_counter()>deadline-.65:
                record(folder/"pending.jsonl",dict(slice=iteration,plan=store(p,plan),objective_pJ=score,reason="budget"))
                continue
            key,c=assess(p,plan,expected_switches=sw)
            metric=c["metrics"]
            exact=sum(exact_parts(p,plan,method).values())
            assert 0<=exact-Q(score,PJ)<=Q(3*p.horizon+2*p.n,PJ)
            if metric["status"] in ("SAFE","HOT"):assert exact<=Q.from_float(metric["E_bounds"][1])
            prev=read(OUT/"certificates"/(best_key+".json"))["metrics"]
            strict=metric["status"]=="SAFE" and metric["E_bounds"][1]<prev["E_bounds"][0]
            overlap=metric["status"]=="SAFE" and max(metric["E_bounds"][0],prev["E_bounds"][0])<=min(metric["E_bounds"][1],prev["E_bounds"][1])
            record(folder/"candidates.jsonl",dict(slice=iteration,plan=key,status=metric["status"],bounds=metric["E_bounds"],
                   full_reference_J=str(exact),encoded_pJ=score,prior_best=best_key,strict=strict,overlap=overlap,elapsed_s=perf_counter()-started))
            if metric["status"]=="SAFE" and Q.from_float(metric["E_bounds"][1])<upper:
                upper=Q.from_float(metric["E_bounds"][1])
                best_key=key
            if key not in evaluated:
                # An unclassified thermal outcome keeps its physical lower bound in the global partition.
                evaluated[key]=max(exact,Q.from_float(metric["E_bounds"][0])) if metric["status"]=="SAFE" else exact
                core.forbid(plan)
            certified+=1
            checkpoint("evaluation")
        row=dict(slice=iteration,status=sl.status_name(st),branches=sl.num_branches,conflicts=sl.num_conflicts,
                 solve_s=solving,assessment_archive_s=perf_counter()-t,callback_count=cb.count,retained=len(items),
                 evaluated=certified,CP_bound_pJ=sl.best_objective_bound,objective_pJ=sl.objective_value if cb.count else None,
                 cutoff_pJ=cut,elapsed_s=perf_counter()-started)
        record(folder/"slices.jsonl",row)
        history.append(row)
        if st==cp.INFEASIBLE:break
    checkpoint("finish")
    write(folder/"completion.json",dict(plan=best_key,global_lower_exact_J=str(bound),elapsed_s=perf_counter()-started,
                                      slices=len(history),build_s=build_s))
