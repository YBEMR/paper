"""Pinned-commit analysis of saved R2/R5 schedules; no research execution."""
import ast
from contextlib import ExitStack
import csv
from datetime import datetime,timezone,timedelta
from fractions import Fraction as F
import hashlib
import importlib.abc
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import traceback
from unittest.mock import patch

OUT=Path(__file__).resolve().parent
REPO=OUT.parents[3]
EXEC=OUT.parent/"validation_execution_20261107"
sys.path[:0]=[str(REPO),str(REPO/"research/chapter3_experiments")]
COMMIT="d47bfda700ce76df31d9aae0aea97d01279b501f"


def read(path):return json.loads(Path(path).read_text(encoding="utf-8"))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(name,value):
    with (OUT/name).open("x",encoding="utf-8") as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write("\n")


def components(instance,receipt):
    return {k:[str(sum(F(s["weight"])*F(receipt["scenes"][s["id"]]["energy_components_J"][k][j])
        for s in instance["scenarios"])) for j in (0,1)] for k in ("activity","baseline","external_common","temperature_correction")}


def main():
    began=time.monotonic();started=datetime.now(timezone.utc).isoformat();checks=[];forbidden=[];failure=None
    def check(label,passed):
        checks.append({"check":label,"passed":bool(passed)})
        if not passed:raise AssertionError(label)
    check("HEAD_is_pushed_subject",subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip()==COMMIT)
    branch=subprocess.check_output(["git","branch","--show-current"],cwd=REPO,text=True).strip()
    plan=read(EXEC/"plan.json");completion=read(EXEC/"completion_record.json")
    protected={REPO/p:h for p,h in plan["source_sha256"].items()}
    protected.update({EXEC/p:h for p,h in completion["files_sha256"].items()})
    protected[EXEC/"completion_record.json"]=sha(EXEC/"completion_record.json")
    before={str(p.relative_to(REPO)):sha(p) for p in protected}
    check("all_frozen_sources_and_saved_results_match",all(sha(p)==h for p,h in protected.items()))
    code_paths=["research/chapter3_experiments/heft_method.py","research/chapter3_experiments/sa_method.py",
        "research/chapter3_experiments/heuristic_common.py","research/chapter3_experiments/heuristic_runner.py",
        "research/chapter3_experiments/schedules.py","research/chapter3_experiments/start_domain.py",
        "research/chapter3_experiments/thermal.py","research/chapter3_experiments/timing.py",
        "research/chapter3_experiments/h02_pair_preflight/receipts.py","research/chapter4_scheduler/blocking/core.py",
        "research/chapter4_scheduler/blocking/method.py","research/chapter4_scheduler/graph_core.py",
        "research/chapter4_scheduler/method.py","research/chapter4_scheduler/validation/lifecycle.py",
        "research/chapter4_scheduler/validation/run.py"]
    inventory={}
    for rel in code_paths:
        p=REPO/rel
        check("source_matches_subject:"+rel,subprocess.check_output(["git","show",COMMIT+":"+rel],cwd=REPO)==p.read_bytes())
        tree=ast.parse(p.read_text());inventory[rel]={"sha256":sha(p),"functions":{n.name:{"start":n.lineno,"end":n.end_lineno}
            for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}}
    save("source_inventory.json",inventory)
    def denied(label):
        def call(*args,**kwargs):forbidden.append(label);raise AssertionError("FORBIDDEN_RESEARCH_CALL:"+label)
        return call
    class Guard(importlib.abc.MetaPathFinder):
        def find_spec(self,fullname,path=None,target=None):
            if fullname.rsplit(".",1)[-1] in ("milp","matlab_bridge") or fullname.startswith(("scipy.optimize","matlab.engine","gurobipy","pulp","cvxpy")):
                forbidden.append("import:"+fullname);raise AssertionError("FORBIDDEN_SOLVER_IMPORT:"+fullname)
    import thermal,heft_method,sa_method
    guard=Guard();sys.meta_path.insert(0,guard)
    try:
        with ExitStack() as stack:
            for name in ("thermal.evaluate_candidate","thermal.evaluate_piecewise","heft_method.run_heft","heft_method.build_heft_candidate",
                    "sa_method.run_sa","research.chapter4_scheduler.blocking.method.execute_reconstruction",
                    "research.chapter4_scheduler.blocking.method.candidate_packets","research.chapter4_scheduler.blocking.core.reconstruct",
                    "research.chapter4_scheduler.graph_core.reconstruct","subprocess.Popen","os.system","socket.create_connection","socket.socket.connect"):
                stack.enter_context(patch(name,side_effect=denied(name)))
            from schedules import validate_schedule
            from h02_pair_preflight.receipts import safe_receipt
            rows=[];cases={}
            for case,ids in (("R2",("01_base__R2_HEFT","02_base__R2_OFF","03_base__R2_ON")),
                             ("R5",("06_base__R5_HEFT","05_base__R5_OFF","04_base__R5_ON"))):
                datasets={arm:read(EXEC/"calls"/slot/"method/result.json") for arm,slot in zip(("HEFT","OFF","ON"),ids)}
                folder=EXEC/"calls"/ids[0]/"method";instance=read(folder/"input_instance.json");config=read(folder/"input_config.json")
                init=datasets["HEFT"]["initial_safe_snapshot"]
                states=[("initial",init["candidate"],init["receipt"]),("OFF_final",datasets["OFF"]["safe_candidate"],datasets["OFF"]["evaluation"])]
                accepted=[p for p in datasets["ON"]["graph_proposals"] if p["strict_accepted"]]
                for n,p in enumerate(accepted,1):
                    r=next(r for r in datasets["ON"]["evaluations"] if r["candidate_sha256"]==p["candidate_sha256"])
                    states.append(("ON_step"+str(n),r["candidate"],r["receipt"]))
                state_records=[]
                for name,candidate,receipt in states:
                    legal=validate_schedule(instance,candidate)
                    check(case+":"+name+":original_legality",legal==receipt["legality"] and legal["state"]=="SCHEDULE_VALID_THERMAL_UNCHECKED")
                    energy=safe_receipt(instance,candidate,receipt,config["accuracy_targets"],300)
                    scene_records={}
                    for scene in instance["scenarios"]:
                        sid=scene["id"];rr=legal["scenes"][sid]["rows"];byid={r["stage_id"]:r for r in rr}
                        all_ok=True;dependency_margins=[];resource_checks=[]
                        for a,b in scene["dependencies"]:
                            gap=F(byid[b]["start_ms"])-F(byid[a]["end_ms"]);all_ok &= gap>=0
                            dependency_margins.append({"from":a,"to":b,"gap_ms":str(gap)})
                        for a in rr:
                            all_ok &= F(a["start_ms"])>=F(a["release_ms"]) and F(a["end_ms"])<=min(F(a["deadline_ms"]),F(instance["window_ms"]))
                            all_ok &= (F(a["start_ms"])/F(instance["start_grid_ms"])).denominator==1
                            rows.append({"case":case,"state":name,"scene":sid,"stage":a["stage_id"],"unit":a["unit"],"opp":a["opp"],
                                "start_ms":a["start_ms"],"end_ms":a["end_ms"],"duration_ms":a["duration_ms"],"deadline_ms":a["deadline_ms"],
                                "deadline_margin_ms":str(F(a["deadline_ms"])-F(a["end_ms"]))})
                        for i,a in enumerate(rr):
                            for b in rr[i+1:]:
                                overlap=max(F(a["start_ms"]),F(b["start_ms"]))<min(F(a["end_ms"]),F(b["end_ms"]))
                                okay=not overlap or a["unit"]!=b["unit"] and (a["domain_id"]!=b["domain_id"] or a["opp"]==b["opp"])
                                all_ok &= okay
                                if a["unit"]==b["unit"] or a["domain_id"]==b["domain_id"]:
                                    resource_checks.append({"a":a["stage_id"],"b":b["stage_id"],"overlap":overlap,"legal":okay})
                        check(case+":"+name+":"+sid+":independent_exact_release_grid_dependency_resource_deadline_check",all_ok)
                        request_checks=[]
                        for req in scene["requests"]:
                            finish=max(F(byid[i]["end_ms"]) for i in req["stage_instance_ids"])
                            request_checks.append({"request":req["id"],"finish_ms":str(finish),"deadline_ms":req["deadline_ms"],"margin_ms":str(F(req["deadline_ms"])-finish)})
                        # Meter each domain once over already archived intervals.
                        domain_base={d:str(sum(F(seg["duration_ms"])/1000*F(seg["baseline_by_power_group_W"][d]) for seg in legal["scenes"][sid]["segments"])) for d in instance["platform"]["domains"]}
                        modes={st["id"]:instance["stage_modes"][st["shared_stage_id"]] for st in scene["stage_instances"]}
                        activity={a["stage_id"]:str(F(a["activity_power_W"])*F(a["duration_ms"])/1000) for a in rr}
                        scene_records[sid]={"requests":request_checks,"dependency_margins":dependency_margins,"resource_checks":resource_checks,
                            "domain_baseline_J":domain_base,"stage_activity_J":activity,"energy_J":receipt["scenes"][sid]["energy_J"],
                            "energy_components_J":receipt["scenes"][sid]["energy_components_J"],"peaks_degC":receipt["scenes"][sid]["peaks_degC"],
                            "covered_until_s":receipt["scenes"][sid]["covered_until_s"]}
                    state_records.append({"state":name,"candidate":candidate,"energy":energy,"weighted_components_J":components(instance,receipt),"scenes":scene_records})
                first=accepted[0]
                check(case+":first_joint_step_has_one_extra_post_edge",len(first["additional_reversed_edges"])==1 and "post" in first["additional_reversed_edges"][0][0])
                check(case+":saved_base_has_deadline_violation",bool(first["base_deadline_violations"]))
                check(case+":ON_AC_unchanged",datasets["ON"]["safe_candidate"]["scenes"]["AC_offset_0ms"]==init["candidate"]["scenes"]["AC_offset_0ms"])
                parts0,parts1=components(instance,init["receipt"]),components(instance,datasets["ON"]["evaluation"])
                cases[case]={"source_slots":dict(zip(("HEFT","OFF","ON"),ids)),"input_sha256":plan["input_identities"]["base__"+case]["input_sha256"],
                    "states":state_records,"saved_first_joint_metadata":{k:first[k] for k in ("candidate_sha256","energy_target","selected_stages","orientation","template","additional_reversed_edges","base_deadline_violations","base_blocking_traces")},
                    "weighted_ON_savings_J":{k:[str(F(parts0[k][0])-F(parts1[k][1])),str(F(parts0[k][1])-F(parts1[k][0]))] for k in parts0},
                    "observation":"Stored step is legal and complete SAFE; base skeleton has recorded late path; no new schedule or thermal calculation performed",
                    "inference_limits":"This explains the saved restricted skeleton and search trajectory, not impossibility for all other algorithms or globally optimal energy; component attribution is not an independent timing-vs-mode counterfactual"}
            with (OUT/"schedules.csv").open("x",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
            save("mechanism_evidence.json",cases)
            parameters=sa_method.algorithm_parameters()
            orderA=("HEFT","SA101","ON","SA102","SA103","SA104","SA105")
            orderB=tuple(reversed(orderA))
            slots=[]
            for case,order in (("base__R2",orderA),("base__R5",orderB)):
                for arm in order:
                    slots.append({"case_id":case,"method":"SA" if arm.startswith("SA") else arm,"seed":int(arm[2:]) if arm.startswith("SA") else None,
                        "method_budget_s":300,"post_budget_s":60,"status":"NOT_RUN","SAFE":None,"energy_interval_J":None,"elapsed_s":None,"evaluator_calls":None})
            proposal={"status":"DESIGN_ONLY_NOT_AUTHORIZED_NOT_EXECUTABLE","authorized":False,"execution_enabled":False,"subject_commit":COMMIT,
                "inputs":deepcopy_inputs(plan["input_identities"]),"cases":["base__R2","base__R5"],
                "selection_note":"Same fixed original inputs only. Already exposed R2/R5 can support method comparison, not a new blind mechanism validation. No new cases or parameters proposed.",
                "methods":{"HEFT":"Original run_heft including original energy pass; common full SAFE recording, native initialization",
                    "ON":"Existing implemented HEFT plus saving-mode/one-blocking-edge reconstruction, unchanged",
                    "SA":"Original run_sa native constructor/fallback/random initialization; mapping/OPP/priority/delay moves and uphill-current acceptance unchanged"},
                "SA_parameters":parameters,"SA_seeds":[101,102,103,104,105],"slots":slots,
                "budget_proposal":{"method_calls":14,"method_s_each":300,"method_total_s":4200,"post_calls_at_most":14,"post_s_each":60,"post_total_s_at_most":840,"calendar_s":9000},
                "initialization_fairness":"Native initialization charged independently to the same per-run 300s cap. SA uses only HEFT constructor, not the enhanced HEFT energy pass. No same-initial assertion for SA; primary comparison is end-to-end. A forced HEFT-warm SA would be a separately named variant, not silently substituted.",
                "critical_adapter_gap":"Current validation.dispatch has no SA arm; REAL binding accepts run_heft only. CompleteRecorder freezes deployment for refinement and cannot be reused unchanged after freeze for SA mapping moves. A future recording adapter must preserve all original SA moves/current-state semantics while applying the identical full receipt checks and separately retaining best SAFE upper bound.",
                "evaluation":"Original complete legality plus all scenes/nodes/400ms continuous thermal and weighted energy, original accuracy; zero-weight safety too; same post evaluator in a fresh <=60s process, not an independent numerical implementation",
                "metrics":"All seed outcomes and complete intervals; SAFE count/5 and failures/timeouts; median/range among SAFE seeds labelled conditional. Best-of-five only if explicitly labelled 5x300s, never as a single 300s result. Full initialization and total timing, first SAFE/improvement, decode failures, proposals, unique evaluations and cache hits",
                "comparison_limits":"Equal per-run time cap, not equal evaluation count or total seed-batch cost. No population win-rate or stable speedup claim from two cases. Do not use historical timing as concurrent controls; fresh 14 slots only after separate authorization.",
                "safety":"SA may accept a worse complete SAFE as current according to original annealing, but final archive keeps best SAFE. Reject non-SAFE/unresolved without energy penalties. No fixed-deployment lock imposed on SA; no model-domain restriction to make ON look better.",
                "stops":"No retries, refunds, case/seed replacement, tuning or extra scans. Retain normal no-SAFE/time-limit/no-improvement outcomes; technical/numerical/identity/post failure stops remaining slots.",
                "prerequisites":["Separate approval of exact future budget/order","Implement only the necessary SA recording/dispatch adapter and guarded acceptance tests","Freeze unchanged science/parameters/environment and new source identity","No old claims/candidates reused; do not change historical records"]}
            check("comparison_proposal_inert",proposal["authorized"] is False and proposal["execution_enabled"] is False and all(s["status"]=="NOT_RUN" and s["energy_interval_J"] is None for s in slots))
            save("comparison_proposal.json",proposal)
    except BaseException:failure=traceback.format_exc()
    finally:sys.meta_path.remove(guard)
    check("no_new_research_calls",not forbidden)
    after={str(p.relative_to(REPO)):sha(p) for p in protected}
    check("all_protected_bytes_unchanged",before==after)
    check("commit_and_branch_unchanged",subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip()==COMMIT
        and subprocess.check_output(["git","branch","--show-current"],cwd=REPO,text=True).strip()==branch)
    ended=datetime.now(timezone.utc)
    record={"started_utc":started,"ended_utc":ended.isoformat(),"ended_client_time":ended.astimezone(timezone(timedelta(hours=8))).isoformat(),
        "wall_s":time.monotonic()-began,"subject_commit":COMMIT,"branch":branch,"passed":failure is None and all(c["passed"] for c in checks),"failure":failure,
        "checks":checks,"forbidden_calls":forbidden,"source_script_sha256":sha(__file__),"protected_files":len(before),
        "before_sha256":before,"after_sha256":after,"environment":{"python":sys.version,"executable":sys.executable,"platform":platform.platform(),
            "packages":{n:importlib.metadata.version(n) for n in ("numpy","scipy")},"cpu_count":os.cpu_count(),"matlab":shutil.which("matlab"),"octave":shutil.which("octave")},
        "new_HEFT_calls":0,"new_SA_calls":0,"new_schedule_generations":0,"new_thermal_integrations":0,"new_optimizer_calls":0,
        "evidence_kind":"SAVED_SCHEDULE_CONSTRAINT_REPLAY_AND_ALGEBRA_ONLY; PROPOSAL_IS_NOT_AN_EXPERIMENT_RESULT"}
    save("analysis_run.json",record)
    print(json.dumps({k:record[k] for k in ("passed","started_utc","ended_utc","wall_s","protected_files","failure","forbidden_calls")},ensure_ascii=False))
    if not record["passed"]:raise SystemExit(1)


def deepcopy_inputs(identities):return json.loads(json.dumps(identities))


if __name__=="__main__":main()
