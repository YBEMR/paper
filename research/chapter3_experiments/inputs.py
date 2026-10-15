"""Exact input preparation for the chapter 3 abstract experiment proposal.

Public interfaces:
    load_config(path=None) -> raw configuration dict
    build_instances(config) -> list of 95 independent problem dicts
    expand_options(instance, config) -> flat list of Stage/mode/start options

All physical and time scalars are JSON strings. Derived rationals are reduced
``numerator/denominator`` strings (or integer strings); counts remain integers.
Use ``Fraction(value)`` to consume them. No binary floating-point arithmetic,
schedule enumeration, thermal simulation, solver or reference answer is used.
Times remain milliseconds; a future energy evaluator must convert ms to s.
"""

from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path


def _fraction(value):
    """Reject float inputs instead of silently treating rounding as exact."""
    if isinstance(value, bool) or not isinstance(value, (str, int, Fraction)):
        raise TypeError("Exact scalar must be a string, integer or Fraction")
    return Fraction(value)


def _rational(value):
    return str(_fraction(value))


def load_config(path=None):
    """Read the raw numeric proposal without executing an experiment."""
    path = Path(path) if path is not None else Path(__file__).with_name("config_v01.json")
    with path.open("r", encoding="utf-8") as stream:
        config = json.load(stream)
    if config.get("schema_version") != "chapter3-input-v0.1":
        raise ValueError("Unsupported chapter 3 input schema")
    if len({item["id"] for item in config["conditions"]}) != len(config["conditions"]):
        raise ValueError("Duplicate condition identifiers")
    if len({item["id"] for item in config["samples"]}) != len(config["samples"]):
        raise ValueError("Duplicate workload sample identifiers")
    return config


def _application_stages(config):
    applications = {}
    for stage in config["stage_catalog"]:
        applications.setdefault(stage["application"], []).append(stage)
    return {
        app: sorted(stages, key=lambda stage: stage["position"])
        for app, stages in applications.items()
    }


def _mean_alpha(config, sample):
    """Weight each legal catalog Stage once, before any resource mask.

    CPU1 and CPU2 use the same device-class profile. Request/scenario copies
    do not change this fixed-catalog mean; each sample's duration scale does.
    """
    numerator = {key: Fraction(0) for key in config["platform"]["domains"]}
    denominator = dict(numerator)
    for stage in config["stage_catalog"]:
        scale = _fraction(sample["duration_scale"][stage["application"]])
        for device, profile in stage["profiles"].items():
            weight = _fraction(profile["d_ref_ms"]) * scale
            numerator[device] += weight * _fraction(profile["alpha"])
            denominator[device] += weight
    return {
        device: numerator[device] / denominator[device]
        for device in numerator if denominator[device] > 0
    }


def _expand_modes(config, sample, settings):
    means = _mean_alpha(config, sample)
    variant = settings["response_variant"]
    if variant not in ("H", "M", "R"):
        raise ValueError("Response variant must be H, M or R")
    available = set(settings["available_device_classes"])
    stage_modes = {}
    for stage in config["stage_catalog"]:
        modes = []
        scale = _fraction(sample["duration_scale"][stage["application"]])
        for unit in config["platform"]["units"]:
            device = unit["device_class"]
            if device not in available or device not in stage["profiles"]:
                continue
            profile = stage["profiles"][device]
            domain = config["platform"]["domains"][unit["domain_id"]]
            reference = domain["opps"][domain["reference_opp"]]
            d_ref = _fraction(profile["d_ref_ms"]) * scale
            alpha = (Fraction(1) if variant == "R" else
                     means[device] if variant == "M" else
                     _fraction(profile["alpha"]))
            for opp_id, opp in domain["opps"].items():
                frequency = _fraction(opp["frequency_GHz"])
                voltage = _fraction(opp["voltage_V"])
                ref_frequency = _fraction(reference["frequency_GHz"])
                ref_voltage = _fraction(reference["voltage_V"])
                duration = d_ref * (1 - alpha + alpha * ref_frequency / frequency)
                activity_power = (_fraction(profile["q_ref_W"]) *
                                  (voltage / ref_voltage) ** 2 *
                                  frequency / ref_frequency)
                modes.append({
                    "mode_id": f"{stage['id']}@{unit['id']}:{opp_id}",
                    "shared_stage_id": stage["id"],
                    "unit_id": unit["id"],
                    "domain_id": unit["domain_id"],
                    "power_group_id": unit["power_group_id"],
                    "thermal_node_id": unit["thermal_node_id"],
                    "opp_id": opp_id,
                    "frequency_GHz": _rational(frequency),
                    "voltage_V": _rational(voltage),
                    "d_ref_ms": _rational(d_ref),
                    "alpha": _rational(alpha),
                    "duration_ms": _rational(duration),
                    "activity_power_W": _rational(activity_power),
                    "activity_energy_J": _rational(activity_power * duration / 1000)
                })
        if not modes:
            raise ValueError(f"Stage {stage['id']} has no supported available unit")
        stage_modes[stage["id"]] = modes
    return stage_modes, {device: _rational(value) for device, value in means.items()}


def _expand_scenarios(config, sample, settings):
    applications = _application_stages(config)
    beta = _fraction(settings["deadline_beta"])
    lengths = {
        app: sum((_fraction(stage["profiles"]["CPU"]["d_ref_ms"])
                  for stage in stages), Fraction(0)) *
             _fraction(sample["duration_scale"][app])
        for app, stages in applications.items()
    }
    pairs = settings["scene_application_pairs"]
    offsets = settings["scene_release_offsets_ms"]
    count = len(pairs) * len(offsets)
    if not count:
        raise ValueError("At least one declared scenario is required")
    copies = settings["requests_per_application"]
    if isinstance(copies, bool) or not isinstance(copies, int) or copies < 1:
        raise ValueError("Request copy count must be a positive integer")
    scenarios = []
    for pair in pairs:
        if len(pair) != 2:
            raise ValueError("This input package requires two-application scenarios")
        for offset in offsets:
            offset = _fraction(offset)
            scenario_id = f"{pair[0]}{pair[1]}_offset_{offset}ms"
            requests = []
            stage_instances = []
            dependencies = []
            for app_index, app in enumerate(pair):
                release = Fraction(0) if app_index == 0 else offset
                deadline = release + beta * lengths[app]
                for copy in range(1, copies + 1):
                    request_id = f"{scenario_id}::{app}_r{copy}"
                    ids = []
                    for stage in applications[app]:
                        instance_id = f"{request_id}::{stage['id']}"
                        ids.append(instance_id)
                        stage_instances.append({
                            "id": instance_id,
                            "request_id": request_id,
                            "shared_stage_id": stage["id"],
                            "application": app,
                            "chain_position": stage["position"]
                        })
                    dependencies.extend([[left, right] for left, right in zip(ids, ids[1:])])
                    requests.append({
                        "id": request_id,
                        "application": app,
                        "copy_index": copy,
                        "release_ms": _rational(release),
                        "reference_CPU_H_chain_ms": _rational(lengths[app]),
                        "relative_deadline_ms": _rational(beta * lengths[app]),
                        "deadline_ms": _rational(deadline),
                        "stage_instance_ids": ids
                    })
            scenarios.append({
                "id": scenario_id,
                "application_pair": list(pair),
                "second_application_release_offset_ms": _rational(offset),
                "weight": _rational(Fraction(1, count)),
                "entry": {
                    "temperature_degC": [_rational(settings["initial_temperature_degC"])] *
                                         len(config["platform"]["node_order"]),
                    "domain_opp": {key: value["entry_opp"] for key, value in
                                   config["platform"]["domains"].items()},
                    "unfinished_work": []
                },
                "maximum_temperature_degC": [_rational(settings["maximum_temperature_degC"])] *
                                            len(config["platform"]["node_order"]),
                "requests": requests,
                "stage_instances": stage_instances,
                "dependencies": dependencies
            })
    return scenarios


def build_instances(config):
    """Generate each declared single-factor condition paired with each sample.

    The complete physical platform is retained in every instance, including
    masked devices and thermal nodes. The mask limits Stage mapping only.
    Deadline scaling uses CPU-H reference duration and never the R/M/H alpha.
    """
    instances = []
    seen_settings = set()
    for condition in config["conditions"]:
        settings = deepcopy(config["defaults"])
        unknown = set(condition["overrides"]) - set(settings)
        if unknown:
            raise ValueError(f"Unknown condition override keys: {sorted(unknown)}")
        settings.update(deepcopy(condition["overrides"]))
        signature = json.dumps(settings, sort_keys=True, ensure_ascii=False)
        if signature in seen_settings:
            raise ValueError("Duplicate effective condition; shared baseline must run once")
        seen_settings.add(signature)
        for sample in config["samples"]:
            stage_modes, means = _expand_modes(config, sample, settings)
            instances.append({
                "schema_version": config["schema_version"],
                "id": f"{condition['id']}__{sample['id']}",
                "condition_id": condition["id"],
                "experiment_group": condition["group"],
                "sample_id": sample["id"],
                "settings": deepcopy(settings),
                "duration_scale": {app: _rational(value) for app, value in sample["duration_scale"].items()},
                "platform": deepcopy(config["platform"]),
                "execution_rules": deepcopy(config["execution_rules"]),
                "units": deepcopy(config["units"]),
                "window_ms": _rational(settings["window_ms"]),
                "start_grid_ms": _rational(settings["start_grid_ms"]),
                "response_variant": settings["response_variant"],
                "catalog_duration_weighted_mean_alpha": means,
                "stage_modes": stage_modes,
                "scenarios": _expand_scenarios(config, sample, settings),
                "ablation_input": condition["id"] in config["run_protocol"]["ablation_condition_ids"],
                "status": "input_only_not_evaluated"
            })
    return instances


def expand_options(instance, config):
    """Return local Stage/mode/start choices, not complete arrangements.

    Start times satisfy the grid and request release; true rational finishes
    must not exceed the window. Dependencies, request deadlines, resource
    exclusivity, shared mapping, busy-domain OPP compatibility and continuous
    heat are intentionally left for the planner/evaluator. An option list is
    not a feasible schedule and carries no safety or optimality certificate.
    """
    if instance["schema_version"] != config["schema_version"]:
        raise ValueError("Instance/config schema mismatch")
    window = _fraction(instance["window_ms"])
    grid = _fraction(instance["start_grid_ms"])
    if grid <= 0 or window < 0:
        raise ValueError("Start grid must be positive and window nonnegative")
    maximum_index = window // grid
    options = []
    for scenario in instance["scenarios"]:
        requests = {request["id"]: request for request in scenario["requests"]}
        for stage in scenario["stage_instances"]:
            request = requests[stage["request_id"]]
            release = _fraction(request["release_ms"])
            first_index = max(0, -((-release) // grid))
            for mode in instance["stage_modes"][stage["shared_stage_id"]]:
                duration = _fraction(mode["duration_ms"])
                if duration <= 0:
                    raise ValueError("Stage duration must be positive")
                last_index = min(maximum_index, (window - duration) // grid)
                for index in range(first_index, last_index + 1):
                    start = index * grid
                    finish = start + duration
                    option = dict(mode)
                    option.update({
                        "option_id": f"{stage['id']}@{mode['unit_id']}:{mode['opp_id']}:g{index}",
                        "scenario_id": scenario["id"],
                        "request_id": request["id"],
                        "stage_instance_id": stage["id"],
                        "start_grid_index": index,
                        "start_ms": _rational(start),
                        "end_ms": _rational(finish),
                        "request_release_ms": request["release_ms"],
                        "request_deadline_ms": request["deadline_ms"]
                    })
                    options.append(option)
    return options
