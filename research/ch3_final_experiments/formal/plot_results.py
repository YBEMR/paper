"""Draw chapter 3 from accepted tables and traces. This module invokes no solver."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib.ticker import MaxNLocator
import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
TABLES = HERE / "tables"
DERIVED = HERE.parent / "derived"
FIGURES = HERE / "figures"
WIDTH = 150 / 25.4
TIE_J = 1e-9  # Absolute energy tie convention in derive.py.
CASES = ["forward_flat_25C", "forward_alternating_25C",
         "reverse_flat_25C", "reverse_alternating_25C"]
SCENES = ["正序原驻留", "正序交替驻留", "逆序原驻留", "逆序交替驻留"]
PRESSURE = ["reverse_flat_25C", "reverse_flat_27p5C"]
AMBIENTS = ["25 °C", "27.5 °C"]
METHODS = ["CT-Joint", "Kim-Adapt", "Kim-Adapt+SAFE", "Thermal-GA"]
NAMES = ["本文方法", *METHODS[1:]]
COLORS = ["#20242a", "#285984", "#1d7164", "#a25325"]
MARKERS = ["*", "o", "s", "D"]
RATE = LinearSegmentedColormap.from_list("fraction", ["#f6f7f7", "#b8d1cf", "#315f65"])
GRID = "#d8dddf"


def read(folder, name):
    return pd.read_csv(folder / name, encoding="utf-8-sig", float_precision="round_trip")


def style():
    fonts = {f.name for f in font_manager.fontManager.ttflist}
    cjk = next((name for name in ("SimSun", "Noto Serif CJK SC", "Source Han Serif SC",
                                   "Microsoft YaHei") if name in fonts), None)
    if not cjk:
        raise RuntimeError("Install SimSun or Noto Serif CJK SC to render Chinese labels.")
    plt.rcParams.update({
        "font.family": cjk, "font.size": 9, "xtick.labelsize": 8.5, "ytick.labelsize": 8.5,
        "axes.unicode_minus": False, "axes.spines.top": False, "axes.spines.right": False,
        "axes.linewidth": .65, "axes.edgecolor": "#4b5256", "xtick.major.size": 3,
        "ytick.major.size": 3, "legend.frameon": False, "axes.axisbelow": True,
        "svg.fonttype": "none", "svg.hashsalt": "ch3-accepted-tables",
        "pdf.fonttype": 42, "path.simplify": False, "savefig.facecolor": "white",
    })


def save(fig, letter):
    FIGURES.mkdir(exist_ok=True)
    for ext in ("svg", "pdf", "png"):
        metadata = {"Date": None} if ext == "svg" else {"CreationDate": None} if ext == "pdf" else {}
        fig.savefig(FIGURES / f"fig{letter}.{ext}", dpi=450, metadata=metadata)
    plt.close(fig)


def panel(ax, title):
    ax.set_title(title, loc="left", fontsize=9, pad=4)


def energy_figure(pressure):
    letter = "G" if pressure else "A"
    data = read(TABLES, f"fig{letter}.csv")
    cases, labels = (PRESSURE, AMBIENTS) if pressure else (CASES, SCENES)
    second = ("margin_c", "热裕量 / °C", "热裕量") if pressure else ("gap_pct", "最优差距 / %", "同域最优差距")
    fig, axes = plt.subplots(2, 1, sharex=True, figsize=(WIDTH, 3.75))
    fig.subplots_adjust(left=.126, top=.95, right=.984, bottom=.18, hspace=.36)
    for ax, (field, ylabel, title) in zip(axes, [
        ("safe_energy_j", "系统能耗 / J", "(a) 全窗安全方案能耗"),
        (second[0], second[1], "(b) " + second[2]),
    ]):
        panel(ax, title)
        for m, method in enumerate(METHODS):
            for j, case in enumerate(cases):
                rows = data[(data["case"] == case) & (data.method == method)
                            & (data.outcome == "SAFE")].sort_values("seed")
                if rows.empty:
                    continue
                center = j + (m - 1.5) * .175
                offset = np.linspace(-.048, .048, len(rows)) if len(rows) > 1 else [0.]
                ax.scatter(center + np.asarray(offset), rows[field], marker=MARKERS[m],
                           s=45 if m == 0 else 16, facecolor=COLORS[m] if m in (0, 3) else "white",
                           edgecolor=COLORS[m], linewidth=.8, zorder=3)
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", color=GRID, linewidth=.45)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=4))
        ax.margins(y=.16)
        ax.ticklabel_format(axis="y", useOffset=False)
    axes[-1].set_xticks(range(len(cases)), labels)
    axes[-1].set_xlim(-.49, len(cases) - .51)
    handles = [Line2D([], [], marker=mark, linestyle="none", markeredgecolor=color,
                      markerfacecolor=color if i in (0, 3) else "white", markersize=6)
               for i, (color, mark) in enumerate(zip(COLORS, MARKERS))]
    fig.legend(handles, NAMES, loc="lower center", ncol=4, fontsize=8, handletextpad=.35,
               columnspacing=1.3, bbox_to_anchor=(.52, .003))
    save(fig, letter)


def optimal_hits():
    rows = read(TABLES, "run_results.csv")
    main = rows[(rows.group == "AB") & (rows.domain == 81)]
    results = []
    for case in CASES:
        case_rows = main[main["case"] == case]
        ref, = case_rows.loc[(case_rows.method == METHODS[0]) &
                             (case_rows.outcome == "SAFE"), "safe_energy_j"]
        for method in METHODS[1:]:
            runs = case_rows[case_rows.method == method]
            if sorted(runs.seed.tolist()) != list(range(20261121, 20261126)):
                raise ValueError(f"Seed mismatch in {case} / {method}")
            if not (runs.exact_energy_j == ref).all():
                raise ValueError(f"Reference mismatch in {case} / {method}")
            safe = runs.outcome == "SAFE"
            hits = safe & ((runs.safe_energy_j - ref).abs() <= TIE_J)
            results.append(dict(case=case, domain=81, method=method, n=len(runs), safe=int(safe.sum()),
                                optimal_hits=int(hits.sum()), exact_energy_j=ref, absolute_tie_j=TIE_J,
                                hit_seeds="|".join(str(int(s)) for s in runs.loc[hits, "seed"])))
    table = pd.DataFrame(results)
    table.to_csv(TABLES / "figB_optimal_hits.csv", index=False, encoding="utf-8-sig", lineterminator="\n")
    return table


def count_figure(pressure):
    data = read(TABLES, "figF.csv") if pressure else optimal_hits()
    cases, labels = (PRESSURE, AMBIENTS) if pressure else (CASES, SCENES)
    methods = METHODS if pressure else METHODS[1:]
    fig, ax = plt.subplots(figsize=(WIDTH, 1.72 if pressure else 1.55))
    fig.subplots_adjust(left=.235, right=.985, bottom=.19, top=.985)
    for i, method in enumerate(methods):
        for j, case in enumerate(cases):
            row = data[(data.method == method) & (data["case"] == case)].iloc[0]
            count = int(row["safe" if pressure else "optimal_hits"])
            n = int(row.n)
            reference = method == METHODS[0]
            ratio = count / n
            ax.add_patch(Rectangle((j-.5, i-.5), 1, 1, facecolor="#e5e9eb" if reference else RATE(ratio),
                                   edgecolor="white", linewidth=1.2))
            ax.text(j, i, "已证安全" if reference else f"{count}/{n}", ha="center", va="center",
                    fontsize=10, color="white" if not reference and ratio >= .8 else "#202629")
    ax.set(xlim=(-.5, len(cases)-.5), ylim=(len(methods)-.5, -.5))
    ax.set_xticks(range(len(cases)), labels)
    ax.set_yticks(range(len(methods)), NAMES if pressure else methods)
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    save(fig, "F" if pressure else "B")


def figure_c():
    archive = read(DERIVED, "temperature_traces.csv")
    peaks = read(DERIVED, "peak_certificates.csv")
    trace = read(HERE / "raw/figureC", "samples.csv")
    cert = json.loads((HERE / "raw/figureC/certificate.json").read_bytes())["physical"]
    fig, (top, bottom) = plt.subplots(2, 1, sharex=True, figsize=(WIDTH, 3.8))
    fig.subplots_adjust(left=.115, right=.957, top=.948, bottom=.14, hspace=.42)
    panel(top, "(a) 部署 C，四场景均为 HHH")
    panel(bottom, "(b) 部署 C，频率依次为 LLL、LLL、LHL、LHL")
    for mode, label, color, line in [
        ("continuous", "连续继承", COLORS[1], "-"), ("independent", "场景重置", COLORS[3], "--")
    ]:
        d = archive[(archive.node == "gpu") & (archive.eval_mode == mode) &
                    (archive.sample_type == "archived_sample")]
        peak = peaks[(peaks.solution_id == d.solution_id.iloc[0]) & (peaks.eval_mode == mode)].iloc[0]
        top.plot(d.t_s, d.temperature_c, color=color, ls=line, lw=1.15,
                 label=f"{label}  {peak.peak_upper_c:.2f} °C")
    bottom.plot(trace.t_ns / 1e9, trace.gpu_c, color=COLORS[2], lw=1.05,
                label=f"连续继承  {max(cert['peak_upper_c']):.2f} °C")
    for ax in (top, bottom):
        for row in cert["scene_rows"][1:]:
            ax.axvline(row["start_ns"] / 1e9, lw=.6, ls=":", color="#858e93")
        ax.axhline(80, color="#46494c", lw=.7, ls="-.")
        ax.text(.15, 81.6, "80 °C 温限", fontsize=8)
        ax.set(ylim=(25, 90), xlim=(0, 10.04), ylabel="GPU 温度 / °C")
        ax.set_yticks([30, 50, 70, 90])
        ax.legend(loc="upper left", bbox_to_anchor=(.008, .77), fontsize=8,
                  handlelength=1.6, frameon=True, facecolor="white", edgecolor="none",
                  framealpha=1, borderpad=.2)
    bottom.set_xticks([0, 2.48, 5, 7.48, 10.04], ["0", "2.48", "5.00", "7.48", "10.04"])
    bottom.set_xlabel("时间 / s")
    save(fig, "C")


def figure_d():
    reset = read(DERIVED, "reset_confusion.csv")
    pressure = read(DERIVED, "pressure_classification.csv").set_index(["instance_id", "deployment"])
    fig, (left, right) = plt.subplots(1, 2, figsize=(WIDTH, 2.1), gridspec_kw={"width_ratios": [1, 1.75]})
    fig.subplots_adjust(left=.09, right=.99, top=.87, bottom=.21, wspace=.69)
    panel(left, "(a) 重置评价误收率")
    bars = left.bar(range(3), reset.false_accept_pct, width=.55, color=[COLORS[1], COLORS[1], "#667276"])
    left.bar_label(bars, fmt="%.2f", fontsize=8, padding=2)
    left.set_xticks(range(3), ["A", "C", "A+C"])
    left.set(ylim=(0, 5.7), ylabel="误收率 / %", xlabel="部署")
    left.set_yticks([0, 2, 4])
    left.grid(axis="y", color=GRID, lw=.45)
    panel(right, "(b) 连续评价的安全数 / 满足期限数")
    cases = ["forward_alternating_27p5C", "reverse_flat_27p5C", "reverse_alternating_27p5C"]
    deps = ["A", "C", "D001", "D015"]
    for i, case in enumerate(cases):
        for j, dep in enumerate(deps):
            r = pressure.loc[(case, dep)]
            ratio = r.safe / r.deadline_legal
            right.add_patch(Rectangle((j-.5, i-.5), 1, 1, facecolor=RATE(ratio),
                                      edgecolor="white", linewidth=1))
            right.text(j, i, f"{r.safe:,}\n/{r.deadline_legal:,}", fontsize=8, linespacing=1.0,
                       ha="center", va="center", color="white" if ratio >= .8 else "#202629")
    right.set(xlim=(-.5, 3.5), ylim=(2.5, -.5), xlabel="部署")
    right.set_xticks(range(4), deps)
    right.set_yticks(range(3), ["正序交替", "逆序原驻留", "逆序交替"])
    right.tick_params(length=0, pad=2)
    for spine in right.spines.values():
        spine.set_visible(False)
    save(fig, "D")


def figure_e():
    table = read(DERIVED, "ablation_results.csv").set_index("ablation_id")
    fig, ax = plt.subplots(figsize=(WIDTH, 2.25))
    fig.subplots_adjust(left=.11, right=.985, top=.95, bottom=.25)
    for positions, prefix in zip(([0, 1], [2.6, 3.6]), ["FixA", "Select81"]):
        for x, policy, face, hatch in zip(positions, ["Static", "Scene"],
                                          ["#b5c6d3", "#4f817c"], ["", "///"]):
            r = table.loc[f"{prefix}-{policy}-DVFS"]
            ax.bar(x, r.best_safe_j, width=.72, facecolor=face, hatch=hatch,
                   edgecolor="#37484e", linewidth=.6)
            ax.text(x, r.best_safe_j+1.1, f"{r.best_safe_j:.3f}", ha="center", fontsize=9)
            ax.text(x, 4, f"{r.delta_pct:.2f}%", ha="center", fontsize=8,
                    bbox=dict(facecolor="white", edgecolor="none", pad=1.2))
    ax.set_xticks([0, 1, 2.6, 3.6], ["整窗同频", "逐场景调频"]*2)
    for x, label in ((.5, "固定部署 A"), (3.1, "81 个部署可选")):
        ax.text(x, -.205, label, transform=ax.get_xaxis_transform(), ha="center", fontsize=9)
    ax.set(ylim=(0, 56), ylabel="最低安全能耗 / J")
    ax.set_yticks([0, 10, 20, 30, 40, 50])
    ax.grid(axis="y", color=GRID, lw=.45)
    save(fig, "E")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--only-c", action="store_true")
    args = parser.parse_args()
    style()
    figure_c()
    if not args.only_c:
        energy_figure(False)
        count_figure(False)
        figure_d()
        figure_e()
        count_figure(True)
        energy_figure(True)
