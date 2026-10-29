"""Explicit, reviewable calibration configuration and planned calls, no workloads."""

from copy import deepcopy

from research.chapter3_deadline_reference.contract import content_hash, exact


PROTOCOL_COMMIT = "6fcb6ef38c68a3b95582af2b76267679a9e13c33"


def approved_configuration():
    """User confirmed candidate bundle and bounds on 2026-10-29, not formal data."""
    return {
        "schema_version": "calibration-run-configuration-v1", "protocol_commit": PROTOCOL_COMMIT,
        "authorization": "USER_CONFIRMED_CANDIDATE_AND_BOUNDED_CALIBRATION_20261029",
        "namespace": "ch3-calibration-v1", "seed": 20261029,
        "formal_namespace_reserved": "ch3-formal-v1",
        "candidate_not_formal_freeze": True,
        "betas": ["1", "1.3", "1.6", "2"], "priority_beta": "1.3",
        "warning_thresholds": {"medium_low_on_time_rate": "0.1", "low_high_on_time_rate": "0.9",
                               "low_obvious_slack_eta": "0.1"},
        "limits": {"conditions": 160, "timetables": 480, "condition_seconds": 60,
                   "batch_seconds": 3600, "retries": 0},
        "settings": {
            "reference_topology": "branch_join", "split_rule": "equal_contiguous",
            "s7_release_rule": "synchronous_same_application", "relative_release_factor": "0.1",
            "profiles": {
                "category_weights": {k: "1/4" for k in ("cpu_only", "gpu_friendly", "npu_friendly", "multi_device")},
                "cpu_prototype_weights": {k: "1/6" for k in ("A.pre", "A.post", "B.pre", "B.post", "C.pre", "C.post")},
                "workload": {"minimum": "0.5", "maximum": "2", "quantum": "0.001",
                             "precision": 60, "rounding": "ROUND_HALF_UP"},
                "specialization_probabilities": {"gpu_friendly": "0.4", "npu_friendly": "0.4"}},
            "topology": {"algorithm_version": "layered-forward-v1", "layer_rule": "ceil_sqrt_balanced",
                         "output_rule": "all_last_layer", "edge_target_multiplier": "3/2",
                         "edge_target_rounding": "half_up", "edge_cap_rule": "max_bipartite_degree_capacity",
                         "max_indegree": 3, "max_outdegree": 3, "max_attempts": 64,
                         "small_two_node_rule": "chain", "branch_rule": "first_diamond_then_tail_chain",
                         "reject_total_reachability_order": True, "reject_branch_template": True}},
        "extra_implementation_rules": {
            "branch_extension": "first_diamond_then_tail_chain_preserves_prefix_edges",
            "split": "equal_halves_or_quarters",
            "seed_reason": "public_date_seed_fixed_before_workload_generation",
            "topology_attempts": "at_most_64_within_one_generation_not_research_retries",
            "window": "UNFROZEN_NOT_USED_BY_TIME_REFERENCE",
            "stop": "first_contract_generation_validation_or_timeout_failure_no_retry",
            "beta_selection": "NONE_USER_REVIEW_REQUIRED"}}


def planned_calls(config):
    if config["namespace"] == config["formal_namespace_reserved"]:
        raise ValueError("CALIBRATION_FORMAL_NAMESPACE_COLLISION")
    calls = []
    for index in range(1, 25):
        root = f"C{index:02d}"
        focus = (6, 24, 96)[(index - 1) // 8]
        offset = (index - 1) % 8
        scene_pool = "A" if offset < 4 else "B"
        pool = "cpu_common" if offset % 4 < 2 else "heterogeneous"
        common = {"root_id": root, "scene_pool": scene_pool, "compatibility_pool": pool,
                  "focus_scale": focus, "seed": config["seed"]}
        for scale in (6, 24, 96):
            calls.append({**common, "condition_id": f"{root}__base_{scale}", "kind": "base",
                          "scale": scale, "value": None,
                          "parent_condition_id": None if scale == 6 else f"{root}__base_{6 if scale == 24 else 24}"})
        for kind in ("serial", "layered"):
            calls.append({**common, "condition_id": f"{root}__S4_{kind}", "kind": "S4",
                          "scale": focus, "value": kind, "parent_condition_id": f"{root}__base_{focus}"})
        axis, value = ("S5", "1.25") if index % 2 else ("S7", 2)
        calls.append({**common, "condition_id": f"{root}__{axis}", "kind": axis,
                      "scale": focus, "value": value, "parent_condition_id": f"{root}__base_{focus}"})
        if index <= 8:
            for split in (2, 4):
                calls.append({**common, "condition_id": f"{root}__S3_{split}", "kind": "S3",
                              "scale": 6, "value": split, "parent_condition_id": f"{root}__base_6"})
    if len(calls) != config["limits"]["conditions"] or 3 * len(calls) != config["limits"]["timetables"]:
        raise ValueError("COVERAGE_COUNT_MISMATCH")
    return {"schema_version": "calibration-call-manifest-v1", "configuration": deepcopy(config),
            "configuration_hash": content_hash(config), "calls": calls,
            "planned_reference_mapping_calls": 72, "planned_timetable_constructions": 480,
            "planned_scene_schedules": 3840, "planned_S1_projection_calls": 360,
            "planned_formal_algorithm_calls": 0, "planned_thermal_integrations": 0}


def validate_manifest(manifest):
    expected = planned_calls(manifest["configuration"])
    if manifest != expected:
        raise ValueError("MANIFEST_DRIFT")
    if manifest["configuration"] != approved_configuration():
        raise ValueError("APPROVED_CONFIGURATION_CHANGED")
    return True
