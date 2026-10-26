"""Explicit MOCK ONLY task inputs, never frozen research cases or old answers.

These fixtures have no RC matrices/capacities and cannot support a genuine
thermal evaluation. Only the four canonical input hashes may reach an actual
constructor during the protected test suite. Search tests mock every builder.
"""
from copy import deepcopy
from fractions import Fraction as F
from h02_pair_preflight.common import sha

TOY_FIXTURE_NAMES = ("gap", "single", "two_copies", "two_cpus")


def _input(names, *, units=1, copies=1, identifier):
    node_ids = ["MOCK_N" + str(n + 1) for n in range(units)]
    unit_ids = ["CPU" + str(n + 1) for n in range(units)]
    platform = {
        "node_order": node_ids, "reference_temperature_degC": "25",
        "external_common_power_W": "0", "external_common_heat_distribution": ["0"] * units,
        "power_model_temperature_range_degC": ["0", "100"],
        "units": [{"id": u, "device_class": "CPU", "domain_id": "CPU",
                   "power_group_id": "CPU", "thermal_node_id": node}
                  for u, node in zip(unit_ids, node_ids)],
        "domains": {"CPU": {"unit_ids": unit_ids, "entry_opp": "L", "reference_opp": "H",
            "baseline_heat_distribution": [str(F(1, units))] * units,
            "opps": {"L": {"frequency_GHz": "1", "voltage_V": "1"},
                     "H": {"frequency_GHz": "2", "voltage_V": "6/5"}},
            "baseline_W": {"L": "1/10", "H": "1/5"},
            "local_temperature_slope_W_per_K": {"L": "0", "H": "0"}}}}
    rules = {"preemption": False, "migration": False, "in_stage_opp_change": False,
             "switch_only_when_domain_empty": True, "interval_convention": "[start,end)",
             "idle_holds_last_opp": False, "idle_policy": "auto_low_immediate_v1", "idle_delay_ms": "0"}
    for name in ("transfer", "switch", "handoff"):
        rules["extra_" + name + "_time_ms"] = "0"
        rules["extra_" + name + "_energy_J"] = "0"
    modes, requests, stages = {}, [], []
    for name, high, deadline in names:
        modes[name] = []
        for u, node in zip(unit_ids, node_ids):
            for opp, duration in (("L", F(high) + 1), ("H", F(high))):
                modes[name].append({"mode_id": name + "@" + u + ":" + opp,
                    "shared_stage_id": name, "unit_id": u, "domain_id": "CPU", "power_group_id": "CPU",
                    "thermal_node_id": node, "opp_id": opp,
                    **platform["domains"]["CPU"]["opps"][opp],
                    "duration_ms": str(duration), "activity_power_W": "1",
                    "activity_energy_J": str(duration / 1000)})
        for n in range(1, copies + 1):
            req, stage = "toy:req:" + name + ":r" + str(n), "toy:iid:" + name + ":r" + str(n)
            requests.append({"id": req, "application": name, "copy_index": n,
                "release_ms": "0", "deadline_ms": str(deadline), "stage_instance_ids": [stage]})
            stages.append({"id": stage, "request_id": req, "shared_stage_id": name, "application": name})
    scene = {"id": "toy", "weight": "1", "entry": {"temperature_degC": ["25"] * units,
        "domain_opp": {"CPU": "L"}, "unfinished_work": []}, "maximum_temperature_degC": ["80"] * units,
        "requests": requests, "stage_instances": stages, "dependencies": []}
    return {"id": identifier, "mock_only": True, "fixture_kind": "NO_THERMAL_PARAMETERS",
        "schema_version": "chapter3-input-v0.1", "window_ms": "30", "start_grid_ms": "1",
        "response_variant": "H", "platform": platform, "execution_rules": rules,
        "stage_modes": modes, "scenarios": [scene]}


def make_toy_fixture(name="gap"):
    if name not in TOY_FIXTURE_NAMES:
        raise ValueError("Unknown canonical MOCK ONLY constructor fixture")
    spec = (("Long", "10", "30"), ("Urgent", "2", "6"))
    if name in ("single", "two_copies"):
        spec = (("Only", "3", "20"),)
    return _input(spec, units=2 if name == "two_cpus" else 1,
                  copies=2 if name == "two_copies" else 1,
                  identifier="MOCK_ONLY_DF_" + name.upper())


def constructor_fixture_sha256s():
    return {sha(make_toy_fixture(name)) for name in TOY_FIXTURE_NAMES}


def is_canonical_constructor_fixture(instance):
    return (isinstance(instance, dict) and instance.get("mock_only") is True and
            instance.get("fixture_kind") == "NO_THERMAL_PARAMETERS" and
            str(instance.get("id", "")).startswith("MOCK_ONLY_DF_") and
            sha(instance) in constructor_fixture_sha256s())
