"""Read-only C01 component receipt/source audit; no additional evaluation."""
from contextlib import ExitStack
from datetime import datetime,timezone
from fractions import Fraction as F
from pathlib import Path
import sys
import time
from unittest.mock import patch

OUT=Path(__file__).resolve().parent;REPO=OUT.parents[3]
sys.path[:0]=[str(REPO),str(REPO/"research/chapter3_experiments")]
from research.chapter4_scheduler.mechanism_check.run import read,save,sha,digest
from research.chapter4_scheduler.c01.smoke import verify
from schedules import validate_schedule
from h02_pair_preflight.receipts import safe_receipt

started=datetime.now(timezone.utc).isoformat();clock=time.monotonic();checks=[]
def check(name,value):
    checks.append({"name":name,"passed":bool(value)})
    if not value:raise AssertionError(name)
def deny(*args,**kwargs):raise AssertionError("AUDIT_FORBIDS_SEARCH_AND_THERMAL_INTEGRATION")
with ExitStack() as stack:
    for target in ("thermal.evaluate_candidate","thermal.evaluate_piecewise","heft_method.run_heft","heft_method.build_heft_candidate","sa_method.run_sa"):
        stack.enter_context(patch(target,side_effect=deny))
    smoke=OUT/"smoke";plan=read(smoke/"plan.json");verify(plan,protected=True)
    check("plan hash",sha(smoke/"plan.json")==read(smoke/"plan_identity.json")["sha256"])
    lineage=read(OUT/"lineage_audit.json")
    check("original lineage sources intact",lineage["passed"] and all(sha(REPO/p)==h for p,h in lineage["source_files_sha256"].items()))
    for folder,count in (("unit_run02",17),("graph_regression",109),("comparison_regression",20)):
        r=read(OUT/folder/"checks.json");check(folder+" passing guarded tests",r["passed"] and r["tests_run"]==count and not r["forbidden_calls"])
    result=read(smoke/"result.json");instance=read(smoke/"input_instance.json");config=read(smoke/"input_config.json")
    check("correct existing C01 input identity",digest(instance)==lineage["input_sha256"] and digest(config)==lineage["config_sha256"])
    check("exact component counts and no formal claim",result["constructor_calls"]==result["graph_generator_calls"]==result["graph_packets"]==1 and result["thermal_calls"]==2 and result["formal_comparison"] is False)
    check("bounded successful component stop",result["status"]=="COMPONENTS_VERIFIED" and result["error"] is None and result["wall_s"]<60)
    check("structure root within bound",result["structure_timing"]["method_elapsed_s"]<10)
    original_units=None
    for component in result["component_results"]:
        label=component["label"];candidate=read(smoke/(label+"_candidate.json"));receipt=read(smoke/(label+"_receipt.json"))
        check(label+": candidate digest",digest(candidate)==component["candidate_sha256"])
        legality=validate_schedule(instance,candidate)
        check(label+": full twelve-node schedule legality",legality==receipt["legality"] and legality["state"]=="SCHEDULE_VALID_THERMAL_UNCHECKED")
        energy=safe_receipt(instance,candidate,receipt,config["accuracy_targets"],10)
        check(label+": full SAFE evidence",energy==component["energy"] and receipt["state"]=="SAFE")
        check(label+": original horizon for both scenes",set(receipt["scenes"])=={"C1","C2"} and all(r["complete"] and F(r["covered_until_s"])==F(23,100) for r in receipt["scenes"].values()))
        check(label+": formed before original cutoff",0<=receipt["completed_at_elapsed_s"]<10 and receipt["completed_at_elapsed_s"]<=component["timing"]["method_elapsed_s"])
        if original_units is None:original_units=legality["shared_deployment"]
        else:check(label+": original fixed-unit graph scope",legality["shared_deployment"]==original_units)
    packet=read(smoke/"first_graph_packet.json");scene=next(s for s in instance["scenarios"] if s["id"]==packet["scene_id"])
    task_edges={(e["from"],e["to"]) for e in packet["edges"] if "task_dependency" in e["reasons"]}
    check("all original task edges survive graph reconstruction",task_edges=={tuple(e) for e in scene["dependencies"]})
    check("unselected scene preserved",packet["candidate"]["scenes"]["C2"]==read(smoke/"fresh_native_constructor_candidate.json")["scenes"]["C2"])
    diagnostics=read(smoke/"graph_diagnostics.json")
    check("internal graph trials recorded",len(diagnostics)>0 and len(packet["additional_reversed_edges"])<=1)
    trace={"internal_reconstruction_attempts":len(diagnostics),
           "complete_legal_attempts":sum(d["state"]=="COMPLETE_LEGAL_CANDIDATE" for d in diagnostics),
           "rejected_attempts":sum(d["state"]!="COMPLETE_LEGAL_CANDIDATE" for d in diagnostics),
           "extra_resource_edge_trials":sum(d["extra_resource_edge"] is not None for d in diagnostics),
           "selected_packet_additional_edges":packet["additional_reversed_edges"],
           "selected_scene":packet["scene_id"],"selected_stages":packet["selected_stages"],"target":packet["energy_target"]}
record={"started_utc":started,"ended_utc":datetime.now(timezone.utc).isoformat(),"wall_s":time.monotonic()-clock,
    "passed":all(c["passed"] for c in checks),"checks":checks,"assertion_count":len(checks),"trace":trace,
    "main_comparison_protected_files":len(plan["protected_main_comparison_sha256"]),"source_identities":len(plan["source_sha256"]),
    "real_thermal_calls":0,"real_method_calls":0,
    "nature":"Read-only source/archive hashes and original schedule/full-receipt gates; same receipt verifier, no independent thermal numerical implementation",
    "selection_label_clarification":"Plan 'no energy-based selection' means no posthoc selection using new full thermal-energy results; the unchanged ON generator retains its pre-existing activity-saving order and nonthermal ranking. Internal 75 reconstructions are not 75 thermal evaluations."}
save(OUT/"audit.json",record)
print({k:record[k] for k in ("passed","assertion_count","wall_s","trace","main_comparison_protected_files")},flush=True)
