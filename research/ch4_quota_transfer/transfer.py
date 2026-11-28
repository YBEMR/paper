"""A single cold solve; both methods use the frozen direct thermal mapping optimizer."""
import ast,inspect,json,os,sys,time
from pathlib import Path

ROOT=Path(os.environ["TRANSFER_ROOT"])
S=Path(os.environ["FAST_SCRATCH"])
for k in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMBA_NUM_THREADS"):os.environ[k]="1"
os.environ.update(U1_NT=str(S/"nt"),U1_THREE=str(S/"none"),U1_FOUR=str(S/"four"),GEN=str(S/"nt"))
sys.path[:0]=[str(S/"site"),str(ROOT/"driver/ch3_direct_thermal_final")]
import cold_cell as cold
from cold_cell import f,m,paired
T=time.perf_counter


def init():
    m.RUN=m.u2.stack()
    import simplified
    return simplified.expand


def emit(p,obj):
    with p.open("ab",buffering=0) as h:h.write(json.dumps(obj,separators=(",",":"),default=lambda x:x.item()).encode()+b"\n")


def make(native,arm,mode="light",record=None):
    src=inspect.getsource(native)
    def change(a,b):
        nonlocal src
        assert src.count(a)==1,a
        src=src.replace(a,b)
    if arm=="B":
        a=src.index("            center =")
        b=src.index("            assert len(set",a)
        src=src[:a]+"            center = None\n            chosen = list(original)\n"+src[b:]
    if mode=="bare":
        ns=dict(native.__globals__)
        exec(src,ns)
        return ns["expand"]
    fine=mode=="fine"
    change("    pool = {}", "    pool = {}\n    slots=checks=prop=groups=0")
    if fine:
        change("    types, a, b =", "    gen0=clock()\n    types, a, b =")
        change("            load = load_planes","            load = load_planes")
        boundary="            center ="
        change(boundary,"            gen1=clock()\n"+boundary)
        if arm=="A":
            change("            chosen = synthesize","            slice0=clock()\n            chosen = synthesize")
        else:
            change("            chosen = list", "            slice0=clock()\n            chosen = list")
        change("            assert len(set", "            eval0=clock()\n            replay=thermal=extend=0.\n            assert len(set")
        change("                ledger = c.ledger", "                tt=clock()\n                ledger = c.ledger")
        change("                if not ledger[0]:","                replay+=clock()-tt\n                if not ledger[0]:")
        change("                for mean, dt", "                tt=clock()\n                for mean, dt")
        change("                risk = peak if final", "                thermal+=clock()-tt\n                tt=clock()\n                risk = peak if final")
        change("                drain =","                extend+=clock()-tt\n                drain =")
    change("            for x, y in chosen:","            slots+=len(chosen)\n            for x, y in chosen:")
    change("                ledger = c.ledger","                checks+=1\n                ledger = c.ledger")
    change("                widths = np.minimum","                prop+=len(means)+int(not final)\n                widths = np.minimum")
    tag="            log[\"groups\"].append"
    prefix="            groups+=1\n"
    if fine:
        prefix+="            now=clock()\n            record(dict(j=j,g=g,n=n,common_gen=gen1-gen0,center= slice0-gen1,slice=eval0-slice0,replay=replay,heat=thermal,extension=extend,other_eval=now-eval0-replay-thermal-extend,total=now-gen0,chosen=chosen))\n"
    else:
        prefix+="            if groups%16==0:record(dict(j=j,groups=groups,slots=slots,checks=checks,valid=len(pool),prop=prop,complete=False))\n"
    change(tag,prefix+tag)
    if fine:change("    return pool, True","            gen0=clock()\n    return pool, True")
    else:change("    return pool, True","    record(dict(j=j,groups=groups,slots=slots,checks=checks,valid=len(pool),prop=prop,complete=True))\n    return pool, True")
    ns=dict(native.__globals__,record=record)
    exec(compile(src,"<frozen expansion with quota selector and measurements>","exec"),ns)
    return ns["expand"]


def short_clock(fn,cap):
    tree=ast.parse(inspect.getsource(fn))
    for node in ast.walk(tree):
        if isinstance(node,ast.Constant) and type(node.value) is int and node.value in (55,60):
            node.value={55:cap-3,60:cap}[node.value]
    ns={}
    exec(compile(tree,inspect.getsourcefile(fn),"exec"),fn.__globals__,ns)
    return ns[fn.__name__]


def main(case,arm,cap,dest):
    f.ORIGIN=m.CLOCK=float(os.environ["CELL_START"])
    f.log(dest/"start.jsonl","begin",core=list(os.sched_getaffinity(0)))
    native=init()
    obj=next(o for o in m.u2.CASES if m.label(o)==case)
    first=True
    def note(row):
        nonlocal first
        emit(dest/"layers.jsonl",dict(new=first,**row));first=False
    expand=make(native,arm,"light",note)
    def layer(*args):
        nonlocal first
        first=True
        return expand(*args)
    m.RUN[0].e.expand=layer
    f.refine=cold.refine_safe
    paired.online.refine_hot=cold.direct
    if cap!=60:
        for module,name in ((f,"search"),(f,"refine"),(paired.hot,"census"),(paired.online,"select"),(paired.online,"refine")):
            setattr(module,name,short_clock(getattr(module,name),cap))
        paired.online.census=paired.hot.census
        src=inspect.getsource(paired.baseline)
        assert src.count("split = limit-5")==1
        ns=dict(paired.__dict__)
        exec(src.replace("split = limit-5","split = limit-3"),ns)
        ns["baseline"](obj,dest,cap)
    else:paired.baseline(obj,dest,cap)


if __name__=="__main__":main(sys.argv[1],sys.argv[2],int(sys.argv[3]),Path(sys.argv[4]))
