"""Plot two archived thesis figures. Optional --source points to a checkout's research directory."""
import argparse
import csv
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from figure_style import BLUE, DATA, GRAY, ORANGE, RED, TEAL, save, setup


DOMAINS = ("CPU", "GPU", "DLA")
NODES = ("cpu", "gpu", "dla0", "dla1")
CASE = "10s_25fps_25C_on_base"
POWER_FILE = DATA / "fig02_power.csv"
TRACE_FILE = DATA / "fig04_temperature.csv"
CERT_FILE = DATA / "fig04_peak_certificates.csv"


def read_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_rows(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)


def extract_power(platform):
    clock = platform["clock"]
    static = platform["power"]
    service = platform["service"]
    reference = platform["thermal"]["reference_C"]
    rows = []
    for domain in DOMAINS:
        freq = clock["mhz"][domain]
        volts = clock["volt"][domain]
        for i, level in enumerate(clock["levels"]):
            factor = (freq[i] / freq[-1]) * (volts[i] / volts[-1]) ** 2
            idle = static["idle_by_domain_W"][domain][i]
            slope = static["temp_slope_domain_W_K"][domain][i]
            leakage = (30 - reference) * slope
            activity = service[domain]
            row = dict(domain=domain, level=level, freq_MHz=freq[i], voltage_V=volts[i],
                       idle_domain_25C_W=idle, slope_domain_W_per_K=slope,
                       temp_increment_domain_30C_W=leakage, static_domain_30C_W=idle + leakage,
                       active_increment_W="", cpu_pre_single_core_increment_W="",
                       cpu_post_single_core_increment_W="")
            if domain == "CPU":
                row["cpu_pre_single_core_increment_W"] = activity["pre_active_W_H"] * factor
                row["cpu_post_single_core_increment_W"] = activity["post_active_W_H"] * factor
            else:
                row["active_increment_W"] = activity["active_W_H"] * factor
            rows.append(row)
    write_rows(POWER_FILE, rows)


def extract_traces(research):
    raw = research / "kim_synthetic_platform_v1" / "raw"
    trace_rows = [r for r in read_rows(raw / "traces.csv")
                  if r["case_id"] == CASE and r["deployment"] == "C" and r["opp"] == "HHH"]
    assert len(trace_rows) == 413
    write_rows(TRACE_FILE, trace_rows)

    records = []
    for r in read_rows(raw / "candidates.csv"):
        if (r["case_id"], r["deployment"], r["opp"]) != (CASE, "C", "HHH"):
            continue
        for node in NODES:
            records.append(dict(ambient_C=25, scene_order="forward", dwell="original", window_s=r["window_s"],
                                deployment="C", code="", sequence="HHH/HHH/HHH/HHH",
                                mode=r["mode"], thermal_status=r["thermal_status"],
                                deadline_ok=r["deadline_ok"], required=r["required"], completed=r["completed"],
                                energy_J=r["energy_j"], min_deadline_slack_ms=r["min_slack_ms"], node=node,
                                peak_lower_C=r[f"peak_lo_{node}_c"], peak_upper_C=r[f"peak_{node}_c"]))

    path = research / "kim_multidnn_expansion/raw/expanded/forward_flat_25C/deployment_D001.json"
    record = json.loads(path.read_text(encoding="utf-8"))["joint"]
    replay = record["physical"]
    assert record["code"] == 448 and replay["thermal_status"] == "SAFE"
    assert replay["fully_replayed"] and replay["completed"] == replay["required"] == 500
    for i, node in enumerate(NODES):
        records.append(dict(ambient_C=25, scene_order="forward", dwell="original",
                            window_s=replay["scene_rows"][-1]["end_ns"] / 1e9,
                            deployment="D001", code=record["code"], sequence="/".join(record["opps"]),
                            mode="continuous", thermal_status=replay["thermal_status"],
                            deadline_ok=replay["deadline_ok"], required=replay["required"],
                            completed=replay["completed"], energy_J=replay["energy_j"],
                            min_deadline_slack_ms=replay["min_slack_ms"], node=node,
                            peak_lower_C=replay["peak_lower_c"][i], peak_upper_C=replay["peak_upper_c"][i]))
    assert len(records) == 12
    write_rows(CERT_FILE, records)


def draw_power():
    rows = read_rows(POWER_FILE)
    fig, axes = plt.subplots(1, 3, figsize=(7.75, 3.47))
    fig.subplots_adjust(left=.075, right=.986, top=.86, bottom=.355, wspace=.36)
    for j, (axis, domain) in enumerate(zip(axes, DOMAINS)):
        group = [r for r in rows if r["domain"] == domain]
        frequencies = [float(r["freq_MHz"]) for r in group]
        def line(field, color, marker, ls):
            return axis.plot(frequencies, [float(r[field]) for r in group], color=color, marker=marker,
                             linestyle=ls, lw=1.75, markersize=5, markerfacecolor="white",
                             markeredgewidth=1.25)[0]
        axis.set_title(f"({chr(97+j)})  {domain}")
        if domain == "CPU":
            active = line("cpu_pre_single_core_increment_W", BLUE, "o", "-")
            post = line("cpu_post_single_core_increment_W", TEAL, "^", "-.")
        else:
            line("active_increment_W", BLUE, "o", "-")
        static = line("static_domain_30C_W", ORANGE, "s", "--")
        axis.set_xticks(frequencies, [r["level"] + "\n" + r["freq_MHz"] for r in group], fontsize=8)
        axis.margins(x=.15)
        ticks = [[0, .5, 1, 1.5], [0, 1, 2, 3, 4, 5], [0, 1, 2, 3, 4]][j]
        axis.set_yticks(ticks)
        axis.set_ylim(0, ticks[-1])
        axis.grid(axis="y")
    axes[0].set_ylabel("模型功率（W）")
    fig.text(.5, .182, "频档及对应频率（MHz）", ha="center", fontsize=9)
    fig.legend([active, post, static],
               ["活动增量（CPU 为前处理）", "CPU 后处理活动增量", "30 °C 域静态功率（含漏电增量）"],
               loc="lower center", ncol=3, bbox_to_anchor=(.52, .081), columnspacing=1.5,
               handlelength=2.6, borderaxespad=0)
    fig.text(.5, .027, "CPU 活动增量按单核计算。DLA 活动增量按单设备计算，静态功率按两个设备的共享频域合计。",
             ha="center", fontsize=8, color=GRAY)
    save(fig, "fig02_power")
    plt.close(fig)


def draw_traces():
    rows = read_rows(TRACE_FILE)
    certs = read_rows(CERT_FILE)
    independent = [r for r in rows if r["mode"] == "independent"]
    continuous = [r for r in rows if r["mode"] == "continuous"]
    assert len(independent) == 209 and len(continuous) == 204
    times = [float(r["t_s"]) for r in independent]
    resets = [times[i] for i in range(1, len(times)) if times[i] == times[i-1]]
    assert len(resets) == 3 and all(math.isclose(x, y) for x, y in zip(resets, (2.48, 5., 7.48)))
    breaks = [0., *resets, times[-1]]

    fig, axes = plt.subplots(2, 2, figsize=(7.75, 5.65), sharex=True, sharey=True)
    fig.subplots_adjust(left=.088, right=.973, top=.898, bottom=.169, hspace=.43, wspace=.16)
    fig.text(.522, .965, "25 °C 环境  ·  正序原驻留  ·  部署 C 全程 HHH", ha="center", fontsize=9, color=GRAY)
    for j, (axis, node) in enumerate(zip(axes.flat, NODES)):
        axis.set_title(f"({chr(97+j)})  {node.upper()}", pad=7)
        axis.grid(axis="y")
        for t in resets:
            axis.axvline(t, color=GRAY, linewidth=.7, alpha=.6, linestyle=":")
        threshold = axis.axhline(80, color=RED, linestyle=(0, (5, 3, 1, 3)), linewidth=.9)
        for k in range(4):
            axis.text((breaks[k]+breaks[k+1])/2, 83.9, f"SC{k}", va="center", ha="center",
                      fontsize=7.5, color=GRAY)
        keep = axis.plot([float(r["t_s"]) for r in continuous], [float(r[node+"_c"]) for r in continuous],
                         color=BLUE, linewidth=1.8, solid_capstyle="round")[0]
        reset = axis.plot(times, [float(r[node+"_c"]) for r in independent], color=ORANGE,
                          linewidth=1.4, linestyle=(0, (4, 2)), dash_capstyle="butt")[0]
        axis.set_xlim(0, 10.04)
        axis.set_ylim(27, 87)
        axis.set_xticks(breaks, ["0", "2.48", "5.00", "7.48", "10.04"])
        axis.set_yticks([30, 40, 50, 60, 70, 80])
        if node == "gpu":
            gpu = {r["mode"]:r for r in certs if r["deployment"] == "C" and r["node"] == "gpu"}
            assert float(gpu["continuous"]["peak_lower_C"]) > 80
            assert float(gpu["independent"]["peak_upper_C"]) < 80
    fig.supylabel("节点温度（°C）", x=.015, y=.525, fontsize=9)
    fig.text(.523, .089, "观测窗时间（s）", ha="center", fontsize=9)
    boundary = Line2D([], [], color=GRAY, linestyle=":", linewidth=1)
    fig.legend([keep, reset, threshold, boundary],
               ["连续传温", "独立重置至 30 °C", "温限 80 °C", "场景边界"],
               loc="lower center", bbox_to_anchor=(.52, .004), ncol=4, columnspacing=1.8,
               handlelength=2.7)
    save(fig, "fig04_temperature")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="re-extract data from repository research directory")
    args = parser.parse_args()
    if args.source:
        platform_file = args.source / "kim_synthetic_platform_v1/platform.json"
        extract_power(json.loads(platform_file.read_text(encoding="utf-8")))
        extract_traces(args.source)
    setup()
    draw_power()
    draw_traces()
