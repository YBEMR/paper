"""Render the full native endpoints and all three quality observations."""
import csv
import json
from pathlib import Path
from statistics import median

ROOT=Path(__file__).resolve().parent

def read(name):
    with (ROOT/"data"/name).open() as f:
        return list(csv.DictReader(f))


def main():
    runs=read("runs.csv")
    points=read("checkpoints.csv")
    cases=list(dict.fromkeys(r["case"] for r in runs))
    end={(r["case"],r["method"]):r for r in runs}
    cut={(r["case"],r["method"],int(r["budget_s"])):r for r in points}
    lines=["# 独立构造终点与公开工况质量曲线","",
           "每格给出从空运行得到的结果。独立算法一旦结束即停止；预算曲线在之后保持已认证最低值。NC、OT 等 M1-f 方法不计入本轮六组。","",
           "## 文献适配各自运行到自然终点","","Zhou、Li 的格子为未构造成功时已放主任务数 / 应放主任务数，以及实际秒数。ZQ、LQ 的格子为自然输出（SAFE 能耗 J 或状态），以及包含物理证书写盘的实际秒数。LQ 表示逆序窗口阶段后的输出。","",
           "| 请求与轻重次序 | Zhou（已放/应放；s） | Li（已放/应放；s） | ZQ（终点；s） | LQ（终点；s） |",
           "|---|---:|---:|---:|---:|"]
    for c in cases:
        vals=[];n=int(c[1:].split("_")[0])
        for m in ("Zhou","Li","ZQ","LQ"):
            row=end[c,m];stats=json.loads(row["stats"])
            if row["final_status"]=="NO_CONSTRUCTION" and m in ("Zhou","Li"):
                desc=f'{n-stats["unplaced_main"]}/{n}'
            elif row["final_status"]=="SAFE":
                desc=f'{float(row["natural_E_J"]):.4f}'
            else:
                desc={"NO_CONSTRUCTION":"未构成","HOT":"HOT"}[row["final_status"]]
            vals.append(desc+f'；{float(row["actual_s"]):.3f}')
        lines.append("| "+" | ".join([c[1:].replace("_"," · ")]+vals)+" |")
    for phase,title in (("development8","八条开发次序"),("former_holdout6","六条原留出次序")):
        lines.extend(["","## "+title,"",f"![完整 SAFE 能耗阶梯](figures/{phase}.png)","",
           "每格为 10 / 30 / 60 秒的最低 SAFE 能耗（J）。— 表示该时刻无 SAFE。Zhou 和 Li 在全部截面均无完整证书，在图中标明。每个点是一次真实认证后的改善，首解前留白。","",
           "| 工况 | NT | 原始 C2 | ZQ | LQ |","|---|---:|---:|---:|---:|"])
        for c in cases:
            if end[c,"NT"]["phase"]!=phase:
                continue
            vals=[]
            for m in ("NT","C2","ZQ","LQ"):
                v=[cut[c,m,t]["SAFE_J"] for t in (10,30,60)]
                vals.append(" / ".join(f"{float(x):.4f}" if x else "—" for x in v))
            lines.append("| "+" | ".join([c[1:].replace("_"," · ")]+vals)+" |")
    lines.extend(["","各截面的首次 SAFE、峰温、期限、能量上下界、认证次数和计划哈希见[截面数据](data/checkpoints.csv)。每次调用见[认证账本](data/calls.csv.gz)，逐工况配对见[配对表](data/paired.csv)。",""])
    (ROOT/"results.md").write_text("\n".join(lines),encoding="utf8")

if __name__=="__main__":
    main()
