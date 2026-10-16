"""Validated affine coefficients for fixed control states and durations.

All input arithmetic and Taylor polynomials are rational. An infinity-norm
tail bound encloses the exponential; directed interval squaring restores the
full duration. No fitted coefficients or unbounded floating expm are used.
Caches live inside one model and never contain candidate/evaluation results.
"""
from fractions import Fraction as F

from thermal import I, _q


def _fraction_product(a, b):
    n = len(a)
    out = [[F(0) for _ in range(n)] for _ in range(n)]
    for i in range(n):
        for k in range(n):
            if a[i][k]:
                for j in range(n):
                    if b[k][j]:
                        out[i][j] += a[i][k]*b[k][j]
    return out


def _interval_product(a, b):
    n = len(a)
    out = [[I(0) for _ in range(n)] for _ in range(n)]
    for i in range(n):
        for k in range(n):
            if a[i][k].lo or a[i][k].hi:
                for j in range(n):
                    if b[k][j].lo or b[k][j].hi:
                        out[i][j] += a[i][k]*b[k][j]
    return out


def _taylor_kernel(matrix, budget=None, order=18):
    """Exact M**k/k! depends on the control state, not the segment length."""
    n = len(matrix)
    norm = max(sum(abs(v) for v in row) for row in matrix)
    term = [[F(int(i == j)) for j in range(n)] for i in range(n)]
    terms = [term]
    for k in range(1, order+1):
        if budget:
            budget.check()
        term = [[v/k for v in row] for row in _fraction_product(term, matrix)]
        terms.append(term)
    entries = {}
    for i in range(n):
        for j in range(n):
            poly = [a[i][j] for a in terms]
            while poly and poly[-1] == 0:
                poly.pop()
            if poly:
                entries[i, j] = tuple(poly)
    return {'size': n, 'norm': norm, 'order': order, 'entries': entries}


def _kernel_exponential(kernel, duration, budget=None):
    duration = _q(duration)
    if duration < 0:
        raise ValueError('negative duration')
    n, norm, order = kernel['size'], kernel['norm'], kernel['order']
    squarings = 0
    while norm*duration/(2**squarings) > F(1, 4):
        squarings += 1
    h = duration/(2**squarings)
    result = [[F(0) for _ in range(n)] for _ in range(n)]
    for (i, j), poly in kernel['entries'].items():
        if budget:
            budget.check()
        # Rational Horner evaluation equals sum(M**k*h**k/k!) exactly.
        value = poly[-1]
        for coefficient in reversed(poly[:-1]):
            value = value*h+coefficient
        result[i][j] = value
    x = norm*h
    scalar_term = F(1)
    for k in range(1, order+2):
        scalar_term *= x/k
    tail = scalar_term/(1-x/(order+2))
    radius = I.rational(tail).hi
    result = [[I.rational(v)+I(radius.copy_negate(), radius) for v in row] for row in result]
    for _ in range(squarings):
        if budget:
            budget.check()
        result = _interval_product(result, result)
    return result


def exponential(matrix, duration, budget=None, order=18):
    """Same Taylor polynomial, tail and squaring; no floating approximation."""
    if _q(duration) < 0:
        raise ValueError('negative duration')
    return _kernel_exponential(_taylor_kernel(matrix, budget, order), duration, budget)


class Coefficients:
    def __init__(self, platform, budget=None):
        self.platform = platform
        self.nodes = list(platform['node_order'])
        self.domains = list(platform['domains'])
        self.n = len(self.nodes)
        self.budget = budget
        self.cache = {}
        self.kernel_cache = {}
        self.calls = 0

    def power(self, state):
        base, slopes = [F(0)]*self.n, [F(0)]*self.n
        units = {u['id']: u for u in self.platform['units']}
        for domain_id, opp in zip(self.domains, state):
            domain = self.platform['domains'][domain_id]
            for i, share in enumerate(domain['baseline_heat_distribution']):
                base[i] += _q(domain['baseline_W'][opp])*_q(share)
            for unit in domain['unit_ids']:
                i = self.nodes.index(units[unit]['thermal_node_id'])
                slopes[i] += _q(domain['local_temperature_slope_W_per_K'][opp])
        return base, slopes

    def get(self, state, duration):
        duration = _q(duration)
        key = (tuple(state), duration)
        if key in self.cache:
            return self.cache[key]
        if self.budget:
            self.budget.check()
        n = self.n
        # [theta/100, per-node active power, constant 1, segment energy].
        size = 2*n+2
        m = [[F(0) for _ in range(size)] for _ in range(size)]
        p = self.platform
        c = list(map(_q, p['heat_capacity_J_per_K']))
        g = [list(map(_q, row)) for row in p['conductance_W_per_K']]
        ambient, reference = _q(p['ambient_temperature_degC']), _q(p['reference_temperature_degC'])
        base, slopes = self.power(state)
        for i in range(n):
            for j in range(n):
                m[i][j] = ((slopes[i] if i == j else 0)-g[i][j])/c[i]
            m[i][n+i] = 1/(100*c[i])
            m[i][2*n] = (base[i]+slopes[i]*(ambient-reference))/(100*c[i])
            m[-1][i] = 100*slopes[i]
            m[-1][n+i] = 1
        m[-1][2*n] = sum(base)+sum(slopes)*(ambient-reference)+_q(p['external_common_power_W'])
        state_key = tuple(state)
        if state_key not in self.kernel_cache:
            # Publish only a complete kernel. An interrupted construction must
            # not leave a partial polynomial available to another duration.
            self.kernel_cache[state_key] = _taylor_kernel(m, self.budget)
        e = _kernel_exponential(self.kernel_cache[state_key], duration, self.budget)
        # Exact zero/identity blocks need no generic tail enlargement.
        for i in range(n, 2*n+1):
            e[i] = [I(int(i == j)) for j in range(size)]
        for i in range(n):
            e[i][-1] = I(0)
        e[-1][-1] = I(1)
        temperature = [row[:n]+[v*100 for v in row[n:2*n+1]] for row in e[:n]]
        energy = [v/100 for v in e[-1][:n]]+e[-1][n:2*n+1]
        result = {'temperature': temperature, 'energy': energy,
                  'state': list(state), 'duration_s': str(duration)}
        self.cache[key] = result
        self.calls += 1
        return result
