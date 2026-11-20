"""Render the fixed-work and 120 s figures; use --trial to re-extract the source data."""
import argparse
import csv
import hashlib
import io
import json
import math
import tarfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

from figure_style import BLUE, DATA, GRAY, INK, TEAL, save, setup


METHODS = {"M0": GRAY, "M1": BLUE, "M2": TEAL}
CONDITIONS = {
    "forward_flat_25C": "正序\n原驻留",
    "forward_alternating_25C": "正序\n交替驻留",
    "reverse_flat_25C": "逆序\n原驻留",
    "reverse_alternating_25C": "逆序\n交替驻留",
}
COMPONENTS = {
    "startup_jit_s": ("启动、导入、校验及冷 JIT", "#A6BDCE"),
    "bounds_s": ("静态松下界", "#DEAE78"),
    "schedule_s": ("场景调度", "#73AA9F"),
    "compile_s": ("场景核构建", BLUE),
    "search_check_s": ("查键、搜索、复核与核对", "#8B7396"),
    "residual_s": ("未分项及退出回收", "#55616B"),
}
FIXED_CSV = DATA / "fig07_fixed.csv"
BUDGET_CSV = DATA / "fig08_budget.csv"


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)


def checked_logs(results):
    index = json.loads((results / "logs_index.json").read_text(encoding="utf-8"))
    parts = []
    for part in index["parts"]:
        blob = (results / part["name"]).read_bytes()
        assert hashlib.sha256(blob).hexdigest() == part["sha256"]
        parts.append(blob)
    joined = b"".join(parts)
    assert hashlib.sha256(joined).hexdigest() == index["whole_sha256"]
    return tarfile.open(fileobj=io.BytesIO(joined), mode="r:gz")


def read_events(lines, cap):
    return [r for line in lines if line.strip() and (r := json.loads(line))["t"] <= cap]


def fixed_row(metric, events):
    by_kind = {e["kind"]: e for e in events}
    stats = by_kind["certificate"]["stats"]
    wall = float(metric["wall_s"])
    parts = {
        "startup_jit_s": by_kind["imports_and_freeze"]["t"] + by_kind["cold_warmup"]["wall_s"],
        "bounds_s": stats["bounds_s"],
        "schedule_s": stats["schedule_s"],
        "compile_s": stats["compile_s"],
        "search_check_s": sum(stats.get(k, 0.0) for k in
                              ("key_s", "affine_search_s", "safe_replay_s", "archive_check_s")),
    }
    parts["residual_s"] = wall - sum(parts.values())
    assert all(v >= 0 for v in parts.values()) and math.isclose(sum(parts.values()), wall)
    assert int(metric["compiles"]) == stats["compiles"]
    assert by_kind["certificate"]["scope"] == "subset" and int(metric["completed"]) == 4
    return dict(run_id=metric["id"], method=metric["method"], case=metric["case"],
                completed=4, scene_compiles=stats["compiles"], scene_kernel_hits=int(metric["legal_hits"]),
                wall_s=wall, **parts, best_safe_j=metric["best_safe_j"],
                first_safe_s=metric["first_safe_s"], subset_certificate_s=metric["certificate_s"])


def budget_row(result, events, repeat, retry=False):
    phase = "constrained" if result["method"] == "M0" else "energy"
    completed = [e["deployment"] for e in events if e["kind"] == "deployment" and e["phase"] == phase]
    assert len(set(completed)) == len(completed) == result["completed"]
    cert = [e["t"] for e in events if e["kind"] == "certificate" and e["scope"] == "catalog"]
    assert cert == ([result["certified_s"]] if result["certified_s"] is not None else [])
    assert result["cap"] == 120 and result["status"] in {"DEADLINE", "PASS"}
    return dict(run_id=result["id"], stage=result["stage"], case=result["case"], repeat=repeat,
                method=result["method"], status=result["status"], retry=int(retry),
                budget_s=result["cap"], catalog_size=81, completed=len(completed),
                catalog_certificate_s=result["certified_s"])


def extract(trial):
    results = trial / "results"
    fixed, budget = [], []
    with checked_logs(results) as logs:
        for row in read_csv(results / "run_metrics.csv"):
            identifier = row["id"]
            events = read_events(logs.extractfile(f"raw/{identifier}/events.jsonl"), int(row["cap_s"]))
            if row["stage"] == "fixed":
                fixed.append(fixed_row(row, events))
                continue
            result = json.load(logs.extractfile(f"raw/{identifier}/result.json"))
            repeat = int(identifier.split("-")[2]) if row["stage"] == "holdout" else 1
            item = budget_row(result, events, repeat)
            assert item["completed"] == int(row["completed"])
            assert item["catalog_certificate_s"] == (float(row["certificate_s"]) if row["certificate_s"] else None)
            budget.append(item)
    retry_folder = results / "retry_h2_m1_20261119"
    audit = json.loads((retry_folder / "audit.json").read_text(encoding="utf-8"))
    retry = audit["result"]
    assert audit["settlement"]["status"] == retry["status"] == "DEADLINE"
    event_path = f"raw/{retry['id']}/events.jsonl"
    contents = (retry_folder / event_path).read_bytes()
    manifest = {entry["path"]: entry["sha256"] for entry in audit["raw_manifest"]}
    assert hashlib.sha256(contents).hexdigest() == manifest[event_path]
    budget.append(budget_row(retry, read_events(contents.splitlines(), 120), repeat=2, retry=True))
    assert len(fixed) == 2 and len(budget) == 24
    assert len({(r["case"], r["repeat"], r["method"]) for r in budget}) == 24
    assert not any(r["run_id"] == "hold-1-2-M1" for r in budget)
    write_csv(FIXED_CSV, fixed)
    write_csv(BUDGET_CSV, budget)


def bar_numbers(ax, rects, values, digits=0, suffix=None):
    for i, (rect, value) in enumerate(zip(rects, values)):
        label = f"{value:.{digits}f}" + (suffix[i] if suffix else "")
        ax.annotate(label, (rect.get_x() + rect.get_width() / 2, rect.get_height()),
                    xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", fontsize=8)


def plot_fixed():
    rows = sorted(read_csv(FIXED_CSV), key=lambda r: r["method"])
    methods = [r["method"] for r in rows]
    x = np.arange(len(rows))
    fig, (ax_count, ax_time) = plt.subplots(1, 2, figsize=(7.6, 3.8))
    fig.subplots_adjust(left=.095, right=.98, top=.89, bottom=.29, wspace=.42)
    ax_count.set_title("(a)  场景核构建次数")
    counts = [int(r["scene_compiles"]) for r in rows]
    bars = ax_count.bar(x, counts, width=.54, color=[METHODS[m] for m in methods])
    bar_numbers(ax_count, bars, counts)
    ax_count.set(ylim=(0, 315), ylabel="构建次数（次）")
    ax_count.set_yticks([0, 50, 100, 150, 200, 250, 300])
    ax_time.set_title("(b)  含冷启动的墙钟耗时")
    bottom = np.zeros(len(rows))
    for key, (label, color) in COMPONENTS.items():
        vals = np.array([float(r[key]) for r in rows])
        ax_time.bar(x, vals, width=.56, bottom=bottom, color=color, label=label)
        if key in {"startup_jit_s", "schedule_s", "compile_s"}:
            for i, value in enumerate(vals):
                ax_time.text(x[i], bottom[i] + value / 2, f"{value:.2f}", ha="center", va="center",
                             fontsize=8.2, color="white" if key == "compile_s" else INK)
        bottom += vals
    for i, r in enumerate(rows):
        ax_time.annotate(f"{float(r['wall_s']):.2f}", (x[i], bottom[i]),
                         xytext=(0, 3), textcoords="offset points", va="bottom", ha="center", fontsize=8)
    ax_time.set(ylim=(0, 24), yticks=[0, 5, 10, 15, 20], ylabel="墙钟耗时（s）")
    for ax in (ax_count, ax_time):
        ax.set(xticks=x, xticklabels=methods, xlim=(-.62, 1.62))
        ax.grid(axis="y")
        ax.tick_params(axis="x", length=0, pad=5)
    handles = [Patch(facecolor=color, label=label) for label, color in COMPONENTS.values()]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(.51, .035), ncols=3,
               handlelength=1.4, handletextpad=.55, columnspacing=2.1, labelspacing=.7)
    save(fig, "fig07_fixed")
    plt.close(fig)


def coverage(ax, rows, keys, labels):
    x = np.arange(len(keys))
    width = .25
    for j, (method, color) in enumerate(METHODS.items()):
        records = [rows[(case, repeat, method)] for case, repeat in keys]
        values = [int(r["completed"]) for r in records]
        bars = ax.bar(x + (j - 1) * width, values, width, color=color, edgecolor="white", linewidth=.45)
        bar_numbers(ax, bars, values, suffix=["*" if r["retry"] == "1" else "" for r in records])
    ax.set(xticks=x, xticklabels=labels, ylim=(0, 92), yticks=[0, 20, 40, 60, 81],
           ylabel="完成部署数（个）", xlim=(-.58, 3.58))
    ax.grid(axis="y")


def certificate(ax, rows, keys, labels):
    times = [float(rows[(case, repeat, "M2")]["catalog_certificate_s"]) for case, repeat in keys]
    x = np.arange(len(keys))
    bars = ax.bar(x, times, width=.53, color=TEAL)
    bar_numbers(ax, bars, times, digits=2)
    ax.set(xticks=x, xticklabels=labels, ylim=(0, 127), yticks=[0, 30, 60, 90, 120],
           ylabel="取得全库证书的时间（s）", xlim=(-.58, 3.58))
    ax.grid(axis="y")
    ax.axhline(120, lw=.85, color=GRAY, linestyle="--")
    ax.text(3.54, 116, "120 s 预算", va="top", ha="right", fontsize=7.4, color=GRAY)


def plot_budget():
    rows = {(r["case"], int(r["repeat"]), r["method"]): r for r in read_csv(BUDGET_CSV)}
    dev_keys = [(case, 1) for case in CONDITIONS]
    hold_keys = [(case, repeat) for case in ("H1", "H2") for repeat in (1, 2)]
    dev_labels = list(CONDITIONS.values())
    hold_labels = [f"{case}\n第 {repeat} 次" for case, repeat in hold_keys]
    fig, axes = plt.subplots(2, 2, figsize=(7.9, 5.75), gridspec_kw={"width_ratios": [1.14, 1]})
    fig.subplots_adjust(left=.091, right=.983, top=.86, bottom=.14, wspace=.34, hspace=.56)
    coverage(axes[0, 0], rows, dev_keys, dev_labels)
    certificate(axes[0, 1], rows, dev_keys, dev_labels)
    coverage(axes[1, 0], rows, hold_keys, hold_labels)
    certificate(axes[1, 1], rows, hold_keys, hold_labels)
    titles = ("(a)  开发工况下的部署覆盖", "(b)  开发工况下的 M2 认证耗时",
              "(c)  留出工况下的部署覆盖", "(d)  留出工况下的 M2 认证耗时")
    for ax, title in zip(axes.flat, titles):
        ax.set_title(title)
        ax.tick_params(axis="x", length=0, pad=4)
    handles = [Patch(facecolor=METHODS[m], label=label) for m, label in
               (("M0", "M0  原约束搜索"), ("M1", "M1  连续能耗松弛认证"), ("M2", "M2  松弛认证＋场景核复用"))]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.52, .991), ncols=3,
               handlelength=1.6, handletextpad=.5, columnspacing=2)
    fig.text(.091, .022, "* H2 第 2 次 M1 取已结算补跑。每次搜索覆盖上限为 81 个部署。", fontsize=8, color=GRAY)
    save(fig, "fig08_budget")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial", type=Path, help="Path to research/kim_multidnn_search_trial")
    args = parser.parse_args()
    if args.trial:
        extract(args.trial)
    setup()
    plot_fixed()
    plot_budget()
