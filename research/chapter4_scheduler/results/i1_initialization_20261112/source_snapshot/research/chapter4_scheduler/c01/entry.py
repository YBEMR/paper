"""Three real C01 lifecycle engineering smoke paths, never formal comparison."""
import argparse
from copy import deepcopy
from datetime import datetime,timezone
from fractions import Fraction as F
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(REPO),str(REPO/"research/chapter3_experiments")]
from research.chapter4_scheduler.mechanism_check.run import read,save,sha,digest,environment
from research.chapter4_scheduler.comparison.core import EvaluationJournal,normalize,CLOCK_ORIGIN
from research.chapter4_scheduler.comparison.run import resources,assert_root,THREADS
from .input import load_c01,SOURCE,SOURCE_SHA256
from .dispatch import dispatch

BASE="183701e3394454ad588f538085bc06f08e7621a3"
BRANCH="chapter4/r2-r5-validation-20261107"
LIMITS={"method_s":30,"method_calls":3,"method_total_s":90,"post_s":10,"post_calls_at_most":3,
        "post_total_s_at_most":30,"calendar_s":240,"method_process_watchdog_s":45,"post_process_watchdog_s":20}
SLOTS=[{"id":"01_C01_HEFT","arm":"HEFT","seed":None},
       {"id":"02_C01_ON","arm":"ON","seed":None},{"id":"03_C01_SA101","arm":"SA","seed":101}]


def now():return datetime.now(timezone.utc).isoformat()


def validate_plan(plan):
    if (plan.get("schema")!="c01-full-lifecycle-engineering-smoke-v1" or plan.get("purpose")!="ENGINEERING_ONLY_NOT_FORMAL_COMPARISON"
            or plan.get("formal_comparison") is not False or plan.get("slots")!=SLOTS
            or plan.get("limits")!=LIMITS or plan.get("input_file_sha256")!=SOURCE_SHA256
            or plan.get("thread_environment")!=THREADS):
        raise ValueError("NEW_C01_ENGINEERING_SCOPE_REQUIRED")


def verify(plan,*,protected=False):
    validate_plan(plan)
    if subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip()!=BASE:
        raise ValueError("C01_ENTRY_SUBJECT_CHANGED")
    if subprocess.check_output(["git","branch","--show-current"],cwd=REPO,text=True).strip()!=BRANCH:
        raise ValueError("C01_ENTRY_BRANCH_CHANGED")
    if environment()!=plan["environment"]:raise ValueError("C01_ENTRY_ENVIRONMENT_CHANGED")
    identities=dict(plan["source_sha256"])
    if protected:identities.update(plan["protected_sha256"])
    for name,value in identities.items():
        if sha(REPO/name)!=value:raise ValueError("C01_ENTRY_FROZEN_BYTES_CHANGED:"+name)


def prepare(out,checks):
    if out.exists():raise FileExistsError(str(out))
    checked=read(checks)
    if not checked.get("passed") or checked.get("forbidden_calls"):raise ValueError("PASSING_LIFECYCLE_TESTS_REQUIRED")
    parent=out.parent
    for name,count in (("c01_regression",17),("graph_regression",109),("comparison_regression",20),("SA_regression",21)):
        r=read(parent/name/"checks.json")
        if not r["passed"] or r["tests_run"]!=count:raise ValueError("PASSING_REGRESSIONS_REQUIRED:"+name)
    from timing import MethodBudget
    from sa_method import algorithm_parameters
    config,instance=load_c01(MethodBudget(5))
    available=resources()
    if not available["sufficient"]:raise ValueError("C01_ENTRY_RESOURCES_INSUFFICIENT")
    previous=read(REPO/"research/chapter4_scheduler/results/c01_migration_20261108/smoke/plan.json")
    sources=dict(previous["source_sha256"])
    for p in sorted(Path(__file__).parent.glob("*.py")):
        sources[p.relative_to(REPO).as_posix()]=sha(p)
        if checked["source_sha256"].get(p.relative_to(REPO).as_posix())!=sha(p):raise ValueError("LIFECYCLE_TEST_SOURCE_DRIFT")
    for p in (checks,parent/"protected_before.json",*(parent/name/"checks.json" for name in ("c01_regression","graph_regression","comparison_regression","SA_regression"))):
        sources[p.relative_to(REPO).as_posix()]=sha(p)
    plan={"schema":"c01-full-lifecycle-engineering-smoke-v1","purpose":"ENGINEERING_ONLY_NOT_FORMAL_COMPARISON",
        "formal_comparison":False,"created_utc":now(),"subject_commit":BASE,"branch":BRANCH,
        "authorization":"Current user instruction: connect complete original HEFT/ON/SA lifecycles, test and run bounded lightweight end-to-end smoke; no formal comparison, expansion, retry, commit, push or merge",
        "limits":LIMITS,"slots":SLOTS,"input_file_sha256":SOURCE_SHA256,
        "input_sha256":digest(instance),"config_sha256":digest(config),"input_id":instance["id"],
        "input_semantics":"Existing C1/C2 explicit DAG,230ms actual horizon,5ms grid,all72 modes,50/80C,original platform/control; config default400ms retained",
        "environment":environment(),"thread_environment":THREADS,"resources":available,
        "source_sha256":sources,"protected_sha256":read(parent/"protected_before.json"),
        "SA_parameters":algorithm_parameters(),
        "lifecycle_budget_bridge":"Isolated C01 HEFT wrapper differs only by accepting supplied (0,300] root and using it for cutoff flags; old300s lifecycle remains byte-identical, 300s equivalence tested. ON/SA use original native short-root APIs.",
        "initialization":"Fresh original native initialization for each call; no prior constructor, candidate, timetable, mapping or shared cache",
        "timing":CLOCK_ORIGIN+"; nominal and actual root both30s, no accelerated clock, hidden300s allowance or early budget reset; interpreter/standard launcher imports separately captured by process wall time",
        "accounting":"Common transparent EvaluationJournal; attempts,returned,validated physical SAFE,cache separate; same original continuous evaluator and complete gates",
        "post":"At most one fresh <=10s process-root per normally stopped SAFE method, same original evaluator, not independent numerical implementation",
        "stops":"No retries/refunds/replacements. Normal short-root expiry/noSAFE retained; technical/numerical/identity/post failure halts remaining paths. Partial initialization/ON coverage is disclosed, never extends cap.",
        "not_a_ranking":"Exactly one seed and short caps for interface coverage; record energy without method ranking or percentage-gain claims"}
    verify(plan,protected=True);out.mkdir(parents=True)
    save(out/"input_identity.json",{"source":SOURCE.relative_to(REPO).as_posix(),"source_file_sha256":SOURCE_SHA256,
        "schema":"ch3-method-entry-common-input-v1","input_sha256":digest(instance),"config_sha256":digest(config),"provenance_role":"Candidate-free common contract, not P0 raw-config triple"})
    for p in Path(__file__).parent.glob("*.py"):
        target=out/"source_snapshot"/p.name;target.parent.mkdir(exist_ok=True);shutil.copyfile(p,target)
    save(out/"plan.json",plan);save(out/"plan_identity.json",{"sha256":sha(out/"plan.json"),"utc":now()})
    print({"prepared":str(out),"plan_sha256":sha(out/"plan.json"),"limits":LIMITS,"source_count":len(sources)},flush=True)


def coverage(raw,arm):
    rows=raw.get("evaluations",[]);timing=raw.get("timing",{})
    init=raw.get("initialization") or {}
    return {"arm":arm,"complete_enhanced_HEFT_initialization":init.get("status")=="BOUNDED_SEARCH_COMPLETED" and raw.get("initial_safe_snapshot") is not None if arm in ("HEFT","ON") else None,
        "HEFT_energy_pass_physical_evaluations":sum(r["source"].startswith("heft:energy-pass:") and not r.get("cache_hit",False) for r in rows),
        "ON_target_phase_entered":any(p["phase"]=="activity_saving_targets" for p in timing.get("phase_records",[])),
        "ON_reconstruction_attempts":len(raw.get("reconstruction_attempts",[])),"ON_proposals":len(raw.get("graph_proposals",[])),
        "ON_graph_physical_evaluations":sum(r["source"].startswith("graph:") and not r.get("cache_hit",False) for r in rows),
        "SA_native_metadata_returned":raw.get("search") is not None,
        "SA_neighbour_candidate_requests":sum(r["source"].startswith("sa_neighbour_") for r in raw.get("candidate_requests",[])),
        "SA_native_counters":(raw.get("search") or {}).get("counters"),
        "scope":"Lifecycle coverage at short cutoff; never exhaustive search completion"}


def worker(out,slot_id,*,post=False):
    entered,started=time.monotonic(),now();phase="post" if post else "method";folder=out/"calls"/slot_id
    returned={"slot_id":slot_id,"phase":phase,"started_utc":started,"error":None,"normal_stop":False,"has_SAFE_archive":False,
              "formal_comparison_result":False,"purpose":"ENGINEERING_ONLY_NOT_FORMAL_COMPARISON"}
    budget=journal=raw=None
    try:
        from timing import MethodBudget
        budget=MethodBudget(LIMITS["post_s"] if post else LIMITS["method_s"])
        budget.start,budget.deadline=entered,entered+budget.seconds
        root=(budget.start,budget.deadline,budget.seconds,budget.clock)
        with budget.phase("C01_plan_sources_and_scientific_imports"):
            plan=read(out/"plan.json");verify(plan)
            if sha(out/"plan.json")!=read(out/"plan_identity.json")["sha256"]:raise ValueError("C01_ENTRY_PLAN_HASH_CHANGED")
            slot=next(s for s in plan["slots"] if s["id"]==slot_id)
            claim=read(folder/("post_claim.json" if post else "claim.json"))
            if claim["plan_sha256"]!=sha(out/"plan.json") or claim["slot"]!=slot:raise ValueError("C01_ENTRY_CLAIM_MISMATCH")
            if any(os.environ.get(k)!=v for k,v in THREADS.items()):raise ValueError("C01_ENTRY_THREADS_CHANGED")
            import thermal
            from heft_method import run_heft
            from sa_method import run_sa,algorithm_parameters
            from research.chapter4_scheduler.blocking.method import Bindings
            from research.chapter4_scheduler.validation.sa_adapter import SABindings
            from h02_pair_preflight.receipts import safe_receipt
            if algorithm_parameters()!=plan["SA_parameters"]:raise ValueError("C01_ENTRY_SA_PARAMETERS_CHANGED")
        with (folder/(phase+"_evaluation_journal.jsonl")).open("x") as stream:
            journal=EvaluationJournal(thermal.evaluate_candidate,budget,stream)
            if post:
                with budget.phase("C01_read_own_final_candidate"):
                    raw=read(folder/"method/result.json");config=read(folder/"method/input_config.json");instance=read(folder/"method/input_instance.json")
                    candidate=raw["safe_candidate"];immutable=(sha(folder/"method/result.json"),digest(config),digest(instance),digest(candidate))
                with budget.phase("complete_post_evaluation"):
                    receipt=journal(instance,candidate,config["accuracy_targets"],budget)
                save(folder/"post_receipt.json",receipt)
                energy=safe_receipt(instance,candidate,receipt,config["accuracy_targets"],LIMITS["post_s"])
                if receipt["completed_at_elapsed_s"]>=LIMITS["post_s"]:raise ValueError("C01_POST_SAFE_AFTER_CUTOFF")
                lo,hi=map(F,raw["evaluation"]["weighted_energy_J"])
                if max(lo,F(energy["lower"]))>min(hi,F(energy["upper"])):raise ValueError("C01_POST_ENERGY_DISJOINT")
                if immutable!=(sha(folder/"method/result.json"),digest(config),digest(instance),digest(candidate)):raise ValueError("C01_POST_ARGUMENT_MUTATION")
                timing=budget.summary();timing["clock_origin"]=CLOCK_ORIGIN
                returned.update(passed=True,normal_stop=True,has_SAFE_archive=True,energy=energy,timing=timing,evaluation_attempts=len(journal.attempts))
            else:
                loads=[]
                def loader(active):
                    if active is not budget or loads:raise ValueError("C01_FRESH_ROOT_AND_INPUT_REQUIRED")
                    loads.append(True)
                    with budget.phase("C01_candidate_free_common_input_read"):
                        config,instance=load_c01(active)
                        if (digest(config),digest(instance))!=(plan["config_sha256"],plan["input_sha256"]):raise ValueError("C01_INPUT_IDENTITY_CHANGED")
                        save(folder/"common_input_identity.json",{"source_file_sha256":SOURCE_SHA256,"input_sha256":digest(instance),
                            "config_sha256":digest(config),"instance_id":instance["id"],"actual_window_ms":instance["window_ms"],
                            "role":"Pinned common-input contract; no fabricated P0 raw configuration"})
                    return config,instance
                with patch.object(thermal,"evaluate_candidate",journal):
                    bindings=SABindings(run_sa,journal,"REAL_CORE") if slot["arm"]=="SA" else Bindings(run_heft,journal,"REAL_CORE")
                    raw=dispatch(slot["arm"],loader,folder/"method",budget,seed=slot["seed"],bindings=bindings)
                returned.update(normalize(raw,journal),slot=slot,fresh_input_calls=len(loads),coverage=coverage(raw,slot["arm"]),
                    raw_result_sha256=sha(folder/"method/result.json"),plan_sha256=sha(out/"plan.json"))
                if not returned["normal_stop"]:raise ValueError("C01_ABNORMAL_METHOD_STOP:"+str(returned.get("raw_reason")))
            assert_root(budget,root);verify(plan)
    except BaseException as error:
        returned["error"]={"type":type(error).__name__,"reason":str(error),"traceback":traceback.format_exc()}
        if budget is not None:
            timing=budget.summary();timing["clock_origin"]=CLOCK_ORIGIN;returned["failure_timing"]=timing
    returned.update(ended_utc=now(),process_body_wall_s=time.monotonic()-entered,
                    evaluation_attempts_journal=deepcopy(journal.attempts) if journal else [])
    save(folder/(phase+"_return.json"),returned)
    print({k:returned.get(k) for k in ("slot_id","phase","normal_stop","has_SAFE_archive","terminal","coverage","error")},flush=True)
    return bool(returned["error"])


def batch(out):
    plan=read(out/"plan.json");verify(plan,protected=True)
    if sha(out/"plan.json")!=read(out/"plan_identity.json")["sha256"]:raise ValueError("C01_ENTRY_PLAN_HASH_CHANGED")
    began=time.monotonic();save(out/"batch_started.json",{"utc":now(),"plan_sha256":sha(out/"plan.json"),"resources":resources()})
    consumed=[];posts=[];error=None;env=dict(os.environ,**THREADS)
    for slot in plan["slots"]:
        if time.monotonic()-began+65>LIMITS["calendar_s"]:error="INSUFFICIENT_FULL_SLOT_CALENDAR";break
        if not resources()["sufficient"]:error="RESOURCE_PREFLIGHT_FAILED";break
        verify(plan)
        folder=out/"calls"/slot["id"];folder.mkdir(parents=True,exist_ok=False)
        save(folder/"claim.json",{"utc":now(),"slot":slot,"plan_sha256":sha(out/"plan.json"),"no_retry":True});consumed.append(slot["id"])
        for phase,watchdog in (("worker",45),("post",20)):
            if phase=="post":
                if not read(folder/"method_return.json")["has_SAFE_archive"]:break
                save(folder/"post_claim.json",{"utc":now(),"slot":slot,"plan_sha256":sha(out/"plan.json"),"no_retry":True});posts.append(slot["id"])
            command=[sys.executable,"-B","-m","research.chapter4_scheduler.c01.entry",phase,"--out",str(out),"--slot",slot["id"]]
            record={"argv":command,"cwd":str(REPO),"started_utc":now(),"thread_environment":THREADS,"process_watchdog_s":watchdog}
            save(folder/(phase+"_command_started.json"),record);start=time.monotonic()
            print({"event":"START","slot":slot,"phase":phase,"utc":now()},flush=True)
            try:
                p=subprocess.run(command,cwd=REPO,env=env,capture_output=True,text=True,timeout=watchdog)
                (folder/(phase+"_stdout.log")).write_text(p.stdout);(folder/(phase+"_stderr.log")).write_text(p.stderr)
                record.update(ended_utc=now(),wall_s=time.monotonic()-start,exit_code=p.returncode);save(folder/(phase+"_command_return.json"),record)
                if p.returncode:error=slot["id"]+":"+phase+":NONZERO_EXIT";break
                r=read(folder/("method_return.json" if phase=="worker" else "post_return.json"))
                if r.get("error") or not r.get("normal_stop"):error=slot["id"]+":"+phase+":ABNORMAL_RETURN";break
                print({"event":"DONE","slot":slot,"phase":phase,"terminal":r.get("terminal"),"coverage":r.get("coverage"),"utc":now()},flush=True)
            except BaseException as failure:
                if isinstance(failure,subprocess.TimeoutExpired):
                    for name,value in (("stdout",failure.stdout),("stderr",failure.stderr)):
                        (folder/(phase+"_partial_"+name+".log")).write_bytes(value.encode() if isinstance(value,str) else value or b"")
                save(folder/(phase+"_process_failure.json"),{"utc":now(),"reason":str(failure),"traceback":traceback.format_exc()})
                error=slot["id"]+":"+phase+":"+type(failure).__name__;break
        if error:break
    try:verify(plan,protected=True)
    except Exception as failure:error=(error or "")+";FINAL_IDENTITY_FAILURE:"+str(failure)
    result={"ended_utc":now(),"wall_s":time.monotonic()-began,"consumed_method_slots":consumed,"consumed_post_slots":posts,
            "error":error,"completed":not error and len(consumed)==3,"formal_comparison":False,"plan_sha256":sha(out/"plan.json"),"no_retry_or_refund":True}
    save(out/"batch_return.json",result);print(result,flush=True);return not result["completed"]


def main():
    parser=argparse.ArgumentParser();parser.add_argument("phase",choices=("prepare","batch","worker","post"));parser.add_argument("--out",required=True,type=Path);parser.add_argument("--checks",type=Path);parser.add_argument("--slot")
    args=parser.parse_args();out=args.out.resolve();out.relative_to(REPO/"research/chapter4_scheduler/results")
    if args.phase=="prepare":prepare(out,args.checks.resolve());return 0
    if args.phase=="batch":return batch(out)
    return worker(out,args.slot,post=args.phase=="post")


if __name__=="__main__":sys.exit(main())
