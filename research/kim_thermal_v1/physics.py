"""Piecewise analytic four-node electrothermal evaluator for the frozen V1 model.

All maps take absolute Celsius at entry.  Extrema are enclosed continuously by
a second-derivative interpolation bound on each interval, with subdivision at
ambiguous constraints.  Floating-point guard is not directed interval rounding;
physics_checks.py compares independently with the archived Decimal kernel.
"""
from fractions import Fraction
from functools import lru_cache

import numpy as np

ROUND_GUARD = 1e-9  # K, numerical guard for binary64, not a physical margin
REPORT_WIDTH = 5e-4  # K, max width of detailed reported peak brackets


def number(x):
    return float(Fraction(x)) if isinstance(x, str) else float(x)


def expand_segment(platform, s):
    """Accept archived full power segments or compact schedule intervals."""
    if 'node_power_constant_at_reference_W' in s:
        return s
    names = platform['node_order']
    durations = Fraction(str(s['end_ms'])) - Fraction(str(s['start_ms']))
    base = dict.fromkeys(names, Fraction(0))
    slopes = dict(base)
    group = {}
    for domain, level in zip(('CPU', 'GPU', 'NPU'), s['opp'], strict=True):
        cfg = platform['domains'][domain]
        group[domain] = Fraction(cfg['baseline_W'][level])
        for node, weight in zip(names, cfg['baseline_heat_distribution'], strict=True):
            base[node] += Fraction(weight) * group[domain]
        for unit in cfg['unit_ids']:
            slopes[unit] += Fraction(cfg['local_temperature_slope_W_per_K'][level])
    act = {k: Fraction(str(v)) for k, v in zip(names, s['activity_W'], strict=True)}
    return {**s, 'start_ms': str(s['start_ms']), 'end_ms': str(s['end_ms']),
            'duration_ms': str(durations), 'baseline_by_node_W': base,
            'baseline_by_power_group_W': group, 'activity_by_node_W': act,
            'node_power_constant_at_reference_W': {k: base[k]+act[k] for k in names},
            'local_leakage_slope_W_per_K': slopes,
            'external_common_power_W': platform['external_common_power_W'],
            'external_common_injected_heat_W': '0',
            'reference_temperature_degC': platform['reference_temperature_degC']}


@lru_cache(maxsize=64)
def modes(c_tuple, g_tuple, slope_tuple):
    # C^-1 (diag(slope)-G) is similar to the symmetric matrix below.
    c = np.asarray(c_tuple)
    inv_sqrt = 1 / np.sqrt(c)
    lam, q = np.linalg.eigh((np.diag(slope_tuple)-np.asarray(g_tuple)) *
                            (inv_sqrt[:, None] * inv_sqrt[None, :]))
    if max(lam) >= 0:
        raise ValueError("V1 requires a stable passive electrothermal model")
    return lam, q * inv_sqrt[:, None], q.T * np.sqrt(c)[None, :]


class Template:
    """Compact maps for repeated search, plus per-event analytical replay."""

    def step(self, T, limits=80, detail=False):
        T = np.asarray(T, dtype=float)
        limits = np.broadcast_to(np.asarray(limits, dtype=float), T.shape)
        if T.shape != self.b.shape or not np.all(np.isfinite(T)) or np.any(np.isnan(limits)):
            raise ValueError("invalid entry or limit dimensions/values")
        x = np.r_[T, 1.0]
        start = self.start_maps @ x
        end = self.end_maps @ x
        coeff = self.coeff_maps @ x
        # For t>=0, all modal factors exp(lambda*t)<=1.  Interpolation
        # differs from the line between endpoints by at most h^2 max|T''|/8.
        curvature = (self.abs_u_lam2 @ np.abs(coeff)[:, :, None])[:, :, 0]
        err = curvature * (self.h**2/8)[:, None] + ROUND_GUARD
        hi_node = np.maximum(start, end)
        lo_node = np.minimum(start, end)
        upper = hi_node + err
        lower = hi_node - ROUND_GUARD
        min_lower = lo_node - err
        low_range, high_range = self.valid
        ambiguous = np.any((upper > limits) & (lower <= limits), axis=1)
        ambiguous |= np.any((min_lower < low_range) | (upper > high_range), axis=1)
        if detail:
            ambiguous |= np.max(err, axis=1) > REPORT_WIDTH
        for i in np.flatnonzero(ambiguous):
            # For detail return tight continuous peak bounds; when deciding a
            # constraint, refine further until its side is unambiguous.
            vals = self._refine(i, coeff[i], start[i], end[i], limits)
            lower[i], upper[i], min_lower[i] = vals
        if np.min(min_lower) < low_range or np.max(upper) > high_range:
            raise ArithmeticError("thermal history outside (or unresolved at) model validity range")
        peaks_lo = lower.max(axis=0)
        peaks_hi = upper.max(axis=0)
        safe = bool(np.all(peaks_hi <= limits))
        if not safe and not np.any(peaks_lo > limits):
            raise ArithmeticError("continuous thermal constraint unresolved at numerical precision")
        energies = self.energy_maps @ x
        out = dict(safe=safe, energy_J=float(self.w@T + self.e),
                   final_T=(self.F@T + self.b).tolist(),
                   peak_lower=peaks_lo.tolist(), peak_upper=peaks_hi.tolist())
        if detail:
            out['trace'] = [
                dict(start_ms=float(self.times[i]*1000), duration_ms=float(self.h[i]*1000),
                     start_T=start[i].tolist(), final_T=end[i].tolist(),
                     peak_lower=lower[i].tolist(), peak_upper=upper[i].tolist(),
                     energy_J=float(energies[i]), constant_W=self.constant[i].tolist(),
                     slope_W_K=self.slope[i].tolist(), external_W=self.external)
                for i in range(len(self.h))]
        return out

    def _refine(self, i, coeff, start, end, limits):
        # Subinterval local lower/upper brackets. Exponential coefficients at
        # the subinterval's left edge give a valid curvature bound thereafter.
        h, lam, u, equilibrium = self.h[i], self.lam[i], self.u[i], self.eq[i]
        work = [(0.0, h, start, end, coeff, 0)]
        top_lo, top_hi = start.copy()-ROUND_GUARD, start.copy()+ROUND_GUARD
        bottom = start.copy()-ROUND_GUARD
        while work:
            t0, t1, a, b, c, depth = work.pop()
            w = t1-t0
            err = self.abs_u_lam2[i] @ np.abs(c) * (w*w/8) + ROUND_GUARD
            observed = np.maximum(a, b)
            hi, lo = observed + err, observed - ROUND_GUARD
            floor = np.minimum(a, b)-err
            # Exact entry/switch endpoints at a hard limit can be settled if
            # the slope sign is known throughout the adjacent cell.
            second = self.abs_u_lam2[i] @ np.abs(c)
            deriv = u @ (lam*c)
            monotone = (deriv > w*second + ROUND_GUARD) | (deriv < -w*second - ROUND_GUARD)
            hi = np.where(monotone, observed + ROUND_GUARD, hi)
            floor = np.where(monotone, np.minimum(a, b)-ROUND_GUARD, floor)
            ambiguous = np.any((hi > limits) & (lo <= limits))
            outside_range = np.any(floor < self.valid[0]) or np.any(hi > self.valid[1])
            if (np.any(lo > self.valid[1]) or np.any(np.minimum(a, b)+ROUND_GUARD < self.valid[0])):
                raise ArithmeticError("power law validity boundary crossed")
            if depth < 24 and (ambiguous or outside_range or max(hi-lo) > REPORT_WIDTH):
                if depth > 16 and (t1-t0 < 1e-7 or max(err) < 2*ROUND_GUARD):
                    raise ArithmeticError("peak classification unresolved")
                middle = (t0+t1)/2
                cm = c*np.exp(lam*(w/2))
                m = equilibrium + u@cm
                work.extend(((middle,t1,m,b,cm,depth+1),(t0,middle,a,m,c,depth+1)))
                continue
            top_lo = np.maximum(top_lo, lo)
            top_hi = np.maximum(top_hi, hi)
            bottom = np.minimum(bottom, floor)
        return top_lo, top_hi, bottom


def compile_template(platform, segments):
    """Compile a contiguous list of power intervals (local time can restart for appended tail)."""
    p = Template()
    names = platform['node_order']
    n = len(names)
    c = tuple(map(number, platform['heat_capacity_J_per_K']))
    g = tuple(tuple(map(number, row)) for row in platform['conductance_W_per_K'])
    p.valid = tuple(map(number, platform['power_model_temperature_range_degC']))
    ambient, reference = map(number,(platform['ambient_temperature_degC'],platform['reference_temperature_degC']))
    p.external = number(platform['external_common_power_W'])
    starts, ends, costs, eigenvalues, eigenvectors, equilibria, coeffs, hs, qs, slopes = ([] for _ in range(10))
    one = np.eye(n+1)[-1]
    state = np.eye(n+1)[:-1]
    if not segments:
        raise ValueError("empty physical window")
    for s in segments:
        s = expand_segment(platform,s)
        q = np.array([number(s['node_power_constant_at_reference_W'][k]) for k in names])
        slope = tuple(number(s['local_leakage_slope_W_per_K'][k]) for k in names)
        lam, u, inv_u = modes(c, g, slope)
        # C*dT/dt=(diag(slope)-G)*T+q-slope*Tref+G*Tamb*ones
        rhs = q - reference*np.array(slope) + ambient*np.asarray(g).sum(axis=1)
        eq = np.linalg.solve(np.asarray(g)-np.diag(slope), rhs)
        h = number(s['duration_ms'])/1000
        if h <= 0 or not np.all(np.isfinite(q)) or any(v<0 for v in slope):
            raise ValueError("invalid power segment")
        coeff = inv_u @ (state - eq[:,None]*one)
        # The energy integral is affine in the initial temperature.
        constant = q.sum() + p.external + np.dot(slope, eq-reference)
        cost = h*constant*one + ((slope@u)*(np.expm1(lam*h)/lam))@coeff
        starts.append(state)
        state = eq[:,None]*one + (u*np.exp(lam*h))@coeff
        ends.append(state)
        costs.append(cost)
        eigenvalues.append(lam)
        eigenvectors.append(u)
        equilibria.append(eq)
        coeffs.append(coeff)
        hs.append(h)
        qs.append(q)
        slopes.append(slope)
    p.start_maps, p.end_maps, p.energy_maps = map(np.array,(starts,ends,costs))
    p.lam, p.u, p.eq, p.coeff_maps = map(np.array,(eigenvalues,eigenvectors,equilibria,coeffs))
    p.h, p.constant, p.slope = map(np.array,(hs,qs,slopes))
    p.times = np.r_[0.0,np.cumsum(p.h)[:-1]]
    p.abs_u_lam2 = np.abs(p.u) * (p.lam**2)[:,None,:]
    p.F, p.b = state[:,:-1].copy(), state[:,-1].copy()
    total = p.energy_maps.sum(axis=0)
    p.w, p.e = total[:-1].copy(), float(total[-1])
    return p
