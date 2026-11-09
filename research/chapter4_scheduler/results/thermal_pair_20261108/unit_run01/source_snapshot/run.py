"""Single C01 paired initial-temperature experiment; original ON unchanged."""
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
from research.chapter4_scheduler.comparison.core import EvaluationJournal,normalize,CLOCK_ORIGIN,time_to_quality,conditional_statistics
from research.chapter4_scheduler.comparison.run import resources,assert_root,THREADS
from .input import load_pair,validate_pair,SOURCE,SOURCE_SHA256
from research.chapter4_scheduler.c01.formal import coverage

BASE="0a01ae35320507618df58dcb19f111548eafc971"
BRANCH="chapter4/r2-r5-validation-20261107"
LIMITS={"method_s":300,"method_calls":2,"method_total_s":600,"post_s":60,"post_calls_at_most":2,
        "post_total_s_at_most":120,"calendar_s":1200,"method_process_watchdog_s":420,"post_process_watchdog_s":90}
SLOTS=[{"id":"01_C01_ON_T50","arm":"ON","seed":None,"temperature":"50"},
       {"id":"02_C01_ON_T78","arm":"ON","seed":None,"temperature":"78"}]


def dispatch(arm,loader,workdir,budget,*,seed=None,bindings=None):
    if arm!="ON" or seed is not None:raise ValueError("ONLY_ORIGINAL_ON_PAIR")
    from research.chapter4_scheduler.blocking.method import execute_reconstruction
    return execute_reconstruction(loader,workdir,bindings=bindings,seconds=300,budget=budget,allow_blocking_edges=True)


def now():return datetime.now(timezone.utc).isoformat()


def validate_plan(plan):
    if (plan.get("schema")!="c01-original-ON-initial-temperature-pair-v1" or plan.get("purpose")!="C01_ON_INITIAL_TEMPERATURE_PAIR"
            or plan.get("paired_temperature_experiment") is not True or plan.get("slots")!=SLOTS
            or plan.get("limits")!=LIMITS or plan.get("input_file_sha256")!=SOURCE_SHA256
            or plan.get("thread_environment")!=THREADS):
        raise ValueError("ONLY_FIXED_TWO_TEMPERATURE_CALLS_REQUIRED")


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
    if not checked.get("passed") or checked.get("forbidden_calls") or checked["tests_run"]<12:raise ValueError("PASSING_PAIR_TESTS_REQUIRED")
    from timing import MethodBudget
    parent=out.parent;inputs={};pairs={}
    for temperature in ("50","78"):
        config,instance=load_pair(MethodBudget(5),temperature)
        inputs[temperature]={"config_sha256":digest(config),"input_sha256":digest(instance)};pairs[temperature]=(config,instance)
    available=resources()
    if not available["sufficient"]:raise ValueError("RESOURCES_INSUFFICIENT")
    previous=read(REPO/"research/chapter4_scheduler/results/c01_formal_20261108/execution/plan.json")
    sources=dict(previous["source_sha256"])
    for name,expected in sources.items():
        if sha(REPO/name)!=expected:raise ValueError("EXISTING_SOURCE_OR_EVIDENCE_DRIFT:"+name)
    for path in sorted(Path(__file__).parent.glob("*.py")):
        name=path.relative_to(REPO).as_posix();sources[name]=sha(path)
        if checked["source_sha256"].get(name)!=sources[name]:raise ValueError("PAIR_TEST_SOURCE_DRIFT")
    for path in (checks,parent/"session_start.json",parent/"model_review.json",SOURCE):sources[path.relative_to(REPO).as_posix()]=sha(path)
    paths=subprocess.check_output(["git","ls-files","-z","research/chapter4_scheduler/results"],cwd=REPO).decode().split("\0")
    protected={name:sha(REPO/name) for name in paths if name}
    plan={"schema":"c01-original-ON-initial-temperature-pair-v1","purpose":"C01_ON_INITIAL_TEMPERATURE_PAIR",
        "paired_temperature_experiment":True,"created_utc":now(),"subject_commit":BASE,"branch":BRANCH,
        "authorization":"Latest user approves ONE existing representative C01, original ON50/78C pair, fixed80C, no new repair, tuning, cases, push or merge",
        "limits":LIMITS,"slots":SLOTS,"input_file_sha256":SOURCE_SHA256,"inputs":inputs,
        "environment":environment(),"thread_environment":THREADS,"resources":available,
        "source_sha256":sources,"protected_sha256":protected,"precheck_tests":checked["tests_run"],
        "derivation":"Original fixed50C common contract validated intact first; fresh copies change only config.defaults.initial_temperature_degC plus both scenarios' four entry temperatures. New hashes; original id and all other fields retained, no forged old provenance.",
        "initialization":"Independent original full enhanced HEFT inside each300s root, no imported answer or shared candidate/cache; no SAFE initialization means no ON refinement or ON-completed claim",
        "timing":CLOCK_ORIGIN+";300s absolute deadline each including initialization and full physical evaluation; post separate<=60s; interpreter/serialization process time recorded separately",
        "evaluation":"Original full continuous outward-bounded evaluator, entire C1/C2 230ms,80C; actual SAFE/THERMAL_VIOLATION/UNRESOLVED and structural failures separate; retain point witnesses",
        "stops":"Original algorithm only. No SAFE constructed witness stops that group without post; not a proof of infeasibility and not ON completion. Critical technical/numerical/identity/post failure stops future slots. No retries/refunds/extension.",
        "scope":"One already exposed C01, only exogenous uniform initial state changed; no OFF ablation, new thermal-guided repair, measured hardware validation or generalization. Preheat energy excluded; same-evaluator post is not independent implementation."}
    verify(plan,protected=True);out.mkdir(parents=True)
    for temperature,(config,instance) in pairs.items():
        folder=out/"frozen_inputs"/("T"+temperature);folder.mkdir(parents=True)
        save(folder/"input_config.json",config);save(folder/"input_instance.json",instance)
        save(folder/"derivation.json",{"temperature_degC":temperature,"original_file_sha256":SOURCE_SHA256,**inputs[temperature],"original_contract_unchanged":True,"not_original_provenance_for_derived_input":True})
    shutil.copyfile(SOURCE,out/"original_common_input.json")
    for name in sources:
        if "/results/" not in name:
            target=out/"source_snapshot"/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(REPO/name,target)
    save(out/"plan.json",plan);save(out/"plan_identity.json",{"sha256":sha(out/"plan.json"),"utc":now()})
    print({"prepared":str(out),"plan_sha256":sha(out/"plan.json"),"source_count":len(sources),"protected_count":len(protected),"limits":LIMITS},flush=True)


def initialization_diagnostic(raw):
    status=(raw.get("initialization") or {}).get("status")
    initialized=status=="BOUNDED_SEARCH_COMPLETED" and raw.get("initial_safe_snapshot") is not None
    return {"HEFT_status":status,"complete_SAFE_initialization":initialized,
        "ON_search_entered":initialized and any(p["phase"]=="activity_saving_targets" for p in raw.get("timing",{}).get("phase_records",[])),
        "ON_search_completed":initialized and raw.get("run_terminal")=="SEARCH_COMPLETED",
        "no_SAFE_initialization_is_not_ON_completion":not initialized,
        "infeasibility_proved":False}


def worker(out,slot_id,*,post=False):
    entered,started=time.monotonic(),now();phase="post" if post else "method";folder=out/"calls"/slot_id
    returned={"slot_id":slot_id,"phase":phase,"started_utc":started,"error":None,"normal_stop":False,"has_SAFE_archive":False,
              "paired_temperature_experiment":True,"purpose":"C01_ON_INITIAL_TEMPERATURE_PAIR"}
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
            from research.chapter4_scheduler.blocking.method import Bindings
            from h02_pair_preflight.receipts import safe_receipt
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
                        config,instance=load_pair(active,slot["temperature"])
                        expected=plan["inputs"][slot["temperature"]]
                        if (digest(config),digest(instance))!=(expected["config_sha256"],expected["input_sha256"]):raise ValueError("C01_INPUT_IDENTITY_CHANGED")
                        save(folder/"common_input_identity.json",{"source_file_sha256":SOURCE_SHA256,"input_sha256":digest(instance),
                            "config_sha256":digest(config),"instance_id":instance["id"],"actual_window_ms":instance["window_ms"],
                            "temperature_degC":slot["temperature"],"role":"Separate derived-input hashes; original fixed50C contract preserved"})
                    return config,instance
                with patch.object(thermal,"evaluate_candidate",journal):
                    bindings=Bindings(run_heft,journal,"REAL_CORE")
                    raw=dispatch(slot["arm"],loader,folder/"method",budget,seed=slot["seed"],bindings=bindings)
                returned.update(normalize(raw,journal),slot=slot,fresh_input_calls=len(loads),coverage=coverage(raw,slot["arm"]),
                    raw_result_sha256=sha(folder/"method/result.json"),plan_sha256=sha(out/"plan.json"),initialization_diagnostic=initialization_diagnostic(raw))
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
        if time.monotonic()-began+510>LIMITS["calendar_s"]:error="INSUFFICIENT_FULL_SLOT_CALENDAR";break
        if not resources()["sufficient"]:error="RESOURCE_PREFLIGHT_FAILED";break
        verify(plan)
        folder=out/"calls"/slot["id"];folder.mkdir(parents=True,exist_ok=False)
        save(folder/"claim.json",{"utc":now(),"slot":slot,"plan_sha256":sha(out/"plan.json"),"no_retry":True});consumed.append(slot["id"])
        for phase,watchdog in (("worker",420),("post",90)):
            if phase=="post":
                if not read(folder/"method_return.json")["has_SAFE_archive"]:break
                save(folder/"post_claim.json",{"utc":now(),"slot":slot,"plan_sha256":sha(out/"plan.json"),"no_retry":True});posts.append(slot["id"])
            command=[sys.executable,"-B","-m","research.chapter4_scheduler.thermal_pair.run",phase,"--out",str(out),"--slot",slot["id"]]
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
            "error":error,"completed":not error and len(consumed)==2,"paired_temperature_experiment":True,"plan_sha256":sha(out/"plan.json"),"no_retry_or_refund":True}
    result["completion_semantics"]="Completed means two planned slots recorded normally, NOT two ON completions; see each initialization_diagnostic."
    result["ON_search_completed_slots"]=[sid for sid in consumed if (out/"calls"/sid/"method_return.json").exists() and read(out/"calls"/sid/"method_return.json").get("initialization_diagnostic",{}).get("ON_search_completed")]
    save(out/"batch_return.json",result);print(result,flush=True);return not result["completed"]

def main():
    parser=argparse.ArgumentParser();parser.add_argument("phase",choices=("prepare","batch","worker","post"));parser.add_argument("--out",required=True,type=Path);parser.add_argument("--checks",type=Path);parser.add_argument("--slot")
    args=parser.parse_args();out=args.out.resolve();out.relative_to(REPO/"research/chapter4_scheduler/results")
    if args.phase=="prepare":prepare(out,args.checks.resolve());return 0
    if args.phase=="batch":return batch(out)
    return worker(out,args.slot,post=args.phase=="post")


if __name__=="__main__":sys.exit(main())
