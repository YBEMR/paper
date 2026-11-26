"""Measured exact regression and policy checks before using formal samples."""
import ast
import gzip
import json
from design_d import C2,ROOT,METHODS,use_aux,core_kind,read,write

def regress():
    import preflight
    preflight.ROOT=ROOT
    preflight.run()
    # Compare the actual executable arithmetic in both methods with the frozen
    # original. Only a local binding and the return of the split point are new.
    def fn(path,name):
        node=next(v for v in ast.walk(ast.parse(path.read_bytes())) if isinstance(v,ast.FunctionDef) and v.name==name)
        return [ast.dump(x,include_attributes=False) for x in node.body]
    old=fn(C2/"cp_worker.py","auxiliary")
    new=fn(ROOT/"engine_d.py","make_hint")[:-1]+fn(ROOT/"engine_d.py","solve_compact")[2:]
    assert new==old,"hint/compact arithmetic differs from E2-c2"
    import engine_d,cp_worker
    for name in ("execute","offer","assignment","check_time"):
        assert getattr(engine_d.Engine,name) is getattr(cp_worker.Engine,name)
    variants=[]
    for m in METHODS:
        for i in range(4):
            for has in ((False,) if i==3 else (False,True)):
                grant={"sf":[1],"st":[1,2]} if has else None
                kind=core_kind(m,i,grant)
                assert kind==("ordinary_full" if i==3 else "fallback" if not has else None if m=="NoCore" else "compact_core")
                assert use_aux(m)==(m!="NoAux")
                variants.append(dict(method=m,it=i,has_support=has,core=kind,compact=use_aux(m)))
    write(ROOT/"preflight"/"switches.json",dict(frozen_ast_equal=True,cases=variants))

def inspect(folder):
    z=read(folder/"summary.json");method=z["method"];ph=z["phases"]
    assert z["seed"]==103 and [q["phase"] for q in ph]==["G3","joint"]*2
    for q in ph:assert q["actual_end"]<=q["scheduled_end"] and q["after"]["bounds"][1]<=q["before"]["bounds"][1]
    for a,b in zip(ph,ph[1:]):
        for k in ("sha","rng","steps","index","bounds"):assert a["after"][k]==b["before"][k]
    for q in ph[1::2]:
        assert q["after"]["steps"]==q["before"]["steps"] and q["after"]["rng"]==q["before"]["rng"]
        assert q["after"]["index"]>q["before"]["index"]
    with gzip.open(folder/"events.jsonl.gz","rb") as f:events=[json.loads(l) for l in f]
    from evidence_d import check_jobs
    result=check_jobs(folder,events,method)
    assert result["initialized"]>=1 and result["initialization_timeouts"]==0
    assert result["local_count"]==z["iterations"]
    assert any(v["event"]=="module_begin" and v["module"]=="hint" for v in events)
    return dict(seed=z["seed"],method=method,phases=ph,**result)
if __name__=="__main__":regress()
