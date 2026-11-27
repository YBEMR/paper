"""One ablation of the open-window selector in the immutable M1-i runner."""
from bisect import bisect_left
from paths_j import METHODS
from adapter import builder as frozen_builder, e, h
from runner import timed_run as frozen_timed_run

def scalar_four(ordered,closed):
    """Take the first four by the exact existing compromise-seat ordering."""
    assert not closed
    metrics=("energy","drain","risk")
    values={k:sorted(round(float(s[k]),11) for s in ordered) for k in metrics}
    def compromise(s):
        ranks=sum(bisect_left(values[k],round(float(s[k]),11)) for k in metrics)
        energy=round(float(s["energy"]),11)
        return ranks,energy,energy,s["config"]
    return sorted(ordered,key=compromise)[:4]

def builder(method):
    assert method in METHODS
    base=method.split("-")[0]
    build,receipt=frozen_builder(base)
    if method==base:
        return build,receipt
    scalar_build=h.with_binding(build,diverse=scalar_four)
    def run(c,arm,width,start,deadline,stage):
        return scalar_build(c,base,width,start,deadline,stage)
    return run,receipt

timed_run=h.with_binding(frozen_timed_run,builder=builder)
