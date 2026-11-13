"""Deadline-bound comparison windows; never schedule, integrate, or export inputs.

Evidence members need only ``workload`` and ``deadlines``.  The explicit baseline
also supplies the archived H reference.  New candidate completion times are not
window inputs.  Window receipts stay separate from the old time-only bundles.
"""

from research.chapter3_deadline_reference.contract import (
    ContractError, content_hash, exact)
from research.chapter3_deadline_reference.deadlines import (
    _verify_receipt, make_deadlines, inherit_deadlines)
from research.chapter3_workload_calibration.generator import (
    validate_bundle, validate_transform, request_sources, subset)

from .transforms import validated_base_h, validate_adjustment


def _require(condition, reason):
    if not condition:
        raise ContractError(reason)


def ceil_grid_ms(value):
    """Exact upward alignment to the declared 5 ms start grid."""
    value = exact(value)
    _require(value >= 0, "WINDOW_NEGATIVE_TIME")
    return str(-(-value // 5) * 5)


def _baseline_receipt(baseline, beta):
    _require(isinstance(baseline, dict), "WINDOW_BASELINE_REQUIRED")
    check = validated_base_h(baseline)
    data = baseline["workload"]["time_contract"]
    key = str(exact(beta))
    _require(key in baseline.get("deadlines", {}), "WINDOW_EXPLICIT_BETA_NOT_AVAILABLE")
    receipt = baseline["deadlines"][key]
    _verify_receipt(data, receipt)
    expected = make_deadlines(data, baseline["reference"]["timetables"]["H"],
                              beta=beta, reference_topology_id=data["topology_id"])
    _require(receipt == expected, "WINDOW_BASELINE_DEADLINE_PROVENANCE")
    return receipt, check


def _member_receipt(evidence, baseline, base_receipt, beta, group_kind):
    _require(isinstance(evidence, dict) and isinstance(evidence.get("workload"), dict),
             "WINDOW_MEMBER_EVIDENCE_REQUIRED")
    bundle, parent = evidence["workload"], baseline["workload"]
    validate_bundle(bundle)
    data, original = bundle["time_contract"], parent["time_contract"]
    _require(data["root_family_id"] == original["root_family_id"] and
             bundle["provenance"]["scale"] == parent["provenance"]["scale"] and
             bundle["physical_platform"] == parent["physical_platform"],
             "WINDOW_MIXED_ROOT_SCALE_OR_PHYSICS")
    key = str(exact(beta))
    _require(key in evidence.get("deadlines", {}), "WINDOW_MEMBER_BETA_NOT_AVAILABLE")
    receipt = evidence["deadlines"][key]
    _verify_receipt(data, receipt)
    _require(exact(receipt["beta"]) == exact(beta), "WINDOW_MEMBER_BETA_MISMATCH")
    if bundle == parent:
        _require(receipt == base_receipt, "WINDOW_BASE_RECEIPT_MISMATCH")
        return receipt
    axis = data["derivation"]["axis"]
    _require(axis == group_kind, "WINDOW_WRONG_DERIVATION_AXIS")
    rule = (bundle.get("transform") or {}).get("rule")
    if rule in ("branch_multi_v1", "staggered_half_base_H_v1"):
        validate_adjustment(baseline, bundle)
    else:
        validate_transform(parent, bundle)
    expected = inherit_deadlines(original, base_receipt, data,
                                 request_sources=request_sources(parent, bundle))
    _require(receipt == expected, "WINDOW_MEMBER_DEADLINE_PROVENANCE")
    return receipt


def make_window_receipt(group_id, group_kind, members, *, beta, baseline):
    """Create an unapproved-for-execution, standalone finite-window record.

    S1 requires exactly the 1/2/4/6/8 projections of one eight-scene baseline.
    S7 requires keys ``single``, ``synchronous``, ``staggered``.  S2 has one
    baseline at one scale.  Other axes permit the explicit base and/or derived
    conditions, all inheriting the same original deadlines.  The original
    single-diamond baseline need not be a fourth S4 comparison method.
    """
    _require(isinstance(group_id, str) and bool(group_id.strip()), "WINDOW_GROUP_ID_REQUIRED")
    _require(group_kind in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "E2"),
             "WINDOW_UNSUPPORTED_GROUP")
    _require(isinstance(members, dict) and bool(members) and
             all(isinstance(k, str) and k.strip() for k in members), "WINDOW_MEMBERS_REQUIRED")
    base_receipt, h_check = _baseline_receipt(baseline, beta)
    parent = baseline["workload"]
    receipts = {name: _member_receipt(value, baseline, base_receipt, beta, group_kind)
                for name, value in members.items()}

    if group_kind == "S1":
        _require(len(parent["time_contract"]["scenarios"]) == 8 and
                 set(members) == {"1", "2", "4", "6", "8"}, "WINDOW_S1_COMPLETE_GROUP_REQUIRED")
        for count, member in members.items():
            _require(member["workload"] == subset(parent, int(count)), "WINDOW_S1_NOT_ORIGINAL_PREFIX")
    elif group_kind == "S2":
        _require(len(members) == 1 and next(iter(members.values()))["workload"] == parent,
                 "WINDOW_S2_SINGLE_SCALE_BASE_REQUIRED")
    elif group_kind == "S7":
        _require(set(members) == {"single", "synchronous", "staggered"},
                 "WINDOW_S7_THREE_ROLES_REQUIRED")
        _require(members["single"]["workload"] == parent, "WINDOW_S7_SINGLE_BASE_REQUIRED")
        sync, staggered = members["synchronous"]["workload"], members["staggered"]["workload"]
        _require(sync["time_contract"]["derivation"]["axis"] == "S7" and
                 (sync.get("transform") or {}).get("rule") != "staggered_half_base_H_v1",
                 "WINDOW_S7_SYNCHRONOUS_REQUIRED")
        validate_transform(parent, sync)
        _require((staggered.get("transform") or {}).get("rule") == "staggered_half_base_H_v1",
                 "WINDOW_S7_STAGGERED_REQUIRED")
        validate_adjustment(baseline, staggered)

    # S1 uses all eight original scenes even for smaller projected members.
    # For common-deadline axes this baseline anchor also makes group coverage
    # independent of whether the original branch_join is a tested condition.
    considered = [base_receipt] + list(receipts.values())
    latest = max(exact(row["deadline_ms"]) for receipt in considered
                 for requests in receipt["requests"].values() for row in requests.values())
    window = ceil_grid_ms(latest)
    result = {
        "schema_version": "calibration-adjustment-window-v1",
        "state": "WINDOW_RULE_APPLIED_NOT_FORMAL_EXECUTION_AUTHORIZATION",
        "group_id": group_id, "group_kind": group_kind,
        "root_family_id": parent["time_contract"]["root_family_id"],
        "scale": parent["provenance"]["scale"], "beta": str(exact(beta)),
        "grid_ms": "5", "window_ms": window, "latest_deadline_ms": str(latest),
        "baseline_bundle_hash": parent["bundle_hash"],
        "baseline_contract_hash": parent["contract_hash"],
        "baseline_deadline_receipt_hash": base_receipt["receipt_hash"],
        "baseline_h_timetable_hash": h_check["timetable_hash"],
        "deadline_origin_hash": base_receipt["deadline_origin_hash"],
        "members": {name: {
            "bundle_hash": members[name]["workload"]["bundle_hash"],
            "contract_hash": members[name]["workload"]["contract_hash"],
            "deadline_receipt_hash": receipt["receipt_hash"],
            "window_ms": window,
        } for name, receipt in sorted(receipts.items())},
        "scope": "FINITE_ENERGY_WINDOW_NO_EXTRA_COOLING_TAIL_SUBJECT_TO_IDLE_CERTIFICATE",
        "thermal_status": "NOT_EVALUATED", "energy_status": "NOT_EVALUATED",
        "formal_input_exported": False,
    }
    result["receipt_hash"] = content_hash(result)
    return result


def validate_window_receipt(receipt, group_id, group_kind, members, *, beta, baseline):
    """Recompute deadline provenance, group membership, rounding, and digest."""
    expected = make_window_receipt(group_id, group_kind, members, beta=beta, baseline=baseline)
    _require(receipt == expected, "WINDOW_RECEIPT_DRIFT")
    return True
