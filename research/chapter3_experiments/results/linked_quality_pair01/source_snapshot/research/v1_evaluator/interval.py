"""Directed Decimal intervals and bounded Taylor propagation (standard library).

Coordinates: temperature rise / 1 K, leakage energy / 1 J, constant 1.
No float is accepted as an exact input. No transcendental library call is used.
"""
from decimal import Decimal, Context, ROUND_FLOOR, ROUND_CEILING
from fractions import Fraction
import math
import time

D = Decimal
DOWN = Context(prec=60, rounding=ROUND_FLOOR)
UP = Context(prec=60, rounding=ROUND_CEILING)


class I:
    __slots__ = ('lo', 'hi')

    def __init__(self, lo=0, hi=None):
        if isinstance(lo, float) or isinstance(hi, float):
            raise TypeError('float is not an exact input')
        self.lo = D(lo)
        self.hi = self.lo if hi is None else D(hi)
        if not self.lo.is_finite() or not self.hi.is_finite() or self.lo > self.hi:
            raise ValueError('invalid interval')

    @staticmethod
    def rational(q):
        q = Fraction(q)
        return I(DOWN.divide(D(q.numerator), D(q.denominator)),
                 UP.divide(D(q.numerator), D(q.denominator)))

    def __add__(self, b):
        b = box(b)
        return I(DOWN.add(self.lo, b.lo), UP.add(self.hi, b.hi))

    __radd__ = __add__

    def __neg__(self):
        return I(self.hi.copy_negate(), self.lo.copy_negate())

    def __sub__(self, b):
        return self + (-box(b))

    def __rsub__(self, b):
        return box(b) - self

    def __mul__(self, b):
        b = box(b)
        pairs = [(a, c) for a in (self.lo, self.hi) for c in (b.lo, b.hi)]
        return I(min(DOWN.multiply(a, c) for a, c in pairs),
                 max(UP.multiply(a, c) for a, c in pairs))

    __rmul__ = __mul__

    def __truediv__(self, b):
        b = box(b)
        if b.lo <= 0 <= b.hi:
            raise ValueError('division across zero')
        return self * I(DOWN.divide(D(1), b.hi), UP.divide(D(1), b.lo))

    @property
    def width(self):
        return UP.subtract(self.hi, self.lo)

    @property
    def magnitude(self):
        return max(self.lo.copy_abs(), self.hi.copy_abs())

    def data(self):
        return [str(self.lo), str(self.hi)]


def box(x):
    return x if isinstance(x, I) else I(x)


def dot(a, b):
    return sum((x * y for x, y in zip(a, b)), I(0))


def mv(a, x):
    return [dot(row, x) for row in a]


def norm(a):
    return max(sum((I(v.magnitude) for v in row), I(0)).hi for row in a)


class Exhausted(Exception):
    pass


class Budget:
    def __init__(self, seconds=60, panels=100000, refinements=20000):
        self.start = time.monotonic()
        self.seconds = seconds
        self.panel_limit = panels
        self.refinement_limit = refinements
        self.panels = 0
        self.refinements = 0

    def check(self):
        if time.monotonic() - self.start > self.seconds:
            raise Exhausted('wall_time_limit')

    def panel(self):
        self.panels += 1
        if self.panels > self.panel_limit:
            raise Exhausted('panel_limit')
        self.check()

    def refine(self):
        self.refinements += 1
        if self.refinements > self.refinement_limit:
            raise Exhausted('peak_refinement_limit')
        self.check()


class TaylorPanel:
    def __init__(self, matrix, state, h, order=18):
        self.matrix, self.h = matrix, Fraction(h)
        self.coeffs = [state]
        for k in range(1, order + 1):
            self.coeffs.append([v / k for v in mv(matrix, self.coeffs[-1])])
        x = I(norm(matrix)) * I.rational(h)
        if x.hi > D('.5'):
            raise ValueError('panel norm*h must be <= 1/2')
        # Sum_{k=N+1}∞ x^k/k! <= (x^(N+1)/(N+1)!)/(1-x/(N+2)).
        term = I(1)
        for k in range(1, order + 2):
            term = term * x / k
        self.radius = (I(max(v.magnitude for v in state)) * term / (1-x/(order+2))).hi

    def value(self, left, right=None):
        right = left if right is None else right
        t = I(I.rational(left).lo, I.rational(right).hi)
        out = self.coeffs[-1]
        for row in reversed(self.coeffs[:-1]):
            out = [v*t+c for v, c in zip(out, row)]
        r = I(self.radius.copy_negate(), self.radius)
        return [v+r for v in out]

    def peak(self, node, tolerance, budget):
        # Endpoint witnesses give lower bounds. Interval polynomial images cover
        # every time; derivative signs tighten monotone cells to endpoints.
        def cell(l, r):
            a, b = self.value(l), self.value(r)
            image = self.value(l, r)
            derivative = dot(self.matrix[node], image)
            upper = b[node].hi if derivative.lo >= 0 else a[node].hi if derivative.hi <= 0 else image[node].hi
            if a[node].lo >= b[node].lo:
                return (l, r, upper), a[node].lo, l
            return (l, r, upper), b[node].lo, r
        first, lower, at = cell(Fraction(0), self.h)
        cells = [first]
        while True:
            budget.check()
            k = max(range(len(cells)), key=lambda j: cells[j][2])
            upper = max(lower, cells[k][2])
            if UP.subtract(upper, lower) <= tolerance:
                return I(lower, upper), at
            budget.refine()
            l, r, _ = cells[k]
            middle = (l+r)/2
            # Parent remains until both children have been evaluated.
            left, lv, lt = cell(l, middle)
            right, rv, rt = cell(middle, r)
            for v, t in [(lv, lt), (rv, rt)]:
                if v > lower:
                    lower, at = v, t
            cells[k:k+1] = [left, right]
            cells = [c for c in cells if c[2] >= lower] or [(l, r, lower)]


def panel_count(matrix, duration):
    n = Fraction(norm(matrix)) * Fraction(duration) * 2
    return max(1, math.ceil(n))
