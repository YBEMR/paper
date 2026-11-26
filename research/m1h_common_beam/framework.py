"""Reuse the frozen constructor, beam and anytime loop; substitute only the open-window risk."""
import os
import sys
from pathlib import Path
from types import FunctionType

ROOT = Path(__file__).resolve().parent
G = ROOT.parent / "m1g_literature_comparison"
sys.path.insert(0, str(G))
from experiment import case_for, e, inputs
from literature import Profile, reference
import numpy as np

METHODS = ("NT", "NC", "ZQ-Beam", "LQ-Beam", "C2")
CORE = METHODS[:4]


def lookup(profile, method):
    modes = profile.order["main"] if method == "ZQ-Beam" else profile.li_modes("main")
    return {k + 10*(u == 3):rank for rank,(u,k) in enumerate(modes)}


def ordinal(keys):
    """Encode a lexicographic weak ordering without breaking equality."""
    return {key:rank for rank,key in enumerate(sorted(set(keys)))}


class RecordedEnds:
    """Read only the completion ticks already produced by the same frozen FIFO call."""
    def __init__(self, case, left, limits):
        self.case = case
        self.left = left
        self.limits = limits
        self.late = {}

    def __getattr__(self, attr):
        return getattr(self.case, attr)

    def ledger(self, cfg, *args):
        ledger = self.case.ledger(cfg, *args)
        if ledger[0]:
            self.late[cfg] = int(np.count_nonzero(ledger[5][self.left:] > self.limits[self.left:len(cfg)]))
        return ledger


class LiteratureRisk:
    def __init__(self):
        self.ranks = None
        self.limits = None

    def expand(self, case, j, parents, method, start, deadline, stage):
        if j+1 == case.windows:
            return e.expand(case,j,parents,"NC",start,deadline,stage)
        if self.ranks is None:
            profile = Profile(case.p)
            self.ranks = lookup(profile,method)
            if method == "LQ-Beam":
                self.limits = np.asarray(reference(case.p,profile))[1::3]
        left,right = case.release.searchsorted((j*e.WINDOW,(j+1)*e.WINDOW))
        source = case if self.limits is None else RecordedEnds(case,int(left),self.limits)
        first = len(stage["actions"])
        pool,complete = e.expand(source,j,parents,"NC",start,deadline,stage)
        if not complete:
            return pool,False
        keys = {}
        for idx,state in pool.items():
            g,n,x,y = state["action"]
            npu = x+y
            mode_sum = self.ranks[g]*(int(right-left)-npu) + self.ranks[10+n]*npu
            primary = int(state["peak"]>80.) if self.limits is None else source.late[state["config"]]
            keys[idx] = (primary,mode_sum)
        ranks = ordinal(keys.values())
        for idx,state in pool.items():
            state["risk"] = ranks[keys[idx]]
        for pos in range(first,len(stage["actions"])):
            row = stage["actions"][pos]
            if row[9] == "valid":
                stage["actions"][pos] = (*row[:12],keys[row[6]],*row[13:])
        return pool,True


def with_binding(fn, **bindings):
    return FunctionType(fn.__code__,dict(fn.__globals__,**bindings),fn.__name__,fn.__defaults__,fn.__closure__)


def run(case,method):
    if method in ("NT","NC","C2"):
        return e.run(case,method,60.)
    scorer = LiteratureRisk()
    build = with_binding(e.build,expand=scorer.expand)
    return with_binding(e.run,build=build)(case,method,60.)
