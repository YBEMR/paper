"""Four explicit backend recipes on the caller's already-started root clock.

Importing this module starts no planner, native process or physical evaluation.
Only an independently authorized launcher may call the real dispatch path.
``_entries`` is a private in-memory simulation hook: every such dispatch is
marked not_scientific and never receives real HEFT/thermal/native bindings.
"""
from copy import deepcopy
from dataclasses import dataclass
import math
from pathlib import Path


ARMS = ("C", "HEFT", "SINGLE", "PAIR")
METHOD_SECONDS = 300
_C_KEYS = {"seconds", "shared_deployment", "builder_options", "opened_by_scene",
           "scene_slice_s", "linked_opened_by_scene", "preeliminate_closed_anchors"}
_C_BUILD = {"fix_late_options": True, "aggregate_opp_locks": True,
            "relax_auxiliary_integrality": True, "strengthen_energy_lower_bounds": True,
            "prefilter_deadlines": True, "cumulative_precedence": False}
_C_SHARED = {"A.pre": "CPU1", "A.main": "NPU0", "A.post": "CPU1"}


def _blocked_test_backend(*args, **kwargs):
    raise RuntimeError("Simulation cannot start a real initializer, native session or evaluator")


@dataclass(frozen=True)
class _MockOnlyBindings:
    initializer: object = _blocked_test_backend
    evaluator: object = _blocked_test_backend
    kind: str = "MOCK_ONLY"


def _c_kwargs(recipe):
    if not isinstance(recipe, dict) or not isinstance(recipe.get("kwargs"), dict):
        raise ValueError("C requires the separately frozen K172 kwargs recipe")
    kwargs = deepcopy(recipe["kwargs"])
    if (set(kwargs) != _C_KEYS or type(kwargs["seconds"]) is not int
            or kwargs["seconds"] != METHOD_SECONDS
            or type(kwargs["scene_slice_s"]) is not int or kwargs["scene_slice_s"] != 60
            or kwargs["shared_deployment"] != _C_SHARED
            or kwargs["preeliminate_closed_anchors"] is not True
            or kwargs["builder_options"] != _C_BUILD
            or any(type(kwargs["builder_options"][key]) is not bool for key in _C_BUILD)):
        raise ValueError("Original C recipe changed")
    first, second = kwargs["opened_by_scene"], kwargs["linked_opened_by_scene"]
    if (not isinstance(first, dict) or not isinstance(second, dict)
            or set(first) != set(second) or len(first) != 2):
        raise ValueError("C requires matching original two-scene opening declarations")
    for scene_id in first:
        for declaration, count in ((first, 2), (second, 4)):
            values = declaration[scene_id]
            if (not isinstance(scene_id, str) or not isinstance(values, list)
                    or len(values) != count or any(not isinstance(value, str) for value in values)
                    or len(set(values)) != count):
                raise ValueError("Original C 2-open then 4-open declarations changed")
    return kwargs


def dispatch(arm, loader, workdir, budget, recipe, *, _entries=None):
    """Call exactly one declared backend, preserving its raw result object.

    ``recipe`` supplies C's exact ``kwargs``; other arms use fixed recipes here.
    The surrounding registry must additionally bind case identities, source
    hashes, slot order and authorization. No historical result is read here.

    Simulation injection is a dictionary of callable entries keyed only by
    C/HEFT/SINGLE/PAIR; the selected key must exist. Its graph binding and C
    session factory are inert local sentinels rather than real backend objects.
    """
    if arm not in ARMS:
        raise ValueError("Unknown four-arm backend")
    if not callable(loader):
        raise TypeError("A fresh budget-local input loader is required")
    if (isinstance(budget.seconds, bool) or not isinstance(budget.seconds, (int, float))
            or not math.isfinite(budget.seconds) or budget.seconds != METHOD_SECONDS
            or not callable(budget.clock)):
        raise ValueError("The caller must supply one unchanged 300-second root budget")
    budget.check()
    root_start, root_deadline = budget.start, budget.deadline
    root_seconds, root_clock = budget.seconds, budget.clock
    kwargs = _c_kwargs(recipe) if arm == "C" else None
    simulated = _entries is not None
    if simulated and (not isinstance(_entries, dict) or set(_entries) - set(ARMS)
                      or arm not in _entries or not callable(_entries[arm])):
        raise ValueError("Only explicit callable four-arm test entries may be injected")
    before_imports = budget.elapsed
    with budget.phase("selected_arm_imports"):
        if simulated:
            entry = _entries[arm]
            session_factory = _blocked_test_backend
            bindings = _MockOnlyBindings()
        elif arm == "C":
            from functools import partial
            from linked_method import execute_linked_fixed_unit_opp_start
            from matlab_bridge import MatlabSession
            entry = execute_linked_fixed_unit_opp_start
            session_factory = partial(MatlabSession, cut_max_iterations=10)
        elif arm == "HEFT":
            from heuristic_runner import execute_heuristic
            entry = execute_heuristic
        else:
            from heft_method import run_heft
            from thermal import evaluate_candidate
            from research.chapter4_scheduler.method import Bindings, execute_reconstruction
            entry = execute_reconstruction
            bindings = Bindings(initializer=run_heft, evaluator=evaluate_candidate, kind="REAL_CORE")
    selected_imports_elapsed_s = budget.elapsed - before_imports
    budget.check()
    if arm == "C":
        result = entry(loader, Path(workdir), **kwargs, budget=budget,
                       clock=budget.clock, session_factory=session_factory)
    elif arm == "HEFT":
        result = entry(loader, Path(workdir), method="heft", seconds=METHOD_SECONDS,
                       seed=None, allow_auto_low=True, budget=budget, clock=budget.clock)
    else:
        result = entry(loader, Path(workdir), bindings=bindings, seconds=METHOD_SECONDS,
                       variant="single" if arm == "SINGLE" else "pair",
                       budget=budget, clock=budget.clock)
    return {"result": result, "not_scientific": simulated,
            "root_start": root_start, "root_deadline": root_deadline,
            "selected_imports_elapsed_s": selected_imports_elapsed_s, "arm": arm,
            "budget_unchanged": (budget.start == root_start and budget.deadline == root_deadline
                and budget.seconds == root_seconds and budget.clock is root_clock)}
