"""Exact regressions and fixed-attempt comparison with the original frozen G3."""
import pickle
import random
import sys
from settings import ROOT, INITIAL, write, sha
import c1r_assets
import checks
from g3_flow import Flow,search
from base import Problem, archived, key, evaluate, raw

def g3_comparison(n=48):
    p=Problem("D3");ident,plan=archived("D3");assert key(p,plan)==ident==INITIAL
    def tracker():
        tr=search.Tracker(p,float("inf"));tr.consider(plan,True)
        return tr
    a=tracker();b=tracker();ra=random.Random(101);rb=Flow(p,b,101)
    seq=[];seq_b=[];accept=[];accept_b=[]
    a.on_change=lambda:accept.append((key(p,a.plan),a.best["E_bounds"]))
    b.on_change=lambda:accept_b.append((key(p,b.plan),b.best["E_bounds"]))
    old=search.check
    class Limit(Exception):pass
    def fixed_attempt(end):
        if sys._getframe(1).f_code is search.lns.__code__ and len(seq)>=n:raise Limit
        old(end)
    search.check=fixed_attempt
    try:
        try:search.lns(p,plan,a,ra,"G3",dict(moves=seq))
        except Limit:pass
    finally:search.check=old
    for part in (14,19,n-33):
        for _ in range(part):rb.step(seq_b.append)
    assert seq==seq_b and ra.getstate()==rb.rng.getstate() and accept==accept_b
    assert key(p,a.plan)==key(p,b.plan) and (a.count,a.certified,a.invalid)==(b.count,b.certified,b.invalid)
    write(ROOT/"preflight"/"g3_equivalence.json",dict(attempts=n,partition=[14,19,n-33],moves=seq,accepted=accept,
         rng_sha=sha(pickle.dumps(ra.getstate(),protocol=4)),terminal=key(p,a.plan),certified=a.certified,initial=ident))
def run():
    import assets_e2,verify_core
    dest=ROOT/"preflight"
    assets_e2.HERE=verify_core.HERE=dest/"regression"
    verify_core.finite();verify_core.replay()
    for name in ("finite_gate.json","replay_gate.json"):
        from settings import read
        assert read(dest/"regression"/"validation"/name)["passed"]
    checks.ROOT=dest;checks.finite()
    assert len(read(dest/"validation"/"finite.json"))==46
    g3_comparison()
    write(dest/"correctness.json",dict(passed=True,compact_checks=46,g3_moves=48))
if __name__=="__main__":run()
