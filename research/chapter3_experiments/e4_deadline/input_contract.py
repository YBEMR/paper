"""E4a changes only original declared deadline scale on one physical platform.

Fresh expansion uses the unchanged generator. CPU-H reference chain lengths,
release times, response H, Stage modes and thermal limits remain fixed. These
functions do not search, propagate temperature or create any real SAFE.
"""
from copy import deepcopy
from fractions import Fraction as F

from control_policy import AUTO_LOW_IMMEDIATE_V1, resolve_idle_policy, with_auto_low_idle
from h02_pair_preflight.common import ContractError, require, sha
from inputs import build_instance, load_config

PROBLEM_IDS=("beta_1.0__R1", "base__R1", "beta_1.6__R1")
BASE_ID="base__R1"
BETAS={PROBLEM_IDS[0]:"1.0", BASE_ID:"1.3", PROBLEM_IDS[2]:"1.6"}
LABEL_FIELDS=("id", "condition_id", "experiment_group", "ablation_input")
ALLOWED_DIFFERENCE_PATHS=("/id", "/condition_id", "/experiment_group", "/ablation_input",
    "/settings/deadline_beta", "/scenarios/<scene-index>/requests/<request-index>/relative_deadline_ms",
    "/scenarios/<scene-index>/requests/<request-index>/deadline_ms")


def _reference_config(config=None):
    frozen=with_auto_low_idle(load_config())
    if config is not None:
        require(sha(with_auto_low_idle(config))==sha(frozen), "CONFIG_DRIFT_FROM_FROZEN_SOURCE")
    return frozen


def prepare_inputs(config=None):
    """Return independent FULL packets from the three existing conditions."""
    frozen=_reference_config(config)
    return {pid:{"config":deepcopy(frozen), "instance":build_instance(frozen,pid),
                 "objective":"FULL"} for pid in PROBLEM_IDS}


def _normalize(instance,base):
    normalized=deepcopy(instance)
    for field in LABEL_FIELDS: normalized[field]=deepcopy(base[field])
    normalized["settings"]["deadline_beta"]=base["settings"]["deadline_beta"]
    originals={scene["id"]:scene for scene in base["scenarios"]}
    require(set(originals)=={s["id"] for s in instance["scenarios"]}, "SCENE_IDENTITY_DRIFT")
    for scene in normalized["scenarios"]:
        original_requests={r["id"]:r for r in originals[scene["id"]]["requests"]}
        require(set(original_requests)=={r["id"] for r in scene["requests"]}, "REQUEST_IDENTITY_DRIFT")
        for request in scene["requests"]:
            source=original_requests[request["id"]]
            for field in ("relative_deadline_ms", "deadline_ms"):
                request[field]=source[field]
    return normalized


def _difference_paths(left,right,path=""):
    if type(left) is not type(right): return [path]
    if isinstance(left,dict):
        return [item for key in sorted(set(left)|set(right))
                for item in ([path+"/"+str(key)] if key not in left or key not in right else
                             _difference_paths(left[key],right[key],path+"/"+str(key)))]
    if isinstance(left,list):
        if len(left)!=len(right): return [path]
        return [item for index,(a,b) in enumerate(zip(left,right))
                for item in _difference_paths(a,b,path+"/"+str(index))]
    return [] if left==right else [path]


def _deadline_formula_evidence(instance,config):
    sample=next(s for s in config["samples"] if s["id"]==instance["sample_id"])
    references={}
    for stage in config["stage_catalog"]:
        app=stage["application"]
        references[app]=references.get(app,F(0))+F(stage["profiles"]["CPU"]["d_ref_ms"])*F(sample["duration_scale"][app])
    beta=F(instance["settings"]["deadline_beta"])
    records={}
    for scene in instance["scenarios"]:
        requests={}
        for request in scene["requests"]:
            app=request["application"]
            reference=references[app]
            relative=beta*reference
            deadline=F(request["release_ms"])+relative
            require(F(request["reference_CPU_H_chain_ms"])==reference,
                    "CPU_H_DEADLINE_REFERENCE_DRIFT")
            require(F(request["relative_deadline_ms"])==relative and F(request["deadline_ms"])==deadline,
                    "DEADLINE_FORMULA_MISMATCH")
            require(deadline<=F(instance["window_ms"]), "DEADLINE_OUTSIDE_FIXED_WINDOW")
            requests[request["id"]]={"application":app, "release_ms":request["release_ms"],
                "reference_CPU_H_chain_ms":str(reference), "beta":str(beta),
                "relative_deadline_ms":str(relative), "deadline_ms":str(deadline)}
        records[scene["id"]]=requests
    return {"formula":"deadline = unchanged release + beta * sum(scaled CPU-H reference Stage durations)",
            "reference_source":"original stage_catalog CPU d_ref_ms and sample duration_scale; independent of response alpha",
            "application_reference_chain_ms":{k:str(v) for k,v in references.items()},
            "requests":records}


def _validate(packets):
    require(isinstance(packets,dict) and set(packets)==set(PROBLEM_IDS), "EXACT_THREE_DEADLINE_INPUTS_REQUIRED")
    frozen=_reference_config()
    expected={pid:build_instance(frozen,pid) for pid in PROBLEM_IDS}
    base=packets[BASE_ID]["instance"]
    evidence={}
    for pid in PROBLEM_IDS:
        packet=packets[pid]
        require(isinstance(packet,dict) and set(packet)=={"config","instance","objective"}, "PACKET_FIELD_SET")
        require(sha(packet["config"])==sha(frozen), "CONFIG_DRIFT_FROM_FROZEN_SOURCE")
        require(packet["objective"]=="FULL", "DEADLINE_EXPERIMENT_REQUIRES_FULL_OBJECTIVE")
        instance=packet["instance"]
        require(instance["id"]==pid, "PROBLEM_ID_MISMATCH")
        require(instance["settings"]["deadline_beta"]==BETAS[pid], "DEADLINE_BETA_DRIFT")
        require(resolve_idle_policy(instance)==AUTO_LOW_IMMEDIATE_V1, "IDLE_POLICY_DRIFT")
        require(sha(instance)==sha(expected[pid]), "INPUT_DIFFERS_FROM_ORIGINAL_GENERATOR")
        normalized=_normalize(instance,base)
        require(sha(normalized)==sha(base), "NON_DEADLINE_INPUT_DIFFERENCE")
        evidence[pid]={"input_sha256":sha(instance), "config_sha256":sha(packet["config"]),
            "beta":BETAS[pid], "normalized_input_sha256":sha(normalized),
            "deadline_formula":_deadline_formula_evidence(instance,frozen),
            "exact_difference_paths_from_base":_difference_paths(base,instance),
            "deployment_stage_count":len(instance["stage_modes"]),
            "total_catalog_mode_count":sum(len(m) for m in instance["stage_modes"].values())}
    inclusion=[]
    for tight,loose in zip(PROBLEM_IDS,PROBLEM_IDS[1:]):
        tighter=packets[tight]["instance"]; looser=packets[loose]["instance"]
        count=0
        for ts,ls in zip(tighter["scenarios"],looser["scenarios"]):
            for tr,lr in zip(ts["requests"],ls["requests"]):
                require(tr["id"]==lr["id"] and F(tr["release_ms"])==F(lr["release_ms"]) and
                        F(tr["deadline_ms"])<=F(lr["deadline_ms"]), "DEADLINE_DOMAIN_INCLUSION_FAILED")
                count+=1
        inclusion.append({"subset":tight, "superset":loose, "request_deadline_checks":count,
                          "all_other_fields_identical_after_declared_normalization":True})
    return {"state":"STATIC_DEADLINE_INPUT_CONTRACT_PASSED", "source_config_sha256":sha(frozen),
            "allowed_difference_paths":list(ALLOWED_DIFFERENCE_PATHS), "inputs":evidence,
            "deadline_domain_inclusions":inclusion,
            "domain_scope_note":"Only deadlines relax. Same candidate keeps identical power and thermal model; heuristic outcomes need not be monotone.",
            "ablation_input_note":"Original labels: beta conditions false, shared base true; no physical effect.",
            "candidate_search_performed":False, "thermal_propagation_performed":False,
            "real_SAFE_created":False}


def validate_inputs(packets):
    """Reject drift beyond the original generator's declared beta conditions."""
    try: return _validate(packets)
    except ContractError: raise
    except (KeyError,TypeError,ValueError,AttributeError,ZeroDivisionError,StopIteration) as error:
        raise ContractError("MALFORMED_DEADLINE_INPUT:"+type(error).__name__) from error
