"""Single substitution in the immutable NT expansion; preserve all three pilot replays."""
import inspect
import os
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
PREVIOUS = ROOT.parent / "ch3_mapping_first_nested"
sys.path.insert(0, str(PREVIOUS))
import paired
from solver import f, m

FIT = "cost = np.linalg.solve(np.column_stack((np.ones(3), pilots)), energies)"
DIRECT = "cost = analytic_plane(c.eng, a, b, g, n)"

def analytic_plane(engine,a,b,g,n):
    inc=engine.inc
    ag,bg,an,bn=(int(inc[t,u,k]) for t,u,k in (("A",2,g),("B",2,g),("A",3,n),("B",3,n)))
    # Use exact Python integers in the engine's scaled units. The sampler only sorts.
    return np.array([int(a)*ag+int(b)*bg,an-ag,bn-bg],dtype=object)

def analytic_expand(original):
    source=inspect.getsource(original)
    assert source.count(FIT)==1 and "def expand(" in source
    namespace=dict(original.__globals__,analytic_plane=analytic_plane)
    exec(compile(source.replace(FIT,DIRECT),"<analytic quota cost>","exec"),namespace)
    return namespace["expand"]

def capture(expand,dest):
    seen=set()
    def observe(c,j,parents,method,start,deadline,log):
        if j in (0,c.windows//2,c.windows-1) and j not in seen:
            p=parents[0]
            f.save(dest/f"parent-{j}.json",dict(j=j,config=p["config"].hex(),id=p["id"],f=p["f"],k=p["k"],
                   temperature=list(p["temperature"]),peak=p["peak"]))
            seen.add(j)
        return expand(c,j,parents,method,start,deadline,log)
    return observe

def main(code,arm,budget,folder):
    assert arm in ("fit","analytic") and budget in (60,600)
    dest=Path(folder)
    f.ORIGIN=m.CLOCK=float(os.environ["CELL_START"])
    f.log(dest/"start.jsonl","begin",core=list(os.sched_getaffinity(0)))
    m.RUN=m.u2.stack()
    implementation=m.RUN[0].e
    original=implementation.expand
    assert Path(inspect.getsourcefile(original)).parent.name=="m1e_thermal_quota_ablation"
    expand=analytic_expand(original) if arm=="analytic" else original
    implementation.expand=capture(expand,dest)
    obj=next(o for o in m.u2.CASES if m.label(o)==code)
    paired.baseline(obj,dest,budget)

if __name__=="__main__":
    main(sys.argv[1],sys.argv[2],int(sys.argv[3]),sys.argv[4])
