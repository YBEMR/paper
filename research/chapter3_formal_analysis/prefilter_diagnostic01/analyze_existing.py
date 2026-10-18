"""P1 archive-only accounting of existing SAFE schedules (no thermal evaluation).

Reads the frozen merged CSV and selected original result/input archives. Imports
only the common legality/power-state reconstruction, never a solver or thermal
evaluator. Outputs are explanatory tables and must not be method inputs.
"""
from __future__ import annotations

import csv
import hashlib
import json
import statistics
import sys
from collections import defaultdict
from fractions import Fraction as F
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = HERE.parent / "results02"
sys.path.insert(0, str(ROOT / "research" / "chapter3_experiments"))
from schedules import validate_schedule  # No thermal integration or search.


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(name, rows):
    with (HERE / name).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def dec(value):
    return format(float(value), ".12g")


def midpoint(bounds):
    return (F(bounds[0]) + F(bounds[1])) / 2


def main():
    calls_path = OLD / "calls.csv"
    parts_path = OLD / "energy_components.csv"
    calls = read_csv(calls_path)
    parts = {row["call_id"]: row for row in read_csv(parts_path)}
    by_problem = defaultdict(list)
    for row in calls:
        if row["safe"] == "True" and row["method"] in {"milp", "heft", "sa"}:
            by_problem[row["problem_id"]].append(row)
    assert len(by_problem) == 15
    chosen, representative = [], {}
    for problem, rows in sorted(by_problem.items()):
        for method in ("milp", "heft"):
            matches = [r for r in rows if r["method"] == method]
            assert len(matches) == 1
            chosen.append(matches[0])
        sa = [r for r in rows if r["method"] == "sa"]
        med = statistics.median(F(r["U_J"]) for r in sa)
        pick = min(sa, key=lambda r: (abs(F(r["U_J"]) - med), int(r["seed"])))
        chosen.append(pick)
        representative[problem] = {
            "seed": int(pick["seed"]), "successful_seeds": len(sa),
            "median_U_J": str(med), "representative_U_J": pick["U_J"],
            "rule": "nearest successful-seed median U; ties use smaller seed; not best-seed selection",
        }

    energy_rows, domain_rows, trajectory_rows, stage_rows = [], [], [], []
    exact = {}
    sources = {str(p.relative_to(ROOT)): sha(p) for p in (
        calls_path, parts_path, ROOT / "research/chapter3_experiments/schedules.py",
        ROOT / "research/chapter3_experiments/start_domain.py", Path(__file__))}
    for call in chosen:
        cid, problem, method = call["call_id"], call["problem_id"], call["method"]
        folder = Path(call["source_batch"]) / cid
        result_path, input_path = folder / "result.json", folder / "input_instance.json"
        result, instance = read_json(result_path), read_json(input_path)
        assert result["state"] == "SAFE"
        assert F(result["safe_upper_bound_J"]) == F(call["U_J"])
        canonical_input_sha = hashlib.sha256(json.dumps(instance, sort_keys=True,
            separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        assert canonical_input_sha == call["input_sha256"]
        sources[str(result_path.relative_to(ROOT))] = sha(result_path)
        sources[str(input_path.relative_to(ROOT))] = sha(input_path)
        legal = validate_schedule(instance, result["safe_candidate"])
        assert legal["state"] == "SCHEDULE_VALID_THERMAL_UNCHECKED", cid
        assert legal["scenes"] == result["evaluation"]["legality"]["scenes"], cid
        if method == "milp":
            assert call["strict_MILP_seed_improvement_from_receipts"] == "False"
            assert F(call["initial_U_J"]) == F(call["U_J"])
        old = parts[cid]
        assert old["available"] == "True"
        bounds = json.loads(old["weighted_components_J"])
        comp = {k: midpoint(v) for k, v in bounds.items()}
        split = json.loads(old["weighted_constant_terms_by_period_J"])
        assert abs(sum(comp.values(), F(0)) - F(call["U_J"])) < F("1e-20")
        rebuilt_baseline = rebuilt_activity = F(0)
        tail_base_by_domain = F(0)
        for scene in instance["scenarios"]:
            sid, weight = scene["id"], F(scene["weight"])
            data, window = legal["scenes"][sid], F(instance["window_ms"])
            all_end = max(F(r["end_ms"]) for r in data["rows"])
            for stage in data["rows"]:
                predecessors = [left for left, right in scene["dependencies"] if right == stage["stage_id"]]
                predecessor_end = max((F(r["end_ms"]) for r in data["rows"]
                                       if r["stage_id"] in predecessors), default=F(stage["release_ms"]))
                if problem == "base__R1":
                    stage_rows.append({"call_id": cid, "method": method, "seed": call["seed"],
                        "scene_id": sid, "stage_id": stage["stage_id"],
                        "shared_stage_id": stage["shared_stage_id"], "unit": stage["unit"],
                        "domain": stage["domain_id"], "opp": stage["opp"],
                        "start_ms": stage["start_ms"], "end_ms": stage["end_ms"],
                        "wait_after_predecessor_or_release_ms": str(F(stage["start_ms"]) - predecessor_end),
                        "shared_unit_consistency": "verified_by_common_legality"})
            for segment in data["segments"]:
                dt = F(segment["duration_ms"]) / 1000
                rebuilt_baseline += weight * dt * sum(map(F, segment["baseline_by_power_group_W"].values()))
                rebuilt_activity += weight * dt * sum(map(F, segment["activity_by_node_W"].values()))
            for domain, spec in instance["platform"]["domains"].items():
                rows = [r for r in data["rows"] if r["domain_id"] == domain]
                busy = []
                for row in rows:
                    start, end = F(row["start_ms"]), F(row["end_ms"])
                    if busy and (start < busy[-1][1] or
                                 (start == busy[-1][1] and row["opp"] == busy[-1][2])):
                        assert row["opp"] == busy[-1][2]
                        busy[-1][1] = max(end, busy[-1][1])
                    else:
                        busy.append([start, end, row["opp"]])
                # Same-OPP, touching occupancy intervals are merged. A legal
                # switch at a touching boundary starts a different busy run.
                last_start, last_end, last_opp = busy[-1] if busy else (None, F(0), None)
                last_dispatch = max((F(r["start_ms"]) for r in rows), default=None)
                entry_opp = scene["entry"]["domain_opp"][domain]
                final_opp = data["segments"][-1]["domain_opps"][domain]
                assert last_opp is None or last_opp == final_opp
                runs = []
                for seg in data["segments"]:
                    start, end, opp = F(seg["start_ms"]), F(seg["end_ms"]), seg["domain_opps"][domain]
                    if runs and runs[-1][2] == opp:
                        runs[-1][1] = end
                    else:
                        runs.append([start, end, opp])
                for index, (start, end, opp) in enumerate(runs):
                    trajectory_rows.append({"call_id": cid, "problem_id": problem, "method": method,
                        "seed": call["seed"], "scene_id": sid, "domain": domain,
                        "entry_opp": entry_opp, "run_index": index, "opp": opp,
                        "start_ms": str(start), "end_ms": str(end),
                        "baseline_W": spec["baseline_W"][opp],
                        "weight": str(weight), "weighted_baseline_J": str(
                            weight * F(spec["baseline_W"][opp]) * (end - start) / 1000)})
                full_base = sum((F(spec["baseline_W"][opp]) * (end-start) / 1000
                                 for start, end, opp in runs), F(0))
                tail_base = F(spec["baseline_W"][final_opp]) * (window-last_end) / 1000
                tail_base_by_domain += weight * tail_base
                domain_rows.append({"call_id": cid, "problem_id": problem, "method": method,
                    "seed": call["seed"], "scene_id": sid, "scene_weight": str(weight),
                    "domain": domain, "entry_opp": entry_opp,
                    "opp_runs": ";".join(f"{opp}@{start}-{end}" for start, end, opp in runs),
                    "last_busy_start_ms": "" if last_start is None else str(last_start),
                    "last_busy_end_ms": "" if not busy else str(last_end),
                    "last_busy_opp": last_opp or "NO_WORK", "final_held_opp": final_opp,
                    "last_stage_dispatch_ms": "" if last_dispatch is None else str(last_dispatch),
                    "last_dispatched_stage_ids": ";".join(r["stage_id"] for r in rows
                        if F(r["start_ms"]) == last_dispatch),
                    "domain_idle_tail_ms": str(window-last_end),
                    "scene_last_stage_end_ms": str(all_end), "scene_idle_tail_ms": str(window-all_end),
                    "domain_full_baseline_J": str(full_base),
                    "domain_idle_tail_baseline_J": str(tail_base),
                    "idle_tail_temperature_correction_J": "UNAVAILABLE"})
        assert F(bounds["baseline"][0]) <= rebuilt_baseline <= F(bounds["baseline"][1])
        assert F(bounds["activity"][0]) <= rebuilt_activity <= F(bounds["activity"][1])
        row = {"call_id": cid, "problem_id": problem, "method": method, "seed": call["seed"],
            "U_J": dec(F(call["U_J"])), **{f"{k}_J": dec(v) for k, v in comp.items()},
            "global_execution_baseline_J": dec(F(split["execution"]["baseline"])),
            "global_idle_tail_baseline_J": dec(F(split["tail"]["baseline"])),
            "sum_domain_idle_tail_baseline_J": dec(tail_base_by_domain),
            "temperature_correction_split": "UNAVAILABLE_whole_window_integrals_only",
            "SA_successful_seed_median_U_J": dec(F(representative[problem]["median_U_J"])) if method == "sa" else "",
            "source_result": str(result_path.relative_to(ROOT)),
            "source_energy_csv_call_id": cid}
        energy_rows.append(row)
        exact[(problem, method)] = {"U": F(call["U_J"]), **comp,
            "global_tail_baseline": F(split["tail"]["baseline"]),
            "global_execution_baseline": F(split["execution"]["baseline"]),
            "sum_domain_tail_baseline": tail_base_by_domain}
        del result

    paired = []
    for problem in sorted(by_problem):
        seed = exact[(problem, "milp")]
        for method in ("heft", "sa"):
            other = exact[(problem, method)]
            diff = {k: seed[k] - other[k] for k in seed}
            paired.append({"problem_id": problem, "comparison": "MILP_seed_minus_" + method,
                "other_seed": representative[problem]["seed"] if method == "sa" else "",
                **{f"difference_{k}_J": dec(v) for k, v in diff.items()},
                "baseline_difference_over_total_difference": dec(diff["baseline"]/diff["U"]),
                "scope": "paired_saved_schedules; arithmetic_component_differences_not_causal_effects"})
    write_csv("existing_energy_components.csv", energy_rows)
    write_csv("existing_paired_differences.csv", paired)
    write_csv("existing_domain_tails.csv", domain_rows)
    write_csv("existing_domain_opp_runs.csv", trajectory_rows)
    write_csv("base_R1_stages.csv", stage_rows)
    audit = {"scope": "existing archives only; no thermal propagation, new solve, candidate generation or method injection",
        "selected_calls": len(chosen), "problems": len(by_problem),
        "common_legality_and_saved_power_tables_equal": len(chosen),
        "constant_component_checks_passed": len(chosen),
        "sa_representatives": representative, "source_sha256": sources,
        "output_use": "post-hoc explanation only; forbidden as method candidates/x0/cache/U"}
    (HERE / "existing_analysis_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = ["# P1：原15题的已有方案能耗与尾段解释", "",
        "本次只读取K.104—105档案：MILP全部仍为原种子，HEFT为已有最终SAFE；SA取正式成功种子中最接近中位能量的一条，并列取较小seed。它是展示代表，不是最佳种子或新统计。45份原candidate仅重建共同合法性／功率时间表，与原回执逐项相同；没有热轨迹积分、求解或新方法调用，也不向后续调用提供候选、x0、缓存或U。", "",
        "**结论：15/15题中，MILP种子的全窗基准项、活动项和温度修正项均高于HEFT及SA代表；公共项始终0.12 J、差为0。差异说明已有方案整体不同，不能解释成单一尾段OPP的因果收益。**", "",
        "| base R1，J | MILP种子 | HEFT | SA代表seed%d |" % representative["base__R1"]["seed"],
        "|---|---:|---:|---:|"]
    for key, label in (("U", "完整能量U"), ("baseline", "全窗基准"), ("activity", "活动"),
                       ("temperature_correction", "温度修正"), ("external_common", "公共"),
                       ("global_execution_baseline", "执行区间基准"), ("global_tail_baseline", "全域空闲尾段基准")):
        lines.append("| %s | %s |" % (label, " | ".join(f"{float(exact[('base__R1', m)][key]):.6f}" for m in ("milp", "heft", "sa"))))
    lines.extend(["", "执行区间按各场景[0,最后Stage结束)，全域空闲尾段按[最后Stage结束,400 ms]。只能拆分常数基准／活动／公共项；回执没有分段温度积分，执行／尾段的温度修正及完整总能量均不足以判断，不从采样补积分。", "",
        "| base R1场景／方法 | CPU末忙段→尾段 | GPU末忙段→尾段 | NPU末忙段→尾段 |", "|---|---|---|---|"])
    for sid in ["AB_offset_0ms", "AC_offset_0ms"]:
        for method in ("milp", "heft", "sa"):
            lookup = {r["domain"]: r for r in domain_rows if r["problem_id"] == "base__R1" and r["scene_id"] == sid and r["method"] == method}
            cells = []
            for domain in ("CPU", "GPU", "NPU"):
                r = lookup[domain]
                if r["last_busy_opp"] == "NO_WORK":
                    cells.append(f"无忙段；{r['final_held_opp']}保持400 ms")
                else:
                    cells.append(f"{r['last_busy_opp']} {dec(F(r['last_busy_start_ms']))}–{dec(F(r['last_busy_end_ms']))}；尾{dec(F(r['domain_idle_tail_ms']))} ms")
            lines.append(f"| {sid[:2]}/{method} | " + " | ".join(cells) + " |")
    lines.extend(["", "所有入口OPP均L；CPU1／CPU2共用CPU域。末忙段将相接且同OPP的占用合并；尾段从该域最后Stage结束起算。逐次轨迹及最后派发事件见`existing_domain_opp_runs.csv`／`existing_domain_tails.csv`，base R1具体单元／起止／依赖后等待见`base_R1_stages.csv`。无工作域仍保留入口OPP并计量。", ""])
    for method, label in (("heft", "HEFT"), ("sa", "SA代表")):
        ps = [r for r in paired if r["comparison"] == "MILP_seed_minus_" + method]
        ratios = [float(r["baseline_difference_over_total_difference"]) for r in ps]
        assert all(exact[(p, "milp")][k] > exact[(p, method)][k]
                   for p in by_problem for k in ("baseline", "activity", "temperature_correction"))
        p0 = next(r for r in ps if r["problem_id"] == "base__R1")
        lines.append(f"对{label}：15题基准项差／总差的数值占比为{min(ratios)*100:.1f}%–{max(ratios)*100:.1f}%；base R1为{float(p0['baseline_difference_over_total_difference'])*100:.1f}%。base R1总差{float(p0['difference_U_J']):.6f} J，其中全域空闲尾段基准差{float(p0['difference_global_tail_baseline_J']):.6f} J、执行区间基准差{float(p0['difference_global_execution_baseline_J']):.6f} J；两者相加才是全窗基准差。")
    lines.extend(["", f"base R1仅4/5个正式SA种子成功，中位U为{float(F(representative['base__R1']['median_U_J'])):.6f} J；展示seed{representative['base__R1']['seed']}的U不同于中位数。其余14题均5/5。本页不改变原排名、失败状态或统一300 s预算口径。", "",
        "边界：完成较早与全窗能耗较低并非同义；部署、OPP、时序和温度轨迹同时变化，尚未用合法反事实隔离各因素。原15题只能支持本批事后分项解释，不支持尾段单因素节能率、全方向判断或新方法选择。详细数值及源文件SHA256见本目录CSV和`existing_analysis_audit.json`；至此结束P1，不延伸研究方向。", ""])
    (HERE / "summary_existing.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"selected_calls": len(chosen), "domain_rows": len(domain_rows),
        "opp_runs": len(trajectory_rows), "base_R1_stage_rows": len(stage_rows),
        "all_checks_passed": True, "output_directory": str(HERE)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
