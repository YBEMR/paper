"""Map a verified time-only workload into the existing formal input contract.

No workload generation, reference scheduling, option expansion, optimization,
or thermal evaluation occurs here. The caller supplies the selected deadline
and comparison-window receipts. Reference mappings/timetables are deliberately
not accepted by this API and cannot become a deployment constraint or seed.
"""

from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path

from research.chapter3_deadline_reference.contract import (
    ContractError, content_hash, exact, normalize, shared_units)
from research.chapter3_deadline_reference.deadlines import _verify_receipt
from research.chapter3_workload_calibration.generator import validate_bundle
from research.chapter3_workload_calibration.profiles import SOURCE_SHA256
from research.chapter3_experiments.control_policy import with_auto_low_idle


SCHEMA = "chapter3-formal-adaptation-receipt-v1"


def _require(condition, code, **details):
    if not condition:
        raise ContractError(code, **details)


def _hash_receipt(receipt, code):
    _require(isinstance(receipt, dict) and receipt.get("receipt_hash") ==
             content_hash({k: v for k, v in receipt.items() if k != "receipt_hash"}), code)


def _source_config(config, bundle, data):
    """Bind the original physical/precision source, with explicit auto-L only."""
    path = Path(__file__).resolve().parents[1] / "chapter3_experiments/config_v01.json"
    raw = path.read_bytes()
    _require(hashlib.sha256(raw).hexdigest() == SOURCE_SHA256,
             "ADAPTER_FROZEN_SOURCE_HASH_MISMATCH")
    source = json.loads(raw.decode("utf-8"))
    _require(bundle["provenance"]["source_sha256"] == SOURCE_SHA256,
             "ADAPTER_PROFILE_SOURCE_MISMATCH")
    _require(config["platform"] == source["platform"] == bundle["physical_platform"],
             "ADAPTER_PHYSICAL_PLATFORM_MISMATCH")
    for key in ("schema_version", "units", "accuracy_targets"):
        _require(config[key] == source[key], "ADAPTER_CONFIG_SOURCE_MISMATCH", field=key)
    for key in ("start_grid_ms", "maximum_temperature_degC"):
        _require(exact(config["defaults"][key]) == exact(source["defaults"][key]),
                 "ADAPTER_CONFIG_SOURCE_MISMATCH", field=key)
    target = with_auto_low_idle(config)
    expected = with_auto_low_idle(source)
    _require(target["execution_rules"] == expected["execution_rules"],
             "ADAPTER_EXECUTION_RULE_MISMATCH")
    _require(all(target["execution_rules"].get(k) == v
                 for k, v in data["execution_rules"].items()),
             "ADAPTER_TIME_EXECUTION_RULE_MISMATCH")
    physical = target["platform"]
    time_units = sorted(({"id": u["id"], "domain_id": u["domain_id"]}
                         for u in physical["units"]), key=lambda u: u["id"])
    _require(data["platform"]["units"] == time_units,
             "ADAPTER_TIME_UNIT_MISMATCH")
    _require(set(data["platform"]["domains"]) == set(physical["domains"]),
             "ADAPTER_TIME_DOMAIN_MISMATCH")
    for did, declared in data["platform"]["domains"].items():
        domain = physical["domains"][did]
        _require(declared["reference_opp"] == domain["reference_opp"] and
                 set(declared["opps"]) == set(domain["opps"]),
                 "ADAPTER_TIME_OPP_MISMATCH", domain=did)
        _require(all(exact(v["frequency_GHz"]) == exact(domain["opps"][opp]["frequency_GHz"])
                     for opp, v in declared["opps"].items()),
                 "ADAPTER_TIME_FREQUENCY_MISMATCH", domain=did)
    return target


def _window(bundle, data, deadlines, receipt, member_key):
    _hash_receipt(receipt, "ADAPTER_WINDOW_HASH_MISMATCH")
    _require(receipt.get("schema_version") == "calibration-adjustment-window-v1" and
             receipt.get("state") == "WINDOW_RULE_APPLIED_NOT_FORMAL_EXECUTION_AUTHORIZATION",
             "ADAPTER_UNSUPPORTED_WINDOW_RECEIPT")
    _require(isinstance(member_key, str) and member_key in receipt.get("members", {}),
             "ADAPTER_WINDOW_MEMBER_REQUIRED")
    _require(receipt["root_family_id"] == data["root_family_id"] and
             receipt["scale"] == bundle["provenance"]["scale"] and
             exact(receipt["grid_ms"]) == exact(data["start_grid_ms"]) and
             exact(receipt["beta"]) == exact(deadlines["beta"]) and
             receipt["deadline_origin_hash"] == deadlines["deadline_origin_hash"],
             "ADAPTER_WINDOW_CONTEXT_MISMATCH")
    window, latest = exact(receipt["window_ms"]), exact(receipt["latest_deadline_ms"])
    _require(window > 0 and window == -(-latest // 5) * 5,
             "ADAPTER_WINDOW_ROUNDING_MISMATCH")
    _require(receipt["members"][member_key] == {
        "bundle_hash": bundle["bundle_hash"], "contract_hash": bundle["contract_hash"],
        "deadline_receipt_hash": deadlines["receipt_hash"], "window_ms": str(window)},
        "ADAPTER_WINDOW_MEMBER_MISMATCH")
    _require(all(exact(row["deadline_ms"]) <= window
                 for scene in deadlines["requests"].values() for row in scene.values()),
             "ADAPTER_DEADLINE_OUTSIDE_WINDOW")
    return window


def _application_outputs(bundle):
    """Require all application nodes to be mandatory ancestors of sink outputs."""
    application_of, outputs = {}, {}
    for aid, app in bundle["applications"].items():
        nodes = set(app["nodes"])
        _require(bool(nodes) and len(nodes) == len(app["nodes"]),
                 "ADAPTER_APPLICATION_NODE_IDENTITIES")
        _require(not nodes.intersection(application_of), "ADAPTER_SHARED_APPLICATION_IDENTITY")
        succ = {n: [] for n in nodes}
        for edge in app["edges"]:
            _require(isinstance(edge, list) and len(edge) == 2 and
                     all(n in nodes for n in edge), "ADAPTER_APPLICATION_EDGE_ENDPOINT")
            succ[edge[0]].append(edge[1])
        sinks = {n for n in nodes if not succ[n]}
        _require(sinks and len(set(app["required_outputs"])) == len(app["required_outputs"]) and
                 set(app["required_outputs"]) == sinks,
                 "ADAPTER_REQUIRED_OUTPUTS_MISMATCH")
        # Acyclicity is independently checked on actual execution instances by
        # normalize. Verify application closure without assuming list order.
        covered = set(sinks)
        while True:
            extra = {n for n in nodes if succ[n] and set(succ[n]) <= covered}
            if extra <= covered:
                break
            covered.update(extra)
        _require(covered == nodes, "ADAPTER_OUTPUT_CLOSURE_MISMATCH")
        application_of.update({n: aid for n in nodes})
        outputs[aid] = sorted(sinks)
    _require(set(application_of) == set(bundle["physical_profiles"]),
             "ADAPTER_APPLICATION_PROFILE_COVERAGE")
    return application_of, outputs


def _occurrence_graphs(bundle, data, applications):
    """Verify that request DAGs instantiate the declared application templates.

    Additional explicit cross-request dependencies remain in the exported
    contract. They do not replace any required internal application edge.
    """
    for scene in data["scenarios"]:
        stages = {s["id"]: s for s in scene["stage_instances"]}
        for request in scene["requests"]:
            members = [stages[i] for i in request["stage_instance_ids"]]
            app_ids = {applications[s["shared_stage_id"]] for s in members}
            _require(len(app_ids) == 1, "ADAPTER_REQUEST_APPLICATION_MISMATCH")
            aid = next(iter(app_ids))
            app = bundle["applications"][aid]
            shared = {s["shared_stage_id"] for s in members}
            _require(len(shared) == len(members) and shared == set(app["nodes"]),
                     "ADAPTER_REQUEST_TEMPLATE_COVERAGE", scene=scene["id"], request=request["id"])
            instance_ids = set(request["stage_instance_ids"])
            actual = {(stages[a]["shared_stage_id"], stages[b]["shared_stage_id"])
                      for a, b in scene["dependencies"] if a in instance_ids and b in instance_ids}
            _require(actual == {tuple(e) for e in app["edges"]},
                     "ADAPTER_REQUEST_TEMPLATE_EDGE_MISMATCH", scene=scene["id"], request=request["id"])


def _modes(bundle, data, allowed, physical):
    units = {u["id"]: u for u in physical["units"]}
    modes = {}
    for sid, legal in allowed.items():
        modes[sid] = []
        for uid in legal:
            unit = units[uid]
            profile = bundle["physical_profiles"][sid]["units"][uid]
            timed = data["stage_profiles"][sid]["units"][uid]
            domain = physical["domains"][unit["domain_id"]]
            reference = domain["opps"][domain["reference_opp"]]
            f_ref, v_ref = exact(reference["frequency_GHz"]), exact(reference["voltage_V"])
            d_ref, alpha, q_ref = (exact(profile[k]) for k in ("d_ref_ms", "alpha", "q_ref_W"))
            for opp_id in sorted(timed["legal_opps"]):
                opp = domain["opps"][opp_id]
                frequency, voltage = exact(opp["frequency_GHz"]), exact(opp["voltage_V"])
                duration = d_ref * ((1 - alpha) + alpha * f_ref / frequency)
                power = q_ref * (voltage / v_ref) ** 2 * frequency / f_ref
                modes[sid].append({
                    "mode_id": f"{sid}@{uid}:{opp_id}", "shared_stage_id": sid,
                    "unit_id": uid, "domain_id": unit["domain_id"],
                    "power_group_id": unit["power_group_id"], "thermal_node_id": unit["thermal_node_id"],
                    "opp_id": opp_id, "frequency_GHz": str(frequency), "voltage_V": str(voltage),
                    "d_ref_ms": str(d_ref), "alpha": str(alpha), "duration_ms": str(duration),
                    "activity_power_W": str(power), "activity_energy_J": str(power * duration / 1000),
                })
    return modes


def adapt_bundle(bundle, deadline_receipt, window_receipt, *, member_key, config, instance_id):
    """Return new config/instance/receipt objects, preserving every input object.

    Explicit deadline/window receipts select beta and the common evaluation
    horizon. This is input export, never an execution authorization or SAFE.
    """
    _require(isinstance(instance_id, str) and instance_id.strip(), "ADAPTER_INSTANCE_ID_REQUIRED")
    validate_bundle(bundle)
    data = normalize(bundle["time_contract"])
    _verify_receipt(data, deadline_receipt)
    _require(exact(deadline_receipt["beta"]) >= 1, "ADAPTER_INVALID_BETA")
    target_config = _source_config(config, bundle, data)
    window = _window(bundle, data, deadline_receipt, window_receipt, member_key)
    applications, outputs = _application_outputs(bundle)
    _occurrence_graphs(bundle, data, applications)
    allowed = shared_units(data)  # Only actually present current-subset occurrences.
    physical = target_config["platform"]
    initial = data["context"].get("initial_temperature_C")
    _require(isinstance(initial, list) and len(initial) == len(physical["node_order"]),
             "ADAPTER_EXPLICIT_INITIAL_TEMPERATURE_REQUIRED")
    initial = list(map(exact, initial))
    lower, upper = map(exact, physical["power_model_temperature_range_degC"])
    _require(all(lower <= value <= upper for value in initial),
             "ADAPTER_INITIAL_TEMPERATURE_OUTSIDE_MODEL")
    maximum = exact(target_config["defaults"]["maximum_temperature_degC"])
    _require(lower <= maximum <= upper, "ADAPTER_LIMIT_OUTSIDE_POWER_MODEL")
    identity, inverse, scenes = {}, {}, []
    global_ids = set()
    for scene in data["scenarios"]:
        sid = scene["id"]
        ids = {"requests": {r["id"]: f"{sid}::{r['id']}" for r in scene["requests"]},
               "stages": {s["id"]: f"{sid}::{s['id']}" for s in scene["stage_instances"]}}
        for kind in ids:
            values = list(ids[kind].values())
            _require(len(set(values)) == len(values) and not set(values).intersection(global_ids),
                     "ADAPTER_GLOBAL_ID_COLLISION")
            global_ids.update(values)
        identity[sid] = ids
        inverse[sid] = {kind: {new: old for old, new in mapping.items()}
                        for kind, mapping in ids.items()}
        requests = []
        for request in scene["requests"]:
            row = deadline_receipt["requests"][sid][request["id"]]
            requests.append({"id": ids["requests"][request["id"]],
                             "release_ms": str(exact(row["release_ms"])),
                             "deadline_ms": str(exact(row["deadline_ms"])),
                             "relative_deadline_ms": str(exact(row["relative_deadline_ms"])),
                             "stage_instance_ids": [ids["stages"][v] for v in request["stage_instance_ids"]]})
        stages = [{"id": ids["stages"][s["id"]], "request_id": ids["requests"][s["request_id"]],
                   "shared_stage_id": s["shared_stage_id"], "application": applications[s["shared_stage_id"]],
                   "legal_units": list(s["legal_units"])} for s in scene["stage_instances"]]
        scenes.append({"id": sid, "weight": scene["weight"], "requests": requests,
                       "stage_instances": stages,
                       "dependencies": [[ids["stages"][a], ids["stages"][b]] for a, b in scene["dependencies"]],
                       "entry": {"temperature_degC": list(map(str, initial)),
                                 "domain_opp": {did: d["entry_opp"] for did, d in physical["domains"].items()},
                                 "unfinished_work": []},
                       "maximum_temperature_degC": [str(maximum)] * len(initial)})
    instance = {
        "schema_version": target_config["schema_version"], "id": instance_id,
        "condition_id": data["variant_id"], "experiment_group": data["derivation"]["axis"],
        "sample_id": data["root_family_id"], "platform": deepcopy(physical),
        "execution_rules": deepcopy(target_config["execution_rules"]),
        "units": deepcopy(target_config["units"]), "window_ms": str(window),
        "start_grid_ms": data["start_grid_ms"], "response_variant": "H",
        "stage_modes": _modes(bundle, data, allowed, physical), "scenarios": scenes,
        "settings": {"window_ms": str(window), "start_grid_ms": data["start_grid_ms"],
                     "deadline_beta": str(exact(deadline_receipt["beta"])), "response_variant": "H",
                     "maximum_temperature_degC": str(maximum)},
        "ablation_input": False, "status": "input_only_not_evaluated",
    }
    receipt = {
        "schema_version": SCHEMA, "state": "EXPLICIT_INPUT_EXPORTED_NOT_EVALUATED",
        "source_bundle_hash": bundle["bundle_hash"], "source_contract_hash": bundle["contract_hash"],
        "deadline_receipt_hash": deadline_receipt["receipt_hash"],
        "window_receipt_hash": window_receipt["receipt_hash"], "window_member_key": member_key,
        "source_config_file_sha256": SOURCE_SHA256,
        "source_config_content_hash": content_hash(config), "config_hash": content_hash(target_config),
        "physical_platform_hash": content_hash(physical), "instance_hash": content_hash(instance),
        "identity_map": identity, "inverse_identity_map": inverse,
        "active_shared_legal_units": {s: list(v) for s, v in allowed.items()},
        "required_outputs_by_application": outputs,
        "beta": str(exact(deadline_receipt["beta"])), "window_ms": str(window),
        "reference_deployment_imported": False, "reference_timetable_imported": False,
        "fixed_deployment": None, "formal_initial_solution": None,
        "thermal_status": "NOT_EVALUATED", "energy_status": "NOT_EVALUATED",
        "method_readiness": {"whole_milp": "COMMON_INPUT_ONLY_NOT_RUN",
                             "heft": "COMMON_INPUT_ONLY_NOT_RUN", "sa": "COMMON_INPUT_ONLY_NOT_RUN",
                             "linked_C": "NEIGHBORHOOD_GENERALIZATION_REQUIRED_NOT_RUN"},
    }
    receipt["receipt_hash"] = content_hash(receipt)
    return {"config": target_config, "instance": instance, "receipt": receipt}
