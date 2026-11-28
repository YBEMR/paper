"""One fresh timed cell. No historical maps or certificates are read here."""
import ast
import inspect
import os
import sys
from pathlib import Path
from solver import ROOT, evaluate, f, m
import hot
import online


def score(point):
    if point is None:
        return (2,)
    if point["status"] == "SAFE":
        return (0, point["J"])
    return (1, point["peak"] - 80, point["J"])


def unified(obj, dest):
    eng, flow = m.build(obj, dest)
    groups = [flow.kinds[ids] for ids in eng.groups]
    counts = [(int((t == 0).sum()), int((t == 1).sum())) for t in groups]
    quotas = []
    backlog = [0, 0]
    for j,(a,b) in enumerate(counts):
        # Minimize the maximum estimated finish at the highest legal OPP.
        # Propagate nominal device work across windows. Lexicographic ties.
        start = [max(j*10000, v) for v in backlog]
        def finish(x,y):
            return (start[0]+(a-x)*eng.length["A",2,9]+(b-y)*eng.length["B",2,9],
                    start[1]+x*eng.length["A",3,2]+y*eng.length["B",3,2])
        _,x,y = min((max(finish(x,y)),x,y) for x in range(a+1) for y in range(b+1))
        quotas.extend((x,y))
        backlog = finish(x,y)
    bounds = [n for row in counts for n in row]
    cache = {}
    best_safe = None
    def log(event, **kw):
        f.log(dest/"maps.jsonl", event, **kw)
    def visit(q):
        nonlocal best_safe
        chunks = [flow.extension(t,a,b,0,0,*q[2*j:2*j+2]) for j,(t,(a,b)) in enumerate(zip(groups,counts))]
        mapping = bytes(3 if v==10 else 2 for block in chunks for v in block)
        key = f.digest(mapping)
        if mapping in cache:
            log("cache",mapping=key)
            return cache[mapping]
        idx = len(cache)
        path = dest / "visits" / str(idx)
        path.mkdir(parents=True)
        log("visit",mapping=key,index=idx,quota=q)
        points = []
        def emit(stage, p, reason):
            nonlocal best_safe
            if p and p["status"] in ("SAFE","HOT"):
                points.append(p)
            if p and p["status"]=="SAFE" and (best_safe is None or p["J"]<best_safe["J"]):
                best_safe=p
            log("certificate" if p else "failed",point=p,reason=reason,stage=stage,
                mapping=key,index=idx,incumbent=best_safe["plan"] if best_safe else None)
        evaluate(eng,flow,mapping,path,emit)
        chosen = min(points,key=score,default=None)
        cache[mapping] = chosen
        log("complete",mapping=key,index=idx,point=chosen)
        return chosen
    current = visit(quotas)
    sweep = 0
    while True:
        sweep += 1
        changed = False
        for i, bound in enumerate(bounds):
            original = quotas[i]
            choice, winner = original, current
            log("coordinate",sweep=sweep,coordinate=i,quota=quotas)
            for value in range(bound+1):
                trial = quotas.copy()
                trial[i] = value
                p = visit(trial)
                if score(p) < score(winner):
                    choice, winner = value, p
            quotas[i],current = choice,winner
            changed |= choice != original
            log("coordinate_end",sweep=sweep,coordinate=i,chosen=choice)
        if not changed:
            log("converged",sweep=sweep)
            return


def clock_variant(fn):
    # The only transformed literals in these source functions are the two cutoffs.
    tree = ast.parse(inspect.getsource(fn))
    for node in ast.walk(tree):
        if isinstance(node,ast.Constant) and type(node.value) is int:
            if node.value in (55,60):
                node.value = {55:595,60:600}[node.value]
    ns = {}
    exec(compile(tree,inspect.getsourcefile(fn),"exec"),fn.__globals__,ns)
    return ns[fn.__name__]


def baseline(obj, dest, limit):
    if limit == 600:
        for module, name in ((f,"search"),(f,"refine"),(hot,"census"),(online,"select"),(online,"refine")):
            setattr(module,name,clock_variant(getattr(module,name)))
        online.census = hot.census
    native_flow = m.u2.make_flow
    def measured_flow(api, item, path):
        flow = native_flow(api, item, path)
        native_ledger = flow.ledger
        size = len(flow.p.req)
        maps = set()
        table = bytes(2 if x<10 else 3 for x in range(256))
        def ledger(config,*args,**kwargs):
            result = native_ledger(config,*args,**kwargs)
            closed = args[3] if len(args)>3 else kwargs.get("closed",False)
            if len(config)==size and closed:
                key = bytes(config).translate(table)
                if key not in maps:
                    maps.add(key)
                    f.log(dest/"ledger.jsonl","full_mapping",mapping=f.digest(key))
                if not result[0]:
                    f.log(dest/"ledger.jsonl","timing_failure")
            return result
        flow.ledger = ledger
        return flow
    m.u2.make_flow = measured_flow
    split = limit-5
    search = f.worker(f.search,(obj,"integrated",dest),f.ORIGIN+limit)
    events = f.readlog(dest/"search.jsonl")
    post = None
    if any(e["event"]=="certificate" and e["point"]["status"]=="SAFE" and e["t"]<split for e in events):
        if f.T()<f.ORIGIN+limit:
            post=f.worker(online.refine,(obj,dest,events),f.ORIGIN+limit)
    f.save(dest/"native.json",dict(search=search,refine=post))


if __name__ == "__main__":
    code, arm, budget, folder = sys.argv[1:]
    limit = int(budget)
    assert limit in (60,600)
    f.ORIGIN = m.CLOCK = float(os.environ["CELL_START"])
    dest = Path(folder)
    f.log(dest/"start.jsonl","begin",core=list(os.sched_getaffinity(0)))
    m.RUN = m.u2.stack()
    obj = next(o for o in m.u2.CASES if m.label(o)==code)
    assert arm in ("baseline","unified")
    if arm=="baseline":
        baseline(obj,dest,limit)
    else:
        unified(obj,dest)
