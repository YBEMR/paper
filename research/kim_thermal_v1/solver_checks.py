"""Small reference cases only. Use python solver_checks.py to emit complete JSON."""
import json
from itertools import product
from math import isclose

import numpy as np

from physics import compile_template
from solvers import Action, CONFIGS, kim_table, solve_b, solve_d
import workload


def physical_layers():
    scenes = workload.scenes("light", 101)
    layers = []
    for i, scene in enumerate(("AB", "AC")):
        layer = {}
        for cfg in CONFIGS:
            schedule = workload.schedule(scenes[scene], cfg)
            template = None
            if schedule["legal"]:
                segments = list(schedule["segments"])
                if i == 1:
                    segments += workload.tail_segments()
                template = compile_template(workload.PLATFORM, segments)
            layer[cfg] = Action(template, schedule["legal"])
        layers.append(layer)
    return layers


def direct_product(layers, initial, limit):
    # No affine bound, prefix pruning, or cache shared with D.
    trials = []
    for path in product(CONFIGS, repeat=len(layers)):
        entry = np.array(initial, dtype=float)
        energy = 0.
        status = "feasible"
        for layer, cfg in zip(layers, path):
            action = layer[cfg]
            if not action.deadline_ok:
                status = "deadline_or_boundary"
                break
            result = action.thermal.step(entry, limit)
            if not result["safe"]:
                status = "temperature"
                break
            energy += result["energy_J"]
            entry = np.asarray(result["final_T"])
        trials.append({"path": list(path), "status": status,
                       "energy_J": energy if status == "feasible" else None})
    feasible = [r for r in trials if r["status"] == "feasible"]
    return min(feasible, key=lambda r: r["energy_J"]), trials


class ResetBoundary:
    """A deliberate test-only intervention: return nominal T after the segment."""
    def __init__(self, real_template, nominal):
        self.real = real_template
        self.F = np.zeros_like(real_template.F)
        self.b = np.array(nominal)
        self.w, self.e = self.real.w, self.real.e

    def step(self, entry, limits):
        outcome = self.real.step(entry, limits)
        return {**outcome, "final_T": self.b.tolist()}


class Toy:
    def __init__(self, rise, energy):
        self.F, self.b = np.eye(1), np.array([rise], dtype=float)
        self.w, self.e = np.zeros(1), float(energy)

    def step(self, entry, limits):
        end = self.F @ entry + self.b
        return {"safe": bool(max(entry[0], end[0]) <= limits),
                "energy_J": self.e, "final_T": end.tolist()}


def run():
    layers = physical_layers()
    initial = [50] * 4
    expected, trials = direct_product(layers, initial, 80)
    found = solve_d(layers, initial, 80)
    assert found["status"] == "optimal" and found["path"] == expected["path"]
    assert isclose(found["energy_J"], expected["energy_J"], abs_tol=1.e-10, rel_tol=0.)
    limited = solve_d(layers, initial, 80, max_visits=1)
    assert limited["status"] == "budget_limit" and limited["visits"] == 1
    assert limited["lower_bound_J"] <= expected["energy_J"] + 1.e-10
    reset = [{c: Action(ResetBoundary(a.thermal, initial), True) if a.deadline_ok else a
              for c,a in layer.items()} for layer in layers]
    independent = [direct_product([layer], initial, 80)[0] for layer in layers]
    independent_cost = sum(x["energy_J"] for x in independent)
    decoupled = solve_d(reset, initial, 80)
    assert decoupled["status"] == "optimal"
    assert decoupled["path"] == [r["path"][0] for r in independent]
    assert isclose(decoupled["energy_J"], independent_cost, abs_tol=1.e-10, rel_tol=0.)

    first = {c: Action(None, False) for c in CONFIGS}
    second = first.copy()
    first["HHH"] = Action(Toy(0, 2), True)
    first["LLL"] = Action(Toy(8, 1), True)
    second["HHH"] = Action(Toy(5, 3), True)
    lookahead = solve_d([first,second], [25], 35)
    myopic = solve_b([first,second], [25], 35)
    assert myopic["status"] == "no_feasible_current_action"
    assert lookahead["path"] == ["HHH","HHH"] and lookahead["energy_J"] == 5
    impossible = solve_d([first,second], [34], 35)
    assert impossible["status"] == "infeasible" and impossible["energy_J"] is None
    tied = {c: Action(None, c != "HLH", nominal_energy=1.) for c in CONFIGS}
    saved, visited = kim_table(tied, [])
    assert saved == "HHH" and [x["cfg"] for x in visited][:4] == ["HHH","HLH","HHH","LHH"]
    return {"status": "passed", "physical_two_segment_fixture": ["light",101,"AB","AC",50,80],
            "full_product": trials, "product_optimum": expected, "exact": found,
            "budget_one_visit": limited, "independent_scenes": independent,
            "reset_boundary_exact": decoupled, "teaching_only": {"B": myopic, "D": lookahead,
            "infeasible": impossible}, "kim_high_to_low_and_rollback_first_four": visited[:4]}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, allow_nan=False))
