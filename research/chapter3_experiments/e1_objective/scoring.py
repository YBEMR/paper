"""Objective-only E1 scoring of already accepted complete true-H evidence.

This module does not search, reconstruct temperatures, or change receipts.
OMIT_TEMP is an exact integration of the non-temperature power components,
not subtraction of two interval enclosures. FULL retains the true interval.
"""
from fractions import Fraction as F
import math

from h02_pair_preflight.common import (ContractError, candidate_identity, exact,
                                      require, sha)
from h02_pair_preflight.receipts import interval, safe_receipt

OBJECTIVES = frozenset({"FULL", "OMIT_TEMP"})


def _nonnegative_map(value, keys, reason):
    require(isinstance(value, dict) and set(value) == set(keys), reason)
    result = {key: exact(item) for key, item in value.items()}
    require(all(item >= 0 for item in result.values()), "NEGATIVE_POWER")
    return result


def _check(instance, candidate, legality, receipt, accuracy, seconds, objective):
    require(isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and
            math.isfinite(seconds) and seconds > 0, "INVALID_ROOT_BUDGET")
    require(objective in OBJECTIVES, "UNKNOWN_OBJECTIVE")
    identity = candidate_identity(instance, candidate)
    safe_receipt(instance, candidate, receipt, accuracy, seconds)
    require(legality.get("state") == "SCHEDULE_VALID_THERMAL_UNCHECKED",
            "INVALID_LEGALITY_FOR_SCORE")
    require(legality == receipt.get("legality"), "LEGALITY_RECEIPT_MISMATCH")
    require(legality.get("problem_id") == instance["id"], "LEGALITY_PROBLEM_ID")
    scenes = {scene["id"]: scene for scene in instance["scenarios"]}
    require(len(scenes) == len(instance["scenarios"]) and bool(scenes),
            "DUPLICATE_OR_EMPTY_SCENES")
    require(set(legality["scenes"]) == set(scenes), "LEGALITY_SCENE_COVERAGE")
    weights = {sid: exact(scene["weight"]) for sid, scene in scenes.items()}
    require(all(weight >= 0 for weight in weights.values()) and
            sum(weights.values()) == 1, "INVALID_SCENARIO_WEIGHTS")
    nodes = instance["platform"]["node_order"]
    domains = instance["platform"]["domains"]
    require(bool(nodes) and len(set(nodes)) == len(nodes), "INVALID_NODE_IDENTITIES")
    require(legality.get("node_order") == nodes, "LEGALITY_NODE_ORDER")
    require(bool(domains), "EMPTY_POWER_GROUPS")
    window = exact(instance["window_ms"])
    require(window > 0, "INVALID_WINDOW")
    external = exact(instance["platform"]["external_common_power_W"])
    require(external >= 0, "NEGATIVE_EXTERNAL_POWER")
    no_temperature = F(0)
    for sid in scenes:
        segments = legality["scenes"][sid]["segments"]
        require(isinstance(segments, list) and bool(segments), "EMPTY_POWER_SEGMENTS")
        cursor = F(0)
        components = {name: F(0) for name in ("baseline", "activity", "external_common")}
        for segment in segments:
            start, end, duration = (exact(segment[key]) for key in
                                    ("start_ms", "end_ms", "duration_ms"))
            require(start == cursor and end > start and end <= window and
                    duration == end - start, "POWER_SEGMENT_COVERAGE")
            groups = _nonnegative_map(segment["baseline_by_power_group_W"],
                                      domains, "BASELINE_GROUP_COVERAGE")
            bases = _nonnegative_map(segment["baseline_by_node_W"],
                                     nodes, "BASELINE_NODE_COVERAGE")
            activity = _nonnegative_map(segment["activity_by_node_W"],
                                        nodes, "ACTIVITY_NODE_COVERAGE")
            constants = _nonnegative_map(segment["node_power_constant_at_reference_W"],
                                         nodes, "POWER_CONSTANT_NODE_COVERAGE")
            require(sum(groups.values()) == sum(bases.values()),
                    "BASELINE_GROUP_NODE_MISMATCH")
            require(all(constants[n] == bases[n] + activity[n] for n in nodes),
                    "POWER_CONSTANT_MISMATCH")
            require(exact(segment["external_common_power_W"]) == external and
                    exact(segment["external_common_injected_heat_W"]) == 0,
                    "EXTERNAL_SEGMENT_POWER_MISMATCH")
            components["baseline"] += duration * sum(groups.values()) / 1000
            components["activity"] += duration * sum(activity.values()) / 1000
            components["external_common"] += duration * external / 1000
            cursor = end
        require(cursor == window, "INCOMPLETE_POWER_WINDOW")
        receipt_components = receipt["scenes"][sid]["energy_components_J"]
        for name, value in components.items():
            lo, hi = interval(receipt_components[name])
            require(lo <= value <= hi, "COMPONENT_ACCOUNTING_MISMATCH:" + name)
        no_temperature += weights[sid] * sum(components.values())
    lo, hi = interval(receipt["weighted_energy_J"])
    score = (lo, hi) if objective == "FULL" else (no_temperature, no_temperature)
    return {"objective": objective,
            "planning_score_J": [str(score[0]), str(score[1])],
            "true_energy_J": [str(lo), str(hi)],
            "true_U_J": receipt["safe_upper_bound_J"],
            "candidate_sha256": identity["candidate_raw_sha256"],
            "input_sha256": sha(instance)}


def score_candidate(instance, candidate, legality, receipt, accuracy, seconds, objective):
    """Validate one complete receipt, return a separate immutable score value.

    The caller supplies an independently reconstructed legality record. Both
    objectives require the same complete continuous true-H safety receipt.
    The caller must also check its root clock after this calculation before
    using the returned score for an in-budget selection.
    """
    try:
        return _check(instance, candidate, legality, receipt, accuracy, seconds, objective)
    except ContractError:
        raise
    except (KeyError, TypeError, ValueError, ZeroDivisionError, AttributeError) as error:
        raise ContractError("MALFORMED_SCORING_INPUT:" + type(error).__name__) from error
