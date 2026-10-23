"""Read archived H02 terminal receipts only; no scientific module imports."""
import argparse
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def run(repo, destination):
    core = repo / "research/chapter3_experiments"
    result_dir = core / "results/response_information_execution01"
    supervision = core / "results/response_information_execution01_supervision"
    declaration_path = supervision / "declaration.json"
    declaration = read(declaration_path)
    terminal, outer = read(result_dir / "terminal.json"), read(supervision / "terminal.json")
    if outer["status"] not in ("COMPLETED", "CONTROLLER_STOPPED", "CONTROLLER_NONZERO_EXIT", "CALENDAR_DEADLINE", "SUPERVISOR_TECHNICAL_FAILURE"):
        raise RuntimeError("Terminal archive required; never analyze live search")
    destination.mkdir(parents=True, exist_ok=False)
    checks = []

    def check(name, passed, evidence):
        checks.append(dict(name=name, passed=bool(passed), evidence=evidence))

    expected_order = [dict(ordinal=1, problem_id="base__R1", view="H"),
        dict(ordinal=2, problem_id="base__R1", view="R"),
        dict(ordinal=3, problem_id="base__R2", view="R"),
        dict(ordinal=4, problem_id="base__R2", view="H")]
    ledger = outer["controller_ledger"]
    source_drift = [p for p, old in declaration["expected_sha"].items() if digest(repo / p) != old]
    claims = [read(p) for p in sorted((result_dir / "ledger").glob("*.claim.json"))]
    original_declaration_path = core / "results/response_information_execution_precheck01/execution_declaration.json"
    check("declaration_identity", digest(original_declaration_path) == outer["declaration_sha256"]
        and read(original_declaration_path) == declaration,
        dict(original_byte_sha256=digest(original_declaration_path),
             archived_semantic_sha256=canonical(declaration),
             note="Supervisor canonicalizes its declaration copy; bind original bytes and exact JSON content"))
    check("frozen_order", declaration["slots"] == expected_order, declaration["slots"])
    check("budgets_120_60_720", declaration["budgets"] == dict(audit_s=60, audit_total_s=240,
        maximum_audit_calls=4, maximum_plan_calls=4, plan_s=120, plan_total_s=480,
        scientific_total_s=720), declaration["budgets"])
    check("calendar_bound", outer["calendar_elapsed_s"] < 1200 and outer["calendar_limit_s"] == 1200, outer["calendar_elapsed_s"])
    check("no_automatic_retry", terminal["no_automatic_retry"] is True and outer["automatic_retry"] is False, "Both terminal receipts")
    check("call_counts_within_limits", ledger["plan_calls_consumed"] <= 4 and ledger["audit_calls_consumed"] <= 4,
        dict(plan=ledger["plan_calls_consumed"], audit=ledger["audit_calls_consumed"]))
    check("budget_reserved_not_refunded", ledger["reserved_scientific_budget_s"] == 120 and len(claims) == 1, ledger)
    check("source_unchanged", not source_drift, source_drift)
    check("exception_stop_preserved", terminal["stopped"] and outer["status"] == "CONTROLLER_STOPPED", terminal)
    slots = []
    for slot in expected_order:
        folder = result_dir / ("slot_" + str(slot["ordinal"]))
        job_path = folder / "planner_public/job.json"
        raw_path = folder / "planner_public/method/result.json"
        if not raw_path.exists():
            slots.append(dict(slot=slot, method_started=job_path.exists(), raw_result_present=False,
                H_independent_post_started=(folder / "H_audit_private").exists(), comparative_output=False))
            continue
        raw = read(raw_path)
        checkpoint = read(folder / "planner_public/accepted_checkpoint.json")
        packet = read(job_path)["packet"]
        instance, config = packet["planner"]["instance"], packet["planner"]["config"]
        exact_external = F(instance["platform"]["external_common_power_W"]) * F(instance["window_ms"]) / 1000
        point_mismatches, all_external_contains, exact_segment_sums = [], [], []
        accepted = []
        for index, row in enumerate(raw["evaluations"]):
            if row.get("accepted_safe") is not True:
                continue
            accepted.append(row)
            receipt = row["evaluation"]
            for sid, scene in receipt["scenes"].items():
                interval = list(map(F, scene["energy_components_J"]["external_common"]))
                all_external_contains.append(interval[0] <= exact_external <= interval[1])
                segments = receipt["legality"]["scenes"][sid]["segments"]
                accounted = sum((F(v["external_common_power_W"]) * F(v["duration_ms"]) / 1000 for v in segments), F(0))
                exact_segment_sums.append(accounted == exact_external)
                if interval != [exact_external, exact_external]:
                    point_mismatches.append(dict(evaluation_index_zero_based=index,
                        candidate_number=index+1, source=row["source"], scene=sid,
                        interval=scene["energy_components_J"]["external_common"],
                        exact_expected_J=str(exact_external), contains_exact=True,
                        lower_offset_J=str(interval[0]-exact_external), upper_offset_J=str(interval[1]-exact_external),
                        interval_width_J=str(interval[1]-interval[0]),
                        exact_segment_sum_J=str(accounted), candidate_sha256=row["candidate_sha256"]))
        best = min(accepted, key=lambda row:F(row["evaluation"]["safe_upper_bound_J"]))
        stderr = (folder / "planner_public/stderr.log").read_text(encoding="utf-8")
        process = read(folder / "planner_public/process_receipt.json")
        best_match = best["candidate"] == raw["safe_candidate"] and best["evaluation"] == raw["evaluation"]
        checkpoint_match = checkpoint["best"]["candidate"] == raw["safe_candidate"] and checkpoint["best"]["evaluation"] == raw["evaluation"]
        slots.append(dict(slot=slot, method_started=True, raw_result_present=True,
            raw_method_state=raw["state"], raw_method_reason=raw["reason"],
            raw_method_elapsed_s=raw["timing"]["method_elapsed_s"],
            raw_first_safe_at_s=raw["first_safe_at_s"], raw_candidate_count=raw["candidate_count"],
            raw_thermal_evaluations=raw["thermal_evaluations"], accepted_count=len(accepted),
            raw_U_J=raw["safe_upper_bound_J"], raw_energy_J=raw["evaluation"]["weighted_energy_J"],
            candidate_sha256=canonical(raw["safe_candidate"]), candidate=raw["safe_candidate"],
            actual_planner_input_sha256=canonical(instance), actual_planner_config_sha256=canonical(config),
            best_matches_raw_final=best_match, checkpoint_matches_raw_final=checkpoint_match,
            final_scene_energy_components_J={sid:v["energy_components_J"] for sid,v in raw["evaluation"]["scenes"].items()},
            final_scene_peaks_degC={sid:v["peaks_degC"] for sid,v in raw["evaluation"]["scenes"].items()},
            final_scene_request_completion_ms={sid:v["request_completion_ms"] for sid,v in raw["evaluation"]["legality"]["scenes"].items()},
            external_point_equality_mismatches=point_mismatches,
            all_external_intervals_contain_exact=all(all_external_contains),
            exact_segment_energy_sums_correct=all(exact_segment_sums),
            H_independent_post_started=(folder / "H_audit_private").exists(),
            comparative_output=False, stderr=stderr, process_receipt=process))
        check("same_HEFT_identity", raw["method"] == "heft" and raw["seed"] is None, raw.get("search",{}).get("rule_version"))
        check("raw_core_completed_before_deadline", raw["reason"] == "DECLARED_SEARCH_COMPLETED" and raw["timing"]["limit_s"] == 120 and raw["timing"]["method_elapsed_s"] < 120, raw["timing"]["method_elapsed_s"])
        check("all_accepted_receipts_timely", all(0 <= v["evaluation"]["completed_at_elapsed_s"] < 120 for v in accepted), len(accepted))
        check("original_final_best_and_checkpoint_agree", best_match and checkpoint_match, "No repaired or substituted candidate")
        check("external_exact_segment_accounting", all(exact_segment_sums), "Exact Fraction arithmetic on archived legality segments only")
        check("outward_intervals_contain_exact_external", all(all_external_contains), "All accepted scene external intervals contain exact3/25J")
        check("single_offending_outward_interval", len(point_mismatches) == 1, point_mismatches)
        check("thin_export_failure_preserved", "EXTERNAL_POWER_ACCOUNTING" in stderr and process["returncode"] != 0, stderr)
        check("no_H_post_or_comparative_promotion", not (folder / "H_audit_private").exists() and ledger["audit_calls_consumed"] == 0, "Raw core SAFE is diagnostic evidence only")
        check("no_additional_slots_started", not any((result_dir / ("slot_"+str(k))).exists() for k in (2,3,4)), "Slots2–4 unstarted")
    facts = dict(created_utc=datetime.now(timezone.utc).isoformat(), scope="Archived receipts, source hashes and exact arithmetic only; no scientific function calls",
        terminal=terminal, supervision=outer, source_drift=source_drift, slots=slots,
        checks=checks, passed=all(v["passed"] for v in checks),
        conclusion="Thin external-energy point-equality contract rejected a legitimate outward interval. No complete H/R pair and no true-H independent post; cannot answer modeling benefit.",
        proposed_fix="Only proposed: replace exact point equality with exact segment accounting plus outward containment and existing precision criteria, retain all original core output; pure regression before any new authorization. No retry or repair is authorized by this analysis.")
    (destination / "facts.json").write_text(json.dumps(facts,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    raw = next((s for s in slots if s.get("raw_result_present")), {})
    note = f"""# H02终态只读独立核查\n\n结论：本批因薄审计接口错误停止，不能形成H/R建模收益结论。\n\n- 消费规划 {ledger['plan_calls_consumed']} 次、后验 {ledger['audit_calls_consumed']} 次；保留120秒已消费槽，后三槽未启动，不退款、不补跑。\n- 总日历 {outer['calendar_elapsed_s']:.3f} 秒；原HEFT已正常完成，根耗时 {raw.get('raw_method_elapsed_s')} 秒、44候选，保存原始SAFE与检查点；不提升为正常最终交付或真H独立复核。\n- 唯一误拒绝为evaluations[33]的AC外部公共能量：精确值0.12J，区间为0.12±10^(-60)J，宽2×10^(-60)J；完整包围精确值，原片段精确相加也等于0.12J。\n- thermal.py对每个片段计算I.rational(external*h)，再以60位向外舍入累加；一般只保证包围值，不保证区间退化为点。receipts.py要求区间恰为[0.12,0.12]，契约过强。最终best两场景外部能量均为精确点，但导出器先遍历全部accepted SAFE而触发异常。\n- {len(checks)}项只读核对 {'通过' if facts['passed'] else '存在不通过项'}，源码漂移 {len(source_drift)} 项。没有发现外部公共功率的物理重计／少计证据；这不代替重新热评价。\n\n建议仅修正薄审计契约并增加纯夹具回归；不改功热模型、HEFT、安全门或原结果。后续任何研究续接另行确认，不补本批post。H与R尚无成对结果，因此无法判断能耗收益、调度差别或模型贡献。\n"""
    (destination / "independent_review.md").write_text(note,encoding="utf-8")
    print(json.dumps(dict(output=str(destination),passed=facts["passed"],checks=len(checks),source_drift=source_drift,
        plans_consumed=ledger["plan_calls_consumed"],audits_consumed=ledger["audit_calls_consumed"]),ensure_ascii=False))


if __name__ == "__main__":
    p=argparse.ArgumentParser(); p.add_argument("--repo",type=Path,default=Path.cwd()); p.add_argument("--out",type=Path,required=True)
    args=p.parse_args(); run(args.repo.resolve(),args.out.resolve())
