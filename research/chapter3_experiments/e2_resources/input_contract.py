"""E2 exact input masks on one unchanged auto-L physical platform.

Only declared mapping availability changes. Expansion, hashes and idle-power
arithmetic are static checks; no candidate search or temperature propagation.
"""
from copy import deepcopy
from fractions import Fraction as F

from control_policy import AUTO_LOW_IMMEDIATE_V1, resolve_idle_policy, with_auto_low_idle
from h02_pair_preflight.common import ContractError, require, sha
from inputs import build_instance, load_config
from schedules import _power_segments

PROBLEM_IDS = ("resources_CPU__R1", "resources_CPU_GPU__R1",
               "resources_CPU_NPU__R1", "base__R1")
MASKS = {PROBLEM_IDS[0]: ("CPU",), PROBLEM_IDS[1]: ("CPU", "GPU"),
         PROBLEM_IDS[2]: ("CPU", "NPU"), PROBLEM_IDS[3]: ("CPU", "GPU", "NPU")}
BASE_ID = "base__R1"
LABEL_FIELDS = ("id", "condition_id", "experiment_group", "ablation_input")
ALLOWED_DIFFERENCE_PATHS = ("/id", "/condition_id", "/experiment_group",
                            "/ablation_input", "/settings/available_device_classes",
                            "/stage_modes/<shared_stage_id>")


def _reference_config(config=None):
    frozen = with_auto_low_idle(load_config())
    if config is not None:
        require(sha(with_auto_low_idle(config)) == sha(frozen), "CONFIG_DRIFT_FROM_FROZEN_SOURCE")
    return frozen


def prepare_inputs(config=None):
    """Return independent FULL-objective packets for the four existing masks.

    An explicit config must match the unchanged source config, after the sole
    already adopted auto-L control adapter. It is not an input-tuning hook.
    """
    frozen = _reference_config(config)
    return {pid: {"config": deepcopy(frozen),
                  "instance": build_instance(frozen, pid), "objective": "FULL"}
            for pid in PROBLEM_IDS}


def _same_physics_and_workload(base, instance):
    common = deepcopy(instance)
    for name in LABEL_FIELDS:
        common[name] = deepcopy(base[name])
    common["settings"]["available_device_classes"] = deepcopy(
        base["settings"]["available_device_classes"])
    common["stage_modes"] = deepcopy(base["stage_modes"])
    require(sha(common) == sha(base), "UNDECLARED_INPUT_DIFFERENCE")


def idle_power_evidence(instance):
    """Reconstruct the empty-activity fragment, without a schedule or heat solve.

    This verifies that the same power reconstruction used by later evaluation
    still charges every physical domain's L baseline, including masked units.
    Local leakage slopes remain present; no temperature energy is fabricated.
    """
    platform = instance["platform"]
    units = {unit["id"]: unit for unit in platform["units"]}
    scene = instance["scenarios"][0]
    segments = _power_segments(platform, scene, [], platform["node_order"], units,
                               platform["domains"], F(instance["window_ms"]),
                               idle_policy=AUTO_LOW_IMMEDIATE_V1)
    require(len(segments) == 1, "IDLE_FRAGMENT_NOT_SINGLE")
    seg = segments[0]
    require(seg["domain_opps"] == {d: "L" for d in platform["domains"]},
            "IDLE_DOMAIN_OPP_DRIFT")
    expected = {d: F(v["baseline_W"]["L"]) for d, v in platform["domains"].items()}
    actual = {d: F(v) for d, v in seg["baseline_by_power_group_W"].items()}
    require(actual == expected, "MASKED_DEVICE_IDLE_BASELINE_OMITTED")
    require(set(seg["local_leakage_slope_W_per_K"]) == set(platform["node_order"]),
            "MASKED_DEVICE_LEAKAGE_OMITTED")
    require(all(F(v) == 0 for v in seg["activity_by_node_W"].values()),
            "EMPTY_FRAGMENT_HAS_ACTIVITY")
    return {"kind": "EMPTY_ACTIVITY_POWER_ARITHMETIC_NOT_SCHEDULE_OR_THERMAL_RESULT",
            "domain_opps": seg["domain_opps"],
            "baseline_by_power_group_W": seg["baseline_by_power_group_W"],
            "baseline_by_node_W": seg["baseline_by_node_W"],
            "local_leakage_slope_W_per_K": seg["local_leakage_slope_W_per_K"],
            "baseline_window_energy_at_reference_J":
                str(sum(expected.values()) * F(instance["window_ms"]) / 1000),
            "external_common_window_energy_J":
                str(F(platform["external_common_power_W"]) * F(instance["window_ms"]) / 1000)}


def _validate(packets):
    require(isinstance(packets, dict) and set(packets) == set(PROBLEM_IDS),
            "EXACT_FOUR_RESOURCE_INPUTS_REQUIRED")
    frozen = _reference_config()
    expected = {pid: build_instance(frozen, pid) for pid in PROBLEM_IDS}
    base = packets[BASE_ID]["instance"]
    units = {u["id"]: u for u in expected[BASE_ID]["platform"]["units"]}
    report = {}
    for pid in PROBLEM_IDS:
        packet = packets[pid]
        require(isinstance(packet, dict) and set(packet) == {"config", "instance", "objective"},
                "PACKET_FIELD_SET")
        require(sha(packet["config"]) == sha(frozen), "CONFIG_DRIFT_FROM_FROZEN_SOURCE")
        require(packet["objective"] == "FULL", "RESOURCE_EXPERIMENT_REQUIRES_FULL_OBJECTIVE")
        instance = packet["instance"]
        require(instance["id"] == pid, "PROBLEM_ID_MISMATCH")
        require(resolve_idle_policy(instance) == AUTO_LOW_IMMEDIATE_V1, "IDLE_POLICY_DRIFT")
        require(tuple(instance["settings"]["available_device_classes"]) == MASKS[pid],
                "RESOURCE_MASK_DRIFT")
        require(instance["response_variant"] == "H" and instance["window_ms"] == "400" and
                instance["start_grid_ms"] == "5", "FIXED_RESPONSE_OR_TIMING_DRIFT")
        _same_physics_and_workload(base, instance)
        for name in LABEL_FIELDS:
            require(sha(instance[name]) == sha(expected[pid][name]), "GENERATED_LABEL_DRIFT:" + name)
        require(set(instance["stage_modes"]) == set(base["stage_modes"]),
                "STAGE_MODE_COVERAGE_DRIFT")
        modes_report = {}
        for sid, all_modes in base["stage_modes"].items():
            filtered = [m for m in all_modes if units[m["unit_id"]]["device_class"] in MASKS[pid]]
            modes = instance["stage_modes"][sid]
            require(sha(modes) == sha(filtered) and bool(modes), "MODE_MASK_NOT_EXACT_BASE_SUBSET:" + sid)
            require(len({m["mode_id"] for m in modes}) == len(modes), "DUPLICATE_MODES")
            modes_report[sid] = {"mode_count": len(modes), "mode_list_sha256": sha(modes),
                                 "base_mode_count": len(all_modes)}
        require(sha(instance) == sha(expected[pid]), "INPUT_DIFFERS_FROM_ORIGINAL_GENERATOR")
        report[pid] = {"input_sha256": sha(instance), "config_sha256": sha(packet["config"]),
                       "available_device_classes": list(MASKS[pid]),
                       "stage_modes": modes_report,
                       "total_catalog_mode_count": sum(len(v) for v in instance["stage_modes"].values()),
                       "idle_power": idle_power_evidence(instance)}
    # These are logical-domain inclusions, not a promise about heuristic outcomes.
    inclusions = []
    for left, right in ((PROBLEM_IDS[0], PROBLEM_IDS[1]), (PROBLEM_IDS[0], PROBLEM_IDS[2]),
                        (PROBLEM_IDS[1], BASE_ID), (PROBLEM_IDS[2], BASE_ID)):
        for sid in base["stage_modes"]:
            left_modes = {sha(m) for m in packets[left]["instance"]["stage_modes"][sid]}
            right_modes = {sha(m) for m in packets[right]["instance"]["stage_modes"][sid]}
            require(left_modes <= right_modes, "RESOURCE_DOMAIN_INCLUSION_FAILED")
        inclusions.append({"subset": left, "superset": right, "all_stage_modes_included": True})
    return {"state": "STATIC_RESOURCE_INPUT_CONTRACT_PASSED",
            "validation_kind": "INPUT_EXPANSION_AND_EMPTY_ACTIVITY_POWER_ARITHMETIC",
            "source_config_sha256": sha(frozen),
            "allowed_difference_paths": list(ALLOWED_DIFFERENCE_PATHS),
            "ablation_input_note": "Original generator label: resource masks false, shared base true; no physics effect.",
            "physical_node_order": base["platform"]["node_order"],
            "physical_domain_ids": sorted(base["platform"]["domains"]),
            "inputs": report, "mode_domain_inclusions": inclusions,
            "CPU_GPU_and_CPU_NPU_are_not_declared_mutual_subsets": True,
            "candidate_search_performed": False, "thermal_propagation_performed": False,
            "real_SAFE_created": False}


def validate_inputs(packets):
    """Reject changes beyond the original resource masks and generated labels."""
    try:
        return _validate(packets)
    except ContractError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, ZeroDivisionError) as error:
        raise ContractError("MALFORMED_RESOURCE_INPUT:" + type(error).__name__) from error
