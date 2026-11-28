"""Audit physical evidence offline; distinguish model outcomes from incomplete execution."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "stage1"
CODES = "A01 A02 A03 A04 A05 A06 B07 B08 C09 C10 C11 C12".split()

def read(path):
    return json.loads(path.read_bytes())

def audited(folder, stage, mapping):
    record = folder / (stage + ".json")
    if not record.exists():
        return {}, "未交付"
    value = read(record)
    assert value["mapping_sha"] == hashlib.sha256(mapping).hexdigest()
    p = value["point"]
    if p is None:
        return {}, value["reason"]
    paths = list((folder / stage / "evidence").glob("*/" + p["plan"]))
    assert len(paths) == 1
    path = paths[0]
    plan = (path / "plan.json").read_bytes()
    assert hashlib.sha256(plan.strip()).hexdigest() == p["plan"]
    assert bytes(r[0] for r in json.loads(plan)["rows"][1::3]) == mapping
    cert = read(path / "certificate.json")
    assert cert["plan_sha256"] == p["plan"] and cert["metrics"]["E_bounds"] == p["bounds"]
    assert cert["metrics"]["status"] == p["status"] and cert["metrics"]["E_J"] == p["J"]
    with np.load(path / "trace.npz") as file:
        a = file["events"]
        assert a.shape[1] == 31 and np.isfinite(a).all() and a[0,0] == 0
        assert np.all(a[:,1] > a[:,0]) and np.array_equal(a[:-1,1], a[1:,0])
    return p, p["status"]

def main():
    rows = []
    for code in CODES:
        folder = OUT / "cases" / code
        hp = OUT / "history" / (code + ".json")
        history = read(hp)["point"] if hp.exists() else {}
        mp = OUT / "inputs" / (code + ".bin")
        mapping = mp.read_bytes() if mp.exists() else b""
        a, sa = audited(folder, "ordinary", mapping)
        b, sb = audited(folder, "thermal", mapping)
        if sa not in ("SAFE", "HOT") and sb == "未交付":
            sb = "无合法普通轨迹" if sa != "未交付" else "未执行"
        best = min((p for p in (a,b) if p.get("status") == "SAFE"),key=lambda p:p["J"],default={})
        delta = best["J"] - history["J"] if best else None
        strict = ("更省" if best["bounds"][1] < history["bounds"][0] else
                  "更耗" if history["bounds"][1] < best["bounds"][0] else "区间重叠") if best else "缺失"
        rows.append(dict(case=code,historical_J=history.get("J"),ordinary=sa,ordinary_J=a.get("J"),
                         thermal=sb,thermal_J=b.get("J"),best_SAFE_J=best.get("J"),delta_J=delta,
                         strict=strict,peak_upper_C=best.get("peak"),slack_ms=best.get("slack"),
                         plan=best.get("plan"),original_plan=history.get("plan")))
    with (OUT / "results.csv").open("w",newline="",encoding="utf-8") as stream:
        w=csv.DictWriter(stream,fieldnames=rows[0],lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    n=sum(r["best_SAFE_J"] is not None for r in rows)
    receipt=OUT/"receipt.json"
    passed=n==12 and receipt.exists()
    elapsed=read(receipt)["elapsed_s"] if receipt.exists() else None
    assert elapsed is None or elapsed <= 120
    (OUT/"gate.json").write_text(json.dumps(dict(passed=passed,safe=n,elapsed_s=elapsed))+"\n")
    def num(v):return "—" if v is None else f"{v:.6f}"
    report=["# 映射优先的嵌套电热优化", "",
            f"十二条代表性最终排程中，仅给出主设备分配，独立求得 SAFE 的有 {n} 条。",
            "已满足启动四流配对比较的条件。" if passed else "第二阶段保持关闭。缺少阶段记录的行按执行未完成登记。",
            "", "## 独立调频", "",
            "每条流固定取冻结第三轮正式版本的第一次重复。历史排程在读档时投影为逐请求设备字节；普通动态规划从零构造频率，重建 CPU 前处理、主计算与 CPU 后处理。合法普通轨迹驱动一次温度修正。两个候选分别经过连续电热认证，其中能耗最低的 SAFE 作为结果。差值取新减旧，负数表示节能。",
            "", "|流|原 SAFE（J）|普通调频|普通（J）|温度修正|修正（J）|最佳 SAFE（J）|差值（J）|证书比较|",
            "|---|---:|---|---:|---|---:|---:|---:|---|"]
    for r in rows:
        report.append("|"+"|".join([r["case"],num(r["historical_J"]),r["ordinary"],num(r["ordinary_J"]),
                     r["thermal"],num(r["thermal_J"]),num(r["best_SAFE_J"]),num(r["delta_J"]),r["strict"]])+"|")
    report += ["", f"普通调频直接取得 SAFE {sum(r['ordinary']=='SAFE' for r in rows)} 条，温度修正首次取得 SAFE {sum(r['ordinary']!='SAFE' and r['thermal']=='SAFE' for r in rows)} 条。相对同映射历史端点，证书区间确认能耗升高 {sum(r['strict']=='更耗' for r in rows)} 条。",
               "", "该比较衡量已知优质映射上的频率求解能力。由负载均衡起点能找到哪些映射，需要端到端实验判定。",
               "", f"单核总耗时 {num(elapsed)} 秒，上限 120 秒。逐流输入、历史来源、动态规划日志、三阶段排程、证书和温度轨迹在 [stage1](stage1)。"]
    (ROOT/"REPORT_zh.md").write_text("\n".join(report)+"\n",encoding="utf-8")

if __name__=="__main__":
    main()
