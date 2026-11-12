"""Exact, deadline-free input contract for the independent reference scheduler.

Only standard-library code is used.  This module does not create workloads or
import a planner, a power model, or a thermal evaluator.  ``normalize`` returns
a new canonical object; it never supplies missing scientific parameters.
"""

from collections import deque
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import math


SCHEMA_VERSION = "deadline-reference-input-v1"
RESPONSE_MODEL = "stage_affine_inverse_v1"
OPPS = ("L", "M", "H")
UNIT_DOMAINS = {"CPU1": "CPU", "CPU2": "CPU", "GPU0": "GPU", "NPU0": "NPU"}
AXES = {"BASE", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "E2"}


class ContractError(ValueError):
    """A rejected explicit input, not a scheduling infeasibility result."""

    def __init__(self, code, **details):
        self.code = code
        self.details = details
        super().__init__(code)


def _require(condition, code, **details):
    if not condition:
        raise ContractError(code, **details)


def exact(value):
    """Accept JSON strings/integers or an already exact Fraction, never float."""
    if isinstance(value, bool) or not isinstance(value, (str, int, Fraction)):
        raise ContractError("EXACT_SCALAR_REQUIRED", value_type=type(value).__name__)
    try:
        return Fraction(value)
    except (ValueError, TypeError, ZeroDivisionError, OverflowError) as error:
        raise ContractError("INVALID_EXACT_SCALAR", value=str(value)) from error


def _keys(value, expected, field):
    _require(isinstance(value, dict), "OBJECT_REQUIRED", field=field)
    _require(set(value) == set(expected), "OBJECT_FIELDS", field=field,
             missing=sorted(set(expected) - set(value)),
             unexpected=sorted(str(k) for k in set(value) - set(expected)))


def _id(value, field):
    _require(isinstance(value, str) and bool(value.strip()), "NONEMPTY_ID_REQUIRED", field=field)
    return value


def _list(value, field, *, nonempty=False):
    _require(isinstance(value, list), "LIST_REQUIRED", field=field)
    _require(not nonempty or bool(value), "EMPTY_LIST", field=field)
    return value


def _ids(values, field, *, nonempty=False):
    values = [_id(value, field) for value in _list(values, field, nonempty=nonempty)]
    _require(len(values) == len(set(values)), "DUPLICATE_ID", field=field)
    return sorted(values)


def _positive(value, field):
    number = exact(value)
    _require(number > 0, "NONPOSITIVE_VALUE", field=field)
    return str(number)


def _json_metadata(value, field="context"):
    """Check JSON without coercing non-string keys or accepting NaN/infinity."""
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        _require(math.isfinite(value), "NONFINITE_METADATA", field=field)
        return
    if isinstance(value, list):
        for item in value:
            _json_metadata(item, field)
        return
    if isinstance(value, dict):
        _require(all(isinstance(key, str) for key in value), "METADATA_KEY_TYPE", field=field)
        for key, item in value.items():
            _json_metadata(item, field + "." + key)
        return
    raise ContractError("NON_JSON_METADATA", field=field, value_type=type(value).__name__)


def content_hash(obj):
    """Hash a JSON-compatible object; callers choose its canonical list order."""
    _json_metadata(obj, "hash_payload")
    payload = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _execution_rules(value):
    booleans = {
        "preemption": False, "migration": False, "in_stage_opp_change": False,
        "idle_holds_last_opp": False, "switch_only_when_domain_empty": True,
    }
    zeros = ("idle_delay_ms", "extra_switch_time_ms", "extra_switch_energy_J",
             "extra_transfer_time_ms", "extra_transfer_energy_J",
             "extra_handoff_time_ms", "extra_handoff_energy_J")
    literals = {"idle_policy": "auto_low_immediate_v1", "interval_convention": "[start,end)"}
    _keys(value, set(booleans) | set(zeros) | set(literals), "execution_rules")
    result = {}
    for key, expected in booleans.items():
        _require(value[key] is expected, "UNSUPPORTED_EXECUTION_RULE", field=key)
        result[key] = expected
    for key, expected in literals.items():
        _require(value[key] == expected, "UNSUPPORTED_EXECUTION_RULE", field=key)
        result[key] = expected
    for key in zeros:
        _require(exact(value[key]) == 0, "UNSUPPORTED_NONZERO_OVERHEAD", field=key)
        result[key] = "0"
    return result


def _platform(value):
    _keys(value, ("units", "domains"), "platform")
    units = []
    for item in _list(value["units"], "platform.units", nonempty=True):
        _keys(item, ("id", "domain_id"), "platform.unit")
        uid = _id(item["id"], "unit.id")
        _require(uid in UNIT_DOMAINS and item["domain_id"] == UNIT_DOMAINS[uid],
                 "UNIT_DOMAIN_MISMATCH", unit=uid)
        units.append({"id": uid, "domain_id": item["domain_id"]})
    _require(len(units) == 4 and {u["id"] for u in units} == set(UNIT_DOMAINS),
             "FOUR_UNIT_PLATFORM_REQUIRED")
    _keys(value["domains"], set(UNIT_DOMAINS.values()), "platform.domains")
    domains = {}
    for name in sorted(value["domains"]):
        domain = value["domains"][name]
        _keys(domain, ("reference_opp", "opps"), "domain." + name)
        _require(domain["reference_opp"] == "H", "REFERENCE_OPP_MUST_BE_H", domain=name)
        _keys(domain["opps"], OPPS, "opps." + name)
        opps = {}
        for opp in OPPS:
            _keys(domain["opps"][opp], ("frequency_GHz",), "opp." + name + "." + opp)
            opps[opp] = {"frequency_GHz": _positive(domain["opps"][opp]["frequency_GHz"],
                                                  name + "." + opp + ".frequency_GHz")}
        _require(exact(opps["L"]["frequency_GHz"]) < exact(opps["M"]["frequency_GHz"]) <
                 exact(opps["H"]["frequency_GHz"]), "OPPS_NOT_STRICTLY_ORDERED", domain=name)
        domains[name] = {"reference_opp": "H", "opps": opps}
    return {"units": sorted(units, key=lambda item: item["id"]), "domains": domains}


def _profiles(value):
    _require(isinstance(value, dict) and bool(value), "STAGE_PROFILES_REQUIRED")
    profiles = {}
    for shared_id, profile in value.items():
        _id(shared_id, "shared_stage_id")
        _keys(profile, ("work_units", "units"), "stage_profile." + shared_id)
        _require(isinstance(profile["units"], dict) and bool(profile["units"]),
                 "PROFILE_UNITS_REQUIRED", shared_stage_id=shared_id)
        unit_profiles = {}
        for uid, entry in profile["units"].items():
            _require(uid in UNIT_DOMAINS, "UNKNOWN_PROFILE_UNIT", unit=str(uid))
            _keys(entry, ("d_ref_ms", "alpha", "legal_opps"), "unit_profile." + shared_id + "." + uid)
            alpha = exact(entry["alpha"])
            _require(0 <= alpha <= 1, "ALPHA_OUT_OF_RANGE", shared_stage_id=shared_id, unit=uid)
            opps = _ids(entry["legal_opps"], "legal_opps", nonempty=True)
            _require(set(opps) == set(OPPS), "REFERENCE_OPP_MISSING_OR_EXTRA",
                     shared_stage_id=shared_id, unit=uid)
            unit_profiles[uid] = {"d_ref_ms": _positive(entry["d_ref_ms"], "d_ref_ms"),
                                  "alpha": str(alpha), "legal_opps": opps}
        profiles[shared_id] = {"work_units": _positive(profile["work_units"], "work_units"),
                               "units": {uid: unit_profiles[uid] for uid in sorted(unit_profiles)}}
    return {sid: profiles[sid] for sid in sorted(profiles)}


def _scene(value, profiles):
    _keys(value, ("id", "weight", "requests", "stage_instances", "dependencies"), "scenario")
    sid = _id(value["id"], "scenario.id")
    requests = {}
    for request in _list(value["requests"], "requests", nonempty=True):
        _keys(request, ("id", "release_ms", "stage_instance_ids"), "request")
        rid = _id(request["id"], "request.id")
        _require(rid not in requests, "DUPLICATE_REQUEST_ID", scenario=sid, request=rid)
        release = exact(request["release_ms"])
        _require(release >= 0, "NEGATIVE_RELEASE", request=rid)
        requests[rid] = {"id": rid, "release_ms": str(release),
                         "stage_instance_ids": _ids(request["stage_instance_ids"],
                                                    "request.stage_instance_ids", nonempty=True)}
    stages = {}
    for stage in _list(value["stage_instances"], "stage_instances", nonempty=True):
        _keys(stage, ("id", "request_id", "shared_stage_id", "legal_units"), "stage_instance")
        iid = _id(stage["id"], "stage.id")
        _require(iid not in stages, "DUPLICATE_STAGE_ID", scenario=sid, stage=iid)
        rid, shared_id = stage["request_id"], stage["shared_stage_id"]
        _id(rid, "stage.request_id")
        _id(shared_id, "stage.shared_stage_id")
        _require(rid in requests, "UNKNOWN_STAGE_REQUEST", stage=iid)
        _require(shared_id in profiles, "UNKNOWN_SHARED_STAGE", stage=iid)
        legal = _ids(stage["legal_units"], "stage.legal_units", nonempty=True)
        _require(set(legal) <= set(profiles[shared_id]["units"]), "ILLEGAL_OCCURRENCE_UNIT", stage=iid)
        stages[iid] = {"id": iid, "request_id": rid, "shared_stage_id": shared_id, "legal_units": legal}
    for rid, request in requests.items():
        expected = {iid for iid, stage in stages.items() if stage["request_id"] == rid}
        _require(set(request["stage_instance_ids"]) == expected, "REQUEST_STAGE_MEMBERSHIP", request=rid)
    edges, seen = [], set()
    for edge in _list(value["dependencies"], "dependencies"):
        _require(isinstance(edge, list) and len(edge) == 2, "INVALID_DEPENDENCY", scenario=sid)
        left, right = (_id(item, "dependency endpoint") for item in edge)
        _require(left in stages and right in stages, "UNKNOWN_DEPENDENCY_STAGE", scenario=sid)
        _require((left, right) not in seen, "DUPLICATE_DEPENDENCY", scenario=sid)
        seen.add((left, right))
        edges.append([left, right])
    indegree = {iid: 0 for iid in stages}
    successors = {iid: [] for iid in stages}
    for left, right in edges:
        indegree[right] += 1
        successors[left].append(right)
    queue = deque(iid for iid in stages if indegree[iid] == 0)
    visited = 0
    while queue:
        iid = queue.popleft()
        visited += 1
        for successor in successors[iid]:
            indegree[successor] -= 1
            if indegree[successor] == 0:
                queue.append(successor)
    _require(visited == len(stages), "CYCLIC_DAG", scenario=sid)
    return {"id": sid, "weight": _positive(value["weight"], "scenario.weight"),
            "requests": [requests[key] for key in sorted(requests)],
            "stage_instances": [stages[key] for key in sorted(stages)],
            "dependencies": sorted(edges)}


def shared_units(normalized):
    """Intersection across every occurrence, including request copies."""
    allowed = {}
    for scene in normalized["scenarios"]:
        for stage in scene["stage_instances"]:
            sid = stage["shared_stage_id"]
            if sid not in allowed:
                allowed[sid] = set(stage["legal_units"])
            else:
                allowed[sid].intersection_update(stage["legal_units"])
            _require(bool(allowed[sid]), "EMPTY_SHARED_UNIT_INTERSECTION", shared_stage_id=sid)
    return {sid: tuple(sorted(allowed[sid])) for sid in sorted(allowed)}


def normalize(data):
    """Validate the explicit time contract and return canonical rational data."""
    try:
        required = ("schema_version", "root_family_id", "variant_id", "topology_id", "derivation",
                    "start_grid_ms", "response_model", "context", "execution_rules", "platform",
                    "stage_profiles", "scenarios")
        _keys(data, required, "input")
        _require(data["schema_version"] == SCHEMA_VERSION, "UNSUPPORTED_SCHEMA")
        _require(data["response_model"] == RESPONSE_MODEL, "UNSUPPORTED_RESPONSE_MODEL")
        _require(exact(data["start_grid_ms"]) == 5, "START_GRID_MUST_BE_5_MS")
        derivation = data["derivation"]
        _keys(derivation, ("axis", "parent_contract_hash"), "derivation")
        axis, parent = derivation["axis"], derivation["parent_contract_hash"]
        _require(isinstance(axis, str) and axis in AXES, "UNSUPPORTED_DERIVATION_AXIS")
        if axis == "BASE":
            _require(parent is None, "BASE_PARENT_MUST_BE_NULL")
        else:
            _require(isinstance(parent, str) and len(parent) == 64 and
                     all(ch in "0123456789abcdef" for ch in parent), "PARENT_HASH_REQUIRED")
        _require(isinstance(data["context"], dict), "CONTEXT_OBJECT_REQUIRED")
        _json_metadata(data["context"])
        profiles = _profiles(data["stage_profiles"])
        scenes = [_scene(scene, profiles) for scene in _list(data["scenarios"], "scenarios", nonempty=True)]
        _require(len(scenes) == len({scene["id"] for scene in scenes}), "DUPLICATE_SCENARIO_ID")
        _require(sum((exact(scene["weight"]) for scene in scenes), Fraction(0)) == 1,
                 "SCENARIO_WEIGHTS_MUST_SUM_TO_ONE")
        result = {
            "schema_version": SCHEMA_VERSION,
            "root_family_id": _id(data["root_family_id"], "root_family_id"),
            "variant_id": _id(data["variant_id"], "variant_id"),
            "topology_id": _id(data["topology_id"], "topology_id"),
            "derivation": {"axis": axis, "parent_contract_hash": parent},
            "start_grid_ms": "5", "response_model": RESPONSE_MODEL,
            "context": deepcopy(data["context"]),
            "execution_rules": _execution_rules(data["execution_rules"]),
            "platform": _platform(data["platform"]),
            "stage_profiles": profiles,
            "scenarios": sorted(scenes, key=lambda scene: scene["id"]),
        }
        shared_units(result)
        return result
    except ContractError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as error:
        raise ContractError("MALFORMED_CONTRACT", error_type=type(error).__name__) from error


def contract_hash(data):
    return content_hash(normalize(data))


def duration(normalized, shared_id, unit_id, opp_id):
    """Planner-side response calculation; independent checker must not call it."""
    profile = normalized["stage_profiles"][shared_id]["units"][unit_id]
    domain = normalized["platform"]["domains"][UNIT_DOMAINS[unit_id]]
    reference = domain["opps"][domain["reference_opp"]]["frequency_GHz"]
    frequency = domain["opps"][opp_id]["frequency_GHz"]
    alpha = exact(profile["alpha"])
    return exact(profile["d_ref_ms"]) * (1 - alpha + alpha * exact(reference) / exact(frequency))
