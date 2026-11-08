"""One new authorized six-slot R2/R5 validation, never reusing old claims."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from fractions import Fraction as F
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

REPO=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(REPO),str(REPO/"research/chapter3_experiments")]
from research.chapter4_scheduler.mechanism_check.run import read, save, sha, digest, environment, semantic

HERE=Path(__file__).resolve().parent
DESIGN=REPO/"research/chapter4_scheduler/results/validation_design_20261107"
PREVIOUS=DESIGN.parent/"cloud_mechanism_20261107"
ORDER=(("base__R2","HEFT"),("base__R2","OFF"),("base__R2","ON"),
       ("base__R5","ON"),("base__R5","OFF"),("base__R5","HEFT"))
CLIENT_TZ=timezone(timedelta(hours=8))


def now():
    return datetime.now(timezone.utc).isoformat()


def resources():
    memory=next(x.split(":",1)[1].strip() for x in Path("/proc/meminfo").read_text().splitlines() if x.startswith("MemAvailable:"))
    return {"utc":now(),"loadavg":list(os.getloadavg()),"memory_available":memory,
        "disk_free_bytes":shutil.disk_usage(REPO).free,"cpu_count":os.cpu_count()}


def verify(plan):
    if plan.get("authorized") is not True or plan.get("execution_enabled") is not True:
        raise ValueError("This new six-slot declaration must be explicitly authorized")
    if [(s["case"],s["arm"]) for s in plan["slots"]]!=list(ORDER):
        raise ValueError("Frozen six-slot order changed")
    if plan["budgets"]!={"method_s":300,"post_s":60,"method_calls":6,"method_total_s":1800,
        "post_calls_at_most":6,"post_total_s":360,"calendar_s":3600}:
        raise ValueError("Frozen authorized budgets changed")
    mismatches=[p for p,h in plan["source_sha256"].items() if sha(REPO/p)!=h]
    if mismatches:raise ValueError("Frozen sources or protected evidence changed: "+repr(mismatches))
    if environment()!=plan["environment"]:raise ValueError("Frozen runtime changed")


def prepare(out,checks):
    proposal=read(DESIGN/"validation_proposal.json")
    if [(s["case_id"],s["arm"]) for s in proposal["slots"]]!=list(ORDER):
        raise ValueError("Original proposal order changed")
    precheck=read(checks)
    if precheck.get("passed") is not True or precheck.get("forbidden_calls"):
        raise ValueError("Passing new guarded lifecycle/launcher checks required")
    protected=read(PREVIOUS/"execution/plan.json")["source_sha256"]
    protected={p:sha(REPO/p) if sha(REPO/p)==h else (_ for _ in ()).throw(ValueError("Prior drift: "+p)) for p,h in protected.items()}
    completion=read(DESIGN/"completion_record.json")
    for p,h in completion["new_artifacts_sha256"].items():
        full=DESIGN/p
        if sha(full)!=h:raise ValueError("Design artifact changed: "+p)
        protected[full.relative_to(REPO).as_posix()]=h
    protected[(DESIGN/"completion_record.json").relative_to(REPO).as_posix()]=sha(DESIGN/"completion_record.json")
    for p in sorted(HERE.glob("*.py")):
        protected[p.relative_to(REPO).as_posix()]=sha(p)
    protected[checks.relative_to(REPO).as_posix()]=sha(checks)
    regression=out/"regression/checks.json"
    if read(regression).get("passed") is not True:raise ValueError("Original 109 prechecks required")
    protected[regression.relative_to(REPO).as_posix()]=sha(regression)
    plan={"protocol":"chapter4-R2-R5-six-slot-original-core-validation-v1","authorized":True,"execution_enabled":True,
        "created_utc":now(),"baseline_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip(),
        "authorization":"Current delegated instruction: user agrees to R2/R5 enhanced HEFT, blocking-edge OFF and ON, six slots under prior fixed proposal; no MILP, automatic merge or push",
        "prior_proposal_sha256":sha(DESIGN/"validation_proposal.json"),"prior_false_declaration_left_unchanged":True,
        "environment":environment(),"resource_preflight":resources(),"source_sha256":protected,
        "input_identities":{r["case_id"]:{k:r[k] for k in ("input_sha256","config_sha256","raw_config_sha256")} for r in proposal["input_identities"]},
        "slots":[{"id":f"{n:02d}_{case}_{arm}","case":case,"arm":arm,"allow_blocking_edges":None if arm=="HEFT" else arm=="ON"}
                 for n,(case,arm) in enumerate(ORDER,1)],
        "budgets":{"method_s":300,"post_s":60,"method_calls":6,"method_total_s":1800,
            "post_calls_at_most":6,"post_total_s":360,"calendar_s":3600},
        "methods":{"HEFT":"Original heft_method.run_heft; common blocking.CompleteRecorder; stop after original initialization and its energy pass",
            "OFF":"Original blocking.execute_reconstruction, allow_blocking_edges=False",
            "ON":"Original blocking.execute_reconstruction, allow_blocking_edges=True"},
        "wrapper_disclosure":"HEFT algorithm unchanged; use same complete recorder as OFF/ON instead of heuristic_runner's separate bookkeeping/lower-bound prepass. No lower-bound certificate is computed or claimed.",
        "evaluation":"Original thermal.evaluate_candidate, full original scenes/nodes/window/energy and safe_receipt. No alternate parameters or approximations",
        "same_initialization":"Each call independently reloads input and runs original HEFT under its own 300s root; after completion compare candidate semantics, interval and ordered initialization candidates. Never force a historical or cross-call answer",
        "post":"One fresh process, independent <=60s root, same original evaluator on unchanged final candidate. Energy intervals must overlap. Not an independent numerical implementation",
        "stops":"No retry/refund/replacement. Normal budget or no-safe result retained. Technical/numerical/identity/post/uncertain failure stops later slots",
        "prechecks":{"new":str(checks.relative_to(REPO)),"new_sha256":sha(checks),"new_count":precheck["tests_run"],
            "original":str(regression.relative_to(REPO)),"original_count":read(regression)["tests_run"]},
        "no_old_claims_or_candidates_reused":True,"scope":"Two same-family validation cases, one call per arm; no generalization, statistical speedup or optimality claim"}
    verify(plan)
    snapshot=out/"source_snapshot"
    for relative in protected:
        if "/results/" not in relative:
            target=snapshot/relative;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(REPO/relative,target)
    save(out/"plan.json",plan)
    print(json.dumps({"prepared":str(out),"source_identities":len(protected),"slots":plan["slots"],"resources":plan["resource_preflight"]}),flush=True)


def dispatch(arm,loader,folder,budget,bindings):
    if arm=="HEFT":
        from .lifecycle import execute_heft
        return execute_heft(loader,folder,bindings=bindings,budget=budget)
    if arm in ("OFF","ON"):
        from research.chapter4_scheduler.blocking.method import execute_reconstruction
        return execute_reconstruction(loader,folder,bindings=bindings,budget=budget,seconds=300,
            allow_blocking_edges=arm=="ON")
    raise ValueError("Unknown arm")


def normal_outcome(result):
    if result["run_terminal"] in ("SEARCH_COMPLETED","BUDGET_EXHAUSTED","NORMAL_NO_SAFE"):
        return True
    # Retain the original OFF/ON raw classification without changing its code.
    return (result["run_terminal"]=="UNRESOLVED_STOP" and result["reason"]=="INITIALIZATION_NOT_COMPLETED"
        and (result.get("initialization") or {}).get("status")=="NO_SAFE_CONSTRUCTED_WITNESS"
        and result.get("safe_candidate") is None
        and all(row["receipt"]["state"]=="THERMAL_VIOLATION" for row in result.get("evaluations",[])))


def worker(out,slot_id,post=False):
    entered,started=time.monotonic(),now()
    plan=read(out/"plan.json");slot=next(s for s in plan["slots"] if s["id"]==slot_id)
    folder=out/"calls"/slot_id;phase="post" if post else "method"
    claim=read(folder/"claim.json")
    if claim["plan_sha256"]!=sha(out/"plan.json") or claim["slot"]!=slot:
        raise ValueError("Claim/plan mismatch")
    save(folder/(phase+"_started.json"),{"utc":started,"pid":os.getpid(),"root_monotonic":entered,"plan_sha256":sha(out/"plan.json")})
    outcome={"slot":slot,"phase":phase,"started_utc":started,"error":None}
    try:
        from timing import MethodBudget
        budget=MethodBudget(60 if post else 300)
        budget.start,budget.deadline=entered,entered+budget.seconds
        root=(budget.start,budget.deadline,budget.seconds,budget.clock)
        with budget.phase("frozen_identity_and_selected_imports"):
            verify(plan)
            from research.chapter4_scheduler.blocking.method import Bindings
            from heft_method import run_heft
            from thermal import evaluate_candidate
            from p0_batch.run_p0 import fresh_input
            from .lifecycle import execute_heft
        if post:
            with budget.phase("read_original_final_evidence"):
                result=read(folder/"method/result.json");instance=read(folder/"method/input_instance.json");config=read(folder/"method/input_config.json")
                candidate=result["safe_candidate"]
                immutable={"result":sha(folder/"method/result.json"),"input":digest(instance),"candidate":digest(candidate),"config":digest(config)}
            receipt=evaluate_candidate(instance,candidate,config["accuracy_targets"],budget)
            save(folder/"post_receipt.json",receipt)
            from h02_pair_preflight.receipts import safe_receipt
            energy=safe_receipt(instance,candidate,receipt,config["accuracy_targets"],60)
            lo,hi=map(F,result["evaluation"]["weighted_energy_J"])
            if max(lo,F(energy["lower"]))>min(hi,F(energy["upper"])):raise ValueError("Post energy intervals disjoint")
            if immutable!={"result":sha(folder/"method/result.json"),"input":digest(instance),"candidate":digest(candidate),"config":digest(config)}:
                raise ValueError("Post mutated arguments or original result")
            outcome.update(passed=True,energy=energy,immutable=immutable,timing=budget.summary())
        else:
            loads=[]
            def loader(active):
                if active is not budget or loads:raise ValueError("Input or root reused")
                loads.append(True)
                with budget.phase("fresh_original_input_expansion_and_hash_check"):
                    raw,config,instance=fresh_input(slot["case"],active)
                    actual={"input_sha256":digest(instance),"config_sha256":digest(config),"raw_config_sha256":digest(raw)}
                    if actual!=plan["input_identities"][slot["case"]]:raise ValueError("Frozen original input drift")
                    save(folder/"input_raw_config.json",raw)
                return config,instance
            result=dispatch(slot["arm"],loader,folder/"method",budget,Bindings(run_heft,evaluate_candidate,kind="REAL_CORE"))
            outcome.update(run_terminal=result["run_terminal"],reason=result["reason"],safe=result["safe_candidate"] is not None,
                initialization_completed=(result.get("initialization") or {}).get("status")=="BOUNDED_SEARCH_COMPLETED" and result.get("initial_safe_snapshot") is not None,
                fresh_input_calls=len(loads),timing=result["timing"],usable=result["usable_as_research_evidence"],
                result_sha256=sha(folder/"method/result.json"))
            if not normal_outcome(result):raise ValueError("Abnormal method outcome: "+str(result["reason"]))
        if root!=(budget.start,budget.deadline,budget.seconds,budget.clock):raise ValueError("Root reset or budget drift")
        verify(plan)
    except BaseException as error:
        outcome["error"]={"type":type(error).__name__,"message":str(error),"traceback":traceback.format_exc()}
    outcome.update(ended_utc=now(),process_body_wall_s=time.monotonic()-entered)
    save(folder/(phase+"_return.json"),outcome)
    print(json.dumps({k:outcome.get(k) for k in ("slot","phase","started_utc","ended_utc","run_terminal","safe","passed","error")}),flush=True)
    return bool(outcome["error"])


def batch(out):
    plan=read(out/"plan.json");verify(plan);began=time.monotonic()
    save(out/"batch_started.json",{"utc":now(),"pid":os.getpid(),"plan_sha256":sha(out/"plan.json"),"resources":resources()})
    consumed=[];posts=[];error=None
    for slot in plan["slots"]:
        if time.monotonic()-began+500>plan["budgets"]["calendar_s"]:
            error="INSUFFICIENT_CALENDAR_FOR_COMPLETE_SLOT";break
        folder=out/"calls"/slot["id"];folder.mkdir(parents=True,exist_ok=False)
        save(folder/"claim.json",{"utc":now(),"slot":slot,"plan_sha256":sha(out/"plan.json"),"no_retry":True})
        consumed.append(slot["id"])
        for phase,timeout in (("worker",420),("post",70)):
            if phase=="post":
                if not read(folder/"method_return.json")["safe"]:break
                save(folder/"post_claim.json",{"utc":now(),"plan_sha256":sha(out/"plan.json"),"no_retry":True})
                posts.append(slot["id"])
            cmd=[sys.executable,"-B","-m","research.chapter4_scheduler.validation.run",phase,"--out",str(out),"--slot",slot["id"]]
            save(folder/(phase+"_command.json"),{"argv":cmd,"cwd":str(REPO),"utc":now()})
            print(json.dumps({"launch":slot["id"],"phase":phase,"utc":now()}),flush=True)
            try:
                process=subprocess.run(cmd,cwd=REPO,capture_output=True,text=True,timeout=timeout)
                (folder/(phase+"_stdout.log")).write_text(process.stdout,encoding="utf-8")
                (folder/(phase+"_stderr.log")).write_text(process.stderr,encoding="utf-8")
                if process.returncode:
                    error="WORKER_FAILURE:"+slot["id"]+":"+phase;break
            except subprocess.TimeoutExpired as exc:
                (folder/(phase+"_timeout.log")).write_text(str(exc),encoding="utf-8")
                for label,value in (("stdout",exc.stdout),("stderr",exc.stderr)):
                    if value:(folder/(phase+"_partial_"+label+".log")).write_bytes(value if isinstance(value,bytes) else value.encode())
                error="UNCERTAIN_TIMEOUT:"+slot["id"]+":"+phase;break
        if error:break
    record={"started":read(out/"batch_started.json"),"ended_utc":now(),"wall_s":time.monotonic()-began,
        "consumed_method_slots":consumed,"consumed_post_slots":posts,"error":error,
        "not_run":[s["id"] for s in plan["slots"] if s["id"] not in consumed]}
    save(out/"batch_return.json",record);print(json.dumps(record),flush=True)
    return bool(error)


def weighted_parts(instance,receipt):
    return {part:[str(sum(F(s["weight"])*F(receipt["scenes"][s["id"]]["energy_components_J"][part][j])
        for s in instance["scenarios"])) for j in (0,1)] for part in ("activity","baseline","external_common","temperature_correction")}


def analyze(out):
    plan=read(out/"plan.json");verify(plan)
    from h02_pair_preflight.receipts import safe_receipt
    from schedules import validate_schedule
    rows=[];checks=[];tokens=[];receipts=0
    def check(name,passed):checks.append({"name":name,"passed":bool(passed)})
    for slot in plan["slots"]:
        folder=out/"calls"/slot["id"];file=folder/"method/result.json"
        if not file.exists():rows.append({**slot,"state":"NOT_RUN_OR_NO_RESULT"});continue
        r=read(file);instance=read(folder/"method/input_instance.json");config=read(folder/"method/input_config.json")
        init=r.get("initial_safe_snapshot");candidate=r.get("safe_candidate");evals=r.get("evaluations",[]);graphs=r.get("graph_proposals",[])
        check(slot["id"]+":input_identity",{"input_sha256":digest(instance),"config_sha256":digest(config),
            "raw_config_sha256":digest(read(folder/"input_raw_config.json"))}==plan["input_identities"][slot["case"]])
        if r.get("root_context"):tokens.append(r["root_context"]["root_token"])
        for row in evals:
            receipt=row["receipt"]
            check(slot["id"]+":candidate_hash",digest(row["candidate"])==row["candidate_sha256"])
            check(slot["id"]+":legality",receipt.get("legality")==validate_schedule(instance,row["candidate"]))
            if receipt.get("state")=="SAFE":
                safe_receipt(instance,row["candidate"],receipt,config["accuracy_targets"],300);receipts+=1
        post=read(folder/"post_return.json") if (folder/"post_return.json").exists() else None
        if post and post.get("passed"):
            pr=read(folder/"post_receipt.json");safe_receipt(instance,candidate,pr,config["accuracy_targets"],60);receipts+=1
            check(slot["id"]+":post_original_result_unchanged",post["immutable"]["result"]==sha(file))
        phases=r["timing"]["phase_records"]
        initphase=next((p for p in phases if p["phase"]=="heft_initialization"),None)
        freeze=next((p for p in phases if p["phase"]=="complete_initial_safe_freeze"),None)
        energy=r["evaluation"]["weighted_energy_J"] if r.get("evaluation") else None
        diagnostics=r.get("reconstruction_attempts",[])
        row={**slot,"state":r["state"],"run_terminal":r["run_terminal"],"reason":r["reason"],
            "initialization_completed":(r.get("initialization") or {}).get("status")=="BOUNDED_SEARCH_COMPLETED" and init is not None,
            "initial_candidate_sha256":init["candidate_sha256"] if init else None,"initial_semantic_sha256":semantic(init["candidate"]) if init else None,
            "initial_energy":init["receipt"]["weighted_energy_J"] if init else None,
            "initialization_metadata_sha256":digest(r.get("initialization")),
            "initial_candidate_order_sha256":digest([e["candidate_sha256"] for e in evals if e["phase"]=="initialization"]),
            "final_candidate_sha256":digest(candidate) if candidate else None,"final_energy":energy,
            "initial_parts_J":weighted_parts(instance,init["receipt"]) if init else None,
            "final_parts_J":weighted_parts(instance,r["evaluation"]) if energy else None,
            "method_root_s":r["timing"]["method_elapsed_s"],"process_body_s":read(folder/"method_return.json")["process_body_wall_s"],
            "initialization_wall_s":initphase["wall_s"] if initphase else None,"initial_freeze_at_s":freeze["end_s"] if freeze else None,
            "first_safe_at_s":r.get("first_safe_at_s"),"first_strict_improvement_at_s":r.get("first_graph_strict_improvement_at_s"),
            "post_root_s":post["timing"]["method_elapsed_s"] if post and post.get("passed") else None,
            "post_passed":bool(post and post.get("passed")),"full_evaluator_calls":sum(not e.get("cache_hit",False) for e in evals),
            "initial_evaluator_calls":sum(e["phase"]=="initialization" and not e.get("cache_hit",False) for e in evals),
            "refinement_evaluator_calls":sum(e["phase"]=="refinement" and not e.get("cache_hit",False) for e in evals),
            "cache_hits":r.get("cache_hits",0),"graph_proposals":len(graphs),"graph_improvements":r["graph_strict_improvements"],
            "extra_edge_attempts":sum(d["extra_resource_edge"] is not None for d in diagnostics),
            "accepted_packets":[p for p in graphs if p["strict_accepted"]],
            "final_peaks_degC":{sid:s["peaks_degC"] for sid,s in r["evaluation"]["scenes"].items()} if energy else None,
            "result_sha256":sha(file),"timing":r["timing"]}
        rows.append(row)
        check(slot["id"]+":OFF_no_extra",slot["arm"]!="OFF" or not any(p.get("additional_reversed_edges") for p in graphs))
        check(slot["id"]+":HEFT_no_refinement",slot["arm"]!="HEFT" or not graphs and not diagnostics)
    comparisons=[]
    for case in ("base__R2","base__R5"):
        group=[r for r in rows if r["case"]==case];complete=len(group)==3 and all(r.get("initialization_completed") for r in group)
        matching=complete and all(len({digest(r[k]) for r in group})==1 for k in ("initial_semantic_sha256","initial_energy","initialization_metadata_sha256","initial_candidate_order_sha256"))
        comparative={"case":case,"three_completed_equal_initializations":matching,"arms":{}}
        off=next((r for r in group if r["arm"]=="OFF"),None)
        on=next((r for r in group if r["arm"]=="ON"),None)
        for r in group:
            if r.get("initial_energy") and r.get("final_energy"):
                old,new=F(r["initial_energy"][0]),F(r["final_energy"][1])
                comparative["arms"][r["arm"]]={"strictly_improves_own_initial":new<old,
                    "saving_lower_J":str(old-new),"saving_lower_percent":str((old-new)/old*100)}
        if off and on and off.get("final_energy") and on.get("final_energy"):
            comparative["ON_strictly_beats_OFF"]=F(on["final_energy"][1])<F(off["final_energy"][0])
            comparative["ON_final_candidate_equal_OFF"]=on["final_candidate_sha256"]==off["final_candidate_sha256"]
        comparisons.append(comparative)
    check("distinct_call_roots",len(tokens)==len(set(tokens)))
    check("frozen_sources_and_prior_archives_unchanged",True)
    check("all_returned_SAFE_had_post",all(r.get("post_passed") for r in rows if r.get("state")=="SAFE"))
    summary={"created_utc":now(),"batch":read(out/"batch_return.json"),"rows":rows,"comparisons":comparisons,
        "read_only_audit":{"passed":all(c["passed"] for c in checks),"checks":checks,"count":len(checks),"complete_safe_receipts_audited":receipts,"new_physical_evaluations":0},
        "budget_comparability":"Same 300s cap, independent charged initialization and identical complete evaluator/recorder; actual early-stop times and evaluation counts differ and are reported",
        "limitations":["Two same-family validation cases, one call per arm","Not a blind external/IID test set","Same evaluator reused for post; no independent numerical implementation","No MILP or optimality certificate","Original formal_experiment_result=false labels retained","No automatic commit, merge or push"]}
    save(out/"summary.json",summary)
    print(json.dumps({"comparisons":comparisons,"audit_passed":summary["read_only_audit"]["passed"],"audit_checks":len(checks),
        "audited_safe_receipts":receipts,"rows":[{k:r.get(k) for k in ("id","state","final_energy","method_root_s","full_evaluator_calls","refinement_evaluator_calls","graph_improvements","post_passed")} for r in rows]},ensure_ascii=False),flush=True)


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("action",choices=("prepare","batch","worker","post","analyze"));p.add_argument("--out",required=True,type=Path);p.add_argument("--checks",type=Path);p.add_argument("--slot")
    args=p.parse_args();out=args.out.resolve();out.relative_to(REPO/"research/chapter4_scheduler/results")
    if args.action=="prepare":prepare(out,args.checks.resolve())
    elif args.action=="batch":return batch(out)
    elif args.action in ("worker","post"):return worker(out,args.slot,args.action=="post")
    else:analyze(out)
    return 0


if __name__=="__main__":sys.exit(main())
