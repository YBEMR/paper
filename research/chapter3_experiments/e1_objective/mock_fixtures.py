"""Hand-written MOCK ONLY E1 data; no physical propagation or search is run."""
from copy import deepcopy
from fractions import Fraction as F

from h02_pair_preflight.common import POLICY, sha
from schedules import validate_schedule


def make_fixture(*, opp="L", start_ms="0", temperature_energy_J="1/25", completed_at_s=1.0, h_activity_power_W="3"):
    """Return instance/candidate/legality/receipt/accuracy for isolated mock tests.

    The exact nonthermal components come from a manually supplied schedule;
    the temperature component and envelopes are invented test values. The
    input has no RC matrices and is deliberately unsuitable for a real run.
    """
    platform = {
        "node_order": ["N0"], "reference_temperature_degC": "25",
        "external_common_power_W": "3/10", "external_common_heat_distribution": ["0"],
        "power_model_temperature_range_degC": ["0", "100"],
        "units": [{"id": "CPU1", "domain_id": "CPU", "power_group_id": "CPU",
                   "thermal_node_id": "N0"}],
        "domains": {"CPU": {"unit_ids": ["CPU1"], "baseline_heat_distribution": ["1"],
            "opps": {"L": {"frequency_GHz": "1", "voltage_V": "1"},
                     "H": {"frequency_GHz": "2", "voltage_V": "6/5"}},
            "baseline_W": {"L": "1", "H": "2"},
            "local_temperature_slope_W_per_K": {"L": "1/100", "H": "1/50"}}}}
    rules = {"preemption": False, "migration": False, "in_stage_opp_change": False,
        "switch_only_when_domain_empty": True, "interval_convention": "[start,end)",
        "idle_holds_last_opp": False, "idle_policy": POLICY, "idle_delay_ms": "0"}
    for kind in ("transfer", "switch", "handoff"):
        rules["extra_" + kind + "_time_ms"] = "0"
        rules["extra_" + kind + "_energy_J"] = "0"
    modes = []
    for point, duration, power in (("L", "100", "2"), ("H", "50", h_activity_power_W)):
        modes.append({"mode_id": "A@CPU1:" + point, "shared_stage_id": "A", "unit_id": "CPU1",
            "opp_id": point, "domain_id": "CPU", "thermal_node_id": "N0", "power_group_id": "CPU",
            **platform["domains"]["CPU"]["opps"][point],
            "duration_ms": duration, "activity_power_W": power})
    scenarios = []
    for sid in ("AB", "AC"):
        stage_id = sid + ":A"
        scenarios.append({"id": sid, "weight": "1/2", "entry": {"temperature_degC": ["30"],
            "domain_opp": {"CPU": "L"}, "unfinished_work": []}, "maximum_temperature_degC": ["80"],
            "stage_instances": [{"id": stage_id, "shared_stage_id": "A", "request_id": sid + ":req"}],
            "requests": [{"id": sid + ":req", "release_ms": "0", "deadline_ms": "400",
                "stage_instance_ids": [stage_id]}], "dependencies": []})
    instance = {"id": "MOCK_ONLY_E1", "schema_version": "chapter3-input-v0.1",
        "window_ms": "400", "start_grid_ms": "5", "response_variant": "H", "platform": platform,
        "execution_rules": rules, "stage_modes": {"A": modes}, "scenarios": scenarios}
    candidate = {"scenes": {scene["id"]: [{"stage_id": scene["stage_instances"][0]["id"],
        "unit": "CPU1", "opp": opp, "start_ms": start_ms}] for scene in scenarios}}
    legality = validate_schedule(instance, candidate)
    if legality["state"] != "SCHEDULE_VALID_THERMAL_UNCHECKED":
        raise ValueError("Mock fixture schedule is invalid: " + str(legality))
    accuracy = {"energy_absolute_error_J": "1/1000000", "energy_relative_error": "1/1000000",
                "temperature_enclosure_width_K": "1/1000"}
    results = {}
    for scene in scenarios:
        components = {name: F(0) for name in ("baseline", "activity", "external_common")}
        for segment in legality["scenes"][scene["id"]]["segments"]:
            duration = F(segment["duration_ms"]) / 1000
            components["baseline"] += duration * sum(map(F, segment["baseline_by_power_group_W"].values()))
            components["activity"] += duration * sum(map(F, segment["activity_by_node_W"].values()))
            components["external_common"] += duration * F(segment["external_common_power_W"])
        components["temperature_correction"] = F(temperature_energy_J)
        total = str(sum(components.values()))
        results[scene["id"]] = {"state": "SAFE", "complete": True, "rankable_energy": True,
            "energy_accuracy_met": True, "covered_until_s": "2/5", "energy_J": [total, total],
            "energy_components_J": {name: [str(value), str(value)] for name, value in components.items()},
            "peaks_degC": {"N0": ["32", "32"]}, "minimum_degC": {"N0": ["30", "30"]}}
    weighted = str(sum(F(scene["weight"]) * F(results[scene["id"]]["energy_J"][0]) for scene in scenarios))
    receipt = {"state": "SAFE", "rankable_energy": True, "completed_at_elapsed_s": completed_at_s,
        "problem_id": instance["id"], "evidence_identity": {"input_sha256": sha(instance),
            "candidate_sha256": sha(candidate)}, "control_policy": {"idle_policy": POLICY, "idle_delay_ms": "0"},
        "numerical_protocol": "directed-decimal60-taylor18-scaled100-v1", "violations": [],
        "legality": deepcopy(legality), "scenes": results, "weighted_energy_J": [weighted, weighted],
        "safe_upper_bound_J": weighted}
    return {"instance": instance, "candidate": candidate, "legality": legality,
            "receipt": receipt, "accuracy": accuracy}
