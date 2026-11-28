"""Measure the exact formal counter and log path against the uninstrumented expansion."""
import json,mmap,sys
from pathlib import Path
from transfer import init,make,m,T,ROOT,emit
import numpy as np


def main(dest):
    native=init()
    obj=next(o for o in m.u2.CASES if m.label(o)=="C10")
    c=m.u2.make_flow(m.RUN[0],obj,dest)
    rows=[json.loads(l) for l in (ROOT/"diag1/parents.jsonl").read_text().splitlines()]
    with (dest/"mem").open("w+b") as f:
        f.truncate(32);live=memoryview(mmap.mmap(f.fileno(),32)).cast("q")
    for parent in (r for r in rows if r["case"]=="C10"):
        j=parent["j"]
        parent.update(config=bytes.fromhex(parent["config"]),temperature=np.array(parent["temperature"]))
        def snap(x):emit(dest/"layers.jsonl",x)
        for arm in ("A","B"):
            bare=make(native,arm,"bare")
            light=make(native,arm,"light",snap,live)
            def run(fn):
                log=dict(actions=[],groups=[]);start=T()
                ps,ok=fn(c,j,[parent],"NT",start,start+60,log)
                return T()-start,ps,ok
            run(bare)
            for i in range(3):
                data={}
                ids=None
                for label,fn in ((("bare",bare),("formal",light)) if i%2==0 else (("formal",light),("bare",bare))):
                    dt,pool,ok=run(fn)
                    assert ok
                    if ids is not None:assert ids==list(pool)
                    ids=list(pool);data[label]=dt
                emit(dest/"probe.jsonl",dict(j=j,arm=arm,rep=i,**data))


if __name__=="__main__":main(Path(sys.argv[1]))
