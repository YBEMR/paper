"""Read-only independent aggregation/receipt audit of the frozen batch.

No independent thermal numerical implementation: integrations/search are
explicitly forbidden. Original full-receipt checks and schedule checks only.
"""
from collections import Counter
from contextlib import ExitStack
import csv
from datetime import datetime,timezone
from fractions import Fraction as F
from pathlib import Path
import json
import subprocess
import sys
import time
from unittest.mock import patch

OUT=Path(__file__).resolve().parent
REPO=OUT.parents[3]
sys.path[:0]=[str(REPO),str(REPO/"research/chapter3_experiments")]
from research.chapter4_scheduler.mechanism_check.run import read,save,sha,digest
from research.chapter4_scheduler.comparison.run import verify,slots
from research.chapter4_scheduler.comparison.core import EvaluationJournal,normalize,time_to_quality,conditional_statistics,CLOCK_ORIGIN
from schedules import validate_schedule
from h02_pair_preflight.receipts import safe_receipt,thermal_witness

execution=OUT/"execution"
plan=read(execution/"plan.json")
started=datetime.now(timezone.utc).isoformat();clock=time.monotonic()
checks=[];records=[];tokens=[];raws={};initials={}
def check(name,condition):
    checks.append({"name":name,"passed":bool(condition)})
    if not condition:raise AssertionError(name)
def deny(*args,**kwargs):raise AssertionError("READ_ONLY_AUDIT_FORBIDS_SEARCH_AND_INTEGRATION")
def energy_float(bounds):return [float(F(v)) for v in bounds] if bounds else None

with ExitStack() as stack:
    for target in ("thermal.evaluate_candidate","thermal.evaluate_piecewise","sa_method.run_sa","heft_method.run_heft"):
        stack.enter_context(patch(target,side_effect=deny))
    verify(plan,protected=True)
    check("plan hash",sha(execution/"plan.json")==read(execution/"plan_identity.json")["plan_sha256"])
    batch=read(execution/"batch_return.json")
    check("batch completeness flag reflects consumed slots",batch["completed"]==(not batch["error"] and len(batch["consumed_method_slots"])==14))
    check("frozen exact fourteen slots",plan["slots"]==slots())
    check("tracked scientific and historical bytes unchanged",not subprocess.check_output(["git","diff","HEAD","--name-only"],cwd=REPO))
    for slot in plan["slots"]:
        folder=execution/"calls"/slot["id"]
        if not (folder/"method_return.json").exists():
            records.append({"slot":slot,"state":"NOT_RUN_OR_PROCESS_FAILED","success":False});continue
        returned=read(folder/"method_return.json")
        if not (folder/"method/result.json").exists():
            records.append({"slot":slot,"state":"NO_RAW_METHOD_RESULT","success":False,"return":returned});continue
        raw=read(folder/"method/result.json");raws[slot["id"]]=raw
        instance=read(folder/"method/input_instance.json");config=read(folder/"method/input_config.json")
        root=raw["root_context"];tokens.append(root["root_token"])
        check(slot["id"]+": original input",digest(instance)==plan["input_identities"][slot["case"]]["input_sha256"])
        check(slot["id"]+": original config",digest(config)==plan["input_identities"][slot["case"]]["config_sha256"])
        check(slot["id"]+": 300s root",root["root_seconds"]==300 and float(root["root_deadline"])-float(root["root_start"])==300)
        check(slot["id"]+": no shared answer or cache",raw["candidate_or_cache_shared_between_calls"] is False)
        check(slot["id"]+": exact raw result digest",sha(folder/"method/result.json")==returned["raw_result_sha256"])
        if slot["arm"]=="SA":
            check(slot["id"]+": original SA seed and parameters",raw["seed"]==slot["seed"] and raw["parameters"]==plan["SA_parameters"])
        attempts=returned["evaluation_attempts_journal"]
        journal=EvaluationJournal(deny,object());journal.attempts=attempts
        unified=normalize(raw,journal)
        check(slot["id"]+": unified accounting reproduced",all(returned[k]==v for k,v in unified.items()))
        starts=[];ends=[]
        with (folder/"method_evaluation_journal.jsonl").open() as stream:
            for line in stream:
                item=json.loads(line)
                if item["event"]=="START":
                    check(slot["id"]+": journal full candidate SHA "+str(item["ordinal"]),digest(item["candidate"])==item["candidate_sha256"])
                    starts.append(item)
                else:ends.append(item)
        check(slot["id"]+": actual boundary starts and ends",len(starts)==len(ends)==len(attempts))
        check(slot["id"]+": journal order matches attempt record",[a["candidate_sha256"] for a in starts]==[a["candidate_sha256"] for a in attempts])
        valid=[];changed_mapping_safe=0;mapping_evaluated=0
        initial=(raw.get("initial_safe_snapshot") or {})
        for number,row in enumerate(raw["evaluations"]):
            candidate=row["candidate"];receipt=row["receipt"]
            check(slot["id"]+": candidate identity "+str(number),digest(candidate)==row["candidate_sha256"])
            if row.get("accepted_safe"):
                check(slot["id"]+": accepted receipt identity "+str(number),receipt["evidence_identity"]=={"input_sha256":digest(instance),"candidate_sha256":digest(candidate)})
                legality=validate_schedule(instance,candidate)
                check(slot["id"]+": full schedule legality "+str(number),legality==receipt["legality"] and legality["state"]=="SCHEDULE_VALID_THERMAL_UNCHECKED")
                energy=safe_receipt(instance,candidate,receipt,config["accuracy_targets"],300)
                check(slot["id"]+": complete timely SAFE "+str(number),energy==row["energy"] and 0<=receipt["completed_at_elapsed_s"]<300 and receipt["completed_at_elapsed_s"]<=row["returned_at_s"])
                valid.append(row)
                if row["source"]=="sa_neighbour_mapping" and not row.get("cache_hit",False):
                    changed_mapping_safe+=legality["shared_deployment"]!=initial.get("shared_deployment")
            elif receipt.get("state")=="THERMAL_VIOLATION":
                check(slot["id"]+": thermal violation witness "+str(number),bool(thermal_witness(instance,receipt,300)))
            if row["source"]=="sa_neighbour_mapping" and not row.get("cache_hit",False):mapping_evaluated+=1
        if raw.get("evaluation"):
            check(slot["id"]+": final candidate has own full SAFE",any(r["candidate_sha256"]==digest(raw["safe_candidate"]) and r["receipt"]==raw["evaluation"] for r in valid))
            if slot["arm"]=="SA":
                check(slot["id"]+": best upper archive preserved",F(raw["safe_upper_bound_J"])==min(F(r["energy"]["upper"]) for r in valid))
        post=read(folder/"post_return.json") if (folder/"post_return.json").exists() else None
        success=bool(returned.get("normal_stop") and not returned.get("error") and returned.get("has_SAFE_archive") and post and post.get("passed") and not post.get("error"))
        if post and post.get("passed"):
            receipt=read(folder/"post_receipt.json")
            energy=safe_receipt(instance,raw["safe_candidate"],receipt,config["accuracy_targets"],60)
            check(slot["id"]+": fresh complete SAFE post",energy==post["energy"] and receipt["completed_at_elapsed_s"]<60 and post["evaluation_attempts"]==1)
            lo,hi=map(F,raw["evaluation"]["weighted_energy_J"])
            check(slot["id"]+": post energy overlap",max(lo,F(energy["lower"]))<=min(hi,F(energy["upper"])))
            check(slot["id"]+": corrected post timing label",post["timing"]["clock_origin"]==CLOCK_ORIGIN and post["timing"]["limit_s"]==60 and "complete_post_evaluation" in post["timing"]["phases_exclusive_s"])
        if slot["arm"] in ("HEFT","ON"):
            initials[(slot["case"],slot["arm"])]=raw
        records.append({"slot":slot,"state":returned.get("terminal"),"success":success,
            "energy_interval_J":returned.get("energy_interval_J"),"energy_interval_J_float":energy_float(returned.get("energy_interval_J")),
            "counts":returned.get("counts"),"method_elapsed_s":returned["timing"]["method_elapsed_s"],
            "deadline_overshoot_s":returned["timing"]["deadline_overshoot_s"],
            "method_process_wall_s":read(folder/"worker_command_return.json")["wall_s"],
            "post_elapsed_s":post["timing"]["method_elapsed_s"] if post and post.get("passed") else None,
            "first_SAFE_at_s":returned["first_SAFE_at_s"],"first_strict_improvement_at_s":returned["first_strict_improvement_over_first_SAFE_at_s"],
            "first_own_final_quality_at_s":returned["first_own_final_quality_at_s"],
            "thermal_evaluation_phase_s":returned["timing"]["phases_exclusive_s"].get("complete_continuous_evaluation",0),
            "initialization_phase_records":returned["initialization_phase_records"],
            "SA_first_neighbour_assessment_at_s":returned.get("first_neighbour_assessment_at_s"),
            "SA_native_initialization_source":(raw.get("search") or {}).get("initialisation_source"),
            "SA_moves_proposed":(raw.get("search") or {}).get("moves_proposed"),
            "SA_counters":(raw.get("search") or {}).get("counters"),
            "physical_mapping_evaluations":mapping_evaluated,"full_SAFE_mapping_evaluations_changed_from_initial_deployment":changed_mapping_safe})
    check("independent root tokens",len(tokens)==len(set(tokens)))
    initial_comparison={}
    for case in ("base__R2","base__R5"):
        if (case,"HEFT") in initials and (case,"ON") in initials:
            a,b=initials[(case,"HEFT")],initials[(case,"ON")]
            same=a["initial_safe_snapshot"]["candidate_sha256"]==b["initial_safe_snapshot"]["candidate_sha256"]
            sequence=lambda r:[e["candidate_sha256"] for e in r["evaluations"] if e["phase"]=="initialization"]
            initial_comparison[case]={"candidate_sha256_equal":same,"initialization_candidate_sequence_equal":sequence(a)==sequence(b),
                "HEFT_initial":a["initial_safe_snapshot"]["energy"],"ON_initial":b["initial_safe_snapshot"]["energy"]}
            check(case+": fresh HEFT and ON initialization independently agrees",same and sequence(a)==sequence(b))
    by_case={}
    for case in ("base__R2","base__R5"):
        case_rows=[r for r in records if r["slot"]["case"]==case]
        refs={r["slot"]["arm"]:r for r in case_rows if r["slot"]["arm"] in ("HEFT","ON") and r["success"]}
        for row in case_rows:
            raw=raws.get(row["slot"]["id"])
            row["time_to_reference_upper_s"]={arm:time_to_quality(raw,ref["energy_interval_J"][1]) if raw else None for arm,ref in refs.items()}
            row["certified_strictly_below_reference"]={arm:bool(row.get("energy_interval_J") and F(row["energy_interval_J"][1])<F(ref["energy_interval_J"][0])) for arm,ref in refs.items()}
        sa=[r for r in case_rows if r["slot"]["arm"]=="SA"]
        successful=[r for r in sa if r["success"]]
        stats=conditional_statistics([r["energy_interval_J"][1] for r in successful],5)
        summary=read(execution/"summary.json")
        check(case+": median/range and success rate reproduced",stats==summary["cases"][case]["SA"])
        stats["evaluation_attempts_each_seed"]={str(r["slot"]["seed"]):r.get("counts",{}).get("evaluation_attempts") for r in sa}
        stats["seeds_reaching_HEFT_upper"]=[r["slot"]["seed"] for r in successful if r["time_to_reference_upper_s"].get("HEFT") is not None]
        stats["seeds_reaching_ON_upper"]=[r["slot"]["seed"] for r in successful if r["time_to_reference_upper_s"].get("ON") is not None]
        by_case[case]={"SA":stats,"deterministic_references":{arm:{"energy_interval_J":r["energy_interval_J"],"elapsed_s":r["method_elapsed_s"],"counts":r["counts"]} for arm,r in refs.items()}}

output={"started_utc":started,"ended_utc":datetime.now(timezone.utc).isoformat(),"wall_s":time.monotonic()-clock,
    "passed":all(c["passed"] for c in checks),"assertion_count":len(checks),"checks":checks,
    "nature":"Read-only source/archive hashing, journal recounting, exact schedule/complete-receipt checks and Fraction statistics; no new integrations/search",
    "source_identities":len(plan["source_sha256"]),"protected_archives":len(plan["protected_archive_sha256"]),
    "real_thermal_integrations":0,"real_search_calls":0,"post_same_evaluator_not_independent_implementation":True,
    "batch":batch,"initialization_comparison":initial_comparison,"cases":by_case,"rows":records}
save(OUT/"audit.json",output)
fields=["case","arm","seed","state","success","energy_lower_J","energy_upper_J","method_elapsed_s","method_process_wall_s","post_elapsed_s","first_SAFE_at_s","first_strict_improvement_at_s","first_own_final_quality_at_s","time_to_HEFT_upper_s","time_to_ON_upper_s","evaluation_attempts","returned_receipts","validated_SAFE_receipts","cache_hits","physical_mapping_evaluations"]
with (OUT/"metrics.csv").open("x",newline="") as stream:
    writer=csv.DictWriter(stream,fieldnames=fields,lineterminator="\n");writer.writeheader()
    for row in records:
        record={k:row.get(k) for k in fields if k in row}
        record.update(case=row["slot"]["case"],arm=row["slot"]["arm"],seed=row["slot"]["seed"])
        if row.get("energy_interval_J_float"):record.update(energy_lower_J=row["energy_interval_J_float"][0],energy_upper_J=row["energy_interval_J_float"][1])
        for key in ("evaluation_attempts","returned_receipts","validated_SAFE_receipts","cache_hits"):record[key]=row.get("counts",{}).get(key)
        record.update(time_to_HEFT_upper_s=row.get("time_to_reference_upper_s",{}).get("HEFT"),time_to_ON_upper_s=row.get("time_to_reference_upper_s",{}).get("ON"))
        writer.writerow(record)
print({"passed":output["passed"],"assertions":len(checks),"wall_s":output["wall_s"],"cases":by_case},flush=True)
