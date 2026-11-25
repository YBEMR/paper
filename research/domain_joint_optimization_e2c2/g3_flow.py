"""One G3 move from frozen search.lns. The Tracker and RNG live across phases."""
import random
from settings import clock
import c1r_assets
import bounded
import search
from base import evaluate

class Flow:
    def __init__(self,p,tr,seed):
        self.p,self.tr=p,tr
        self.rng=random.Random(seed)
        self.steps=0
        # lns evaluates its initial current_val once on entry.
        evaluate(p,tr.plan,cert=True)

    def step(self,log_move):
        tr=self.tr;p=self.p;rng=self.rng
        search.check(tr.end)
        self.steps+=1
        plan=tr.plan
        size=rng.choice([2,3,4,5,7,9])
        i=rng.randrange(p.n)
        st=search.ordinary(p,plan[0],i,size,rng) if rng.random()<.55 else [i]+rng.sample([j for j in range(p.n) if j!=i],size-1)
        if self.steps%3==0:
            st=list(dict.fromkeys([i,3*(i//3),3*(i//3)+1,3*(i//3)+2,*st]))[:size]
        log_move([i,st])
        alt=search.rebuild(p,plan,st,rng)
        if alt is not None:
            tr.consider(alt)
