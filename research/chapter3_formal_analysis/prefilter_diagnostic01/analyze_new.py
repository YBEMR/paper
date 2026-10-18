"""Controller-gated archive analysis for the six K.108 diagnostic calls.

Run only after the parent confirms the declared batch has stopped. No solver,
thermal evaluator, schedule generator or experiment module is imported.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from fractions import Fraction as F
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DEFAULT_INPUT = ROOT / "research/chapter3_experiments/results/prefilter_diagnostic01"
sys.path.insert(0, str(HERE.parent))
from analyze_formal import archived_safe_records, call_row, canonical_hash, number


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def write_csv(path, rows):
    if not rows:
        path.write_text("no_records\n", encoding="utf-8-sig")
        return
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: compact(v) if isinstance(v, (dict, list)) else v
                             for k, v in row.items()})


def display(value, digits=3):
    n = number(value)
    return "—" if n is None else f"{n:.{digits}f}"


class ArchiveReader:
    def __init__(self):
        self.sha256 = {}

    def load(self, path):
        data = path.read_bytes()
        self.sha256[str(path.relative_to(ROOT))] = hashlib.sha256(data).hexdigest()
        return json.loads(data.decode("utf-8-sig"))


def native_archive(folder, result, base, reader):
    """Retain raw native diagnostics separately, with no invented method time."""
    rows = []
    rounds = {r.get("request_number", i): r
              for i, r in enumerate(result.get("rounds") or [], 1)}
    received = {(e.get("request"), e.get("event_number")): e
                for e in (result.get("diagnostic") or {}).get("solver_progress", [])}
    for path in sorted((folder / "matlab").glob("request_*.response.json")):
        raw = reader.load(path)
        request = path.name.split(".", 1)[0]
        request_no = int(request.rsplit("_", 1)[-1])
        own_round = rounds.get(request_no, {})
        timed_return = own_round.get("budget_valid") is True
        callbacks = raw.get("callbacks") or []
        if isinstance(callbacks, dict):
            callbacks = [callbacks]
        observed = [number((r.get("values") or {}).get("numnodes")) for r in callbacks]
        observed = [v for v in observed if v is not None]
        out = raw.get("output") or {}
        opts = raw.get("options") or {}
        initial = raw.get("initial_point") or {}
        rows.append({**base, "request": request, "source_file": str(path.relative_to(ROOT)),
            "record_kind": "raw_final_response", "raw_status": raw.get("status"),
            "raw_exitflag": raw.get("exitflag"), "raw_output": out,
            "raw_output_numnodes": number(out.get("numnodes")),
            "raw_callback_max_numnodes": max(observed) if observed else None,
            "raw_fval_J": number(raw.get("fval")),
            "raw_lowerbound_J": number(out.get("lowerbound")),
            "raw_relativegap_native": number(out.get("relativegap")),
            "matching_return_budget_valid": timed_return,
            "method_elapsed_s": None,
            "timeline_eligible": False,
            "scope": "raw archive only; use accepted result callbacks/rounds for budget evidence",
            "RootLPAlgorithm": opts.get("RootLPAlgorithm"),
            "RootLPMaxIterations": opts.get("RootLPMaxIterations"),
            "LPPreprocess": opts.get("LPPreprocess"),
            "IntegerPreprocess": opts.get("IntegerPreprocess"),
            "raw_initial_point_provided": initial.get("provided"),
            "native_solver_x0_acceptance": initial.get("solver_acceptance"),
            "native_phase_seconds": raw.get("phase_seconds") or {},
            "raw_callback_count": len(callbacks)})
        for event in callbacks:
            values = event.get("values") or {}
            linked = received.get((request, event.get("event_number")), {})
            at = number(linked.get("method_elapsed_s"))
            rows.append({**base, "request": request, "source_file": str(path.relative_to(ROOT)),
                "record_kind": "raw_callback", "raw_callback_state": event.get("state"),
                "raw_phase": values.get("phase"), "event_number": event.get("event_number"),
                "raw_output_numnodes": number(values.get("numnodes")),
                "raw_fval_J": number(values.get("fval")),
                "raw_lowerbound_J": number(values.get("lowerbound")),
                "raw_relativegap_native": number(values.get("relativegap")),
                "request_wall_seconds": event.get("request_wall_seconds"),
                "linked_method_elapsed_s": at,
                "matching_received_in_budget": at is not None and 0 <= at < 300,
                "timeline_eligible": False,
                "scope": "raw archive only; never infer method time from request-relative clock"})
    return rows


def collect(folder):
    reader = ArchiveReader()
    declaration = reader.load(folder / "declaration.json")
    calls = reader.load(folder / "calls.json")
    assert isinstance(calls, list)
    jobs = declaration["manifest"]["jobs"]
    assert len(jobs) == 6
    declared = {j["call_id"]: j for j in jobs}
    assert len(declared) == 6
    byid = {c["job"]["call_id"]: c for c in calls}
    assert len(byid) == len(calls)
    assert all(c["job"] == declared[c["job"]["call_id"]] for c in calls)
    rows, timeline, progress, phases, native, details = [], [], [], [], [], []
    for job in jobs:
        cid = job["call_id"]
        call = byid.get(cid)
        callfolder = folder / cid
        base = {"call_id": cid, "problem_id": job["problem_id"], "variant": job["variant"]}
        accepted = (call is not None and call.get("returncode") == 0
                    and (call.get("technical_check") or {}).get("passed") is True)
        if not accepted:
            state = ("CONTROLLER_REJECTED" if call is not None else
                     "STARTED_NOT_CONTROLLER_FINAL" if (folder / (cid + ".claim.json")).is_file()
                     else "NOT_STARTED")
            rows.append({**base, "controller_state": state, "controller_accepted": False,
                "worker_returncode": call.get("returncode") if call else None,
                "controller_errors": (call.get("technical_check") or {}).get("errors") if call else None,
                "scope": "result/input/native archives deliberately unread without terminal controller acceptance"})
            continue
        result = reader.load(callfolder / "result.json")
        instance = reader.load(callfolder / "input_instance.json")
        assert canonical_hash(instance) == declaration["manifest"]["input_sha256"][job["problem_id"]]
        assert result.get("input_sha256") == canonical_hash(instance)
        assert result.get("preprocessing_variant") == job["variant"]
        existing = call_row(job, call, result, instance, callfolder, (folder / "stop.json").is_file(),
                            declaration["manifest"]["input_sha256"][job["problem_id"]])
        assert existing["call_state"] == "COMPLETED"
        assert not existing["safe"] or existing["audit_preserved_safe_evidence"]["preserved"]
        model = result.get("model_summary") or {}
        construction = result.get("construction") or {}
        timing = result.get("timing") or {}
        diag = result.get("diagnostic") or {}
        init = result.get("initialisation") or {}
        completion = init.get("completion") or {}
        admission = completion.get("numerical_acceptance") or {}
        native_rows = native_archive(callfolder, result, base, reader)
        native.extend(native_rows)
        final_native = [r for r in native_rows if r["record_kind"] == "raw_final_response"]
        entered = number(diag.get("solver_entered_received_s"))
        cb = []
        for event in diag.get("solver_progress", []):
            values = event.get("values") or {}
            at = number(event.get("method_elapsed_s"))
            event_row = {**base, "method_elapsed_s": at, "event_kind": event.get("kind"),
                "event_state": event.get("state"), "request": event.get("request"),
                "event_number": event.get("event_number"), "phase": values.get("phase"),
                "numnodes": number(values.get("numnodes")),
                "numfeaspoints": number(values.get("numfeaspoints")),
                "solver_reported_lowerbound_J": number(values.get("lowerbound")),
                "solver_reported_fval_J": number(values.get("fval")),
                "solver_reported_relativegap_native": number(values.get("relativegap")),
                "received_in_budget": at is not None and 0 <= at < job["seconds"],
                "independently_certified": False}
            cb.append(event_row)
            progress.append(event_row)
        budget_cb = [r for r in cb if r["received_in_budget"]]
        nodes = [r["numnodes"] for r in budget_cb if r["numnodes"] is not None]
        budget_reports = [r for r in existing["solver_reported_records"] if r["received_in_budget"]]
        root_phases = [r for r in budget_cb if "root" in str(r.get("phase", "")).lower()]
        conditional_calls = (construction.get("construction_components") or {}).get(
            "thermal_conditional_rows", {}).get("calls")
        complete_model = result.get("model_complete") is True and construction.get("status") == "MODEL_CONSTRUCTED"
        conditional_rows = (conditional_calls * 2 * (len(instance["platform"]["node_order"]) + 1)
                            if complete_model and isinstance(conditional_calls, int) else None)
        row = {**base, "controller_state": "COMPLETED", "controller_accepted": True,
            "worker_returncode": call["returncode"], "result_state": result.get("state"),
            "raw_reason": result.get("reason"), "safe": existing["safe"],
            "options": model.get("options"), "variables": model.get("variables"),
            "integer_variables": model.get("binary_variables"), "logical_binary_variables": model.get("logical_binary_variables"),
            "rows": model.get("rows"), "events_per_scene": model.get("events_per_scene"),
            "event_count_total": sum((model.get("events_per_scene") or {}).values()) or None,
            "control_intervals_per_scene": construction.get("scene_control_intervals_begun"),
            "conditional_thermal_energy_rows_derived": conditional_rows,
            "conditional_row_derivation": "completed recorded state-interval calls * 2*(thermal_nodes+energy_equation)",
            "model_complete": complete_model, "matrix_complete": result.get("matrix_complete"),
            "model_completed_at_s": result.get("model_completed_at_s"),
            "model_construction_s": (timing.get("phases_exclusive_s") or {}).get("model_construction"),
            "initialisation_state": init.get("state"), "initial_U_J": existing["initial_U_J"],
            "first_SAFE_at_s": existing["first_safe_at_s"],
            "first_legal_at_s": existing["first_legal_at_s"],
            "initial_x0_ready_at_s": completion.get("completed_at_s"),
            "x0_numerically_accepted": admission.get("accepted_numerically"),
            "x0_roundtrip": completion.get("decoded_roundtrip"),
            "x0_inequality_violation": admission.get("inequality_violation"),
            "native_solver_x0_acceptance": final_native[-1].get("native_solver_x0_acceptance") if final_native else "NO_FINAL_NATIVE_RECEIPT",
            "integer_solver_entered": existing["integer_solver_entered"],
            "solver_entered_received_s": entered,
            "post_entry_time_to_budget_s": job["seconds"]-entered if entered is not None and entered < job["seconds"] else None,
            "MILP_U_J": existing["MILP_U_J"], "final_SAFE_U_J": existing["U_J"],
            "strict_MILP_seed_improvement_from_receipts": existing["strict_MILP_seed_improvement_from_receipts"],
            "strict_improvement_reported": existing["strict_seed_improvement_reported"],
            "safe_solution_source": existing["safe_solution_source"],
            "first_MILP_legal_at_s": diag.get("first_legal_candidate_s"),
            "first_MILP_SAFE_at_s": diag.get("first_safe_receipt_s"),
            "certified_L0_J": existing["certified_L0_J"], "L0_formed_at_s": existing["L0_formed_at_s"],
            "solver_reported_lowerbound_J": existing["solver_reported_lowerbound_J"],
            "solver_reported_relativegap_native": existing["solver_reported_relativegap_native"],
            "solver_reported_bound_above_U_anomaly": existing["solver_reported_bound_above_U_anomaly"],
            "inbudget_callback_count": len(budget_cb), "inbudget_max_nodes_callback": max(nodes) if nodes else None,
            "root_LP_phase_observed": bool(root_phases),
            "root_LP_first_received_at_s": min((r["method_elapsed_s"] for r in root_phases), default=None),
            "heuristics_first_received_at_s": min((r["method_elapsed_s"] for r in budget_cb
                if str(r.get("phase", "")).lower() == "heuristics"), default=None),
            "root_LP_reported_fval_J": next((r["solver_reported_fval_J"] for r in reversed(root_phases)
                if r["solver_reported_fval_J"] is not None), None),
            "observed_nonempty_phases": sorted({str(r["phase"]) for r in budget_cb if r.get("phase")}),
            "root_LP_completion_or_duration": "NOT_IDENTIFIED_FROM_EMPTY_OR_MISSING_PHASE" if not root_phases else "CALLBACK_PHASE_ONLY",
            "RootLPAlgorithm_raw_config": final_native[-1].get("RootLPAlgorithm") if final_native else None,
            "budget_valid_rounds": sum(r.get("budget_valid") is True for r in result.get("rounds") or []),
            "round_statuses": [{k:r.get(k) for k in ("request_number", "status", "budget_valid", "exitflag", "accepted_for_evaluation")}
                               for r in result.get("rounds") or []],
            "feedback_calls": existing["feedback_calls"], "feedback_rows": existing["feedback_rows"],
            "method_elapsed_s": timing.get("method_elapsed_s"), "cleanup_s": timing.get("cleanup_s"),
            "process_wall_s": call.get("process_wall_s"), "budget_exhausted": result.get("budget_exhausted"),
            "original_safe_or_unsafe_status": result.get("state"),
            "independently_proven_optimal": result.get("independently_proven_optimal", False),
            "independently_proven_infeasible": result.get("independently_proven_infeasible", False)}
        rows.append(row)
        for name, seconds in (timing.get("phases_exclusive_s") or {}).items():
            phases.append({**base, "phase": name, "exclusive_s": seconds,
                           "scope": "disjoint method phase accounting; includes cooperative-checkpoint overshoot as archived"})
        for index, frame in enumerate(timing.get("phase_records") or []):
            details.append({**base, "index": index, **frame})
        safe_events = archived_safe_records(result, job["seconds"])
        best = None
        for event in safe_events:
            receipt = event["evaluation"]
            at, upper = number(receipt["completed_at_elapsed_s"]), F(receipt["safe_upper_bound_J"])
            assert at is not None and 0 <= at < job["seconds"]
            best = upper if best is None else min(best, upper)
            timeline.append({**base, "at_s": at, "kind": "independent_SAFE_U", "value_J": str(upper),
                "best_so_far_U_J": str(best), "source": event["source"],
                "budget_eligible": True, "independently_certified": "SAFE_only_not_optimality"})
        lower_at = number(existing["L0_formed_at_s"])
        if existing["certified_L0_J"] is not None and lower_at is not None and 0 <= lower_at < job["seconds"]:
            timeline.append({**base, "at_s": lower_at, "kind": "independent_L0", "value_J": existing["certified_L0_J"],
                "budget_eligible": True, "independently_certified": True})
        for event in budget_reports:
            value, at = number(event.get("lowerbound_J")), number(event.get("at_s"))
            # No fabricated callback time for a returned round without one.
            if value is not None and at is not None and 0 <= at < job["seconds"]:
                timeline.append({**base, "at_s": at, "kind": "solver_reported_lowerbound", "value_J": value,
                    "budget_eligible": True, "independently_certified": False})
        del result
    return {"rows": rows, "timeline": timeline, "progress": progress, "phases": phases,
            "phase_records": details, "native": native, "source_sha256": reader.sha256,
            "declaration": declaration, "calls": calls}


def plots(data, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    fig, axes = plt.subplots(1, 3, figsize=(13.2, 4.2), sharex=True, sharey=True)
    colors = {"current": "#2463a6", "prefilter": "#d15a28"}
    problems = list(dict.fromkeys(r["problem_id"] for r in data["rows"]))
    for ax, problem in zip(axes, problems):
        saw_solver = False
        for variant, color in colors.items():
            ts = [t for t in data["timeline"] if t["problem_id"] == problem and t["variant"] == variant]
            safe = sorted((t for t in ts if t["kind"] == "independent_SAFE_U"), key=lambda t:t["at_s"])
            if safe:
                x = [r["at_s"] for r in safe] + [300]
                y = [float(F(r["best_so_far_U_J"])) for r in safe]
                ax.step(x, y+[y[-1]], where="post", color=color, lw=2)
                ax.scatter([safe[0]["at_s"]], [y[0]], color=color, s=28, zorder=3)
            lower = [t for t in ts if t["kind"] == "independent_L0"]
            if lower:
                r = lower[0]
                ax.plot([r["at_s"], 300], [float(F(r["value_J"]))]*2, color=color, linestyle=":", lw=1.5)
            solver = sorted((t for t in ts if t["kind"] == "solver_reported_lowerbound"), key=lambda t:t["at_s"])
            if solver:
                saw_solver = True
                ax.plot([t["at_s"] for t in solver], [float(F(str(t["value_J"]))) for t in solver],
                        color=color, linestyle="-.", marker="x", lw=1)
        ax.set_title(problem.replace("__R1", ""))
        ax.set_xlim(0, 300)
        ax.grid(alpha=.2)
        ax.set_xlabel("Method elapsed time (s)")
        if not saw_solver:
            ax.text(.03, .04, "No finite in-budget solver bound", transform=ax.transAxes, fontsize=8)
    axes[0].set_ylabel("Complete-window weighted energy (J)")
    fig.legend(handles=[Line2D([0],[0],color=colors["current"],lw=2,label="current SAFE U"),
        Line2D([0],[0],color=colors["prefilter"],lw=2,label="prefilter SAFE U"),
        Line2D([0],[0],color="#555555",ls=":",label="Independent L0 (variant color)"),
        Line2D([0],[0],color="#555555",ls="-.",marker="x",label="Solver-reported bound (uncertified)")],
        loc="upper center",ncol=2,frameon=False,bbox_to_anchor=(.5,1.03),fontsize=9)
    fig.tight_layout(rect=(0,0,1,.86))
    fig.savefig(out / "safe_U_L0_timeline.png", dpi=170, bbox_inches="tight")
    fig.savefig(out / "safe_U_L0_timeline.pdf", bbox_inches="tight")
    plt.close(fig)


def summary(data, out):
    rows = data["rows"]
    accepted = [r for r in rows if r["controller_accepted"]]
    improved = [r for r in accepted if r["strict_MILP_seed_improvement_from_receipts"]]
    later = [r for r in accepted if number(r["MILP_U_J"]) is not None]
    lines = ["# K.108：期限前置过滤的六次完整链诊断", "",
        f"控制器已验收{len(accepted)}/6次；预算内后续MILP严格改善初始化{len(improved)}次。{len(accepted)-len(later)}次没有后续MILP SAFE，{len(later)}次取得后续SAFE，详见下表。每题每版仅一次、各300 s，只回答本次表达诊断，不推断总体胜率、稳定加速或算法贡献。77项冻结源码与当前文件／运行快照全部匹配。", "",
        "唯一差异为`prefilter_deadlines=false/true`及相应事件／状态／物理误差包络重建；原三Stage、共享具体单元、物理输入、初始构造器、LP none、连续热标准和预算保持。两版均采用conditional热反馈，本轮未运行assignment反馈消融；即使出现反馈也只支持实际触发／处理，不能把版本间U差归为反馈收益。未重跑原115项，没有跨调用导入旧候选、x0、热缓存或U。", "",
        "| 条件／版本 | 选项 | 事件总数 | 行数 | 主条件行¹ | 构模s | 首SAFE s | 初始U J | 最终U J | 严格改善 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for r in rows:
        if not r["controller_accepted"]:
            lines.append(f"| {r['problem_id']}/{r['variant']} | {r['controller_state']} | | | | | | | | |")
            continue
        lines.append(f"| {r['problem_id'].replace('__R1','')}/{r['variant']} | {r['options']} | {r['event_count_total']} | {r['rows']} | {r['conditional_thermal_energy_rows_derived']} | {display(r['model_construction_s'])} | {display(r['first_SAFE_at_s'])} | {display(r['initial_U_J'],6)} | {display(r['final_SAFE_U_J'],6)} | {'是' if r['strict_MILP_seed_improvement_from_receipts'] else '否'} |")
    lines.extend(["", "¹主条件行据已完成构模的状态—片段调用次数×2×(4个热节点＋1条能量式)还原，仅指热传播／完整能量条件行；不把它当总约束行。完整选项、变量、场景事件及阶段时间见`calls.csv`、`phases.csv`／`phase_records.csv`。", "",
        "| 条件／版本 | x0数值接纳 | 进入求解器s | 后续MILP U J | 预算内最大节点² | 求解器报告界 J | 反馈行 | 原状态／原因 |",
        "|---|---|---:|---:|---:|---:|---:|---|"])
    for r in accepted:
        lines.append(f"| {r['problem_id'].replace('__R1','')}/{r['variant']} | {r['x0_numerically_accepted']} | {display(r['solver_entered_received_s'])} | {display(r['MILP_U_J'],6)} | {display(r['inbudget_max_nodes_callback'],0)} | {display(r['solver_reported_lowerbound_J'],6)} | {r['feedback_rows']} | {r['result_state']}/{r['raw_reason']} |")
    lines.extend(["", "²节点来自预算内收到的callback；`0`不能证明根LP已结束，也不能精确归因根LP耗时。root LP配置、非空phase及原生终回执另存；没有阶段证据时明确记未识别。x0数值接纳只是原行／界容差检查，MATLAB的独立x0接纳状态按原回执`not_independently_observed`保留。", ""])
    for r in later:
        lines.append(f"{r['call_id']}在{display(r['first_MILP_SAFE_at_s'])} s取得后续完整SAFE，U={display(r['MILP_U_J'],6)} J，与本次种子等能量，最终保留初始化来源。它在{display(r['root_LP_first_received_at_s'])} s收到rootlp回调（报告松弛目标{display(r['root_LP_reported_fval_J'],9)} J），在{display(r['heuristics_first_received_at_s'])} s收到heuristics及有限内部界{display(r['solver_reported_lowerbound_J'],9)} J；预算内节点仍0，不能把该松弛目标当SAFE U或独立最优证书。该次没有原生最终response；前五次保存的最终原生response均在Python预算回执之外，不升级为预算内证据。")
    if later:
        lines.append("")
    for problem in dict.fromkeys(r["problem_id"] for r in rows):
        pair = {r["variant"]:r for r in accepted if r["problem_id"] == problem}
        if len(pair) != 2:
            lines.append(f"{problem}未形成完整已验收配对，不能作版本比较。")
            continue
        a,b = pair["current"],pair["prefilter"]
        gain = (number(a["final_SAFE_U_J"])-number(b["final_SAFE_U_J"])) if a["safe"] and b["safe"] else None
        lines.append(f"{problem}：current→prefilter构模{display(a['model_construction_s'])}→{display(b['model_construction_s'])} s，首SAFE {display(a['first_SAFE_at_s'])}→{display(b['first_SAFE_at_s'])} s，最终安全U差(current−prefilter)={display(gain,6)} J；两版后续严格改善分别为{a['strict_MILP_seed_improvement_from_receipts']}/{b['strict_MILP_seed_improvement_from_receipts']}。")
    lines.extend(["", "![预算内SAFE U、独立L0及求解器报告界](safe_U_L0_timeline.png)", "",
        "图只使用预算内完整SAFE回执及形成时间已知的L0。内部界使用点划线和×标记、明确`solver-reported`，不升级为独立证书；预算后原生done／response只在`raw_native_receipts.csv`审计，不填入预算内轨迹。没有有限内部界时图中明确标缺失。", "",
        "未验收／未完成／未启动调用在`calls.csv`单列，未读取其结果文件。反馈为0只表示本次未触发，不能据此证明反馈有效或无用。所有状态、原始原因及求解器界异常保留；性能不佳不触发补跑、扩时或调参。", "",
        "## P1：已有15题能耗归因（一页）", ""])
    old = (HERE / "summary_existing.md").read_text(encoding="utf-8")
    lines.append("\n".join(old.splitlines()[2:]))
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()
    data = collect(args.input.resolve())
    frozen_sources = data["declaration"]["source_sha256"]
    source77 = {name: {
        "current_matches_frozen": hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected,
        "snapshot_matches_frozen": hashlib.sha256((args.input / "source_snapshot" / name).read_bytes()).hexdigest() == expected,
        "frozen_sha256": expected}
        for name, expected in frozen_sources.items()}
    assert len(source77) == 77
    assert all(v["current_matches_frozen"] and v["snapshot_matches_frozen"] for v in source77.values())
    for name, key in (("calls.csv", "rows"), ("timeline.csv", "timeline"),
                      ("solver_progress.csv", "progress"), ("phases.csv", "phases"),
                      ("phase_records.csv", "phase_records"), ("raw_native_receipts.csv", "native")):
        write_csv(HERE / name, data[key])
    plots(data, HERE)
    summary(data, HERE)
    audit = {"scope": "controller-terminal-accepted archive reads only; no solve/thermal propagation/candidate construction",
        "declared_calls": 6, "controller_terminal_calls": len(data["calls"]),
        "controller_accepted_calls": sum(r["controller_accepted"] for r in data["rows"]),
        "source_sha256": data["source_sha256"],
        "frozen_source_count": len(source77), "frozen_source_verification": source77,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "archive_helper_sha256": hashlib.sha256((HERE.parent / "analyze_formal.py").read_bytes()).hexdigest(),
        "raw_native_diagnostics_are_never_timeline_inputs": True,
        "new_method_calls": 0, "new_thermal_evaluations": 0,
        "output_use": "post-hoc diagnostic only; not method candidates/x0/cache/U"}
    (HERE / "new_analysis_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(compact({"accepted_calls": audit["controller_accepted_calls"],
        "timeline_records": len(data["timeline"]), "out": str(HERE)}))


if __name__ == "__main__":
    main()
