"""Read-only lifecycle-smoke audit. No new optimization or integration."""
from contextlib import ExitStack
from datetime import datetime,timezone
from fractions import Fraction as F
from pathlib import Path
import json
import sys
import time
from unittest.mock import patch

OUT=Path(__file__).resolve().parent;REPO=OUT.parents[3]
sys.path[:0]=[str(REPO),str(REPO/"research/chapter3_experiments")]
from research.chapter4_scheduler.mechanism_check.run import read,save,sha,digest
from research.chapter4_scheduler.c01.entry import verify,coverage,SLOTS,LIMITS
from research.chapter4_scheduler.comparison.core import normalize,EvaluationJournal,CLOCK_ORIGIN
from schedules import validate_schedule
from h02_pair_preflight.receipts import safe_receipt

started=datetime.now(timezone.utc).isoformat();clock=time.monotonic();checks=[];records=[];tokens=[];raws={}
def check(name,value):
    checks.append({"name":name,"passed":bool(value)})
    if not value:raise AssertionError(name)
def deny(*args,**kwargs):raise AssertionError("C01_AUDIT_FORBIDS_SEARCH_OR_INTEGRATION")
execution=OUT/"execution";plan=read(execution/"plan.json");batch=read(execution/"batch_return.json")
with ExitStack() as stack:
    for target in ("thermal.evaluate_candidate","thermal.evaluate_piecewise","heft_method.run_heft","heft_method.build_heft_candidate","sa_method.run_sa"):
        stack.enter_context(patch(target,side_effect=deny))
    verify(plan,protected=True)
    check("frozen plan hash",sha(execution/"plan.json")==read(execution/"plan_identity.json")["sha256"])
    check("three method and three post calls exactly once",batch["completed"] and not batch["error"] and batch["consumed_method_slots"]==[s["id"] for s in SLOTS] and batch["consumed_post_slots"]==[s["id"] for s in SLOTS])
    check("engineering only",plan["formal_comparison"] is False and batch["formal_comparison"] is False)
    for slot in SLOTS:
        folder=execution/"calls"/slot["id"];returned=read(folder/"method_return.json");raw=read(folder/"method/result.json");raws[slot["arm"]]=raw
        instance=read(folder/"method/input_instance.json");config=read(folder/"method/input_config.json")
        check(slot["id"]+": pinned full input",digest(instance)==plan["input_sha256"] and digest(config)==plan["config_sha256"])
        check(slot["id"]+": C01 horizon and modes intact",instance["window_ms"]=="230" and config["defaults"]["window_ms"]=="400" and len(instance["stage_modes"])==8 and sum(map(len,instance["stage_modes"].values()))==72)
        root=raw["root_context"];tokens.append(root["root_token"])
        check(slot["id"]+": actual30s root",root["root_seconds"]==returned["timing"]["limit_s"]==30 and float(root["root_deadline"])-float(root["root_start"])==30)
        check(slot["id"]+": fresh loader and no shared cache",returned["fresh_input_calls"]==1 and raw["candidate_or_cache_shared_between_calls"] is False)
        check(slot["id"]+": original result immutable",sha(folder/"method/result.json")==returned["raw_result_sha256"])
        check(slot["id"]+": normalized engineering stop",returned["normal_stop"] and returned["error"] is None and returned["formal_comparison_result"] is False)
        check(slot["id"]+": common input identity instead of P0 raw tuple",(folder/"common_input_identity.json").exists() and not (folder/"input_raw_config.json").exists())
        journal=EvaluationJournal(deny,object());journal.attempts=returned["evaluation_attempts_journal"]
        normalized=normalize(raw,journal)
        check(slot["id"]+": normalized counts and timing reproduced",all(returned[k]==v for k,v in normalized.items()))
        check(slot["id"]+": lifecycle coverage reproduced",returned["coverage"]==coverage(raw,slot["arm"]))
        with (folder/"method_evaluation_journal.jsonl").open() as stream:
            events=[json.loads(line) for line in stream]
        starts=[r for r in events if r["event"]=="START"];ends=[r for r in events if r["event"]!="START"]
        check(slot["id"]+": journal attempt boundaries",len(starts)==len(ends)==len(journal.attempts))
        for row in starts:check(slot["id"]+": journal candidate "+str(row["ordinal"]),digest(row["candidate"])==row["candidate_sha256"])
        safe=[];mapping_SAFE=0
        for index,row in enumerate(raw["evaluations"]):
            check(slot["id"]+": receipt candidate SHA "+str(index),digest(row["candidate"])==row["candidate_sha256"])
            if row.get("accepted_safe"):
                receipt=row["receipt"]
                check(slot["id"]+": identity "+str(index),receipt["evidence_identity"]=={"input_sha256":plan["input_sha256"],"candidate_sha256":row["candidate_sha256"]})
                check(slot["id"]+": complete DAG legality "+str(index),validate_schedule(instance,row["candidate"])==receipt["legality"])
                energy=safe_receipt(instance,row["candidate"],receipt,config["accuracy_targets"],30)
                check(slot["id"]+": timely full SAFE "+str(index),energy==row["energy"] and 0<=receipt["completed_at_elapsed_s"]<30)
                check(slot["id"]+": both230ms scenes "+str(index),set(receipt["scenes"])=={"C1","C2"} and all(s["complete"] and F(s["covered_until_s"])==F(23,100) for s in receipt["scenes"].values()))
                safe.append(row)
                mapping_SAFE+=row["source"]=="sa_neighbour_mapping" and not row.get("cache_hit",False)
        check(slot["id"]+": final archive backed by own full SAFE",any(r["candidate_sha256"]==digest(raw["safe_candidate"]) and r["receipt"]==raw["evaluation"] for r in safe))
        if slot["arm"]=="SA":
            check(slot["id"]+": seed and parameters intact",raw["seed"]==101 and raw["parameters"]==plan["SA_parameters"])
            check(slot["id"]+": best SAFE upper archive",F(raw["safe_upper_bound_J"])==min(F(r["energy"]["upper"]) for r in safe))
        post=read(folder/"post_return.json");receipt=read(folder/"post_receipt.json")
        energy=safe_receipt(instance,raw["safe_candidate"],receipt,config["accuracy_targets"],10)
        check(slot["id"]+": fresh full SAFE post",post["passed"] and not post["error"] and post["evaluation_attempts"]==1 and receipt["completed_at_elapsed_s"]<10 and energy==post["energy"])
        check(slot["id"]+": post interval overlap",max(F(energy["lower"]),F(raw["evaluation"]["weighted_energy_J"][0]))<=min(F(energy["upper"]),F(raw["evaluation"]["weighted_energy_J"][1])))
        check(slot["id"]+": corrected post clock and phase",post["timing"]["limit_s"]==10 and post["timing"]["clock_origin"]==CLOCK_ORIGIN and "complete_post_evaluation" in post["timing"]["phases_exclusive_s"])
        records.append({"slot":slot,"terminal":returned["terminal"],"counts":returned["counts"],"coverage":returned["coverage"],
            "energy_interval_J":returned["energy_interval_J"],"diagnostic_upper_J":float(F(returned["safe_upper_bound_J"])),
            "method_elapsed_s":returned["timing"]["method_elapsed_s"],"method_process_wall_s":read(folder/"worker_command_return.json")["wall_s"],
            "post_elapsed_s":post["timing"]["method_elapsed_s"],"first_SAFE_at_s":returned["first_SAFE_at_s"],
            "first_own_final_quality_at_s":returned["first_own_final_quality_at_s"],"physical_SAFE_mapping_evaluations":mapping_SAFE,
            "successful_post":True,"formal_comparison_result":False})
    check("independent invocation tokens",len(tokens)==len(set(tokens))==3)
    a,b=raws["HEFT"],raws["ON"]
    sequence=lambda r:[x["candidate_sha256"] for x in r["evaluations"] if x["phase"]=="initialization"]
    check("independent HEFT and ON completed same initialization",a["initial_safe_snapshot"]["candidate_sha256"]==b["initial_safe_snapshot"]["candidate_sha256"] and sequence(a)==sequence(b))
    check("HEFT full energy pass actually evaluated",records[0]["coverage"]["complete_enhanced_HEFT_initialization"] and records[0]["coverage"]["HEFT_energy_pass_physical_evaluations"]>0)
    check("ON target and reconstruction/evaluation path actually entered",records[1]["coverage"]["ON_target_phase_entered"] and records[1]["coverage"]["ON_reconstruction_attempts"]>0 and records[1]["coverage"]["ON_graph_physical_evaluations"]>0)
    check("SA neighbour search and uphill acceptance actually occurred",records[2]["coverage"]["SA_neighbour_candidate_requests"]>0 and records[2]["coverage"]["SA_native_counters"].get("accepted_uphill_midpoint",0)>0)
record={"started_utc":started,"ended_utc":datetime.now(timezone.utc).isoformat(),"wall_s":time.monotonic()-clock,
    "passed":all(c["passed"] for c in checks),"assertion_count":len(checks),"checks":checks,"rows":records,
    "source_identities":len(plan["source_sha256"]),"protected_existing_files":len(plan["protected_sha256"]),
    "counts_total":{k:sum(r["counts"][k] for r in records) for k in ("evaluation_attempts","returned_receipts","validated_SAFE_receipts","cache_hits","returned_unresolved_receipts")},
    "real_search_or_thermal_calls":0,"purpose":"Read-only engineering receipt/coverage audit, not formal ranking or independent thermal implementation",
    "batch":batch}
save(OUT/"audit.json",record)
save(OUT/"engineering_summary.json",{"purpose":"ENGINEERING_ONLY_NOT_FORMAL_COMPARISON","plan_sha256":batch["plan_sha256"],"batch":batch,"rows":records,"counts_total":record["counts_total"]})
print({"passed":record["passed"],"assertions":len(checks),"wall_s":record["wall_s"],"counts_total":record["counts_total"]},flush=True)
