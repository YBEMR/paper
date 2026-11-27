"""Bound the complete frozen E2-a model build and search in a disposable single-core process."""
import multiprocessing as mp
import time,traceback

def child(pipe,p,plan,requests,permission,limit):
    try:
        from reference_objective import Core,error_bound,PJ
        from master import cp,solver
        from compact import Layout
        from fractions import Fraction
        start=time.monotonic()
        ids=sorted(3*j+k for j in requests for k in range(3))
        core=Core(p,plan,ids,permission,region={'prior':{},'envelopes':[]})
        built=time.monotonic()-start
        left=limit-built-0.5
        if left<=0:
            pipe.send((None,dict(status='BUILD_CUTOFF',build_s=built)));return
        sl=solver(min(22,left));sl.parameters.random_seed=101;sl.parameters.max_presolve_iterations=2
        status=sl.solve(core.m);info=dict(status=sl.status_name(status),branches=sl.num_branches,build_s=built,solve_s=sl.wall_time,
               variables=len(core.m.Proto().variables),constraints=len(core.m.Proto().constraints),
               bound_pJ=sl.best_objective_bound)
        candidate=None
        if status in (cp.FEASIBLE,cp.OPTIMAL):
            candidate=core.plan(sl)
            assert Layout(p,candidate[0]).switches(candidate[1])==core.switches(sl)
            ref=sum(Layout(p,candidate[0]).components(candidate[1]).values())
            assert abs(ref-Fraction(sl.value(core.total),PJ))<=error_bound(p)
            info['objective_pJ']=sl.value(core.total)
        elif status==cp.MODEL_INVALID:raise RuntimeError(sl.response_stats())
        pipe.send((candidate,info))
    except BaseException:
        pipe.send((None,dict(status='ERROR',traceback=traceback.format_exc())))
    finally:pipe.close()

def local(p,plan,requests,permission,limit):
    ctx=mp.get_context('fork');rx,tx=ctx.Pipe(False);start=time.monotonic()
    proc=ctx.Process(target=child,args=(tx,p,plan,requests,permission,limit-.25))
    proc.start();tx.close()
    try:
        if rx.poll(max(0,limit-.35-(time.monotonic()-start))):
            cand,info=rx.recv()
        else:
            cand=None;info=dict(status='INTERRUPTED_LOCAL_LIMIT')
    finally:
        rx.close()
        if proc.is_alive():proc.kill()
        proc.join()
    info['local_wall_s']=time.monotonic()-start
    return cand,info
