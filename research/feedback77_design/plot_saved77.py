"""Render saved CSV evidence with visible markers; no solver or thermal calls."""
from pathlib import Path
import csv
import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RUN = Path(__file__).resolve().parents[1] / "matlab_config_value_src/feedback77_reports/frozen_20260928_172132_129"
OUT = RUN / "plots"
OUT.mkdir(exist_ok=True)


def table(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


summary = table(RUN / "summary.csv")
for i in range(1, 11):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    fig.suptitle(summary[2*(i-1)]["case_id"], fontsize=13)
    all_values = []
    for j, (method, color, marker) in enumerate(
            [("no_good", "#2166ac", "o"), ("thermal_row", "#d95f02", "s")], 1):
        r = summary[2*(i-1)+j-1]
        bt = table(RUN / f"bounds_units_{i:02d}_{j:02d}.csv")
        st = table(RUN / f"solver_trace_units_{i:02d}_{j:02d}.csv")
        safe = [(float(t["elapsed_s"]), float(t["safe_upper_units"])*.0625)
                for t in bt if math.isfinite(float(t["safe_upper_units"]))]
        if safe:
            axes[0].plot(*zip(*safe), color=color, marker=marker, markersize=5,
                         drawstyle="steps-post", label=method)
            lower = float(r["first_safe_s"])
            upper = float(r["first_safe_upper_s"])
            axes[0].errorbar(lower, safe[0][1], xerr=[[0], [upper-lower]],
                            fmt="none", ecolor=color, capsize=4)
            all_values.extend(y for _, y in safe)
        else:
            axes[0].plot([], [], color=color, marker=marker, label=method + ": no safe U")
        axes[1].plot([float(t["elapsed_s"]) for t in bt],
                     [float(t["certified_L0_units"])*.0625 for t in bt],
                     color=color, linestyle="--", label=method + " independent L0")
        reported = [(float(t["elapsed_s"]), float(t["solver_lower_units"])*.0625)
                    for t in st if math.isfinite(float(t["solver_lower_units"]))]
        if reported:
            axes[1].plot(*zip(*reported), color=color, marker=marker, markersize=5,
                         linestyle=":", label=method + " solver-reported")
    axes[0].set_title("Safe upper bound (caps: first-safe time interval)")
    axes[1].set_title("Independent lower bound vs. internal reports")
    if not all_values:
        axes[0].text(.5, .5, "No safe witness\nSolver-reported infeasible only",
                     ha="center", va="center", transform=axes[0].transAxes)
        axes[0].set_xlim(0, max(float(r["elapsed_s"]) for r in summary[2*(i-1):2*i]))
        axes[0].set_ylim(0, 1)
        axes[0].set_yticks([])
    else:
        lo, hi = min(all_values), max(all_values)
        axes[0].set_ylim(lo-.2, hi+.2)
    for ax in axes:
        ax.set_xlabel("Enclosing elapsed time, lower estimate (s)")
        ax.set_ylabel("System energy (mJ)")
        ax.grid(alpha=.2)
        ax.legend(fontsize=8, loc="best")
    fig.tight_layout()
    fig.savefig(OUT / f"bounds_{i:02d}.png", dpi=150)
    plt.close(fig)
print("Rendered 10 saved-evidence figures; no new solving.")
