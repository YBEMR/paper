"""Fail-closed classification of one reported true-H scheduling violation.

This is an exact certificate check of the reported violation, not a schedule
validator, scheduler, thermal evaluator, or source of SAFE claims.  Inputs must
also be bound to the frozen truth/candidate identities by the caller.
"""
from fractions import Fraction

from h02_pair_preflight.common import candidate_identity, copy, exact, require


CERTIFICATE_REASONS = frozenset({
    "BEFORE_RELEASE", "WINDOW_EXCEEDED", "REQUEST_DEADLINE_EXCEEDED",
    "DEPENDENCY_VIOLATION", "EXECUTION_UNIT_OVERLAP", "FREQUENCY_DOMAIN_CONFLICT",
})


def _indexed(items, name):
    require(isinstance(items, list) and items, "MISSING_" + name)
    result = {}
    for item in items:
        require(isinstance(item, dict), "MALFORMED_" + name)
        identity = item["id"]
        require(isinstance(identity, str) and identity and identity not in result,
                "DUPLICATE_OR_INVALID_" + name)
        result[identity] = item
    return result


def _truth_rows(instance, candidate):
    require(instance["schema_version"] == "chapter3-input-v0.1", "TRUTH_SCHEMA")
    require(instance["response_variant"] == "H", "TRUTH_RESPONSE_NOT_H")
    if "settings" in instance:
        require(instance["settings"]["response_variant"] == "H", "TRUTH_SETTINGS_NOT_H")
    candidate_identity(instance, candidate)  # Strict coverage, raw schema and supported identities.
    window = exact(instance["window_ms"])
    require(window > 0, "INVALID_TRUTH_WINDOW")
    scenes = _indexed(instance["scenarios"], "SCENE")
    units = _indexed(instance["platform"]["units"], "UNIT")
    domains = instance["platform"]["domains"]
    require(isinstance(domains, dict) and domains, "INVALID_TRUTH_DOMAINS")
    rows, dependencies = {}, set()
    for scene_id, scene in scenes.items():
        requests = _indexed(scene["requests"], "REQUEST")
        stages = _indexed(scene["stage_instances"], "STAGE")
        for request_id, request in requests.items():
            release, deadline = exact(request["release_ms"]), exact(request["deadline_ms"])
            require(0 <= release <= deadline <= window, "INVALID_TRUTH_REQUEST_WINDOW")
            members = request["stage_instance_ids"]
            require(isinstance(members, list) and members and len(members) == len(set(members)) and
                    set(members) == {sid for sid, stage in stages.items()
                                     if stage["request_id"] == request_id},
                    "INVALID_TRUTH_REQUEST_MEMBERSHIP")
        for supplied in candidate["scenes"][scene_id]:
            stage_id = supplied["stage_id"]
            require(stage_id not in rows, "DUPLICATE_GLOBAL_STAGE_ID")
            stage = stages[stage_id]
            require(stage["request_id"] in requests, "UNKNOWN_TRUTH_REQUEST")
            request = requests[stage["request_id"]]
            matches = [mode for mode in instance["stage_modes"][stage["shared_stage_id"]]
                       if mode["unit_id"] == supplied["unit"] and mode["opp_id"] == supplied["opp"]]
            require(len(matches) == 1, "AMBIGUOUS_TRUTH_MODE")
            mode = matches[0]
            unit = units[supplied["unit"]]
            domain = unit["domain_id"]
            require(mode["domain_id"] == domain and domain in domains and
                    supplied["unit"] in domains[domain]["unit_ids"] and
                    supplied["opp"] in domains[domain]["opps"], "TRUTH_MODE_PLATFORM_MISMATCH")
            start = exact(supplied["start_ms"])
            duration, power = exact(mode["duration_ms"]), exact(mode["activity_power_W"])
            require(duration > 0 and power >= 0, "INVALID_TRUTH_MODE_COST")
            rows[stage_id] = dict(scene=scene_id, unit=supplied["unit"], opp=supplied["opp"],
                                  domain=domain, request=stage["request_id"], start=start,
                                  end=start + duration, release=exact(request["release_ms"]),
                                  deadline=exact(request["deadline_ms"]))
        require(isinstance(scene["dependencies"], list), "INVALID_TRUTH_DEPENDENCIES")
        for edge in scene["dependencies"]:
            require(isinstance(edge, list) and len(edge) == 2 and
                    all(isinstance(sid, str) and sid in stages for sid in edge),
                    "INVALID_TRUTH_DEPENDENCY")
            dependencies.add(tuple(edge))
    return rows, dependencies, window


def _certificate(reason, details, rows, dependencies, window):
    if reason in {"BEFORE_RELEASE", "WINDOW_EXCEEDED", "REQUEST_DEADLINE_EXCEEDED"}:
        keys = {"stage", "request", "finish_ms", "deadline_ms"} if reason == "REQUEST_DEADLINE_EXCEEDED" else {"stage"}
        require(set(details) == keys, "VIOLATION_DETAIL_FIELDS")
        stage_id = details["stage"]
        require(isinstance(stage_id, str) and stage_id in rows, "UNKNOWN_WITNESS_STAGE")
        row = rows[stage_id]
        if reason == "BEFORE_RELEASE":
            require(row["start"] < row["release"], "FALSE_RELEASE_WITNESS")
            return dict(stage=stage_id, start_ms=str(row["start"]), release_ms=str(row["release"]))
        if reason == "WINDOW_EXCEEDED":
            require(row["end"] > window, "FALSE_WINDOW_WITNESS")
            return dict(stage=stage_id, finish_ms=str(row["end"]), window_ms=str(window))
        require(details["request"] == row["request"] and
                exact(details["finish_ms"]) == row["end"] and
                exact(details["deadline_ms"]) == row["deadline"] and
                row["end"] > row["deadline"], "FALSE_DEADLINE_WITNESS")
        return dict(stage=stage_id, request=row["request"], finish_ms=str(row["end"]),
                    deadline_ms=str(row["deadline"]))
    if reason == "DEPENDENCY_VIOLATION":
        require(set(details) == {"predecessor", "successor"}, "VIOLATION_DETAIL_FIELDS")
        edge = (details["predecessor"], details["successor"])
        require(all(isinstance(sid, str) and sid in rows for sid in edge) and
                edge in dependencies and rows[edge[0]]["scene"] == rows[edge[1]]["scene"],
                "UNKNOWN_WITNESS_DEPENDENCY")
        predecessor, successor = (rows[sid] for sid in edge)
        require(predecessor["end"] > successor["start"], "FALSE_DEPENDENCY_WITNESS")
        return dict(predecessor=edge[0], successor=edge[1],
                    predecessor_finish_ms=str(predecessor["end"]),
                    successor_start_ms=str(successor["start"]))
    require(set(details) == {"stages"}, "VIOLATION_DETAIL_FIELDS")
    ids = details["stages"]
    require(isinstance(ids, list) and len(ids) == 2 and ids[0] != ids[1] and
            all(isinstance(sid, str) and sid in rows for sid in ids), "INVALID_WITNESS_PAIR")
    left, right = (rows[sid] for sid in ids)
    overlap_start, overlap_end = max(left["start"], right["start"]), min(left["end"], right["end"])
    require(left["scene"] == right["scene"] and overlap_start < overlap_end,
            "FALSE_OVERLAP_WITNESS")
    if reason == "EXECUTION_UNIT_OVERLAP":
        require(left["unit"] == right["unit"], "FALSE_UNIT_WITNESS")
    else:
        require(left["unit"] != right["unit"] and left["domain"] == right["domain"] and
                left["opp"] != right["opp"], "FALSE_FREQUENCY_DOMAIN_WITNESS")
    return dict(stages=copy(ids), scene=left["scene"], overlap_ms=[str(overlap_start), str(overlap_end)])


def classify_invalid_schedule(instance, candidate, legal):
    """Classify only a bound INVALID_SCHEDULE receipt using an exact witness.

    Unknown, input/policy/schema/accounting and ambiguous failures fail closed.
    Grid/shared-deployment identities are already enforced before this layer;
    domain-only reasons lack a specific Stage pair and are not accepted here.
    """
    reason = legal.get("reason") if isinstance(legal, dict) else None
    result = dict(audit_status="INPUT_OR_INTERFACE_ERROR", reason=reason or "INVALID_REASON_MISSING",
                  certificate_checked=False,
                  details=dict(reported_reason=reason,
                               reported_details=copy(legal.get("details")) if isinstance(legal, dict) else None))
    try:
        require(isinstance(legal, dict) and legal.get("state") == "INVALID_SCHEDULE" and
                legal.get("thermal_status") == "NOT_EVALUATED" and
                legal.get("energy_status") == "NOT_EVALUATED", "INVALID_LEGALITY_ENVELOPE")
        details = legal.get("details")
        require(isinstance(reason, str) and isinstance(details, dict), "INVALID_REASON_OR_DETAILS")
        require(reason in CERTIFICATE_REASONS,
                "INPUT_POLICY_INTERFACE_OR_UNCERTIFIED_REASON")
        rows, dependencies, window = _truth_rows(instance, candidate)
        witness = _certificate(reason, details, rows, dependencies, window)
        result.update(audit_status="TRUE_H_INVALID", certificate_checked=True)
        result["details"].update(classification_explanation="EXACT_REPORTED_VIOLATION_CHECKED", witness=witness)
    except (ValueError, TypeError, KeyError, ZeroDivisionError, OverflowError) as error:
        result["details"]["classification_explanation"] = type(error).__name__ + ":" + str(error)
    return result
