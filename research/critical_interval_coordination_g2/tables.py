"""Render the report tables directly from the reviewed certified comparisons."""
import csv,json
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from pathlib import Path
from statistics import median
ROOT=Path(__file__).resolve().parent
def read_csv(n):
    with (ROOT/n).open(encoding="utf8",newline="") as f:return list(csv.DictReader(f))
def table(columns,rows):
    return "\n".join(["| "+" | ".join(columns)+" |","|"+"|".join(["---"]*len(columns))+"|",*["| "+" | ".join(map(str,row))+" |" for row in rows]])
def number(x,d=6):return f"{float(x):.{d}f}" if x not in (None,"") else "未决"


def endpoint(value, upper, digits=10):
    rounding = ROUND_CEILING if upper else ROUND_FLOOR
    return format(Decimal(value).quantize(Decimal(1).scaleb(-digits), rounding=rounding), "f")
def render():
    runs=read_csv("summary.csv");pairs=read_csv("paired.csv");construction=read_csv("construction.csv")
    assert len(runs)==40 and len(pairs)==14
    by={(r["batch"],r["case"],r["seed"],r["method"]):r for r in runs}
    lines=["## 核心消融的完整配对","每行使用同一初解。能耗单位为 J，差额用 mJ 表示，正数表示关键区间反馈更节能。"]
    detail=[];stages=[]
    for case in ("S32","S80","D1","D2"):
        for seed in ("101","102","103"):
            x=next(p for p in pairs if (p["batch"],p["case"],p["seed"])==("main",case,seed))
            ab=by["main",case,seed,"AB"];pro=by["main",case,seed,"Proposed"]
            detail.append([case,seed,number(pro["initial_J"]),number(x["compact_final_J"]),number(x["final_AB_J"]),
                           number(x["final_Proposed_J"]),number(1000*float(x["final_AB_minus_Proposed_J"]),4) if x["final_AB_minus_Proposed_J"] else "未决",x["final_verdict"]])
            stages.append([case,seed,number(1000*float(x["config_AB_minus_Proposed_J"]),4),
                           number(1000*float(ab["post_gain_J"]),4) if ab["post_gain_J"] else "未决",
                           number(1000*float(pro["post_gain_J"]),4) if pro["post_gain_J"] else "未决",
                           pro["config_main_changes"],pro["realized_compensation_rounds"]])
    lines.append(table(["实例","种子","共同初解","Compact","AB","Proposed","AB − Proposed (mJ)","认证判定"],detail))
    lines+=["## 配置阶段与共同后处理",
            table(["实例","种子","配置阶段 AB − Proposed (mJ)","AB 后处理节能 (mJ)","Proposed 后处理节能 (mJ)","Proposed 改变 main 配置数","实际改变补偿任务的轮数"],stages)]
    strong=[]
    for x in pairs:
        if x["batch"]!="strong":continue
        p=by["strong",x["case"],x["seed"],"Proposed"]
        strong.append([x["case"],number(p["initial_J"]),number(x["config_AB_J"]),number(x["config_Proposed_J"]),
                      number(x["final_AB_J"]),number(x["final_Proposed_J"]),x["final_verdict"]])
    lines+=["## 强初解诊断","各方法使用种子 101，墙钟上限 600 秒。",table(["实例","初解","AB 配置终点","Proposed 配置终点","AB 最终","Proposed 最终","判定"],strong)]
    inits=[]
    for x in construction:
        attempts=json.loads((ROOT/"runs"/("init_"+x["case"])/"construction.json").read_bytes())
        inits.append([x["case"],x["status"],number(x["J"]) if x["J"] else "无完整排程",max(a["depth"] for a in attempts),number(x["seconds"],2)])
    lines+=["## 自动构造与规模",table(["实例","构造状态","共同初解 (J)","最深完成请求数","构造墙钟 (s)"],inits)]
    lines.extend(quality_tables(runs, pairs))
    return "\n\n".join(lines)


def quality_tables(runs, pairs):
    comparison, safety = [], []
    for case in ("S32", "S80", "D1", "D2"):
        arm = [r for r in runs if r["batch"] == "main" and r["method"] == "Proposed"
               and r["case"] == case and r["final_J"]]
        rows = [r for r in pairs if r["batch"] == "main" and r["case"] == case]
        deltas = [1000 * float(r["final_AB_minus_Proposed_J"]) for r in rows
                  if r["final_AB_minus_Proposed_J"]]
        comparison.append([case, len(deltas), sum(r["final_verdict"] == "Proposed严格更低" for r in rows),
                           sum(r["final_verdict"] == "AB严格更低" for r in rows),
                           number(min(deltas), 4), number(median(deltas), 4), number(max(deltas), 4)])
        best = min(arm, key=lambda r: float(r["final_hi"]))
        safety.append([case, best["seed"], endpoint(best["final_lo"], False), endpoint(best["final_hi"], True),
                       number(best["total_gain_J"], 7), endpoint(best["lower_J"], False, 7),
                       endpoint(best["final_peak_C"], True, 3), endpoint(best["final_slack_ms"], False, 3)])
    return ["## 种子稳定性",
            "仅统计双方均有最终回执的种子。最小、中位和最大值均为配对差额 AB − Proposed，单位 mJ。",
            table(["实例", "完整配对数", "Proposed 严格胜", "AB 严格胜", "最小", "中位", "最大"], comparison),
            "## 最佳 Proposed 计划的认证与质量下界",
            "每个主实例在有最终回执的种子中按连续 SAFE 上界取最小。显示的认证区间向外取整，质量下界为全物理域解析界。",
            table(["实例","种子","认证下端 (J)","认证上端 (J)","相对初解节能 (J)","质量下界 (J)",
                   "峰温上界 (°C)","最小期限余量 (ms)"], safety)]
