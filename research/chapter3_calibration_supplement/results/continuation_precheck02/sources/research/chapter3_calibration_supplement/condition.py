"""One supplemental time diagnostic; archived comparisons are never rescheduled.

Archive authentication, authorization, one-shot claims and clocks belong to the
runtime. This layer accepts an explicit call and supplies checkpoint callbacks.
It never invokes workload sampling, formal optimization or thermal integration.
"""

from copy import deepcopy

from research.chapter3_deadline_reference.contract import ContractError, content_hash, exact
from research.chapter3_deadline_reference.deadlines import inherit_deadlines
from research.chapter3_workload_calibration.evaluation import evaluate_condition
from research.chapter3_workload_calibration.generator import (
    inherited_mapping, request_sources, validate_transform)
from research.chapter3_calibration_adjustment.transforms import (
    BRANCH_RULE, STAGGER_RULE, derive_branch_multi, derive_staggered,
    validate_adjustment, validated_base_h)
from research.chapter3_calibration_adjustment.window_policy import make_window_receipt


BETAS = ("1", "1.3", "1.6", "2")
BETA_KEYS = tuple(str(exact(b)) for b in BETAS)
OPPS = ("H", "M", "L")
EMPTY_COUNTERS = {"mapping_constructions": 0, "timetable_constructions": 0,
                  "S1_projections": 0, "formal_method_calls": 0,
                  "thermal_integrations": 0}


def require(ok, message):
    if not ok:
        raise ContractError(message)


def _validate_inputs(call, parent, comparisons):
    require(isinstance(call, dict) and call.get("axis") in ("S4", "S7"), "SUPPLEMENT_AXIS")
    root, scale, axis = call.get("root_id"), call.get("scale"), call["axis"]
    require(isinstance(root, str) and root and isinstance(scale, int) and scale > 0,
            "SUPPLEMENT_ROOT_SCALE")
    rule = BRANCH_RULE if axis == "S4" else STAGGER_RULE
    comparison_ids = ([root + "__S4_serial", root + "__S4_layered"] if axis == "S4"
                      else [root + "__S7"])
    expected = {"condition_id": root + "__" + axis + "_" + rule,
                "root_id": root, "scale": scale, "axis": axis, "rule": rule,
                "parent_id": f"{root}__base_{scale}", "comparison_ids": comparison_ids}
    require(call == expected, "SUPPLEMENT_CALL_DRIFT")
    require(isinstance(parent, dict) and parent.get("call", {}).get("condition_id") == call["parent_id"],
            "SUPPLEMENT_PARENT_RECEIPT_ID")
    validated_base_h(parent)
    base = parent["workload"]
    require(base["time_contract"]["root_family_id"] == root and
            base["provenance"]["root_id"] == root and base["provenance"]["scale"] == scale,
            "SUPPLEMENT_PARENT_ROOT_SCALE")
    require(set(parent["deadlines"]) == set(BETA_KEYS), "SUPPLEMENT_FOUR_BETAS_REQUIRED")
    require(isinstance(comparisons, dict) and set(comparisons) == set(comparison_ids),
            "SUPPLEMENT_COMPARISON_COVERAGE")
    parent_mapping = parent["reference"]["mapping_record"]["mapping"]
    origin = parent["reference"]["mapping_origin_hash"]
    for condition_id, evidence in comparisons.items():
        require(evidence.get("state") == "TIME_CALIBRATION_COMPLETE" and
                evidence.get("call", {}).get("condition_id") == condition_id,
                "SUPPLEMENT_COMPARISON_RECEIPT_ID")
        child = evidence["workload"]
        require(child["provenance"]["root_id"] == root and child["provenance"]["scale"] == scale,
                "SUPPLEMENT_COMPARISON_ROOT_SCALE")
        require(child["time_contract"]["derivation"]["axis"] == axis,
                "SUPPLEMENT_COMPARISON_AXIS")
        if axis == "S4":
            topology = "serial" if condition_id.endswith("_serial") else "layered"
            require(child["time_contract"]["topology_id"] == topology,
                    "SUPPLEMENT_COMPARISON_TOPOLOGY")
        # This old validator is applied only to the archived old transforms.
        # The new staggered transform uses validate_adjustment below.
        validate_transform(base, child)
        require(set(evidence["deadlines"]) == set(BETA_KEYS), "SUPPLEMENT_COMPARISON_BETAS")
        for beta in BETA_KEYS:
            expected_due = inherit_deadlines(base["time_contract"], parent["deadlines"][beta],
                                             child["time_contract"],
                                             request_sources=request_sources(base, child))
            require(evidence["deadlines"][beta] == expected_due, "SUPPLEMENT_COMPARISON_DEADLINES")
        reference = evidence["reference"]
        require(reference["contract_hash"] == child["contract_hash"] and
                reference["mapping_origin_hash"] == origin and
                reference["mapping_record"]["mapping"] == inherited_mapping(parent_mapping, child),
                "SUPPLEMENT_COMPARISON_MAPPING")
        require(set(reference["timetables"]) == set(reference["checks"]) == set(OPPS),
                "SUPPLEMENT_COMPARISON_HML")
        require(evidence.get("thermal_status") == evidence.get("energy_status") == "NOT_EVALUATED",
                "SUPPLEMENT_COMPARISON_SCOPE")


def evaluate_supplement(call, parent_evidence, comparison_evidence, *, progress):
    """Construct exactly three new tables, inherit four betas, attach group W.

The parent and all comparison evidence are immutable inputs. Every synchronous
or old-topology timetable remains an archived result, not a fresh construction.
Callbacks may raise a timeout at any checkpoint; partial work is never returned
as a complete condition. Missed deadlines are observations and do not raise.
"""
    counters = dict(EMPTY_COUNTERS)
    progress("SUPPLEMENT_VALIDATION_STARTED", dict(counters))
    before = content_hash([parent_evidence, comparison_evidence])
    _validate_inputs(call, parent_evidence, comparison_evidence)
    progress("SUPPLEMENT_ARCHIVE_INPUTS_VALIDATED", dict(counters))
    bundle = (derive_branch_multi(parent_evidence["workload"]) if call["axis"] == "S4"
              else derive_staggered(parent_evidence))
    validate_adjustment(parent_evidence, bundle)
    progress("SUPPLEMENT_TRANSFORM_VALIDATED", dict(counters))

    def checkpoint(phase, current):
        counters.update(current)
        progress(phase, dict(counters))

    evidence = evaluate_condition(bundle, {"betas": list(BETAS)},
                                   parent=parent_evidence, progress=checkpoint)
    require(evidence["counters"] == {**EMPTY_COUNTERS, "timetable_constructions": 3},
            "SUPPLEMENT_REFERENCE_CALL_COUNT")
    require(evidence["reference"]["mapping_origin_hash"] ==
            parent_evidence["reference"]["mapping_origin_hash"], "SUPPLEMENT_MAPPING_REBUILT")
    if call["axis"] == "S4":
        members = {"serial": comparison_evidence[call["comparison_ids"][0]],
                   "branch_multi": evidence,
                   "layered": comparison_evidence[call["comparison_ids"][1]]}
    else:
        members = {"single": parent_evidence,
                   "synchronous": comparison_evidence[call["comparison_ids"][0]],
                   "staggered": evidence}
    windows = {}
    for beta, key in zip(BETAS, BETA_KEYS):
        progress("WINDOW_" + key + "_STARTED", dict(counters))
        windows[key] = make_window_receipt(call["root_id"] + "__" + call["axis"] + "__beta_" + key,
                                           call["axis"], members, beta=beta, baseline=parent_evidence)
        progress("WINDOW_" + key + "_VERIFIED", dict(counters))
    require(content_hash([parent_evidence, comparison_evidence]) == before,
            "SUPPLEMENT_ARCHIVED_INPUT_MUTATION")
    evidence.update(call=deepcopy(call), window_receipts=windows,
                    comparison_bindings={name: {
                        "contract_hash": old["workload"]["contract_hash"],
                        "bundle_hash": old["workload"]["bundle_hash"],
                        "HML_timetable_hashes": {opp: old["reference"]["checks"][opp]["timetable_hash"]
                                                 for opp in OPPS},
                        "deadline_receipt_hashes": {key: old["deadlines"][key]["receipt_hash"]
                                                    for key in BETA_KEYS}}
                        for name, old in {call["parent_id"]: parent_evidence,
                                          **comparison_evidence}.items()},
                    diagnostic_scope="TIME_ONLY_ORIGINAL_MAPPING_AND_DEADLINES_NO_BETA_SELECTION")
    progress("SUPPLEMENT_COMPLETE", dict(counters))
    return evidence
