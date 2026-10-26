"""E4b uses original one/two simultaneous request-copy conditions.

Each copy retains the original per-request deadline and original deployment
identity. Shared units persist across copies/scenes; OPP/start remain separate
execution choices. No search, temperature propagation or real SAFE occurs here.
"""
from copy import deepcopy
from fractions import Fraction as F

from control_policy import AUTO_LOW_IMMEDIATE_V1, resolve_idle_policy, with_auto_low_idle
from h02_pair_preflight.common import ContractError, require, sha
from inputs import build_instance, load_config

BASE_ID="base__R1"
DOUBLE_ID="requests_2__R1"
PROBLEM_IDS=(BASE_ID,DOUBLE_ID)
COPY_COUNTS={BASE_ID:1,DOUBLE_ID:2}
LABEL_FIELDS=("id","condition_id","experiment_group","ablation_input")
ALLOWED_DIFFERENCE_PATHS=("/id","/condition_id","/experiment_group","/ablation_input",
    "/settings/requests_per_application","/scenarios/<scene-index>/requests",
    "/scenarios/<scene-index>/stage_instances","/scenarios/<scene-index>/dependencies")


def _reference_config(config=None):
    frozen=with_auto_low_idle(load_config())
    if config is not None:
        require(sha(with_auto_low_idle(config))==sha(frozen),"CONFIG_DRIFT_FROM_FROZEN_SOURCE")
    return frozen


def prepare_inputs(config=None):
    """Fresh original generator expansion; never edit frozen default counts."""
    frozen=_reference_config(config)
    return {pid:{"config":deepcopy(frozen),"instance":build_instance(frozen,pid),
                 "objective":"FULL"} for pid in PROBLEM_IDS}


def weighted_request_denominator_if_all_complete(instance):
    """Expected requests per scenario, for a wholly complete weighted energy.

    The numerator is sum(scene_weight * complete_window_energy), hence its
    matching denominator is sum(scene_weight * request_count), not the raw
    count across mutually alternative scenarios. This function does not certify
    completion; later result code must first require complete valid evidence.
    """
    scenes=instance["scenarios"]
    weights=[F(s["weight"]) for s in scenes]
    require(bool(scenes) and all(w>=0 for w in weights) and sum(weights)==1,"INVALID_SCENARIO_WEIGHTS")
    denominator=sum((w*len(s["requests"]) for w,s in zip(weights,scenes)),F(0))
    require(denominator>0,"EMPTY_WEIGHTED_REQUEST_COUNT")
    return denominator


def _normalize(instance,base):
    normalized=deepcopy(instance)
    for name in LABEL_FIELDS:normalized[name]=deepcopy(base[name])
    normalized["settings"]["requests_per_application"]=base["settings"]["requests_per_application"]
    for scene in normalized["scenarios"]:
        scene["requests"]=[r for r in scene["requests"] if r["copy_index"]==1]
        request_ids={r["id"] for r in scene["requests"]}
        scene["stage_instances"]=[s for s in scene["stage_instances"] if s["request_id"] in request_ids]
        stage_ids={s["id"] for s in scene["stage_instances"]}
        scene["dependencies"]=[edge for edge in scene["dependencies"]
                               if edge[0] in stage_ids and edge[1] in stage_ids]
    return normalized


def _difference_paths(left,right,path=""):
    if type(left) is not type(right):return [path]
    if isinstance(left,dict):
        return [p for key in sorted(set(left)|set(right))
                for p in ([path+"/"+str(key)] if key not in left or key not in right else
                          _difference_paths(left[key],right[key],path+"/"+str(key)))]
    if isinstance(left,list):
        if len(left)!=len(right):return [path]
        return [p for i,(a,b) in enumerate(zip(left,right))
                for p in _difference_paths(a,b,path+"/"+str(i))]
    return [] if left==right else [path]


def _copy_evidence(instance,base):
    expected_copies=COPY_COUNTS[instance["id"]]
    base_scenes={s["id"]:s for s in base["scenarios"]}
    scenes={}
    for scene in instance["scenarios"]:
        old=base_scenes[scene["id"]]
        old_by_app={r["application"]:r for r in old["requests"]}
        stage_by_id={s["id"]:s for s in scene["stage_instances"]}
        copies={}
        for app,original in old_by_app.items():
            members=[r for r in scene["requests"] if r["application"]==app]
            require({r["copy_index"] for r in members}==set(range(1,expected_copies+1)),"REQUEST_COPY_COVERAGE")
            reports=[]
            for r in members:
                require(F(r["release_ms"])==0==F(original["release_ms"]),"SIMULTANEOUS_RELEASE_DRIFT")
                for field in ("release_ms","reference_CPU_H_chain_ms","relative_deadline_ms","deadline_ms"):
                    require(r[field]==original[field],"PER_REQUEST_SERVICE_CONDITION_DRIFT:"+field)
                shared_ids=[stage_by_id[sid]["shared_stage_id"] for sid in r["stage_instance_ids"]]
                old_shared=[next(s["shared_stage_id"] for s in old["stage_instances"] if s["id"]==sid)
                            for sid in original["stage_instance_ids"]]
                require(shared_ids==old_shared,"COPY_DEPLOYMENT_IDENTITY_DRIFT")
                reports.append({"request_id":r["id"],"copy_index":r["copy_index"],
                    "release_ms":r["release_ms"],"deadline_ms":r["deadline_ms"],"shared_stage_ids":shared_ids})
            copies[app]=reports
        scenes[scene["id"]]={"requests":len(scene["requests"]),"stage_executions":len(scene["stage_instances"]),
            "dependencies":len(scene["dependencies"]),"weight":scene["weight"],"application_copies":copies}
    return scenes


def _validate(packets):
    require(isinstance(packets,dict) and set(packets)==set(PROBLEM_IDS),"EXACT_TWO_REQUEST_INPUTS_REQUIRED")
    frozen=_reference_config()
    expected={pid:build_instance(frozen,pid) for pid in PROBLEM_IDS}
    base=packets[BASE_ID]["instance"]
    evidence={}
    for pid in PROBLEM_IDS:
        packet=packets[pid]
        require(isinstance(packet,dict) and set(packet)=={"config","instance","objective"},"PACKET_FIELD_SET")
        require(sha(packet["config"])==sha(frozen),"CONFIG_DRIFT_FROM_FROZEN_SOURCE")
        require(packet["objective"]=="FULL","REQUEST_EXPERIMENT_REQUIRES_FULL_OBJECTIVE")
        instance=packet["instance"]
        require(instance["id"]==pid,"PROBLEM_ID_MISMATCH")
        require(type(instance["settings"]["requests_per_application"]) is int and
                instance["settings"]["requests_per_application"]==COPY_COUNTS[pid],"REQUEST_COUNT_DRIFT")
        require(resolve_idle_policy(instance)==AUTO_LOW_IMMEDIATE_V1,"IDLE_POLICY_DRIFT")
        require(sha(instance)==sha(expected[pid]),"INPUT_DIFFERS_FROM_ORIGINAL_GENERATOR")
        normalized=_normalize(instance,base)
        require(sha(normalized)==sha(base),"NON_COPY_INPUT_DIFFERENCE")
        require(sha(instance["stage_modes"])==sha(base["stage_modes"]),"MODE_CATALOG_DRIFT")
        scenes=_copy_evidence(instance,base)
        denominator=weighted_request_denominator_if_all_complete(instance)
        require(denominator==2*COPY_COUNTS[pid],"WEIGHTED_REQUEST_DENOMINATOR_DRIFT")
        evidence[pid]={"input_sha256":sha(instance),"config_sha256":sha(packet["config"]),
            "requests_per_application":COPY_COUNTS[pid],"scenes":scenes,
            "total_requests_across_alternative_scenarios":sum(len(s["requests"]) for s in instance["scenarios"]),
            "total_stage_executions_across_alternative_scenarios":sum(len(s["stage_instances"]) for s in instance["scenarios"]),
            "deployment_stage_count":len(instance["stage_modes"]),
            "total_catalog_mode_count":sum(len(m) for m in instance["stage_modes"].values()),
            "weighted_request_denominator_if_all_complete":str(denominator),
            "normalized_input_sha256":sha(normalized),"exact_difference_paths_from_base":_difference_paths(base,instance)}
    return {"state":"STATIC_REQUEST_INPUT_CONTRACT_PASSED","source_config_sha256":sha(frozen),
        "allowed_difference_paths":list(ALLOWED_DIFFERENCE_PATHS),"inputs":evidence,
        "copy_semantics":"All copies released at 0 with unchanged individual deadlines; concrete Stage unit shared across copies/scenes, OPP/start per execution.",
        "per_request_energy_formula":"sum(weight * complete_window_energy) / sum(weight * request_count)",
        "per_request_energy_scope":"Only after every required scene has complete valid safety/energy evidence. No partial-prefix or raw cross-scenario total denominator.",
        "not_a_nested_domain_claim":"Different copy counts are different workloads; no common-domain or per-request energy monotonicity is asserted.",
        "candidate_search_performed":False,"thermal_propagation_performed":False,"real_SAFE_created":False}


def validate_inputs(packets):
    """Reject drift beyond original copy expansion, without evaluating candidates."""
    try:return _validate(packets)
    except ContractError:raise
    except (KeyError,TypeError,ValueError,AttributeError,ZeroDivisionError,StopIteration) as error:
        raise ContractError("MALFORMED_REQUEST_INPUT:"+type(error).__name__) from error
