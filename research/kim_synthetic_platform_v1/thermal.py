"""Four-node, constant-OPP electrothermal integration on actual event intervals.

The V1 symmetric eigenbasis gives an analytic state and leakage energy integral.
The transient forcing is expressed relative to ambient to avoid cancellations.
The V1 continuous-peak interpolation bound is tightened by checking the sign of
the derivative and subdividing ambiguous intervals. Bounds include a binary64
roundoff guard and are not directed-rounding interval certificates.
"""
import sys
from pathlib import Path

import numpy as np
from numba import njit

# Import only the shared analytic eigensystem from the pinned repository.
V1_DIR = Path(__file__).resolve().parent.parent / "kim_thermal_v1"
if str(V1_DIR) not in sys.path:
    sys.path.append(str(V1_DIR))
from physics import modes

ROUND_GUARD = 1e-8
DEFAULT_PEAK_WIDTH = 5e-4


@njit(cache=True)
def _primitive(lam, h):
    """Return integral exp(lam*t) and its integral from 0 to h."""
    lh = lam*h
    phi = np.expm1(lh)/lam
    if abs(lh) < 0.01:
        psi = h*h*(0.5+lh*(1/6+lh*(1/24+lh*(1/120+lh*(1/720+lh/5040)))))
    else:
        psi = (np.expm1(lh)-lh)/(lam*lam)
    return phi, psi


@njit(cache=True)
def _tighten_peak(start, end, h, limit, lam, coeff, width):
    """Enclose the maximum of one coordinate of a four-mode trajectory.

    coeff[k] is the modal contribution to the node derivative at t=0.
    Each item on the bounded DFS stack is an interval within this power event.
    """
    stack = np.empty((36, 5))
    stack[0] = np.array([0.0, h, start, end, 0.0])
    size = 1
    lower = max(start, end)-ROUND_GUARD
    upper = lower
    while size:
        size -= 1
        left, right, a, b, depth = stack[size]
        dt = right-left
        observed = max(a, b)
        curvature = 0.0
        derivative = 0.0
        for k in range(4):
            rate = coeff[k]*np.exp(lam[k]*left)
            curvature += abs(lam[k]*rate)
            derivative += rate
        delta = curvature*dt*dt/8
        if abs(derivative) > curvature*dt + ROUND_GUARD:
            delta = 0.0
        lo = observed-ROUND_GUARD
        hi = observed + delta + ROUND_GUARD
        ambiguity = lo <= limit < hi
        if (delta > width or ambiguity) and delta > ROUND_GUARD and depth < 30:
            mid = (left+right)*0.5
            temp = start
            for k in range(4):
                temp += coeff[k]*np.expm1(lam[k]*mid)/lam[k]
            stack[size] = np.array([mid, right, temp, b, depth+1])
            stack[size+1] = np.array([left, mid, a, temp, depth+1])
            size += 2
        else:
            if lo > lower:
                lower = lo
            if hi > upper:
                upper = hi
    return lower, upper


@njit(cache=True)
def _replay(h, activity, transfer, reset, capacity, idle_heat, transfer_share,
            slopes, ta, tref, start, limits, lam, u, inv_u, trace, width):
    times = np.empty(len(h)+np.count_nonzero(reset[1:])+1 if trace else 0)
    temperatures = np.empty((len(times), 4))
    T = start.copy()
    peak_low = start.copy()-ROUND_GUARD
    peak_high = start.copy()+ROUND_GUARD
    d = np.zeros(4)
    x = inv_u @ (T-ta)
    int_x = np.zeros(4)
    x_next = np.zeros(4)
    heat = np.zeros(4)
    coeff = np.zeros(4)
    int_T_inc = np.zeros(4)
    elapsed = 0.0
    pos = 0
    if trace:
        times[pos], temperatures[pos] = 0.0, start
        pos += 1
    for i in range(len(h)):
        dt = h[i]
        if reset[i] and i > 0:
            T = start.copy()
            x = inv_u @ (T-ta)
            if trace:
                times[pos], temperatures[pos] = elapsed, T
                pos += 1
        for n in range(4):
            heat[n] = (idle_heat[n] + activity[i,n] + slopes[n]*(ta-tref)
                       + transfer[i]*transfer_share[n])/capacity[n]
        for k in range(4):
            forcing = 0.0
            for n in range(4):
                forcing += inv_u[k,n]*heat[n]
            d[k] = lam[k]*x[k] + forcing
            phi, psi = _primitive(lam[k],dt)
            int_x[k] = dt*x[k] + psi*d[k]
            x_next[k] = x[k] + phi*d[k]
        for n in range(4):
            end = ta
            excess_integral = (ta-tref)*dt
            curvature = 0.0
            for k in range(4):
                end += u[n,k]*x_next[k]
                excess_integral += u[n,k]*int_x[k]
                coeff[k] = u[n,k]*d[k]
                curvature += abs(lam[k]*coeff[k])
            int_T_inc[n] += excess_integral
            observed = max(T[n],end)
            delta = dt*dt*curvature/8
            lo, hi = observed-ROUND_GUARD, observed+delta+ROUND_GUARD
            if delta > width or (lo <= limits[n] < hi and delta > ROUND_GUARD):
                lo, hi = _tighten_peak(T[n],end,dt,limits[n],lam,coeff,width)
            if lo > peak_low[n]:
                peak_low[n] = lo
            if hi > peak_high[n]:
                peak_high[n] = hi
            T[n] = end
        for k in range(4):
            x[k] = x_next[k]
        elapsed += dt
        if trace:
            times[pos], temperatures[pos] = elapsed, T
            pos += 1
    return T, peak_low, peak_high, int_T_inc, times, temperatures


def _vector(values, label):
    a = np.broadcast_to(np.asarray(values, dtype=float), (4,)).copy()
    if not np.all(np.isfinite(a)):
        raise ValueError(f"Nonfinite {label}")
    return a


def _shares(values, label):
    a = _vector(values, label)
    if np.any(a < 0) or sum(a) > 1 + 1e-12:
        raise ValueError(f"Invalid shares for {label}")
    return a


def evaluate_thermal(durations_s, activity_W, *, capacity_J_K, conductance_W_K,
                     idle_W, slope_W_K, board_W, board_heat_fraction, ambient_C,
                     reference_C, initial_C, limits_C, reset_indices=(), trace=False,
                     transfer_W=None, transfer_heat_fraction=(0,0,0,0),
                     peak_width_C=DEFAULT_PEAK_WIDTH):
    """Integrate complete power events, including idle and the evaluation tail.

    Use a positive full conductance matrix G=diag(environment)+L(coupling);
    C*T'= idle + active + injected board/transfer heat + slope*(T-ref)
    - G*(T-ambient). Whole-board energy includes entire board/transfer power
    even when some heat dissipates outside the four modeled sites. Leakage_J
    is the incremental leakage above the reference-temperature idle intercept.
    """
    dt = np.ascontiguousarray(durations_s, dtype=float)
    activity = np.ascontiguousarray(activity_W, dtype=float)
    transfer = np.zeros(len(dt)) if transfer_W is None else np.ascontiguousarray(transfer_W, dtype=float)
    if dt.ndim != 1 or not len(dt) or not np.all(np.isfinite(dt)) or np.any(dt <= 0):
        raise ValueError("Expected positive finite interval durations in seconds")
    if activity.shape != (len(dt),4) or not np.all(np.isfinite(activity)) or np.any(activity < 0):
        raise ValueError("Expected one nonnegative activity power per event and node")
    if transfer.shape != dt.shape or not np.all(np.isfinite(transfer)) or np.any(transfer < 0):
        raise ValueError("Invalid transfer power")
    c = _vector(capacity_J_K, "capacity")
    idle = _vector(idle_W, "reference idle power")
    slope = _vector(slope_W_K, "leakage slope")
    initial = _vector(initial_C, "initial temperature")
    limits = _vector(limits_C, "temperature limits")
    if np.any(c <= 0) or np.any(idle < 0) or np.any(slope < 0):
        raise ValueError("Invalid capacity, idle power or leakage slope")
    g = np.asarray(conductance_W_K,dtype=float)
    if (g.shape != (4,4) or not np.all(np.isfinite(g))
            or not np.allclose(g, g.T, atol=1e-12, rtol=0)
            or np.any(g-np.diag(np.diag(g)) > 0) or np.min(g.sum(axis=1)) < -1e-12):
        raise ValueError("Conductance must describe passive symmetric coupling to ambient")
    if not np.all(np.isfinite([board_W,ambient_C,reference_C,peak_width_C])) or board_W < 0 or peak_width_C <= 0:
        raise ValueError("Invalid temperatures, board power or peak tolerance")
    if ambient_C < reference_C or min(initial) < reference_C:
        raise ValueError("This nonnegative incremental leakage law requires ambient and entry >= reference")
    reset = np.zeros(len(dt), dtype=bool)
    indices = np.asarray(reset_indices)
    if indices.size:
        if indices.ndim != 1 or indices.dtype.kind not in "iu" or np.any(indices < 0) or np.any(indices >= len(dt)):
            raise ValueError("Reset indices must locate interval starts")
        reset[indices] = True
    idle_heat = idle + board_W*_shares(board_heat_fraction, "board heat")
    tr_heat = _shares(transfer_heat_fraction, "transfer heat")
    lam,u,inv_u = modes(tuple(c),tuple(map(tuple,g)),tuple(slope))
    end,lo,hi,inc,times,temps = _replay(
        dt,activity,transfer,reset,c,idle_heat,tr_heat,slope,float(ambient_C),
        float(reference_C),initial,limits,lam,np.ascontiguousarray(u),
        np.ascontiguousarray(inv_u),trace,float(peak_width_C))
    span = float(np.sum(dt))
    common = board_W*span
    transfer_energy = float(np.sum(transfer*dt))
    base = idle*span
    active = np.sum(activity*dt[:,None],axis=0)
    leakage = slope*inc
    if np.min(leakage) < -1e-9:
        raise ArithmeticError("Model left the nonnegative incremental leakage range")
    leakage = np.maximum(leakage,0.0)
    if not np.all(np.isfinite(np.r_[end,lo,hi,leakage])):
        raise ArithmeticError("Nonfinite thermal replay")
    status = "VIOLATION" if np.any(lo > limits) else ("SAFE" if np.all(hi <= limits) else "UNRESOLVED")
    result = dict(energy_J=float(common+transfer_energy+sum(base)+sum(active)+sum(leakage)),
                  common_J=common, transfer_J=transfer_energy, idle_J=base.tolist(),
                  activity_J=active.tolist(), leakage_J=leakage.tolist(), final_C=end.tolist(),
                  peak_lower_C=lo.tolist(),peak_upper_C=hi.tolist(),thermal_status=status)
    if trace:
        result.update(trace_time_s=times,trace_C=temps)
    return result
