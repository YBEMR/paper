"""Render Fig. 4-4 from the event CSV, or rebuild the CSV using --source.

The source is the repository root (or the archive's source directory) containing
research/kim_multidnn_search_trial. No simulator or research code is executed.
"""
import argparse
import csv
import hashlib
import io
import json
import tarfile
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from figure_style import BLUE, DATA, GRAY, TEAL, save, setup


CASE_LABELS = {
    "forward_flat_25C": "正序 · 原驻留",
    "forward_alternating_25C": "正序 · 交替驻留",
    "reverse_flat_25C": "逆序 · 原驻留",
    "reverse_alternating_25C": "逆序 · 交替驻留",
}
METHODS = {"M0": (GRAY, ":"), "M1": (BLUE, "--"), "M2": (TEAL, "-")}
EVENTS_CSV = DATA / "fig09_progress_events.csv"
FIELDS = (
    "run_id", "case", "method", "cap_s", "catalog_size", "event", "phase",
    "elapsed_s", "completed", "deployment",
)
ARCHIVE_SHA256 = "6087fe14cbada605d1aa1ccc171d53fdb0438c55efff8ef5a2ef26ecb50a65c4"


def read_archive(results):
    index = json.loads((results / "logs_index.json").read_bytes())
    stream = io.BytesIO()
    for part in index["parts"]:
        data = (results / part["name"]).read_bytes()
        assert len(data) == part["bytes"]
        assert hashlib.sha256(data).hexdigest() == part["sha256"], part["name"]
        stream.write(data)
    assert stream.tell() == index["bytes"]
    assert hashlib.sha256(stream.getbuffer()).hexdigest() == index["whole_sha256"] == ARCHIVE_SHA256
    stream.seek(0)
    return tarfile.open(fileobj=stream, mode="r:gz")


def extract_run(tar, metric):
    run_id = metric["id"]
    method = metric["method"]
    cap = int(metric["cap_s"])
    result = json.load(tar.extractfile(f"raw/{run_id}/result.json"))
    events = [json.loads(line) for line in tar.extractfile(f"raw/{run_id}/events.jsonl")]
    times = [event["t"] for event in events]
    assert times == sorted(times)
    events = [event for event in events if event["t"] <= cap]
    start, = [event for event in events if event["kind"] == "start_search"]
    assert start["case"]["id"] == metric["case"] and start["method"] == method
    assert len(start["domain"]) == len(set(start["domain"])) == 81
    assert result["status"] == metric["status"] and cap == 120
    phase = "constrained" if method == "M0" else "energy"
    completed = [e for e in events if e["kind"] == "deployment" and e["phase"] == phase]
    assert [e["completed"] for e in completed] == list(range(1, len(completed) + 1))
    assert [e["deployment"] for e in completed] == start["domain"][:len(completed)]
    assert len(completed) == int(metric["completed"]) == result["completed"]
    certificates = [e for e in events if e["kind"] == "certificate" and e["scope"] == "catalog"]
    if metric["certificate_s"]:
        certificate, = certificates
        assert len(completed) == certificate["n"] == 81
        assert certificate["t"] == float(metric["certificate_s"]) == result["certified_s"]
        assert certificate["t"] >= completed[-1]["t"] and method == "M2"
    else:
        assert not certificates and result["status"] == "DEADLINE"
    for event in completed + certificates:
        yield dict(zip(FIELDS, (
            run_id, metric["case"], method, cap, len(start["domain"]), event["kind"],
            event.get("phase", ""), event["t"], event.get("completed", len(completed)),
            event.get("deployment", ""),
        )))


def rebuild_csv(source):
    results = source / "research/kim_multidnn_search_trial/results"
    with (results / "run_metrics.csv").open(encoding="utf-8", newline="") as file:
        metrics = [row for row in csv.DictReader(file) if row["stage"] == "dev"]
    assert len(metrics) == 12
    assert {(m["case"], m["method"]) for m in metrics} == {
        (case, method) for case in CASE_LABELS for method in METHODS
    }
    with read_archive(results) as tar:
        rows = [row for m in sorted(metrics, key=lambda row: row["id"]) for row in extract_run(tar, m)]
    with EVENTS_CSV.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def plot():
    setup()
    groups = defaultdict(list)
    with EVENTS_CSV.open(encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            groups[row["case"], row["method"]].append(row)

    fig, axes = plt.subplots(2, 2, figsize=(7.6, 5.05), sharex=True, sharey=True)
    fig.subplots_adjust(left=.095, right=.985, top=.85, bottom=.12, wspace=.15, hspace=.35)
    for index, (case, label) in enumerate(CASE_LABELS.items()):
        axis = axes.flat[index]
        axis.set_title(f"（{'abcd'[index]}）{label}", loc="left", x=-.02, pad=4)
        axis.set_xlim(0, 130)
        axis.set_ylim(-3, 89)
        axis.set_xticks([0, 30, 60, 90, 120])
        axis.set_yticks([0, 20, 40, 60, 81])
        axis.spines["bottom"].set_bounds(0, 120)
        axis.spines["left"].set_bounds(0, 81)
        axis.grid(axis="y")
        for method, (color, dash) in METHODS.items():
            records = groups[case, method]
            completed = [r for r in records if r["event"] == "deployment"]
            certificates = [r for r in records if r["event"] == "certificate"]
            xs = [0, *(float(r["elapsed_s"]) for r in completed)]
            ys = [0, *(int(r["completed"]) for r in completed)]
            cap = int(records[0]["cap_s"])
            end = float(certificates[0]["elapsed_s"]) if certificates else cap
            axis.step(xs + [end], ys + [ys[-1]], where="post", color=color, ls=dash, lw=1.6)
            if certificates:
                axis.plot(end, ys[-1], "D", color=color, markersize=4.3, clip_on=False)
                axis.annotate(f"{end:.2f} s", (end, ys[-1]), xytext=(7, 0),
                              textcoords="offset points", va="center", color=color, fontsize=8)
            else:
                axis.text(end + 1.6, ys[-1], str(ys[-1]), color=color, fontsize=8, va="center")
    handles = [Line2D([], [], color=c, linestyle=s, linewidth=1.8, label=m)
               for m, (c, s) in METHODS.items()]
    handles.append(Line2D([], [], color=TEAL, marker="D", linestyle="none", markersize=4.3,
                          label="M2 全库认证"))
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.52, .997),
               ncol=4, handlelength=2.5, columnspacing=2.3)
    fig.supxlabel("自冷启动起的累计时间（s）", fontsize=9, x=.53, y=.02)
    fig.supylabel("累计完成部署数（个）", fontsize=9, x=.015, y=.49)
    save(fig, "fig09_progress")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="Optional directory containing research/")
    args = parser.parse_args()
    if args.source is not None:
        rebuild_csv(args.source)
    plot()
