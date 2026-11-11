"""Make two scientific figures from saved summaries; no scientific execution.

Writes PNG and PDF for each figure. Missing, failed, unverified and over-limit
results remain visually distinct; no missing result is replaced with zero.
"""
import argparse
from fractions import Fraction as Q
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D

FULL = "#2166AC"
NO_LIMIT = "#7B3294"
UNVERIFIED = "#C77C1F"
UNSAFE = "#C43C39"


def configure_fonts():
    installed = {entry.name for entry in font_manager.fontManager.ttflist}
    selected = next((name for name in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Arial Unicode MS") if name in installed), None)
    if selected is None:
        raise RuntimeError("A Chinese font is required for the scientific figures; none of the declared fonts is installed")
    plt.rcParams.update({"font.family": selected, "font.size": 10,
                         "axes.unicode_minus": False, "pdf.fonttype": 42,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.titlelocation": "left", "savefig.facecolor": "white"})
    return selected


def value(v):
    return None if v is None else float(Q(str(v)))


def energy(row):
    interval = row.get("final_energy_interval_J")
    if interval and row.get("physical_values_source"):
        return value(interval[1])
    if row.get("post_complete_physical_evaluation") and row.get("post_diagnostic_energy_interval_J"):
        return value(row["post_diagnostic_energy_interval_J"][1])
    return None


def short_status(row):
    if row.get("common_80_C_feasible") is False:
        return "超温"
    state = row.get("execution_status")
    if state == "NOT_RUN":
        return "未运行"
    if state == "NO_TERMINAL_RECEIPT":
        return "无终态记录"
    if state and not state.startswith("NORMAL_"):
        return "异常"
    if not row.get("planning_complete_SAFE"):
        return "无完整方案"
    if not row.get("rankable_80C"):
        return "未独立确认"
    return "80°C复核通过"


def plot_point(ax, x, y, row, color=FULL, marker="o", label=None, label_height=7):
    if y is None:
        ax.text(x, 0.04, short_status(row), transform=ax.get_xaxis_transform(),
                ha="center", va="bottom", fontsize=8, color="#666666", rotation=30)
        return False
    if row.get("common_80_C_feasible") is False:
        ax.scatter([x], [y], marker="x", color=UNSAFE, s=65, linewidth=1.8, zorder=5)
    elif row.get("rankable_80C"):
        ax.scatter([x], [y], marker=marker, color=color, s=45, zorder=5)
    elif short_status(row) == "异常":
        ax.scatter([x], [y], marker="^", facecolors="none", edgecolors=UNVERIFIED,
                   linewidth=1.5, s=65, zorder=5)
    else:
        ax.scatter([x], [y], marker=marker, facecolors="none", edgecolors=UNVERIFIED,
                   linewidth=1.5, s=60, zorder=5)
    if label:
        ax.annotate(label, (x, y), xytext=(0, label_height), textcoords="offset points",
                    ha="center", fontsize=8, color="#333333")
    return True


def conditional_figure(data):
    fig, ax = plt.subplots(figsize=(8.6, 5.4))
    fig.subplots_adjust(left=0.12, right=0.97, bottom=0.27, top=0.85)
    fixed = data["shared_conditioned_optima"]
    numbers = [value(fixed["CPU1"]["exact_J"][1]), value(fixed["NPU0"]["exact_J"][1]),
               value(data["HEFT"]["energy"]["exact_J"][1])]
    ax.bar(range(3), numbers, color=["#9E9E9E", FULL, "#E69F00"], width=0.58)
    labels = ["固定 A.main＝CPU1\n其余决策充分优化", "固定 NPU0／开放部署\n条件最优＝开放最优", "适配 HEFT 实际结果\nA.main＝CPU1"]
    ax.set_xticks(range(3), labels)
    ax.set_ylabel("场景加权完整能耗 / J")
    ax.set_ylim(0, max(numbers) * 1.21)
    ax.grid(axis="y", alpha=0.2)
    ax.set_axisbelow(True)
    for x, y in enumerate(numbers):
        ax.text(x, y + 0.018, f"{y:.12f}", ha="center", fontsize=10)
    ax.set_title("K.194：提前固定部署会改变后续可达到的能耗", fontsize=14, pad=20)
    penalty = value(data["CPU1_fixing_penalty_J"]["exact_J"][1])
    saving = value(data["opening_CPU1_choice_saving_percent_of_CPU1"][1])
    residual = value(data["HEFT"]["gap_to_CPU1_conditional_optimum_J"]["exact_J"][1])
    fig.text(0.12, 0.145, f"开放 CPU1／NPU0 选择：相对 CPU1 条件最优减少 {penalty:.6f} J（{saving:.4f}%）。", fontsize=10)
    fig.text(0.12, 0.100, f"HEFT 距 CPU1 条件最优仅 {residual * 1e6:.3f} μJ；本例共享与独立部署最优值相同。", fontsize=10)
    fig.text(0.12, 0.035, "仅对应 K.194 受限选择域，AB／AC 权重各 1/2。区间宽度小于图示分辨率；图示数值为上界。\n条件最优差额不等于单因素消融因果贡献，不能外推自然完整域。", fontsize=8.4, color="#555555")
    return fig


def method_panel(ax, rows, metric, title, ylabel):
    ax.set_title(title, fontsize=12)
    ax.set_ylabel(ylabel)
    ax.set_xticks([0, 1, 2], ["MILP", "适配 HEFT", "SA 101—105"])
    ax.set_xlim(-0.45, 2.45)
    ax.grid(axis="y", alpha=0.22)
    plotted = []
    for method, x in (("whole_milp", 0), ("heft", 1)):
        selection = [row for row in rows if row["method"] == method]
        if not selection:
            continue
        row = selection[0]
        y = metric(row)
        if plot_point(ax, x, y, row, label=None if y is None else f"{y:.6f}" if metric is energy else f"{y:.1f}"):
            plotted.append(y)
    sa = sorted((row for row in rows if row["method"] == "sa"), key=lambda row: row["seed"])
    missing = []
    for index, row in enumerate(sa):
        offset = (index - (len(sa) - 1) / 2) * 0.085
        y = metric(row)
        if y is None:
            missing.append(f"{row['seed']}：{short_status(row)}")
            continue
        if plot_point(ax, 2 + offset, y, row, color="#238B45", label=str(row["seed"]), label_height=7 + 14 * (index % 2)):
            plotted.append(y)
    if missing:
        ax.text(2, 0.04, "\n".join(missing), transform=ax.get_xaxis_transform(),
                ha="center", va="bottom", fontsize=7.5, color="#666666")
    valid = [metric(row) for row in sa if row.get("rankable_80C") and metric(row) is not None]
    if valid:
        ordered = sorted(valid)
        middle = len(ordered) // 2
        median = ordered[middle] if len(ordered) % 2 else sum(ordered[middle - 1:middle + 1]) / 2
        ax.plot([2.31, 2.31], [min(valid), max(valid)], color="black", linewidth=1.5, zorder=4)
        ax.plot([2.27, 2.35], [min(valid)] * 2, color="black", linewidth=1)
        ax.plot([2.27, 2.35], [max(valid)] * 2, color="black", linewidth=1)
        ax.scatter([2.31], [median], marker="D", s=24, color="black", zorder=6)
    if plotted:
        lo, hi = min(plotted), max(plotted)
        spread = max(hi - lo, abs(hi) * 0.025, 1e-5)
        ax.set_ylim(max(0, lo - 0.3 * spread), hi + 0.40 * spread)
    else:
        ax.set_ylim(0, 1)
        ax.set_yticks([])
        ax.text(0.5, 0.55, "没有可绘制的已保存数值", transform=ax.transAxes, ha="center", color="#777777")


def ablation_panel(ax, rows, metric, title, ylabel):
    ax.set_title(title, fontsize=12)
    ax.set_ylabel(ylabel)
    ax.set_xticks([0, 1], ["初温 50°C", "初温 78°C"])
    ax.set_xlim(-0.4, 1.4)
    ax.grid(axis="y", alpha=0.22)
    plotted = []
    for x, t in enumerate(("50", "78")):
        paired = []
        for enforced, offset, color, marker in ((True, -0.12, FULL, "o"), (False, 0.12, NO_LIMIT, "s")):
            selection = [r for r in rows if r["method"] == "whole_milp" and Q(r["initial_temperature_degC"]) == Q(t)
                         and r["enforce_80C_in_planning"] is enforced]
            if not selection:
                continue
            row = selection[0]
            y = metric(row)
            if y is None:
                ax.text(x, 0.04 if enforced else 0.13,
                        ("完整：" if enforced else "去温限：") + short_status(row),
                        transform=ax.get_xaxis_transform(), ha="center", va="bottom", fontsize=8, color="#666666")
                continue
            if plot_point(ax, x + offset, y, row, color=color, marker=marker,
                          label=None if y is None else f"{y:.6f}" if metric is energy else f"{y:.3f}"):
                plotted.append(y)
                paired.append((x + offset, y))
        if len(paired) == 2:
            ax.plot([p[0] for p in paired], [p[1] for p in paired], color="#AAAAAA", linewidth=0.8, zorder=1)
    if plotted:
        lo, hi = min(plotted), max(plotted)
        spread = max(hi - lo, abs(hi) * 0.025, 1e-5)
        ax.set_ylim(max(0, lo - 0.3 * spread), hi + 0.35 * spread)
    else:
        ax.set_ylim(0, 1)
        ax.set_yticks([])
        ax.text(0.5, 0.55, "没有可绘制的已保存数值", transform=ax.transAxes, ha="center", color="#777777")


def comparison_figure(summary):
    rows = summary["methods"]
    selected = [r for r in rows if r["case"] == "t50_full"]
    fig, axes = plt.subplots(2, 2, figsize=(12.2, 9.2))
    fig.subplots_adjust(left=0.085, right=0.975, bottom=0.19, top=0.88, hspace=0.48, wspace=0.28)
    fig.suptitle("自然完整选择域：期限 β＝1.0，方法比较与温限消融", fontsize=16, x=0.51, y=0.96)
    method_panel(axes[0, 0], selected, energy, "(a) 初温50°C：最终完整能耗", "能耗 / J")
    method_panel(axes[0, 1], selected, lambda r: value(r.get("total_method_wall_s")),
                 "(b) 初温50°C：实际方法计算时间", "方法进程耗时（含清理）/ s")
    cost_ax = axes[0, 1]
    if any(r.get("total_method_wall_s") is not None for r in selected):
        lo, hi = cost_ax.get_ylim()
        cost_ax.set_ylim(min(lo, 580), max(hi, 630))
        cost_ax.axhline(600, color="#666666", linestyle="--", linewidth=0.9)
        cost_ax.text(0.02, 0.97, "虚线：根预算600 s", transform=cost_ax.transAxes,
                     va="top", fontsize=8, color="#666666")
    ablation_panel(axes[1, 0], rows, energy, "(c) 完整／去温限MILP：最终方案能耗", "能耗 / J")
    ablation_panel(axes[1, 1], rows, lambda r: value((r.get("maximum_peak_degC") or [None, None])[1]),
                   "(d) 最终方案峰温与原80°C温限", "峰温上界 / °C")
    peak_ax = axes[1, 1]
    if any(r.get("maximum_peak_degC") is not None for r in rows if r["method"] == "whole_milp"):
        lo, hi = peak_ax.get_ylim()
        peak_ax.set_ylim(min(lo, 78), max(hi, 82.5))
        peak_ax.axhline(80, color=UNSAFE, linestyle="--", linewidth=1)
        peak_ax.text(-0.35, 80, "原温限80°C", va="bottom", color=UNSAFE, fontsize=8)
    legend = [Line2D([0], [0], marker="o", color="none", markerfacecolor=FULL, markeredgecolor=FULL, label="完整温限方法／80°C复核通过"),
              Line2D([0], [0], marker="s", color="none", markerfacecolor=NO_LIMIT, markeredgecolor=NO_LIMIT, label="去温限 MILP／80°C复核通过"),
              Line2D([0], [0], marker="D", color="black", linewidth=1, markersize=4, label="SA：中位数与最小—最大范围")]
    visible = [r for r in rows if energy(r) is not None or r.get("total_method_wall_s") is not None or r.get("maximum_peak_degC")]
    if any(not r.get("rankable_80C") and r.get("common_80_C_feasible") is not False and short_status(r) != "异常" for r in visible):
        legend.append(Line2D([0], [0], marker="o", color="none", markerfacecolor="none", markeredgecolor=UNVERIFIED, label="空心：未独立确认"))
    if any(short_status(r) == "异常" for r in visible):
        legend.append(Line2D([0], [0], marker="^", color="none", markerfacecolor="none", markeredgecolor=UNVERIFIED, label="△：异常调用的已保存数值"))
    if any(r.get("common_80_C_feasible") is False for r in visible):
        legend.append(Line2D([0], [0], marker="x", color=UNSAFE, linestyle="none", label="×：原80°C条件超温"))
    fig.legend(handles=legend, loc="lower center", bbox_to_anchor=(0.52, 0.075), ncol=3, fontsize=8.6, frameon=False)
    fig.text(0.085, 0.035, "每点为一次独立600 s调用；SA标明全部种子，未运行／无完整方案不置零。超温能耗仅作诊断，不计安全上界。\n耗时点包含进程清理，600 s虚线对应方法根预算。峰温优先使用共同后验；未复核记录以空心标示。", fontsize=8.4, color="#555555")
    if str(summary.get("batch_state", "")).startswith("FIXTURE"):
        fig.text(0.5, 0.91, "人工绘图夹具，非实验数据", color=UNSAFE, ha="center", fontsize=11)
    return fig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--conditional", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    font = configure_fonts()
    summary = json.loads(args.summary.read_bytes())
    conditional = json.loads(args.conditional.read_bytes())
    args.out_dir.mkdir(parents=True, exist_ok=True)
    names = ("conditional_optima", "closure_comparison")
    targets = [args.out_dir / (name + suffix) for name in names for suffix in (".png", ".pdf")]
    if any(p.exists() for p in targets):
        raise SystemExit("Refusing to overwrite existing figure files")
    for name, figure in ((names[0], conditional_figure(conditional)), (names[1], comparison_figure(summary))):
        for suffix in (".png", ".pdf"):
            figure.savefig(args.out_dir / (name + suffix), dpi=220)
        plt.close(figure)
    print(json.dumps({"font": font, "files": list(map(str, targets)), "new_scientific_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
