"""E3 changes only the cross-scenario deployment identity of application A.

No modes, work points, power coefficients or time domains are added/deleted.
Scene-local aliases encode only deployment scope; OPP and start choices remain
per execution. The current adapter deliberately accepts only frozen base__R1.
"""
from copy import deepcopy

from control_policy import with_auto_low_idle
from h02_pair_preflight.common import ContractError, require, sha
from inputs import build_instance, load_config

BASE_ID = "base__R1"
LOCAL_A_ID = "base__R1__E3_SCENE_LOCAL_A"
PROBLEM_IDS = (BASE_ID, LOCAL_A_ID)
A_STAGE_IDS = ("A.pre", "A.main", "A.post")
ALLOWED_DIFFERENCE_PATHS = (
    "/id", "/stage_modes/<A-shared-or-alias-key>",
    "/scenarios/<scene-index>/stage_instances/<A-stage-index>/shared_stage_id")


def _reference_config(config=None):
    frozen = with_auto_low_idle(load_config())
    if config is not None:
        require(sha(with_auto_low_idle(config)) == sha(frozen), "CONFIG_DRIFT_FROM_FROZEN_SOURCE")
    return frozen


def _aliases(base):
    require(set(s["id"] for s in base["scenarios"]) == {"AB_offset_0ms", "AC_offset_0ms"},
            "UNSUPPORTED_SCENE_SET")
    return {scene["id"]: {sid: sid + "@@" + scene["id"] for sid in A_STAGE_IDS}
            for scene in base["scenarios"]}


def _derive(base):
    aliases = _aliases(base)
    result = deepcopy(base)
    result["id"] = LOCAL_A_ID
    for sid in A_STAGE_IDS:
        del result["stage_modes"][sid]
    for scene in result["scenarios"]:
        for stage in scene["stage_instances"]:
            if stage["application"] != "A":
                continue
            sid = stage["shared_stage_id"]
            require(sid in A_STAGE_IDS, "UNSUPPORTED_A_STAGE")
            alias = aliases[scene["id"]][sid]
            stage["shared_stage_id"] = alias
            # Repeated request copies of one Stage in this scene use one alias.
            # The current public adapter still rejects workloads beyond base R1.
            if alias not in result["stage_modes"]:
                result["stage_modes"][alias] = deepcopy(base["stage_modes"][sid])
                for mode in result["stage_modes"][alias]:
                    mode["shared_stage_id"] = alias
                    mode["mode_id"] = alias + "@" + mode["unit_id"] + ":" + mode["opp_id"]
    return result


def derive_scene_local_a(base_instance):
    """Fresh budgeted controller use: accept exactly the frozen true-H base.

    This is an identity adapter, not a general task-model transformation.
    Calling on a modified or already adapted input fails closed.
    """
    try:
        expected = build_instance(_reference_config(), BASE_ID)
        require(sha(base_instance) == sha(expected), "SOURCE_BASE_INPUT_DRIFT")
        return _derive(base_instance)
    except ContractError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise ContractError("MALFORMED_SHARED_DEPLOYMENT_INPUT:" + type(error).__name__) from error


def prepare_inputs(config=None):
    """Return independent packets; neither packet contains a seed candidate."""
    frozen = _reference_config(config)
    base = build_instance(frozen, BASE_ID)
    return {BASE_ID: {"config": deepcopy(frozen), "instance": deepcopy(base), "objective": "FULL"},
            LOCAL_A_ID: {"config": deepcopy(frozen), "instance": _derive(base), "objective": "FULL"}}


def _normalize(local, base):
    """Undo only the exact declared identity changes, for an equality proof."""
    normalized = deepcopy(local)
    normalized["id"] = BASE_ID
    aliases = _aliases(base)
    for scene in normalized["scenarios"]:
        for stage in scene["stage_instances"]:
            if stage["application"] == "A":
                reverse = {value: key for key, value in aliases[scene["id"]].items()}
                require(stage["shared_stage_id"] in reverse, "UNKNOWN_A_DEPLOYMENT_ALIAS")
                stage["shared_stage_id"] = reverse[stage["shared_stage_id"]]
    for sid in A_STAGE_IDS:
        copies = []
        for scene_id, table in aliases.items():
            modes = normalized["stage_modes"].pop(table[sid])
            for mode in modes:
                mode["shared_stage_id"] = sid
                mode["mode_id"] = sid + "@" + mode["unit_id"] + ":" + mode["opp_id"]
            require(sha(modes) == sha(base["stage_modes"][sid]), "MODE_COST_OR_COVERAGE_DRIFT")
            copies.append(modes)
        normalized["stage_modes"][sid] = copies[0]
    return normalized


def _difference_paths(left, right, path=""):
    if type(left) is not type(right):
        return [path]
    if isinstance(left, dict):
        result = []
        for key in sorted(set(left) | set(right)):
            child = path + "/" + str(key)
            result.extend([child] if key not in left or key not in right else
                          _difference_paths(left[key], right[key], child))
        return result
    if isinstance(left, list):
        if len(left) != len(right):
            return [path]
        return [p for index, (a, b) in enumerate(zip(left, right))
                for p in _difference_paths(a, b, path + "/" + str(index))]
    return [] if left == right else [path]


def _validate(packets):
    require(isinstance(packets, dict) and set(packets) == set(PROBLEM_IDS),
            "EXACT_TWO_DEPLOYMENT_INPUTS_REQUIRED")
    frozen = _reference_config()
    expected_base = build_instance(frozen, BASE_ID)
    expected = {BASE_ID: expected_base, LOCAL_A_ID: _derive(expected_base)}
    for pid in PROBLEM_IDS:
        packet = packets[pid]
        require(isinstance(packet, dict) and set(packet) == {"config", "instance", "objective"},
                "PACKET_FIELD_SET")
        require(sha(packet["config"]) == sha(frozen), "CONFIG_DRIFT_FROM_FROZEN_SOURCE")
        require(packet["objective"] == "FULL", "DEPLOYMENT_EXPERIMENT_REQUIRES_FULL_OBJECTIVE")
        require(packet["instance"]["id"] == pid, "PROBLEM_ID_MISMATCH")
        require(sha(packet["instance"]) == sha(expected[pid]), "UNDECLARED_DEPLOYMENT_INPUT_DRIFT")
    base, local = (packets[pid]["instance"] for pid in PROBLEM_IDS)
    normalized = _normalize(local, base)
    require(sha(normalized) == sha(base), "NORMALIZED_INPUT_NOT_IDENTICAL")
    aliases = _aliases(base)
    inputs = {}
    for pid in PROBLEM_IDS:
        instance = packets[pid]["instance"]
        inputs[pid] = {"input_sha256": sha(instance), "config_sha256": sha(packets[pid]["config"]),
                       "deployment_stage_count": len(instance["stage_modes"]),
                       "total_catalog_mode_count": sum(len(m) for m in instance["stage_modes"].values()),
                       "stage_mode_counts": {sid: len(modes) for sid, modes in instance["stage_modes"].items()}}
    require(inputs[BASE_ID]["deployment_stage_count"] == 9 and
            inputs[LOCAL_A_ID]["deployment_stage_count"] == 12 and
            inputs[BASE_ID]["total_catalog_mode_count"] == 66 and
            inputs[LOCAL_A_ID]["total_catalog_mode_count"] == 90, "DEPLOYMENT_COUNTS_DRIFT")
    return {"state": "STATIC_DEPLOYMENT_INPUT_CONTRACT_PASSED",
            "source_config_sha256": sha(frozen), "inputs": inputs,
            "allowed_difference_paths": list(ALLOWED_DIFFERENCE_PATHS),
            "exact_difference_paths": _difference_paths(base, local),
            "scene_A_deployment_aliases": aliases,
            "normalized_local_input_sha256": sha(normalized),
            "normalized_input_identical_to_shared": True,
            "deployment_only_relaxation": "Only application A's concrete unit may differ across AB and AC; B/C unchanged.",
            "OPP_and_start_remain_per_execution_choices": True,
            "candidate_search_performed": False, "thermal_propagation_performed": False,
            "real_SAFE_created": False}


def validate_inputs(packets):
    """Accept only the specified deployment-identity change, without evaluation."""
    try:
        return _validate(packets)
    except ContractError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, ZeroDivisionError) as error:
        raise ContractError("MALFORMED_DEPLOYMENT_INPUT:" + type(error).__name__) from error
