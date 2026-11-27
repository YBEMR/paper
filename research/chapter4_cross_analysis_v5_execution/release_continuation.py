"""Collect the closed v5 continuation, all physical attempts and byte-verified raw evidence."""
import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import shutil
from statistics import median
import sys
import tempfile

from attempt_inventory import attempts, read


def table(path):
    with path.open(encoding="utf8", newline="") as f:
        return list(csv.DictReader(f))


def group_name(path):
    for key in ("pools", "cells"):
        if key in path.parts:
            case = path.parts[path.parts.index(key) + 1].split("_")[0]
            if case not in ("D1", "D2", "F1", "F2"):
                raise ValueError(f"Unexpected evidence group in {path}")
            return case
    return "metadata"


def pack_raw(run, repo, dest):
    sys.path.insert(0, str(repo / "research/chapter3_final_evaluation/analysis"))
    import archive_batch as codec
    codec.OUT, codec.DEST = run, dest
    dest.mkdir()
    groups = defaultdict(list)
    for name in ("formal", "restart_01", "continuation_02", "continuation_03", "continuation_04", "smoke"):
        for path in (run / name).rglob("*"):
            if path.is_file():
                groups[group_name(path.relative_to(run))].append(path)
    for name in ("plan.json", "check.json", "interruption_review_01.json", "formal_console.log",
                 "continuation_03_console.log", "d1_c103_retry_authorization.json"):
        path = run / name
        if path.is_file():
            groups["metadata"].append(path)
    manifest = {}
    for name, files in sorted(groups.items()):
        manifest[name] = codec.pack(name, files)
        codec.verify_archive(name, manifest[name])
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf8", newline="\n")
    return sum(group["files"] for group in manifest.values())


def interval_text(rows, key):
    values = [float(r[key]) for r in rows]
    return f"{median(values):.4f} [{min(values):.4f}, {max(values):.4f}]"


def mechanism_summary(analysis, pairs, cases):
    paired = {(r["case"], r["seed"]) for r in pairs}
    rounds = [r for r in table(analysis / "round_mechanisms.csv") if (r["case"], r["seed"]) in paired]
    matches = [r for r in table(analysis / "matched_rounds.csv") if r["pair"] == "CD" and (r["case"], r["seed"]) in paired]
    lines = ["## 实际补偿与匹配轮次", "",
             "只统计 C/D 两端均有完整证书的种子。B、D 两列依次给出选中补偿请求、确实改动配置、跨场景改动的次数。同一请求在不同轮次重复发生时逐轮计数。", "",
             "| 工况 | B 选中 / 改动 / 跨场景 | D 选中 / 改动 / 跨场景 | C/D 匹配轮数 | 普通邻域外有实际改动的匹配轮数 | 双侧均达时限的匹配轮数 |",
             "|---|---:|---:|---:|---:|---:|"]
    for case in cases:
        counts = []
        for arm in ("B", "D"):
            group = [r for r in rounds if r["case"] == case and r["arm"] == arm]
            fields = ("selected_compensators", "realized_compensators", "cross_scene_realized")
            counts.append(" / ".join(str(sum(int(r[k]) for r in group)) for k in fields) if group else "—")
        same = [r for r in matches if r["case"] == case]
        outside = sum(bool(r["realized_outside_ordinary"]) for r in same)
        time_limited = sum(r["ordinary_solver"] == r["feedback_solver"] == "TIME_LIMIT" for r in same)
        lines.append(f"| {case} | {counts[0]} | {counts[1]} | {len(same)} | {outside} | {time_limited} |")
    lines.extend(["", "匹配要求轮前计划、请求目标和邻域大小相同。双侧均达时限的轮次只能比较各自在截止前找到的解。逐轮记录见 [round_mechanisms.csv](round_mechanisms.csv) 和 [matched_rounds.csv](matched_rounds.csv)。", ""])
    return lines


def main(run, repo, out):
    run, repo, out = run.resolve(), repo.resolve(), out.resolve()
    analysis = (run / ("continuation_04" if (run / "continuation_04").exists() else "continuation_03")) / "analysis"
    audit = read(analysis / "audit.json")
    end = read(analysis.parent / "formal/batch_end.json")
    missing = end["missing"]
    if audit["audited_CD"] != 24 - len(missing) or audit["audited_AB_raw"] != 24 or (
            not missing and audit["outcome"] != "PASS") or (missing and audit["outcome"] != "INCOMPLETE_OR_UNVERIFIED"):
        raise ValueError("Archive audit does not agree with the batch closure")
    if out.is_relative_to(run):
        raise ValueError("Release must be outside the original evidence")
    pairs = table(analysis / "paired.csv")
    scope = [(r["case"], int(r["seed"])) for r in pairs]
    cases = ("D1", "D2", "F1", "F2")
    expected = {(c, s) for c in cases for s in (101, 102, 103) if
                all(f"{c}_{method}_T3_{s}" not in missing for method in ("AB", "Proposed"))}
    if len(scope) != audit["complete_pairs"] or len(scope) != len(expected) or set(scope) != expected:
        raise ValueError("Pair inventory changed")
    runs = attempts(run, closed=True)
    complete = [a for a in runs if a["status"] == "COMPLETE"]
    lost = [a for a in runs if a["status"] == "NO_RECEIPT"]
    failed = Counter(a["status"] for a in runs if a["status"] not in ("COMPLETE", "NO_RECEIPT"))
    if len(complete) != audit["audited_CD"]:
        raise ValueError("Completed attempts disagree with audited endpoints")
    out.mkdir(exist_ok=False, parents=True)
    for path in sorted(analysis.iterdir()):
        if path.is_file():
            shutil.copyfile(path, out / path.name)
    with (out / "attempts.csv").open("x", newline="", encoding="utf8") as f:
        writer = csv.DictWriter(f, fieldnames=runs[0].keys(), lineterminator="\n")
        writer.writeheader()
        for r in runs:
            writer.writerow({**r, "copies": json.dumps(r["copies"])})
    nfiles = pack_raw(run, repo, out / "archive")
    lines = ["# 第四章 A–E 交叉验证", "",
        f"四个工况共登记 12 对。本次归档核实 {len(scope)} 对，包含 {len(complete)} 份 C/D 正式终点、第三章 24 份 A/B 原始记录及四份确定性 E 参照。"
        + (" 缺少正式终点的单元为 " + "、".join(missing) + "。" if missing else ""), "",
        "A 与 B 使用第三章原初解，C 与 D 使用第四章 Q4 初解。A、C 使用普通邻域，B、D 使用关键区间反馈。E 从 Q4 初解运行第四章 ThermalUnion。", "",
        "下表给出同一种子最终能耗的差值。单位为 mJ，表中为有效配对的中位数及范围。A−B、C−D 为正时反馈组能耗较低，D−E 为正时 E 能耗较低。", "",
        "| 工况 | 有效对数 | 原初解 A−B | Q4 初解 C−D | 普通邻域 A−C | 反馈邻域 B−D | D−E |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for case in cases:
        group = [r for r in pairs if r["case"] == case]
        cols = [interval_text(group, f"final_{contrast}_mJ") if group else "—" for contrast in ("A_B", "C_D", "A_C", "B_D", "D_E")]
        lines.append("| " + " | ".join([case, f"{len(group)}/3", *cols]) + " |")
    cd = Counter(r["final_C_D_verdict"] for r in pairs)
    de = Counter(r["final_D_E_verdict"] for r in pairs)
    lines.extend(["", "## 配对证据", "",
        f"以双方认证能耗区间判定，Q4 初解上反馈组低于普通组 {cd['A_HIGHER']} 对，高于普通组 {cd['B_HIGHER']} 对，区间重叠 {cd['INTERVAL_OVERLAP']} 对。D 的终点低于 E {de['B_HIGHER']} 对，高于 E {de['A_HIGHER']} 对，区间重叠 {de['INTERVAL_OVERLAP']} 对。每个工况的 E 为同一个确定性参照。", "",
        "逐种子结果、能耗差及其证书区间见 [paired.csv](paired.csv)。[paired_summary.csv](paired_summary.csv) 给出配置阶段和最终阶段的交互差。[matched_rounds.csv](matched_rounds.csv) 列出相同前态、目标与邻域大小的可比轮次。[common_checkpoints.csv](common_checkpoints.csv) 保留共同时间与轮次检查点，超出实测轨迹的时间点记为截尾。", "",
        "对原配置与目标配置均相同的单请求动作，F1 的超期数从第三章初解的 69/69 降至 Q4 的 0/69，F2 从 0/60 升至 24/60。各类别的分母和幅度分层见[固定初解对照](../fixed_initial/README.md)。", "",
        *mechanism_summary(analysis, pairs, cases),
        "## 计时与中断", "",
        f"{len(complete)} 份完整回执的计费时间合计 {sum(r['charged_s'] for r in complete):.2f} 秒。每个单元的 900 秒上限包含该工况一次共享 Q4 构造的实测时长。本批串行运行 C/D，A/B 来自历史正式批次，E 复用已认证终点。E 的同机耗时本批未测。", "",
        f"按实际启动记录去重，共 {len(runs)} 次正式启动，其中 {len(lost)} 次中断且没有最终回执。"
        + ("另有非完成回执 " + "、".join(f"{status} {n} 份" for status, n in sorted(failed.items())) + "。" if failed else "")
        + f"无最终回执的启动在日志中累计记录了至少 {sum(r['last_recorded_s'] for r in lost):.2f} 秒。各次独立列入 [attempts.csv](attempts.csv)，共享初解池、短预检另存于原始证据。", "",
        "## 复核", "",
        f"[audit.json](audit.json) 汇总排程身份、认证能耗区间、期限与预算的核对结果。此次离线复核读取原核证书。原始证据包含 {nfiles} 个文件，按工况和元数据分片，均已逐字节验证可还原。分片清单见 [archive/manifest.json](archive/manifest.json)。"])
    (out / "README.md").write_text("\n".join(lines) + "\n", encoding="utf8", newline="\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run", "repo", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    target = args.out.resolve()
    if target.exists() or target.is_relative_to(args.run.resolve()):
        raise ValueError("Choose a new release directory outside the original evidence")
    target.parent.mkdir(exist_ok=True, parents=True)
    with tempfile.TemporaryDirectory(prefix=".ch4-release-", dir=target.parent) as temp:
        stage = Path(temp) / "release"
        main(args.run, args.repo, stage)
        stage.rename(target)
