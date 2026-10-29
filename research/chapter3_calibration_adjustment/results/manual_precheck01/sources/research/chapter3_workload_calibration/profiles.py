"""Explicit synthetic profiles drawn from the unchanged P0 prototype catalog.

This module only transforms declared input data. It does not evaluate energy,
heat, schedules or algorithms. No settings or seeds have scientific defaults.
"""

from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP, localcontext
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path


SOURCE_SHA256 = "615be096bfbcb3e7c53ba9b0810d888264d48adbc428f1f7d2f94a5c6a29a4fe"
CATEGORIES = ("cpu_only", "gpu_friendly", "npu_friendly", "multi_device")
CPU_PROTOTYPES = ("A.pre", "A.post", "B.pre", "B.post", "C.pre", "C.post")
UNITS = {"CPU": ("CPU1", "CPU2"), "GPU": ("GPU0",), "NPU": ("NPU0",)}


class ProfileError(ValueError):
    pass


def _require(condition, reason):
    if not condition:
        raise ProfileError(reason)


def _exact(value):
    _require(type(value) in (str, int) or isinstance(value, Fraction),
             "EXACT_SCALAR_REQUIRED")
    try:
        return Fraction(value)
    except (ValueError, TypeError, ZeroDivisionError) as error:
        raise ProfileError("INVALID_EXACT_SCALAR") from error


def _fields(value, fields, name):
    _require(isinstance(value, dict) and set(value) == set(fields),
             "EXPLICIT_FIELDS_REQUIRED:" + name)


def _weights(value, keys, name):
    _fields(value, keys, name)
    converted = {key: _exact(value[key]) for key in keys}
    _require(all(weight >= 0 for weight in converted.values()) and
             sum(converted.values(), Fraction(0)) == 1,
             "PROBABILITIES_MUST_SUM_TO_ONE:" + name)
    return converted


def validate_settings(settings):
    _fields(settings, ("category_weights", "cpu_prototype_weights", "workload",
                       "specialization_probabilities"), "settings")
    category = _weights(settings["category_weights"], CATEGORIES, "category_weights")
    cpu = _weights(settings["cpu_prototype_weights"], CPU_PROTOTYPES,
                   "cpu_prototype_weights")
    workload = settings["workload"]
    _fields(workload, ("minimum", "maximum", "quantum", "precision", "rounding"),
            "workload")
    minimum, maximum, quantum = (_exact(workload[key]) for key in
                                  ("minimum", "maximum", "quantum"))
    _require((minimum, maximum, quantum) == (Fraction(1, 2), Fraction(2), Fraction(1, 1000)),
             "V1_WORKLOAD_RANGE_OR_QUANTUM_CHANGED")
    _require(type(workload["precision"]) is int and workload["precision"] == 60 and
             workload["rounding"] == "ROUND_HALF_UP", "EXPLICIT_NUMERIC_RULE_REQUIRED")
    _fields(settings["specialization_probabilities"], ("gpu_friendly", "npu_friendly"),
            "specialization_probabilities")
    specialization = {key: _exact(value)
                      for key, value in settings["specialization_probabilities"].items()}
    _require(all(0 <= value <= 1 for value in specialization.values()),
             "INVALID_SPECIALIZATION_PROBABILITY")
    return category, cpu, specialization


def substream_digest(*, namespace, seed, root_id, purpose, app_id, stage_id, axis):
    """Hash a full named slot; call order and unrelated slots cannot change it."""
    for value in (namespace, root_id, purpose, app_id, stage_id, axis):
        _require(isinstance(value, str) and bool(value.strip()), "NAMED_SUBSTREAM_REQUIRED")
    _require(type(seed) is int and seed >= 0, "EXPLICIT_NONNEGATIVE_INTEGER_SEED_REQUIRED")
    key = [namespace, seed, root_id, purpose, app_id, stage_id, axis]
    return sha256(json.dumps(key, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def _categorical(weights, digest):
    value, cumulative = Fraction(int(digest, 16), 1 << 256), Fraction(0)
    for key, weight in weights.items():
        cumulative += weight
        if value < cumulative:
            return key
    raise ProfileError("CATEGORICAL_SELECTION_FAILED")


def _multiplier(digest, workload):
    with localcontext() as ctx:
        ctx.prec = workload["precision"]
        ctx.rounding = ROUND_HALF_UP
        minimum_fraction, maximum_fraction = (_exact(workload[key]) for key in ("minimum", "maximum"))
        minimum = Decimal(minimum_fraction.numerator) / Decimal(minimum_fraction.denominator)
        maximum = Decimal(maximum_fraction.numerator) / Decimal(maximum_fraction.denominator)
        # SHA-256 supplies a reproducible [0,1) rational draw; Decimal arithmetic
        # and the final rounding rule are part of the explicit implementation.
        uniform = Decimal(int(digest, 16)) / Decimal(1 << 256)
        raw = (minimum.ln() + uniform * (maximum.ln() - minimum.ln())).exp()
        quantum_fraction = _exact(workload["quantum"])
        quantum = Decimal(quantum_fraction.numerator) / Decimal(quantum_fraction.denominator)
        quantized = raw.quantize(quantum, rounding=ROUND_HALF_UP)
        return str(quantized), str(raw), str(uniform)


def load_catalog(path):
    raw = Path(path).read_bytes()
    digest = sha256(raw).hexdigest()
    _require(digest == SOURCE_SHA256, "P0_SOURCE_HASH_MISMATCH")
    source = json.loads(raw.decode("utf-8"))
    platform = source["platform"]
    time_platform = {
        "units": [{"id": unit["id"], "domain_id": unit["domain_id"]}
                  for unit in platform["units"]],
        "domains": {domain: {"reference_opp": item["reference_opp"],
                              "opps": {opp: {"frequency_GHz": details["frequency_GHz"]}
                                       for opp, details in item["opps"].items()}}
                    for domain, item in platform["domains"].items()}}
    prototypes = {}
    for stage in source["stage_catalog"]:
        prototypes[stage["id"]] = {
            "units": {unit: deepcopy(profile)
                      for device_class, profile in stage["profiles"].items()
                      for unit in UNITS[device_class]}}
    rules = {key: source["execution_rules"][key]
             for key in ("preemption", "migration", "in_stage_opp_change",
                         "switch_only_when_domain_empty", "extra_transfer_time_ms",
                         "extra_switch_time_ms", "extra_handoff_time_ms",
                         "extra_transfer_energy_J", "extra_switch_energy_J",
                         "extra_handoff_energy_J", "interval_convention")}
    rules.update(idle_holds_last_opp=False, idle_policy="auto_low_immediate_v1",
                 idle_delay_ms="0")
    return {"time_platform": time_platform, "execution_rules": rules,
            "physical_platform": deepcopy(platform), "prototypes": prototypes,
            "source_sha256": digest, "source_parameter_origin": source["metadata"]["parameter_origin"],
            "source_execution_rules": deepcopy(source["execution_rules"])}


def make_profile(catalog, *, namespace, seed, root_id, app_id, stage_id, pool, settings):
    category_weights, cpu_weights, special_rates = validate_settings(settings)
    _require(pool in ("cpu_common", "heterogeneous"), "UNKNOWN_COMPATIBILITY_POOL")
    _require(catalog.get("source_sha256") == SOURCE_SHA256, "CATALOG_SOURCE_IDENTITY_MISMATCH")
    slot = dict(namespace=namespace, seed=seed, root_id=root_id, app_id=app_id,
                stage_id=stage_id, axis="fixed_stage_identity")
    digests = {purpose: substream_digest(**slot, purpose=purpose)
               for purpose in ("category", "cpu_prototype", "workload", "specialization")}
    category = _categorical(category_weights, digests["category"])
    prototype_id = (_categorical(cpu_weights, digests["cpu_prototype"]) if category == "cpu_only"
                    else {"gpu_friendly": "C.main", "npu_friendly": "B.main",
                          "multi_device": "A.main"}[category])
    prototype = catalog["prototypes"][prototype_id]
    profiles = deepcopy(prototype["units"])
    multiplier, raw_multiplier, uniform = _multiplier(digests["workload"], settings["workload"])
    specialized = (pool == "heterogeneous" and category in special_rates and
                   Fraction(int(digests["specialization"], 16), 1 << 256) < special_rates[category])
    removed_units = []
    if specialized:
        for unit in ("CPU1", "CPU2"):
            profiles.pop(unit)
            removed_units.append(unit)
    multiplier_exact = Fraction(multiplier)
    for profile in profiles.values():
        profile["d_ref_ms"] = str(Fraction(profile["d_ref_ms"]) * multiplier_exact)
    time_profile = {
        "work_units": str(multiplier_exact),
        "units": {unit: {"d_ref_ms": profile["d_ref_ms"], "alpha": profile["alpha"],
                          "legal_opps": ["L", "M", "H"]}
                  for unit, profile in sorted(profiles.items())}}
    physical_profile = {"prototype_id": prototype_id, "source_sha256": SOURCE_SHA256,
                        "work_units": str(multiplier_exact), "units": profiles}
    trace = {"slot": slot, "substream_sha256": digests, "category": category,
             "prototype_id": prototype_id, "pool": pool, "multiplier": multiplier,
             "pre_quantization_multiplier": raw_multiplier, "uniform_draw": uniform,
             "specialized": specialized, "removed_units": removed_units,
             "original_legal_units": sorted(prototype["units"]),
             "settings_sha256": sha256(json.dumps(settings, sort_keys=True, ensure_ascii=False,
                                                   separators=(",", ":")).encode("utf-8")).hexdigest(),
             "random_key_includes_scale_or_topology": False,
             "power_rule": "q_ref*(V/V_ref)^2*(f/f_ref)",
             "reference_activity_power_scaled": False}
    return {"time_profile": time_profile, "physical_profile": physical_profile, "trace": trace}
