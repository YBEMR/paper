"""Render per-case and descriptive tables, keeping the published eight separate."""
import csv
from pathlib import Path
from statistics import median
from audit_holdout import BASE, DATA, HERE, METHODS, PAIRS, assessments, cases, comparison, write_csv

def read_rows(path):
    with path.open() as f:
        return list(csv.DictReader(f))

def fmt(x,n=3):
    return f"{float(x):.{n}f}" if x not in ("",None) else "—"

def md(cols, rows):
    return "\n".join(["| "+" | ".join(cols)+" |","|"+"|".join("---" for _ in cols)+"|",
                      *["| "+" | ".join(map(str,row))+" |" for row in rows]])

def main():
    holdout=read_rows(DATA/"results.csv")
    archived=read_rows(BASE/"data/ablation.csv")
    names=["V"+label[1:]+"_"+word for label,word in cases()]
    summaries=[]; statistics=[]
    for batch,rs in (("development8",archived),("holdout6",holdout)):
        lookup={(r["case"],r["method"],r["mode"]):r for r in rs}
        pairs=[]
        for case in dict.fromkeys(r["case"] for r in rs):
            for A,B in PAIRS+(("NT","BT"),("BT","HT")):
                for mode in (("fixed",) if "BT" in (A,B) else ("fixed","time")):
                    def as_num(m):
                        r=lookup[case,m,mode].copy()
                        for k in ("SAFE_J","E_low","E_high"):
                            r[k]=float(r[k]) if r[k] else None
                        return r
                    pairs.append(comparison(as_num(A),as_num(B)))
        summaries.extend(dict(batch=batch,**g) for g in assessments(pairs).values())
        for mode in ("fixed","time"):
            for method in METHODS:
                z=[r for r in rs if r["method"]==method and r["mode"]==mode]
                if not z:continue
                def med(col):
                    vals=[float(q[col]) for q in z if q.get(col)]
                    return median(vals) if vals else None
                statistics.append(dict(batch=batch,mode=mode,method=method,success=sum(bool(q["SAFE_J"]) for q in z),
                    cases=len(z),SAFE_cert=sum(int(q["SAFE"]) for q in z),completed=sum(int(q["completed"]) for q in z),
                    median_first_SAFE_s=med("first_SAFE_s"),median_time_s=med("observed_s"),median_build_s=med("build_and_rank_s"),
                    median_cert_s=med("cert_and_write_s"),median_terminal=med("terminal_unique")))
    write_csv("cohort_comparisons.csv",summaries)
    write_csv("method_summary.csv",statistics)
    lines=["# 六条独立留出逐工况结果",
        "能耗和峰温来自同一份最佳 SAFE 证书。若没有 SAFE，单列送验计划的最低峰温上界；若没有及时完成送验，则相应数值缺失。首次与总时从空搜索计，建池含前缀与终端排序，认证含物理回放及证据落盘。等时按操作与预算窗口的交集分解开销。总时含额外的循环控制。实停为整条轨迹的实际结束时刻，越过预算后才完成的认证只计入原始日志。提案和合法数按已完成频率组统计，终池为已就绪终端池去重后的完整计划数。"]
    for case in names:
        lines.append("## "+case[1:].replace("_"," · "))
        for mode,title in (("fixed","固定束宽四、认证四次"),("time","等实际时间")):
            lines.append("### "+title)
            z=[r for r in holdout if r["case"]==case and r["mode"]==mode]
            ordered=("NC","OT","NT","HT","C2","OC","BT")
            vals=[]
            for r in sorted(z,key=lambda x:ordered.index(x["method"])):
                vals.append([r["method"],fmt(r["SAFE_J"],6),fmt(r["peak_C"]),fmt(r["lowest_cert_peak_C"]),r["SAFE"]+"/"+r["completed"],
                    fmt(r["first_SAFE_s"]),fmt(r["observed_s"]),fmt(r["build_and_rank_s"]),fmt(r["cert_and_write_s"]),
                    *([fmt(r["full_run_s"]),r["ready_widths"] or "—"] if mode=="time" else []),
                    r["proposed"]+"/"+r["valid"],r["terminal_unique"]])
            lines.append(md(["方法","最低 SAFE J","该解峰温 °C","最低送验峰温 °C","SAFE/完成","首次 SAFE s","总时 s",
                             "建池 s","认证 s"]+(["实停 s","就绪束宽"] if mode=="time" else [])+["提案/合法","终池"],vals))
    lines.append("[逐次认证](data/certifications.csv) · [各预算指标 CSV](data/results.csv) · [完整证书及候选日志](evidence/)")
    (HERE/"per_case.md").write_text("\n\n".join(lines)+"\n")
if __name__=="__main__":
    main()
