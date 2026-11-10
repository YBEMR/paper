"""Reuse bounded temperature integrals and saved sample points; no thermal solver.

Preparation only validates sources and writes a frozen plan. Derive mode requires
root's A-delivery ordering marker, then computes rational interval means and plots
exactly the fourteen existing scenario trajectories. No research modules import.
"""
import argparse
import csv
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import time

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[4]
COMMIT = "4339bdcc7dc6d37adf42963ed731f78d5f8ff63e"
IDS = ("t50_milp", "t50_heft", *(f"t50_sa{s}" for s in range(101, 106)))
PREFIX = "research/chapter3_experiments/results/"
ROOT = PREFIX + "chapter3_closure_execution01/slots/"
SUMMARY = PREFIX + "chapter3_closure_analysis01/summary.json"
PREPARED = PREFIX + "chapter3_closure_preparation01/t50_full/input_instance.json"


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def read(path):
    return json.loads(path.read_text())


def exact_interval(value):
    lo, hi = map(F, value)
    if lo > hi:
        raise ValueError("REVERSED_INTERVAL")
    return lo, hi


def strings(interval):
    return [str(v) for v in interval]


def temperature_mean(ambient, integral, duration):
    """Exact rational endpoint mapping; no discretization or interpolation."""
    ambient, duration = F(ambient), F(duration)
    if duration <= 0:
        raise ValueError("NONPOSITIVE_DURATION")
    lo, hi = exact_interval(integral)
    return ambient + lo / duration, ambient + hi / duration


def comparison(left, right):
    a, b = exact_interval(left), exact_interval(right)
    # Difference encloses right-left. Distance is zero when intervals overlap.
    delta = b[0] - a[1], b[1] - a[0]
    return {"right_minus_left_interval": strings(delta),
            "midpoint_abs_difference": str(abs(sum(b) - sum(a)) / 2),
            "interval_distance": str(max(F(0), b[0] - a[1], a[0] - b[1])),
            "overlap": max(a[0], b[0]) <= min(a[1], b[1])}


def paths(identifier):
    method = ROOT + identifier + "__method/worker/method/"
    return {"config": method + "input_config.json", "instance": method + "input_instance.json",
            "method": method + "result.json", "post": ROOT + identifier + "__post/worker/post_result.json"}


def committed_source(relative, identities):
    working = (REPO / relative).read_bytes()
    committed = subprocess.check_output(["git", "show", f"{COMMIT}:{relative}"], cwd=REPO)
    if committed != working:
        raise ValueError("SOURCE_DIFFERS_FROM_TARGET_COMMIT:" + relative)
    identities[relative] = {"sha256": hashlib.sha256(working).hexdigest(),
                            "commit_blob": subprocess.check_output(
                                ["git", "rev-parse", f"{COMMIT}:{relative}"], cwd=REPO, text=True).strip(),
                            "bytes": len(working)}
    return json.loads(working)


def prepare():
    if (OUT / "plan.json").exists():
        raise FileExistsError("PLAN_ALREADY_EXISTS")
    entered, started = time.monotonic(), now()
    source_ids = {}
    summary = committed_source(SUMMARY, source_ids)
    prepared = committed_source(PREPARED, source_ids)
    slots = []
    first_config = None
    for identifier in IDS:
        p = paths(identifier)
        data = {key: committed_source(value, source_ids) for key, value in p.items()}
        instance, config = data["instance"], data["config"]
        if first_config is None:
            first_config = config
        assert instance == prepared and config == first_config
        assert instance["window_ms"] == "400"
        assert len(instance["scenarios"]) == 2
        assert len(instance["platform"]["node_order"]) == 4
        final = data["method"]["safe_candidate"]
        post = data["post"]
        evaluation = post["evaluation"]
        entry = next(row for row in summary["methods"] if row["id"] == identifier)
        assert entry["case"] == "t50_full" and entry["enforce_80C_in_planning"]
        assert final == entry["final_candidate"] == post["same_candidate"]
        assert evaluation["state"] == "SAFE" and post["safe"]["preserved"]
        assert evaluation["evidence_identity"] == {
            "input_sha256": canonical(instance), "candidate_sha256": canonical(final)}
        scene_metadata = []
        for scene in instance["scenarios"]:
            sid = scene["id"]
            receipt = evaluation["scenes"][sid]
            assert scene["entry"]["temperature_degC"] == ["50"] * 4
            assert scene["maximum_temperature_degC"] == ["80"] * 4
            assert receipt["state"] == "SAFE" and receipt["complete"]
            assert F(receipt["covered_until_s"]) == F(2, 5)
            assert F(receipt["trace"][-1]["time_s"]) == F(2, 5)
            assert set(receipt["temperature_rise_integrals_Ks"]) == set(instance["platform"]["node_order"])
            scene_metadata.append({"scene_id": sid, "saved_trace_points": len(receipt["trace"]),
                                   "duration_s": receipt["covered_until_s"], "integrals_present": True})
        slots.append({"id": identifier, "method": entry["method"], "seed": entry["seed"], "paths": p,
                      "input_canonical_sha256": canonical(instance), "config_canonical_sha256": canonical(config),
                      "candidate_canonical_sha256": canonical(final), "scene_metadata": scene_metadata})
    assert len(slots) == 7 and sum(len(s["scene_metadata"]) for s in slots) == 14
    plan = {"schema": "workpackage-B-fixed400ms-reuse-v1", "created_utc": now(),
            "source_commit": COMMIT, "runtime_HEAD": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
            "slots": slots, "source_identities": source_ids,
            "scope": "Exactly seven final fixed schedules, each independent AB/AC400ms,50C entry/80C limit; no rescheduling, domain/model/input changes",
            "formula": "mean_T_node = ambient_temperature_degC + integral(T_node-ambient)dt / (2/5 s)",
            "means": "Per node per scene intervals; per scheme max over eight node-scene means, with possible maximizers retained",
            "reuse": "All fourteen complete scene integrals and trace samples already exist. No new evaluator or numerical integration.",
            "plot": "Four nodes per scenario; preserve400ms idle tail, add declared t0, joins are illustrative, original continuous peak enclosure remains safety evidence",
            "semantics": "Energy alone optimization objective. Peaks/means/runtime descriptive. No lifetime ratio or weighted multiobjective score.",
            "gate": "Root must create order_gate.json confirming A feedback delivered before derive mode",
            "new_thermal_integrations": 0, "new_schedule_searches": 0,
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "environment": {"python": platform.python_version(), "platform": platform.platform(),
                            "matplotlib": importlib.metadata.version("matplotlib")},
            "preparation": {"started_utc": started, "ended_utc": now(), "wall_s": time.monotonic() - entered}}
    save(OUT / "plan.json", plan)
    save(OUT / "plan_identity.json", {"sha256": hashlib.sha256((OUT / "plan.json").read_bytes()).hexdigest()})
    print(json.dumps({"prepared": True, "source_files_verified_against_commit": len(source_ids),
                      "fixed_schedules": 7, "scene_integrals_reusable": 14,
                      "new_physics": 0, "preparation_s": plan["preparation"]["wall_s"]}), flush=True)


def validate_frozen(plan):
    if hashlib.sha256((OUT / "plan.json").read_bytes()).hexdigest() != read(OUT / "plan_identity.json")["sha256"]:
        raise ValueError("PLAN_DRIFT")
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != plan["script_sha256"]:
        raise ValueError("SCRIPT_DRIFT")
    for relative, value in plan["source_identities"].items():
        if hashlib.sha256((REPO / relative).read_bytes()).hexdigest() != value["sha256"]:
            raise ValueError("SOURCE_DRIFT:" + relative)


def derive():
    entered, started = time.monotonic(), now()
    plan = read(OUT / "plan.json")
    validate_frozen(plan)
    gate = read(OUT / "order_gate.json")
    if not gate.get("A_feedback_delivered"):
        raise ValueError("A_DELIVERY_ORDER_GATE_REQUIRED")
    if (OUT / "B_metrics.json").exists():
        raise FileExistsError("B_ALREADY_DERIVED")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    means, trajectory_rows, summary_rows, details, checks = [], [], [], [], []
    figure_paths = []
    figures = OUT / "figures"
    figures.mkdir(exist_ok=False)
    colors = {"CPU1": "#3268a8", "CPU2": "#6c91c2", "GPU0": "#c16920", "NPU0": "#27865c"}
    for slot in plan["slots"]:
        identifier = slot["id"]
        data = {key: read(REPO / relative) for key, relative in slot["paths"].items()}
        instance, config = data["instance"], data["config"]
        old = data["method"]["evaluation"]
        post = data["post"]["evaluation"]
        duration = F(instance["window_ms"]) / 1000
        assert duration == F(2, 5)
        ambient = F(instance["platform"]["ambient_temperature_degC"])
        nodes = instance["platform"]["node_order"]
        scheme_means, peak_errors, scene_details = [], [], []
        for scene in instance["scenarios"]:
            sid = scene["id"]
            receipt, previous = post["scenes"][sid], old["scenes"][sid]
            assert receipt["complete"] and F(receipt["covered_until_s"]) == duration
            assert F(receipt["trace"][-1]["time_s"]) == duration
            raw_points = [{"time_s": "0", "temperature_degC": dict(zip(nodes, ([t, t] for t in scene["entry"]["temperature_degC"]))), "source": "declared_entry_added_for_display"}]
            raw_points += [{**point, "source": "existing_panel_end"} for point in receipt["trace"]]
            assert len({F(point["time_s"]) for point in raw_points}) == len(raw_points)
            assert all(F(a["time_s"]) < F(b["time_s"]) for a, b in zip(raw_points, raw_points[1:]))
            maximum_end = max(F(row["end_ms"]) for row in post["legality"]["scenes"][sid]["rows"])
            assert maximum_end <= 400
            fig, ax = plt.subplots(figsize=(9.2, 5.1))
            for node in nodes:
                integral = receipt["temperature_rise_integrals_Ks"][node]
                mean = temperature_mean(ambient, integral, duration)
                minimum, peak = exact_interval(receipt["minimum_degC"][node]), exact_interval(receipt["peaks_degC"][node])
                assert minimum[0] <= mean[0] <= mean[1] <= peak[1]
                assert peak[1] <= F(80)
                row = {"scheme": identifier, "method": slot["method"], "seed": slot["seed"], "scene": sid, "node": node,
                       "duration_s": str(duration), "ambient_degC": str(ambient),
                       "integral_lower_Ks": integral[0], "integral_upper_Ks": integral[1],
                       "mean_lower_degC": str(mean[0]), "mean_upper_degC": str(mean[1]),
                       "mean_lower_degC_display": float(mean[0]), "mean_upper_degC_display": float(mean[1]),
                       "continuous_peak_lower_degC": receipt["peaks_degC"][node][0],
                       "continuous_peak_upper_degC": receipt["peaks_degC"][node][1],
                       "state": receipt["state"], "mean_calculation": "exact rational mapping of existing bounded integral"}
                means.append(row)
                scheme_means.append((sid, node, mean))
                error = comparison(previous["peaks_degC"][node], receipt["peaks_degC"][node])
                peak_errors.append({"scene": sid, "node": node, **error})
                t = [float(F(point["time_s"]) * 1000) for point in raw_points]
                lower = [float(F(point["temperature_degC"][node][0])) for point in raw_points]
                upper = [float(F(point["temperature_degC"][node][1])) for point in raw_points]
                ax.plot(t, [(a + b) / 2 for a, b in zip(lower, upper)], color=colors[node], marker="o", markersize=3.5, linewidth=1.3, label=node)
                ax.fill_between(t, lower, upper, color=colors[node], alpha=0.16)
                witness = receipt["peak_witnesses"][node]
                ax.scatter([float(F(witness["time_s"]) * 1000)], [float(sum(map(F, witness["temperature_degC"])) / 2)], color=colors[node], marker="x", s=28, zorder=4)
                for point in raw_points:
                    interval = point["temperature_degC"][node]
                    trajectory_rows.append({"scheme": identifier, "scene": sid, "node": node,
                        "time_s": point["time_s"], "time_ms": str(F(point["time_s"]) * 1000),
                        "temperature_lower_degC": interval[0], "temperature_upper_degC": interval[1], "point_source": point["source"]})
                trajectory_rows.append({"scheme": identifier, "scene": sid, "node": node,
                    "time_s": witness["time_s"], "time_ms": str(F(witness["time_s"]) * 1000),
                    "temperature_lower_degC": witness["temperature_degC"][0], "temperature_upper_degC": witness["temperature_degC"][1], "point_source": "existing_peak_point_witness_not_line_sample"})
            ax.axvspan(float(maximum_end), 400, color="#d9dce1", alpha=0.25, label="idle tail retained")
            ax.set_xlim(0, 400)
            ax.set_xlabel("Time within independent scene (ms)")
            ax.set_ylabel("Temperature (deg C)")
            ax.set_title(f"{identifier} / {sid.replace('_offset_0ms', '')} / saved 400 ms trajectory")
            ax.grid(alpha=0.18)
            ax.legend(ncol=3, fontsize=8)
            fig.text(0.5, 0.015, "Lines join saved panel-end samples for display only. x = saved peak witness. Safety uses full continuous enclosure.", ha="center", fontsize=7)
            fig.tight_layout(rect=(0, 0.035, 1, 1))
            stem = f"{identifier}__{sid}"
            for extension in ("png", "svg"):
                target = figures / (stem + "." + extension)
                fig.savefig(target, dpi=170)
                figure_paths.append(target.relative_to(OUT).as_posix())
            plt.close(fig)
            scene_details.append({"scene": sid, "complete": receipt["complete"], "covered_until_s": receipt["covered_until_s"],
                "last_task_end_ms": str(maximum_end), "idle_tail_duration_ms": str(400 - maximum_end),
                "saved_panel_end_points": len(receipt["trace"]), "added_entry_points": 1,
                "energy_comparison_original_method_vs_saved_post": comparison(previous["energy_J"], receipt["energy_J"]),
                "new_thermal_integration": False})
        worst = max(value[0] for _, _, value in scheme_means), max(value[1] for _, _, value in scheme_means)
        possible = [(sid, node) for sid, node, mean in scheme_means if mean[1] >= worst[0]]
        upper_winner = max(scheme_means, key=lambda value: value[2][1])
        energy_error = comparison(old["weighted_energy_J"], post["weighted_energy_J"])
        row = {"scheme": identifier, "method": slot["method"], "seed": slot["seed"],
            "input_canonical_sha256": slot["input_canonical_sha256"], "candidate_canonical_sha256": slot["candidate_canonical_sha256"],
            "system_energy_lower_J": post["weighted_energy_J"][0], "system_energy_upper_J": post["weighted_energy_J"][1],
            "system_energy_upper_J_display": float(F(post["weighted_energy_J"][1])),
            "maximum_continuous_peak_upper_degC_display": float(max(F(interval[1]) for scene in post["scenes"].values() for interval in scene["peaks_degC"].values())),
            "worst_node_scene_time_mean_lower_degC": str(worst[0]), "worst_node_scene_time_mean_upper_degC": str(worst[1]),
            "worst_node_scene_time_mean_upper_degC_display": float(worst[1]),
            "upper_max_scene": upper_winner[0], "upper_max_node": upper_winner[1],
            "possible_maximizers": json.dumps(possible), "original_method_SAFE": old["state"], "saved_post_SAFE": post["state"],
            "weighted_energy_midpoint_abs_difference_J": energy_error["midpoint_abs_difference"],
            "weighted_energy_interval_distance_J": energy_error["interval_distance"],
            "weighted_energy_intervals_overlap": energy_error["overlap"],
            "mean_interval_max_width_K": str(max(value[1] - value[0] for _, _, value in scheme_means))}
        summary_rows.append(row)
        details.append({"scheme": identifier, "scene_details": scene_details, "peak_comparisons": peak_errors,
            "weighted_energy_comparison": energy_error,
            "source_SAFE_checks": {"original_method": old["state"], "saved_post": post["state"],
                "saved_post_identity_matches_frozen_schedule": post["evidence_identity"]["candidate_sha256"] == slot["candidate_canonical_sha256"]}})
    assert len(means) == 56 and len(summary_rows) == 7 and len(figure_paths) == 28
    validate_frozen(plan)
    for name, rows in (("node_time_means.csv", means), ("scheme_thermal_summary.csv", summary_rows), ("saved_trajectory_points.csv", trajectory_rows)):
        with (OUT / name).open("x", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    result = {"schema": "workpackage-B-fixed400ms-derived-results-v1", "created_utc": now(),
        "source_commit": COMMIT, "plan_sha256": read(OUT / "plan_identity.json")["sha256"],
        "A_order_gate": gate, "scope": plan["scope"], "formula": plan["formula"],
        "scheme_summary": summary_rows, "node_time_means": means, "comparison_details": details,
        "figure_paths": figure_paths, "scenario_trajectories": 14, "new_schedule_searches": 0,
        "new_thermal_integrations": 0, "new_periodic_solves": 0,
        "source_receipts_reused": 14, "means_are_not_independent_evaluator_validation": True,
        "plot_interpolation_is_not_a_safety_proof": True,
        "lifetime_ratio_or_weighted_multiobjective_score_computed": False,
        "execution": {"started_utc": started, "ended_utc": now(), "wall_s": time.monotonic() - entered,
            "posterior_derivation_and_plot_time_only": True}}
    save(OUT / "B_metrics.json", result)
    write_summary(result)
    print(json.dumps({"B_complete": True, "means": 56, "fixed_scene_trajectories": 14,
        "figures": 14, "files_png_svg": 28, "new_physics": 0,
        "postprocessing_s": result["execution"]["wall_s"]}), flush=True)


def write_summary(result):
    rows = result["scheme_summary"]
    lines = ["# 工作包B：七方案400ms温度轨迹与时间均温", "",
        "已复用指定提交中七个终解的14份完整场景凭证，计算56个节点/场景时间均温与每方案最坏场景/节点均温；没有新增热积分或调度搜索。时间范围完整保留400ms及任务后的空闲尾段。", "",
        "|方案|完整系统能耗上界 J|连续峰温上界 °C|最坏节点/场景时间均温上界 °C|对应场景/节点|",
        "|---|---:|---:|---:|---|"]
    for row in rows:
        lines.append(f"|{row['scheme']}|{row['system_energy_upper_J_display']:.12f}|{row['maximum_continuous_peak_upper_degC_display']:.9f}|{row['worst_node_scene_time_mean_upper_degC_display']:.9f}|{row['upper_max_scene']} / {row['upper_max_node']}|")
    energy_errors = [F(row["weighted_energy_midpoint_abs_difference_J"]) for row in rows]
    peak_errors = [F(row["midpoint_abs_difference"]) for detail in result["comparison_details"] for row in detail["peak_comparisons"]]
    lines += ["", "均温用原记录的有向包络积分逐端点作精确有理数变换：`Ta + integral(T-Ta)dt/(2/5 s)`；完整区间与积分值在 `node_time_means.csv`，每方案取八个节点/场景均温的最大值，不作场景串接或综合加权得分。最大者区间重叠时保留全部可能最大对象。", "",
        f"原方法凭证与原post凭证比较：加权总能量中点最大绝对差 {float(max(energy_errors)):.12g} J；峰温区间中点最大绝对差 {float(max(peak_errors)):.12g} K。逐项差区间、区间距离与是否重叠见 `B_metrics.json`。此处比较既有两份记录，未重新求解或形成新的独立数值证书。原方法及post七份均为SAFE。", "",
        "完整系统能耗仍为唯一优化目标；峰温、时间均温和运行时间均为描述性指标。没有计算寿命延长比例或加权多目标分数。", "",
        "## 图与原始点", "",
        "`figures/` 有14张场景图，每张四节点曲线，PNG/SVG双格式。补入各场景原声明t=0入口50°C，灰区标出最后任务完成后仍保留的空闲尾段；×号是原凭证保存的峰值点见证。折线仅连接原数值面板末点展示，不能据此宣称连续曲线安全；连续安全依据为原全窗口峰温包络与完整SAFE凭证。", ""]
    for path in result["figure_paths"]:
        if path.endswith(".png"):
            lines.append(f"- [{Path(path).stem}]({path})")
    lines += ["", "`saved_trajectory_points.csv` 区分原面板末点、补入的声明入口及原峰值点见证；均未调用新热评价。", "",
        "## 来源、计时与验证", "",
        f"固定源提交 `{COMMIT}`。`plan.json` 列出七个固定候选的canonical身份与所有源文件SHA256/Git blob，准备阶段逐文件核对提交与工作区字节完全相等。执行前后再核对源哈希；运行方案哈希 `{result['plan_sha256']}`。", "",
        f"后验派生/绘图开始 {result['execution']['started_utc']}，结束 {result['execution']['ended_utc']}，耗时 {result['execution']['wall_s']:.6f}秒，单独记录，不并入原方法搜索耗时。准备、测试及实际命令日志见 `command_*`。", "",
        "实际命令（cwd `/workspace/paper`）：", "", "```text",
        "python -B research/chapter4_scheduler/results/evaluation_workpackages_20261110/workpackage_B/reuse_trajectories.py prepare",
        "python -B research/chapter4_scheduler/results/evaluation_workpackages_20261110/workpackage_B/reuse_trajectories.py derive",
        "```", "",
        "范围仅指定七份固定终解、独立AB/AC的400ms单轮描述；没有延长窗口、改变部署/频档/时间表、串接场景、周期稳态求解、参数扫描或新优化。单轮均温不能替代周期稳态峰温，也不能推断长期寿命或算法普遍性。", ""]
    with (OUT / "B_summary.md").open("x") as stream:
        stream.write("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("prepare", "derive"))
    args = parser.parse_args()
    prepare() if args.phase == "prepare" else derive()
