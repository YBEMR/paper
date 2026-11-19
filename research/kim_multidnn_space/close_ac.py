"""Close exactly four named A/C cases with the frozen exhaustive evaluator."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter

HERE = Path(__file__).resolve().parent
AUDIT = HERE.parent / "kim_safety_repair_audit"
sys.path.insert(0, str(AUDIT))
import runner as audit
from design import cases, make_scenes
import numpy as np

BASE = "02f3f621cc9ce7f1cd991577388343fa906bbf56"
CASE_IDS = (
    "forward_flat_27p5C", "forward_alternating_25C",
    "reverse_flat_25C", "reverse_alternating_25C",
)


def check_freeze(commit):
    git = ["git", "-C", str(HERE.parents[1])]
    if len(commit) != 40:
        raise ValueError("Full preregistration commit required")
    parent = subprocess.check_output(git + ["rev-parse", commit + "^"], text=True).strip()
    if parent != BASE:
        raise ValueError("Preregistration must descend directly from the frozen result")
    relative = (HERE / "close_ac.py").relative_to(HERE.parents[1]).as_posix()
    frozen = subprocess.check_output(git + ["show", commit + ":" + relative])
    if frozen.replace(b"\r\n", b"\n") != Path(__file__).read_bytes().replace(b"\r\n", b"\n"):
        raise ValueError("Closure code differs from preregistration")
    subprocess.run(git + ["diff", "--quiet", BASE, "--",
                          "research/kim_safety_repair_audit", "research/kim_scene_dvfs_admission",
                          "research/kim_synthetic_platform_v1", "research/kim_case_b_freeze"], check=True)


def run_case(case, folder):
    folder.mkdir(parents=True, exist_ok=True)
    start = perf_counter()
    scenes = make_scenes(case)
    schedules, kwargs, scores, choices, rows, timing = audit.local_tables(scenes, case["ambient"])
    audit.put_csv(folder / "local.csv", rows)
    selected = audit.lowest(choices, "predicted_j")
    if selected is None:
        raise AssertionError("Registered safety control has no independent choice")
    mark = perf_counter()
    selected["physical"] = audit.replay_sequence(audit.PLATFORM, scenes, selected["deployment"],
                                                 selected["opps"], case["ambient"])
    timing["selected_replay_s"] = perf_counter() - mark
    original = json.loads((AUDIT / "raw" / "new" / case["id"] / "result.json").read_bytes())
    if selected["deployment"] != original["independent"]["deployment"]:
        raise AssertionError("Original selected deployment changed")
    if selected["code"] != original["independent"]["code"]:
        raise AssertionError("Original selected clocks changed")
    actual = selected["physical"]
    if not actual["feasible"] or actual["completed"] != 500:
        raise AssertionError("Original safety control failed")
    if abs(actual["energy_j"] - original["independent"]["physical"]["energy_j"]) > 1e-7:
        raise AssertionError("Frozen physical energy changed")
    oracle = audit.certify(scenes, case, schedules, kwargs, folder)
    if not oracle["optimality_proven"] or oracle["status"] != "SAFE_EXISTS":
        raise AssertionError("No globally certified minimum for the registered safe case")
    # Independent array-level confirmation of the exact minimizer and coverage.
    minima = []
    for deployment in "AC":
        solution = oracle["solutions"][deployment]
        if solution["method"] != "EXHAUSTIVE":
            raise AssertionError("Expected complete exhaustive A/C arrays")
        with np.load(folder / f"space_{deployment}.npz") as data:
            states, energy = data["status"], data["energy_j"]
            if states.size != 27**4 or np.count_nonzero(states == 3):
                raise AssertionError("Incomplete state coverage")
            if not np.array_equal(np.isnan(energy), states == 0):
                raise AssertionError("Deadline-only NaN accounting failed")
            safe = np.flatnonzero(states == 1)
            if len(safe):
                minimum = float(energy[safe].min())
                code = int(safe[np.flatnonzero(energy[safe] <= minimum + audit.EPS)[0]])
                minima.append(audit.choice(deployment, code, float(energy[code])))
    confirmation = audit.lowest(minima, "predicted_j")
    if (confirmation["deployment"], confirmation["code"]) != (oracle["deployment"], oracle["code"]):
        raise AssertionError("Global choice differs from independent array check")
    if abs(confirmation["predicted_j"] - oracle["energy_j"]) > 1e-7:
        raise AssertionError("Global minimum energy differs from physical replay")
    gap = actual["energy_j"] - oracle["energy_j"]
    if gap < -1e-7:
        raise AssertionError("Reference is more expensive than its feasible incumbent")
    info = dict(case=case, independent=selected, oracle=oracle, gap_j=gap,
                gap_percent=100 * gap / oracle["energy_j"], timing=timing,
                total_case_s=perf_counter() - start,
                local_thermal_integrations=sum(row["deadline_ok"] for row in rows),
                certificate_thermal_integrations=sum(row["deadline_ok"] for row in rows),
                independent_full_replays=1, optimal_full_replays=1)
    audit.put_json(folder / "result.json", info)
    return info


def write_report(rows, freeze, timing):
    lines = [
        "# A/C 有限候选集的四组最优差距收尾", "",
        "本次仅完成此前已经安全、但尚未求全局最优的四组工况。完成后结束当前 A/C 候选集合的反复价值验证。",
        "", "冻结结果基线为 `" + BASE + "`，本次方法预注册为 `" + freeze + "`。",
        "", "| 工况 | 独立选策连续能耗 J | 最优安全能耗 J | 差距 J | 差距 % | 全局最优部署与逐段频率 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(f"| {row['case']} | {row['independent_j']:.9f} | {row['optimum_j']:.9f} | "
                     f"{row['gap_j']:.9f} | {row['gap_percent']:.9f} | "
                     f"{row['optimum_deployment']} / {row['optimum_opps']} |")
    lines.extend([
        "", "相对最优差距定义为 `(独立选策连续能耗 − 最优安全能耗) / 最优安全能耗`。",
        "所有工况沿用 25 FPS、四应用各 125 次推理、40 ms 请求期限、10 s 服务和 40 ms 评价尾段。",
        "各选策及最优方案均须在原四节点连续物理评价器中完成全部请求并通过温限。",
        "", "| 工况 | 逻辑完整序列 | 期限失败 | 连续安全 | 连续超温 | 未决 | 共享前缀热评价 | 原核回退段数 | 编译 s | 搜索 s | 参考总计 s |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in rows:
        lines.append(f"| {row['case']} | {row['logical_sequences']} | {row['deadline_failed']} | "
                     f"{row['safe']} | {row['overtemp']} | {row['unresolved']} | {row['prefix_evaluations']} | "
                     f"{row['fallback_segment_replays']} | {row['compile_s']:.6f} | "
                     f"{row['search_only_s']:.6f} | {row['reference_total_s']:.6f} |")
    lines.extend([
        "", "搜索复用精确场景传递与共享前缀，并未把每个完整编码都重新积分整窗。每组另有 2 次完整物理重放，分别复核独立胜者和全局胜者；每次包含 4 段原核积分。",
        "每组另有 144 次独立入口的段级热评价及 144 次最低可达入口的段级证书评价。原核回退段数由参考求解器逐项记录。",
        f"单线程总用时 {timing['total_s']:.6f} s，含首次预热 {timing['warmup_s']:.6f} s；墙钟时间与运行机器及负载有关。",
        "", "每个工况的两个 NPZ 保存全部编码状态和能耗。对期限失败编码的能耗保存为空值，安全与超温编码均保留完整能耗。最优解能量和编码还通过独立数组最小值检查与原物理重放交叉核验。",
        "", "复现命令如下。", "", "```shell",
        "python -B close_ac.py --freeze " + freeze, "```", "",
        "[四组汇总](raw/closure/summary.csv) · [完整结果与物理重放](raw/closure/results.json) · [计时](raw/closure/timing.json)",
    ])
    (HERE / "closure.md").write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--out", type=Path, default=HERE / "raw" / "closure")
    args = parser.parse_args()
    check_freeze(args.freeze)
    args.out.mkdir(parents=True, exist_ok=True)
    start = perf_counter()
    audit.joint.warmup()
    warmup = perf_counter() - start
    indexed = {case["id"]: case for case in cases()}
    reports = []
    summary = []
    for name in CASE_IDS:
        info = run_case(indexed[name], args.out / name)
        info["freeze_commit"] = args.freeze
        audit.put_json(args.out / name / "result.json", info)
        reports.append(info)
        oracle = info["oracle"]
        solutions = list(oracle["solutions"].values())
        summary.append(dict(case=name, independent_deployment=info["independent"]["deployment"],
                            independent_opps=" ".join(info["independent"]["opps"]),
                            independent_j=info["independent"]["physical"]["energy_j"],
                            optimum_deployment=oracle["deployment"], optimum_opps=" ".join(oracle["opps"]),
                            optimum_j=oracle["energy_j"], gap_j=info["gap_j"], gap_percent=info["gap_percent"],
                            logical_sequences=oracle["logical_complete_space"],
                            safe=sum(s["safe"] for s in solutions),
                            overtemp=sum(s["overtemp"] for s in solutions),
                            deadline_failed=sum(s["deadline_failed"] for s in solutions),
                            unresolved=sum(s["unresolved"] for s in solutions),
                            prefix_evaluations=sum(s["prefix_thermal_evaluations"] for s in solutions),
                            fallback_segment_replays=sum(s["fallback_segment_replays"] for s in solutions),
                            local_thermal_integrations=info["local_thermal_integrations"],
                            certificate_thermal_integrations=info["certificate_thermal_integrations"],
                            complete_physical_replays=2,
                            search_only_s=sum(s["search_s"] for s in solutions),
                            compile_s=sum(s["compile_s"] for s in solutions),
                            reference_total_s=oracle["total_s"], total_case_s=info["total_case_s"]))
        print(name, "gap_j", info["gap_j"], flush=True)
    audit.put_json(args.out / "results.json", reports)
    audit.put_csv(args.out / "summary.csv", summary)
    timing = dict(warmup_s=warmup, total_s=perf_counter() - start,
                  cases=len(reports), threads=1, freeze_commit=args.freeze)
    audit.put_json(args.out / "timing.json", timing)
    write_report(summary, args.freeze, timing)


if __name__ == "__main__":
    main()
