"""One bounded C01 component check, not HEFT/ON/SA method comparison."""
import argparse
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import shutil
import sys
import time
import traceback

REPO=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(REPO),str(REPO/"research/chapter3_experiments")]
from research.chapter4_scheduler.mechanism_check.run import read,save,sha,digest,environment
from .input import load_c01,SOURCE,SOURCE_SHA256

LIMITS={"structure_root_s":10,"native_HEFT_constructor_calls":1,"graph_packets_at_most":1,
        "thermal_calls_at_most":2,"thermal_root_s_each":10,"thermal_total_s_at_most":20,"calendar_s":60,"retries":0}


def now():return datetime.now(timezone.utc).isoformat()


def validate_plan(plan):
    if (plan.get("schema")!="c01-component-migration-smoke-v1" or plan.get("limits")!=LIMITS
            or plan.get("formal_comparison") is not False or plan.get("input_file_sha256")!=SOURCE_SHA256):
        raise ValueError("C01_SMOKE_SCOPE_CHANGED")


def verify(plan,*,protected=False):
    validate_plan(plan)
    if environment()!=plan["environment"]:raise ValueError("C01_SMOKE_ENVIRONMENT_CHANGED")
    for name,value in plan["source_sha256"].items():
        if sha(REPO/name)!=value:raise ValueError("C01_SMOKE_SOURCE_CHANGED:"+name)
    if protected:
        for name,value in plan["protected_main_comparison_sha256"].items():
            if sha(REPO/name)!=value:raise ValueError("MAIN_COMPARISON_CHANGED:"+name)


def prepare(out,checks):
    if out.exists():raise FileExistsError(str(out))
    checked=read(checks)
    if not checked["passed"] or checked["forbidden_calls"]:raise ValueError("PASSING_C01_PRECHECK_REQUIRED")
    parent=out.parent
    if not read(parent/"lineage_audit.json")["passed"]:raise ValueError("VERIFIED_ORIGINAL_LINEAGE_REQUIRED")
    previous=REPO/"research/chapter4_scheduler/results/main_comparison_20261108/execution/plan.json"
    sources=dict(read(previous)["source_sha256"])
    for p in sorted(Path(__file__).parent.glob("*.py")):
        sources[p.relative_to(REPO).as_posix()]=sha(p)
        if checked["source_sha256"].get(p.relative_to(REPO).as_posix())!=sha(p):
            raise ValueError("C01_PRECHECK_SOURCE_DRIFT")
    for p in (SOURCE,checks,parent/"lineage_audit.json",REPO/"research/chapter3_method_entry_preparation/prepare.py"):
        sources[p.relative_to(REPO).as_posix()]=sha(p)
    plan={"schema":"c01-component-migration-smoke-v1","created_utc":now(),"formal_comparison":False,
        "authorization":"Current user task permits minimal C01 adaptation and bounded unit/component smoke; no formal comparison or new task-family experiment",
        "limits":LIMITS,"input_file_sha256":SOURCE_SHA256,"input_identity":"Existing C01 C1/C2 candidate-free common contract; 230ms,5ms,original beta13/10 and legal modes",
        "selection":"One new original HEFT constructor, then at most the first legal packet from unchanged ON generator; no energy-based selection, fallback, tuning or retry",
        "initialization":"No historic timetable/candidate import; constructor is not full enhanced HEFT energy pass",
        "evaluation":"At most base and first packet once each, original full-window evaluator and full SAFE gates; no extra post or method search",
        "scope":"Interface/graph/thermal continuity only; not algorithm performance, mechanism gain or generalization evidence",
        "environment":environment(),"source_sha256":sources,
        "protected_main_comparison_sha256":read(parent/"protected_main_comparison.json")}
    verify(plan,protected=True)
    out.mkdir(parents=True)
    for path in Path(__file__).parent.glob("*.py"):
        target=out/"source_snapshot"/path.name;target.parent.mkdir(exist_ok=True);shutil.copyfile(path,target)
    save(out/"plan.json",plan);save(out/"plan_identity.json",{"sha256":sha(out/"plan.json"),"utc":now()})
    print({"prepared":str(out),"sha256":sha(out/"plan.json"),"limits":LIMITS},flush=True)


def execute(out):
    entered=time.monotonic();started=now();plan=read(out/"plan.json");verify(plan,protected=True)
    if sha(out/"plan.json")!=read(out/"plan_identity.json")["sha256"]:raise ValueError("C01_SMOKE_PLAN_CHANGED")
    save(out/"claim.json",{"utc":now(),"plan_sha256":sha(out/"plan.json"),"no_retry":True})
    result={"started_utc":started,"formal_comparison":False,"constructor_calls":0,"graph_generator_calls":0,
            "graph_packets":0,"thermal_calls":0,"error":None,"status":"NOT_COMPLETED","plan_sha256":sha(out/"plan.json")}
    def calendar():
        if time.monotonic()-entered>=LIMITS["calendar_s"]:raise RuntimeError("C01_SMOKE_CALENDAR_EXHAUSTED")
    try:
        root_entered=time.monotonic()
        from timing import MethodBudget
        structure=MethodBudget(10);structure.start,structure.deadline=root_entered,root_entered+10
        with structure.phase("fresh_input_constructor_and_first_graph_packet"):
            from heft_method import build_heft_candidate
            from research.chapter4_scheduler.blocking.method import candidate_packets
            from schedules import validate_schedule
            config,instance=load_c01(structure)
            result["constructor_calls"]+=1
            built=build_heft_candidate(instance,budget=structure)
            save(out/"constructor.json",built)
            base=built.get("candidate")
            if base is None:raise RuntimeError("ORIGINAL_CONSTRUCTOR_NO_CANDIDATE_NOT_INFEASIBILITY_PROOF")
            if validate_schedule(instance,base)["state"]!="SCHEDULE_VALID_THERMAL_UNCHECKED":raise RuntimeError("CONSTRUCTOR_CANDIDATE_NOT_LEGAL")
            diagnostics=[];result["graph_generator_calls"]+=1
            packet=next(candidate_packets(instance,base,structure,diagnostics=diagnostics,allow_blocking_edges=True),None)
            save(out/"graph_diagnostics.json",diagnostics)
            if packet is not None:
                result["graph_packets"]+=1;save(out/"first_graph_packet.json",packet)
                if validate_schedule(instance,packet["candidate"])["state"]!="SCHEDULE_VALID_THERMAL_UNCHECKED":raise RuntimeError("GRAPH_CANDIDATE_NOT_LEGAL")
            save(out/"input_instance.json",instance);save(out/"input_config.json",config)
        structure.check()
        result["structure_timing"]=structure.summary()
        result["structure_timing"]["clock_origin"]="Before selected scientific imports and fresh C01 read; native constructor and first graph generation included"
        candidates=[("fresh_native_constructor",base)]
        if packet is not None:candidates.append(("first_original_ON_packet",packet["candidate"]))
        results=[];result["component_results"]=results
        for label,candidate in candidates:
            calendar()
            root_entered=time.monotonic();budget=MethodBudget(10);budget.start,budget.deadline=root_entered,root_entered+10
            with budget.phase("fresh_input_and_complete_continuous_evaluation"):
                from thermal import evaluate_candidate
                from h02_pair_preflight.receipts import safe_receipt
                current_config,current_instance=load_c01(budget)
                evaluation_candidate=deepcopy(candidate)
                frozen=(digest(current_instance),digest(current_config),digest(evaluation_candidate))
                if (digest(current_instance),digest(current_config))!=(digest(instance),digest(config)):raise RuntimeError("C01_INPUT_CHANGED_BETWEEN_COMPONENTS")
                save(out/(label+"_candidate.json"),candidate)
                result["thermal_calls"]+=1
                receipt=evaluate_candidate(current_instance,evaluation_candidate,current_config["accuracy_targets"],budget)
                save(out/(label+"_receipt.json"),receipt)
                if receipt.get("state")!="SAFE":raise RuntimeError("ACTUAL_COMPONENT_RESULT_"+str(receipt.get("state")))
                energy=safe_receipt(current_instance,candidate,receipt,current_config["accuracy_targets"],10)
                if receipt["completed_at_elapsed_s"]>=10:raise RuntimeError("COMPONENT_SAFE_AFTER_DEADLINE")
                if frozen!=(digest(current_instance),digest(current_config),digest(evaluation_candidate)):raise RuntimeError("COMPONENT_ARGUMENT_MUTATION")
            timing=budget.summary();timing["clock_origin"]="Before fresh input/read/check and one full evaluation; no reference answer or budget reset"
            results.append({"label":label,"candidate_sha256":digest(candidate),"state":receipt["state"],"energy":energy,"timing":timing})
            save(out/(label+"_return.json"),results[-1])
        result.update(status="COMPONENTS_VERIFIED",component_results=results,
            graph_no_packet_is_not_global_infeasibility=packet is None)
        verify(plan,protected=True);calendar()
    except BaseException as error:
        result.update(status="STOPPED_WITHOUT_RETRY",error={"type":type(error).__name__,"reason":str(error),"traceback":traceback.format_exc()})
    result.update(ended_utc=now(),wall_s=time.monotonic()-entered)
    save(out/"result.json",result);print(result,flush=True)
    return bool(result["error"])


def main():
    parser=argparse.ArgumentParser();parser.add_argument("phase",choices=("prepare","execute"));parser.add_argument("--out",type=Path,required=True);parser.add_argument("--checks",type=Path)
    args=parser.parse_args();out=args.out.resolve();out.relative_to(REPO/"research/chapter4_scheduler/results")
    if args.phase=="prepare":prepare(out,args.checks.resolve());return 0
    return execute(out)


if __name__=="__main__":sys.exit(main())
