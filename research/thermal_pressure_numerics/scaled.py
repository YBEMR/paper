"""K.29: diagonal coordinate scaling of the unchanged bounded Taylor evaluator.

Physical temperatures, segments, energy units and accuracy remain unchanged.
No global in an old module is mutated; a function-local dependency table selects
the scaled panel and a conservative step-count function.
"""
from fractions import Fraction as F
from decimal import Decimal as D
from pathlib import Path
from types import FunctionType
import math
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'thermal_pressure_precheck'))
import adapter as a
from interval import TaylorPanel, I, mv


def scales(n):
    # Augmented coordinates: n temperatures (K), leakage energy (J), constant.
    return [100]*(n-2)+[1, 1]


def transform(matrix):
    d = scales(len(matrix))
    return [[v*I(d[j])/I(d[i]) for j, v in enumerate(row)] for i, row in enumerate(matrix)]


def panel_count(matrix, duration):
    scaled = transform(matrix)
    norm_upper = max(sum(F(v.magnitude) for v in row) for row in scaled)
    return max(1, math.ceil(4*norm_upper*F(duration)))


class TransitionPanel(TaylorPanel):
    """Point values use exp(Mt) times the interval state, limiting wrapping.

    Each column is enclosed by the original TaylorPanel on an exact basis vector.
    The cache is local to a single thermal evaluation and contains no states.
    Interval-time images still use the original bounded Taylor polynomial.
    """
    def __init__(self,matrix,state,h,cache):
        super().__init__(matrix,state,h)
        self.state,self.cache=state,cache
        self.key=tuple(tuple((v.lo,v.hi) for v in row) for row in matrix)

    def value(self,left,right=None):
        if right is not None and right!=left:
            return super().value(left,right)
        t=F(left)
        if t==0: return self.state
        key=(self.key,self.h,t)
        if key not in self.cache:
            n=len(self.state)
            columns=[TaylorPanel(self.matrix,[I(int(i==j)) for i in range(n)],self.h).value(t) for j in range(n)]
            self.cache[key]=[[columns[j][i] for j in range(n)] for i in range(n)]
        return mv(self.cache[key],self.state)


class ScaledPanel:
    def __init__(self, matrix, state, h, cache=None):
        self.d = scales(len(matrix))
        self.panel = TransitionPanel(transform(matrix), [v/I(d) for v,d in zip(state,self.d)], h,
                                     {} if cache is None else cache)

    def value(self, left, right=None):
        return [v*I(d) for v,d in zip(self.panel.value(left,right),self.d)]

    def peak(self, node, tolerance, budget):
        # Dividing a finite Decimal by 100 is an exact exponent change,
        # independent of the ambient Decimal context precision.
        tup = D(tolerance).as_tuple()
        tol = D((tup.sign,tup.digits,tup.exponent-2)) if self.d[node]==100 else D(tolerance)
        peak, at = self.panel.peak(node,tol,budget)
        return peak*I(self.d[node]), at


def thermal(p, initial, segments, accuracy, budget):
    cache={}
    globals_local=dict(a.v1.thermal.__globals__,
                       TaylorPanel=lambda matrix,state,h: ScaledPanel(matrix,state,h,cache),
                       panel_count=panel_count)
    evaluator=FunctionType(a.v1.thermal.__code__,globals_local,'scaled_thermal',a.v1.thermal.__defaults__)
    return evaluator(p,initial,segments,accuracy,budget)


def identities():
    out=a.identities()
    for p in [HERE/'scaled.py',HERE/'precheck.py']:
        out[str(p.relative_to(a.old.REPO))]=a.cp.sha(p)
    return out
