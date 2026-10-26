"""Read-only E4 deadline-fallback pair accounting; standard-library arithmetic only.

This script never imports a planner, schedule validator, solver or thermal
kernel. It consumes archived receipts after the authorized research batch.
"""
from collections import Counter
import csv
import hashlib
import json
from fractions import Fraction as F
from pathlib import Path

HERE=Path(__file__).resolve().parent
RUN=HERE/"results/e4_df_01"
EVIDENCE=HERE/"evidence/e4_deadline_fallback_precheck02"
COMPONENTS=("baseline","activity","external_common","temperature_correction")


def read(path):return json.loads(Path(path).read_bytes())
def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                                    ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def save(path,value):
    Path(path).write_bytes((json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode())
def interval(values):
    assert isinstance(values,list) and len(values)==2,"invalid saved interval"
    lo,hi=map(F,values)
    assert 0<=lo<=hi,"invalid saved energy bounds"
    return lo,hi

def write_csv(path,fields,rows):
    with Path(path).open("w",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,fields,extrasaction="ignore",lineterminator="\n")
        writer.writeheader();writer.writerows(rows)


def weighted_components(receipt,instance):
    out={key:[F(0),F(0)] for key in COMPONENTS}
    for scene in instance["scenarios"]:
        weight=F(scene["weight"])
        for key in COMPONENTS:
            lo,hi=interval(receipt["scenes"][scene["id"]]["energy_components_J"][key])
            out[key][0]+=weight*lo;out[key][1]+=weight*hi
    return {key:list(map(str,value)) for key,value in out.items()}


def audit_phase(folder,phase,ordinal,method,manifest,auth,ledger_root,ledger_batch):
    """Bind saved results to once-only records and every actual source copy."""
    accepted_path=folder/"accepted_result.json"
    if not accepted_path.exists():
        claim_path=ledger_root/f"{ordinal:02d}_{phase.lower()}_claim.json"
        state="CLAIMED_NO_ACCEPTED_RESULT" if claim_path.exists() else "NOT_RUN"
        return None,dict(state=state,verified_source_copies=0)
    accepted=read(accepted_path);result=accepted["result"]
    stem=f"{ordinal:02d}_{phase.lower()}"
    claim=read(ledger_root/(stem+"_claim.json"));finish=read(ledger_root/(stem+"_finish.json"))
    bare={k:v for k,v in claim.items() if k!="claim_sha256"}
    assert claim["claim_sha256"]==digest(bare),"claim self identity"
    assert claim["authorization_sha256"]==digest(auth) and claim["batch_sha256"]==digest(ledger_batch)
    assert claim["phase"]==phase and claim["ordinal"]==ordinal and claim["source_sha"]==manifest["source_sha"]
    assert claim["context_sha256"]==digest(claim["job_context"])
    assert claim["job_context"]["method_policy"]==method,"claim method policy"
    assert claim["run_dir"]==str(RUN.resolve())
    assert finish["claim_sha256"]==claim["claim_sha256"] and finish["result_sha256"]==digest(result)
    record=dict(state=result["state"],claim_sha256=claim["claim_sha256"],result_sha256=digest(result),
                ledger_claim=stem+"_claim.json",ledger_finish=stem+"_finish.json",verified_source_copies=0)
    job_path=folder/"job.json";launch_path=ledger_root/(stem+"_launch.json")
    if job_path.exists():
        job=read(job_path)
        assert job["claim"]==claim and job["method_policy"]==method and job["scope_sha256"]==digest(manifest)
        assert job["authorization"]==auth and job["phase"]==phase and job["ordinal"]==ordinal
        assert job["limit_s"]==manifest["budgets"][phase.lower()+"_s"]
        assert job["root_origin"]==claim["root_origin"] and job["run_dir"]==str(RUN.resolve())
        packet=job["packet"];problem,objective=manifest["slots"][ordinal-1]
        assert packet["instance"]["id"]==problem and packet["objective"]==objective=="FULL"
        expected=manifest["inputs"][problem]
        assert digest(packet["instance"])==expected["input_sha256"]
        assert digest(packet["config"])==expected["config_sha256"]
        assert digest(packet)==expected["packet_sha256"][objective]
        runtime_manifest=folder/"bundle/runtime_manifest.json"
        if runtime_manifest.exists():
            assert read(runtime_manifest)==manifest,"runtime/frozen manifest drift"
            for relative,expected_hash in manifest["files"].items():
                source=folder/"bundle"/Path(relative)
                assert source.is_file() and hashlib.sha256(source.read_bytes()).hexdigest()==expected_hash,relative
                record["verified_source_copies"]+=1
        if launch_path.exists():
            launch=read(launch_path)
            assert launch["claim_sha256"]==claim["claim_sha256"] and launch["job_sha256"]==digest(job)
            assert launch["limit_s"]==job["limit_s"] and launch["root_origin"]==job["root_origin"]
            assert launch["worker_dir"]==str(folder.resolve())
            assert record["verified_source_copies"]==len(manifest["files"]),"launched bundle incomplete"
            record["launched"]=True
    else:
        assert not launch_path.exists(),"launch without job"
    return accepted,record


def main():
    manifest=read(EVIDENCE/"frozen_real_manifest.json");auth=read(HERE/"authorizations/e4_df_01.json")
    batch=read(RUN/"batch_summary.json")
    assert manifest["protocol_id"]=="E4_DEADLINE_FALLBACK_V1" and len(manifest["slots"])==2
    assert manifest["methods"]==["ORIGINAL_HEFT","DEADLINE_FALLBACK"]
    assert all(tuple(slot)==("requests_2__R1","FULL") for slot in manifest["slots"])
    assert auth["authorized"] is True and auth["scope_sha256"]==digest(manifest)
    assert auth["source_sha"]==manifest["source_sha"] and auth["methods"]==manifest["methods"]
    assert batch["authorization_id"]==auth["authorization_id"] and batch["retries"]==0
    ledger_root=Path(auth["authority_store"])/digest({"authorization_id":auth["authorization_id"]})
    ledger_batch=read(ledger_root/"batch.json")
    assert ledger_batch["authorization_sha256"]==digest(auth) and ledger_batch["scope_sha256"]==digest(manifest)
    assert ledger_batch["run_dir"]==str(RUN.resolve()) and ledger_batch["source_sha"]==manifest["source_sha"]
    assert ledger_batch["context_sha256"]==digest(ledger_batch["context"])
    slots=[];all_stages=[];request_rows=[];domain_segments=[];phase_audits=[];packet_hashes=[]
    for ordinal,((problem,objective),method) in enumerate(zip(manifest["slots"],manifest["methods"]),1):
        packet=read(EVIDENCE/(problem+".json"));instance=packet["instance"]
        assert packet["objective"]==objective and digest(instance)==manifest["inputs"][problem]["input_sha256"]
        assert digest(packet["config"])==manifest["inputs"][problem]["config_sha256"]
        assert digest(packet)==manifest["inputs"][problem]["packet_sha256"][objective]
        packet_hashes.append(digest(packet))
        count=sum((F(s["weight"])*len(s["requests"]) for s in instance["scenarios"]),F(0))
        assert count==4 and instance["settings"]["requests_per_application"]==2
        item=dict(ordinal=ordinal,method_policy=method,problem_id=problem,objective=objective,state="NOT_RUN",
            weighted_requests_per_window=str(count),plan_safe_witness_available=False,post_safe_witness_available=False,
            plan_U_approx_J=None,post_U_approx_J=None,per_request_U_approx_J=None,
            no_global_optimality_proof=True)
        folder=RUN/f"slot_{ordinal}"
        accepted,audit=audit_phase(folder/"plan","PLAN",ordinal,method,manifest,auth,ledger_root,ledger_batch)
        phase_audits.append(dict(ordinal=ordinal,method_policy=method,phase="PLAN",**audit))
        if accepted is None:slots.append(item);continue
        plan=accepted["result"];process=accepted.get("process") or {};archive=plan.get("archive",{})
        search=plan.get("search")
        item.update(state=plan["state"],reason=plan.get("reason"),stop_required=plan.get("stop_required"),
            plan_method_s=plan.get("timing",{}).get("method_elapsed_s"),plan_process_s=process.get("method_elapsed_s"),
            startup_s=process.get("startup_elapsed_s"),plan_process_classification=process.get("classification"),
            plan_reaped=process.get("reaped"),first_candidate_s=archive.get("first_candidate_at_s"),
            first_legal_s=archive.get("first_legal_at_s"),first_safe_s=archive.get("first_safe_at_s"),
            selected_at_s=plan.get("selected_at_s"),selected_source=plan.get("selected_source"),
            candidate_attempts=archive.get("candidates"),unique_evaluations=len(archive.get("evaluations",[])),
            cache_hits=archive.get("cache_hits"),score_improvements=len(archive.get("events",[])),
            candidate_states=dict(Counter(r["evaluation"]["state"] for r in archive.get("evaluations",[]))),
            search_metadata=search,coverage_complete=plan.get("coverage_complete",False),
            independently_proven_optimal=plan.get("independently_proven_optimal",False))
        if search is not None:
            constructions=search.get("construction_attempts",[])
            initial=constructions[:4]
            item.update(construction_attempt_count=len(constructions),
                original_complete_legal_candidate_count=sum(c.get("status")=="COMPLETE_LEGAL_CANDIDATE" for c in initial),
                constructor_failure_counts=dict(Counter(c.get("reason") for c in constructions if c.get("reason"))),
                fallback_metadata=search.get("deadline_fallback"),
                local_attempt_count=len(search.get("local_attempts",[])),local_accepted=search.get("local_accepted"))
        receipt_for_schedule=None;evidence_phase=None
        if plan["state"]=="SAFE":
            assert plan.get("method_policy")==method
            candidate=plan["safe_candidate"];key=digest(candidate)
            assert key==plan["selected_candidate_sha256"]
            evaluation=plan["evaluation"]
            assert evaluation["evidence_identity"]==dict(input_sha256=digest(instance),candidate_sha256=key)
            a,b=interval(evaluation["weighted_energy_J"])
            assert F(plan["safe_upper_bound_J"])==b
            item.update(plan_safe_witness_available=True,candidate_sha256=key,
                planning_score_J=plan["planning_score_J"],plan_true_energy_J=evaluation["weighted_energy_J"],
                plan_U_approx_J=float(b),plan_per_request_energy_J=[str(a/count),str(b/count)],
                plan_weighted_components_J=weighted_components(evaluation,instance))
            receipt_for_schedule=evaluation;evidence_phase="PLAN"
        post,paudit=audit_phase(folder/"post","POST",ordinal,method,manifest,auth,ledger_root,ledger_batch)
        phase_audits.append(dict(ordinal=ordinal,method_policy=method,phase="POST",**paudit))
        if post is not None:
            final=post["result"];p=post.get("process") or {}
            item.update(post_state=final["state"],post_reason=final.get("reason"),post_stop_required=final.get("stop_required"),
                post_method_s=final.get("timing",{}).get("method_elapsed_s"),post_process_s=p.get("method_elapsed_s"),
                post_process_classification=p.get("classification"),post_reaped=p.get("reaped"))
            if final["state"]=="POST_SAFE":
                assert plan["state"]=="SAFE" and final["candidate_sha256"]==item["candidate_sha256"]
                evaluation=final["evaluation"]
                assert evaluation["evidence_identity"]==dict(input_sha256=digest(instance),candidate_sha256=item["candidate_sha256"])
                a,b=interval(plan["evaluation"]["weighted_energy_J"]);lo,hi=interval(evaluation["weighted_energy_J"])
                assert max(a,lo)<=min(b,hi),"plan/post disjoint energy receipts"
                item.update(state="POST_SAFE",post_safe_witness_available=True,post_true_energy_J=evaluation["weighted_energy_J"],
                    post_U_J=str(hi),post_U_approx_J=float(hi),per_request_energy_J=[str(lo/count),str(hi/count)],
                    per_request_U_approx_J=float(hi/count),weighted_components_J=weighted_components(evaluation,instance),
                    peak_temperature_upper_degC=str(max(F(v[1]) for s in evaluation["scenes"].values() for v in s["peaks_degC"].values())))
                receipt_for_schedule=evaluation;evidence_phase="POST"
        if receipt_for_schedule is not None:
            legality=receipt_for_schedule["legality"];units={u["id"]:u for u in instance["platform"]["units"]}
            assert legality["problem_id"]==problem
            mapping={}
            candidate_by_scene={sid:{r["stage_id"]:r for r in rows} for sid,rows in plan["safe_candidate"]["scenes"].items()}
            for sid,scene in legality["scenes"].items():
                assert len(scene["rows"])==len(candidate_by_scene[sid])
                for row in scene["rows"]:
                    original=candidate_by_scene[sid][row["stage_id"]]
                    assert all(row[k]==original[k] for k in ("unit","opp","start_ms"))
                    assert F(row["end_ms"])==F(row["start_ms"])+F(row["duration_ms"])
                    mapping[row["shared_stage_id"]]=row["unit"]
                    all_stages.append(dict(ordinal=ordinal,method_policy=method,evidence_phase=evidence_phase,
                        problem_id=problem,scene_id=sid,stage_id=row["stage_id"],shared_stage_id=row["shared_stage_id"],
                        device_class=units[row["unit"]]["device_class"],
                        **{k:row[k] for k in ("unit","opp","start_ms","duration_ms","end_ms")}))
                domain_segments.extend(dict(ordinal=ordinal,method_policy=method,evidence_phase=evidence_phase,
                    problem_id=problem,scene_id=sid,**segment) for segment in scene["segments"])
            for scene in instance["scenarios"]:
                saved=legality["scenes"][scene["id"]]
                for req in scene["requests"]:
                    completion=saved["request_completion_ms"][req["id"]]
                    assert F(completion)==max(F(r["end_ms"]) for r in saved["rows"] if r["request_id"]==req["id"])
                    slack=F(req["deadline_ms"])-F(completion);assert slack>=0
                    request_rows.append(dict(ordinal=ordinal,method_policy=method,evidence_phase=evidence_phase,
                        problem_id=problem,scene_id=scene["id"],request_id=req["id"],application=req["application"],
                        copy_index=req["copy_index"],release_ms=req["release_ms"],deadline_ms=req["deadline_ms"],
                        completion_ms=completion,slack_ms=str(slack)))
            item["shared_mapping"]=mapping
            item["min_deadline_slack_ms"]=str(min(F(r["slack_ms"]) for r in request_rows if r["ordinal"]==ordinal))
            item["stage_OPP_counts_by_execution"]=dict(Counter(r["opp"] for r in all_stages if r["ordinal"]==ordinal))
            item["stage_device_counts_by_execution"]=dict(Counter(r["device_class"] for r in all_stages if r["ordinal"]==ordinal))
        slots.append(item)
    assert len(set(packet_hashes))==1,"the two method inputs are not identical"
    comparison=dict(state="NOT_COMPARABLE_NO_TWO_POST_SAFE",energy_delta_original_minus_fallback_J=None,
        energy_reduction_percent=None,energy_reduction_percent_approx=None,
        original_final_safe=slots[0]["post_safe_witness_available"],fallback_final_safe=slots[1]["post_safe_witness_available"],
        conclusion="NO_PAIRED_FINAL_ENERGY_COMPARISON")
    if all(s["post_safe_witness_available"] for s in slots):
        a0,a1=interval(slots[0]["post_true_energy_J"]);b0,b1=interval(slots[1]["post_true_energy_J"])
        assert a0>0
        delta=(a0-b1,a1-b0);ratios=[v/u*100 for v in delta for u in (a0,a1)]
        comparison.update(state="TWO_POST_SAFE_COMPARABLE",energy_delta_original_minus_fallback_J=list(map(str,delta)),
            energy_reduction_percent=list(map(str,(min(ratios),max(ratios)))),
            energy_reduction_percent_approx=float(sum(delta)/(a0+a1)*100),
            conclusion="FALLBACK_STRICTLY_LOWER" if b1<a0 else ("ORIGINAL_STRICTLY_LOWER" if a1<b0 else "NUMERICALLY_UNRESOLVED"))
    elif slots[1]["post_safe_witness_available"] and not slots[0]["plan_safe_witness_available"]:
        comparison["conclusion"]="FALLBACK_FINAL_SAFE_WITNESS_FOUND_ORIGINAL_NO_SAFE_WITNESS_IN_BUDGET"
    claims=list(ledger_root.glob("*_claim.json"));launches=list(ledger_root.glob("*_launch.json"))
    for claim in map(read,claims):
        assert claim["phase"] in ("PLAN","POST") and 1<=claim["ordinal"]<=len(manifest["slots"])
    plan_calls=sum(read(p)["phase"]=="PLAN" for p in claims)
    post_calls=sum(read(p)["phase"]=="POST" for p in claims)
    assert plan_calls<=manifest["budgets"]["plan_calls"] and post_calls<=manifest["budgets"]["post_calls"]
    summary=dict(material_passport=dict(type="code_experiment_result",mode="run",status="READ_ONLY_SAVED_RESULT_ACCOUNTING",
        scope="same requests_2 R1 true-H auto-L physical problem; original adapted HEFT versus one empty-construction deadline-ready fallback"),
        authorization_id=auth["authorization_id"],source_sha=manifest["source_sha"],manifest_sha256=digest(manifest),
        planned_plan_calls=manifest["budgets"]["plan_calls"],planned_max_post_calls=manifest["budgets"]["post_calls"],
        consumed_plan_calls=plan_calls,consumed_post_calls=post_calls,
        launched_plan_calls=sum("plan_launch" in p.name for p in launches),
        launched_post_calls=sum("post_launch" in p.name for p in launches),
        real_backend_entries=len(list(RUN.rglob("real_backend_entry.json"))),ledger_json_files=len(list(ledger_root.glob("*.json"))),
        files_per_runtime_bundle=len(manifest["files"]),verified_source_copies=sum(p["verified_source_copies"] for p in phase_audits),
        retries=batch["retries"],batch_wall_s=batch["wall_s"],plan_SAFE_slots=sum(s["plan_safe_witness_available"] for s in slots),
        final_POST_SAFE_slots=sum(s["post_safe_witness_available"] for s in slots),
        sum_plan_process_s=sum(s.get("plan_process_s") or 0 for s in slots),
        sum_post_process_s=sum(s.get("post_process_s") or 0 for s in slots),
        slots=slots,phase_identity_audits=phase_audits,method_comparison=comparison,
        interpretation="single-run finite heuristic results; no exact infeasibility/optimality, thermal-feedback benefit or hardware measurement claim")
    save(RUN/"readonly_analysis.json",summary);save(RUN/"domain_segments.json",domain_segments)
    write_csv(RUN/"summary.csv",["ordinal","method_policy","problem_id","objective","state","reason","post_state","post_reason",
        "weighted_requests_per_window","plan_safe_witness_available","post_safe_witness_available","plan_U_approx_J","post_U_approx_J",
        "per_request_U_approx_J","min_deadline_slack_ms","plan_process_s","post_process_s","startup_s","first_candidate_s","first_legal_s",
        "first_safe_s","selected_at_s","candidate_attempts","unique_evaluations","cache_hits","construction_attempt_count",
        "original_complete_legal_candidate_count","local_attempt_count","local_accepted","peak_temperature_upper_degC"],slots)
    write_csv(RUN/"stage_schedules.csv",["ordinal","method_policy","evidence_phase","problem_id","scene_id","stage_id","shared_stage_id",
        "device_class","unit","opp","start_ms","duration_ms","end_ms"],all_stages)
    write_csv(RUN/"request_deadlines.csv",["ordinal","method_policy","evidence_phase","problem_id","scene_id","request_id","application",
        "copy_index","release_ms","deadline_ms","completion_ms","slack_ms"],request_rows)
    print(json.dumps({k:summary[k] for k in ("consumed_plan_calls","consumed_post_calls","final_POST_SAFE_slots","batch_wall_s","verified_source_copies")}))
    print(json.dumps(comparison,ensure_ascii=False))


if __name__=="__main__":main()
