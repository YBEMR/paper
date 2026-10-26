"""E1 objective-only HEFT adaptation; no scientific evaluation at import.

The construction and single-pass neighborhood are inherited unchanged from
``heft_method``. This module consumes a search-facing score view; a score is
never substituted into the saved true electrothermal receipt.
"""
from copy import deepcopy
from fractions import Fraction as F

from auto_heuristic_policy import require_heuristic_control
from start_domain import explicit_start_sets
from heft_method import (_check, _q, _candidate_state, _next_start,
                         build_heft_candidate, RULES as HEFT_RULES,
                         RULE_VERSION as HEFT_RULE_VERSION)


HEFT_SOURCE_SHA256 = "0ea5d95222938f430918d0109032a43a3ca3dcc115ffb879da49e79b83fda6a1"
RULE_VERSION = HEFT_RULE_VERSION + "-e1-objective-view-v1"
RULES = dict(HEFT_RULES)
RULES["energy_adjustment"] = (
    "one unchanged deterministic unit/OPP/one-successor-start pass; "
    "SAFE planning-score interval-strict descent only")


def _planning_interval(receipt):
    if not isinstance(receipt, dict) or receipt.get("state") != "SAFE":
        return None
    values = receipt.get("planning_score_J")
    if not isinstance(values, (list, tuple)) or len(values) != 2:
        return None
    lower, upper = F(values[0]), F(values[1])
    if lower < 0 or upper < lower:
        return None
    return lower, upper


def run_search(instance, config, budget, assess, *, allow_auto_low=False):
    """Construct and make the original single pass using an explicit score view.

    ``assess(candidate, source)`` returns only a search-facing SAFE score view
    with ``planning_score_J``; the outer recorder keeps the original physical
    receipt unchanged and selects its final candidate by the same objective.
    Local interval-strict acceptance, all candidate construction rules and
    budget checkpoints are inherited verbatim. Exhaustion propagates.
    """
    require_heuristic_control(instance, config, 'HEFT search', allow_auto_low=allow_auto_low)
    del config  # Same expanded instance supplies all options; no hidden answers.
    meta = {"rule_version": RULE_VERSION, "rules": dict(RULES),
            "construction_attempts": [], "local_attempts": [],
            "local_accepted": 0, "coverage_status": "HEURISTIC_NOT_EXHAUSTIVE",
            "infeasibility_status": "NOT_PROVED", "optimality_status": "NOT_PROVED"}
    current, receipt = None, None
    seen = set()
    for rank in (None, 0, 1, 2):
        _check(budget)
        constructed = build_heft_candidate(instance, budget, opp_rank=rank)
        meta["construction_attempts"].append({key: value for key, value in constructed.items()
                                               if key not in ("candidate", "validation")})
        candidate = constructed["candidate"]
        if candidate is None:
            continue
        signature = tuple((sid, tuple((row["stage_id"], row["unit"], row["opp"], row["start_ms"])
                                      for row in rows))
                          for sid, rows in sorted(candidate["scenes"].items()))
        if signature in seen:
            meta["construction_attempts"][-1]["duplicate_construction"] = True
            continue
        seen.add(signature)
        result = assess(candidate, "heft:eft" if rank is None else f"heft:fallback-opp-rank-{rank}")
        if _planning_interval(result) is not None:
            current, receipt = deepcopy(candidate), result
            break
    if current is None:
        meta["status"] = "NO_SAFE_CONSTRUCTED_WITNESS"
        return meta
    declared = explicit_start_sets(instance, budget)
    identity_order = sorted(instance["stage_modes"])
    execution_order = sorted((scene["id"], stage["id"]) for scene in instance["scenarios"]
                             for stage in scene["stage_instances"])
    shared_for = {(scene["id"], stage["id"]): stage["shared_stage_id"]
                  for scene in instance["scenarios"] for stage in scene["stage_instances"]}

    def attempt(kind, details, **overrides):
        nonlocal current, receipt
        _check(budget)
        built = build_heft_candidate(instance, budget, **overrides)
        event = {"kind": kind, **details, "construction_status": built["status"], "accepted": False}
        meta["local_attempts"].append(event)
        if built["candidate"] is None:
            event["reason"] = built["reason"]
            return
        result = assess(built["candidate"], "heft:energy-pass:" + kind)
        interval, previous = _planning_interval(result), _planning_interval(receipt)
        event["assessment_state"] = result.get("state")
        if interval is not None and interval[1] < previous[0]:
            current, receipt = deepcopy(built["candidate"]), result
            event["accepted"] = True
            meta["local_accepted"] += 1

    for shared in identity_order:
        for unit in sorted({mode["unit_id"] for mode in instance["stage_modes"][shared]}):
            _check(budget)
            deployment, opps, _ = _candidate_state(current, instance)
            if unit == deployment[shared]:
                continue
            deployment[shared] = unit
            opps = {key: opp for key, opp in opps.items() if shared_for[key] != shared}
            attempt("shared-unit", {"shared_stage_id": shared, "unit": unit},
                    deployment_override=deployment, opp_override=opps)
    for key in execution_order:
        for opp in sorted({mode["opp_id"] for mode in instance["stage_modes"][shared_for[key]]}):
            _check(budget)
            deployment, opps, _ = _candidate_state(current, instance)
            if opp == opps[key]:
                continue
            opps[key] = opp
            attempt("execution-opp", {"scenario": key[0], "stage_id": key[1], "opp": opp},
                    deployment_override=deployment, opp_override=opps)
    for key in execution_order:
        _check(budget)
        deployment, opps, floors = _candidate_state(current, instance)
        nxt = _next_start(instance, key[0], key[1], _q(floors[key]), declared)
        if nxt is None:
            continue
        floors[key] = str(nxt)
        attempt("one-start-delay", {"scenario": key[0], "stage_id": key[1], "floor_ms": str(nxt)},
                deployment_override=deployment, opp_override=opps, start_floor=floors)
    meta.update(status="BOUNDED_SEARCH_COMPLETED", local_base_candidate=current,
                local_base_planning_score_J=receipt["planning_score_J"])
    return meta
