"""Exact affine segment transfer with a continuous, conservative thermal screen.

The constant-OPP passive four-node model is the frozen synthetic evaluator.
SAFE and VIOLATION below concern the entire segment, not only the handoff.
"""
from pathlib import Path
import sys

import numpy as np
from numba import njit

PLATFORM_DIR = Path(__file__).resolve().parents[1] / "kim_synthetic_platform_v1"
if str(PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(PLATFORM_DIR))
from thermal import evaluate_thermal, modes


SAFE = 1
VIOLATION = 0
UNRESOLVED = -1
NEEDS_REPLAY = -2
# Wider than the original 1e-8 K floating-point guard. Near a limit the
# reference implementation decides, using its own continuous certificate.
SCREEN_GUARD_C = 1e-6
BLOCK_SECONDS = 0.05


@njit(cache=True)
def _screen(modal_delta, u, left_exp, right_exp, upper, witness_temp, witness_exp, limits):
    result = np.empty(len(modal_delta), dtype=np.int8)
    for item in range(len(modal_delta)):
        state = SAFE
        for block in range(len(upper)):
            for node in range(4):
                hi = upper[block, node] + SCREEN_GUARD_C
                at_point = witness_temp[block, node] - SCREEN_GUARD_C
                for mode in range(4):
                    coefficient = u[node, mode] * modal_delta[item, mode]
                    # Each exponential is decreasing throughout the block.
                    envelope = left_exp[block, mode] if coefficient >= 0 else right_exp[block, mode]
                    hi += coefficient * envelope
                    at_point += coefficient * witness_exp[block, node, mode]
                if at_point > limits[node]:
                    state = VIOLATION
                    break
                if hi >= limits[node]:
                    state = NEEDS_REPLAY
            if state == VIOLATION:
                break
        result[item] = state
    return result


class SceneKernel:
    def __init__(self, durations_s, activity_W, transfer_W, thermal_kwargs, block_seconds):
        self.dt = np.asarray(durations_s, dtype=float)
        self.activity = np.asarray(activity_W, dtype=float)
        self.transfer = np.asarray(transfer_W, dtype=float)
        self.kw = dict(thermal_kwargs)
        self.initial = np.broadcast_to(np.asarray(self.kw["initial_C"], dtype=float), (4,)).copy()
        self.limits = np.broadcast_to(np.asarray(self.kw["limits_C"], dtype=float), (4,)).copy()
        # Full call validates input and records a reference anchored precisely
        # on the same integrator as final physical review.
        base = self.replay(self.initial)
        self.energy0 = base["energy_J"]
        self.final0 = np.asarray(base["final_C"])
        lam, u, inv = modes(tuple(self.kw["capacity_J_K"]), tuple(map(tuple,self.kw["conductance_W_K"])),
                            tuple(self.kw["slope_W_K"]))
        self.u = np.ascontiguousarray(u)
        self.inverse = np.ascontiguousarray(inv)
        duration = self.dt.sum()
        self.F = (u * np.exp(lam * duration)) @ inv
        slope = np.asarray(self.kw["slope_W_K"])
        self.w = ((slope @ u) * (np.expm1(lam * duration) / lam)) @ inv
        if not np.isfinite(block_seconds) or block_seconds <= 0:
            raise ValueError("expected positive block duration")
        elapsed = np.r_[0., np.cumsum(self.dt)]
        edges = np.unique(np.r_[0, np.searchsorted(elapsed, np.arange(block_seconds, duration,
                                                                      block_seconds)), len(self.dt)])
        edges = edges[edges <= len(self.dt)]
        self.left_exp = np.exp(elapsed[edges[:-1], None] * lam)
        self.right_exp = np.exp(elapsed[edges[1:], None] * lam)
        self.upper = np.empty((len(edges)-1, 4))
        self.witness_temp = np.empty_like(self.upper)
        self.witness_exp = np.empty((len(edges)-1, 4, 4))
        center = self.initial
        for block, (start, stop) in enumerate(zip(edges[:-1], edges[1:])):
            options = dict(self.kw, initial_C=center, trace=True)
            observed = evaluate_thermal(self.dt[start:stop], self.activity[start:stop],
                                        transfer_W=self.transfer[start:stop], **options)
            self.upper[block] = observed["peak_upper_C"]
            timestamps = observed["trace_time_s"]
            trace = observed["trace_C"]
            witness = np.argmax(trace, axis=0)
            self.witness_temp[block] = trace[witness, np.arange(4)]
            self.witness_exp[block] = np.exp((elapsed[start]+timestamps[witness])[:,None] * lam)
            center = observed["final_C"]
        self.screen_calls = 0
        self.fallback_calls = 0

    def replay(self, entry, trace=False):
        """Use the original physical function, bypassing the compiled screen."""
        options = dict(self.kw, initial_C=np.asarray(entry, dtype=float), trace=trace)
        return evaluate_thermal(self.dt, self.activity, transfer_W=self.transfer, **options)

    def batch(self, entries):
        """Return (J per segment, exit Celsius, status) for an N-by-4 array."""
        entries = np.asarray(entries, dtype=float)
        if entries.ndim != 2 or entries.shape[1] != 4 or not np.all(np.isfinite(entries)):
            raise ValueError("expected a finite N-by-4 array of inlet temperatures")
        if np.any(entries < self.kw["reference_C"]):
            raise ValueError("entry below reference temperature of the original model")
        delta = entries - self.initial
        energy = self.energy0 + delta @ self.w
        final = self.final0 + delta @ self.F.T
        status = _screen(np.ascontiguousarray(delta @ self.inverse.T), self.u,
                         self.left_exp, self.right_exp, self.upper, self.witness_temp,
                         self.witness_exp, self.limits)
        self.screen_calls += len(entries)
        uncertain = np.flatnonzero(status == NEEDS_REPLAY)
        self.fallback_calls += len(uncertain)
        code = {"SAFE":SAFE, "VIOLATION":VIOLATION, "UNRESOLVED":UNRESOLVED}
        for item in uncertain:
            status[item] = code[self.replay(entries[item])["thermal_status"]]
        return energy, final, status


def compile_scene(durations_s, activity_W, transfer_W, thermal_kwargs, block_seconds=BLOCK_SECONDS):
    """Compile one deterministic constant-clock segment; include tail in its last scene."""
    return SceneKernel(durations_s, activity_W, transfer_W, thermal_kwargs, block_seconds)
