"""Offline Kim adaptation, myopic enumeration, and finite-domain exact search.

All three receive the same time-feasible actions and compiled physical templates.
Path order uses CPU/GPU/NPU triplets. Energies are joules, temperatures Celsius.
"""
from dataclasses import dataclass
from itertools import product
from math import inf
from time import perf_counter

import numpy as np


CONFIGS = tuple("".join(parts) for parts in product("LH", repeat=3))


@dataclass(frozen=True)
class Action:
    thermal: object
    deadline_ok: bool
    nominal_energy: float = None


def _energy(action, entry):
    return float(action.thermal.w @ entry + action.thermal.e)


def _check(template, entry, limits):
    result = template.step(entry, limits)
    if result.get("unresolved"):
        raise ArithmeticError("Continuous safety at a visited search point is unresolved")
    return result


def kim_table(layer, nominal_T):
    """Adapted Kim Algorithm 3. Traverse two passes, remember best feasible trial."""
    current = list("HHH")
    best = None
    best_energy = inf
    trials = []
    for _ in range(2):
        for domain in (1, 0, 2):  # GPU, CPU, DLA
            for level in "HL":
                current[domain] = level
                cfg = "".join(current)
                action = layer[cfg]
                score = None
                if action.deadline_ok:
                    score = action.nominal_energy
                    if score is None:
                        score = _energy(action, nominal_T)
                    if score < best_energy:
                        best, best_energy = cfg, score
                trials.append({"cfg": cfg, "deadline_ok": bool(action.deadline_ok),
                               "nominal_energy_J": score})
                if not action.deadline_ok:
                    if level == "L":
                        current[domain] = "H"
                    break
    return best, trials


def _policy_result(path, energies, feasible, status, details, started):
    return {"path": path, "energy_J": sum(energies) if feasible else None,
            "evaluated_prefix_energy_J": sum(energies), "feasible": bool(feasible),
            "status": status, "decisions": details, "elapsed_s": perf_counter()-started}


def solve_a(layers, initial_T, limits, nominal_T):
    started = perf_counter()
    entry = np.asarray(initial_T, dtype=float)
    path, energies, details = [], [], []
    safe = True
    for layer in layers:
        cfg, trials = kim_table(layer, np.asarray(nominal_T))
        if cfg is None:
            details.append({"trials": trials})
            return _policy_result(path, energies, False, "no_schedulable_trial", details, started)
        chosen = _check(layer[cfg].thermal, entry, limits)
        details.append({"trials": trials, "selected": cfg, "safe": bool(chosen["safe"])})
        safe = safe and chosen["safe"]
        entry = np.asarray(chosen["final_T"])
        energies.append(chosen["energy_J"])
        path.append(cfg)
    return _policy_result(path, energies, safe, "feasible" if safe else "over_temperature",
                          details, started)


def solve_b(layers, initial_T, limits):
    started = perf_counter()
    entry = np.asarray(initial_T, dtype=float)
    path, energies, details = [], [], []
    for layer in layers:
        best, best_energy, best_exit = None, inf, None
        trials = []
        for cfg in CONFIGS:
            action = layer[cfg]
            if not action.deadline_ok:
                trials.append({"cfg": cfg, "deadline_ok": False})
                continue
            trial = _check(action.thermal, entry, limits)
            trials.append({"cfg": cfg, "deadline_ok": True, "safe": bool(trial["safe"]),
                           "current_energy_J": trial["energy_J"]})
            if trial["safe"] and trial["energy_J"] < best_energy:
                best, best_energy, best_exit = cfg, trial["energy_J"], trial["final_T"]
        details.append({"trials": trials, "selected": best})
        if best is None:
            return _policy_result(path, energies, False, "no_feasible_current_action",
                                  details, started)
        entry = np.asarray(best_exit)
        energies.append(best_energy)
        path.append(best)
    return _policy_result(path, energies, True, "feasible", details, started)


def _lower_planes(options, initial_T):
    """f_i(T) >= intercept_i + slope_i @ (T-floor_i).

    Propagators are nonnegative (cooperative RC dynamics). Taking componentwise
    minima over actions gives a reachable temperature floor at each depth. On
    T >= floor_i every coordinate's displacement is nonnegative, so the min of
    the affine action costs dominates the plane with all coefficients minimized
    separately. Ignoring temperature constraints can only weaken this bound.
    """
    floors = [np.asarray(initial_T, dtype=float)]
    for actions in options:
        if any(np.min(t.F) < 0 for _, t in actions):
            raise ValueError("Reachability floor requires nonnegative RC propagators")
        floors.append(np.min([t.F @ floors[-1] + t.b for _, t in actions], axis=0)-1e-10)
    slope = np.zeros_like(floors[0])
    intercept = 0.
    planes = [(slope, intercept)]
    for i in range(len(options)-1, -1, -1):
        next_floor = floors[i+1]
        floor = floors[i]
        intercepts, slopes = [], []
        for _, t in options[i]:
            exit_at_floor = t.F @ floor + t.b
            intercepts.append(t.w @ floor + t.e + intercept + slope @ (exit_at_floor-next_floor))
            slopes.append(t.w + slope @ t.F)
        slope = np.min(slopes, axis=0)
        intercept = float(min(intercepts)) - 1e-10
        planes.append((slope, intercept))
    return floors, planes[::-1]


def solve_d(layers, initial_T, limits, max_visits=100000, time_limit_s=60.0):
    started = perf_counter()
    initial_T = np.asarray(initial_T, dtype=float)
    options = [[(cfg, layer[cfg].thermal) for cfg in CONFIGS if layer[cfg].deadline_ok]
               for layer in layers]
    if not all(options):
        return {"path": [], "energy_J": None, "feasible": False, "status": "infeasible",
                "lower_bound_J": None, "upper_bound_J": None, "visits": 0,
                "thermal_checks": 0, "elapsed_s": perf_counter()-started}
    floors, planes = _lower_planes(options, initial_T)
    incumbent, solution = inf, []
    visits, checks, hot, pruned = 0, 0, 0, 0
    cutoff = False
    path = []

    def search(i, entry, spent):
        nonlocal incumbent, solution, visits, checks, hot, pruned, cutoff
        if i == len(options):
            if spent < incumbent:
                incumbent, solution = spent, list(path)
            return
        slope, intercept = planes[i+1]
        children = []
        for j, (cfg, t) in enumerate(options[i]):
            next_entry = t.F @ entry + t.b
            cost = spent + float(t.w @ entry + t.e)
            lower = cost + intercept + float(slope @ (next_entry-floors[i+1]))
            children.append((lower, j, cfg, t, next_entry, cost))
        for lower, _, cfg, t, next_entry, cost in sorted(children, key=lambda item: item[:2]):
            if visits >= max_visits or perf_counter()-started >= time_limit_s:
                cutoff = True
                return
            visits += 1
            if lower > incumbent + 1e-9:
                pruned += 1
                continue
            checks += 1
            if not _check(t, entry, limits)["safe"]:
                hot += 1
                continue
            path.append(cfg)
            search(i+1, next_entry, cost)
            path.pop()
            if cutoff:
                return
    search(0, initial_T, 0.)
    feasible = incumbent < inf
    status = "budget_limit" if cutoff else ("optimal" if feasible else "infeasible")
    energy = incumbent if feasible else None
    lower = max(0., planes[0][1]) if cutoff else energy
    return {"path": solution, "energy_J": energy, "feasible": feasible, "status": status,
            "lower_bound_J": lower, "upper_bound_J": energy, "visits": visits,
            "thermal_checks": checks, "thermal_rejects": hot, "bound_prunes": pruned,
            "elapsed_s": perf_counter()-started}
