"""Disaggregated exact inlet-temperature master, with external continuous certification."""
from dataclasses import dataclass
import numpy as np
from scipy.optimize import Bounds, LinearConstraint
from scipy.sparse import coo_matrix

PAD = 1e-8


@dataclass
class Kernel:
    b: np.ndarray
    F: np.ndarray
    e: float
    w: np.ndarray
    peak: np.ndarray
    h: np.ndarray
    time: np.ndarray


def affine_box(k, low, high):
    pos, neg = np.maximum(k.F, 0), np.minimum(k.F, 0)
    return k.b + pos @ low + neg @ high, k.b + pos @ high + neg @ low


class Master:
    def __init__(self, grids, kernels, incumbent, witnesses, cuts):
        self.obj, self.integer, self.lo, self.hi = [], [], [], []
        self.row, self.col, self.val, self.lhs, self.rhs = [], [], [], [], []
        self.x, self.v, self.pruned = {}, {}, 0
        self.z = {d: self.var(binary=True) for d in grids}
        self.y = [[self.var(binary=True) for f in range(27)] for j in range(4)]
        self.add([(z, 1) for z in self.z.values()], 1, 1)
        by_clock = {(j, f): [] for j in range(4) for f in range(27)}
        self.energy_bounds = {}
        for d, grid in grids.items():
            z = self.z[d]
            if any(not modes for modes in grid):
                self.hi[z] = 0
                continue
            low = high = np.zeros(4)
            boxes, costs = [], []
            for modes in grid:
                boxes.append((low, high))
                cost = {f: kernels[i].e + np.maximum(kernels[i].w, 0) @ low
                        + np.minimum(kernels[i].w, 0) @ high - PAD for f, i in modes.items()}
                costs.append(cost)
                bounds = [affine_box(kernels[i], low, high) for i in modes.values()]
                low = np.min([b[0] for b in bounds], axis=0) - PAD
                high = np.max([b[1] for b in bounds], axis=0) + PAD
            mins = [min(c.values()) for c in costs]
            self.energy_bounds[d] = sum(mins)
            for j, modes in enumerate(grid):
                low, high = boxes[j]
                choices = []
                for f, i in modes.items():
                    k = kernels[i]
                    # An interval lower bound conditional on this option. Keep fixed-zero
                    # options in the integer domain bookkeeping, including clock marginals.
                    fixed = sum(mins) - mins[j] + costs[j][f] > incumbent + 1e-7
                    x = self.var(obj=k.e, high=0 if fixed else 1)
                    self.x[d, j, f] = x
                    choices.append((x, 1))
                    by_clock[j, f].append((x, 1))
                    if fixed:
                        self.pruned += 1
                        continue
                    v = []
                    if j:
                        for n in range(4):
                            a = self.var(obj=k.w[n], low=min(0, low[n]), high=max(0, high[n]))
                            v.append(a)
                            self.add([(a, 1), (x, -low[n])], 0, np.inf)
                            self.add([(a, 1), (x, -high[n])], -np.inf, 0)
                        self.v[d, j, f] = v
                    if witnesses:
                        for n in range(4):
                            self.add([(x, k.peak[n] - 80 - PAD)] + list(zip(v, k.h[n])),
                                     -np.inf, 0)
                self.add(choices + [(z, -1)], 0, 0)
                if j:
                    for n in range(4):
                        terms = [(self.v[d, j, f][n], 1) for f in modes if (d,j,f) in self.v]
                        for f, i in grid[j-1].items():
                            k = kernels[i]
                            terms.append((self.x[d,j-1,f], -k.b[n]))
                            terms.extend(zip(self.v.get((d,j-1,f), []), -k.F[n]))
                        self.add(terms, 0, 0)
        for (j,f), terms in by_clock.items():
            self.add(terms + [(self.y[j][f], -1)], 0, 0)
        for d, prefix in cuts:
            self.add([(self.x[d,j,f], 1) for j,f in enumerate(prefix)], -np.inf, len(prefix)-1)
        shape = (len(self.lhs), len(self.obj))
        matrix = coo_matrix((self.val, (self.row,self.col)), shape=shape).tocsc()
        self.constraint = LinearConstraint(matrix, self.lhs, self.rhs)
        self.bounds = Bounds(self.lo, self.hi)
        self.size = dict(rows=shape[0], columns=shape[1], binaries=sum(self.integer),
                         continuous=shape[1]-sum(self.integer), nonzeros=matrix.nnz,
                         certified_cost_fixings=self.pruned)

    def var(self, obj=0., low=0., high=1., binary=False):
        idx = len(self.obj)
        self.obj.append(obj)
        self.integer.append(int(binary))
        self.lo.append(low)
        self.hi.append(high)
        return idx

    def add(self, terms, low, high):
        r = len(self.lhs)
        for c, value in terms:
            if value:
                self.row.append(r)
                self.col.append(c)
                self.val.append(value)
        self.lhs.append(low)
        self.rhs.append(high)

    def decode(self, solution):
        def one(pairs):
            selected = [k for k,i in pairs if solution[i] > 0.5]
            if len(selected) != 1:
                raise ValueError("missing or ambiguous integer choice")
            return selected[0]
        return one(self.z.items()), [one(enumerate(row)) for row in self.y]
