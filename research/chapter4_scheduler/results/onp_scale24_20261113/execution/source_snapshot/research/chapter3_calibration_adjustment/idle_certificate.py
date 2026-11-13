"""Exact boundary arithmetic for the original four-node all-idle-L model.

This is not a thermal integrator or a schedule-safety certificate.  The frozen
source bytes are verified independently of the caller-supplied digest.  Changed
physics require a new review; they cannot reuse this source-specific receipt.
"""

from fractions import Fraction
import hashlib
import json
from pathlib import Path

from research.chapter3_deadline_reference.contract import ContractError, exact, content_hash


SOURCE_SHA256 = "615be096bfbcb3e7c53ba9b0810d888264d48adbc428f1f7d2f94a5c6a29a4fe"
SOURCE_PATH = Path(__file__).resolve().parents[1] / "chapter3_experiments/config_v01.json"
POLICY = "auto_low_immediate_v1"


def _require(condition, reason):
    if not condition:
        raise ContractError(reason)


def make_idle_certificate(config, *, source_sha256, policy, lower_C, upper_C):
    """Bind the proved [20,80]^4 box to exact original parameters and auto-L."""
    payload = SOURCE_PATH.read_bytes()
    _require(hashlib.sha256(payload).hexdigest() == SOURCE_SHA256 and
             source_sha256 == SOURCE_SHA256, "IDLE_FROZEN_SOURCE_MISMATCH")
    archived = json.loads(payload.decode("utf-8"))
    _require(config == archived and content_hash(config) == content_hash(archived),
             "IDLE_PARAMETER_CONTENT_MISMATCH")
    _require(policy == POLICY, "IDLE_AUTO_LOW_POLICY_REQUIRED")
    lower, upper = exact(lower_C), exact(upper_C)
    _require(lower == 20 and upper == 80, "IDLE_DECLARED_BOX_MISMATCH")
    platform = config["platform"]
    nodes = platform["node_order"]
    _require(nodes == ["CPU1", "CPU2", "GPU0", "NPU0"], "IDLE_NODE_ORDER_MISMATCH")
    valid = list(map(exact, platform["power_model_temperature_range_degC"]))
    _require(valid[0] <= lower < upper <= valid[1], "IDLE_BOX_OUTSIDE_POWER_RANGE")
    ambient, reference = (exact(platform[k]) for k in
                          ("ambient_temperature_degC", "reference_temperature_degC"))
    c = list(map(exact, platform["heat_capacity_J_per_K"]))
    g = [list(map(exact, row)) for row in platform["conductance_W_per_K"]]
    _require(len(c) == len(g) == len(nodes) and all(v > 0 for v in c), "IDLE_CAPACITY_INVALID")
    _require(all(len(row) == len(nodes) for row in g), "IDLE_MATRIX_DIMENSION")
    _require(all(g[i][j] <= 0 for i in range(4) for j in range(4) if i != j),
             "IDLE_NONCOOPERATIVE_COUPLING")
    _require(all(g[i][j] == g[j][i] for i in range(4) for j in range(4)),
             "IDLE_CONDUCTANCE_ASYMMETRY")
    gsum = list(map(sum, g))
    _require(all(v > 0 for v in gsum), "IDLE_NONPOSITIVE_GROUNDING")
    b = [Fraction(0)] * 4
    k = [Fraction(0)] * 4
    units = {u["id"]: u for u in platform["units"]}
    base_groups = {}
    for domain_id, domain in platform["domains"].items():
        baseline = exact(domain["baseline_W"]["L"])
        weights = list(map(exact, domain["baseline_heat_distribution"]))
        _require(len(weights) == 4 and sum(weights) == 1 and all(w >= 0 for w in weights),
                 "IDLE_BASELINE_DISTRIBUTION_INVALID")
        base_groups[domain_id] = str(baseline)
        for i, weight in enumerate(weights):
            b[i] += baseline * weight
        for unit_id in domain["unit_ids"]:
            k[nodes.index(units[unit_id]["thermal_node_id"])] += exact(
                domain["local_temperature_slope_W_per_K"]["L"])
    _require(all(exact(v) == 0 for v in platform["external_common_heat_distribution"]),
             "IDLE_EXTERNAL_HEAT_NOT_ZERO")
    low_power = [b[i] + k[i] * (lower - reference) for i in range(4)]
    low_flow = [-gsum[i] * (lower - ambient) + low_power[i] for i in range(4)]
    high_flow = [-gsum[i] * (upper - ambient) + b[i] + k[i] * (upper - reference)
                 for i in range(4)]
    _require(all(p >= 0 for p in low_power), "IDLE_NEGATIVE_NODE_POWER")
    _require(all(v >= 0 for v in low_flow) and all(v <= 0 for v in high_flow),
             "IDLE_BOX_NOT_INVARIANT")
    result = {
        "schema_version": "four-node-idle-box-certificate-v1",
        "state": "ALGEBRAIC_POSITIVE_INVARIANCE_VERIFIED",
        "source_sha256": SOURCE_SHA256,
        "source_parameter_content_hash": content_hash(config),
        "physical_platform_hash": content_hash(platform),
        "control_policy": policy,
        "policy_assumptions": {"all_domains_idle": True, "domain_opp": "L",
                               "lowering_delay_ms": "0", "switch_energy_J": "0",
                               "source_legacy_hold_field_is_not_control_policy": True},
        "lower_temperature_C": str(lower), "upper_temperature_C": str(upper),
        "node_order": list(nodes),
        "heat_capacity_J_per_K": list(map(str, c)),
        "conductance_row_sums_W_per_K": list(map(str, gsum)),
        "baseline_by_group_W": base_groups,
        "baseline_by_node_W": list(map(str, b)),
        "local_slope_W_per_K": list(map(str, k)),
        "lower_face_min_net_heat_W": list(map(str, low_flow)),
        "upper_face_max_net_heat_W": list(map(str, high_flow)),
        "external_common_power_W": str(exact(platform["external_common_power_W"])),
        "external_injected_heat_W": "0",
        "conditions": ["all work completed", "no subsequent new work", "T(W) lies in the declared box",
                       "original parameters and explicit auto-L policy unchanged"],
        "thermal_integrations": 0, "schedule_safe_certified": False,
        "energy_after_window_included": False,
    }
    result["certificate_hash"] = content_hash(result)
    return result


def validate_idle_certificate(certificate, config, *, source_sha256, policy, lower_C, upper_C):
    """A cached certificate is usable only for exactly the same proved model."""
    expected = make_idle_certificate(config, source_sha256=source_sha256, policy=policy,
                                     lower_C=lower_C, upper_C=upper_C)
    _require(certificate == expected, "IDLE_CERTIFICATE_DRIFT")
    return True
