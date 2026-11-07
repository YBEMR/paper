"""Read stored evidence and prepare an INERT two-case validation proposal.

No new schedule, HEFT construction, optimizer, physical integration, or real
candidate assessment is allowed. All writes stay in this new artifact folder.
"""
from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timezone, timedelta
from fractions import Fraction as F
import hashlib
import importlib.abc
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
import traceback
from unittest.mock import patch

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[3]
LEGACY = REPO / "research/chapter3_experiments"
PRIOR = OUT.parent / "cloud_mechanism_20261107"
sys.path[:0] = [str(REPO), str(LEGACY)]
CASES = ("base__R2", "base__R5")  # Fixed before static outcome inspection.
CLIENT_TZ = timezone(timedelta(hours=8))


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(name, value):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def parts(instance, receipt):
    return {k: [str(sum(F(s["weight"]) * F(receipt["scenes"][s["id"]]["energy_components_J"][k][j])
        for s in instance["scenarios"])) for j in (0, 1)]
        for k in ("activity", "baseline", "external_common", "temperature_correction")}


def chain_relaxation(instance, scene, request):
    """Optimistic chain bound ignoring all resource conflicts, not a schedule."""
    stages = {s["id"]: s["shared_stage_id"] for s in scene["stage_instances"]}
    grid, cursor = F(instance["start_grid_ms"]), F(request["release_ms"])
    for iid in request["stage_instance_ids"]:
        cursor = -((-cursor)//grid)*grid
        cursor += min(F(m["duration_ms"]) for m in instance["stage_modes"][stages[iid]])
    return {"request": request["id"], "optimistic_finish_ms": str(cursor),
        "deadline_ms": request["deadline_ms"], "optimistic_deadline_pass": cursor <= F(request["deadline_ms"]),
        "meaning": "Necessary relaxed check only; shared deployment, resource conflicts and thermal safety not solved"}


def main():
    began, started = time.monotonic(), utc()
    checks, forbidden, failure = [], [], None
    def check(name, passed):
        checks.append({"name": name, "passed": bool(passed)})
        if not passed:
            raise AssertionError(name)
    def denied(label):
        def call(*args, **kwargs):
            forbidden.append(label)
            raise AssertionError("FORBIDDEN_REAL_CALL:" + label)
        return call
    class NoSolverImports(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.rsplit(".", 1)[-1] in ("milp", "matlab_bridge") or fullname.startswith((
                    "scipy.optimize", "matlab.engine", "gurobipy", "pulp", "cvxpy")):
                forbidden.append("import:"+fullname)
                raise AssertionError("FORBIDDEN_SOLVER_IMPORT:"+fullname)
            return None
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=REPO, text=True).strip()
    prior_plan = read(PRIOR / "execution/plan.json")
    manifest = read(PRIOR / "deliverables_manifest.json")
    protected = {REPO/p: h for p, h in prior_plan["source_sha256"].items()}
    protected.update({PRIOR/p: h for p, h in manifest["files_sha256"].items()})
    protected[PRIOR / "deliverables_manifest.json"] = sha(PRIOR / "deliverables_manifest.json")
    before = {str(p.relative_to(REPO)): sha(p) for p in protected}
    check("all_prior_frozen_sources_and_artifacts_match", all(sha(p)==h for p,h in protected.items()))
    sources = [REPO/"research/第四章算法方案设计与可行性分析.md",
               REPO/"research/第四章固定部署与跨资源降档联动审查.md"]
    sources += [p for p in (REPO/"research/chapter4_scheduler").rglob("*.md")
                if "source_snapshot" not in p.parts and not p.is_relative_to(OUT)]
    exposure = {r: [] for r in ("R1", "R2", "R3", "R4", "R5")}
    for path in sorted(set(sources)):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for r in exposure:
                if re.search(r"\b"+r+r"\b|base__"+r+r"\b", line):
                    exposure[r].append({"path":str(path.relative_to(REPO)), "line":n, "excerpt":line[:500]})
    save("development_exposure.json", {"scope":"Chapter4 proposal reports and scheduler Markdown, excluding source snapshots and this new folder",
        "files_sha256":{str(p.relative_to(REPO)):sha(p) for p in sorted(set(sources))},
        "matches":exposure, "not_a_proof_of_unseen_data":True,
        "selection":"Exclude R1/R3 mechanism cases and R4 explicitly used in K179; use original R2/R5 irrespective of any future outcome",
        "limitations":"All five samples belong to the same self-set catalog and have prior chapter3 history; not an external/blind/IID holdout"})
    check("R4_was_exposed_and_is_excluded", bool(exposure["R4"]) and "base__R4" not in CASES)
    check("R2_R5_not_seen_in_targeted_mechanism_documents", not exposure["R2"] and not exposure["R5"])
    import thermal, heft_method
    from research.chapter4_scheduler.blocking import method as blocking
    guard = NoSolverImports()
    sys.meta_path.insert(0, guard)
    try:
        with ExitStack() as stack:
            for target in ("thermal.evaluate_candidate", "thermal.evaluate_piecewise", "heft_method.run_heft",
                    "heft_method.build_heft_candidate", "research.chapter4_scheduler.blocking.method.execute_reconstruction",
                    "research.chapter4_scheduler.blocking.method.candidate_packets",
                    "research.chapter4_scheduler.blocking.core.reconstruct", "research.chapter4_scheduler.graph_core.reconstruct",
                    "subprocess.Popen", "os.system", "socket.create_connection", "socket.socket.connect"):
                stack.enter_context(patch(target, side_effect=denied(target)))
            # Only expand declared inputs. No constructor or schedule search.
            from inputs import load_config, build_instance
            from control_policy import with_auto_low_idle, resolve_idle_policy
            from p0_batch.run_p0 import fresh_input
            raw = load_config()
            input_rows = []
            for case in CASES:
                rc, config, instance = fresh_input(case)
                expected = with_auto_low_idle(build_instance(raw,case))
                check(case+":fresh_expansion_matches_direct_original_recipe", instance==expected and rc==raw)
                check(case+":physical_platform_unchanged", instance["platform"]==raw["platform"])
                check(case+":policy_matches_development", instance["execution_rules"]==read(PRIOR/"execution/calls/01_base__R1_OFF/method/input_instance.json")["execution_rules"])
                check(case+":full_modes_unchanged", instance["stage_modes"]==build_instance(raw,case)["stage_modes"])
                check(case+":original_base_H_window_grid", instance["condition_id"]=="base" and instance["response_variant"]=="H"
                      and F(instance["window_ms"])==400 and F(instance["start_grid_ms"])==5)
                check(case+":original_all_devices_and_thermal_nodes", len(instance["platform"]["units"])==4
                      and instance["platform"]["node_order"]==["CPU1","CPU2","GPU0","NPU0"])
                check(case+":full_two_scene_three_stage_chains", len(instance["scenarios"])==2 and all(
                    len(s["stage_instances"])==6 and len(s["dependencies"])==4 and all(len(r["stage_instance_ids"])==3 for r in s["requests"])
                    for s in instance["scenarios"]))
                check(case+":entry_limits_weights_unchanged", all(s["weight"]=="1/2" and all(F(t)==50 for t in s["entry"]["temperature_degC"])
                      and all(F(t)==80 for t in s["maximum_temperature_degC"]) for s in instance["scenarios"]))
                counts=[]
                for s in instance["scenarios"]:
                    req={r["id"]:r for r in s["requests"]}
                    for st in s["stage_instances"]:
                        r=req[st["request_id"]];grid=F(instance["start_grid_ms"])
                        for m in instance["stage_modes"][st["shared_stage_id"]]:
                            first=-((-F(r["release_ms"]))//grid)*grid
                            last=((min(F(r["deadline_ms"]),F(instance["window_ms"]))-F(m["duration_ms"]))//grid)*grid
                            counts.append({"scene":s["id"],"stage":st["id"],"mode":m["mode_id"],
                                "legal_start_count_ignoring_other_stages":max(0,int((last-first)//grid)+1)})
                relaxed=[chain_relaxation(instance,s,r) for s in instance["scenarios"] for r in s["requests"]]
                check(case+":nonempty_per_execution_start_domain", all(any(x["legal_start_count_ignoring_other_stages"]>0
                      for x in counts if x["stage"]==st["id"]) for s in instance["scenarios"] for st in s["stage_instances"]))
                check(case+":optimistic_chain_necessary_check", all(r["optimistic_deadline_pass"] for r in relaxed))
                check(case+":input_not_a_development_duplicate", digest(instance) not in [v["input_sha256"] for v in prior_plan["inputs"].values()])
                prefix="static_inputs/"+case
                save(prefix+"_raw_config.json",rc);save(prefix+"_config.json",config);save(prefix+"_instance.json",instance)
                row={"case_id":case,"duration_scale":instance["duration_scale"],"input_sha256":digest(instance),
                     "config_sha256":digest(config),"raw_config_sha256":digest(rc),"policy":resolve_idle_policy(instance),
                     "logical_mode_count":sum(map(len,instance["stage_modes"].values())),
                     "execution_mode_count":len(counts),"all_declared_mode_start_pairs_ignoring_conflicts":sum(x["legal_start_count_ignoring_other_stages"] for x in counts),
                     "per_mode_start_counts":counts,"optimistic_chain_checks":relaxed,
                     "safe_feasibility":"NOT_EVALUATED","energy_J":None,"algorithm_wall_s":None,"full_evaluator_calls":0,
                     "static_label":"INPUT_CONSISTENT_ONLY_NO_COMPLETE_SCHEDULE_OR_THERMAL_CERTIFICATE"}
                save(prefix+"_static_checks.json",row);input_rows.append(row)
            evidence={}
            for case,folder in (("R1","02_base__R1_ON"),("R3","03_base__R3_ON")):
                d=PRIOR/"execution/calls"/folder/"method"
                result,instance=read(d/"result.json"),read(d/"input_instance.json")
                initial=result["initial_safe_snapshot"]
                oldparts,newparts=parts(instance,initial["receipt"]),parts(instance,result["evaluation"])
                target_rows=[]
                for scene in instance["scenarios"]:
                    shared={s["id"]:s["shared_stage_id"] for s in scene["stage_instances"]}
                    for row in initial["candidate"]["scenes"][scene["id"]]:
                        modes=instance["stage_modes"][shared[row["stage_id"]]]
                        current=next(m for m in modes if m["unit_id"]==row["unit"] and m["opp_id"]==row["opp"])
                        activity=lambda m:F(m["activity_power_W"])*F(m["duration_ms"])/1000
                        target_rows.append({"scene":scene["id"],"stage":row["stage_id"],"unit":row["unit"],"opp":row["opp"],
                            "current_activity_J":str(activity(current)),"minimum_fixed_unit_activity_J":str(min(activity(m) for m in modes if m["unit_id"]==row["unit"])),
                            "minimum_all_legal_modes_activity_J":str(min(map(activity,modes)))})
                from timing import MethodBudget
                targets=blocking.energy_targets(instance,initial["candidate"],MethodBudget(60))
                weights={s["id"]:F(s["weight"]) for s in instance["scenarios"]}
                activity_floor=sum(weights[r["scene"]]*F(r["minimum_all_legal_modes_activity_J"]) for r in target_rows)
                baseline_floor=F(instance["window_ms"])/1000*sum(min(map(F,d["baseline_W"].values()))
                    for d in instance["platform"]["domains"].values())
                common=F(instance["window_ms"])/1000*F(instance["platform"]["external_common_power_W"])
                floor=activity_floor+baseline_floor+common
                initial_nontemp=[sum(F(oldparts[k][j]) for k in ("activity","baseline","external_common")) for j in (0,1)]
                if case=="R3":
                    check("R3_exact_target_list_empty",targets==[])
                    check("R3_all_12_rows_at_global_activity_minimum",all(F(r["current_activity_J"])==F(r["minimum_all_legal_modes_activity_J"]) for r in target_rows))
                    check("R3_zero_reconstruction_and_followup_evaluation",not result["graph_proposals"] and not result["reconstruction_attempts"]
                          and not any(r["phase"]=="refinement" for r in result["evaluations"]))
                    check("R3_final_candidate_identical_to_initial",initial["candidate"]==result["safe_candidate"])
                    check("R3_nonthermal_floor_is_enclosed_by_initial_nonthermal",initial_nontemp[0]<=floor<=initial_nontemp[1])
                else:
                    accepted=[p for p in result["graph_proposals"] if p["strict_accepted"]]
                    check("R1_one_strict_atomic_extra_edge_acceptance",len(accepted)==1 and len(accepted[0]["additional_reversed_edges"])==1
                          and F(result["evaluation"]["weighted_energy_J"][1])<F(initial["energy"]["lower"]))
                # Node-level residual accounting uses only already archived
                # segments and injected energies, not new heat trajectories.
                node_savings={}
                for sid,final_scene in result["evaluation"]["scenes"].items():
                    vals=[]
                    for receipt in (initial["receipt"],result["evaluation"]):
                        segments=receipt["legality"]["scenes"][sid]["segments"]
                        residual={}
                        for node in instance["platform"]["node_order"]:
                            nontemp=sum(F(seg["duration_ms"])/1000*(F(seg["baseline_by_node_W"][node])+F(seg["activity_by_node_W"][node])) for seg in segments)
                            residual[node]=[F(x)-nontemp for x in receipt["scenes"][sid]["node_injected_energy_J"][node]]
                        vals.append(residual)
                    node_savings[sid]={node:[str(vals[0][node][0]-vals[1][node][1]),str(vals[0][node][1]-vals[1][node][0])]
                        for node in instance["platform"]["node_order"]}
                evidence[case]={"source_result":str((d/"result.json").relative_to(REPO)),"source_sha256":sha(d/"result.json"),
                    "initial_energy":initial["receipt"]["weighted_energy_J"],"final_energy":result["evaluation"]["weighted_energy_J"],
                    "weighted_parts_before":oldparts,"weighted_parts_after":newparts,
                    "weighted_component_savings_J":{k:[str(F(oldparts[k][0])-F(newparts[k][1])),str(F(oldparts[k][1])-F(newparts[k][0]))] for k in oldparts},
                    "exact_energy_targets":targets,"activity_mode_audit":target_rows,
                    "relaxed_nonthermal_floor_J":{"activity":str(activity_floor),"domain_baseline":str(baseline_floor),"external_common":str(common),
                        "sum":str(floor),"initial_nonthermal_interval":list(map(str,initial_nontemp)),
                        "scope":"Nonthermal components only; not a lower bound certificate for total temperature-dependent energy"},
                    "unweighted_scene_node_temperature_correction_savings_J":node_savings,
                    "accepted_packets":[p for p in result["graph_proposals"] if p["strict_accepted"]],
                    "reconstruction_attempts":result["reconstruction_attempts"],"formal_experiment_result":result["evaluation"]["formal_experiment_result"],
                    "known":"R1: saved atomic repaired candidate is legal, SAFE and strictly cheaper; R3: no declared activity-saving target and no refinement",
                    "not_identified":"Separate causal shares of timing, leakage-slope choice and coupled temperatures require counterfactuals not evaluated here; no global thermal-energy optimum or tight-temperature benefit established"}
            save("mechanism_analysis.json",evidence)
            slots=[]
            for case,arms in ((CASES[0],("HEFT","OFF","ON")),(CASES[1],("ON","OFF","HEFT"))):
                for arm in arms:
                    slots.append({"slot_id":case+"__"+arm,"case_id":case,"arm":arm,"state":"NOT_RUN",
                        "method_seconds":300,"post_seconds":60,"safe":None,"energy_interval_J":None,
                        "initial_semantic_sha256":None,"method_elapsed_s":None,"full_evaluation_calls":None})
            proposal={"status":"PROPOSAL_ONLY_NOT_AUTHORIZED_OR_EXECUTABLE","execution_enabled":False,"authorized":False,
                "created_utc":utc(),"baseline_commit":base,"case_selection_frozen_before_static_checks":list(CASES),
                "selection_independence":"Outside targeted chapter4 mechanism-development records; same prior synthetic catalog, not blind or IID",
                "input_origin":"Unmodified config_v01.json original base condition, R2/R5 samples; fresh_input auto-L adapter identical to development",
                "input_identities":[{k:r[k] for k in ("case_id","input_sha256","config_sha256","raw_config_sha256","duration_scale")} for r in input_rows],
                "slots":slots,"budget_proposal":{"method_calls":6,"method_seconds_each":300,"method_total_s":1800,
                    "post_calls_at_most":6,"post_seconds_each":60,"post_total_s_at_most":360,"calendar_s":3600},
                "frozen_rules":{"HEFT":"Original complete HEFT including its existing energy pass, 300s single root",
                    "OFF_ON":"Same original HEFT initialization, activity targets, primary pairs, templates, ranking, legality and complete evaluator; only allow_blocking_edges differs",
                    "original_legal_choices":"All original device and OPP choices retained at input/initialization; refinement fixed-unit scope remains an algorithm limitation, never a model mask",
                    "initialization":"Fresh independent per slot; charge imports, input, initializer, sorting and all evaluations to one root; no historical warm start or shared caches",
                    "strict_acceptance":"Full SAFE and new.upper < incumbent.lower; no worse intermediate incumbent",
                    "matching":"Compare completed best-initial semantic candidate, interval and initialization candidate order; mismatch/incomplete restricts attribution and never triggers a free rerun",
                    "metrics":"Per-case SAFE feasibility/status, full weighted energy intervals, component energies, end-to-end and refinement times, first SAFE/improvement, complete evaluator/cache counts; missing/invalid is not zero energy",
                    "post":"At most one fresh <=60s recomputation on original final candidate, same evaluator; label as process-independent rerun, not an independent numerical implementation",
                    "outcomes":"Retain all no-gain, unresolved, initialization mismatch, slower, worse-than-HEFT and missing-SAFE outcomes; no case replacement or favorable-only aggregate",
                    "stops":"No retries/refunds or parameter tuning; technical/numerical/source/identity/post failure stops later slots; normal no-SAFE may continue as an explicit outcome",
                    "no_formal_claim":"Two cases once each cannot prove statistical robustness, external generalization, active thermal constraints or optimality"},
                "prerequisites_before_any_run":["Separate explicit authorization of this six-slot budget","Fresh frozen source/environment identities and dedicated inert-to-active admission reviewed","All launcher and complete evidence gates passing","No reuse of old claims or authorizations"],
                "not_started":{"real_HEFT_calls":0,"real_schedule_constructions":0,"full_evaluator_calls":0,"thermal_integrations":0,"optimizer_calls":0}}
            check("proposal_is_inert",proposal["execution_enabled"] is False and proposal["authorized"] is False)
            check("six_fixed_balanced_slots",len(slots)==6 and Counter(s["arm"] for s in slots)=={"HEFT":2,"OFF":2,"ON":2})
            check("all_results_explicitly_not_run",all(s["state"]=="NOT_RUN" and s["safe"] is None and s["energy_interval_J"] is None for s in slots))
            check("equal_per_arm_budgets",all(s["method_seconds"]==300 and s["post_seconds"]==60 for s in slots))
            save("validation_proposal.json",proposal)
    except BaseException:
        failure=traceback.format_exc()
    finally:
        sys.meta_path.remove(guard)
    check("no_forbidden_calls",not forbidden)
    after={str(p.relative_to(REPO)):sha(p) for p in protected}
    check("all_prior_sources_and_results_byte_preserved",before==after)
    check("HEAD_and_branch_unchanged",base==subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip()
          and branch==subprocess.check_output(["git","branch","--show-current"],cwd=REPO,text=True).strip())
    ended=utc()
    record={"started_utc":started,"ended_utc":ended,"started_client_time":datetime.fromisoformat(started).astimezone(CLIENT_TZ).isoformat(),
        "ended_client_time":datetime.fromisoformat(ended).astimezone(CLIENT_TZ).isoformat(),"wall_s":time.monotonic()-began,
        "baseline_commit":base,"branch":branch,"environment":{"python":sys.version,"executable":sys.executable,"platform":platform.platform(),
            "cpu_count":os.cpu_count(),"packages":{n:importlib.metadata.version(n) for n in ("numpy","scipy")},"matlab":shutil.which("matlab"),"octave":shutil.which("octave")},
        "passed":failure is None and all(c["passed"] for c in checks),"failure":failure,"checks":checks,"forbidden_calls":forbidden,
        "protected_unique_files":len(before),"protected_before_sha256":before,"protected_after_sha256":after,
        "new_real_HEFT_calls":0,"new_research_schedule_constructions":0,"new_thermal_evaluations":0,"new_optimization_calls":0,
        "script_sha256":sha(__file__),"evidence_kind":"READ_ONLY_ARCHIVE_ALGEBRA_AND_STATIC_INPUT_CHECKS_NOT_EXPERIMENT_RESULTS"}
    save("static_run.json",record)
    print(json.dumps({k:record[k] for k in ("passed","started_utc","ended_utc","wall_s","failure","forbidden_calls","protected_unique_files")},ensure_ascii=False))
    if not record["passed"]:
        raise SystemExit(1)


if __name__=="__main__":
    main()
