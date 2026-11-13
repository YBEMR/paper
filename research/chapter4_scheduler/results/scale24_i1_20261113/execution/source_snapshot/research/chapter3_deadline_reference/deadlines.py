"""Deadline arithmetic and explicitly requested inheritance; no construction."""

from copy import deepcopy
from fractions import Fraction

from .contract import ContractError, normalize, contract_hash, content_hash, exact
from .checker import check_timetable


def _checked(data, candidate, opp=None):
    check = check_timetable(data, candidate, required_opp=opp)
    if check["state"] != "TIME_STRUCTURAL_VALID":
        raise ContractError("TIME_CHECK_REQUIRED", check=check)
    return check


def _requests(data):
    return {s["id"]: {r["id"]: r for r in s["requests"]} for s in data["scenarios"]}


def _stamp(receipt):
    receipt["receipt_hash"] = content_hash({k: v for k, v in receipt.items() if k != "receipt_hash"})
    return receipt


def _verify_receipt(data, receipt):
    if not isinstance(receipt, dict):
        raise ContractError("INVALID_DEADLINE_RECEIPT")
    if (receipt.get("schema_version") != "deadline-reference-deadlines-v1" or
            receipt.get("contract_hash") != contract_hash(data) or
            receipt.get("receipt_hash") != content_hash({k: v for k, v in receipt.items()
                                                        if k != "receipt_hash"})):
        raise ContractError("DEADLINE_RECEIPT_IDENTITY_MISMATCH")
    requests = _requests(data)
    rows = receipt.get("requests")
    if not isinstance(rows, dict) or set(rows) != set(requests):
        raise ContractError("DEADLINE_REQUEST_COVERAGE")
    for sid, scene_requests in requests.items():
        if not isinstance(rows[sid], dict) or set(rows[sid]) != set(scene_requests):
            raise ContractError("DEADLINE_REQUEST_COVERAGE", scene=sid)
        for rid, req in scene_requests.items():
            row = rows[sid][rid]
            if not isinstance(row, dict) or set(row) != {
                    "release_ms", "deadline_ms", "relative_deadline_ms"}:
                raise ContractError("INVALID_DEADLINE_ROW", scene=sid, request=rid)
            release, due, relative = (exact(row[k]) for k in
                                      ("release_ms", "deadline_ms", "relative_deadline_ms"))
            if release != exact(req["release_ms"]) or relative <= 0 or due != release + relative:
                raise ContractError("INVALID_DEADLINE_ROW", scene=sid, request=rid)


def _make(data, h_check, beta, reference_topology_id):
    if data["derivation"]["axis"] not in ("BASE", "S2"):
        raise ContractError("DERIVED_DEADLINES_MUST_BE_INHERITED")
    if reference_topology_id != data["topology_id"]:
        raise ContractError("REFERENCE_TOPOLOGY_MISMATCH")
    beta = exact(beta)
    if beta < 1:
        raise ContractError("BETA_BELOW_ONE")
    rows, anchor = {}, {}
    for sid, reqs in _requests(data).items():
        rows[sid], anchor[sid] = {}, {}
        for rid, req in reqs.items():
            release = exact(req["release_ms"])
            finish = exact(h_check["completions_ms"][sid][rid])
            if finish <= release:
                raise ContractError("NONPOSITIVE_H_RESPONSE", scene=sid, request=rid)
            relative = beta * (finish - release)
            rows[sid][rid] = {"release_ms": str(release), "deadline_ms": str(release + relative),
                              "relative_deadline_ms": str(relative)}
            anchor[sid][rid] = str(finish)
    origin = {"contract_hash": contract_hash(data), "h_completions_ms": anchor,
              "h_timetable_hash": h_check["timetable_hash"], "beta": str(beta),
              "reference_topology_id": reference_topology_id}
    return _stamp({"schema_version": "deadline-reference-deadlines-v1",
                   "contract_hash": contract_hash(data), "beta": str(beta),
                   "reference_topology_id": reference_topology_id,
                   "deadline_origin_hash": content_hash(origin), "origin": origin,
                   "parent_receipt_hash": None, "request_sources": None, "requests": rows})


def make_deadlines(data, h_candidate, *, beta, reference_topology_id):
    """Create base/S2 deadlines from a structurally legal H timetable.

    This does not itself certify that H was produced by the deterministic rule.
    diagnose requires the bundle's mapping identity and all three timetables.
    """
    data = normalize(data)
    return _make(data, _checked(data, h_candidate, "H"), beta, reference_topology_id)


def _compare(data, check, receipt):
    _verify_receipt(data, receipt)
    slacks = {s: {r: str(exact(row["deadline_ms"]) - exact(check["completions_ms"][s][r]))
                  for r, row in reqs.items()} for s, reqs in receipt["requests"].items()}
    scene_pass = {s: all(exact(v) >= 0 for v in row.values()) for s, row in slacks.items()}
    return {"all_on_time": all(scene_pass.values()), "scene_on_time": scene_pass,
            "slack_ms": slacks, "check": check,
            "thermal_status": "NOT_EVALUATED", "energy_status": "NOT_EVALUATED"}


def compare_deadlines(data, candidate, receipt):
    """A missed deadline in a derived condition is not a construction error."""
    data = normalize(data)
    return _compare(data, _checked(data, candidate), receipt)


def diagnose(data, bundle, *, betas, reference_topology_id):
    """Evaluate supplied H/M/L tables for explicit beta values; no replanning."""
    data = normalize(data)
    if (not isinstance(bundle, dict) or bundle.get("contract_hash") != contract_hash(data) or
            set(bundle.get("timetables", {})) != {"H", "M", "L"}):
        raise ContractError("REFERENCE_BUNDLE_IDENTITY_MISMATCH")
    if not isinstance(betas, (list, tuple)) or not betas:
        raise ContractError("EXPLICIT_BETAS_REQUIRED")
    beta_values = [exact(v) for v in betas]
    if len(set(beta_values)) != len(beta_values):
        raise ContractError("DUPLICATE_BETA")
    checks = {opp: _checked(data, bundle["timetables"][opp], opp) for opp in ("H", "M", "L")}
    mapping = checks["H"]["shared_deployment"]
    if any(checks[opp]["shared_deployment"] != mapping for opp in ("M", "L")):
        raise ContractError("REFERENCE_MAPPING_MISMATCH")
    record = bundle.get("mapping_record", {})
    if (not isinstance(record.get("mapping"), dict) or
            any(record["mapping"].get(s) != u for s, u in mapping.items()) or
            bundle.get("mapping_origin_hash") != content_hash(record)):
        raise ContractError("REFERENCE_MAPPING_IDENTITY_MISMATCH")
    ratios = {opp: {} for opp in ("M", "L")}
    for sid, reqs in _requests(data).items():
        for opp in ("M", "L"):
            ratios[opp][sid] = {}
        for rid, req in reqs.items():
            release = exact(req["release_ms"])
            base = exact(checks["H"]["completions_ms"][sid][rid]) - release
            if base <= 0:
                raise ContractError("NONPOSITIVE_H_RESPONSE", scene=sid, request=rid)
            for opp in ("M", "L"):
                ratios[opp][sid][rid] = str((exact(checks[opp]["completions_ms"][sid][rid]) - release) / base)
    by_beta = {}
    for beta in beta_values:
        receipt = _make(data, checks["H"], beta, reference_topology_id)
        by_beta[str(beta)] = {"deadlines": receipt,
                              "by_opp": {opp: _compare(data, checks[opp], receipt)
                                         for opp in ("H", "M", "L")}}
    return {"state": "DEADLINE_DIAGNOSTICS_COMPLETE", "contract_hash": contract_hash(data),
            "thresholds": {opp: str(max(exact(v) for reqs in ratios[opp].values() for v in reqs.values()))
                           for opp in ("M", "L")},
            "per_request_ratios": ratios, "by_beta": by_beta,
            "beta_selected": None, "thermal_status": "NOT_EVALUATED", "energy_status": "NOT_EVALUATED"}


def inherit_deadlines(parent_data, parent_receipt, target_data, *, request_sources):
    """Copy deadlines with explicit provenance, never invoking the reference rule.

    This checks the deadline relation, not scientific correctness of a workload
    transformation (e.g. S3 work conservation must be checked by its generator).
    No random workload generator or transformation policy is supplied here.
    """
    parent, target = normalize(parent_data), normalize(target_data)
    _verify_receipt(parent, parent_receipt)
    axis = target["derivation"]["axis"]
    if axis not in ("S1", "S3", "S4", "S5", "S6", "S7", "E2"):
        raise ContractError("NOT_AN_INHERITANCE_AXIS")
    if target["derivation"]["parent_contract_hash"] != contract_hash(parent):
        raise ContractError("DEADLINE_PARENT_MISMATCH")
    for field in ("root_family_id", "platform", "execution_rules", "response_model", "start_grid_ms"):
        if parent[field] != target[field]:
            raise ContractError("INHERITANCE_PLATFORM_OR_FAMILY_CHANGED", field=field)
    reqs = _requests(target)
    if not isinstance(request_sources, dict) or set(request_sources) != set(reqs):
        raise ContractError("EXPLICIT_REQUEST_SOURCES_REQUIRED")
    original = _requests(parent)
    if axis == "S1":
        if not set(reqs).issubset(original):
            raise ContractError("S1_UNKNOWN_SCENARIO")
    elif set(reqs) != set(original):
        raise ContractError("INHERITANCE_SCENARIO_SET_CHANGED")
    for sid in reqs:
        if axis == "S7":
            if not set(original[sid]).issubset(reqs[sid]):
                raise ContractError("S7_ORIGINAL_REQUEST_REMOVED")
        elif set(reqs[sid]) != set(original[sid]):
            raise ContractError("INHERITANCE_REQUEST_SET_CHANGED", scene=sid)
    rows = {}
    for sid, scene_requests in reqs.items():
        if not isinstance(request_sources[sid], dict) or set(request_sources[sid]) != set(scene_requests):
            raise ContractError("EXPLICIT_REQUEST_SOURCES_REQUIRED", scene=sid)
        rows[sid] = {}
        for rid, req in scene_requests.items():
            source = request_sources[sid][rid]
            if not isinstance(source, dict) or set(source) != {"source_scene", "source_request", "policy"}:
                raise ContractError("INVALID_REQUEST_SOURCE")
            src_s, src_r, policy = (source[k] for k in ("source_scene", "source_request", "policy"))
            if src_s not in original or src_r not in original[src_s]:
                raise ContractError("UNKNOWN_SOURCE_REQUEST")
            existing = sid in original and rid in original[sid]
            if existing or axis != "S7":
                if not existing or (src_s, src_r, policy) != (sid, rid, "absolute"):
                    raise ContractError("ORIGINAL_REQUEST_DEADLINE_MUST_BE_PRESERVED")
                if exact(req["release_ms"]) != exact(original[sid][rid]["release_ms"]):
                    raise ContractError("ORIGINAL_RELEASE_CHANGED")
                rows[sid][rid] = deepcopy(parent_receipt["requests"][sid][rid])
            else:
                if policy != "same_relative" or src_s != sid:
                    raise ContractError("EXPLICIT_NEW_REQUEST_RELATIVE_RULE_REQUIRED")
                relative = exact(parent_receipt["requests"][src_s][src_r]["relative_deadline_ms"])
                release = exact(req["release_ms"])
                rows[sid][rid] = {"release_ms": str(release), "relative_deadline_ms": str(relative),
                                  "deadline_ms": str(release + relative)}
    receipt = {"schema_version": "deadline-reference-deadlines-v1",
               "contract_hash": contract_hash(target), "beta": parent_receipt["beta"],
               "reference_topology_id": parent_receipt["reference_topology_id"],
               "deadline_origin_hash": parent_receipt["deadline_origin_hash"],
               "origin": deepcopy(parent_receipt["origin"]),
               "parent_receipt_hash": parent_receipt["receipt_hash"],
               "request_sources": deepcopy(request_sources), "requests": rows}
    return _stamp(receipt)


def counts(data):
    """Report actual instances separately from shared identities and requests."""
    data = normalize(data)
    return {s["id"]: {
        "fixed_stage_count": len({j["shared_stage_id"] for j in s["stage_instances"]}),
        "stage_instance_count": len(s["stage_instances"]), "requests": len(s["requests"]),
        "work_units": str(sum((exact(data["stage_profiles"][j["shared_stage_id"]]["work_units"])
                               for j in s["stage_instances"]), Fraction(0)))}
        for s in data["scenarios"]}
